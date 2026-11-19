# -*- coding: utf-8 -*-
"""Toon Outline Manager — Paint Effects のトゥーンアウトラインを追加し、
線幅・表示・ボーダーライン・スクリーンスペース幅をまとめて操作するツール（PySide）。

もとは単体スクリプト `toon_outline_manager.py`。 2026-11 に標準セットへ載せ、
本体は `ui.py` に移した。 **従来の `toon_outline_manager.build_ui()` も
そのまま使える**（`show()` の別名）。

Qt は `qt.py` の shim 経由で import する（Maya 2024 = PySide2 / 2025 = PySide6）。
"""

from __future__ import annotations

# 先に定義する（サブモジュールが `from . import __version__` で参照するため）
__version__ = "0.1.0"

# シェルフボタンに出す短い名前（10 文字以内）
SHELF_LABEL = "ToonOutln"

# optionVar / scriptJob / ウィンドウ名の衝突回避の札。 ハブ `install.py` の
# `_NAMESPACE` と同じ値にする（`check_tools.py` が突き合わせる）
NAMESPACE = "ntk"

from . import dev_tools  # noqa: E402  バージョン表示 / GitHub から更新
from . import ui        # noqa: E402  PySide の UI

__all__ = ["show", "build_ui", "ui", "dev_tools", "__version__", "NAMESPACE",
           "SHELF_LABEL"]


def show():
    """ツールウィンドウを開く。 シェルフボタンが呼ぶ入口。"""
    return ui.show()


# 単体スクリプト時代の入口名。 手元のシェルフや習慣を壊さないために残す
build_ui = show
