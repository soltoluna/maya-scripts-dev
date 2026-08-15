新しい Maya ツールを標準セット付きで作成してください。

対象: $ARGUMENTS

標準セットの定義と設計意図は `docs/TOOL_SCAFFOLD.md` にある。**この手順を実行する前に
必ず読むこと**（ここには手順だけを書き、理由はそちらにある）。

## 1. 仕様を確定する

引数からツール名を読み取る。以下が引数から決まらない場合は、
**`AskUserQuestion` で1回だけまとめて聞く**（1問ずつ往復しない）。

| 項目 | 例 | 決め方 |
|---|---|---|
| フォルダ名 / モジュール名 | `rename_helper` | 引数の snake_case。**ツール名に `ntk_` は付けない**（社内配布するため。ただし optionVar / ウィンドウ名には付ける。CLAUDE.md「ルール」） |
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

コピーした**すべてのファイル**（パッケージ内の `.py` / 3つの `.md` /
`tests/README.md`）に対して、長いものから順に置換する。

1. `tool_template` → `<name>`
2. `Tool Template` → `<表示名>`
3. `ToolTmpl` → `<シェルフボタン ラベル>`（`__init__.py` の `SHELF_LABEL`）

**置換のほかに手で決めるものは無い。** optionVar キーもウィンドウ名も
`NAMESPACE`（`__init__.py`）と `__package__` から組み立ててあるので、モジュール名を
置換すれば `ntk_<name>Win` / `ntk_<name>_<key>` が自動で揃う。

**`NAMESPACE` は雛形の `"ntk"` のまま触らない。** ツール名には付けないが、
Maya のフラットな名前空間（optionVar / scriptJob / ウィンドウ名）で他人のツールと
衝突しないために必要（CLAUDE.md「ルール」）。

**インストーラは作らない。** 配布はリポジトリ直下のハブ `install.py` が担い、
`<name>/<name>/__init__.py` の形になっていれば**自動で配布対象になる**。
登録作業も配布リストへの追記も無い（`docs/TOOL_SCAFFOLD.md`）。

続けて手で直す箇所:

- `__init__.py` の `SHELF_LABEL` が確定した値（10 文字以内）であること
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
cd ..\..\tests
python -m unittest discover -v          # ハブが新しいツールを拾えるか
cd ..
python tools\check_tools.py <name>
```

**tests が全件通り、check_tools が `0 error` になるまで直す。**
ここで落ちるのは置換漏れかバージョン不一致がほとんど。
**ルート `tests/` も必ず走らせる** — 新しいツールがハブの探索規則から
外れていると、ここだけが落ちる（外れたまま push すると実機に何も届かない）。

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

**既にハブを入れている人は、更新ボタンを押すだけで新しいツールも降ってくる**
（ハブが tree API で列挙するので、ツールが増えても導線は変わらない）。
初めて入れる人だけ次の手順:

1. GitHub で**リポジトリ直下**の `install.py` を開き、Raw から保存する
2. 保存した `install.py` を Maya のビューポートにドラッグ&ドロップ
3. 完了ダイアログにツールごとの `previous → current` が並び、シェルフボタン
   `<ラベル>` が出れば成功
4. 左クリックでウィンドウが開き、下端に `v0.1.0` が表示されることを確認

**以降の更新はドラッグではなく**、UI の「GitHub から更新」ボタンかシェルフボタンの
右クリックで行うことも併せて伝える（同じファイルの2回目のドロップは Maya が無視する）。
