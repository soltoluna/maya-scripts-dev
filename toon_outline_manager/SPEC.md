# Toon Outline Manager — 詳細仕様

## 概要
- バージョン: 0.1.0 / 対応Maya: 2024+
- カテゴリ: Rendering
- 表示場所: シェルフボタン `ToonOutln`（アイコン `icon.png`。 左クリックで起動）
- Paint Effects のトゥーンアウトラインの追加と、線幅・表示・BL・SS の一括操作を
  行う PySide のツール。

## アーキテクチャ

```
../install.py       リポジトリ直下のハブ。 全ツールをまとめて配る（触らない）
toon_outline_manager/
  __init__.py       __version__（版数の唯一の情報源）/ SHELF_LABEL / NAMESPACE /
                    show()（と旧名 build_ui）
  qt.py             PySide2 / PySide6 の shim。 Qt はここからだけ import する
  ui.py             Maya 操作 + PySide の UI（単体スクリプト時代の本体）
  dev_tools.py      「GitHub から更新」の処理（全ツール共通・触らない）
  icon.png          シェルフアイコン（ハブが置くだけで拾う）
```

### 設計判断

- **PySide のまま両対応にする**（CLAUDE.md 2026-08-16 決定）。 import 名の差は
  `qt.py` で吸収する。 Qt6 で消えた API は使っておらず、`tests/test_qt.py` が
  混入を検出する。 使っていなかった `MayaQWidgetDockableMixin` の import は外した
- **ウィンドウの objectName を `ntk_toon_outline_managerWin` にした**
  （単体版は `ToonOutlineManagerWindow`）。 ハブが更新前にこの名前で閉じる。
  `show()` は旧名のウィンドウも探して閉じる（単体版を開いたまま初回更新した場合）
- **`build_ui()` を `show()` の別名として残す。** 手元のシェルフや習慣を壊さない
- **バージョン表示と更新ボタンはウィンドウ下端。** `dev_tools.build_footer()` は
  `cmds` の UI なので、同じ働きを Qt で作った
- **`core.py` はまだ無い。** Maya 操作の関数が `ui.py` に同居している。
  純ロジックを切り出すのは今後の課題

## 機能詳細

### 1. Add Toon Outline
- 選択に `assignNewPfxToon` を掛け、新しくできた pfxToon に既定値
  （lineWidth 0.2 / borderLines OFF / screenspaceWidth OFF / maxPixelWidth 0.5）を入れる
- オプションで `outline_grp` にまとめる

### 2. 一覧と一括操作
- シーン内の pfxToon を一覧し、表示 / 非表示・線幅・BL・SS を
  選択行（未選択なら全行）に適用する

## 実装状況

### v0.1.0
- 単体スクリプト `toon_outline_manager.py` を標準セットに載せた。 機能は単体版のまま。
  変更は Qt の shim 化・objectName の変更・タイトルと下端へのバージョン表示・
  「GitHub から更新」ボタン・シェルフアイコン。
- 2026-11-19: 実機で「GitHub から更新」からの配布・シェルフ登録を確認（ユーザー報告）。
  確認した版（2024 / 2025）と機能の動作確認の範囲は記録なし。 **2025（PySide6）で開けるかは要確認。**
