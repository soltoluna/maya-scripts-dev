# -*- coding: utf-8 -*-
"""Penetration Checker — `maya.cmds` による UI。

ここは「値を集める → `scene.check` に渡す → 結果を一覧と選択に流す」だけに保つ。
判定・集計・探索は `core`（Maya 非依存）と `scene`（シーンを読む層）にある。

**シーンを変更しない。** 結果として変わるのは選択だけ（`cmds.select` は
Maya の undo に積まれるので、ここで undo チャンクは開かない）。
"""

from __future__ import annotations

from maya import cmds

from . import NAMESPACE, __version__, core, dev_tools


_PACKAGE = __package__ or __name__.rsplit(".", 1)[0]
_NS = "%s_%s" % (NAMESPACE, _PACKAGE)          # ntk_penetration_checker

# `<NAMESPACE>_<モジュール名>Win` 固定（ハブが同じ規則で古いウィンドウを閉じる）
WINDOW = _NS + "Win"

_OPTVAR_TOLERANCE = _NS + "_tolerance"
_OPTVAR_OPEN_CONTAINERS = _NS + "_open_containers"
_OPTVAR_SKIP_HIDDEN = _NS + "_skip_hidden"
_OPTVAR_AUTO_SELECT = _NS + "_auto_select"

_CTRL = {}       # コントロール名の控え。 show() のたびに作り直す
_STATE = {
    "targets": [],   # 検査対象（ユーザーが登録したノード。 グループ可）
    "result": None,  # 直近の scene.check() の戻り値
}


def _scene():
    # scene は OpenMaya を使う。 import をここに閉じ込めておくと、
    # テストでは差し替えやすく、UI を開くだけなら API を触らない
    from . import scene
    return scene


# --------------------------------------------------------------------------- #
# 設定
# --------------------------------------------------------------------------- #

def _get_opt(key, default):
    if cmds.optionVar(exists=key):
        value = cmds.optionVar(q=key)
        return default if value is None else value
    return default


def _save_options(*_args):
    cmds.optionVar(fv=(_OPTVAR_TOLERANCE,
                       cmds.floatFieldGrp(_CTRL["tolerance"], q=True, v1=True) or 0.0))
    cmds.optionVar(iv=(_OPTVAR_OPEN_CONTAINERS,
                       int(bool(cmds.checkBox(_CTRL["open"], q=True, v=True)))))
    cmds.optionVar(iv=(_OPTVAR_SKIP_HIDDEN,
                       int(bool(cmds.checkBox(_CTRL["hidden"], q=True, v=True)))))
    cmds.optionVar(iv=(_OPTVAR_AUTO_SELECT,
                       int(bool(cmds.checkBox(_CTRL["auto"], q=True, v=True)))))


# --------------------------------------------------------------------------- #
# 対象リスト
# --------------------------------------------------------------------------- #

def _refresh_target_list():
    ctrl = _CTRL.get("targets")
    if not ctrl:
        return
    cmds.textScrollList(ctrl, e=True, removeAll=True)
    for node in _STATE["targets"]:
        cmds.textScrollList(ctrl, e=True, append=core.short_name(node))
    cmds.text(_CTRL["target_count"], e=True,
              label="対象: %d 個（空なら選択中のものを調べる）"
              % len(_STATE["targets"]))


def _on_add(*_args):
    for node in cmds.ls(selection=True, long=True, objectsOnly=True) or []:
        if node not in _STATE["targets"]:
            _STATE["targets"].append(node)
    _refresh_target_list()


def _on_remove(*_args):
    picked = cmds.textScrollList(_CTRL["targets"], q=True, selectIndexedItem=True) or []
    for index in sorted(picked, reverse=True):
        if 1 <= index <= len(_STATE["targets"]):
            del _STATE["targets"][index - 1]
    _refresh_target_list()


def _on_clear(*_args):
    del _STATE["targets"][:]
    _refresh_target_list()


def _on_target_picked(*_args):
    picked = cmds.textScrollList(_CTRL["targets"], q=True, selectIndexedItem=True) or []
    nodes = [_STATE["targets"][i - 1] for i in picked
             if 1 <= i <= len(_STATE["targets"])]
    nodes = [n for n in nodes if cmds.objExists(n)]
    if nodes:
        cmds.select(nodes, replace=True)


# --------------------------------------------------------------------------- #
# 判定
# --------------------------------------------------------------------------- #

def _set_status(message):
    if _CTRL.get("status"):
        cmds.text(_CTRL["status"], e=True, label=message)


def _on_check(*_args):
    _save_options()
    nodes = list(_STATE["targets"]) or (
        cmds.ls(selection=True, long=True, objectsOnly=True) or [])
    if not nodes:
        cmds.warning("[%s] 対象が登録されておらず、何も選択されていません。" % _PACKAGE)
        return

    scene = _scene()
    tolerance = cmds.floatFieldGrp(_CTRL["tolerance"], q=True, v1=True) or 0.0

    cmds.progressWindow(title="Penetration Checker", progress=0, maxValue=100,
                        status="調べています...", isInterruptable=True)
    try:
        def progress(done, total, label):
            if cmds.progressWindow(q=True, isCancelled=True):
                return False
            cmds.progressWindow(e=True, progress=int(100.0 * done / max(total, 1)),
                                status=label)
            return True

        result = scene.check(
            nodes, tolerance_ui=tolerance,
            use_open_containers=bool(cmds.checkBox(_CTRL["open"], q=True, v=True)),
            skip_hidden=bool(cmds.checkBox(_CTRL["hidden"], q=True, v=True)),
            progress=progress)
    finally:
        cmds.progressWindow(endProgress=True)

    _STATE["result"] = result
    _show_result(result, scene)

    targets = result.get("targets") or []
    if targets and cmds.checkBox(_CTRL["auto"], q=True, v=True):
        cmds.textScrollList(_CTRL["results"], e=True, selectIndexedItem=1)
        _select_target(0)


def _show_result(result, scene):
    ctrl = _CTRL["results"]
    cmds.textScrollList(ctrl, e=True, removeAll=True)
    unit = scene.ui_unit()
    for entry in result.get("targets") or []:
        shown = dict(entry, depth=scene.to_ui_distance(entry.get("depth", 0.0)))
        cmds.textScrollList(ctrl, e=True, append=core.format_target_row(shown, unit))

    for message in result.get("warnings") or []:
        print("[%s] %s" % (_PACKAGE, message))

    frame = core.format_frame(cmds.currentTime(q=True))
    if result.get("cancelled"):
        status = "中断しました（途中までの結果）"
    elif result.get("targets"):
        status = "フレーム %s: %d 組のめり込み" % (frame, len(result.get("hits") or []))
    else:
        status = "フレーム %s: めり込みなし（%d メッシュ / %d 組を調査）" % (
            frame, len(result.get("meshes") or []), len(result.get("pairs") or []))
    if result.get("warnings"):
        status += "  ※警告 %d 件（Script Editor）" % len(result["warnings"])
    _set_status(status)


def _picked_result_index():
    picked = cmds.textScrollList(_CTRL["results"], q=True, selectIndexedItem=True) or []
    return picked[0] - 1 if picked else None


def _current_entry(index=None):
    result = _STATE.get("result") or {}
    targets = result.get("targets") or []
    if index is None:
        index = _picked_result_index()
    if index is None or not 0 <= index < len(targets):
        return None
    return targets[index]


def _select_target(index=None):
    entry = _current_entry(index)
    if not entry:
        return
    node = entry["target"]
    if not cmds.objExists(node):
        cmds.warning("[%s] %s はもう存在しません。" % (_PACKAGE, node))
        return
    cmds.select(node, replace=True)


def _on_result_picked(*_args):
    _select_target()


def _on_select_vertices(*_args):
    entry = _current_entry()
    if not entry:
        cmds.warning("[%s] 結果の行を選んでください。" % _PACKAGE)
        return
    result = _STATE.get("result") or {}
    pairs = set(tuple(p) for p in entry.get("pairs") or [])
    components = []
    for hit in result.get("hits") or []:
        if (hit["mesh"], hit["other"]) not in pairs:
            continue
        components.extend("%s.vtx[%d]" % (hit["mesh"], index)
                          for index, _depth in hit["vertices"])
    components = [c for c in components if cmds.objExists(c.split(".", 1)[0])]
    if components:
        cmds.select(components, replace=True)


# --------------------------------------------------------------------------- #
# ウィンドウ
# --------------------------------------------------------------------------- #

def _build_body():
    cmds.separator(h=4, style="none")
    cmds.text(l="対象（オブジェクト / グループ）", al="left", fn="boldLabelFont")
    _CTRL["targets"] = cmds.textScrollList(
        numberOfRows=6, allowMultiSelection=True, sc=_on_target_picked,
        ann="ここに登録したもの（グループは配下のメッシュ全部）を総当たりで調べます")
    cmds.rowLayout(nc=3, adj=3, cw3=(110, 110, 80))
    cmds.button(l="選択を追加", h=24, c=_on_add)
    cmds.button(l="リストから外す", h=24, c=_on_remove)
    cmds.button(l="クリア", h=24, c=_on_clear)
    cmds.setParent("..")
    _CTRL["target_count"] = cmds.text(l="", al="left")

    cmds.separator(h=8, style="in")
    _CTRL["tolerance"] = cmds.floatFieldGrp(
        label="許容する深さ", numberOfFields=1, precision=3,
        v1=float(_get_opt(_OPTVAR_TOLERANCE, 0.0)), cw2=(90, 80),
        ann="この深さ以下のめり込みは無視します（シーンの単位）")
    _CTRL["open"] = cmds.checkBox(
        l="開いたメッシュも「内側」があるものとして調べる",
        v=bool(_get_opt(_OPTVAR_OPEN_CONTAINERS, 0)),
        ann="オフ: 境界のあるメッシュ（1 枚布など）は、めり込まれる側として"
            "調べません（裏側を内側とみなすと誤検出が多いため）")
    _CTRL["hidden"] = cmds.checkBox(
        l="非表示のメッシュを除く", v=bool(_get_opt(_OPTVAR_SKIP_HIDDEN, 1)))
    _CTRL["auto"] = cmds.checkBox(
        l="最も影響の大きいコントローラーを自動で選択",
        v=bool(_get_opt(_OPTVAR_AUTO_SELECT, 1)))

    cmds.button(l="現在のフレームを調べる", h=34, c=_on_check, bgc=(0.36, 0.45, 0.55))

    cmds.separator(h=8, style="in")
    cmds.text(l="結果（影響の大きい順。 クリックで選択）", al="left", fn="boldLabelFont")
    _CTRL["results"] = cmds.textScrollList(numberOfRows=8, allowMultiSelection=False,
                                           sc=_on_result_picked)
    cmds.rowLayout(nc=2, adj=2, cw2=(150, 150))
    cmds.button(l="コントローラーを選択", h=24, c=lambda *_: _select_target())
    cmds.button(l="めり込み頂点を選択", h=24, c=_on_select_vertices)
    cmds.setParent("..")
    _CTRL["status"] = cmds.text(l="", al="left")

    _refresh_target_list()


def show():
    """ツールウィンドウを開く（既に開いていれば作り直す）。"""
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW)
    _CTRL.clear()

    win = cmds.window(WINDOW,
                      title="Penetration Checker  —  v%s" % (__version__,),
                      widthHeight=(380, 560),
                      minimizeButton=True, maximizeButton=False, sizeable=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6,
                      columnAttach=("both", 10))

    _build_body()

    # バージョン表示 + 「GitHub から更新」。 全ツール共通なので消さない
    dev_tools.build_footer()

    cmds.showWindow(win)
    return win
