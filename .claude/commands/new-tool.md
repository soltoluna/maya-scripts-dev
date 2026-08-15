新しい Maya ツールを標準セット付きで作成してください。

対象: $ARGUMENTS

標準セットの定義と設計意図は `docs/TOOL_SCAFFOLD.md` にある。**この手順を実行する前に
必ず読むこと**（ここには手順だけを書き、理由はそちらにある）。

## 1. 仕様を確定する

引数からツール名を読み取る。以下が引数から決まらない場合は、
**`AskUserQuestion` で1回だけまとめて聞く**（1問ずつ往復しない）。

| 項目 | 例 | 決め方 |
|---|---|---|
| フォルダ名 / モジュール名 | `rename_helper` | 引数の snake_case。**個人の接頭辞（`ntk_` 等）は付けない**（社内配布する方針。CLAUDE.md「ルール」） |
| 表示名 | `Rename Helper` | ウィンドウタイトルとドキュメントの見出しに使う |
| シェルフボタン ラベル | `RenameHlp` | **10 文字以内**。シェルフは幅が狭い |
| カテゴリ | `Rigging` | `Modeling` / `Rigging` / `Animation` / `Lighting` / `Pipeline` / `Utility` など |
| 対応Maya | `2024` | **CLAUDE.md「環境」の値で固定。聞かない** |
| 機能概要 | 1〜2行 | `SPEC.md` / `README.md` の「概要」とルート README に使う |

**構成は常にパッケージ**（`<name>/<name>/__init__.py`）。単一ファイル構成は
選ばない（`docs/TOOL_SCAFFOLD.md`「なぜパッケージ構成なのか」）。構成を聞く必要は無い。

## 2. 雛形をコピーする

```powershell
Copy-Item -Recurse docs\templates\tool_template <name>
Rename-Item <name>\tool_template <name>
```

## 3. 置換する

コピーした**すべてのファイル**（`install.py` / パッケージ内の `.py` / 3つの `.md` /
`tests/README.md`）に対して、長いものから順に置換する。

1. `tool_template` → `<name>`
2. `Tool Template` → `<表示名>`
3. `ToolTmpl` → `<シェルフボタン ラベル>`

**手で決める接頭辞は無い。** optionVar キーもウィンドウ名も `__package__` から
導いてあるので、モジュール名さえ置換すれば自動で追従する（CLAUDE.md「ルール」）。

続けて手で直す箇所:

- `install.py` の CUSTOMIZE ブロック — `_REPO_SUBDIR` と `_MODULE` が `<name>` に
  なっていること、`_SHELF_BUTTON_LABEL` が確定した値であること
- `<パッケージ>/dev_tools.py` の CUSTOMIZE ブロック — GitHub 座標を install.py と
  **同一値**にする（食い違うと更新が別の場所を見に行く）
- 3つの `.md` の「概要」を実際の内容にする（`- バージョン: 0.1.0` の行はそのまま）
- `SPEC.md` の `## 機能詳細` と `## 実装状況`、`README.md` の `## 使い方` を実際の
  内容にする。まだ実装が無いなら「未実装」と正直に書く
- 雛形のサンプル（`core.make_numbered_names` / `ui._on_apply`）は、実装を始めるまで
  残しておいてよい。ただし最初の機能を入れたら消す

**`ui.py` の `WINDOW` と `dev_tools.py` の `_PACKAGE` は触らない。** どちらも
`__package__` から導いているので、フォルダ名を変えれば自動で追従する。

## 4. ルート README.md の一覧表に行を足す

既存の並びに合わせて追記する。列は
`ツール / カテゴリ / バージョン / 対応Maya / 起動方法 / 機能概要`。
値は `SPEC.md` の「概要」と `__version__` に一致させる（`check_tools.py` が検査する）。

## 5. 検証する

```powershell
cd <name>\tests
python -m unittest discover -v
cd ..\..
python tools\check_tools.py <name>
```

**tests が全件通り、check_tools が `0 error` になるまで直す。**
ここで落ちるのは置換漏れかバージョン不一致がほとんど。

## 6. コミットして push する

```
feat(<name>): 新規ツールを標準セット付きで作成 (v0.1.0)
```

**push まで行う。** ローカルのコミットは実機から見えない（`install.py` は GitHub の
commit SHA を見に行くので、push していないコードは絶対に届かない）。

## 7. 報告する

作ったファイル一覧、テスト結果、`check_tools` の結果、次にやること（最初の機能の実装）
を簡潔に伝える。

**実機確認の手順を必ず添える。そして実機未確認であることを明記する。** この開発機に
Maya は無いので、ここで「動作確認しました」とは書けない。手順は次の形:

1. GitHub でこのツールの `install.py` を開き、Raw から保存する
2. 保存した `install.py` を Maya のビューポートにドラッグ&ドロップ
3. 完了ダイアログとシェルフボタン `<ラベル>` が出れば成功
4. 左クリックでウィンドウが開き、下端に `v0.1.0` が表示されることを確認

**以降の更新はドラッグではなく**、UI の「GitHub から更新」ボタンかシェルフボタンの
右クリックで行うことも併せて伝える（同じファイルの2回目のドロップは Maya が無視する）。
