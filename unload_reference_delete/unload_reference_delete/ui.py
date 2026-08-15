# -*- coding: utf-8 -*-
"""Unload Reference Delete — `maya.cmds` による UI。

ここは「`cmds` で値を集める → `core` に渡す → 結果を `cmds` に流す」だけに保つ。
判定を書き始めたら `core.py` へ移す（自宅に Maya が無いので、`core` に無い処理は
実機に持っていくまで一度も実行されない）。

**`cmds.file(removeReference=True)` は undo できない。** undo チャンクで囲っても
戻せないので、代わりに確認ダイアログで守っている（`SPEC.md` の設計判断）。
"""

from __future__ import annotations

from maya import cmds

from . import NAMESPACE, __version__, core, dev_tools


# Maya の optionVar / scriptJob / ウィンドウ名はフラットな 1 つの名前空間を
# 共有する。 汎用名は他人のツールと**後勝ちで静かに衝突する**ので、
# この 3 つには必ず `<NAMESPACE>_<モジュール名>` を付ける。
_PACKAGE = __package__ or __name__.rsplit(".", 1)[0]
_NS = "%s_%s" % (NAMESPACE, _PACKAGE)          # ntk_unload_reference_delete

# ウィンドウ名は `<NAMESPACE>_<モジュール名>Win` 固定。 install.py の
# `_close_existing_window()` が同じ規則で古いウィンドウを探す
WINDOW = _NS + "Win"

_OPTVAR_CONFIRM = _NS + "_confirm_before_remove"

TITLE = "Unload Reference Delete"

_CTRL = {}   # コントロール名の控え。 show() のたびに作り直す
_ROWS = []   # スクロールリストの行と同じ順の ReferenceEntry


# --------------------------------------------------------------------------- #
# Maya からの読み取り — ここだけが `cmds` に触る
# --------------------------------------------------------------------------- #

def _reference_node(file_path):
    """リファレンスファイルのパスからリファレンスノード名を引く。

    参照が壊れている・アンロード直後などで引けないことがあるので、
    落ちずに空文字を返す（`core` 側が `unresolved` として扱う）。
    """
    try:
        return cmds.file(file_path, query=True, referenceNode=True) or ""
    except Exception:
        return ""


def _is_loaded(target):
    """ロード済みか。 **判別できないものは「ロード済み」に倒す**（安全側）。

    削除は取り返しがつかないので、迷ったら消さない。
    """
    try:
        return bool(cmds.referenceQuery(target, isLoaded=True))
    except Exception:
        return True


def _parent_node(reference_node):
    """親のリファレンスノード。 引けなければ None（＝独立した参照として扱う）。"""
    if not reference_node:
        return None
    try:
        parent = cmds.referenceQuery(reference_node,
                                     referenceNode=True, parent=True)
    except Exception:
        return None
    if isinstance(parent, (list, tuple)):
        parent = parent[0] if parent else None
    return parent or None


def collect_entries():
    """シーン中のリファレンスを `core.ReferenceEntry` の一覧にする。

    `cmds.file(q=True, reference=True)` はアンロード中のものも含めて返す。
    """
    paths = cmds.file(query=True, reference=True) or []
    entries = []
    for file_path in paths:
        node = _reference_node(file_path)
        entries.append(core.ReferenceEntry(
            reference_node=node,
            file_path=file_path,
            is_loaded=_is_loaded(node or file_path),
            parent_node=_parent_node(node)))
    return entries


# --------------------------------------------------------------------------- #
# 実処理
# --------------------------------------------------------------------------- #

def remove_unloaded(confirm=True):
    """アンロード中のリファレンスを削除して `(削除できた数, 失敗した数)` を返す。

    UI が無くても呼べる（元の `unloadReferenceDelete.py` と同じ使い方）。
    """
    plan = core.plan_removal(collect_entries())

    if not plan.targets:
        message = "アンロード中のリファレンスはありません。"
        if plan.unresolved:
            message += ("\n\n（リファレンスノードが引けないものが %d 件あります）"
                        % (len(plan.unresolved),))
        _notify(message)
        return (0, 0)

    if confirm:
        answer = cmds.confirmDialog(
            title=TITLE, message=core.format_plan(plan),
            button=["Delete", "Cancel"], defaultButton="Cancel",
            cancelButton="Cancel", dismissString="Cancel")
        if answer != "Delete":
            print("[%s] cancelled" % (_PACKAGE,))
            return (0, 0)

    removed, failed = [], []
    for entry in plan.targets:
        try:
            # ファイルパスではなくリファレンスノードを渡す。 同じファイルを
            # 複数回参照していると、パスは `{1}` 付きで曖昧になるため
            cmds.file(removeReference=True, referenceNode=entry.reference_node)
            removed.append(entry)
        except Exception as exc:
            failed.append((entry, "%s: %s" % (type(exc).__name__, exc)))

    report = core.format_result(removed, failed)
    print("[%s]\n%s" % (_PACKAGE, report))
    _notify(report)
    return (len(removed), len(failed))


def _notify(message):
    """ダイアログを出す。 UI の無い環境（バッチ）では print だけで済ませる。"""
    try:
        cmds.confirmDialog(title=TITLE, message=message, button=["OK"])
    except Exception:
        print("[%s] %s" % (_PACKAGE, message))


# --------------------------------------------------------------------------- #
# コールバック
# --------------------------------------------------------------------------- #

def _on_refresh(*_args):
    _refresh()


def _on_remove(*_args):
    remove_unloaded(confirm=_confirm_enabled())
    _refresh()


def _on_confirm_changed(value, *_args):
    cmds.optionVar(intValue=(_OPTVAR_CONFIRM, 1 if value else 0))


def _confirm_enabled():
    """チェックボックスの状態。 ウィンドウが無ければ既定（確認する）。"""
    control = _CTRL.get("confirm")
    if control and cmds.checkBox(control, exists=True):
        return bool(cmds.checkBox(control, query=True, value=True))
    return _stored_confirm_pref()


def _stored_confirm_pref():
    if cmds.optionVar(exists=_OPTVAR_CONFIRM):
        return bool(cmds.optionVar(query=_OPTVAR_CONFIRM))
    return True


# --------------------------------------------------------------------------- #
# ウィンドウ
# --------------------------------------------------------------------------- #

def _refresh():
    """一覧を取り直して表示する。 削除対象だけでなく全件出す。

    「消えないもの」も理由付きで見せないと、消えなかったのが不具合なのか
    仕様なのか区別できない。
    """
    control = _CTRL.get("list")
    if not control or not cmds.textScrollList(control, exists=True):
        return

    del _ROWS[:]
    cmds.textScrollList(control, edit=True, removeAll=True)

    entries = collect_entries()
    plan = core.plan_removal(entries)
    reasons = {}
    for entry in plan.nested:
        reasons[id(entry)] = "親ごと削除"
    for entry in plan.unresolved:
        reasons[id(entry)] = "ノード不明・削除不可"

    for entry in entries:
        if entry.is_loaded:
            mark = "     "
        elif id(entry) in reasons:
            mark = "  -  "
        else:
            mark = "  x  "
        suffix = ""
        if entry.is_loaded:
            suffix = "   (loaded)"
        elif id(entry) in reasons:
            suffix = "   (%s)" % (reasons[id(entry)],)
        _ROWS.append(entry)
        cmds.textScrollList(control, edit=True,
                            append=mark + core.display_label(entry) + suffix)

    _set_status("リファレンス %d 件 / 削除対象 %d 件"
                % (len(entries), len(plan.targets)))


def _set_status(message):
    control = _CTRL.get("status")
    if control and cmds.text(control, exists=True):
        cmds.text(control, edit=True, label=message)


def _build_body():
    cmds.separator(h=4, style="none")
    cmds.text(l="アンロード中のリファレンスを削除します（x 印が削除対象）。",
              al="left")

    _CTRL["list"] = cmds.textScrollList(
        numberOfRows=12, allowMultiSelection=False, h=200,
        ann="シーン中のリファレンス一覧。 x 印が削除対象")

    _CTRL["confirm"] = cmds.checkBox(
        l="削除前に確認する（removeReference は undo できません）",
        v=_stored_confirm_pref(), cc=_on_confirm_changed)

    cmds.rowLayout(nc=2, adj=2, cw2=(110, 300), columnAlign2=("both", "both"))
    cmds.button(l="Refresh", h=28, c=_on_refresh, ann="一覧を取り直します")
    cmds.button(l="Delete Unloaded References", h=28, c=_on_remove,
                ann="アンロード中のリファレンスをすべて削除します")
    cmds.setParent("..")

    _CTRL["status"] = cmds.text(l="", al="left", fn="smallObliqueLabelFont")


def show():
    """ツールウィンドウを開く（既に開いていれば作り直す）。"""
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW)

    win = cmds.window(WINDOW,
                      title="%s  —  v%s" % (TITLE, __version__),
                      widthHeight=(470, 400),
                      minimizeButton=True, maximizeButton=False, sizeable=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=8,
                      columnAttach=("both", 10))

    _build_body()
    _refresh()

    # バージョン表示 +「GitHub から更新」。 全ツール共通なので消さない
    dev_tools.build_footer()

    cmds.showWindow(win)
    return win
