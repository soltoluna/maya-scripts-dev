# -*- coding: utf-8 -*-
"""Scene TimeWarp HUD (Maya 2024)

シーンタイムワープノードが存在する場合、ビューポートHUDに
現在の ON / OFF 状態を表示する。ON時はHUDの文字色を赤に、
OFF時は既定色に切り替える。

usage:
    import scene_timewarp_hud
    scene_timewarp_hud.install()    # HUD表示を有効化
    scene_timewarp_hud.uninstall()  # HUD削除、色設定を元に戻す
"""
from maya import cmds

HUD_NAME = 'HUD_sceneTimeWarp'

# HUDカラーインデックス (displayColor "headsUpDisplayValues" が使用する
# userDefined カラーパレットのインデックス。1〜24 の範囲)
HUD_COLOR_INDEX = 'headsUpDisplayValues'
COLOR_INDEX_ON = 14   # 赤
COLOR_INDEX_OFF = 16  # 明るいグレー(デフォルト相当)

_color_script_job = None
_original_color_index = None  # uninstall時に復元するため保存


def _get_scene_timewarp():
    """time1 に接続されたシーンタイムワープノードを返す(なければ None)"""
    if not cmds.attributeQuery('timewarpIn_Raw', node='time1', exists=True):
        return None
    conns = cmds.listConnections(
        'time1.timewarpIn_Raw', source=True, destination=False) or []
    return conns[0] if conns else None


def _is_timewarp_enabled():
    """シーンタイムワープが存在し、かつ有効かどうか"""
    if not _get_scene_timewarp():
        return False
    return bool(cmds.getAttr('time1.enableTimewarp'))


def _status_text():
    """HUDに表示する文字列を生成"""
    if not _get_scene_timewarp():
        return 'None'
    return 'ON' if _is_timewarp_enabled() else 'OFF'


# ---------------------------------------------------------------------------
# HUD
# ---------------------------------------------------------------------------
def _install_hud():
    block = cmds.headsUpDisplay(nextFreeBlock=2)
    cmds.headsUpDisplay(
        HUD_NAME,
        section=2,
        block=block,
        blockSize='small',
        label='TimeWarp:',
        labelFontSize='small',
        dataFontSize='small',
        command=_status_text,
        attachToRefresh=True,
    )


def _uninstall_hud():
    if cmds.headsUpDisplay(HUD_NAME, exists=True):
        cmds.headsUpDisplay(HUD_NAME, remove=True)


# ---------------------------------------------------------------------------
# HUD text color
# ---------------------------------------------------------------------------
def _apply_color():
    """タイムワープの状態に応じてHUD文字色を切り替える"""
    index = COLOR_INDEX_ON if _is_timewarp_enabled() else COLOR_INDEX_OFF
    cmds.displayColor(HUD_COLOR_INDEX, index, dormant=True)


def _refresh_color(*_args):
    _apply_color()


def _install_color():
    global _color_script_job, _original_color_index
    _original_color_index = cmds.displayColor(HUD_COLOR_INDEX, query=True, dormant=True)
    _apply_color()
    _color_script_job = cmds.scriptJob(
        attributeChange=['time1.enableTimewarp', _refresh_color],
        protected=True,
    )


def _uninstall_color():
    global _color_script_job, _original_color_index
    if _color_script_job is not None and cmds.scriptJob(exists=_color_script_job):
        cmds.scriptJob(kill=_color_script_job, force=True)
    _color_script_job = None
    if _original_color_index is not None:
        cmds.displayColor(HUD_COLOR_INDEX, _original_color_index, dormant=True)
        _original_color_index = None


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


if __name__ == '__main__':
    install()
