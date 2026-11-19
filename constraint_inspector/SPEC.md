# Constraint Inspector — 詳細仕様

## 概要
- バージョン: 0.1.0 / 対応Maya: 2024+
- カテゴリ: Rigging
- 表示場所: シェルフボタン `ConstInsp`（アイコン `icon.png`。 左クリックで起動）
- シーンのコンストレインを一覧し、ドリブン / ドライバー / コンストレインノードの
  選択を支援する PySide のツール。

## アーキテクチャ

```
../install.py       リポジトリ直下のハブ。 全ツールをまとめて配る（触らない）
constraint_inspector/
  __init__.py       __version__（版数の唯一の情報源）/ SHELF_LABEL / NAMESPACE / show()
  qt.py             PySide2 / PySide6 の shim。 Qt はここからだけ import する
  ui.py             データ収集 + PySide の UI（単体スクリプト時代の本体）
  dev_tools.py      「GitHub から更新」の処理（全ツール共通・触らない）
  icon.png          シェルフアイコン（ハブが置くだけで拾う）
```

### 設計判断

- **PySide のまま両対応にする**（CLAUDE.md 2026-08-16 決定）。 `cmds` へ
  書き直すと既存のレイアウトが崩れるため。 import 名の差は `qt.py` で吸収する。
  Qt6 で消えた API（`QAction` の移動・`exec_`・`QRegExp` 等）は使っておらず、
  `tests/test_qt.py` が混入を検出する
- **import しただけでは開かない。** 単体スクリプト時代はモジュール末尾で
  `show()` を呼んでいたが、シェルフボタンは import と `show()` を別に呼ぶので
  残すと 2 回開く
- **ウィンドウは objectName `ntk_constraint_inspectorWin` で探して閉じる。**
  ハブの更新は `sys.modules` を落とすので、モジュール変数のインスタンスは
  更新後に辿れない
- **バージョン表示と更新ボタンはステータスバーの右端。** `dev_tools.build_footer()`
  は `cmds` の UI なので Qt のウィンドウには使えず、同じ働きを Qt で作った
- **`core.py` はまだ無い。** データ収集（`get_constraints_in_hierarchy` など）は
  `cmds` 依存で `ui.py` に同居している。 純ロジックを切り出すのは今後の課題

## 機能詳細

### 1. スキャン
- Root（空欄ならシーン全体）以下の 9 種類のコンストレインを集める
  （parent / point / orient / scale / aim / geometry / normal / tangent / poleVector）

### 2. 一覧とフィルター
- ノード名・種類で絞り込み。 列のクリックでコンストレイン / ドリブン / ドライバーを選択

### 3. 詳細パネル
- ドリブンの選択・追加選択、ドライバーごとの選択とウェイト表示

## 実装状況

### v0.1.0
- 単体スクリプト `ConstrainInspector/constraint_inspector.py` を標準セットに載せた。
  機能は単体版のまま。 変更は Qt の shim 化・import 時の自動起動の廃止・
  タイトルとステータスバーへのバージョン表示・「GitHub から更新」ボタン・
  シェルフアイコン。
- 2026-11-19: **Maya 2024 / 2025 の両方で実機確認済み**（ユーザー報告: 「GitHub から更新」での
  シェルフ登録・アイコン、ウィンドウの起動。 2025 = PySide6 でも開いた）。
