# -*- coding: utf-8 -*-
"""Scene TimeWarp HUD — HUD の設置と後片付け（cmds）。

シーンタイムワープノードが存在する場合、ビューポート HUD に現在の
ON / OFF 状態を表示する。 ON 時は HUD の文字色を赤に、OFF 時は既定色に
切り替える。

usage:
    import scene_timewarp_hud
    scene_timewarp_hud.show()       # 表示 / 非表示を切り替える（シェルフボタン）
    scene_timewarp_hud.install()    # HUD 表示を有効化
    scene_timewarp_hud.uninstall()  # HUD 削除、色設定を元に戻す
"""

from __future__ import annotations

import sys

from maya import cmds

from . import NAMESPACE, core

_PACKAGE = __package__ or __name__.rsplit(".", 1)[0]
_NS = "%s_%s" % (NAMESPACE, _PACKAGE)     # ntk_scene_timewarp_hud

# HUD 名は単体スクリプト時代のまま（変えると古い版が出した HUD を消せなくなる）
HUD_NAME = "HUD_sceneTimeWarp"

HUD_COLOR_INDEX = "headsUpDisplayValues"


def _state():
    """scriptJob の番号と元の色を持つ dict。

    **モジュール変数には置かない。** ハブの更新は `sys.modules` からこの
    パッケージを落とすので、モジュール変数に置くと更新後に scriptJob を
    止められず、色も戻せなくなる。 `__main__` は落とされないのでそこに置く。
    """
    main = sys.modules.get("__main__")
    store = getattr(main, "__dict__", None)
    if store is None:                      # 念のため（通常は起きない）
        store = globals()
    return store.setdefault(_NS + "_state", {"job": None, "original": None})


def _get_scene_timewarp():
    """time1 に接続されたシーンタイムワープノードを返す（なければ None）"""
    if not cmds.attributeQuery("timewarpIn_Raw", node="time1", exists=True):
        return None
    conns = cmds.listConnections(
        "time1.timewarpIn_Raw", source=True, destination=False) or []
    return conns[0] if conns else None


def _timewarp_status():
    """(存在するか, 有効か)"""
    if not _get_scene_timewarp():
        return False, False
    return True, bool(cmds.getAttr("time1.enableTimewarp"))


def _status_text():
    """HUD に表示する文字列を生成"""
    return core.status_text(*_timewarp_status())


# ---------------------------------------------------------------------------
# HUD
# ---------------------------------------------------------------------------
def is_installed():
    return bool(cmds.headsUpDisplay(HUD_NAME, exists=True))


def _install_hud():
    block = cmds.headsUpDisplay(nextFreeBlock=2)
    cmds.headsUpDisplay(
        HUD_NAME,
        section=2,
        block=block,
        blockSize="small",
        label="TimeWarp:",
        labelFontSize="small",
        dataFontSize="small",
        command=_status_text,
        attachToRefresh=True,
    )


def _uninstall_hud():
    if is_installed():
        cmds.headsUpDisplay(HUD_NAME, remove=True)


# ---------------------------------------------------------------------------
# HUD text color
# ---------------------------------------------------------------------------
def _apply_color():
    """タイムワープの状態に応じて HUD 文字色を切り替える"""
    index = core.color_index(*_timewarp_status())
    cmds.displayColor(HUD_COLOR_INDEX, index, dormant=True)


def _refresh_color(*_args):
    _apply_color()


def _install_color():
    state = _state()
    state["original"] = cmds.displayColor(HUD_COLOR_INDEX, query=True,
                                          dormant=True)
    _apply_color()
    state["job"] = cmds.scriptJob(
        attributeChange=["time1.enableTimewarp", _refresh_color],
        protected=True,
    )


def _uninstall_color():
    state = _state()
    job = state.get("job")
    if job is not None and cmds.scriptJob(exists=job):
        cmds.scriptJob(kill=job, force=True)
    state["job"] = None
    if state.get("original") is not None:
        cmds.displayColor(HUD_COLOR_INDEX, state["original"], dormant=True)
        state["original"] = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def install():
    uninstall()
    _install_hud()
    _install_color()


def uninstall():
    _uninstall_color()
    _uninstall_hud()


def toggle():
    """表示中なら消し、無ければ出す。 戻り値は切り替え後に表示中かどうか。"""
    if is_installed():
        uninstall()
        return False
    install()
    return True
