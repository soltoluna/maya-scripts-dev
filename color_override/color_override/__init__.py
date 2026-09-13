# -*- coding: utf-8 -*-
"""Color Override — 選択したオブジェクトを任意の色でフラットに塗り分ける。

同じような色のオブジェクトが重なっていると、ビューポートでは**どこまでが
どちらなのか分からず、貫通（めり込み）に気づけない**。 このツールは対象に
`surfaceShader` を一時的に割り当てて、ライティングに影響されないフラットな色で
塗り分ける。 陰影が乗らないぶん、境界が輪郭としてはっきり出る。

    Apply to Selected     選択物にカラーピッカーで指定した色を掛ける
    Random → Selected     選択物に互いに見分けやすい色を自動で振る
    Random → All Meshes   シーンの全メッシュに同上
    Restore               元のマテリアル割り当てに戻す

**元の割り当てはシーンに書き込んで保持する**（オーバーライド用シェーダーの
文字列属性）。 Python 側の辞書に持たないので、シーンを保存して開き直しても
Restore が効く。

実装は `core.py`（Maya 非依存の純ロジック）と `ui.py`（cmds）に分けてある —
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
SHELF_LABEL = "ColorOvr"

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
