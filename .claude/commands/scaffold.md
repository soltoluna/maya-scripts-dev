既存ツールに不足している標準セットを後付けしてください。

対象: $ARGUMENTS

標準セットの定義と設計意図は `docs/TOOL_SCAFFOLD.md` にある。**この手順を実行する前に
必ず読むこと**。

引数を省略された場合は、まず状況を出してから対象を確認する:

```powershell
python tools\check_tools.py --list-missing
```

## 1. 何が足りていないかを確認する

```powershell
python tools\check_tools.py <ツール名>
```

**既にあるものは作り直さない。** 足りないものだけを足す。既存の `SPEC.md` を
テンプレートで上書きするのは論外（手で書いた内容が消える）。

## 2. パッケージ構成にする

`check_tools.py` が「パッケージが無い」と言ったら、**他の何より先にここを済ませる。**
ハブ `install.py` は `<名前>/<名前>/` の形のフォルダだけを配布対象として探すので、
構成が違うと配布そのものが成立しない（＝実機に何も届かない）。

```powershell
New-Item -ItemType Directory <ツール名>\<ツール名>
git mv <ツール名>\<何か>.py <ツール名>\<ツール名>\__init__.py
```

- `__version__` を `__init__.py` の先頭付近に置く（**版数の唯一の情報源**）
- `SHELF_LABEL` を `__init__.py` に置く（10 文字以内。 ハブがシェルフボタンに使う）
- `NAMESPACE = "ntk"` を `__init__.py` に置き、**optionVar / scriptJob /
  ウィンドウ名を `<NAMESPACE>_<モジュール名>` で切り直す**。既存スクリプトは
  接頭辞なしの汎用キー（`lastDir` など）を使っていることが多く、社内配布すると
  他人のツールと後勝ちで衝突する。**キーを変えると保存済み設定は引き継がれない**
  ので、その旨を報告に書く（CLAUDE.md「ルール」）
- `show()` をパッケージ直下に置く（シェルフボタンの起動コマンドが呼ぶ入口）
- `maya` を import しない純ロジックがあれば `core.py` に切り出す。
  **自宅でテストできる範囲がここで決まる**ので、この機に寄せておく
- **バージョンを上げる**（構成変更だけなら patch）

## 3. 不足資産を作る

作る順序と作り方。それぞれ**ツール本体を読んで実際の内容を書く**こと。
テンプレートの穴埋め文言をそのまま残さない。

### install.py は作らない

配布はリポジトリ直下のハブ 1 本に集約してある。**ツールフォルダに `install.py` を
置かないこと**（置くと `check_tools.py` が ERROR を出す）。`<名前>/<名前>/__init__.py`
の形になっていれば、ハブが tree API で自動的に見つけて配る。登録作業は無い。

### dev_tools.py（バージョン表示と「GitHub から更新」）

```powershell
Copy-Item docs\templates\tool_template\tool_template\dev_tools.py <ツール名>\<ツール名>\dev_tools.py
```

- **中身は 1 文字も書き換えない**（パッケージ名は `__package__` から導き、
  GitHub 座標は全ツール共通。`check_tools.py` がハブと突き合わせる）
- `ui.py` の `show()` で、ウィンドウ下端に `dev_tools.build_footer()` を呼ぶ
- ウィンドウ名が `<NAMESPACE>_<モジュール名>Win` でなければ直す。ハブの
  `_close_existing_window()` がこの規則で古いウィンドウを閉じるため

### tests/

```powershell
Copy-Item -Recurse docs\templates\tool_template\tests <ツール名>\tests
```

`_bootstrap.py` と `test_tool_meta.py` はツール非依存なので**無編集で動く**。
`tests/README.md` のツール名とパスだけ置換する。

この時点で一度走らせる:

```powershell
cd <ツール名>\tests
python -m unittest discover -v
```

`test_tool_meta` が落ちたら、それは**既存ツールの実際の不備**である可能性が高い
（バージョン不一致、`SHELF_LABEL` の欠落、undo チャンクの閉じ忘れ）。
テストを緩めるのではなくツール側を直す。

### README.md

ツール本体を読み、`docs/templates/tool_template/README.md` の構成で書き起こす。
`## 概要`（`- バージョン: <__version__ と同じ> / 対応Maya: x+` の行を必ず入れる）/
`## インストール` / `## 使い方` / `## 更新` / `## 制約・既知の問題` / `## 開発者向け`。

**`## 更新` は省略しない。** 「ドラッグし直しても更新されない」ことを知らないと、
ユーザーは更新できずに詰まる。

### CHANGELOG.md

`docs/templates/tool_template/CHANGELOG.md` の形。**過去の履歴をでっち上げない。**
現行バージョンの見出しを1つ立て、分かる範囲で「現行仕様」とだけ書く。

### SPEC.md（無い場合のみ）

雛形の `SPEC.md` の構成に従う。既にある場合は触らない。

## 4. バージョンを上げる

**コードが変わっているならバージョンを上げる**（CLAUDE.md のルール）。
`dev_tools.py` の追加は UI に1行増えるのでマイナー。`.md` だけを足した場合は上げない。

上げるときは3箇所を同期: `SPEC.md` の「概要」 / `README.md` の「概要」 /
ルート `README.md` の一覧表。さらに `SPEC.md` の `## 実装状況` と
`CHANGELOG.md` にも追記する。

## 5. 検証する

```powershell
cd <ツール名>\tests
python -m unittest discover -v
cd ..\..\tests
python -m unittest discover -v          # ハブがこのツールを拾えるか
cd ..
python tools\check_tools.py <ツール名>
```

**tests が全件通り、check_tools が `0 error` になるまで直す。**
**ルート `tests/` も必ず走らせる** — ハブの探索規則から外れていると
ここだけが落ちる（外れたまま push すると実機に何も届かない）。

## 6. コミットして push する

```
chore(<ツール名>): 標準セットを整備（dev_tools/tests/CHANGELOG） (vx.y.z)
```

## 7. 報告する

足したもの・足さなかったもの（と理由）・テスト結果・バージョン変更を伝える。
テストが既存の不備を炙り出した場合は、それも明記する。

**実機確認の手順を必ず添え、実機未確認であることを明記する。** ハブを既に入れて
いる人は、**更新ボタンを押すだけで新しく標準セット化したツールも降ってくる**
（ハブが tree API で列挙するため）。初めて入れる人だけ、リポジトリ直下の
`install.py` を一度ドラッグ&ドロップする。
