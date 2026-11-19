# -*- coding: utf-8 -*-
"""Scene TimeWarp HUD — シーンタイムワープの ON / OFF をビューポート HUD に出す。

もとは単体スクリプト `scene_timewarp_hud.py`。 2026-11 に標準セットへ載せ、
本体は `hud.py` に移した。 **従来の `install()` / `uninstall()` はそのまま使える。**

ウィンドウを持たないツールなので、シェルフボタン（`show()`）は
**HUD の表示 / 非表示の切り替え**になる。
"""

from __future__ import annotations

# 先に定義する（サブモジュールが `from . import __version__` で参照するため）
__version__ = "0.1.0"

# シェルフボタンに出す短い名前（10 文字以内）
SHELF_LABEL = "TWarpHUD"

# optionVar / scriptJob / ウィンドウ名の衝突回避の札。 ハブ `install.py` の
# `_NAMESPACE` と同じ値にする（`check_tools.py` が突き合わせる）
NAMESPACE = "ntk"

from . import core       # noqa: E402  Maya 非依存の純ロジック
from . import dev_tools  # noqa: E402  更新処理（UI が無いのでボタンは出さない）
from . import hud        # noqa: E402  cmds による HUD

__all__ = ["show", "install", "uninstall", "core", "hud", "dev_tools",
           "__version__", "NAMESPACE", "SHELF_LABEL"]

install = hud.install
uninstall = hud.uninstall


def show():
    """HUD の表示 / 非表示を切り替える。 シェルフボタンが呼ぶ入口。

    ウィンドウが無いので、**バージョンは切り替え時のメッセージに出す**
    （更新が届いたかを確かめる手段がこれしかない）。
    """
    from maya import cmds

    shown = hud.toggle()
    message = "TimeWarp HUD: %s  (v%s)" % ("ON" if shown else "OFF",
                                           __version__)
    print("[%s] %s" % (__name__, message))
    try:
        cmds.inViewMessage(amg=message, pos="topCenter", fade=True)
    except Exception:
        pass
    return shown
