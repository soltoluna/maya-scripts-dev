# -*- coding: utf-8 -*-
"""Scene TimeWarp HUD の純ロジック（Maya 非依存）。

`maya` を import しないこと — 自宅でテストできるのはここだけ。
"""

from __future__ import annotations

# HUD の値の色（`displayColor headsUpDisplayValues` が使う userDefined
# パレットのインデックス。 1〜24）
COLOR_INDEX_ON = 14    # 赤
COLOR_INDEX_OFF = 16   # 明るいグレー（既定相当）


def status_text(has_timewarp, enabled):
    """HUD に出す文字列。 タイムワープが無ければ 'None'。"""
    if not has_timewarp:
        return "None"
    return "ON" if enabled else "OFF"


def color_index(has_timewarp, enabled):
    """HUD の値の色。 タイムワープが有効なときだけ赤にする。"""
    return COLOR_INDEX_ON if (has_timewarp and enabled) else COLOR_INDEX_OFF
