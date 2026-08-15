# Unload Reference Delete — 詳細仕様

## 概要
- バージョン: 0.2.0 / 対応Maya: 2024+
- カテゴリ: Reference
- 表示場所: シェルフボタン `UnldRefDel`（左クリックで起動）
- シーン中の**アンロード中（unloaded）のリファレンス**を一覧し、まとめて
  削除する。 使わなくなった参照がアンロードされたまま残り、`Reference Editor`
  が延々と伸びていくのを掃除するためのツール。

## アーキテクチャ

```
../install.py               リポジトリ直下のハブ。 全ツールをまとめて配る
unload_reference_delete/
  __init__.py               __version__ / SHELF_LABEL / show() / remove_unloaded()
  core.py                   Maya 非依存の純ロジック ← 自宅でテストできるのはここだけ
  ui.py                     cmds による UI と、cmds からの読み取り
  dev_tools.py              バージョン表示と「GitHub から更新」（全ツール共通・触らない）
```

`ui.collect_entries()` が `cmds` でシーンを読んで `core.ReferenceEntry` の並びを
作り、`core.plan_removal()` が「消すもの / 親ごと消えるもの / 消せないもの」に
仕分ける。 `ui` は返ってきた `targets` に `removeReference` を呼ぶだけ。

## 元スクリプトからの変更点

元は `unloadReferenceDelete.py`（10 行・import しただけで全削除が走る）。
標準セットに載せるにあたって次を変えた。

| | 元 | 現行 |
|---|---|---|
| 実行 | import した瞬間に無警告で全削除 | 一覧を見せ、確認ダイアログを経てから削除 |
| 削除の指定 | ファイルパス | **リファレンスノード** |
| 入れ子 | 考慮なし | 親が削除対象なら子は触らない |
| 失敗時 | 1 本落ちるとその場で止まる | 1 本ずつ捕捉して続行し、最後にまとめて報告 |

### 設計判断

- **undo チャンクではなく確認ダイアログで守る。** `cmds.file(removeReference=True)`
  は undo キューに乗らないので、`undoInfo(openChunk=...)` で囲っても戻せない。
  「囲ってあるから安全」に見えるほうが有害なので、囲わずに事前確認を必須にした
  （チェックボックスで外せるが、既定は ON）。
- **リファレンスノードで消す。** 同じファイルを複数回参照していると、Maya は
  パスの末尾に `{1}` を付けて区別する。 パスを渡す元の実装では、どちらの参照が
  消えるかがパス文字列の一致に依存してしまう。 ノード名なら一意に決まる。
- **判別できないものは「ロード済み」に倒す。** `referenceQuery` が失敗した参照は
  削除対象に入れない。 削除は取り返しがつかないので、迷ったら消さない側に倒す。
- **親子が引けなくても動く。** `referenceQuery(..., parent=True)` が失敗した場合は
  すべて独立した参照として扱う。 その場合に起きるのは「親ごと消えた子に対して
  `removeReference` を呼んで個別に失敗する」だけで、シーンは壊れない。
- **一覧にはロード済みも含めて全件出す。** 消えないものを隠すと、消えなかったのが
  不具合なのか仕様なのかユーザーに区別できない。 行頭の印で表す（`x` = 削除対象、
  `-` = 親ごと消える／消せない、空白 = ロード済み）。

## 機能詳細

### 1. 一覧（`ui._refresh`）
- `cmds.file(q=True, reference=True)` で全リファレンスを取得
- 各件について リファレンスノード / ロード状態 / 親ノード を引く
- `core.plan_removal()` の仕分け結果を行頭の印と注釈で表示
- ステータス行に「リファレンス N 件 / 削除対象 M 件」

### 2. 削除（`ui.remove_unloaded`）
- 対象が無ければその旨を出して何もしない
- 確認 ON なら、消す対象を名指しで並べたダイアログを出す（既定は Cancel）
- 1 件ずつ `cmds.file(removeReference=True, referenceNode=...)`。 例外は捕捉して
  続行し、最後に成功／失敗をまとめて報告する
- UI 無しでも呼べる: `import unload_reference_delete as u; u.remove_unloaded()`

### 3. 確認の ON/OFF
- optionVar `ntk_unload_reference_delete_confirm_before_remove` に保存

## 実装状況

### v0.2.0
- ツール固有の `install.py` を廃止し、**リポジトリ直下のハブ 1 本**に配布を
  集約した。 このツール側の変更は `SHELF_LABEL` の追加だけ（ハブがシェルフ
  ボタンを貼るときに読む）。 配布ファイルの宣言（`_REMOTE_FILES`）は無くなり、
  ハブが tree API で自動列挙する。
- **実機未確認**。 v0.1.0 の未確認項目に加え、新しい配布経路そのものも未確認。

### v0.1.0
- 既存スクリプトを標準セット（`install.py` / `core` + `ui` 分離 / `dev_tools` /
  テスト / ドキュメント）に載せた。 フォルダ名を `UnloadReferenceDelete` から
  `unload_reference_delete` へ変更（CLAUDE.md のモジュール命名規則）。
- **実機（会社の Maya）未確認。** 手元で確かめられたのは `core.py` の仕分け
  ロジックと、スタブでの `show()` の一往復まで。 特に次の 3 つは実機でしか
  確認できない:
  1. `referenceQuery(..., parent=True)` が期待どおり親ノードを返すか
  2. アンロード中の参照が `cmds.file(q=True, reference=True)` に現れるか
  3. `removeReference` をリファレンスノード指定で呼べるか
