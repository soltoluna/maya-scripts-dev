# -*- coding: utf-8 -*-
"""Tool Template — `maya.cmds` による UI。

ここは「値を集める → `core` に渡す → 結果を `cmds` に流す」だけに保つ。
判定や計算を書き始めたら `core.py` に移す（自宅に Maya が無いので、
`core` に無い処理は実機に持っていくまで一度も実行されない）。

雛形のサンプル（`_on_apply`）は、最初の機能を実装したら消す。
"""

from __future__ import annotations

from maya import cmds

from . import __version__, core, dev_tools


# ウィンドウ名は `<モジュール名>Win` 固定。 install.py の
# `_close_existing_window()` がこの規則で古いウィンドウを探すので、
# 定数で書かず自分の位置から導く（リネームしてもずれない）
_PACKAGE = __package__ or __name__.rsplit(".", 1)[0]
WINDOW = _PACKAGE + "Win"

# optionVar / scriptJob / ウィンドウ名は Maya 全体で 1 つのフラットな
# 名前空間を共有する。 **モジュール名を接頭辞にして必ず名前空間を切る**
# （社内で他の人のツールと同居するので、`lastTarget` のような汎用名は
# 後勝ちで静かに上書きされる）。 定数で書かず `_PACKAGE` から導けば、
# リネームしても自動で追従し、付け忘れも起きない
_OPTVAR_BASE_NAME = "%s_base_name" % _PACKAGE

_CTRL = {}   # コントロール名の控え。 show() のたびに作り直す


# --------------------------------------------------------------------------- #
# コールバック
# --------------------------------------------------------------------------- #

def _on_apply(*_args):
    """雛形のサンプル。 選択ノードに連番の名前を付ける。"""
    base = cmds.textFieldGrp(_CTRL["base"], q=True, text=True).strip()
    selection = cmds.ls(selection=True, long=True) or []

    if not selection:
        cmds.warning("[%s] ノードが選択されていません。" % (_PACKAGE,))
        return

    # 名前の生成は core（Maya 非依存）に任せる。 不正な入力はここで弾かれる
    try:
        names = core.make_numbered_names(base, len(selection))
    except ValueError as exc:
        cmds.confirmDialog(title="Tool Template",
                           message="名前が不正です:\n%s" % (exc,),
                           button=["OK"])
        return

    cmds.optionVar(sv=(_OPTVAR_BASE_NAME, base))

    # シーンを変更する処理は 1 操作 = 1 undo にまとめる。
    # openChunk したら例外が出ても必ず closeChunk する（閉じ忘れると
    # 以降の undo が壊れ、Maya を再起動するまで直らない）
    cmds.undoInfo(openChunk=True, chunkName="%s apply" % (_PACKAGE,))
    try:
        for node, new_name in zip(selection, names):
            cmds.rename(node, new_name)
    finally:
        cmds.undoInfo(closeChunk=True)

    print("[%s] renamed %d node(s)" % (_PACKAGE, len(selection)))


# --------------------------------------------------------------------------- #
# ウィンドウ
# --------------------------------------------------------------------------- #

def _build_body():
    """ツール本体の UI。 **ここを自分の機能に差し替える。**"""
    default_base = "node"
    if cmds.optionVar(exists=_OPTVAR_BASE_NAME):
        default_base = cmds.optionVar(q=_OPTVAR_BASE_NAME) or default_base

    cmds.separator(h=4, style="none")
    _CTRL["base"] = cmds.textFieldGrp(label="Base Name", text=default_base,
                                      cw2=(80, 200), adj=2)
    cmds.button(l="Apply", h=28, c=_on_apply)


def show():
    """ツールウィンドウを開く（既に開いていれば作り直す）。"""
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW)

    win = cmds.window(WINDOW,
                      title="Tool Template  —  v%s" % (__version__,),
                      widthHeight=(360, 200),
                      minimizeButton=True, maximizeButton=False, sizeable=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=8,
                      columnAttach=("both", 10))

    _build_body()

    # バージョン表示 + 「GitHub から更新」。 全ツール共通なので消さない
    dev_tools.build_footer()

    cmds.showWindow(win)
    return win
