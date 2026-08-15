# リポジトリ直下のテスト — ハブ `install.py`

ツールごとのテストは各ツールの `tests/` にある。 ここは**全ツールに共通する
配布の仕組み**（リポジトリ直下の `install.py`）だけを検査する。

```powershell
cd D:\maya\scripts\dev\tests
python -m unittest discover -v
```

Maya のインストールは不要。

## なぜ分けてあるか

ツール側のテスト（`<ツール>/tests/`）は `_bootstrap.py` で **`maya` スタブを
`sys.modules` に注入する**。 その状態で `install.py` を読み込むと、末尾の

```python
try:
    from maya import cmds
    install()          # ← 本当に GitHub へ取りに行き、実機に書き込む
except ImportError:
    pass
```

が通ってしまう。 **ここでは `_bootstrap` を import しない**ので、`maya` が
無い素の Python として読み込まれ、自動実行は `ImportError` で握り潰される。

## 何を担保しているか

- **探索規則** — `<名前>/<名前>/__init__.py` の形だけをツールと見なし、
  雛形（`docs/templates/`）や標準セット化前の単体スクリプトは拾わない
- **実リポジトリとの突き合わせ** — `check_tools.py` が見るツールを
  ハブも漏れなく拾えるか。 パッケージ内の全ファイルが配布対象の拡張子
  （`_ALLOWED_SUFFIXES`）に収まっているか。 **これが `_REMOTE_FILES` 検査の
  後継**で、自宅では絶対に再現しない配布漏れを止める最後の砦
- `NAMESPACE` がハブと全パッケージで一致しているか（ずれると更新後に
  古いウィンドウが残る）
- シェルフラベルの導出（宣言があればそれ、無ければモジュール名から生成）

## 何を担保していないか

**実際に GitHub から落として Maya に書き込む経路は一切通していない。**
tree API のレスポンス形、raw URL の組み立て、`cmds.shelfButton` の挙動は
実機でしか確かめられない。
