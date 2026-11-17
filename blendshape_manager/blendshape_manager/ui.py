# -*- coding: utf-8 -*-
"""BlendShape Manager — `maya.cmds` による UI。

ここは「値を集める → `core` で検証・計画する → `scene` に流す」だけに保つ。
判定や計算を書き始めたら `core.py` に移す（自宅に Maya が無いので、
`core` に無い処理は実機に持っていくまで一度も実行されない）。

シーンを変える操作はすべて `_action` を通す。 1 操作 = 1 undo チャンクにして、
`ValueError`（入力の問題）はダイアログ、それ以外の例外は Script Editor に
出したうえでダイアログにする。 どちらの場合も一覧は作り直す。
"""

from __future__ import annotations

import functools
import traceback

from maya import cmds

from . import NAMESPACE, __version__, core, dev_tools, scene


_PACKAGE = __package__ or __name__.rsplit(".", 1)[0]
_NS = "%s_%s" % (NAMESPACE, _PACKAGE)          # ntk_blendshape_manager

# ウィンドウ名は `<NAMESPACE>_<モジュール名>Win` 固定（ハブが同じ規則で閉じる）
WINDOW = _NS + "Win"
_TITLE = "BlendShape Manager"

_OPTVAR_LAST_NODE = _NS + "_last_node"
_OPTVAR_FRONT = _NS + "_front_of_chain"
_OPTVAR_AXIS = _NS + "_mirror_axis"
_OPTVAR_TOLERANCE = _NS + "_mirror_tolerance"
_OPTVAR_OVERWRITE = _NS + "_mirror_overwrite"

_NO_NODE = "(blendShape なし)"

_CTRL = {}    # コントロール名の控え。 show() のたびに作り直す
_ROWS = {}    # ターゲット番号 → (チェックボックス, 名前)
_STATE = {"bs": None}


# --------------------------------------------------------------------------- #
# 小物
# --------------------------------------------------------------------------- #

def _get_opt(key, default):
    if cmds.optionVar(exists=key):
        value = cmds.optionVar(q=key)
        return default if value is None else value
    return default


def _dialog(message, buttons=("OK",)):
    return cmds.confirmDialog(title=_TITLE, message=message, button=list(buttons),
                              defaultButton=buttons[0], cancelButton=buttons[-1],
                              dismissString=buttons[-1])


def _status(message):
    if "status" in _CTRL:
        cmds.text(_CTRL["status"], e=True, label=message)
    print("[%s] %s" % (_PACKAGE, message))


def _action(chunk_name):
    """シーンを変えるコールバックを包む。 undo チャンク・エラー表示・一覧の更新。"""
    def decorate(func):
        @functools.wraps(func)
        def wrapper(*_args):
            cmds.undoInfo(openChunk=True, chunkName="%s %s" % (_PACKAGE, chunk_name))
            try:
                func()
            except ValueError as exc:
                _dialog(str(exc))
            except Exception as exc:   # noqa: BLE001  実機で何が来るか分からない
                traceback.print_exc()
                _dialog("失敗しました（詳細は Script Editor）:\n%s" % (exc,))
            finally:
                cmds.undoInfo(closeChunk=True)
                _rebuild_rows()
        return wrapper
    return decorate


def _require_bs():
    bs = _STATE["bs"]
    if not bs or not cmds.objExists(bs):
        raise ValueError("blendShape ノードを選んでください（上のメニュー / 「選択から」）")
    return bs


def _selected_transforms():
    return cmds.ls(selection=True, objectsOnly=True, long=True) or []


def _checked_indices():
    return [i for i, (cb, _name) in sorted(_ROWS.items())
            if cmds.checkBox(cb, q=True, v=True)]


def _require_checked(exactly_one=False):
    checked = _checked_indices()
    if not checked:
        raise ValueError("ターゲットにチェックを入れてください")
    if exactly_one and len(checked) != 1:
        raise ValueError("ターゲットのチェックは 1 つだけにしてください（今 %d 個）"
                         % len(checked))
    return checked


def _check_topology(base, meshes):
    base_count = scene.vertex_count(base)
    if base_count is None:
        raise ValueError("ベースがメッシュではない: %s" % core.short_name(base))
    counts = {}
    for mesh in meshes:
        count = scene.vertex_count(mesh)
        if count is None:
            raise ValueError("メッシュではない: %s" % core.short_name(mesh))
        counts[mesh] = count
    bad = core.topology_mismatches(base_count, counts)
    if bad:
        raise ValueError("頂点数がベース（%d）と違う:\n%s"
                         % (base_count, "\n".join(
                             "  %s (%d)" % (core.short_name(m), counts[m]) for m in bad)))


# --------------------------------------------------------------------------- #
# blendShape ノードの選択
# --------------------------------------------------------------------------- #

def _refresh_nodes(select=None):
    menu = _CTRL["node_menu"]
    for item in cmds.optionMenu(menu, q=True, itemListLong=True) or []:
        cmds.deleteUI(item)
    nodes = scene.list_blendshapes()
    for node in nodes:
        cmds.menuItem(label=node, parent=menu)
    if not nodes:
        cmds.menuItem(label=_NO_NODE, parent=menu)

    wanted = select or _STATE["bs"] or _get_opt(_OPTVAR_LAST_NODE, None)
    if wanted not in nodes:
        wanted = nodes[0] if nodes else None
    if wanted:
        cmds.optionMenu(menu, e=True, value=wanted)
    _set_current(wanted)


def _set_current(bs):
    _STATE["bs"] = bs
    if bs:
        cmds.optionVar(sv=(_OPTVAR_LAST_NODE, bs))
    _rebuild_rows()


def _on_node_changed(value, *_args):
    _set_current(None if value == _NO_NODE else value)


def _on_load_selection(*_args):
    found = scene.find_blendshapes(_selected_transforms())
    if not found:
        cmds.warning("[%s] 選択したもののヒストリに blendShape がありません。" % _PACKAGE)
        return
    _refresh_nodes(select=found[0])
    if len(found) > 1:
        _status("blendShape が %d 個見つかった。 先頭の %s を表示（メニューで切り替え）"
                % (len(found), found[0]))


# --------------------------------------------------------------------------- #
# ターゲットの一覧
# --------------------------------------------------------------------------- #

def _rebuild_rows():
    if "list" not in _CTRL or not cmds.columnLayout(_CTRL["list"], exists=True):
        return
    keep = set(_checked_indices()) if _ROWS else set()
    for child in cmds.columnLayout(_CTRL["list"], q=True, childArray=True) or []:
        cmds.deleteUI(child)
    _ROWS.clear()

    bs = _STATE["bs"]
    if not bs or not cmds.objExists(bs):
        cmds.text(label="blendShape がありません", parent=_CTRL["list"])
        cmds.text(_CTRL["base_info"], e=True, label="")
        return

    base = scene.base_geometry(bs)
    targets = scene.read_targets(bs)
    cmds.text(_CTRL["base_info"], e=True,
              label="ベース: %s   ターゲット: %d" % (core.short_name(base) if base else "-",
                                                    len(targets)))
    filter_text = cmds.textField(_CTRL["filter"], q=True, text=True) or ""
    shown = set(i for i, _n in core.filter_entries(
        [(t["index"], t["name"]) for t in targets], filter_text))

    for target in targets:
        index = target["index"]
        if index not in shown:
            continue
        label = target["name"]
        if target["inbetweens"]:
            label += "  (+%d)" % len(target["inbetweens"])
        cmds.rowLayout(numberOfColumns=2, adjustableColumn=2,
                             columnWidth2=(170, 200), parent=_CTRL["list"])
        cb = cmds.checkBox(label=label, value=index in keep,
                           annotation="weight[%d]  インビトウィーン: %s"
                           % (index, ", ".join("%.3f" % w for w in target["inbetweens"])
                              or "なし"))
        cmds.attrFieldSliderGrp(attribute=scene.weight_plug(bs, index), label="",
                                minValue=0.0, maxValue=1.0,
                                columnWidth3=(1, 50, 140), adjustableColumn=3)
        cmds.setParent("..")
        _ROWS[index] = (cb, target["name"])


def _on_check_all(value):
    for cb, _name in _ROWS.values():
        cmds.checkBox(cb, e=True, value=value)


# --------------------------------------------------------------------------- #
# 操作
# --------------------------------------------------------------------------- #

@_action("create")
def _on_create():
    targets, base = core.split_create_selection(_selected_transforms())
    _check_topology(base, targets)
    name = cmds.textFieldGrp(_CTRL["new_name"], q=True, text=True).strip()
    name = name or core.default_node_name(base)
    if not core.is_valid_name(name):
        raise ValueError("ノード名に使えない文字が含まれている: %r" % name)
    front = bool(cmds.checkBox(_CTRL["front"], q=True, v=True))
    cmds.optionVar(iv=(_OPTVAR_FRONT, int(front)))
    bs = scene.create(base, targets, name, front_of_chain=front)
    _refresh_nodes(select=bs)
    _status("%s を作成（ターゲット %d 個）" % (bs, len(targets)))


@_action("add targets")
def _on_add_targets():
    bs = _require_bs()
    base = scene.base_geometry(bs)
    base_parent = (cmds.listRelatives(base, parent=True, fullPath=True) or [None])[0]
    meshes = [n for n in _selected_transforms() if n != base_parent]
    if not meshes:
        raise ValueError("ターゲットにするメッシュを選択してください（ベース以外）")
    _check_topology(base, meshes)
    added = scene.add_targets(bs, meshes)
    _status("%d 個追加（weight[%s]）" % (len(added), ", ".join(str(i) for i in added)))


@_action("delete targets")
def _on_delete():
    bs = _require_bs()
    checked = _require_checked()
    names = [_ROWS[i][1] for i in checked]
    if _dialog("%d 個のターゲットを削除しますか？\n%s"
               % (len(names), "\n".join(names[:15]) + ("\n…" if len(names) > 15 else "")),
               ("削除", "キャンセル")) != "削除":
        return
    scene.delete_targets(bs, checked)
    _status("%d 個削除" % len(checked))


def _set_weight_action(value, every):
    @_action("set weights")
    def run():
        bs = _require_bs()
        indices = sorted(_ROWS) if every else _require_checked()
        skipped = scene.set_weights(bs, indices, value)
        message = "%d 個を %g に" % (len(indices) - len(skipped), value)
        if skipped:
            message += "（接続・ロック中の %d 個は飛ばした）" % len(skipped)
        _status(message)
    return run


def _apply_renames(bs, new_names):
    targets = scene.read_targets(bs)
    steps, errors = core.plan_renames([(t["index"], t["name"]) for t in targets],
                                      new_names)
    if errors:
        raise ValueError("リネームできません:\n" + "\n".join(errors[:20]))
    if not steps:
        _status("名前は変わりませんでした")
        return
    scene.rename_targets(bs, steps)
    _status("%d 個リネーム" % len(new_names))


@_action("rename")
def _on_rename_one():
    bs = _require_bs()
    index = _require_checked(exactly_one=True)[0]
    new = cmds.textFieldGrp(_CTRL["rename"], q=True, text=True).strip()
    _apply_renames(bs, {index: new})


@_action("batch rename")
def _on_batch_rename():
    bs = _require_bs()
    indices = _checked_indices() or sorted(_ROWS)
    if not indices:
        raise ValueError("リネームするターゲットがありません")
    values = {key: cmds.textFieldGrp(_CTRL[key], q=True, text=True)
              for key in ("search", "replace", "prefix", "suffix")}
    olds = [_ROWS[i][1] for i in indices]
    news = core.batch_rename(olds, **values)
    _apply_renames(bs, {i: n for i, o, n in zip(indices, olds, news) if o != n})


@_action("add inbetween")
def _on_add_inbetween():
    bs = _require_bs()
    index = _require_checked(exactly_one=True)[0]
    base = scene.base_geometry(bs)
    meshes = _selected_transforms()
    if len(meshes) != 1:
        raise ValueError("インビトウィーンにするメッシュを 1 つだけ選択してください")
    weight = cmds.floatFieldGrp(_CTRL["ib_weight"], q=True, value1=True)
    items = next((t["items"] for t in scene.read_targets(bs) if t["index"] == index), [])
    reason = core.validate_inbetween_weight(weight, items)
    if reason:
        raise ValueError(reason)
    _check_topology(base, meshes)
    scene.add_inbetween(bs, index, meshes[0], weight)
    _status("%s に重み %.3f のインビトウィーンを追加" % (_ROWS[index][1], weight))


@_action("mirror")
def _on_mirror():
    bs = _require_bs()
    checked = _require_checked()
    axis = core.AXES[cmds.radioButtonGrp(_CTRL["axis"], q=True, select=True) - 1]
    tolerance = cmds.floatFieldGrp(_CTRL["tolerance"], q=True, value1=True)
    overwrite = bool(cmds.checkBox(_CTRL["overwrite"], q=True, v=True))
    if not tolerance or tolerance <= 0:
        raise ValueError("許容誤差は 0 より大きくする")
    cmds.optionVar(sv=(_OPTVAR_AXIS, axis))
    cmds.optionVar(fv=(_OPTVAR_TOLERANCE, tolerance))
    cmds.optionVar(iv=(_OPTVAR_OVERWRITE, int(overwrite)))

    by_name = {_ROWS[i][1]: i for i in checked}
    todo, skipped = core.plan_mirror([_ROWS[i][1] for i in checked])
    lines = []
    has_missing = False
    for name in todo:
        result = scene.mirror_target(bs, by_name[name], axis, tolerance, overwrite)
        line = "%s → %s%s" % (name, result["name"], "（上書き）" if result["replaced"] else "")
        if result["missing"]:
            line += "  ※反対側が見つからない頂点 %d 個" % result["missing"]
            has_missing = True
        lines.append(line)
    for name in skipped:
        lines.append("%s は組の相手と一緒に選ばれていたので飛ばした" % name)
    _status("ミラー %d 個" % len(todo))
    if any("※" in line for line in lines) or skipped:
        _dialog("\n".join(lines) + "\n\n反対側が見つからない頂点は動かしていません。"
                "ベースが左右対称か、許容誤差を確認してください。")


# --------------------------------------------------------------------------- #
# ウィンドウ
# --------------------------------------------------------------------------- #

def _frame(label, collapse=False):
    return cmds.frameLayout(label=label, collapsable=True, collapse=collapse,
                            marginWidth=6, marginHeight=4)


def _build_body():
    # --- 作成 ---------------------------------------------------------------
    _frame("作成")
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    _CTRL["new_name"] = cmds.textFieldGrp(label="ノード名", text="",
                                          columnWidth2=(70, 200), adjustableColumn=2,
                                          annotation="空ならベース名_BS")
    _CTRL["front"] = cmds.checkBox(
        label="デフォーマの先頭に入れる（Front of chain）",
        value=bool(_get_opt(_OPTVAR_FRONT, 1)))
    cmds.button(label="選択から作成（ターゲット → ベースの順に選択）", height=28,
                command=_on_create)
    cmds.setParent("..")
    cmds.setParent("..")

    # --- ターゲット -----------------------------------------------------------
    _frame("ターゲット")
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    cmds.rowLayout(numberOfColumns=3, adjustableColumn=1, columnWidth3=(200, 70, 50))
    _CTRL["node_menu"] = cmds.optionMenu(changeCommand=_on_node_changed)
    cmds.button(label="選択から", command=_on_load_selection,
                annotation="選択したメッシュのヒストリから blendShape を探す")
    cmds.button(label="更新", command=lambda *_: _refresh_nodes())
    cmds.setParent("..")
    _CTRL["base_info"] = cmds.text(label="", align="left")

    cmds.rowLayout(numberOfColumns=3, adjustableColumn=1, columnWidth3=(200, 70, 70))
    _CTRL["filter"] = cmds.textField(placeholderText="絞り込み（空白区切りで OR）",
                                     changeCommand=lambda *_: _rebuild_rows())
    cmds.button(label="全チェック", command=lambda *_: _on_check_all(True))
    cmds.button(label="全解除", command=lambda *_: _on_check_all(False))
    cmds.setParent("..")

    cmds.scrollLayout(height=260, childResizable=True)
    _CTRL["list"] = cmds.columnLayout(adjustableColumn=True, rowSpacing=1)
    cmds.setParent("..")
    cmds.setParent("..")

    cmds.rowLayout(numberOfColumns=2, adjustableColumn=1, columnWidth2=(200, 200))
    cmds.button(label="選択メッシュをターゲットに追加", command=_on_add_targets)
    cmds.button(label="チェックしたものを削除", command=_on_delete)
    cmds.setParent("..")
    cmds.rowLayout(numberOfColumns=3, adjustableColumn=3, columnWidth3=(130, 130, 130))
    cmds.button(label="チェック → 0", command=_set_weight_action(0.0, False))
    cmds.button(label="チェック → 1", command=_set_weight_action(1.0, False))
    cmds.button(label="表示中を全部 → 0", command=_set_weight_action(0.0, True))
    cmds.setParent("..")
    cmds.setParent("..")
    cmds.setParent("..")

    # --- 名前 ---------------------------------------------------------------
    _frame("名前", collapse=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    _CTRL["rename"] = cmds.textFieldGrp(label="新しい名前", columnWidth2=(70, 200),
                                        adjustableColumn=2)
    cmds.button(label="チェックした 1 つをリネーム", command=_on_rename_one)
    cmds.separator(height=6, style="in")
    _CTRL["search"] = cmds.textFieldGrp(label="検索", columnWidth2=(70, 200),
                                        adjustableColumn=2)
    _CTRL["replace"] = cmds.textFieldGrp(label="置換", columnWidth2=(70, 200),
                                         adjustableColumn=2)
    _CTRL["prefix"] = cmds.textFieldGrp(label="接頭辞", columnWidth2=(70, 200),
                                        adjustableColumn=2)
    _CTRL["suffix"] = cmds.textFieldGrp(label="接尾辞", columnWidth2=(70, 200),
                                        adjustableColumn=2)
    cmds.button(label="一括リネーム（チェックしたもの / 無ければ表示中の全部）",
                command=_on_batch_rename)
    cmds.setParent("..")
    cmds.setParent("..")

    # --- インビトウィーン ---------------------------------------------------
    _frame("インビトウィーン", collapse=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    _CTRL["ib_weight"] = cmds.floatFieldGrp(label="重み", numberOfFields=1,
                                            value1=0.5, precision=3,
                                            columnWidth2=(70, 80))
    cmds.button(label="選択メッシュをチェックした 1 つのインビトウィーンに追加",
                command=_on_add_inbetween)
    cmds.setParent("..")
    cmds.setParent("..")

    # --- ミラー -------------------------------------------------------------
    _frame("ミラー", collapse=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    axis = _get_opt(_OPTVAR_AXIS, "x")
    _CTRL["axis"] = cmds.radioButtonGrp(
        label="対称軸", numberOfRadioButtons=3, labelArray3=("X", "Y", "Z"),
        select=(core.AXES.index(axis) + 1) if axis in core.AXES else 1,
        columnWidth4=(70, 50, 50, 50))
    _CTRL["tolerance"] = cmds.floatFieldGrp(
        label="許容誤差", numberOfFields=1, precision=4,
        value1=float(_get_opt(_OPTVAR_TOLERANCE, 0.001)), columnWidth2=(70, 80),
        annotation="左右の頂点を位置で対応させるときの距離（オブジェクト空間）")
    _CTRL["overwrite"] = cmds.checkBox(
        label="反対側の名前のターゲットが既にあれば上書きする",
        value=bool(_get_opt(_OPTVAR_OVERWRITE, 1)))
    cmds.button(label="チェックしたターゲットの反対側を作成（L_ ↔ R_ など）", height=28,
                command=_on_mirror)
    cmds.setParent("..")
    cmds.setParent("..")

    _CTRL["status"] = cmds.text(label="", align="left")


def show():
    """ツールウィンドウを開く（既に開いていれば作り直す）。"""
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW)
    _CTRL.clear()
    _ROWS.clear()

    win = cmds.window(WINDOW, title="%s  —  v%s" % (_TITLE, __version__),
                      widthHeight=(440, 720),
                      minimizeButton=True, maximizeButton=False, sizeable=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6, columnAttach=("both", 6))

    _build_body()

    # バージョン表示 + 「GitHub から更新」。 全ツール共通なので消さない
    dev_tools.build_footer()

    cmds.showWindow(win)
    _refresh_nodes()
    return win
