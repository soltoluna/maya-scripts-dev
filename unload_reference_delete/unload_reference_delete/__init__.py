# -*- coding: utf-8 -*-
"""Unload Reference Delete — アンロード中のリファレンスをまとめて削除する。

元は `unloadReferenceDelete.py`（import しただけで全削除が走る 10 行の
スクリプト）。 標準セットに載せるにあたり、次を変えている:

* **一覧を見せてから消す。** 元のスクリプトは import した瞬間に無警告で
  削除していた。 `cmds.file(removeReference=True)` は **undo できない**ので、
  取り返しがつかない操作を確認なしに走らせない
* **リファレンスノードで消す。** 元はファイルパスを渡していたが、同じファイルを
  複数回参照していると `{1}` 付きのパスで曖昧になる。 ノード名なら一意
* 入れ子のリファレンスを考慮する（親を消すと子も一緒に消えるので、子は触らない）

判定ロジックは `core.py`（Maya 非依存）に置いてある。 開発機に Maya が無いので、
`core` に寄せた分だけ手元で検証できる。

**`__version__` がこのツールのバージョンの唯一の情報源。**
"""

from __future__ import annotations

# 先に定義する（サブモジュールが `from . import __version__` で参照するため）
__version__ = "0.1.0"

# ─── 衝突回避の名前空間 ────────────────────────────────────────────────────
# Maya の optionVar / scriptJob / ウィンドウ名は**全体で 1 つのフラットな空間**を
# 共有する。 社内で他の人のツールと同居するので、これらの識別子には必ず
# `NAMESPACE + モジュール名` を付けて衝突を避ける。
#
# **ツール名（フォルダ名・モジュール名）には付けない。** 配る相手から見て
# 個人名の名前空間は意味を持たないため（CLAUDE.md「ルール」）。
#
# `install.py` の `_NAMESPACE` と同じ値にする（`check_tools.py` が突き合わせる）。
NAMESPACE = "ntk"
# ──────────────────────────────────────────────────────────────────────────

from . import core      # noqa: E402  Maya 非依存の純ロジック
from . import dev_tools  # noqa: E402  バージョン表示 / GitHub から更新
from . import ui        # noqa: E402  cmds による UI

__all__ = ["show", "remove_unloaded", "core", "ui", "dev_tools",
           "__version__", "NAMESPACE"]


def show():
    """ツールウィンドウを開く。 シェルフボタンが呼ぶ入口。"""
    return ui.show()


def remove_unloaded(confirm=True):
    """UI を出さずに削除だけ行う（元のスクリプトと同じ使い方）。

    `confirm=False` にすると確認ダイアログも出さない。 **undo できない**ので、
    バッチから呼ぶとき以外は既定のままにしておくこと。
    """
    return ui.remove_unloaded(confirm=confirm)
