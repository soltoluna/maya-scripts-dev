# Maya Tool Dev

Maya 用 Python ツールを**自宅（Maya 無し）で開発し、GitHub 経由で会社の Maya に配る**
ためのワークスペース。 Blender 側（`D:\BlenderData\addons\dev`）と同じ運用に揃えてある。

## 環境

- **会社では Maya 2024 と 2025 の両方を使っている**（今後さらに上がる可能性あり）。
  したがって**両対応が既定**で、判断は常に**下限の 2024 に合わせる**。
  - コードは **Python 3.10 で動く構文**に留める（2024=3.10 / 2025=3.11。`match` 文は
    3.10 から使えるが、下限が下がったときに壊れるので避ける。型注釈を書くなら
    `from __future__ import annotations` を付ける）
  - **新規ツールの UI は `maya.cmds` で書く。** 2024 は PySide2、2025 は
    PySide6 で **import 名から互換が無く**、両対応するには shim が要る。
    `cmds` なら 1 本のコードがそのまま両方で動く
  - **既に PySide で書かれているツールは PySide のまま両対応にする**
    （2026-08-16 決定）。`cmds` へ書き直すとレイアウトが崩れるため。
    下の「PySide2/6 両対応 shim」に従う
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
**この 3 本は `cmds` へ書き直さず、PySide のまま両対応にする**（2026-08-16 決定。
既にあるレイアウトを崩したくないため）。手順は下の「PySide2/6 両対応 shim」。

### PySide2/6 両対応 shim

既存の PySide ツールを Maya 2025 でも動かすときの型。**パッケージ内に
`qt.py` を 1 枚置き、他のモジュールはそこからだけ import する**
（各ファイルに try/except を散らすと、必ずどこかが漏れて 2025 で落ちる）。

```python
# <pkg>/qt.py
try:                                              # Maya 2025+
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:                               # Maya 2024
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance
```

Qt5 → Qt6 で実際にぶつかる差（import 名だけ直しても落ちる箇所）:

- **`QAction` / `QActionGroup` が `QtWidgets` から `QtGui` へ移った。**
  `QtWidgets.QAction` は 2025 で `AttributeError`
- `exec_()` → `exec()`（Qt5 側にも `exec()` があるので `exec()` に寄せる）
- `QRegExp` 廃止 → `QtCore.QRegularExpression`
- `QDesktopWidget` 廃止 → `QtGui.QGuiApplication.primaryScreen().geometry()`
- `.setMargin()` 廃止 → `.setContentsMargins()`
- enum は Qt6 でスコープ必須の箇所がある（`Qt.AlignLeft` → `Qt.AlignmentFlag.AlignLeft`）。
  Qt5 でも後者が通るので、迷ったら長い方で書く

**自宅では PySide が無いので import すら確かめられない。** テストは
`tests/_bootstrap.py` のスタブに PySide を足すか、Qt を触るコードを
`core.py` 側へ寄せて回避する。実機確認は 2024 と 2025 の**両方**で行う
（片方だけ通しても意味が無いのがこの作業の目的）。

### 新規ツール

ツール 1 本が 1 フォルダ。 **中に同名のパッケージを持つ**。 この「同名 2 段」が
**ハブ `install.py` の探索条件そのもの**で、崩すと丸ごと配布されない。

```
install.py                リポジトリ直下。 全ツール共通のハブ（ツール側には置かない）
<tool_name>/
├── <tool_name>/          実装本体（Maya の userScriptDir にこの形で配置される）
│   ├── __init__.py       __version__ / SHELF_LABEL / NAMESPACE / show()
│   ├── core.py           Maya 非依存の純ロジック（← 自宅でテストできるのはここ）
│   ├── ui.py             cmds による UI。 ロジックを持たない
│   └── dev_tools.py      バージョン表示 / GitHub から更新（無改変でコピー）
├── SPEC.md               現行仕様・設計判断 + `## 実装状況`
├── README.md             ユーザー目線の機能・使い方・制約
├── CHANGELOG.md          版ごとの経緯
└── tests/                Maya 非依存の回帰テスト
    ├── _bootstrap.py     maya.cmds スタブを sys.modules に注入
    └── test_tool_meta.py メタ情報・配布形・後片付けの検査
```

**`core.py` と `ui.py` を分ける理由**: 自宅に Maya が無いので、`cmds` を呼ぶコードは
実行して確かめられない。 判定・変換・命名規則といった**純ロジックを `core.py` に寄せる
ほど、自宅で検証できる範囲が広がる**。 `ui.py` は「値を集めて `core` に渡し、結果を
`cmds` に流すだけ」に保つ。

## 配布と反映（ホットアップデート）

**実装の全パターンと踏んだ落とし穴は [`docs/MAYA_HOT_UPDATE_PATTERNS.md`](docs/MAYA_HOT_UPDATE_PATTERNS.md) に
まとまっている。 ここに書いていない挙動で迷ったら再調査せずそちらを読む。**

**`install.py` はリポジトリ直下に 1 本だけ**（2026-08-16 にツールごとから集約）。
GitHub の tree API で `<名前>/<名前>/` の形のフォルダを探し、**全ツールをまとめて**
配る。 新しいツールを足しても**どこにも登録しなくていい**。

- 初回のみ: リポジトリ直下の `install.py` を Maya のビューポートにドラッグ&ドロップ
  （これ 1 回で全ツールが入る）
- 以降: ツール UI の「GitHub から更新」ボタン、またはシェルフボタン**右クリック** >
  Update All Tools。 **どちらも全ツールをまとめて更新する**
  - **同じファイルを 2 回ドラッグしても何も起きない**（`onMayaDroppedPythonFile` は
    セッション内で 1 度しか呼ばれない）。 ドラッグはアップデート手段にならない
- **Script Editor から `exec(open(...))` で走らせるなら `encoding="utf-8"` を必ず付ける。**
  日本語版 Windows の `open()` は cp932 で読むので、UTF-8 + 日本語コメントの
  `install.py` が `UnicodeDecodeError` で落ちる。 `# -*- coding: utf-8 -*-` は
  `open()` には効かない。 **自宅では絶対に再現しない**ので、`exec` を案内する
  文面を書くときに思い出すこと（`docs/MAYA_HOT_UPDATE_PATTERNS.md` §1-11）
- 更新は必ず **commit SHA を含む immutable URL** から取る。 `raw.githubusercontent.com` の
  CDN は**クエリ文字列を無視してパスだけで**キャッシュするので、`?_=<時刻>` は効かない
- 実機に届く条件は **push 済みであること**。 ローカルのコミットは実機から見えない
- **未認証の GitHub API は 1 時間 60 回 / IP。** 会社は NAT で全員が同じ枠を共有する。
  ハブが API を 2 回（SHA 解決 + tree）しか使わないのはこのため。 更新経路に
  API コールを足すときはこの枠を思い出すこと
- **ハブはどのパッケージにも import 依存を持たせない。** パッケージが壊れて
  import できないときに、直すための更新まで走らなくなると詰む

## ルール

### 名前空間 — ツール名には付けない、実行時識別子には必ず付ける

**この 2 つを混同しないこと。** 同じ `ntk` でも、付ける場所によって意味が違う。

| | 接頭辞 | 理由 |
|---|---|---|
| **ツール名**（フォルダ名・モジュール名・表示名・シェルフラベル） | **付けない** | 社内配布する。 配る相手から見て個人名の名前空間は意味を持たない |
| **実行時識別子**（optionVar / scriptJob / ウィンドウ名） | **必ず付ける** | Maya 全体で 1 つのフラットな空間を共有する。 他人のツールと**後勝ちで静かに衝突する** |

前者は人が読む名前、後者は Maya の内部でぶつからないための札。 札のほうは
むしろ社内配布で危険が増すので、`ntk` を積極的に使う。

| 対象 | 形 | 例 |
|---|---|---|
| パッケージ / モジュール名 | 機能を表す snake_case | `rename_helper` |
| 表示名（ウィンドウタイトル） | 自然な英語 | `Rename Helper` |
| シェルフボタン label | 10 文字以内の短縮名 | `RenameHlp` |
| ウィンドウ名 | `<NAMESPACE>_<モジュール名>Win` | `ntk_rename_helperWin` |
| optionVar キー | `<NAMESPACE>_<モジュール名>_<key>` | `ntk_rename_helper_last_target` |
| scriptJob / callback の識別子 | `<NAMESPACE>_<モジュール名>_<用途>` | `ntk_rename_helper_selection_job` |

**`NAMESPACE` は 1 箇所で定義して組み立てる。** 直書きすると付け忘れとリネーム漏れが
必ず起きるので、雛形は次の形にしてある:

```python
# <pkg>/__init__.py
NAMESPACE = "ntk"

# <pkg>/ui.py
from . import NAMESPACE
_PACKAGE = __package__ or __name__.rsplit(".", 1)[0]
_NS = "%s_%s" % (NAMESPACE, _PACKAGE)     # ntk_rename_helper
WINDOW = _NS + "Win"
_OPTVAR_LAST_TARGET = _NS + "_last_target"
```

- **ハブ `install.py` の `_NAMESPACE` は各 `__init__.py` の `NAMESPACE` と同じ値にする。**
  `_close_existing_window()` がこの規則でウィンドウを探すので、ずれると更新後に
  古いウィンドウが残る（`check_tools.py` とテストが突き合わせる）
- **モジュール名 = フォルダ名。** この 2 つがずれるとハブの探索
  （`<名前>/<名前>/`）から外れ、**そのツールだけ実機に届かなくなる**
- `check_tools.py` とテストは、optionVar のリテラルキーが `<NAMESPACE>_<モジュール名>`
  で始まるかを検査する。 `lastTarget` のような汎用名を書いた時点で止まる
- **チームで別の札に変えるなら 各 `NAMESPACE` とハブの `_NAMESPACE` だけ**
  （`ars` など）。 それ以外は組み立てなので自動で追従する

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

### モジュールを増やしても登録作業は無い（ただし拡張子には注意）

ハブは tree walk でパッケージの中身を全部配るので、**`.py` を足しても
どこにも追記しなくてよい**（`_REMOTE_FILES` は 2026-08-16 に廃止した。
`docs/MAYA_HOT_UPDATE_PATTERNS.md` §1-10 の事故は原理的に起きなくなった）。

**残っている穴は拡張子だけ。** ハブは `_ALLOWED_SUFFIXES` で対象を絞っている
ので、未登録の拡張子でリソースを足すと実機にだけ届かない。 ルートの
`tests/test_installer.py` がパッケージの実体と突き合わせて検出する。
**コミット前に `tests/` とツールの `tests/` の両方を走らせる。**

### その他

- `__pycache__/` はコミットしない
- **ツールフォルダに `install.py` を置かない**（`check_tools.py` が ERROR）。
  配布ロジックが 2 箇所になると必ず片方が古くなる
- ハブ `install.py` は**パッケージに依存しない自己完結**を保つ。 パッケージが
  壊れていても Update が走らないと復旧できなくなる

## ツール標準セット

すべてのツールは以下を揃える。 定義と設計意図は [`docs/TOOL_SCAFFOLD.md`](docs/TOOL_SCAFFOLD.md)、
雛形の実体は [`docs/templates/tool_template/`](docs/templates/) にある。

配布は**リポジトリ直下のハブ `install.py`** が担うので、ツール側には置かない。

| 資産 | 中身 |
|---|---|
| `<pkg>/__init__.py` | `__version__` / `SHELF_LABEL` / `NAMESPACE` / `show()` |
| `dev_tools.py` | UI 内のバージョン表示と「GitHub から更新」ボタン（無改変でコピー） |
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
- **コードを変更したら、そのツールの `tests/` とルートの `tests/` を走らせてから
  報告する。** 併せて `check_tools.py` で **0 error** を確認する
- **実機確認ができていないことを報告に必ず明記する。** 自宅に Maya は無いので、
  ここで「動作確認しました」とは書けない。 実機で確かめてほしい手順を添える

### 検査コマンド

```powershell
python tools\check_tools.py                    # ハブ + 全ツール（ERROR があれば終了コード 1）
python tools\check_tools.py rename_helper      # 指定したツールだけ
python tools\check_tools.py --list-missing     # 標準セットの充足状況だけ

cd rename_helper\tests
python -m unittest discover -v                 # ツール固有（Maya 不要）

cd ..\..\tests
python -m unittest discover -v                 # ハブ install.py（配布の形）
```

## レビュー

- `/review [ファイル or ツールフォルダ名]` で 6 観点（機能性 / UI・UX / パフォーマンス /
  コード品質 / 安定性 / 配布・拡張性）の並列レビューを実行する
- 引数を省略すると、そのセッションで変更した `.py` のみを対象にする
- 観点別のサブエージェント定義は `.claude/agents/` にある
- サブエージェントは読み取り専用（Read/Grep/Glob）なので、レビューがコードを書き換えることはない

## Git 運用

- **`main` で直接作業する。作業ブランチも PR も作らない。**
- **理由は「push = 配布」だから。** `install.py` のホットアップデートは
  `_GITHUB_BRANCH = "main"`（`install.py:51`）の先端 commit SHA を GitHub API で引き、
  そこから raw を取る。**ブランチに積んだものは会社の Maya に永久に届かない。**
  `/wrapup` が「push していないものは実機に届かない」と念を押しているのはこのため。
- 裏を返すと **`main` に入れた時点で会社側の「GitHub から更新」に出る**。この開発機に
  Maya は無くテストはスタブ止まりなので、**壊れた版を push すると実機で初めて分かる**。
  push 前に `tools/check_tools.py` とテストを必ず通すこと。
- **実機未確認の版が `main` に載るのはこのワークスペースの常態。**「未確認だから `main` に
  入れない」ではなく、**「未確認と分かる形で `main` に入れる」** — 追跡は下の
  「セッション管理」の実機確認の待ち行列で行う。
- **Git の運用はワークスペースごとに理由が違う。他リポジトリに合わせて揃えないこと。**

## セッション管理

- 作業ログは `docs/PROGRESS.md` に要点のみ記録（会話ログそのものは書かない）
- セッション終了時は `/wrapup`、開始時は `/resume`
- **`/wrapup` と `/resume` の実体は `~/.claude/commands/` にあり、全プロジェクト共通**
  （2026-08-19 に共通化。`.claude/commands/` の専用版は削除した。復活させないこと）。
  **この節がこのワークスペース固有の追加ルールで、`/wrapup` はここを読んで従う**
- **PROGRESS.md の「現状」には、実機（会社の Maya）で確認済みか未確認かを必ず書く。**
  この開発機に Maya は無いので、テストが通っただけの版を「動いた」と書かない
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
