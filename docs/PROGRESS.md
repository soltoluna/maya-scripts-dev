# 開発ログ (Progress Log)

<!--
運用ルール:
- 新しいエントリは一番上に追加(降順)
- 会話の詳細やコードの中身は書かない。次回セッションが迷わず再開できる最小限の情報のみ
- フォーマット: 日付 / やったこと(3〜5行) / 現状 / 次回TODO / メモ(重要な判断理由・ハマりどころ)
- 直近10件を目安に、古いものは docs/archive/YYYY-MM.md へ移動してこのファイルを軽く保つ
- **実機(会社の Maya)での確認待ちを必ず「現状」に残す。** 開発機に Maya が無いので、
  「実装済み・実機未確認」が常態になる。どの版がどこまで確認済みかを追えるようにする
-->

## 2026-08-15
- やったこと: **ワークスペースを新規作成した**（`D:\maya\scripts\dev`）。 Blender 側
  （`D:\BlenderData\addons\dev`）の運用をそのまま持ち込み、Maya 向けに置き換えた —
  雛形（`install.py` + パッケージ + テスト）、`maya.cmds` スタブ、`tools/check_tools.py`、
  スラッシュコマンド 5 本、レビュー用サブエージェント 6 本。 手元の
  `maya-hot-update-patterns.md` を `docs/MAYA_HOT_UPDATE_PATTERNS.md` として取り込み、
  その §1-10（`_REMOTE_FILES` の追記忘れ）を**テストと checker で機械検出**にした。
- 現状: 雛形のテスト 17 件パス。 **GitHub リポジトリは未作成**（`soltoluna/maya-tools` を
  想定して定数を入れてある）。 ツールはまだ 1 本も無い。 **実機（会社の Maya）での
  ドラッグ&ドロップは未検証** — この一連の仕組みが実機で通るかはまだ誰も見ていない。
- 次回: (1) GitHub に `maya-tools` を作って push、(2) `/new-tool` で最初のツールを 1 本作る、
  (3) **会社の Maya で install.py のドラッグ&ドロップと「GitHub から更新」を通す**。
  ここが通るまでは全部が机上。
- メモ: 対応 Maya は **2023 / Python 3.9 を仮置き**（`maya-hot-update-patterns.md` の
  前提に合わせた）。 会社の Maya が違うなら CLAUDE.md の「環境」と
  `tools/check_tools.py` の `TARGET_PYTHON`、テストの `_TARGET_PYTHON` を直す。
  2025 以降は Qt が PySide6 になるが、雛形は `cmds` だけで書いてあるので影響しない。
