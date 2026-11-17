# -*- coding: utf-8 -*-
"""BlendShape Manager — ブレンドシェイプの作成・管理を 1 つのウィンドウで行う。

* 選択から blendShape を作る / ターゲットを足す・消す
* ターゲットの一覧（チェック + ウェイトのスライダー）と絞り込み
* 1 つずつ / 一括（検索置換・接頭辞・接尾辞）のリネーム
* インビトウィーンの追加
* 左右反転したターゲットの作成（`L_smile` → `R_smile`）

層は 3 つ: `core`（Maya 非依存・自宅でテストできる）/ `scene`（cmds と
OpenMaya でシーンを読み書き）/ `ui`（cmds のウィンドウ）。

**`__version__` がこのツールのバージョンの唯一の情報源。**
"""

from __future__ import annotations

# 先に定義する（サブモジュールが `from . import __version__` で参照するため）
__version__ = "0.1.0"

# シェルフボタンに出す短い名前（10 文字以内）。 ハブ `install.py` がここを読んで
# ボタンを貼る。 **表示名であってツール名ではない**ので接頭辞は付けない
SHELF_LABEL = "BSManager"

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
from . import scene     # noqa: E402  シーンの読み書き（cmds / OpenMaya）
from . import ui        # noqa: E402  cmds による UI

__all__ = ["show", "core", "scene", "ui", "dev_tools", "__version__", "NAMESPACE",
           "SHELF_LABEL"]


def show():
    """ツールウィンドウを開く。 シェルフボタンが呼ぶ入口。"""
    return ui.show()
