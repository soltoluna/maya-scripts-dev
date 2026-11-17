# -*- coding: utf-8 -*-
"""Penetration Checker — シーンを読む層（Maya 依存）。

**シーンを一切変更しない。** 読むのは頂点座標・最近接点・スキンウェイト・
接続だけで、判定と集計は `core` に任せる。 ここは「Maya から値を取ってきて
`core` に関数として渡す」だけに保つ（自宅で検証できないコードを薄くするため）。

座標はすべて **Maya の内部単位（cm）のワールド空間**で扱う。 OpenMaya の
`getPoints(kWorld)` は UI の単位設定に関係なく内部単位で返すので、
`cmds.exactWorldBoundingBox`（UI 単位）と混ぜない。 ボックスも点から作る。
許容値と深さの表示だけ `MDistance` で UI 単位と変換する。

実機の戻り値が想定と違ったときのために `diagnose()` を置いてある。
"""

from __future__ import annotations

from maya import cmds
from maya.api import OpenMaya as om

from . import core


# 接続を辿るときに無視する入力アトリビュート。 これらはジョイントの動きの
# 「出どころ」ではない（親ジョイントの scale・表示レイヤー・セットなど）
_IGNORED_DEST_ATTRS = frozenset((
    "message", "inverseScale", "drawOverride", "instObjGroups",
    "lockInfluenceWeights", "bindPose", "objectColorRGB", "useObjectColor",
    "hiddenInOutliner", "isHistoricallyInteresting",
))

# 1 組のめり込みにつき、スキンウェイトを問い合わせる頂点数の上限（深い順）
_WEIGHT_SAMPLE_LIMIT = 200


# --------------------------------------------------------------------------- #
# 対象メッシュの列挙
# --------------------------------------------------------------------------- #

def expand_meshes(nodes, skip_hidden=True):
    """指定ノード（グループ可）の配下にあるメッシュのトランスフォームを返す。

    中間オブジェクト（スキンの元形状など）は除く。 重複は 1 つにまとめ、
    フルパスで返す。
    """
    found = []
    seen = set()
    for node in nodes or []:
        if not cmds.objExists(node):
            continue
        shapes = []
        if cmds.nodeType(node) == "mesh":
            shapes.append(node)
        shapes.extend(cmds.listRelatives(node, allDescendents=True, type="mesh",
                                         fullPath=True, noIntermediate=True) or [])
        for shape in shapes:
            if cmds.getAttr(shape + ".intermediateObject"):
                continue
            parent = (cmds.listRelatives(shape, parent=True, fullPath=True) or [None])[0]
            if not parent or parent in seen:
                continue
            if skip_hidden and not _is_visible(shape):
                continue
            seen.add(parent)
            found.append(parent)
    return found


def _dag_path(node):
    sel = om.MSelectionList()
    sel.add(node)
    return sel.getDagPath(0)


def _shape_path(transform):
    # extendToShape() は使わない。 スキンされたメッシュは中間オブジェクト
    # （ShapeOrig）も持つので、シェイプが 2 つになって失敗しうる
    shapes = cmds.listRelatives(transform, shapes=True, type="mesh",
                                fullPath=True, noIntermediate=True) or []
    if not shapes:
        raise RuntimeError("no mesh shape under %s" % transform)
    return _dag_path(shapes[0])


def _is_visible(node):
    try:
        return _dag_path(node).isVisible()
    except Exception:
        return True


# --------------------------------------------------------------------------- #
# メッシュの読み取り
# --------------------------------------------------------------------------- #

class _MeshData(object):
    """1 メッシュ分の読み取り結果。 判定のあいだ使い回す。"""

    def __init__(self, transform):
        self.transform = transform
        self.shape_path = _shape_path(transform)
        self.shape = self.shape_path.fullPathName()
        self.fn = om.MFnMesh(self.shape_path)
        self.points = [(p.x, p.y, p.z)
                       for p in self.fn.getPoints(om.MSpace.kWorld)]
        self.bbox = core.bbox_of_points(self.points)
        self._closed = None

    def is_closed(self):
        """境界エッジが 1 本も無ければ閉じたメッシュ。"""
        if self._closed is None:
            closed = True
            it = om.MItMeshEdge(self.shape_path)
            while not it.isDone():
                if it.onBoundary():
                    closed = False
                    break
                it.next()
            self._closed = closed
        return self._closed

    def closest(self, point):
        try:
            hit, normal, _face = self.fn.getClosestPointAndNormal(
                om.MPoint(point[0], point[1], point[2]), om.MSpace.kWorld)
        except Exception:
            return None
        return (hit.x, hit.y, hit.z), (normal.x, normal.y, normal.z)


# --------------------------------------------------------------------------- #
# スキン
# --------------------------------------------------------------------------- #

def find_skin_cluster(shape):
    history = cmds.listHistory(shape, pruneDagObjects=True) or []
    clusters = cmds.ls(history, type="skinCluster") or []
    return clusters[0] if clusters else None


def _weights_fn(skin, shape):
    def weights(index):
        component = "%s.vtx[%d]" % (shape, index)
        try:
            names = cmds.skinPercent(skin, component, q=True, transform=None,
                                     ignoreBelow=1e-4) or []
            values = cmds.skinPercent(skin, component, q=True, value=True,
                                      ignoreBelow=1e-4) or []
        except Exception:
            return {}
        out = {}
        for name, value in zip(names, values):
            long_name = (cmds.ls(name, long=True) or [name])[0]
            out[long_name] = out.get(long_name, 0.0) + float(value)
        return out
    return weights


# --------------------------------------------------------------------------- #
# コントローラーの探索（グラフを core に渡す）
# --------------------------------------------------------------------------- #

def _long(node):
    return (cmds.ls(node, long=True) or [node])[0]


def sources_of(node):
    """`node` の入力接続の元ノード（無視するアトリビュートを除く）。"""
    pairs = cmds.listConnections(node, source=True, destination=False,
                                 connections=True, plugs=True,
                                 skipConversionNodes=True) or []
    out = []
    for dest, src in zip(pairs[0::2], pairs[1::2]):
        attr = dest.split(".", 1)[-1].split("[", 1)[0]
        if attr in _IGNORED_DEST_ATTRS:
            continue
        src_node = _long(src.split(".", 1)[0])
        if src_node not in out:
            out.append(src_node)
    return out


def parent_of(node):
    """DAG の親。 **ジョイントからは親を辿らない**（親ジョイントのコントローラーを
    拾ってしまうため。 ジョイントは入力接続からだけ辿る）。"""
    try:
        if cmds.nodeType(node) == "joint":
            return None
        if not cmds.objectType(node, isAType="dagNode"):
            return None
    except Exception:
        return None
    return (cmds.listRelatives(node, parent=True, fullPath=True) or [None])[0]


def is_controller(node):
    """コントローラーとみなすか。

    次のどちらかを満たすトランスフォーム:
      * コントローラータグ（`controller` ノード）が付いている
      * 中間オブジェクトでない NURBS カーブのシェイプを持つ
    """
    try:
        if not cmds.objectType(node, isAType="transform"):
            return False
        if cmds.listConnections(node + ".message", type="controller",
                                source=False, destination=True):
            return True
        curves = cmds.listRelatives(node, shapes=True, type="nurbsCurve",
                                    fullPath=True, noIntermediate=True)
        return bool(curves)
    except Exception:
        return False


def resolve_target(node):
    """`node`（インフルエンス or メッシュ）を選ぶべきノードに直す。

    戻り値 `(target, kind, path)`。 コントローラーが見つからなければ
    `node` 自身（ジョイントなら `"joint"`）を返す。
    """
    ctrl, path = core.find_controller(node, sources_of, parent_of, is_controller)
    if ctrl:
        return ctrl, "controller", path
    kind = "joint" if cmds.nodeType(node) == "joint" else "transform"
    return node, kind, [node]


# --------------------------------------------------------------------------- #
# 判定本体
# --------------------------------------------------------------------------- #

def check(nodes, tolerance_ui=0.0, use_open_containers=False, skip_hidden=True,
          progress=None):
    """めり込みを調べて結果を返す。 シーンは変更しない。

    * `tolerance_ui` — UI 単位の許容深さ
    * `use_open_containers` — 開いたメッシュ（境界エッジがある）も「内側」を
      持つものとして扱うか。 既定では閉じたメッシュだけを入れ物にする
    * `progress(done, total, label) -> bool` — False を返すと中断する

    戻り値:
        {"meshes": [...], "pairs": [(a, b), ...], "hits": [...],
         "targets": core.aggregate_targets(...) の戻り値,
         "warnings": [...], "cancelled": bool}

    `hits` の要素は `{"mesh", "other", "vertices": [(index, depth), ...]}`
    （`mesh` の頂点が `other` の内側にある）。 深さは内部単位（cm）。
    """
    tolerance = om.MDistance.uiToInternal(float(tolerance_ui))
    result = {"meshes": [], "pairs": [], "hits": [], "targets": [],
              "warnings": [], "cancelled": False}

    meshes = expand_meshes(nodes, skip_hidden=skip_hidden)
    result["meshes"] = meshes
    if len(meshes) < 2:
        result["warnings"].append("メッシュが 2 つ以上必要です（%d 個）" % len(meshes))
        return result

    data = {}
    for transform in meshes:
        try:
            data[transform] = _MeshData(transform)
        except Exception as exc:
            result["warnings"].append("%s を読めませんでした: %s"
                                      % (core.short_name(transform), exc))
    bboxes = {name: d.bbox for name, d in data.items()}
    pairs = core.candidate_pairs(bboxes, margin=tolerance)
    result["pairs"] = pairs

    open_skipped = set()
    total = len(pairs)
    for done, (a, b) in enumerate(pairs):
        if progress and not progress(done, total, "%s / %s" % (
                core.short_name(a), core.short_name(b))):
            result["cancelled"] = True
            break
        for mesh, other in ((a, b), (b, a)):
            container = data[other]
            if not use_open_containers and not container.is_closed():
                open_skipped.add(other)
                continue
            vertices = core.find_inside_vertices(
                data[mesh].points, container.bbox, container.closest, tolerance)
            if vertices:
                result["hits"].append({"mesh": mesh, "other": other,
                                       "vertices": vertices})

    for name in sorted(open_skipped):
        result["warnings"].append(
            "%s は開いたメッシュなので、めり込まれる側としては調べていません"
            % core.short_name(name))

    result["targets"] = core.aggregate_targets(_contributions(result["hits"], data))
    return result


def _contributions(hits, data):
    contributions = []
    resolved = {}
    for hit in hits:
        mesh = hit["mesh"]
        shape = data[mesh].shape
        vertices = hit["vertices"]
        skin = find_skin_cluster(shape)
        if skin:
            scores = core.influence_scores(vertices, _weights_fn(skin, shape),
                                           limit=_WEIGHT_SAMPLE_LIMIT)
        else:
            # スキンが無いメッシュ（コンストレイントされた小物など）は
            # メッシュ自身から辿る
            scores = core.influence_scores(vertices, lambda _i: {mesh: 1.0},
                                           limit=_WEIGHT_SAMPLE_LIMIT)
        if not scores:
            continue
        # 1 組につき最も効いているインフルエンスを 1 つ選ぶ
        influence, score = core.rank_scores(scores)[0]
        if influence not in resolved:
            resolved[influence] = resolve_target(influence)
        target, kind, _path = resolved[influence]
        contributions.append({
            "target": target, "kind": kind, "score": score,
            "mesh": mesh, "other": hit["other"],
            "count": len(vertices), "depth": vertices[0][1],
        })
    return contributions


def to_ui_distance(value):
    return om.MDistance.internalToUI(value)


def ui_unit():
    return cmds.currentUnit(query=True, linear=True) or ""


# --------------------------------------------------------------------------- #
# 調査関数
# --------------------------------------------------------------------------- #

def _safe(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception as exc:
        return "<ERROR %s: %s>" % (type(exc).__name__, exc)


def diagnose(node=None):
    """コントローラー探索とメッシュの読み取りを Script Editor に出す。

    **シーンを変更しない。 途中で例外を上げず、`<ERROR ...>` を値にして最後まで出す。**
    結果が期待と違ったら、この出力を貼ってもらって直す（推測で直さない）。

    `node` を省略すると選択中のノード（複数可）を調べる。 渡すと良いもの:
      * めり込みを見たいメッシュ — スキン・閉じているか・最も効くインフルエンス
      * ジョイント — 上流のどこでコントローラーに当たるか
    """
    targets = [node] if node else (cmds.ls(selection=True, long=True) or [])
    lines = ["=" * 60, "[penetration_checker] diagnose", "=" * 60]
    lines.append("maya: %s / unit: %s" % (_safe(cmds.about, version=True),
                                          _safe(ui_unit)))
    if not targets:
        lines.append("<nothing selected>")
    for target in targets:
        lines.append("-" * 60)
        lines.append("node: %s" % target)
        lines.append("  type: %s" % _safe(cmds.nodeType, target))
        lines.append("  is_controller: %s" % _safe(is_controller, target))
        lines.append("  sources: %s" % _safe(sources_of, target))
        lines.append("  parent_of: %s" % _safe(parent_of, target))
        found = _safe(core.find_controller, target, sources_of, parent_of,
                      is_controller)
        lines.append("  find_controller: %s" % (found,))
        meshes = _safe(expand_meshes, [target], False)
        lines.append("  meshes: %s" % (meshes,))
        if isinstance(meshes, list):
            for mesh in meshes[:5]:
                lines.extend(_diagnose_mesh(mesh))
    lines.append("=" * 60)
    text = "\n".join(lines)
    print(text)
    return text


def _diagnose_mesh(mesh):
    out = ["  mesh: %s" % mesh]
    data = _safe(_MeshData, mesh)
    if isinstance(data, str):
        out.append("    read: %s" % data)
        return out
    out.append("    vertices: %d / bbox(cm): %s" % (len(data.points), data.bbox))
    out.append("    closed: %s" % _safe(data.is_closed))
    if data.points:
        out.append("    closest(v0): %s" % (_safe(data.closest, data.points[0]),))
    skin = _safe(find_skin_cluster, data.shape)
    out.append("    skinCluster: %s" % (skin,))
    if skin and not str(skin).startswith("<ERROR"):
        weights = _safe(_weights_fn(skin, data.shape), 0)
        out.append("    weights(v0): %s" % (weights,))
        if isinstance(weights, dict) and weights:
            top = core.rank_scores(weights)[0][0]
            out.append("    resolve_target(%s): %s"
                       % (core.short_name(top), _safe(resolve_target, top)))
    return out
