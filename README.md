# Maya Tools Dev

自宅で開発し、GitHub 経由で会社の Maya に配る Python ツール群。

| ツール | カテゴリ | バージョン | 対応Maya | 起動方法 | 機能概要 |
|---|---|---|---|---|---|
| [color_override](color_override/) | Utility | 0.7.0 | 2024+ | シェルフ `ColorOvr` | 選択物を任意の色でフラットに塗り分け、同系色のオブジェクトの貫通をビューポートで見分ける（Maya 2024 で確認済み / **2025 未確認**） |
| [unload_reference_delete](unload_reference_delete/) | Reference | 0.2.0 | 2024+ | シェルフ `UnldRefDel` | アンロード中のリファレンスを一覧してまとめて削除（**実機未確認**） |

**配布はリポジトリ直下の [`install.py`](install.py) 1 本**。 これを
**Maya のビューポートにドラッグ&ドロップ**すると、上の表のツールが**全部**
インストールされ、ツールごとにシェルフボタンが並ぶ。 以降は Maya を再起動せずに
**UI の「GitHub から更新」ボタン**（またはシェルフボタンの右クリック）で
全ツールをまとめて最新版に更新できる。

配布対象のファイル一覧はどこにも宣言していない。 ハブが GitHub の tree API で
`<名前>/<名前>/` の形のフォルダを探して中身を全部配るので、**モジュールを
足して配布リストへの追記を忘れる事故が起きない**
（[`docs/MAYA_HOT_UPDATE_PATTERNS.md`](docs/MAYA_HOT_UPDATE_PATTERNS.md) §1-10）。

## 1 本だけ渡す / オフラインで配る

普段の配布は `install.py` 1 本で**全ツールがまとめて入る**。 次のどちらかの
ときは、**指定したツールだけを含むオフライン用の ZIP** を作って渡す。

* 1 本だけ渡したい（他のツールまで押しつけたくない）
* 相手の Maya が GitHub に届かない（下の節）

```powershell
python tools\make_bundle.py color_override          # dist\color_override_0.3.0_offline.zip
python tools\make_bundle.py color_override unload_reference_delete
python tools\make_bundle.py --all
```

受け取った人は **ZIP を展開して、中の `install.py` をビューポートへ
ドラッグ&ドロップするだけ**。 環境変数も Script Editor も要らず、
ネットワークにも接続しない（**2026-09-16 に Maya 2024 で確認済み**）。

仕掛けは `install.py` の隣に置かれる **`maya_tools_offline.txt`** 1 枚で、
これがあるとハブは GitHub を見ずに隣のフォルダだけを配る。
出力先の `dist/` は `.gitignore` 済み（ビルド成果物なのでコミットしない）。

> **更新について**: バンドルから入れたツールの「GitHub から更新」ボタンは、
> **相手が GitHub に届くなら動くが、そのとき全ツールが入る**。 1 本だけ渡した
> 意図を保ちたいなら、更新も新しい ZIP を渡す運用にすること。

## GitHub に接続できないとき（社内プロキシ・セキュリティソフト）

社内ネットワークでは、**ブラウザは通るのに Maya の Python だけが外に出られない**
ことがある（TLS 傍受プロキシ・PAC・セキュリティソフト。 詳しい切り分けは
[`docs/MAYA_HOT_UPDATE_PATTERNS.md`](docs/MAYA_HOT_UPDATE_PATTERNS.md) §1-12）。
症状はドラッグ&ドロップ時のこれ:

```
# Error: URLError: <urlopen error A failure in the SSL library occurred (_ssl.c:997)>
```

**その場合はオフラインで入れられる。** ネットワーク側の解決を待たなくてよい。
配る側が上の `make_bundle.py` で ZIP を作って渡すのが確実（相手はドラッグ
&ドロップするだけで、確認ダイアログも出ない）。

相手が自分で何とかする場合は次の手順でも入る:

1. ブラウザで
   [リポジトリの ZIP](https://github.com/soltoluna/maya-scripts-dev/archive/refs/heads/main.zip)
   をダウンロードして展開する
2. **展開したフォルダの中にある** `install.py` を Maya のビューポートへ
   ドラッグ&ドロップする
3. 「GitHub に接続できませんでした / 隣のフォルダから入れますか？」と聞かれるので
   **オフラインで入れる** を選ぶ

**`install.py` だけを取り出すとオフラインでは入らない**（隣にツールのフォルダが
必要）。 この経路で入れた場合、**UI の「GitHub から更新」も同じ理由で失敗する**ので、
更新のたびに ZIP を取り直すことになる。 恒久対応は情シス側でどれか 1 つを通すこと。

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

# 指定したツールだけのオフライン配布 ZIP を作る（dist/ に出る）
python tools\make_bundle.py <ツール名>

# ツールのテストを走らせる（Maya 不要）
cd <ツール名>\tests
python -m unittest discover -v
```

- 運用ルールと落とし穴: [`CLAUDE.md`](CLAUDE.md)
- 標準セットの定義と設計意図: [`docs/TOOL_SCAFFOLD.md`](docs/TOOL_SCAFFOLD.md)
- **ホットアップデートの実装パターンと踏んだ落とし穴**:
  [`docs/MAYA_HOT_UPDATE_PATTERNS.md`](docs/MAYA_HOT_UPDATE_PATTERNS.md)
- 雛形: [`docs/templates/tool_template/`](docs/templates/tool_template/)
- 作業ログ: [`docs/PROGRESS.md`](docs/PROGRESS.md)
