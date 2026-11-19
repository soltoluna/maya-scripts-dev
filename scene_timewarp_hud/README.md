# Scene TimeWarp HUD

## 概要
- バージョン: 0.1.0 / 対応Maya: 2024+
- シーンタイムワープが有効かどうかをビューポートの HUD に `TimeWarp: ON / OFF / None`
  で表示する。 ON のときは HUD の文字が赤くなる。

## インストール

1. GitHub の**リポジトリ直下**の `install.py` を開き、**Raw** から保存する
2. 保存した `install.py` を **Maya のビューポートにドラッグ&ドロップ**する
3. 完了ダイアログが出て、シェルフに `TWarpHUD` ボタンが追加される

Maya の再起動は不要。 **この `install.py` はリポジトリの全ツール共通**で、
1 回のドラッグで入っているツールが全部インストール／更新される。
既にハブを入れている人は、どれかのツールの「GitHub から更新」を押すだけで
このツールも入る。

## 使い方

- シェルフボタン `TWarpHUD` を**左クリックするたびに HUD の表示 / 非表示が切り替わる**。
  切り替えるとビューポート上部に `TimeWarp HUD: ON (v0.1.0)` のように出る
- HUD は右上（section 2）に出る
  - `None`: シーンタイムワープが無い
  - `ON`（赤）/ `OFF`: シーンタイムワープの有効 / 無効
- 非表示にすると HUD の文字色を元に戻す

スクリプトから使う場合（単体スクリプト時代と同じ）:

```python
import scene_timewarp_hud
scene_timewarp_hud.install()     # 表示
scene_timewarp_hud.uninstall()   # 消す
```

## 更新

ウィンドウが無いので、**シェルフボタンを右クリック > Update All Tools from GitHub**
か、他のツールの「GitHub から更新」ボタンで更新する（全ツールがまとめて更新される）。
ドラッグ&ドロップし直しても更新されない。

更新が届いたかは、シェルフボタンで切り替えたときに出るバージョン番号で確かめる。

## 制約・既知の問題

- HUD の表示状態はシーンや Maya の再起動をまたいで残らない（起動のたびにボタンで出す）
- HUD を出したまま Maya を終了すると、赤に変えた HUD の文字色が設定に残ることがある
  （次に HUD を出して消せば、そのとき読んだ色に戻る）
- 更新には GitHub への HTTPS 接続が必要。 塞がれている場合は
  **ルートの README「GitHub に接続できないとき」**のオフライン手順で入れられる

## 開発者向け

- 仕様と設計判断: `SPEC.md`
- 変更履歴: `CHANGELOG.md`
- テスト（Maya 不要）: `cd tests && python -m unittest discover -v`
