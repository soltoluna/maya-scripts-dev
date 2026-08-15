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

## 2026-08-16
- やったこと: **既存 7 本のうち `UnloadReferenceDelete` を標準セットに載せた**
  （`unload_reference_delete` へリネーム、v0.1.0）。 元は import した瞬間に無警告で
  全削除する 10 行のスクリプトだったので、一覧 → 確認ダイアログ → 削除に作り直した。
  続けて **`install.py` をリポジトリ直下のハブ 1 本に集約**（v0.2.0）。 ツールごとの
  install.py は廃止し、tree API で `<名前>/<名前>/` を自動列挙する形にした。
  併せて **PySide の方針を確定**（既存 3 本は `cmds` へ書き直さず PySide のまま両対応）。
- 現状: ルート `tests/` 17 件・ツール `tests/` 37 件パス、`check_tools.py` 0 error。
  **実機（会社の Maya）での確認は依然ゼロ。** ツールの機能も、新しい配布経路も未確認。
  標準セット適用済みは 1 本、未適用は残り 6 本。
- 次回: (1) **会社の Maya で新しい `install.py`（リポジトリ直下）のドラッグ&ドロップと
  「Update All Tools」を通す** — 配布経路を差し替えたので、旧版を入れている場合は
  **一度だけドラッグし直しが必要**（更新ボタンでは新経路に乗り換えられない）、
  (2) `unload_reference_delete` の機能確認、(3) 残り 6 本の標準セット化。
- メモ: ハブ化の決め手は **未認証 GitHub API の 60 回/時/IP が会社の NAT で全員共有**
  になること（旧方式はツール数に比例して消費）。 副産物として `_REMOTE_FILES` を
  廃止でき、§1-10 の追記忘れが原理的に起きなくなった。 判断理由と実装は
  `docs/TOOL_SCAFFOLD.md` と パターン doc §2-6 に記録済み。
  **cwd が Unity プロジェクトのままだと `/scaffold` と `/wrapup` が Blender 側・
  Unity 側のスキルを読み込む。** Maya 側で作業するときは `.claude/commands/` の
  実体を確認すること。

## 2026-08-15 (2)
- やったこと: **既存スクリプト 7 本を取り込み、名前空間の方針を 2 層に分けた**。
  **ツール名には `ntk_` を付けない**（社内配布するので、配る相手に意味のない個人名は
  載せない）が、**optionVar / scriptJob / ウィンドウ名には `ntk_<モジュール名>` を必ず
  付ける**（Maya はこの 3 つがフラットな 1 つの空間で、汎用名は他人のツールと後勝ちで
  衝突する）。 雛形を `tool_template` にリネームし、`NAMESPACE`（`__init__.py`）+
  `__package__` から識別子を組み立てる形に統一。 `check_tools.py` はフォルダ名で判別
  できなくなったので、**`install.py` か同名パッケージの有無**でツールを見分ける。
- 現状: 雛形テスト **19 件**パス、`check_tools.py` 0 error（雛形をコピーして
  `rename_helper` を作る一連の流れで検証済み）。 既存 7 本は標準セット未適用のまま。
  **実機（会社の Maya）での検証は依然ゼロ。**
- 次回: (1) 既存 7 本のうちどれから `/scaffold` で標準セットに載せるか決める、
  (2) **会社の Maya で install.py のドラッグ&ドロップと「GitHub から更新」を通す**。
- メモ: **既存 3 本（`ConstrainInspector` / `MgearToDWpicker` / `toon_outline_manager`）は
  PySide2 + shiboken2 を直接 import しており Maya 2025 で import に失敗する。**
  標準セット化のついでに直すなら `cmds` 書き換えか PySide2/6 の shim。 どちらを選ぶかは
  着手時にユーザーへ確認する。 チーム共通の接頭辞が要る場合は CLAUDE.md「ルール」の
  末尾に手順を書いてある（optionVar 検査を 1 行直すだけ）。

## 2026-08-15
- やったこと: **ワークスペースを新規作成した**（`D:\maya\scripts\dev`）。 Blender 側
  （`D:\BlenderData\addons\dev`）の運用をそのまま持ち込み、Maya 向けに置き換えた —
  雛形（`install.py` + パッケージ + テスト）、`maya.cmds` スタブ、`tools/check_tools.py`、
  スラッシュコマンド 5 本、レビュー用サブエージェント 6 本。 手元の
  `maya-hot-update-patterns.md` を `docs/MAYA_HOT_UPDATE_PATTERNS.md` として取り込み、
  その §1-10（`_REMOTE_FILES` の追記忘れ）を**テストと checker で機械検出**にした。
- 現状: 雛形のテスト 17 件パス、`check_tools.py` 0 error。 リポジトリは
  `soltoluna/maya-scripts-dev`（**public**）。 ツールはまだ 1 本も無い。
  **実機（会社の Maya）での検証はゼロ** — ドラッグ&ドロップも更新ボタンも、
  この仕組みが実機で通るかはまだ誰も見ていない。
- 次回: (1) `/new-tool` で最初のツールを 1 本作る、(2) **会社の Maya（2024 か 2025）で
  install.py のドラッグ&ドロップと「GitHub から更新」を通す**。 ここが通るまでは全部が机上。
- メモ: 対応 Maya は **2024 / 2025 の両対応**で、判断は下限の 2024（Python 3.10）に
  合わせる。 **PySide は使わない方針** — 2024=PySide2 / 2025=PySide6 で import 名から
  互換が無く、`cmds` なら 1 本のコードが両方で動くため。 public にしたのは
  `install.py` の更新機能が GitHub を**匿名で**叩く設計だから（private だと会社 PC 側に
  トークンを置く仕組みが要る）。
