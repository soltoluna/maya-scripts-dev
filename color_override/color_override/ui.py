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
      .ntkColorOverrideOriginal       元の shadingEngine 名 ← 復元の情報源
      .ntkColorOverrideTarget         掛けた時点の対象ノード名（表示用）
    ntk_color_override_<対象名>_SG    上をつないだ shadingEngine

`surfaceShader` を使うのはライティングに影響されないフラットな色になるため。
陰影が乗らないぶん、同系色のオブジェクトの境界（＝貫通している箇所）が
輪郭としてはっきり出る。

**管理対象の判別は名前ではなく `.ntkColorOverrideOriginal` 属性の有無で行う。**
ユーザーがノードをリネームしても追跡できる。
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
    """シェーダーを割り当てる相手（シェイプ）を返す。 見つからなければ自分自身。"""
    shapes = cmds.listRelatives(node, shapes=True, noIntermediate=True,
                                fullPath=True) or []
    return shapes or [node]


def _shading_engines(node):
    """ノードに割り当たっている shadingEngine を重複なく返す。"""
    found = []
    for shape in _shapes_of(node):
        found.extend(cmds.listConnections(shape, type="shadingEngine") or [])
    return core.unique(found)


def _shader_of(shading_engine):
    """shadingEngine の surfaceShader につながっているシェーダーを返す。"""
    connected = cmds.listConnections(shading_engine + ".surfaceShader",
                                     source=True, destination=False) or []
    return connected[0] if connected else None


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
        records.append({
            "shader": shader,
            "sg": shading_engines[0] if shading_engines else None,
            "original": _read_attr(shader, _ATTR_ORIGINAL, _DEFAULT_SG),
            "target": (_read_attr(shader, _ATTR_TARGET)
                       or (members[0] if members else shader)),
            "color": tuple(color[0])[:3],
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

def _existing_override(node):
    """ノードに既に掛かっているオーバーライドの `(シェーダー, 元の SG)`。

    掛け直しのときに**オーバーライド用の SG を「元の SG」として記録して
    しまう**と、二度と元のマテリアルに戻せなくなる。 それを防ぐための照会。
    """
    for shading_engine in _shading_engines(node):
        shader = _shader_of(shading_engine)
        if _is_override_shader(shader):
            return (shader, _read_attr(shader, _ATTR_ORIGINAL, _DEFAULT_SG))
    return (None, None)


def _apply_one(node, rgb):
    """ノード 1 つに色を掛ける。 既に掛かっていれば色だけ差し替える。"""
    shader, _original = _existing_override(node)

    if shader:
        cmds.setAttr(shader + ".outColor", rgb[0], rgb[1], rgb[2],
                     type="double3")
        return shader

    shading_engines = _shading_engines(node)
    original = shading_engines[0] if shading_engines else _DEFAULT_SG

    shader_name, set_name = core.override_node_names(_NODE_PREFIX, node)
    shader = cmds.shadingNode("surfaceShader", asShader=True, name=shader_name)
    shading_engine = cmds.sets(name=set_name, renderable=True,
                               noSurfaceShader=True, empty=True)
    cmds.connectAttr(shader + ".outColor", shading_engine + ".surfaceShader",
                     force=True)

    # 復元の情報源はシーンに書く（Python の辞書に持つとシーンを開き直した
    # 時点で戻せなくなる）
    cmds.addAttr(shader, longName=_ATTR_ORIGINAL, dataType="string")
    cmds.setAttr(shader + "." + _ATTR_ORIGINAL, original, type="string")
    cmds.addAttr(shader, longName=_ATTR_TARGET, dataType="string")
    cmds.setAttr(shader + "." + _ATTR_TARGET, node, type="string")

    cmds.setAttr(shader + ".outColor", rgb[0], rgb[1], rgb[2], type="double3")
    cmds.sets(node, edit=True, forceElement=shading_engine)
    return shader


def _restore_one(record):
    """記録 1 件を元のマテリアルに戻し、作ったノードを片付ける。"""
    shading_engine = record.get("sg")
    original = record.get("original") or _DEFAULT_SG
    if not cmds.objExists(original):
        # 元のマテリアルが既に消えている。 Maya の既定へ逃がす
        original = _DEFAULT_SG

    if shading_engine and cmds.objExists(shading_engine):
        members = cmds.sets(shading_engine, q=True) or []
        if members:
            cmds.sets(members, edit=True, forceElement=original)

    for node in (shading_engine, record.get("shader")):
        if node and cmds.objExists(node):
            cmds.delete(node)


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

    if _CTRL.get("count"):
        cmds.text(_CTRL["count"], edit=True,
                  label="Overridden: %d" % (len(_ROWS),))


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

    def _run():
        for node, rgb in zip(nodes, colors):
            _apply_one(node, rgb)

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
        for record in records:
            _restore_one(record)

    _in_undo_chunk(label, _run)
    _refresh_list()
    print("[%s] %s: %d object(s)" % (_PACKAGE, label, len(records)))


def _on_restore_selected(*_args):
    """一覧で選んだ行、無ければシーンで選択中のものを元に戻す。"""
    records = _rows_selected_in_list()
    if not records:
        records = core.match_records(_collect_records(), _selected_objects())
    _restore(records, "restore")


def _on_restore_all(*_args):
    _restore(_collect_records(), "restore all")


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
