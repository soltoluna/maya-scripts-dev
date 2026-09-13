# -*- coding: utf-8 -*-
"""Color Override — `maya.cmds` による UI と、シェーダー割り当ての操作。

ここは「値を集める → `core` に渡す → 結果を `cmds` に流す」に保つ。
色の作り方・16 進の解釈・ノード名の組み立て・記録の突き合わせは
すべて `core.py`（Maya 非依存）にある。

## オーバーライドの持ち方

対象 1 つにつき `surfaceShader` + `shadingEngine` を 1 組作り、**シェーダー側に
元の shadingEngine 名を文字列属性で書き込む**。 セッション中の Python 辞書に
持たないのは、シーンを保存して開き直したあとも Restore を効かせるため。

    ntk_color_override_<対象名>_SHD   surfaceShader（outColor が表示色）
      .ntkColorOverrideOriginal       元の SG（旧形式・管理対象の目印）
      .ntkColorOverrideTarget         掛けた時点の対象ノード名（表示用）
      .ntkColorOverrideMembers        掛けた相手（シェイプ）
      .ntkColorOverrideOriginals      **それぞれの戻し先** ← 復元の情報源
    ntk_color_override_<対象名>_SG    上をつないだ shadingEngine

**戻し先はメンバーごとに持つ。** グループノードに掛けると中のシェイプは
別々のマテリアルを持ちうるので、1 件につき 1 つでは戻せない（v0.2.0 までは
1 つしか持たず、グループに掛けると全部グレーになった）。

`surfaceShader` を使うのはライティングに影響されないフラットな色になるため。
陰影が乗らないぶん、同系色のオブジェクトの境界（＝貫通している箇所）が
輪郭としてはっきり出る。

**管理対象の判別は名前ではなく `.ntkColorOverrideOriginal` 属性の有無で行う。**
ユーザーがノードをリネームしても追跡できる。

## 一時解除（peek）と Restore の違い

    Hide / Show Colors   対象を元の SG に戻すだけ。 ノードは残すので掛け直せる
    Restore              元の SG に戻したうえでノードごと削除する

**解除中かどうかのフラグは持たない。** shadingEngine にメンバーが居るかどうかが
そのまま状態なので、Maya 側で手作業に割り当てを変えられても表示と食い違わない。
"""

from __future__ import annotations

from maya import cmds

from . import NAMESPACE, __version__, core, dev_tools


# Maya の optionVar / scriptJob / ウィンドウ名はフラットな 1 つの名前空間を
# 共有する。 接頭辞の無いキーは他人のツールと後勝ちで静かに衝突するので、
# 直書きせず `_NS` から組み立てる（CLAUDE.md「ルール」）
_PACKAGE = __package__ or __name__.rsplit(".", 1)[0]
_NS = "%s_%s" % (NAMESPACE, _PACKAGE)            # ntk_color_override

# ウィンドウ名は `<NAMESPACE>_<モジュール名>Win` 固定。 ハブ install.py の
# `_close_existing_window()` が同じ規則で古いウィンドウを探す
WINDOW = _NS + "Win"

_OPTVAR_LAST_COLOR = _NS + "_last_color"         # ntk_color_override_last_color

# シーンに作るノードにも名前空間を付ける。 実機のシーンには他の人が作った
# ノードも同居するため
_NODE_PREFIX = _NS

# オーバーライド用シェーダーに書き込む印。 この属性の有無が管理対象の判定そのもの
_ATTR_ORIGINAL = NAMESPACE + "ColorOverrideOriginal"
_ATTR_TARGET = NAMESPACE + "ColorOverrideTarget"

# 一時解除（peek）中は shadingEngine が空になり、何に掛かっていたのかが
# シーンから読めなくなる。 掛けた相手をシェーダー側に控えておく
_ATTR_MEMBERS = NAMESPACE + "ColorOverrideMembers"

# メンバーと 1 対 1 で対応する戻し先。 グループに掛けると中のシェイプは
# 別々のマテリアルを持ちうるので、_ATTR_ORIGINAL の 1 つでは戻せない。
# v0.2.0 までのシーンにはこの属性が無いので、その場合は _ATTR_ORIGINAL で埋める
_ATTR_ORIGINALS = NAMESPACE + "ColorOverrideOriginals"

# シェーダーを持たないオブジェクトを戻すときの行き先（Maya の既定）
_DEFAULT_SG = "initialShadingGroup"

# 「全メッシュ」でこの数を超えたら一度確認する。 1 オブジェクト = 2 ノードなので、
# 大きいシーンで何も聞かずに走ると戻すのも一苦労になる
_BULK_CONFIRM_THRESHOLD = 50

_DEFAULT_COLOR = core.color_at(0)

_CTRL = {}        # コントロール名の控え。 show() のたびに作り直す
_ROWS = []        # 一覧に出している記録。 行番号 → 記録の対応表


# --------------------------------------------------------------------------- #
# シーンの読み取り
# --------------------------------------------------------------------------- #

def _shapes_of(node):
    """色を割り当てる相手（シェイプ）をフルパスで返す。

    **`listRelatives(shapes=True)` では足りない。** グループノードの子は
    トランスフォームなので直下にシェイプが無く、空が返る。 v0.2.0 までは
    その場合にノード自身へフォールバックしていたため、**グループに掛けると
    「元の shadingEngine が見つからない」→ `initialShadingGroup` を元として
    記録**し、Restore で中身が全部グレーになった（v0.3.0 で修正）。

    `ls(dag=True, shapes=True)` は部分木をたどるので、グループでも中の
    シェイプを全部拾う（ノード自身がシェイプならそれを返す）。
    """
    shapes = cmds.ls(node, dag=True, shapes=True, noIntermediate=True,
                     long=True) or []
    return shapes or [node]


def _shading_engine_of(shape):
    """シェイプに割り当たっている shadingEngine（最初の 1 つ）。"""
    found = cmds.listConnections(shape, type="shadingEngine") or []
    return found[0] if found else _DEFAULT_SG


def _is_override_shader(shader):
    """このツールが作ったシェーダーか（名前ではなく属性で判定する）。"""
    if not shader:
        return False
    return bool(cmds.attributeQuery(_ATTR_ORIGINAL, node=shader, exists=True))


def _read_attr(node, attr, default=""):
    """文字列属性を読む。 読めなければ `default`。"""
    try:
        value = cmds.getAttr("%s.%s" % (node, attr))
    except Exception:
        return default
    return default if value is None else value


def _collect_records():
    """シーンにある全オーバーライドを記録の一覧として返す。

    情報源はシーンのノードそのもの。 Python 側にキャッシュを持たないので、
    シーンを開き直したあとでも、他のツールで消されたあとでも実態と食い違わない。
    """
    records = []
    for shader in cmds.ls(type="surfaceShader", long=True) or []:
        if not _is_override_shader(shader):
            continue
        shading_engines = cmds.listConnections(shader + ".outColor",
                                               type="shadingEngine") or []
        members = []
        for shading_engine in shading_engines:
            members.extend(cmds.sets(shading_engine, q=True) or [])
        color = cmds.getAttr(shader + ".outColor") or [(0.0, 0.0, 0.0)]

        # **色が出ているかは shadingEngine にメンバーが居るかで決まる。**
        # フラグを別に持たないので、Maya 側で手作業に割り当てを変えられても
        # 一覧が実態と食い違わない
        stored = core.split_members(_read_attr(shader, _ATTR_MEMBERS))
        legacy = _read_attr(shader, _ATTR_ORIGINAL, _DEFAULT_SG)

        # **元の SG はメンバーごとに控える**（グループに掛けると中の
        # シェイプは別々のマテリアルを持ちうる）。 v0.2.0 までのシーンには
        # この属性が無いので、旧形式の単一値で埋める
        known = dict(core.align_originals(
            stored, core.split_members(_read_attr(shader, _ATTR_ORIGINALS)),
            legacy))
        live = members or stored

        records.append({
            "shader": shader,
            "sg": shading_engines[0] if shading_engines else None,
            "original": legacy,
            "originals": [known.get(name, legacy) for name in live],
            "target": (_read_attr(shader, _ATTR_TARGET)
                       or (live[0] if live else shader)),
            "color": tuple(color[0])[:3],
            "members": live,
            "enabled": bool(members),
        })
    records.sort(key=lambda rec: core.short_name(rec["target"]))
    return records


def _selected_objects():
    """選択されているオブジェクトをフルパスで返す（コンポーネント選択は除く）。"""
    return core.unique(cmds.ls(selection=True, long=True,
                               objectsOnly=True) or [])


def _all_mesh_objects():
    """シーン内の全メッシュを、その親トランスフォームの形で返す。"""
    nodes = []
    for shape in cmds.ls(type="mesh", noIntermediate=True, long=True) or []:
        parents = cmds.listRelatives(shape, parent=True, fullPath=True) or []
        nodes.append(parents[0] if parents else shape)
    return core.unique(nodes)


# --------------------------------------------------------------------------- #
# シーンの書き換え
# --------------------------------------------------------------------------- #

def _write_string(node, attr, value):
    """文字列属性を（無ければ足してから）書く。"""
    if not cmds.attributeQuery(attr, node=node, exists=True):
        cmds.addAttr(node, longName=attr, dataType="string")
    cmds.setAttr("%s.%s" % (node, attr), value or "", type="string")


def _write_assignment(shader, members, originals):
    """「誰に掛けたか」と「それぞれの戻し先」をシェーダーに控える。

    復元の情報源はシーンに置く。 Python の辞書に持つとシーンを開き直した
    時点で戻せなくなり、一時解除中は shadingEngine が空なので
    シーンからも読めなくなる。
    """
    if not shader or not cmds.objExists(shader):
        return
    _write_string(shader, _ATTR_MEMBERS, core.join_members(members))
    _write_string(shader, _ATTR_ORIGINALS, core.join_members(originals))


def _delete_override(record):
    """オーバーライド用に作ったノードを片付ける。"""
    for node in (record.get("sg"), record.get("shader")):
        if node and cmds.objExists(node):
            cmds.delete(node)


def _original_resolver(records):
    """シェイプ → **本当の**元 shadingEngine を返す関数を作る。

    既にオーバーライドが掛かっているシェイプは、現在の割り当てが
    オーバーライド用の SG なので、そのまま控えると二度と元に戻せない。
    記録に控えてある元の SG を優先する。
    """
    known = {}
    for record in records or []:
        for member, original in core.align_originals(
                record.get("members"), record.get("originals"),
                record.get("original") or _DEFAULT_SG):
            known[member] = original

    def _resolve(shape):
        if shape in known:
            return known[shape]
        return _shading_engine_of(shape)

    return _resolve


def _release_members(records, index, shapes):
    """これから別のオーバーライドが抱えるシェイプを、既存の記録から外す。

    **1 シェイプ = 1 オーバーライド**を保つための後始末。 たとえばグループに
    掛けたあと中の 1 つだけ色を変えると、そのシェイプは新しい記録に移る。
    外した結果メンバーが 0 になった記録は、シェーダーごと片付ける
    （空のまま残すと一覧に `(off)` として出続ける）。
    """
    claimed = set(shapes)
    for record in list(records):
        members = record.get("members") or []
        keep = [name for name in members if name not in claimed]
        if len(keep) == len(members):
            continue

        pairs = dict(core.align_originals(members, record.get("originals"),
                                          record.get("original")
                                          or _DEFAULT_SG))
        for name in members:
            if name not in claimed:
                continue
            for key in (name, core.short_name(name)):
                if index.get(key) is record:
                    index.pop(key, None)

        record["members"] = keep
        record["originals"] = [pairs[name] for name in keep]

        if keep:
            _write_assignment(record["shader"], keep, record["originals"])
            continue

        _delete_override(record)
        records.remove(record)
        for key in [k for k, value in index.items() if value is record]:
            index.pop(key, None)


def _apply_one(node, rgb, records, index, resolve_original):
    """ノード 1 つに色を掛ける。 既に掛かっていれば色だけ差し替える。

    `index` は `core.index_by_object()` が作った「対象名 → 記録」の索引。
    **シーンの現在の割り当てを辿らないのが要点**で、一時解除中は対象が元の
    SG に戻っているため、割り当てからは既存のオーバーライドを見つけられない。
    見つけ損なうと 2 本目のシェーダーを作ってしまい、元のマテリアルの記録が
    二重になる。

    グループノードを渡すと、**中のシェイプを全部拾って 1 件の記録にまとめる**。
    戻し先はシェイプごとに控えるので、中身のマテリアルがばらばらでも戻せる。
    """
    record = index.get(node) or index.get(core.short_name(node))

    if record:
        cmds.setAttr(record["shader"] + ".outColor", rgb[0], rgb[1], rgb[2],
                     type="double3")
        # 一時解除中に色を掛けたなら、見えるように戻す（掛けたのに何も
        # 変わらないほうが分かりにくい）
        if not record.get("enabled", True):
            _enable_records([record])
            record["enabled"] = True
        return record["shader"]

    shapes = [name for name in _shapes_of(node) if cmds.objExists(name)]
    if not shapes:
        cmds.warning("[%s] %s にシェイプが見つかりません。"
                     % (_PACKAGE, core.short_name(node)))
        return None

    # **割り当てを書き換える前に、シェイプごとの戻し先を控える。**
    originals = [resolve_original(shape) for shape in shapes]

    # これから抱えるシェイプを既存の記録から外す（1 シェイプ = 1 記録）
    _release_members(records, index, shapes)

    shader_name, set_name = core.override_node_names(_NODE_PREFIX, node)
    shader = cmds.shadingNode("surfaceShader", asShader=True, name=shader_name)
    shading_engine = cmds.sets(name=set_name, renderable=True,
                               noSurfaceShader=True, empty=True)
    cmds.connectAttr(shader + ".outColor", shading_engine + ".surfaceShader",
                     force=True)

    # _ATTR_ORIGINAL は「このツールが作ったシェーダーか」の目印も兼ねるので、
    # 旧形式の単一値として必ず書く（v0.2.0 のコードに開かれても壊れない）
    _write_string(shader, _ATTR_ORIGINAL, originals[0])
    _write_string(shader, _ATTR_TARGET, node)

    cmds.setAttr(shader + ".outColor", rgb[0], rgb[1], rgb[2], type="double3")
    cmds.sets(shapes, edit=True, forceElement=shading_engine)
    _write_assignment(shader, shapes, originals)

    # 同じ処理の中で続けて引けるよう、作ったものも索引に足しておく
    record = {"shader": shader, "sg": shading_engine, "original": originals[0],
              "originals": originals, "target": node, "members": shapes,
              "enabled": True}
    records.append(record)
    for name in [node] + shapes:
        index.setdefault(name, record)
        index.setdefault(core.short_name(name), record)
    index[node] = record
    return shader


def _enable_records(records):
    """一時解除していたオーバーライドを掛け直す。 戻した件数を返す。"""
    restored = 0
    for record in records or []:
        if record.get("enabled", True):
            continue
        shading_engine = record.get("sg")
        if not shading_engine or not cmds.objExists(shading_engine):
            continue
        members = [name for name in (record.get("members") or [])
                   if cmds.objExists(name)]
        if not members:
            continue
        cmds.sets(members, edit=True, forceElement=shading_engine)
        restored += 1
    return restored


def _disable_records(records):
    """色を一時的に外して元のマテリアルに戻す（記録は残す）。 外した件数を返す。

    `Restore` と違ってシェーダーとセットは消さないので、そのまま掛け直せる。
    """
    targets = [rec for rec in records or [] if rec.get("enabled", True)]
    if not targets:
        return 0

    # どこへ戻すかを先に控える。 外した時点で shadingEngine が空になり、
    # シーンからは「何に掛かっていたか」が読めなくなる
    for record in targets:
        _write_assignment(record.get("shader"), record.get("members"),
                          record.get("originals"))

    _return_to_originals(targets)
    return len(targets)


def _return_to_originals(records):
    """記録のメンバーを、**それぞれの**元の shadingEngine へ戻す。

    戻し先が同じものは 1 回の `cmds.sets` にまとめる（`core.group_by_original`）。
    対象ごとに呼ぶと数百オブジェクトで往復が効いてくる。

    元のマテリアルが既に消えていたら Maya の既定へ逃がす。
    """
    for original, members in core.group_by_original(records):
        existing = [name for name in members if cmds.objExists(name)]
        if not existing:
            continue
        destination = (original if original and cmds.objExists(original)
                       else _DEFAULT_SG)
        cmds.sets(existing, edit=True, forceElement=destination)


def _in_undo_chunk(name, func):
    """1 操作 = 1 undo にまとめる。 例外が出ても必ず閉じる。

    閉じ忘れると以降の undo が壊れ、Maya を再起動するまで直らない。
    """
    cmds.undoInfo(openChunk=True, chunkName="%s %s" % (_PACKAGE, name))
    try:
        return func()
    finally:
        cmds.undoInfo(closeChunk=True)


# --------------------------------------------------------------------------- #
# 色のやりとり
# --------------------------------------------------------------------------- #

def _load_last_color():
    """前回使った色（無ければ既定色）。"""
    if cmds.optionVar(exists=_OPTVAR_LAST_COLOR):
        try:
            return core.parse_hex(cmds.optionVar(q=_OPTVAR_LAST_COLOR))
        except ValueError:
            pass
    return _DEFAULT_COLOR


def _current_color():
    """カラースライダの現在値。 読めなければ前回値に落とす。"""
    ctrl = _CTRL.get("color")
    rgb = None
    if ctrl and cmds.colorSliderGrp(ctrl, exists=True):
        rgb = cmds.colorSliderGrp(ctrl, q=True, rgbValue=True)
    try:
        return tuple(core.clamp01(c) for c in rgb)[:3]
    except (TypeError, ValueError):
        return _load_last_color()


def _set_color(rgb):
    """スライダと 16 進欄の両方を同じ色に揃え、optionVar に控える。"""
    if _CTRL.get("color"):
        cmds.colorSliderGrp(_CTRL["color"], edit=True, rgbValue=rgb)
    if _CTRL.get("hex"):
        cmds.textField(_CTRL["hex"], edit=True, text=core.to_hex(rgb))
    cmds.optionVar(sv=(_OPTVAR_LAST_COLOR, core.to_hex(rgb)))


# --------------------------------------------------------------------------- #
# 一覧
# --------------------------------------------------------------------------- #

def _refresh_list(*_args):
    """オーバーライド中の一覧を作り直す。"""
    ctrl = _CTRL.get("list")
    if not ctrl or not cmds.textScrollList(ctrl, exists=True):
        return

    del _ROWS[:]
    _ROWS.extend(_collect_records())

    cmds.textScrollList(ctrl, edit=True, removeAll=True)
    for record in _ROWS:
        cmds.textScrollList(ctrl, edit=True, append=core.format_row(record))

    # 1 件も無いときは「掛かっていない」なので、トグルは押せない状態のまま
    # 既定のラベルにしておく（Show Colors と出ていて押せないのは紛らわしい）
    showing = core.any_enabled(_ROWS) if _ROWS else True

    if _CTRL.get("count"):
        cmds.text(_CTRL["count"], edit=True,
                  label="Overridden: %d%s"
                        % (len(_ROWS), "" if showing else "   — 一時解除中"))

    # トグルのラベルは**シーンの実態から**決める。 別にフラグを持つと、
    # Maya 側で割り当てを手で変えられたときに表示と食い違う
    if _CTRL.get("toggle"):
        cmds.button(_CTRL["toggle"], edit=True, enable=bool(_ROWS),
                    label="Hide Colors" if showing else "Show Colors")


def _rows_selected_in_list():
    """一覧で選ばれている行の記録を返す。"""
    ctrl = _CTRL.get("list")
    if not ctrl or not cmds.textScrollList(ctrl, exists=True):
        return []
    indices = cmds.textScrollList(ctrl, q=True, selectIndexedItem=True) or []
    return [_ROWS[i - 1] for i in indices if 0 < i <= len(_ROWS)]


# --------------------------------------------------------------------------- #
# コールバック
# --------------------------------------------------------------------------- #

def _on_color_changed(*_args):
    _set_color(_current_color())


def _on_hex_changed(*_args):
    """16 進欄の入力を色に反映する。 読めなければ元の表示に戻す。"""
    text = cmds.textField(_CTRL["hex"], q=True, text=True)
    try:
        rgb = core.parse_hex(text)
    except ValueError:
        cmds.warning("[%s] %s は #RRGGBB の形で入れてください。"
                     % (_PACKAGE, text))
        cmds.textField(_CTRL["hex"], edit=True,
                       text=core.to_hex(_current_color()))
        return
    _set_color(rgb)


def _apply_to(nodes, colors, label):
    """共通の入口 — 対象と色の組を undo チャンクにまとめて流す。"""
    if not nodes:
        cmds.warning("[%s] 対象がありません。" % (_PACKAGE,))
        return

    # 既存のオーバーライドは 1 度のスキャンで索引にしておく。 ノードごとに
    # 割り当てを辿ると、対象が増えたときに cmds の往復が効いてくる
    records = _collect_records()
    index = core.index_by_object(records)
    resolve_original = _original_resolver(records)

    def _run():
        for node, rgb in zip(nodes, colors):
            _apply_one(node, rgb, records, index, resolve_original)

    _in_undo_chunk(label, _run)
    _refresh_list()
    print("[%s] %s: %d object(s)" % (_PACKAGE, label, len(nodes)))


def _on_apply_selected(*_args):
    """選択物すべてに、いま指定している色を掛ける。"""
    nodes = _selected_objects()
    rgb = _current_color()
    _set_color(rgb)
    _apply_to(nodes, [rgb] * len(nodes), "apply color")


def _on_random_selected(*_args):
    """選択物に互いに見分けやすい色を振る。"""
    nodes = _selected_objects()
    start = core.next_start_index(_collect_records())
    _apply_to(nodes, core.distinct_colors(len(nodes), start), "random color")


def _on_random_all(*_args):
    """シーンの全メッシュに互いに見分けやすい色を振る。"""
    nodes = _all_mesh_objects()
    if len(nodes) > _BULK_CONFIRM_THRESHOLD:
        answer = cmds.confirmDialog(
            title="Color Override",
            message=("%d 個のメッシュに色を掛けます。\n"
                     "同じ数だけシェーダーとセットが作られます。 続けますか？"
                     % (len(nodes),)),
            button=["OK", "Cancel"], defaultButton="Cancel",
            cancelButton="Cancel", dismissString="Cancel")
        if answer != "OK":
            return
    start = core.next_start_index(_collect_records())
    _apply_to(nodes, core.distinct_colors(len(nodes), start), "random color")


def _restore(records, label):
    if not records:
        cmds.warning("[%s] 戻す対象がありません。" % (_PACKAGE,))
        return

    def _run():
        _return_to_originals(records)
        for record in records:
            _delete_override(record)

    _in_undo_chunk(label, _run)
    _refresh_list()
    print("[%s] %s: %d object(s)" % (_PACKAGE, label, len(records)))


def _selection_with_shapes():
    """選択物と、その下にあるシェイプをまとめて返す。

    記録が抱えているのはシェイプなので、グループやトランスフォームを
    選んだままでは突き合わせられない。
    """
    selection = _selected_objects()
    names = list(selection)
    for node in selection:
        names.extend(_shapes_of(node))
    return core.unique(names)


def _on_restore_selected(*_args):
    """一覧で選んだ行、無ければシーンで選択中のものを元に戻す。"""
    records = _rows_selected_in_list()
    if not records:
        records = core.match_records(_collect_records(),
                                     _selection_with_shapes())
    _restore(records, "restore")


def _on_restore_all(*_args):
    _restore(_collect_records(), "restore all")


def _on_toggle(*_args):
    """色の表示を一時的に外す／掛け直す（記録は残す）。"""
    records = _collect_records()
    if not records:
        cmds.warning("[%s] オーバーライドが掛かっていません。" % (_PACKAGE,))
        _refresh_list()
        return

    if core.any_enabled(records):
        count = _in_undo_chunk("hide overrides",
                               lambda: _disable_records(records))
        message = "hide overrides"
    else:
        count = _in_undo_chunk("show overrides",
                               lambda: _enable_records(records))
        message = "show overrides"

    _refresh_list()
    print("[%s] %s: %d object(s)" % (_PACKAGE, message, count))


def toggle():
    """オーバーライドの表示を一時的に切り替える。

    ウィンドウを開いていなくても呼べるので、**ホットキーやシェルフボタンに
    割り当てて使える**。 「一瞬だけ元のマテリアルを見たい」のが主な用途なので、
    ボタンまでマウスを運ばずに往復できるほうが速い。

        import color_override
        color_override.toggle()
    """
    return _on_toggle()


def _on_select_in_scene(*_args):
    """一覧で選んだ行のオブジェクトをシーンでも選択する。"""
    targets = [rec["target"] for rec in _rows_selected_in_list()
               if rec.get("target") and cmds.objExists(rec["target"])]
    if targets:
        cmds.select(targets, replace=True)


# --------------------------------------------------------------------------- #
# ウィンドウ
# --------------------------------------------------------------------------- #

def _build_body():
    color = _load_last_color()

    cmds.separator(h=4, style="none")

    _CTRL["color"] = cmds.colorSliderGrp(
        label="Color", rgbValue=color, columnWidth3=(44, 60, 150),
        adjustableColumn=3, changeCommand=_on_color_changed,
        annotation="オーバーライドに使う色")

    cmds.rowLayout(numberOfColumns=2, adjustableColumn=2,
                   columnWidth2=(44, 210))
    cmds.text(label="Hex", align="left")
    _CTRL["hex"] = cmds.textField(text=core.to_hex(color),
                                  changeCommand=_on_hex_changed,
                                  annotation="#RRGGBB で直接指定する")
    cmds.setParent("..")

    cmds.button(label="Apply to Selected", height=28, c=_on_apply_selected,
                ann="選択したオブジェクトに上の色を掛ける")

    cmds.rowLayout(numberOfColumns=2, adjustableColumn=1,
                   columnWidth2=(170, 170))
    cmds.button(label="Random → Selected", height=26, c=_on_random_selected,
                ann="選択物に互いに見分けやすい色を振る")
    cmds.button(label="Random → All Meshes", height=26, c=_on_random_all,
                ann="シーンの全メッシュに互いに見分けやすい色を振る")
    cmds.setParent("..")

    cmds.separator(h=8, style="in")

    _CTRL["count"] = cmds.text(label="Overridden: 0", align="left",
                               fn="boldLabelFont")

    # 「一瞬だけ元のマテリアルを見る」ための往復。 Restore と違って
    # シェーダーは消さないので、何度でも掛け直せる
    _CTRL["toggle"] = cmds.button(
        label="Hide Colors", height=28, c=_on_toggle, enable=False,
        ann="色を一時的に外して元のマテリアルを見る／掛け直す。\n"
            "記録は残るので何度でも往復できる。\n"
            "ホットキーに割り当てるなら: "
            "import color_override; color_override.toggle()")

    _CTRL["list"] = cmds.textScrollList(
        height=140, allowMultiSelection=True,
        selectCommand=_on_select_in_scene,
        annotation="行を選ぶとシーン側でも選択される")

    cmds.rowLayout(numberOfColumns=3, adjustableColumn=1,
                   columnWidth3=(130, 110, 90))
    cmds.button(label="Restore Selected", height=26, c=_on_restore_selected,
                ann="一覧で選んだ行（無ければシーンで選択中のもの）を"
                    "元のマテリアルに戻す")
    cmds.button(label="Restore All", height=26, c=_on_restore_all,
                ann="シーン内のオーバーライドを全部戻す")
    cmds.button(label="Refresh", height=26, c=_refresh_list,
                ann="一覧をシーンの実態から作り直す")
    cmds.setParent("..")


def show():
    """ツールウィンドウを開く（既に開いていれば作り直す）。"""
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW)

    _CTRL.clear()

    win = cmds.window(WINDOW,
                      title="Color Override  —  v%s" % (__version__,),
                      widthHeight=(380, 430),
                      minimizeButton=True, maximizeButton=False, sizeable=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=8,
                      columnAttach=("both", 10))

    _build_body()

    # バージョン表示 + 「GitHub から更新」。 全ツール共通なので消さない
    dev_tools.build_footer()

    cmds.showWindow(win)
    _refresh_list()
    return win
