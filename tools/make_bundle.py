#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""指定したツールだけをまとめた**オフライン配布バンドル**を作る。

## 何のためにあるか

普段の配布はリポジトリ直下の `install.py` 1 本で、**全ツールがまとめて入る**。
これは自分のチームに配る分には都合がよいが、

* **1 本だけ渡したい**（他のツールまで押しつけたくない）
* **相手の Maya が GitHub に届かない**（TLS 傍受プロキシ / PAC /
  セキュリティソフト。 `docs/MAYA_HOT_UPDATE_PATTERNS.md` §1-12）

のときに困る。 このスクリプトは、その 2 つを同時に解く ZIP を作る。

## 何ができるか

```
color_override_0.3.0_offline/
├── install.py               リポジトリ直下のハブをそのままコピー
├── maya_tools_offline.txt   **これがあるとハブは GitHub を見ない**
├── README.txt               受け取った人向けの手順（3 行）
└── color_override/
    ├── color_override/      実装本体
    ├── SPEC.md / README.md / CHANGELOG.md
    └── tests/
```

受け取った人は **`install.py` をビューポートにドラッグ&ドロップするだけ**。
環境変数も Script Editor も要らず、ネットワークにも触れない。

## 使い方

```powershell
python tools\make_bundle.py color_override
python tools\make_bundle.py color_override unload_reference_delete
python tools\make_bundle.py --all
python tools\make_bundle.py color_override --out D:\share   # 出力先を変える
python tools\make_bundle.py color_override --no-zip         # フォルダだけ
```

既定の出力先は `dist/`（`.gitignore` 済み。 ビルド成果物なのでコミットしない）。

## 渡したあとの更新について

**バンドルから入れたツールの「GitHub から更新」ボタンは、相手が GitHub に
届くなら動くが、そのとき全ツールが入る。** 1 本だけ渡した意図を保ちたいなら、
更新も新しい ZIP を渡す運用にすること。 相手が GitHub に届かないなら、
そもそも更新は ZIP を渡し直すしかない。
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import sys
import zipfile


HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parent

# バンドルに入れないもの（実装と読み物だけを渡す）
_SKIP_DIRS = {"__pycache__", ".git"}

# ハブが「ネットワークを使うな」と判断するためのファイル名。
# **install.py の `_OFFLINE_MARKER` と同じ値**（下で突き合わせる）
_MARKER_NAME = "maya_tools_offline.txt"

_MARKER_TEXT = """\
このファイルがあると install.py は GitHub を見ず、
隣のフォルダの中身だけをインストールします。

消さないでください。
"""

_READ_ME = """\
{title}

インストール手順
----------------
1. このフォルダの中の install.py を Maya のビューポートへ
   ドラッグ&ドロップする
2. 完了ダイアログが出て、シェルフにボタンが追加される
3. シェルフボタンを左クリックすると起動する

Maya の再起動は不要です。ネットワークにも接続しません。

同梱しているもの
----------------
{tools}

注意
----
* install.py だけを取り出すと動きません。
  このフォルダごと置いてください
* 更新版が必要になったら、配布元に新しい ZIP をもらってください
* 使い方と制約は、各ツールのフォルダの README.md にあります
"""


def _module_constants(path):
    """`check_tools.py` の読み取りを使い回す（同じ解釈にするため）。"""
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import check_tools
    return check_tools._module_constants(path)


def _tool_dirs():
    """リポジトリ直下のツールフォルダ（ハブの探索条件と同じ判定）。"""
    return sorted(p for p in REPO_ROOT.iterdir()
                  if p.is_dir()
                  and not p.name.startswith(".")
                  and (p / p.name / "__init__.py").is_file())


def _describe(tool):
    """`(バージョン, シェルフラベル)`。"""
    consts = _module_constants(tool / tool.name / "__init__.py")
    return (consts.get("__version__", "0.0.0"),
            consts.get("SHELF_LABEL", tool.name))


def _copy_tool(tool, destination):
    """ツールフォルダ 1 本をバンドルへコピーする。"""
    shutil.copytree(
        tool, destination / tool.name,
        ignore=shutil.ignore_patterns(*_SKIP_DIRS, "*.pyc"))


def _bundle_name(tools):
    """1 本なら `<名前>_<版>_offline`、複数なら `maya_tools_offline`。"""
    if len(tools) == 1:
        version, _label = _describe(tools[0])
        return "%s_%s_offline" % (tools[0].name, version)
    return "maya_tools_offline"


def _write_text(path, text):
    """Windows のメモ帳で開かれる前提なので BOM 付きで書く。"""
    path.write_text(text, encoding="utf-8-sig")


def _verify_marker_name():
    """ハブの `_OFFLINE_MARKER` とファイル名がずれていないか。

    ずれると**バンドルが GitHub を見に行ってしまい、全ツールが入る**。
    黙って壊れる種類の食い違いなので、作る前に止める。
    """
    consts = _module_constants(REPO_ROOT / "install.py")
    expected = consts.get("_OFFLINE_MARKER")
    if expected != _MARKER_NAME:
        raise SystemExit(
            "install.py の _OFFLINE_MARKER (%r) と make_bundle.py の "
            "_MARKER_NAME (%r) が食い違っている" % (expected, _MARKER_NAME))


def build(names, out_dir, make_zip=True):
    _verify_marker_name()

    available = {p.name: p for p in _tool_dirs()}
    if not names:
        raise SystemExit("ツール名を指定するか --all を付ける。 "
                         "候補: %s" % (", ".join(sorted(available)),))

    unknown = [n for n in names if n not in available]
    if unknown:
        raise SystemExit("そんなツールは無い: %s\n候補: %s"
                         % (", ".join(unknown), ", ".join(sorted(available))))

    tools = [available[n] for n in names]
    root = out_dir / _bundle_name(tools)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    shutil.copy2(REPO_ROOT / "install.py", root / "install.py")
    _write_text(root / _MARKER_NAME, _MARKER_TEXT)

    lines = []
    for tool in tools:
        _copy_tool(tool, root)
        version, label = _describe(tool)
        lines.append("* %s  v%s  （シェルフボタン: %s）"
                     % (tool.name, version, label))

    title = _bundle_title(tools)
    _write_text(root / "README.txt",
                _READ_ME.format(title=title, tools="\n".join(lines)))

    print("bundle: %s" % (root,))
    for line in lines:
        print("  " + line)

    if not make_zip:
        return root

    # `with_suffix` は使えない。 フォルダ名に `.` が入る（`..._0.3.0_offline`）ので、
    # 最後の `.0_offline` を拡張子と見なして落としてしまう
    archive = root.parent / (root.name + ".zip")
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(root.parent).as_posix())
    print("zip   : %s" % (archive,))
    return archive


def _bundle_title(tools):
    if len(tools) == 1:
        version, _label = _describe(tools[0])
        return "%s v%s — オフライン インストーラ" % (tools[0].name, version)
    return "Maya Tools — オフライン インストーラ"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="指定したツールだけのオフライン配布バンドルを作る")
    parser.add_argument("tools", nargs="*", help="ツール名（フォルダ名）")
    parser.add_argument("--all", action="store_true",
                        help="標準セット適用済みの全ツールを入れる")
    parser.add_argument("--out", default=str(REPO_ROOT / "dist"),
                        help="出力先ディレクトリ（既定: dist/）")
    parser.add_argument("--no-zip", action="store_true",
                        help="ZIP にせずフォルダのまま残す")
    args = parser.parse_args(argv)

    names = ([p.name for p in _tool_dirs()] if args.all else args.tools)
    build(names, pathlib.Path(args.out), make_zip=not args.no_zip)
    return 0


if __name__ == "__main__":
    sys.exit(main())
