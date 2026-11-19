# -*- coding: utf-8 -*-
"""Tangent Fixer — アニメーションカーブのタンジェントを、キー同士が滑らかに
つながり、かつキーに無いオーバーシュートを作らない形に直す。

    import tangent_fixer
    tangent_fixer.show()                 # ウィンドウ
    tangent_fixer.fix()                  # 選択キー / 選択オブジェクトに即適用
    tangent_fixer.probe()                # 実機の単位・値を出す（調査用）

計算は `core.py`（Maya 非依存・Steffen 法）、カーブへの読み書きは `ui.py`。

**`__version__` がこのツールのバージョンの唯一の情報源。** ハブ `install.py` は
ここを読んで `previous → current` を出し、`SPEC.md` / `README.md` /
ルート `README.md` がこの値と一致していることを `tools/check_tools.py` が検査する。
"""

from __future__ import annotations

# 先に定義する（サブモジュールが `from . import __version__` で参照するため）
__version__ = "0.2.0"

# シェルフボタンに出す短い名前（10 文字以内）。 ハブ `install.py` がここを読んで
# ボタンを貼る。 **表示名であってツール名ではない**ので接頭辞は付けない
SHELF_LABEL = "TanFixer"

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

__all__ = ["show", "fix", "probe", "core", "ui", "dev_tools", "__version__",
           "NAMESPACE", "SHELF_LABEL"]


def show():
    """ツールウィンドウを開く。 シェルフボタンが呼ぶ入口。"""
    return ui.show()


def fix(end_mode=None, method=None):
    """選択キー（無ければ選択オブジェクトの全キー）のタンジェントを直す。

    `end_mode` は `"flat"` / `"natural"`、`method` は `"smooth"` /
    `"tangent"` / `"strict"`。 省略するとウィンドウで最後に選んだ値。
    ホットキーに登録する用。
    """
    return ui.fix(end_mode=end_mode, method=method)


def probe(try_it=False):
    """実機のタンジェント角の単位を Script Editor に出す（不具合の切り分け用）。

        tangent_fixer.probe()              # 選択中のカーブを読むだけ（安全）
        tangent_fixer.probe(try_it=True)   # 一時ノードで試して消す
    """
    return ui.probe(try_it=try_it)
