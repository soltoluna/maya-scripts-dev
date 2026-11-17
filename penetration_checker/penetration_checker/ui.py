# -*- coding: utf-8 -*-
"""Penetration Checker — `maya.cmds` による UI。

ここは「値を集める → `core` / `scene` に渡す → 結果を一覧・HUD・選択に流す」
だけに保つ。 判定・スキャン・区間のまとめは `core`、シーンの読み取りと
時間の移動は `scene` にある。

3 つの入口が同じ結果表（`_STATE["results"]` = `{frame: 1 フレーム分の結果}`）に書く:

* 現在のフレームを調べる
* タイムスライダーの範囲をスキャン（時間を動かして全フレーム。 終わったら戻す）
* ライブ — `timeChanged` のたびに調べる（再生しながら / スクラブしながら）

ライブがオフでも、`timeChanged` では結果表を引いて HUD を更新する。 スキャンして
から再生すると、どのフレームでめり込むかがビューポート上で追える。

**シーンを変更しない。** 変わるのは選択と時間（スキャン中のみ・元に戻す）と
HUD（ウィンドウを閉じると消す）だけ。
"""

from __future__ import annotations

from maya import cmds

from . import NAMESPACE, __version__, core, dev_tools


_PACKAGE = __package__ or __name__.rsplit(".", 1)[0]
_NS = "%s_%s" % (NAMESPACE, _PACKAGE)          # ntk_penetration_checker

# `<NAMESPACE>_<モジュール名>Win` 固定（ハブが同じ規則で古いウィンドウを閉じる）
WINDOW = _NS + "Win"
HUD = _NS + "_hud"
_HUD_SECTION = 7      # ビューポート下段の中央

_OPTVAR_TOLERANCE = _NS + "_tolerance"
_OPTVAR_OPEN_CONTAINERS = _NS + "_open_containers"
_OPTVAR_SKIP_HIDDEN = _NS + "_skip_hidden"
_OPTVAR_AUTO_SELECT = _NS + "_auto_select"
_OPTVAR_SHOW_HUD = _NS + "_show_hud"

_CTRL = {}       # コントロール名の控え。 show() のたびに作り直す
_STATE = {
    "targets": [],     # 検査対象（ユーザーが登録したノード。 グループ可）
    "checker": None,   # core.Checker。 対象や設定が変わったら作り直す
    "results": {},     # {frame: 1 フレーム分の結果}
    "groups": [],      # core.group_frames(results)
    "frame": None,     # 内訳に出しているフレーム
    "busy": False,     # スキャン中（timeChanged を無視する）
    "printed": 0,      # checker.warnings のうち Script Editor に出した数
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


def _checked(name):
    return bool(cmds.checkBox(_CTRL[name], q=True, v=True))


def _tolerance():
    return cmds.floatFieldGrp(_CTRL["tolerance"], q=True, v1=True) or 0.0


def _save_options():
    cmds.optionVar(fv=(_OPTVAR_TOLERANCE, _tolerance()))
    cmds.optionVar(iv=(_OPTVAR_OPEN_CONTAINERS, int(_checked("open"))))
    cmds.optionVar(iv=(_OPTVAR_SKIP_HIDDEN, int(_checked("hidden"))))
    cmds.optionVar(iv=(_OPTVAR_AUTO_SELECT, int(_checked("auto"))))
    cmds.optionVar(iv=(_OPTVAR_SHOW_HUD, int(_checked("hud"))))


def _on_condition_changed(*_args):
    """判定の条件（対象・許容値・オプション）が変わった。 結果はもう当てにならない。"""
    _save_options()
    _STATE["checker"] = None
    _clear_results()


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
    _on_condition_changed()


def _on_remove(*_args):
    picked = cmds.textScrollList(_CTRL["targets"], q=True, selectIndexedItem=True) or []
    for index in sorted(picked, reverse=True):
        if 1 <= index <= len(_STATE["targets"]):
            del _STATE["targets"][index - 1]
    _refresh_target_list()
    _on_condition_changed()


def _on_clear_targets(*_args):
    del _STATE["targets"][:]
    _refresh_target_list()
    _on_condition_changed()


def _on_target_picked(*_args):
    picked = cmds.textScrollList(_CTRL["targets"], q=True, selectIndexedItem=True) or []
    nodes = [_STATE["targets"][i - 1] for i in picked
             if 1 <= i <= len(_STATE["targets"])]
    nodes = [n for n in nodes if cmds.objExists(n)]
    if nodes:
        cmds.select(nodes, replace=True)


# --------------------------------------------------------------------------- #
# Checker
# --------------------------------------------------------------------------- #

def _ensure_checker():
    """`core.Checker` を返す（無ければ作る）。 作れなければ警告して `None`。"""
    if _STATE["checker"] is not None:
        return _STATE["checker"]
    nodes = list(_STATE["targets"]) or (
        cmds.ls(selection=True, long=True, objectsOnly=True) or [])
    if not nodes:
        cmds.warning("[%s] 対象が登録されておらず、何も選択されていません。" % _PACKAGE)
        return None
    checker, _meshes, warnings = _scene().make_checker(
        nodes, tolerance_ui=_tolerance(), use_open_containers=_checked("open"),
        skip_hidden=_checked("hidden"))
    for message in warnings:
        print("[%s] %s" % (_PACKAGE, message))
    if checker is None:
        cmds.warning("[%s] %s" % (_PACKAGE, warnings[-1] if warnings
                                  else "調べられるメッシュがありません。"))
        return None
    _STATE["checker"] = checker
    _STATE["printed"] = 0
    return checker


def _flush_warnings():
    checker = _STATE.get("checker")
    if checker is None:
        return 0
    new = checker.warnings[_STATE["printed"]:]
    for message in new:
        print("[%s] %s" % (_PACKAGE, message))
    _STATE["printed"] = len(checker.warnings)
    return len(checker.warnings)


# --------------------------------------------------------------------------- #
# HUD
# --------------------------------------------------------------------------- #
# HUD が出せなくても判定は止めない（警告だけ出して続ける）。

def _hud_remove():
    try:
        if cmds.headsUpDisplay(HUD, exists=True):
            cmds.headsUpDisplay(HUD, remove=True)
    except Exception as exc:
        print("[%s] HUD を消せませんでした: %s" % (_PACKAGE, exc))


def _hud_create():
    _hud_remove()
    try:
        block = cmds.headsUpDisplay(nextFreeBlock=_HUD_SECTION)
        cmds.headsUpDisplay(HUD, section=_HUD_SECTION, block=block,
                            blockSize="medium", labelFontSize="large",
                            label="Penetration: --")
    except Exception as exc:
        print("[%s] HUD を作れませんでした: %s" % (_PACKAGE, exc))


def _hud_set(result):
    if not _CTRL.get("hud") or not _checked("hud"):
        return
    try:
        if not cmds.headsUpDisplay(HUD, exists=True):
            _hud_create()
        scene = _scene()
        text = core.hud_text(result, scene.ui_unit(), scene.to_ui_distance)
        cmds.headsUpDisplay(HUD, edit=True, label="Penetration: " + text)
    except Exception as exc:
        print("[%s] HUD を更新できませんでした: %s" % (_PACKAGE, exc))


def _on_hud_toggled(*_args):
    _save_options()
    if _checked("hud"):
        _hud_create()
        _hud_set(_STATE["results"].get(_current_frame()))
    else:
        _hud_remove()


# --------------------------------------------------------------------------- #
# 判定
# --------------------------------------------------------------------------- #

def _current_frame():
    try:
        return _scene().current_frame()
    except Exception:
        return None


def _set_status(message):
    if _CTRL.get("status"):
        cmds.text(_CTRL["status"], e=True, label=message)


def _progress_fn():
    def progress(done, total, label):
        if cmds.progressWindow(q=True, isCancelled=True):
            return False
        cmds.progressWindow(e=True, progress=int(100.0 * done / max(total, 1)),
                            status=label)
        return True
    return progress


def _on_check_current(*_args):
    checker = _ensure_checker()
    if checker is None:
        return
    frame = _current_frame()
    cmds.progressWindow(title="Penetration Checker", progress=0, maxValue=100,
                        status="調べています...", isInterruptable=True)
    try:
        result = checker.check_frame(progress=_progress_fn())
    finally:
        cmds.progressWindow(endProgress=True)

    _STATE["results"][frame] = result
    _refresh_results(frame)
    _hud_set(result)
    targets = result.get("targets") or []
    status = "フレーム %s: " % core.format_frame(frame)
    if result.get("cancelled"):
        status += "中断しました（途中までの結果）"
    elif targets:
        status += "%d 組のめり込み" % len(result.get("hits") or [])
    else:
        status += "めり込みなし（%d 組を調査）" % result.get("pairs", 0)
    _set_status(status + _warning_note())
    if targets and _checked("auto"):
        cmds.textScrollList(_CTRL["detail"], e=True, selectIndexedItem=1)
        _select_detail(0)


def _on_scan(*_args):
    checker = _ensure_checker()
    if checker is None:
        return
    scene = _scene()
    start, end, label = scene.time_range()
    frames = core.frame_list(start, end)
    original = scene.current_frame()

    _STATE["busy"] = True
    cmds.progressWindow(title="Penetration Checker", progress=0, maxValue=100,
                        status="スキャンしています...", isInterruptable=True)
    try:
        results, cancelled = core.scan(checker, frames, scene.set_frame,
                                       progress=_progress_fn())
    finally:
        # 例外でも時間と進捗表示は必ず戻す
        try:
            scene.set_frame(original)
        finally:
            _STATE["busy"] = False
            cmds.progressWindow(endProgress=True)

    _STATE["results"].update(results)
    _refresh_results(original)
    _hud_set(_STATE["results"].get(original))

    hit_frames = sum(1 for r in results.values() if r.get("targets"))
    status = "%s-%s（%s）: %d フレーム中 %d フレームでめり込み / %d 区間" % (
        core.format_frame(start), core.format_frame(end), label, len(results),
        hit_frames, len(_STATE["groups"]))
    if cancelled:
        status = "中断: " + status
    _set_status(status + _warning_note())


def _warning_note():
    count = _flush_warnings()
    return "  ※警告 %d 件（Script Editor）" % count if count else ""


def _clear_results(*_args):
    _STATE["results"] = {}
    _STATE["groups"] = []
    _STATE["frame"] = None
    if _CTRL.get("ranges"):
        _refresh_results(None)
        _set_status("")
    _hud_set(None)


# --------------------------------------------------------------------------- #
# 時間の変化（ライブ / HUD）
# --------------------------------------------------------------------------- #

def _on_time_changed():
    """`timeChanged` の scriptJob。 再生中は毎フレーム呼ばれるので軽く保つ。

    ライブなら調べて結果表に書き、そうでなければ結果表を引くだけ。
    **ここで例外を上げない**（再生中に毎フレームエラーが出続けるため）。
    ライブの判定に失敗したらライブを切って 1 度だけ警告する。
    """
    if _STATE["busy"] or not _CTRL.get("live"):
        return
    try:
        frame = _current_frame()
        result = _STATE["results"].get(frame)
        if _checked("live"):
            checker = _ensure_checker()
            if checker is None:
                cmds.checkBox(_CTRL["live"], e=True, v=False)
            else:
                try:
                    result = checker.check_frame()
                    _STATE["results"][frame] = result
                except Exception as exc:
                    cmds.checkBox(_CTRL["live"], e=True, v=False)
                    cmds.warning("[%s] ライブの判定に失敗したので止めました: %s"
                                 % (_PACKAGE, exc))
        _hud_set(result)
        if not _scene().is_playing():
            _refresh_results(frame)
    except Exception as exc:
        print("[%s] timeChanged: %s" % (_PACKAGE, exc))


def _on_playback_stopped():
    """再生が止まったら一覧をまとめて更新する（再生中は HUD だけにしている）。"""
    try:
        _refresh_results(_current_frame())
        _warning_note()
    except Exception as exc:
        print("[%s] playback stopped: %s" % (_PACKAGE, exc))


def _on_live_toggled(*_args):
    if _checked("live"):
        if _ensure_checker() is None:
            cmds.checkBox(_CTRL["live"], e=True, v=False)
            return
        _set_status("ライブ: 時間を動かすと調べます。 再生が遅くなるときは"
                    "「Play every frame」で再生してください")
        _on_time_changed()


def _on_window_closed():
    _hud_remove()


def _on_scene_changed():
    """シーンを開き直した / 新規にした。 対象も結果も前のシーンのもの。"""
    del _STATE["targets"][:]
    _STATE["checker"] = None
    _clear_results()
    _refresh_target_list()


def _install_jobs():
    # timeChanged / 再生停止はウィンドウに親子付けして、閉じたら自動で消す
    cmds.scriptJob(event=["timeChanged", _on_time_changed], parent=WINDOW)
    cmds.scriptJob(conditionFalse=["playingBack", _on_playback_stopped],
                   parent=WINDOW)
    for event in ("SceneOpened", "NewSceneOpened"):
        cmds.scriptJob(event=[event, _on_scene_changed], parent=WINDOW)
    # uiDeleted はウィンドウに親子付けできない（消えた瞬間に自分も消える）
    cmds.scriptJob(uiDeleted=[WINDOW, _on_window_closed], runOnce=True)


# --------------------------------------------------------------------------- #
# 結果の表示
# --------------------------------------------------------------------------- #

def _refresh_results(frame):
    """区間一覧と、`frame` の内訳を作り直す。"""
    scene = _scene()
    unit = scene.ui_unit()
    _STATE["groups"] = core.group_frames(_STATE["results"])
    cmds.textScrollList(_CTRL["ranges"], e=True, removeAll=True)
    for group in _STATE["groups"]:
        cmds.textScrollList(_CTRL["ranges"], e=True, append=core.format_range_row(
            group, unit, scene.to_ui_distance))

    _STATE["frame"] = frame
    cmds.textScrollList(_CTRL["detail"], e=True, removeAll=True)
    result = _STATE["results"].get(frame) if frame is not None else None
    if result is None:
        title = "内訳: フレーム %s（未調査）" % core.format_frame(frame)
    else:
        title = "内訳: フレーム %s" % core.format_frame(frame)
        for entry in result.get("targets") or []:
            shown = dict(entry, depth=scene.to_ui_distance(entry.get("depth", 0.0)))
            cmds.textScrollList(_CTRL["detail"], e=True,
                                append=core.format_target_row(shown, unit))
    cmds.text(_CTRL["detail_title"], e=True, label=title)


def _picked(ctrl):
    picked = cmds.textScrollList(_CTRL[ctrl], q=True, selectIndexedItem=True) or []
    return picked[0] - 1 if picked else None


def _detail_entry(index=None):
    result = _STATE["results"].get(_STATE["frame"]) or {}
    targets = result.get("targets") or []
    if index is None:
        index = _picked("detail")
    if index is None or not 0 <= index < len(targets):
        return None
    return targets[index]


def _select_detail(index=None):
    entry = _detail_entry(index)
    if not entry:
        return
    node = entry["target"]
    if not cmds.objExists(node):
        cmds.warning("[%s] %s はもう存在しません。" % (_PACKAGE, node))
        return
    cmds.select(node, replace=True)


def _on_range_picked(*_args):
    """区間をクリック — 最も深いフレームへ移動し、その内訳を出す。"""
    index = _picked("ranges")
    if index is None or not 0 <= index < len(_STATE["groups"]):
        return
    frame = _STATE["groups"][index]["worst_frame"]
    _scene().set_frame(frame)
    _refresh_results(frame)
    cmds.textScrollList(_CTRL["ranges"], e=True, selectIndexedItem=index + 1)
    _hud_set(_STATE["results"].get(frame))
    if _checked("auto") and _detail_entry(0):
        cmds.textScrollList(_CTRL["detail"], e=True, selectIndexedItem=1)
        _select_detail(0)


def _on_detail_picked(*_args):
    _select_detail()


def _on_select_vertices(*_args):
    entry = _detail_entry()
    if not entry:
        cmds.warning("[%s] 内訳の行を選んでください。" % _PACKAGE)
        return
    result = _STATE["results"].get(_STATE["frame"]) or {}
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
        numberOfRows=5, allowMultiSelection=True, sc=_on_target_picked,
        ann="ここに登録したもの（グループは配下のメッシュ全部）を総当たりで調べます")
    cmds.rowLayout(nc=3, adj=3, cw3=(110, 110, 80))
    cmds.button(l="選択を追加", h=24, c=_on_add)
    cmds.button(l="リストから外す", h=24, c=_on_remove)
    cmds.button(l="クリア", h=24, c=_on_clear_targets)
    cmds.setParent("..")
    _CTRL["target_count"] = cmds.text(l="", al="left")

    cmds.separator(h=8, style="in")
    _CTRL["tolerance"] = cmds.floatFieldGrp(
        label="許容する深さ", numberOfFields=1, precision=3,
        v1=float(_get_opt(_OPTVAR_TOLERANCE, 0.0)), cw2=(90, 80),
        cc=_on_condition_changed,
        ann="この深さ以下のめり込みは無視します（シーンの単位）")
    _CTRL["open"] = cmds.checkBox(
        l="開いたメッシュも「内側」があるものとして調べる",
        v=bool(_get_opt(_OPTVAR_OPEN_CONTAINERS, 0)), cc=_on_condition_changed,
        ann="オフ: 境界のあるメッシュ（1 枚布など）は、めり込まれる側として"
            "調べません（裏側を内側とみなすと誤検出が多いため）")
    _CTRL["hidden"] = cmds.checkBox(
        l="非表示のメッシュを除く", v=bool(_get_opt(_OPTVAR_SKIP_HIDDEN, 1)),
        cc=_on_condition_changed)
    _CTRL["auto"] = cmds.checkBox(
        l="最も影響の大きいコントローラーを自動で選択",
        v=bool(_get_opt(_OPTVAR_AUTO_SELECT, 1)), cc=lambda *_: _save_options())

    cmds.separator(h=8, style="in")
    cmds.rowLayout(nc=2, adj=2, cw2=(150, 150))
    cmds.button(l="現在のフレーム", h=32, c=_on_check_current)
    cmds.button(l="タイムスライダーの範囲をスキャン", h=32, c=_on_scan,
                bgc=(0.36, 0.45, 0.55),
                ann="タイムスライダーで範囲を選んでいればその範囲、"
                    "無ければ再生範囲を 1 フレームずつ調べます（Esc で中断）")
    cmds.setParent("..")
    cmds.rowLayout(nc=2, adj=2, cw2=(150, 150))
    _CTRL["live"] = cmds.checkBox(
        l="ライブ（再生しながら）", v=False, cc=_on_live_toggled,
        ann="時間が変わるたびに調べます。 重いシーンでは再生が遅くなります")
    _CTRL["hud"] = cmds.checkBox(
        l="ビューに HUD を表示", v=bool(_get_opt(_OPTVAR_SHOW_HUD, 1)),
        cc=_on_hud_toggled,
        ann="ビューポート下に現在のフレームの結果を出します。 スキャン後に"
            "再生すると、めり込むフレームが追えます")
    cmds.setParent("..")

    cmds.separator(h=8, style="in")
    cmds.rowLayout(nc=2, adj=1, cw2=(200, 90))
    cmds.text(l="めり込み区間（クリックで最深フレームへ）", al="left",
              fn="boldLabelFont")
    cmds.button(l="結果をクリア", h=22, c=_clear_results)
    cmds.setParent("..")
    _CTRL["ranges"] = cmds.textScrollList(numberOfRows=7, allowMultiSelection=False,
                                          sc=_on_range_picked)
    _CTRL["detail_title"] = cmds.text(l="内訳", al="left", fn="boldLabelFont")
    _CTRL["detail"] = cmds.textScrollList(numberOfRows=5, allowMultiSelection=False,
                                          sc=_on_detail_picked)
    cmds.rowLayout(nc=2, adj=2, cw2=(150, 150))
    cmds.button(l="コントローラーを選択", h=24, c=lambda *_: _select_detail())
    cmds.button(l="めり込み頂点を選択", h=24, c=_on_select_vertices)
    cmds.setParent("..")
    _CTRL["status"] = cmds.text(l="", al="left")

    _refresh_target_list()


def show():
    """ツールウィンドウを開く（既に開いていれば作り直す）。"""
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW)
    _CTRL.clear()
    # 開き直したらシーンが変わっているかもしれないので、結果は持ち越さない
    _STATE["checker"] = None
    _STATE["results"] = {}
    _STATE["groups"] = []

    win = cmds.window(WINDOW,
                      title="Penetration Checker  —  v%s" % (__version__,),
                      widthHeight=(400, 700),
                      minimizeButton=True, maximizeButton=False, sizeable=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6,
                      columnAttach=("both", 10))

    _build_body()

    # バージョン表示 + 「GitHub から更新」。 全ツール共通なので消さない
    dev_tools.build_footer()

    cmds.showWindow(win)
    _install_jobs()
    if _checked("hud"):
        _hud_create()
    try:
        _refresh_results(_current_frame())
    except Exception as exc:
        print("[%s] %s" % (_PACKAGE, exc))
    return win
