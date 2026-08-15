# Maya Tools Dev

自宅で開発し、GitHub 経由で会社の Maya に配る Python ツール群。

| ツール | カテゴリ | バージョン | 対応Maya | 起動方法 | 機能概要 |
|---|---|---|---|---|---|
| _(まだ 1 本も無い)_ | | | | | |

各ツールは `install.py` を **Maya のビューポートにドラッグ&ドロップ**するだけで
インストールでき、以降は Maya を再起動せずに **UI の「GitHub から更新」ボタン**
（またはシェルフボタンの右クリック）で最新版に更新できる。

## 既存スクリプト（標準セット化前）

以前から使っている単体スクリプト。 **まだ `install.py` を持たない**ので、
`Documents\maya\scripts` に手で置いて Script Editor から import して使う。
`/scaffold` で順次このリポジトリの標準セットに載せていく。

| フォルダ | 中身 | Qt | 備考 |
|---|---|---|---|
| [ConstrainInspector](ConstrainInspector/) | `constraint_inspector.py` | PySide2 | **Maya 2025 では動かない**（要 PySide6 対応） |
| [MgearToDWpicker](MgearToDWpicker/) | `mgear_pkr_to_dwpicker.py` | PySide2 | mGear Anim Picker (.pkr) → DreamWall Picker (.json) 変換。**2025 不可** |
| [PlayblastTool](PlayblastTool/) | `playblast_tool.py` | — | `cmds` のみ |
| [SelectedReferenceDelete](SelectedReferenceDelete/) | `SelectedReferenceDelete.py` | — | `cmds` のみ |
| [TimewarpHUD](TimewarpHUD/) | `scene_timewarp_hud.py` | — | `cmds` のみ |
| [UnloadReferenceDelete](UnloadReferenceDelete/) | `unloadReferenceDelete.py` | — | `cmds` のみ |
| [toon_outline_manager](toon_outline_manager/) | `toon_outline_manager.py` | PySide2 | **Maya 2025 では動かない**（要 PySide6 対応） |

## 更新方法（ドキュメント）

ツールの `__version__` を上げたら、このテーブルも合わせて更新する。
`python tools\check_tools.py` が食い違いを検出する。

## 開発

**この開発機に Maya は入っていない。** ツールは Maya スタブを使ったテストで
検証し、実機確認は会社の Maya で行う。 テストが通ることと実機で動くことは別。

```powershell
# 新規ツールを標準セット付きで作る
/new-tool <名前>

# 既存ツールに不足している標準セットを後付けする
/scaffold <ツール名>

# 標準セットの充足・配布設定・バージョン同期を検査する
python tools\check_tools.py --list-missing
python tools\check_tools.py                  # ERROR があれば終了コード 1

# ツールのテストを走らせる（Maya 不要）
cd <ツール名>\tests
python -m unittest discover -v
```

- 運用ルールと落とし穴: [`CLAUDE.md`](CLAUDE.md)
- 標準セットの定義と設計意図: [`docs/TOOL_SCAFFOLD.md`](docs/TOOL_SCAFFOLD.md)
- **ホットアップデートの実装パターンと踏んだ落とし穴**:
  [`docs/MAYA_HOT_UPDATE_PATTERNS.md`](docs/MAYA_HOT_UPDATE_PATTERNS.md)
- 雛形: [`docs/templates/ntk_tool_template/`](docs/templates/ntk_tool_template/)
- 作業ログ: [`docs/PROGRESS.md`](docs/PROGRESS.md)
