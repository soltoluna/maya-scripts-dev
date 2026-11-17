# -*- coding: utf-8 -*-
"""BlendShape Manager — シーンを読み書きする層（Maya 依存）。

`cmds` / OpenMaya を呼ぶのはここだけ。 名前の検証・リネームの手順・
インビトウィーンの重み・ミラーの計算は `core` に任せ、ここは
「Maya から値を取る」「`core` の結果を Maya に書く」だけに保つ。

**ベースは blendShape の 1 本目のジオメトリ（`inputTarget[0]` /
`outputGeometry[0]`）だけを扱う。** 1 つの blendShape に複数のメッシュを
ぶら下げた構成は v0.1.0 では対象外。

**undo チャンクはここでは開かない。** 呼ぶ側（`ui.py`）が 1 操作 = 1 チャンクで
包む。
"""

from __future__ import annotations

import contextlib

from maya import cmds, mel
from maya.api import OpenMaya as om

from . import core


_DELETE_PROC = "blendShapeDeleteTargetGroup"


# --------------------------------------------------------------------------- #
# 読む
# --------------------------------------------------------------------------- #

def list_blendshapes():
    """シーン内の blendShape ノード（名前順）。"""
    return sorted(cmds.ls(type="blendShape") or [])


def find_blendshapes(nodes):
    """選択したメッシュのヒストリにある blendShape（見つかった順・重複なし）。"""
    if not nodes:
        return []
    history = cmds.listHistory(nodes, pruneDagObjects=True) or []
    found = []
    for node in cmds.ls(history, type="blendShape") or []:
        if node not in found:
            found.append(node)
    return found


def base_geometry(bs):
    """blendShape のベース（1 本目）のシェイプ名。 無ければ `None`。"""
    geo = cmds.blendShape(bs, q=True, geometry=True) or []
    return geo[0] if geo else None


def weight_indices(bs):
    return [int(i) for i in (cmds.getAttr(bs + ".weight", multiIndices=True) or [])]


def _item_plug(bs, index):
    return "%s.inputTarget[0].inputTargetGroup[%d].inputTargetItem" % (bs, index)


def _weight_plug(bs, index):
    return "%s.weight[%d]" % (bs, index)


def read_targets(bs):
    """ターゲットの一覧 `[{index, name, inbetweens, items}, ...]`（番号順）。"""
    aliases = core.parse_alias_list(cmds.aliasAttr(bs, q=True))
    result = []
    for index, name in core.target_entries(weight_indices(bs), aliases):
        items = cmds.getAttr(_item_plug(bs, index), multiIndices=True) or []
        result.append({
            "index": index,
            "name": name,
            "items": [int(i) for i in items],
            "inbetweens": core.inbetween_weights(items),
        })
    return result


def weight_plug(bs, index):
    """UI のスライダーをつなぐ属性名。"""
    return _weight_plug(bs, index)


def vertex_count(node):
    """メッシュの頂点数。 メッシュでなければ `None`。"""
    try:
        count = cmds.polyEvaluate(node, vertex=True)
    except RuntimeError:
        return None
    # メッシュ以外を渡すと例外ではなく説明の文字列が返ってくる
    return count if isinstance(count, int) else None


# --------------------------------------------------------------------------- #
# 作る・足す・消す
# --------------------------------------------------------------------------- #

def create(base, targets, name, front_of_chain=True):
    """blendShape を作って名前を返す。 ターゲットは選択順に 0, 1, 2… に入る。"""
    kwargs = {"name": name}
    if front_of_chain:
        kwargs["frontOfChain"] = True
    return cmds.blendShape(*(list(targets) + [base]), **kwargs)[0]


def add_targets(bs, meshes):
    """メッシュをターゲットとして末尾に足す。 足した番号のリストを返す。"""
    base = base_geometry(bs)
    if not base:
        raise RuntimeError("%s にベースジオメトリが無い" % bs)
    indices = weight_indices(bs)
    added = []
    for mesh in meshes:
        index = core.next_free_index(indices)
        cmds.blendShape(bs, e=True, target=(base, index, mesh, 1.0))
        indices.append(index)
        added.append(index)
    return added


def delete_targets(bs, indices):
    """ターゲットを消す。 Shape Editor と同じ MEL 手続きがあればそれを使う。

    手続きの呼び出しに失敗したときは警告して、属性を直接外す方法に落とす
    （安全弁で削除そのものを止めない）。
    """
    use_proc = bool(mel.eval('exists "%s"' % _DELETE_PROC))
    for index in sorted(indices, reverse=True):
        if use_proc:
            try:
                mel.eval('%s("%s", %d)' % (_DELETE_PROC, bs, index))
                continue
            except RuntimeError as exc:
                cmds.warning("[blendshape_manager] %s が失敗したので直接削除する: %s"
                             % (_DELETE_PROC, exc))
        _delete_target_directly(bs, index)


def _delete_target_directly(bs, index):
    aliases = core.parse_alias_list(cmds.aliasAttr(bs, q=True))
    if index in aliases:
        cmds.aliasAttr("%s.%s" % (bs, aliases[index]), remove=True)
    cmds.removeMultiInstance("%s.inputTarget[0].inputTargetGroup[%d]" % (bs, index),
                             b=True)
    cmds.removeMultiInstance(_weight_plug(bs, index), b=True)


def rename_targets(bs, steps):
    """`core.plan_renames` が返した手順どおりにエイリアスを付け替える。"""
    for index, name in steps:
        cmds.aliasAttr(name, _weight_plug(bs, index))


def set_weights(bs, indices, value):
    """ウェイトを一括で設定する。 接続・ロックされているものは飛ばして名前を返す。"""
    skipped = []
    for index in indices:
        plug = _weight_plug(bs, index)
        if (cmds.listConnections(plug, source=True, destination=False)
                or cmds.getAttr(plug, lock=True)):
            skipped.append(plug)
            continue
        cmds.setAttr(plug, float(value))
    return skipped


def add_inbetween(bs, index, mesh, weight):
    base = base_geometry(bs)
    cmds.blendShape(bs, e=True, inBetween=True,
                    target=(base, index, mesh, float(weight)))


# --------------------------------------------------------------------------- #
# ミラー
# --------------------------------------------------------------------------- #

def mirror_target(bs, index, axis="x", tolerance=1e-3, overwrite=True):
    """ターゲットを左右反転した新しいターゲットを作る。

    名前は `core.mirror_name`（`L_smile` → `R_smile`）。 その名前が既にあれば
    `overwrite=True` のときそのターゲットの形を置き換え、`False` なら
    `ValueError`。 戻り値は `{"index", "name", "missing", "replaced"}`。

    形はスライダーの値を一時的に「そのターゲットだけ 1」にして
    blendShape の出力を読むので、**他のデフォーマに関係なく blendShape
    単体の結果**で計算する。 終わったら値と接続を元に戻す。
    """
    targets = {t["index"]: t["name"] for t in read_targets(bs)}
    if index not in targets:
        raise ValueError("%s に番号 %d のターゲットが無い" % (bs, index))
    new_name, _swapped = core.mirror_name(targets[index])

    existing = [i for i, n in targets.items() if n == new_name]
    if existing and not overwrite:
        raise ValueError("%s は既にある" % new_name)

    base_points = _evaluate(bs, solo=None)
    target_points = _evaluate(bs, solo=index)
    mirror_map = core.build_mirror_map(base_points, axis, tolerance)
    points, missing = core.mirror_shape(base_points, target_points, mirror_map, axis)

    base = base_geometry(bs)
    xform = _mesh_from_points(bs, points, new_name + "_tmp")
    try:
        if existing:
            new_index = existing[0]
            cmds.blendShape(bs, e=True, target=(base, new_index, xform, 1.0))
        else:
            new_index = core.next_free_index(weight_indices(bs))
            cmds.blendShape(bs, e=True, target=(base, new_index, xform, 1.0))
            cmds.aliasAttr(new_name, _weight_plug(bs, new_index))
    finally:
        if cmds.objExists(xform):
            cmds.delete(xform)
    return {"index": new_index, "name": new_name, "missing": missing,
            "replaced": bool(existing)}


@contextlib.contextmanager
def _solo_weights(bs, solo=None):
    """スライダーを「`solo` だけ 1、他は 0、envelope 1」にして、抜けるときに戻す。

    コントローラーなどがつながっているスライダーは一時的に外してつなぎ直す。
    """
    plugs = [(_weight_plug(bs, i), 1.0 if i == solo else 0.0)
             for i in weight_indices(bs)]
    plugs.append((bs + ".envelope", 1.0))
    saved = []
    try:
        for plug, value in plugs:
            sources = cmds.listConnections(plug, source=True, destination=False,
                                           plugs=True) or []
            locked = bool(cmds.getAttr(plug, lock=True))
            saved.append((plug, sources[0] if sources else None,
                          cmds.getAttr(plug), locked))
            if sources:
                cmds.disconnectAttr(sources[0], plug)
            if locked:
                cmds.setAttr(plug, lock=False)
            cmds.setAttr(plug, value)
        yield
    finally:
        for plug, source, value, locked in reversed(saved):
            try:
                if source:
                    cmds.connectAttr(source, plug, force=True)
                else:
                    cmds.setAttr(plug, value)
                if locked:
                    cmds.setAttr(plug, lock=True)
            except RuntimeError as exc:
                cmds.warning("[blendshape_manager] %s を元に戻せなかった: %s"
                             % (plug, exc))


def _evaluate(bs, solo=None):
    """blendShape の出力（オブジェクト空間の頂点座標）を読む。"""
    with _solo_weights(bs, solo):
        shape = cmds.createNode("mesh", name="bsmEvalShape")
        xform = cmds.listRelatives(shape, parent=True, fullPath=True)[0]
        try:
            cmds.connectAttr(bs + ".outputGeometry[0]", shape + ".inMesh")
            return _get_points(shape)
        finally:
            cmds.delete(xform)


def _mesh_from_points(bs, points, name):
    """blendShape の出力を複製したメッシュを作り、頂点を `points` に置き換える。"""
    shape = cmds.createNode("mesh", name="bsmSrcShape")
    src = cmds.listRelatives(shape, parent=True, fullPath=True)[0]
    try:
        cmds.connectAttr(bs + ".outputGeometry[0]", shape + ".inMesh")
        cmds.dgeval(shape + ".outMesh")
        # 複製すると入力の無い（形が焼き込まれた）メッシュになる
        xform = cmds.duplicate(src, name=name)[0]
    finally:
        cmds.delete(src)
    dup_shape = cmds.listRelatives(xform, shapes=True, fullPath=True)[0]
    _set_points(dup_shape, points)
    return xform


def _dag_path(node):
    sel = om.MSelectionList()
    sel.add(node)
    return sel.getDagPath(0)


def _get_points(shape):
    cmds.dgeval(shape + ".outMesh")   # 読む前に確実に評価させる
    fn = om.MFnMesh(_dag_path(shape))
    return [(p.x, p.y, p.z) for p in fn.getPoints(om.MSpace.kObject)]


def _set_points(shape, points):
    fn = om.MFnMesh(_dag_path(shape))
    fn.setPoints(om.MPointArray([om.MPoint(p[0], p[1], p[2]) for p in points]),
                 om.MSpace.kObject)
    fn.updateSurface()


# --------------------------------------------------------------------------- #
# 調査（実機の戻り値を貼ってもらう用）
# --------------------------------------------------------------------------- #

def diagnose(bs=None):
    """blendShape の読み取り結果を Script Editor に出して文字列で返す。

    **シーンを変更しない。** 途中で失敗しても `<ERROR ...>` を値にして最後まで出す。
    使い方: `import blendshape_manager.scene as s; s.diagnose("body_BS")`
    """
    lines = []

    def probe(label, func):
        try:
            value = func()
        except Exception as exc:   # noqa: BLE001  調査用なので全部拾って値にする
            value = "<ERROR %s: %s>" % (type(exc).__name__, exc)
        lines.append("%s: %r" % (label, value))
        return value

    probe("maya version", lambda: cmds.about(version=True))
    probe("%s exists" % _DELETE_PROC, lambda: mel.eval('exists "%s"' % _DELETE_PROC))
    nodes = probe("ls(type=blendShape)", list_blendshapes)
    if bs is None and isinstance(nodes, list) and nodes:
        bs = nodes[0]
    if bs:
        probe("target", lambda: bs)
        probe("geometry", lambda: cmds.blendShape(bs, q=True, geometry=True))
        probe("aliasAttr q", lambda: cmds.aliasAttr(bs, q=True))
        probe("weight multiIndices",
              lambda: cmds.getAttr(bs + ".weight", multiIndices=True))
        probe("target (blendShape -q -t)", lambda: cmds.blendShape(bs, q=True, target=True))
        probe("weightCount", lambda: cmds.blendShape(bs, q=True, weightCount=True))
        indices = probe("weight_indices", lambda: weight_indices(bs))
        for index in (indices if isinstance(indices, list) else [])[:20]:
            probe("  [%d] items" % index,
                  lambda i=index: cmds.getAttr(_item_plug(bs, i), multiIndices=True))
            probe("  [%d] weight connections" % index,
                  lambda i=index: cmds.listConnections(_weight_plug(bs, i),
                                                       source=True, destination=False,
                                                       plugs=True))
        probe("read_targets", lambda: read_targets(bs))
    text = "\n".join(["# blendshape_manager diagnose"] + lines)
    print(text)
    return text
