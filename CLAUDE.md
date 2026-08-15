# Maya Tool Dev

Maya 用 Python ツールを**自宅（Maya 無し）で開発し、GitHub 経由で会社の Maya に配る**
ためのワークスペース。 Blender 側（`D:\BlenderData\addons\dev`）と同じ運用に揃えてある。

## 環境

- **会社では Maya 2024 と 2025 の両方を使っている**（今後さらに上がる可能性あり）。
  したがって**両対応が既定**で、判断は常に**下限の 2024 に合わせる**。
  - コードは **Python 3.10 で動く構文**に留める（2024=3.10 / 2025=3.11。`match` 文は
    3.10 から使えるが、下限が下がったときに壊れるので避ける。型注釈を書くなら
    `from __future__ import annotations` を付ける）
  - **UI は `maya.cmds` で書く。PySide は使わない。** 2024 は PySide2、2025 は
    PySide6 で **import 名から互換が無く**、両対応するには shim が要る。
    `cmds` なら 1 本のコードがそのまま両方で動く
  - Qt がどうしても必要になったら、その時点でユーザーに相談する（対応方針を
    決めずに `PySide2` を書き始めると 2025 で落ちる）
  - バージョン早見: Maya 2022=3.7 / 2023=3.9 / 2024=3.10 / 2025・2026=3.11
  - **対応バージョンを変えるときは 3 箇所を直す**: この行 /
    `tools/check_tools.py` の `TARGET_PYTHON` / 雛形の `tests/test_tool_meta.py` の
    `_TARGET_PYTHON`
- 開発機（自宅）: **Maya は使えない。** テストは Maya スタブで回す（`tests/`）
  - `C:\Program Files\Autodesk\Maya2025` は**存在するがライセンスが切れている**。
    `mayapy.exe` が起動することを確認しても**使えないので提案しないこと**
    （2026-08-15 に一度この勘違いをした）。 実機確認は会社の Maya のみ
- 実機（会社）: Maya 2024 / 2025。 **実機確認はここでしかできない**
- ワークスペース: `D:\maya\scripts\dev`
- GitHub: `soltoluna/maya-scripts-dev`（**public モノレポ**。 ツール 1 本 = フォルダ 1 つ）
  - **public にしてある理由**: `install.py` の更新機能は GitHub API と raw を
    **匿名で**叩く。 private にすると会社 PC 側にトークンを置く仕組みが要る。
    社外に出せないコードはここに入れない

### Blender ワークスペースとの決定的な違い

| | Blender 側 | ここ（Maya） |
|---|---|---|
| 実機 | 開発機に入っている | **会社にしかない** |
| 反映 | リポジトリを直読み → Reload Addon | **push しないと実機に届かない** |
| 検証 | テスト + 手元で実機確認 | テストのみ。 **実機確認は必ず持ち越し** |

**「テストが通った」は「動く」ではない。** 報告では必ず実機未確認と明記し、
`docs/PROGRESS.md` の「次回」に実機確認を残す。

## フォルダ構造

### 既存スクリプト（標準セット化前のフォルダ）

`ConstrainInspector` / `PlayblastTool` / `toon_outline_manager` などは、
標準セット化する前から使っている**単体スクリプト**。 `install.py` もテストも
無く、`tools/check_tools.py` の対象外（**`install.py` か同名パッケージがある
フォルダだけ**を検査する。 名前で判別しないのは接頭辞を付けない方針のため）。 手を入れるときは
`/scaffold` で標準セットに載せてから触る。

**そのうち 3 本（`ConstrainInspector` / `MgearToDWpicker` / `toon_outline_manager`）は
`PySide2` + `shiboken2` を直接 import しており、Maya 2025 では import に失敗する。**
標準セット化のついでに直すなら、`cmds` で書き直すか PySide2/6 の両対応 shim を
入れることになる（どちらを選ぶかはユーザーに確認する）。

### 新規ツール

ツール 1 本が 1 フォルダ。 **中に同名のパッケージを持つ**（`install.py` をパッケージの
外に置くため。 `install.py` は単体で GitHub から fetch されて `exec` されるので、
パッケージの一部にしてはいけない）。

```
<tool_name>/
├── install.py            エンドユーザーが唯一触るファイル（Maya にドラッグ）
├── <tool_name>/          実装本体（Maya の userScriptDir にこの形で配置される）
│   ├── __init__.py       __version__ と show() をここに置く
│   ├── core.py           Maya 非依存の純ロジック（← 自宅でテストできるのはここ）
│   ├── ui.py             cmds による UI。 ロジックを持たない
│   └── dev_tools.py      バージョン表示 / GitHub から更新 / リロード
├── SPEC.md               現行仕様・設計判断 + `## 実装状況`
├── README.md             ユーザー目線の機能・使い方・制約
├── CHANGELOG.md          版ごとの経緯
└── tests/                Maya 非依存の回帰テスト
    ├── _bootstrap.py     maya.cmds スタブを sys.modules に注入
    └── test_tool_meta.py メタ情報・_REMOTE_FILES・後片付けの検査
```

**`core.py` と `ui.py` を分ける理由**: 自宅に Maya が無いので、`cmds` を呼ぶコードは
実行して確かめられない。 判定・変換・命名規則といった**純ロジックを `core.py` に寄せる
ほど、自宅で検証できる範囲が広がる**。 `ui.py` は「値を集めて `core` に渡し、結果を
`cmds` に流すだけ」に保つ。

## 配布と反映（ホットアップデート）

**実装の全パターンと踏んだ落とし穴は [`docs/MAYA_HOT_UPDATE_PATTERNS.md`](docs/MAYA_HOT_UPDATE_PATTERNS.md) に
まとまっている。 ここに書いていない挙動で迷ったら再調査せずそちらを読む。**

- 初回のみ: `install.py` を Maya のビューポートにドラッグ&ドロップ
- 以降: ツール UI の「GitHub から更新」ボタン、またはシェルフボタン**右クリック** > Update
  - **同じファイルを 2 回ドラッグしても何も起きない**（`onMayaDroppedPythonFile` は
    セッション内で 1 度しか呼ばれない）。 ドラッグはアップデート手段にならない
- 更新は必ず **commit SHA を含む immutable URL** から取る。 `raw.githubusercontent.com` の
  CDN は**クエリ文字列を無視してパスだけで**キャッシュするので、`?_=<時刻>` は効かない
- 実機に届く条件は **push 済みであること**。 ローカルのコミットは実機から見えない

## ルール

### 個人の接頭辞は付けない。名前空間はモジュール名で切る

**`ntk_` のような個人の接頭辞は使わない**（2026-08-15 決定）。 社内配布する
可能性が高く、配る相手から見て個人名の名前空間は意味を持たないため。
ツール名はそのまま機能を表す名前にする（`playblast_tool` / `constraint_inspector`）。

ただし **Maya のグローバル名前空間が浅い**という問題は消えない。 シェルフ・
optionVar・scriptJob・ウィンドウ名はすべてフラットな 1 つの空間を共有していて、
`lastTarget` のような汎用名は**後勝ちで静かに上書きされる**。 社内で他人のツールと
同居するなら、むしろ危険は増える。

そこで **名前空間は「モジュール名そのもの」で切る**。 別に接頭辞を決めない。

| 対象 | 形 | 例 |
|---|---|---|
| パッケージ / モジュール名 | 機能を表す snake_case | `rename_helper` |
| ウィンドウ名 | `<モジュール名>Win` | `rename_helperWin` |
| optionVar キー | `<モジュール名>_<key>` | `rename_helper_last_target` |
| scriptJob / callback の識別子 | `<モジュール名>_<用途>` | `rename_helper_selection_job` |
| シェルフボタン label | 10 文字以内の短縮名 | `RenameHlp` |

- **接頭辞は手で書かず `__package__` から導く**（雛形の `ui.py` / `dev_tools.py` が
  そうしてある）。 定数で持つとリネームでずれ、付け忘れも起きる:
  ```python
  _PACKAGE = __package__ or __name__.rsplit(".", 1)[0]
  WINDOW = _PACKAGE + "Win"
  _OPTVAR_LAST_TARGET = "%s_last_target" % _PACKAGE
  ```
- **ウィンドウ名は `モジュール名 + "Win"` から動かさない。** `install.py` の
  `_close_existing_window()` がこの規則で既存ウィンドウを探すので、外すと更新時に
  古いウィンドウが残る（`check_tools.py` が検査する）
- **モジュール名 = フォルダ名 = `install.py` の `_MODULE` = `_REPO_SUBDIR`。**
  この 4 つがずれるのが最頻の事故（`check_tools.py` が検査する）
- `check_tools.py` は optionVar のリテラルキーがモジュール名で始まるかを検査する

**チーム共通の接頭辞（`ars_` などスタジオ名）が必要になったら方針を変える。**
その場合は上の表の「モジュール名」を「`<接頭辞>_<モジュール名>`」に読み替え、
`check_tools.py` の optionVar 検査を 1 行直せば済む。 現時点では不要と判断。

### バージョン

- **コードに変更を加えたら、軽微な修正でも必ずバージョンを上げる。** ホットアップデートの
  完了ダイアログが `previous → current` を出すので、据え置くと**ユーザーも自分も
  「更新が届いたのか」を判別できなくなる**（これは Blender 側より切実。 実機が手元に無く、
  目視で確かめられるのがこのダイアログしかない）
  - パッチ (x.y.**Z**): バグ修正・エラーハンドリング・リファクタ
  - マイナー (x.**Y**.0): 機能追加、ウィンドウ名 / optionVar キーの変更
  - メジャー (**X**.0.0): 作り直し・大規模な仕様変更
  - ドキュメントのみの修正では上げない
- **情報源は `<tool>/<tool>/__init__.py` の `__version__` ただ 1 つ。**
  同期先は **3 箇所**: `SPEC.md` の「概要」 / ツールの `README.md` の「概要」 /
  ルート `README.md` の一覧表
- バージョンを上げたら `SPEC.md` の `## 実装状況` に `### vX.Y.Z` を、`CHANGELOG.md` に
  `## X.Y.Z — <一行見出し>` を追記する（新しいものを上に積む）

### モジュールを増やしたら `_REMOTE_FILES` に追記する

`install.py` はダウンロード対象を `_REMOTE_FILES` のハードコード一覧で管理している。
**新しい `.py` を足して追記を忘れると、実機で `ModuleNotFoundError` になる**
（`docs/MAYA_HOT_UPDATE_PATTERNS.md` §1-10）。 自宅では絶対に再現しないので、
`python tools\check_tools.py <ツール名>` が突き合わせる。 **コミット前に必ず走らせる。**

### その他

- `__pycache__/` はコミットしない
- `install.py` は**パッケージに依存しない自己完結**を保つ。 パッケージが壊れていても
  Update が走らないと復旧できなくなる

## ツール標準セット

すべてのツールは以下を揃える。 定義と設計意図は [`docs/TOOL_SCAFFOLD.md`](docs/TOOL_SCAFFOLD.md)、
雛形の実体は [`docs/templates/tool_template/`](docs/templates/) にある。

| 資産 | 中身 |
|---|---|
| `install.py` | ドラッグ&ドロップ インストーラ。 SHA 固定 URL・原子的書き込み・`__pycache__` 掃除・シェルフ登録 |
| `dev_tools.py` | UI 内のバージョン表示と「GitHub から更新」ボタン |
| `SPEC.md` | 現行仕様・アーキテクチャ・設計判断 + `## 実装状況` |
| `README.md` | ユーザー目線の機能・使い方・制約・**インストール手順** |
| `CHANGELOG.md` | 版ごとの経緯・試行錯誤・不具合修正の細部 |
| `tests/` | Maya 非依存の回帰テスト。 `python -m unittest discover -v` |

### 指示が無くても自動で行うこと

- **新規ツールを作るときは `/new-tool <名前>` の手順に従い、標準セットを最初から
  全部作る。** 「まずコードだけ書いて後で `.md` を足す」はしない
- **既存ツールに着手するとき（コードを触る前）に `python tools\check_tools.py <ツール名>`
  を走らせ、標準セットが欠けていたら `/scaffold <ツール名>` で先に補完する。**
  補完してよいかだけ一言確認し、拒否されなければ進める。 既にあるものは上書きしない
- **コードを変更したら、そのツールの `tests/` を走らせてから報告する。**
  併せて `check_tools.py` で **0 error** を確認する
- **実機確認ができていないことを報告に必ず明記する。** 自宅に Maya は無いので、
  ここで「動作確認しました」とは書けない。 実機で確かめてほしい手順を添える

### 検査コマンド

```powershell
python tools\check_tools.py                    # 全ツール（ERROR があれば終了コード 1）
python tools\check_tools.py rename_helper      # 指定したツールだけ
python tools\check_tools.py --list-missing     # 標準セットの充足状況だけ

cd rename_helper\tests
python -m unittest discover -v                 # Maya 不要
```

## レビュー

- `/review [ファイル or ツールフォルダ名]` で 6 観点（機能性 / UI・UX / パフォーマンス /
  コード品質 / 安定性 / 配布・拡張性）の並列レビューを実行する
- 引数を省略すると、そのセッションで変更した `.py` のみを対象にする
- 観点別のサブエージェント定義は `.claude/agents/` にある
- サブエージェントは読み取り専用（Read/Grep/Glob）なので、レビューがコードを書き換えることはない

## セッション管理

- 作業ログは `docs/PROGRESS.md` に要点のみ記録（会話ログそのものは書かない）
- セッション終了時は `/wrapup`、開始時は `/resume`
- PROGRESS.md は直近 10 件を目安に、古いものは `docs/archive/YYYY-MM.md` へ移動
- ツール固有の詳細な進捗・既知の課題は各ツールの `SPEC.md` の `## 実装状況` に書く
- **実機確認の待ち行列を PROGRESS.md で管理する。** 「実装済み・実機未確認」の版が
  溜まるのがこのワークスペースの常態なので、どの版がどこまで確認済みかを残す

# Environment

OS: Windows 11
Shell: PowerShell 7 (pwsh)

Workspace root:
D:\maya\scripts\dev

This is a Maya Python tool development workspace. Maya itself is NOT installed on
this machine — never suggest launching Maya, `mayapy`, or running anything that
requires a Maya installation. Verification here is limited to the stub-based tests.

Always use Windows paths.

Correct:
D:\maya\scripts\dev\...

Never use:
- /d/...
- /mnt/d/...
- WSL paths
- Git Bash paths

Use PowerShell syntax for all commands.
