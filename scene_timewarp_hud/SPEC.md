# Scene TimeWarp HUD — 詳細仕様

## 概要
- バージョン: 0.1.0 / 対応Maya: 2024+
- カテゴリ: Animation
- 表示場所: シェルフボタン `TWarpHUD`（左クリックで HUD の表示 / 非表示を切り替え）
- シーンタイムワープの状態をビューポート HUD に出す。

## アーキテクチャ

```
../install.py       リポジトリ直下のハブ。 全ツールをまとめて配る（触らない）
scene_timewarp_hud/
  __init__.py       __version__ / SHELF_LABEL / NAMESPACE / show()（切り替え）/
                    install() / uninstall()（単体版の入口）
  core.py           Maya 非依存の純ロジック（表示文字列・色の判定）
  hud.py            cmds による HUD・文字色・scriptJob の付け外し
  dev_tools.py      更新処理（全ツール共通・触らない。 UI が無いのでボタンは出さない）
```

### 設計判断

- **ウィンドウを持たないので、`show()` は HUD の切り替えにする。** シェルフボタンの
  入口は全ツール共通で `show()` なので、それに合わせた
- **バージョンは切り替え時の `inViewMessage` に出す。** 更新が届いたかを
  確かめる手段がほかに無い
- **scriptJob の番号と元の色は `__main__` に置く**（キー
  `ntk_scene_timewarp_hud_state`）。 ハブの更新は `sys.modules` からパッケージを
  落とすので、モジュール変数に置くと更新後に scriptJob を止められず色も戻せない
- **HUD 名は単体版の `HUD_sceneTimeWarp` のまま。** 変えると単体版が出した HUD を
  消せなくなる

## 機能詳細

### 1. HUD
- `time1.timewarpIn_Raw` に接続があればシーンタイムワープありとみなし、
  `time1.enableTimewarp` で ON / OFF を出す（`attachToRefresh`）

### 2. 文字色
- `displayColor headsUpDisplayValues` を ON なら 14（赤）、それ以外は 16 にする
- `time1.enableTimewarp` の変化を scriptJob で拾って色を追従させる
- 消すときは表示前の色に戻す

## 実装状況

### v0.1.0
- 単体スクリプト `TimewarpHUD/scene_timewarp_hud.py` を標準セットに載せた。
  変更はシェルフボタンでの切り替え（`show()`）・状態の置き場所（更新後も
  後片付けできるように）・判定の `core.py` への切り出し。
- **実機未確認**（2024 / 2025 とも）。
