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
`install.py` はパッケージ単位でファイルを配るので、構成が違うと配布そのものが
成立しない。

```powershell
New-Item -ItemType Directory <ツール名>\<ツール名>
git mv <ツール名>\<何か>.py <ツール名>\<ツール名>\__init__.py
```

- `__version__` を `__init__.py` の先頭付近に置く（**版数の唯一の情報源**）
- `show()` をパッケージ直下に置く（シェルフボタンの起動コマンドが呼ぶ入口）
- `maya` を import しない純ロジックがあれば `core.py` に切り出す。
  **自宅でテストできる範囲がここで決まる**ので、この機に寄せておく
- **バージョンを上げる**（構成変更だけなら patch）

## 3. 不足資産を作る

作る順序と作り方。それぞれ**ツール本体を読んで実際の内容を書く**こと。
テンプレートの穴埋め文言をそのまま残さない。

### install.py

```powershell
Copy-Item docs\templates\ntk_tool_template\install.py <ツール名>\install.py
```

CUSTOMIZE ブロックを埋める。**`_REMOTE_FILES` はパッケージの `.py` を実際に
列挙して書く**（`check_tools.py` が突き合わせる）。

### dev_tools.py（バージョン表示と「GitHub から更新」）

```powershell
Copy-Item docs\templates\ntk_tool_template\ntk_tool_template\dev_tools.py <ツール名>\<ツール名>\dev_tools.py
```

- CUSTOMIZE ブロックの GitHub 座標を `install.py` と**同一値**にする
- `ui.py` の `show()` で、ウィンドウ下端に `dev_tools.build_footer()` を呼ぶ
- **`_REMOTE_FILES` に `dev_tools.py` を追記する**（忘れると実機だけで落ちる）
- ウィンドウ名が `<モジュール名>Win` でなければ直す。`install.py` の
  `_close_existing_window()` がこの規則で古いウィンドウを閉じるため

`dev_tools.py` は**中身を書き換えない**（パッケージ名は `__package__` から導く）。

### tests/

```powershell
Copy-Item -Recurse docs\templates\ntk_tool_template\tests <ツール名>\tests
```

`_bootstrap.py` と `test_tool_meta.py` はツール非依存なので**無編集で動く**。
`tests/README.md` のツール名とパスだけ置換する。

この時点で一度走らせる:

```powershell
cd <ツール名>\tests
python -m unittest discover -v
```

`test_tool_meta` が落ちたら、それは**既存ツールの実際の不備**である可能性が高い
（`_REMOTE_FILES` の漏れ、バージョン不一致、undo チャンクの閉じ忘れ）。
テストを緩めるのではなくツール側を直す。

### README.md

ツール本体を読み、`docs/templates/ntk_tool_template/README.md` の構成で書き起こす。
`## 概要`（`- バージョン: <__version__ と同じ> / 対応Maya: x+` の行を必ず入れる）/
`## インストール` / `## 使い方` / `## 更新` / `## 制約・既知の問題` / `## 開発者向け`。

**`## 更新` は省略しない。** 「ドラッグし直しても更新されない」ことを知らないと、
ユーザーは更新できずに詰まる。

### CHANGELOG.md

`docs/templates/ntk_tool_template/CHANGELOG.md` の形。**過去の履歴をでっち上げない。**
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
cd ..\..
python tools\check_tools.py <ツール名>
```

**tests が全件通り、check_tools が `0 error` になるまで直す。**

## 6. コミットして push する

```
chore(<ツール名>): 標準セットを整備（install.py/dev_tools/tests/CHANGELOG） (vx.y.z)
```

## 7. 報告する

足したもの・足さなかったもの（と理由）・テスト結果・バージョン変更を伝える。
テストが既存の不備を炙り出した場合は、それも明記する。

**実機確認の手順を必ず添え、実機未確認であることを明記する。** 特に `install.py` を
新しく足した場合は、**一度だけドラッグ&ドロップし直す必要がある**（シェルフボタンの
コマンドが古いままなので）。既に入れてある版からの更新ボタンでは新しい配布経路に
乗り換えられない、という点を伝える。
