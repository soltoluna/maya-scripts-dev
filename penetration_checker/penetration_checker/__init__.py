# -*- coding: utf-8 -*-
"""Penetration Checker — メッシュ同士のめり込みを時間軸で調べ、直すべきコントローラーを選ぶ。

アニメーション作業中に「どのフレームで」「どこが刺さっているか」「どれを動かせば
直るか」をすぐ掴むためのツール。 指定したオブジェクト（グループは配下のメッシュ
全部）を総当たりで調べ、めり込んでいる頂点のスキンウェイトから**最も効いている
インフルエンスのコントローラー**（無ければジョイント）を選ぶ。 調べ方は 3 つ:
現在のフレーム / タイムスライダーの範囲をスキャン / ライブ（再生しながら）。
結果はめり込み区間の一覧とビューポートの HUD に出る。 シーンは変更しない。

    core.py   Maya 非依存の純ロジック（ボックス・内外判定・集計・探索）
    scene.py  シーンを読む層（OpenMaya / cmds。 判定は core に任せる）
    ui.py     cmds の UI

実機の戻り値が想定と違うときは `penetration_checker.diagnose()` の出力を見る。
最近接点の求め方は `penetration_checker.set_backend("fnmesh")` で遅いが確実な方へ切り替えられる。

**`__version__` がこのツールのバージョンの唯一の情報源。**
"""

from __future__ import annotations

# 先に定義する（サブモジュールが `from . import __version__` で参照するため）
__version__ = "0.2.0"

# シェルフボタンに出す短い名前（10 文字以内）。 ハブ `install.py` がここを読んで
# ボタンを貼る。 **表示名であってツール名ではない**ので接頭辞は付けない
SHELF_LABEL = "PenetChk"

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

__all__ = ["show", "diagnose", "set_backend", "core", "ui", "dev_tools", "__version__",
           "NAMESPACE", "SHELF_LABEL"]


def show():
    """ツールウィンドウを開く。 シェルフボタンが呼ぶ入口。"""
    return ui.show()


def diagnose(node=None):
    """コントローラー探索とメッシュの読み取りを Script Editor に出す（シーンは変更しない）。"""
    from . import scene
    return scene.diagnose(node)


def set_backend(name):
    """最近接点の求め方を切り替える（`"intersector"` 既定 / `"fnmesh"`）。 保存される。"""
    from . import scene
    return scene.set_backend(name)
