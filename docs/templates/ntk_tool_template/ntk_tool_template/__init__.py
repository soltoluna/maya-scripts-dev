# -*- coding: utf-8 -*-
"""Tool Template — 新規 Maya ツールの雛形。

`/new-tool <名前>` でこのフォルダごとコピーし、以下を機械的に置換する:

    ntk_tool_template  → ntk_<新しい名前>   （フォルダ名・モジュール名・ウィンドウ名）
    tool_template      → <新しい prefix>     （optionVar キー・scriptJob 名）
    Tool Template      → <新しい表示名>      （ウィンドウタイトル・ドキュメント）

置換した時点で「Maya に入れればウィンドウが開き、GitHub から更新できる」状態に
なっている。 実装は `core.py`（Maya 非依存の純ロジック）と `ui.py`（cmds）に分けて
書く — 自宅に Maya が無いので、`core.py` に寄せた分だけ手元で検証できる。

**`__version__` がこのツールのバージョンの唯一の情報源。** `install.py` はここを
読んで `previous → current` を出し、`SPEC.md` / `README.md` / ルート `README.md`
がこの値と一致していることを `tools/check_tools.py` が検査する。
"""

from __future__ import annotations

# 先に定義する（サブモジュールが `from . import __version__` で参照するため）
__version__ = "0.1.0"

from . import core      # noqa: E402  Maya 非依存の純ロジック
from . import dev_tools  # noqa: E402  バージョン表示 / GitHub から更新
from . import ui        # noqa: E402  cmds による UI

__all__ = ["show", "core", "ui", "dev_tools", "__version__"]


def show():
    """ツールウィンドウを開く。 シェルフボタンが呼ぶ入口。"""
    return ui.show()
