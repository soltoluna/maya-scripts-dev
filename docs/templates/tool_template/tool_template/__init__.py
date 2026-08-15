# -*- coding: utf-8 -*-
"""Tool Template — 新規 Maya ツールの雛形。

`/new-tool <名前>` でこのフォルダごとコピーし、以下を機械的に置換する:

    tool_template  → <新しいモジュール名>  （フォルダ名・モジュール名・ウィンドウ名）
    Tool Template  → <新しい表示名>        （ウィンドウタイトル・ドキュメント）
    ToolTmpl       → <シェルフラベル>      （下の `SHELF_LABEL`）

optionVar やウィンドウ名の識別子は `NAMESPACE` と `__package__` から組み立てて
いるので、モジュール名さえ置換すれば自動で追従する（手で直す接頭辞は無い）。

置換してリポジトリ直下に置いた時点で、**ハブ `install.py` が自動で拾う**
（`<名前>/<名前>/__init__.py` の形になっていることが唯一の条件。 配布リストを
どこかに登録する作業は無い）。

実装は `core.py`（Maya 非依存の純ロジック）と `ui.py`（cmds）に分けて書く —
自宅に Maya が無いので、`core.py` に寄せた分だけ手元で検証できる。

**`__version__` がこのツールのバージョンの唯一の情報源。** ハブ `install.py` は
ここを読んで `previous → current` を出し、`SPEC.md` / `README.md` /
ルート `README.md` がこの値と一致していることを `tools/check_tools.py` が検査する。
"""

from __future__ import annotations

# 先に定義する（サブモジュールが `from . import __version__` で参照するため）
__version__ = "0.1.0"

# シェルフボタンに出す短い名前（10 文字以内）。 ハブ `install.py` がここを読んで
# ボタンを貼る。 **表示名であってツール名ではない**ので接頭辞は付けない
SHELF_LABEL = "ToolTmpl"

# ─── 衝突回避の名前空間 ────────────────────────────────────────────────────
# Maya の optionVar / scriptJob / ウィンドウ名は**全体で 1 つのフラットな空間**を
# 共有する。 社内で他の人のツールと同居するので、これらの識別子には必ず
# `NAMESPACE + モジュール名` を付けて衝突を避ける。
#
# **ツール名（フォルダ名・モジュール名）には付けない。** 配る相手から見て
# 個人名の名前空間は意味を持たないため（CLAUDE.md「ルール」）。
# ここは「Maya の内部でぶつからないための札」であって、製品名ではない。
#
# `install.py` の `_NAMESPACE` と同じ値にする（`check_tools.py` が突き合わせる）。
NAMESPACE = "ntk"
# ──────────────────────────────────────────────────────────────────────────

from . import core      # noqa: E402  Maya 非依存の純ロジック
from . import dev_tools  # noqa: E402  バージョン表示 / GitHub から更新
from . import ui        # noqa: E402  cmds による UI

__all__ = ["show", "core", "ui", "dev_tools", "__version__", "NAMESPACE",
           "SHELF_LABEL"]


def show():
    """ツールウィンドウを開く。 シェルフボタンが呼ぶ入口。"""
    return ui.show()
