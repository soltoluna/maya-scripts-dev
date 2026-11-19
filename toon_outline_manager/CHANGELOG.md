# Toon Outline Manager — 変更履歴

現時点の仕様と確定した設計判断は `SPEC.md` を参照。 ここではバージョンごとの
経緯・試行錯誤・不具合修正の細部を記録する。 降順（新しい順）。

## 0.1.0 — 標準セットに載せ、Maya 2025 (PySide6) に対応
- 単体スクリプト `toon_outline_manager.py` をパッケージ `toon_outline_manager/`
  に移し、ハブ `install.py` から配布・シェルフ登録されるようにした
- Qt の import を `qt.py` に集約し、PySide2 / PySide6 の両方で読めるようにした
- 入口を `show()` にした（`build_ui()` は別名として残す）
- ウィンドウの objectName を `ToonOutlineManagerWindow` → `ntk_toon_outline_managerWin`
- タイトルと下端にバージョン、下端に「GitHub から更新」
- 同梱の PNG（`toon_outline_maneger.png`）をシェルフアイコン（`icon.png`）にした
- これ以前（単体スクリプト時代）の経緯は記録が無い
