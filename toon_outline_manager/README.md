# Toon Outline Manager

## 概要
- バージョン: 0.1.0 / 対応Maya: 2024+（2024 = PySide2 / 2025 = PySide6）
- 選択したメッシュに Paint Effects のトゥーンアウトラインを付け、シーン内の
  アウトラインの線幅・表示 / 非表示・ボーダーライン・スクリーンスペース幅を
  一覧からまとめて操作する。

## インストール

1. GitHub の**リポジトリ直下**の `install.py` を開き、**Raw** から保存する
2. 保存した `install.py` を **Maya のビューポートにドラッグ&ドロップ**する
3. 完了ダイアログが出て、シェルフに Toon Outline Manager のアイコンのボタン
   （ラベル `ToonOutln`）が追加される

Maya の再起動は不要。 **この `install.py` はリポジトリの全ツール共通**で、
1 回のドラッグで入っているツールが全部インストール／更新される。
既にハブを入れている人は、どれかのツールの「GitHub から更新」を押すだけで
このツールも入る。

## 使い方

1. シェルフボタンを**左クリック**してウィンドウを開く
2. **① Add Toon Outline**: メッシュを選択して **Add Toon Outline**。
   Width 0.2 / Border line OFF / Screenspace Width OFF（max 0.5）で作られる。
   **outline_grp の中に作成** が ON なら `outline_grp` にまとめる
3. **② Line Width / Visibility**: シーン内のアウトラインが並ぶ。
   行を選んで（未選択なら全ノードが対象）線幅・BL・SS を変える。
   **表示** ボタンで個別に、**選択を非表示** でまとめて表示を切り替える

スクリプトから開く場合:

```python
import toon_outline_manager
toon_outline_manager.show()      # 従来の build_ui() も使える
```

## 更新

**ドラッグ&ドロップし直しても更新されない**（Maya は同じファイルの 2 回目の
ドロップを無視する）。 次のどちらかで更新する。

- ウィンドウ下端の **「GitHub から更新」** ボタン
- シェルフボタンを**右クリック** > **Update All Tools from GitHub**

どちらも Maya の再起動は不要。 更新後はウィンドウが自動で開き直り、タイトルと
下端のバージョン表示が新しい番号に変わる。 **変わっていなければ更新は届いていない。**

## 制約・既知の問題

- **以前の単体版 `toon_outline_manager.py` を手で置いていた場合は消す。**
  ハブと同じフォルダ（`userScriptDir`）なら新しいパッケージが優先されるが、
  別のフォルダ（`Documents\maya\scripts` など）にあると**古い単体版が読まれる
  ことがある**。 どちらが読まれているかは Script Editor で
  `import toon_outline_manager; print(toon_outline_manager.__file__)`
- PySide2 / PySide6 の差は `qt.py` で吸収している。 **自宅では PySide を
  import できないため、Qt の挙動は実機でしか確かめられない**
- 更新には GitHub への HTTPS 接続が必要。 塞がれている場合は
  **ルートの README「GitHub に接続できないとき」**のオフライン手順で入れられる

## 開発者向け

- 仕様と設計判断: `SPEC.md`
- 変更履歴: `CHANGELOG.md`
- テスト（Maya 不要）: `cd tests && python -m unittest discover -v`
