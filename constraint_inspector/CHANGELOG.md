# Constraint Inspector — 変更履歴

現時点の仕様と確定した設計判断は `SPEC.md` を参照。 ここではバージョンごとの
経緯・試行錯誤・不具合修正の細部を記録する。 降順（新しい順）。

## 0.1.0 — 標準セットに載せ、Maya 2025 (PySide6) に対応
- 単体スクリプト `constraint_inspector.py` をパッケージ `constraint_inspector/`
  に移し、ハブ `install.py` から配布・シェルフ登録されるようにした
  （フォルダ名も `ConstrainInspector` → `constraint_inspector` に変更）
- Qt の import を `qt.py` に集約し、PySide2 / PySide6 の両方で読めるようにした
- import しただけで開く挙動をやめ、`show()` で開くようにした
- ウィンドウの objectName を `ntk_constraint_inspectorWin` にし、更新後も
  古いウィンドウを閉じられるようにした
- タイトルとステータスバーにバージョン、ステータスバーに「GitHub から更新」
- 同梱の PNG をシェルフアイコン（`icon.png`）にした
- これ以前（単体スクリプト時代）の経緯は記録が無い
