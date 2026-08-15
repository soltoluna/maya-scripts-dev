# Tool Template — テスト

**開発機に Maya は無い。** ここで回るテストが、実機に持っていく前に踏める
唯一の足場になる。

## 実行方法

```powershell
cd D:\maya\scripts\dev\ntk_tool_template\tests
python -m unittest discover -v
```

Maya のインストールは不要（Python 3.9+ の標準ライブラリのみ）。

## 構成

- `_bootstrap.py` — `maya.cmds` などの最小スタブを `sys.modules` に注入し、
  ツール本体を import できるよう `sys.path` を整える（冪等・ツール非依存）。
  生成された UI・optionVar・undo チャンク・`evalDeferred` の積み残し・
  scriptJob を記録するので、後片付けの検証に使える
- `test_tool_meta.py` — ツール非依存のメタテスト。 バージョンの 3 箇所同期、
  **`install.py` の `_REMOTE_FILES` とパッケージの実体の一致**、GitHub 座標の
  一致、ウィンドウ名の規約、Python 3.9 構文、`show()` の一往復

## 担保しているもの・していないもの

**担保している**: メタ情報と配布設定の整合性、後片付けの対称性、`core.py` の
純ロジック（関数の入出力・境界条件）。

**担保していない**: 実 Maya でのノード操作・UI の見た目・`cmds` の実挙動。
スタブは「呼ばれたこと」しか知らない。 **テストが通っても実機で動く保証には
ならない。** 実機確認は別途必要。

## 新規テストの追加

1. ファイル名を `test_*.py` にする（unittest の discover 対象）
2. 冒頭で `import _bootstrap` を **必ず**行う（ツールの import より前）
3. `core.py` の関数は `from <ツール名>.core import ...` で普通に呼べる。
   **新しいロジックのテストはまずここに書く**（実機と同じ結果が出る唯一の層）
4. `cmds` を経由する処理は `_bootstrap.reset_registry()` を `setUp` で呼び、
   `_bootstrap.CALLS` / `WINDOWS` / `UNDO_CHUNKS` を見て検証する
5. `cmds.ls(selection=True)` の戻り値は `_bootstrap.set_selection([...])` で差し替える

## install.py をテストから実行しないこと

スタブ環境では `from maya import cmds` が通ってしまうため、`install.py` を
`exec` すると末尾の自動実行が**本当に GitHub へ取りに行く**。 静的解析
（`ast`）だけで検査する。
