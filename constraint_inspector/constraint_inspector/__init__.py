# -*- coding: utf-8 -*-
"""Constraint Inspector — シーン内のコンストレインを一覧し、ドライバー /
ドリブンの選択を支援するツール（PySide）。

もとは単体スクリプト `constraint_inspector.py`。 2026-11 に標準セットへ載せ、
本体は `ui.py` に移した。 **`import constraint_inspector; constraint_inspector.show()`
という従来の呼び方はそのまま使える**（ただし import しただけでは開かなくなった。
シェルフボタンが import と `show()` を別々に呼ぶため）。

Qt は `qt.py` の shim 経由で import する（Maya 2024 = PySide2 / 2025 = PySide6）。
"""

from __future__ import annotations

# 先に定義する（サブモジュールが `from . import __version__` で参照するため）
__version__ = "0.1.0"

# シェルフボタンに出す短い名前（10 文字以内）
SHELF_LABEL = "ConstInsp"

# optionVar / scriptJob / ウィンドウ名の衝突回避の札。 ハブ `install.py` の
# `_NAMESPACE` と同じ値にする（`check_tools.py` が突き合わせる）
NAMESPACE = "ntk"

from . import dev_tools  # noqa: E402  バージョン表示 / GitHub から更新
from . import ui        # noqa: E402  PySide の UI

__all__ = ["show", "ui", "dev_tools", "__version__", "NAMESPACE",
           "SHELF_LABEL"]


def show():
    """ツールウィンドウを開く。 シェルフボタンが呼ぶ入口。"""
    return ui.show()
