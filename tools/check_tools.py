#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ツール標準セットの充足と、配布設定・バージョンの同期をまとめて検査する。

CLAUDE.md のルールのうち、機械的に確認できるものを自動化したもの。
**Maya は不要**（`.py` を静的解析し、`.md` を読むだけ）。

このワークスペースでは実機が手元に無いので、`check_tools.py` と `tests/` を
通ったかどうかが、push 前に得られる唯一の客観的な情報になる。

## 情報源

| 情報 | 情報源 |
|---|---|
| バージョン | `<tool>/<tool>/__init__.py` の `__version__` |
| GitHub 座標 / 配布ファイル一覧 | `<tool>/install.py` の定数 |
| カテゴリ / 起動方法 / 機能概要 | `<tool>/SPEC.md` の「概要」 |

## 使い方

```powershell
python tools\check_tools.py                    # 全ツール
python tools\check_tools.py rename_helper      # 指定したツールだけ
python tools\check_tools.py --list-missing     # 不足資産の一覧だけ出す
python tools\check_tools.py --strict           # WARN も終了コード 1 にする
```

終了コード: ERROR が 1 件でもあれば 1、無ければ 0（`--strict` なら WARN も 1）。

## 検査項目

ERROR（放置すると実機で壊れるもの）
- `<tool>/<tool>/__init__.py` がある（パッケージ構成）
- `__version__` が定義され `x.y.z` 形式
- `install.py` がある / `_MODULE` がフォルダ名と一致 / `_REPO_SUBDIR` が妥当
- **`_REMOTE_FILES` がパッケージの `.py` と過不足なく一致**（追記忘れは
  実機だけで `ModuleNotFoundError` になる）
- `install.py` と `dev_tools.py` の GitHub 座標が一致
- パッケージ直下に `show()` がある（シェルフボタンの入口）
- すべての `.py` が Python 3.10 の構文で解析できる（Maya 2024 = 下限）
- `SPEC.md` がある / 「概要」のバージョンが `__version__` と一致
- `README.md` があればバージョンが一致
- ルート `README.md` の一覧表に行がある / バージョンが一致

WARN（標準セットとして揃えたいもの）
- `README.md` / `CHANGELOG.md` / `tests/` / `dev_tools.py` がある
- `CHANGELOG.md` に現行バージョンの見出しがある
- `core.py` があり、`maya` を import していない
- `ui.py` の `WINDOW` が `<モジュール名>Win`
- optionVar のキーがモジュール名で名前空間を切っている
  （接頭辞を付けない方針なので、名前空間はモジュール名そのもので切る）
- `SPEC.md` の「概要」に カテゴリ / 表示場所 の行がある
- ルート `README.md` の カテゴリ / 対応Maya が一致
- GitHub 座標がプレースホルダのまま残っていない
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import re
import sys


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# ツール名に接頭辞を付けない方針なので、フォルダ名では判別できない。
# **標準セットの目印（install.py か同名パッケージ）があるものだけ**を
# 対象にする。 目印が無いフォルダ＝標準セット化前の既存スクリプトで、
# 検査対象外（消さずに一覧だけ出す）
EXCLUDED_DIRS = {"docs", "tools"}
TARGET_PYTHON = (3, 10)         # Maya 2024（下限）。 CLAUDE.md「環境」と揃える
PLACEHOLDERS = ("YOUR_GITHUB_USERNAME", "YOUR_REPO_NAME", "OWNER", "REPO")

_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_DOC_VERSION_LINE = re.compile(r"^-\s*バージョン:\s*(\d+(?:\.\d+)*)", re.M)
_DOC_MAYA_LINE = re.compile(r"対応Maya:\s*([0-9]+)\+?", re.M)
_DOC_CATEGORY = re.compile(r"^-\s*カテゴリ:\s*(.+?)\s*$", re.M)
_DOC_LOCATION = re.compile(r"^-\s*表示場所:\s*(.+?)\s*$", re.M)
_CHANGELOG_HEADING = re.compile(r"^##\s*(\d+\.\d+\.\d+)", re.M)


class Report:
    """1 ツール分の検査結果。"""

    def __init__(self, name):
        self.name = name
        self.errors = []
        self.warns = []
        self.missing = []

    def error(self, message):
        self.errors.append(message)

    def warn(self, message):
        self.warns.append(message)

    def missing_asset(self, label):
        self.missing.append(label)
        self.warns.append("標準セットが欠けている: %s" % (label,))


# --------------------------------------------------------------------------- #
# 読み取り
# --------------------------------------------------------------------------- #

def _read(path):
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def _module_constants(path):
    """モジュール直下の `NAME = <リテラル>` を dict で返す（import しない）。"""
    source = _read(path)
    if source is None:
        return {}
    try:
        tree = ast.parse(source, str(path))
    except SyntaxError:
        return {}
    consts = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        try:
            consts[target.id] = ast.literal_eval(node.value)
        except (ValueError, TypeError, SyntaxError):
            pass
    return consts


def _function_names(path):
    source = _read(path)
    if source is None:
        return set()
    try:
        tree = ast.parse(source, str(path))
    except SyntaxError:
        return set()
    return {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}


def _imported_roots(path):
    source = _read(path)
    if source is None:
        return set()
    try:
        tree = ast.parse(source, str(path))
    except SyntaxError:
        return set()
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def _package_sources(pkg_dir):
    return sorted(p for p in pkg_dir.rglob("*.py") if "__pycache__" not in p.parts)


def _optionvar_literals(path):
    """`cmds.optionVar(...)` に直接渡されている文字列リテラルを集める。

    optionVar は Maya 全体で 1 つのフラットな名前空間なので、接頭辞の無い
    キーは他社ツールと静かに衝突する（後勝ちで値が入れ替わる）。
    定数を組み立てて渡している形は追わない — その場合は組み立て側で
    モジュール名を接頭辞にしているのが通例で、追うと誤検出が増える。
    """
    source = _read(path)
    if source is None:
        return []
    try:
        tree = ast.parse(source, str(path))
    except SyntaxError:
        return []

    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "optionVar"):
            continue
        keys = []
        for operand in list(node.args) + [kw.value for kw in node.keywords]:
            # `sv=("key", value)` の形はタプルの **先頭だけ**がキー。
            # 2 番目まで見ると値のほうを誤検出する
            if isinstance(operand, (ast.Tuple, ast.List)):
                if operand.elts:
                    keys.append(operand.elts[0])
            else:
                keys.append(operand)
        for operand in keys:
            if isinstance(operand, ast.Constant) and isinstance(operand.value, str):
                found.append(operand.value)
    return found


# --------------------------------------------------------------------------- #
# ルート README の一覧表
# --------------------------------------------------------------------------- #

def _root_readme_rows():
    """ルート `README.md` の表を `{ツール名: [セル, ...]}` で返す。"""
    text = _read(REPO_ROOT / "README.md")
    if text is None:
        return {}
    rows = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not cells:
            continue
        found = re.search(r"\]\(([A-Za-z0-9_.-]+)/\)", cells[0])
        if found:
            rows[found.group(1)] = cells
    return rows


# --------------------------------------------------------------------------- #
# 検査
# --------------------------------------------------------------------------- #

def check_tool(tool_dir, readme_rows):
    report = Report(tool_dir.name)
    name = tool_dir.name
    pkg_dir = tool_dir / name
    init_py = pkg_dir / "__init__.py"

    # --- パッケージ構成 -----------------------------------------------------
    if not init_py.is_file():
        report.error("パッケージが無い: %s/%s/__init__.py を作る" % (name, name))
        return report

    consts = _module_constants(init_py)
    version = consts.get("__version__")
    if version is None:
        report.error("__init__.py に __version__ が無い")
    elif not _SEMVER.match(str(version)):
        report.error("__version__ が x.y.z 形式でない: %r" % (version,))

    if "show" not in _function_names(init_py):
        report.error("パッケージ直下に show() が無い"
                     "（シェルフボタンの起動コマンドが呼ぶ入口）")

    # --- 実行時識別子の名前空間 ---------------------------------------------
    # optionVar / scriptJob / ウィンドウ名は Maya 全体で 1 つの空間を共有する。
    # ツール名には接頭辞を付けない方針だが、**この 3 つには必ず付ける**。
    # install.py の検査より先に解決しておく（あちらが参照する）
    namespace = consts.get("NAMESPACE")
    if namespace is None:
        report.warn("__init__.py に NAMESPACE が無い"
                    "（optionVar / scriptJob / ウィンドウ名の衝突回避に使う）")
    ns_prefix = "%s_%s" % (namespace, name) if namespace else name

    # --- Python バージョン --------------------------------------------------
    sources = _package_sources(pkg_dir)
    installer = tool_dir / "install.py"
    for path in sources + ([installer] if installer.is_file() else []):
        source = _read(path)
        if source is None:
            continue
        try:
            ast.parse(source, str(path), feature_version=TARGET_PYTHON)
        except SyntaxError as exc:
            report.error("Python %d.%d で解析できない: %s (%s)"
                         % (TARGET_PYTHON[0], TARGET_PYTHON[1],
                            path.relative_to(tool_dir).as_posix(), exc))

    # --- install.py ---------------------------------------------------------
    if not installer.is_file():
        report.error("install.py が無い（配布とホット更新の入口）")
    else:
        icons = _module_constants(installer)

        if icons.get("_MODULE") != name:
            report.error("install.py の _MODULE がフォルダ名と違う: %r != %r"
                         % (icons.get("_MODULE"), name))

        subdir = icons.get("_REPO_SUBDIR")
        if subdir not in ("", name):
            report.error("install.py の _REPO_SUBDIR はフォルダ名 %r か "
                         "空文字にする: %r" % (name, subdir))

        declared = set(icons.get("_REMOTE_FILES") or ())
        actual = {p.relative_to(pkg_dir).as_posix() for p in sources}
        for rel in sorted(actual - declared):
            report.error("install.py の _REMOTE_FILES に未登録: %s"
                         "（実機で ModuleNotFoundError になる）" % (rel,))
        for rel in sorted(declared - actual):
            report.error("install.py の _REMOTE_FILES に実在しないファイル: %s"
                         "（ダウンロードが 404 で止まる）" % (rel,))

        for key in ("_GITHUB_OWNER", "_GITHUB_REPO"):
            if str(icons.get(key, "")) in PLACEHOLDERS:
                report.warn("install.py の %s がプレースホルダのまま: %r"
                            % (key, icons.get(key)))

        if "onMayaDroppedPythonFile" not in _function_names(installer):
            report.error("install.py に onMayaDroppedPythonFile が無い"
                         "（ドラッグ&ドロップが効かない）")

        # dev_tools との突き合わせ
        dev_tools = pkg_dir / "dev_tools.py"
        if not dev_tools.is_file():
            report.missing_asset("dev_tools.py（バージョン表示と更新ボタン）")
        else:
            dcons = _module_constants(dev_tools)
            for key in ("_GITHUB_OWNER", "_GITHUB_REPO", "_GITHUB_BRANCH",
                        "_REPO_SUBDIR"):
                if icons.get(key) != dcons.get(key):
                    report.error("%s が install.py と dev_tools.py で食い違う: "
                                 "%r != %r" % (key, icons.get(key), dcons.get(key)))

        # NAMESPACE がずれると、更新時に別名のウィンドウを探して閉じ損なう
        if namespace is not None and icons.get("_NAMESPACE") != namespace:
            report.error("NAMESPACE が install.py (%r) とパッケージ (%r) で"
                         "食い違う（更新後に古いウィンドウが残る）"
                         % (icons.get("_NAMESPACE"), namespace))

    # --- レイヤ分離と命名 ---------------------------------------------------
    core_py = pkg_dir / "core.py"
    if not core_py.is_file():
        report.warn("core.py が無い（Maya 非依存の純ロジックを置く層。"
                    "自宅でテストできる範囲がここで決まる）")
    elif "maya" in _imported_roots(core_py):
        report.warn("core.py が maya を import している"
                    "（純ロジックの層は Maya 非依存に保つ）")

    for path in sources:
        for key in _optionvar_literals(path):
            if not key.startswith(ns_prefix):
                report.warn("optionVar のキーが名前空間に入っていない: %r (%s)。 "
                            "%r で始めるか `_NS` から組み立てる"
                            "（Maya 全体で共有される空間なので、社内の他ツールと"
                            "後勝ちで衝突する）"
                            % (key, path.relative_to(tool_dir).as_posix(),
                               ns_prefix + "_"))

    ui_py = pkg_dir / "ui.py"
    if ui_py.is_file():
        ucons = _module_constants(ui_py)
        window = ucons.get("WINDOW")
        source = _read(ui_py) or ""
        derived = "WINDOW = _NS" in source
        expected = ns_prefix + "Win"
        if window is not None and window != expected:
            report.warn("ui.py の WINDOW は %r にする（install.py が古い"
                        "ウィンドウを閉じられない）: %r" % (expected, window))
        elif window is None and not derived:
            report.warn("ui.py に WINDOW が見当たらない"
                        "（`WINDOW = _NS + \"Win\"` で組み立てる）")

    # --- ドキュメント -------------------------------------------------------
    spec = tool_dir / "SPEC.md"
    spec_text = _read(spec)
    if spec_text is None:
        report.error("SPEC.md が無い")
    else:
        found = _DOC_VERSION_LINE.search(spec_text)
        if not found:
            report.error("SPEC.md の「概要」に `- バージョン: x.y.z` の行が無い")
        elif version and found.group(1) != version:
            report.error("SPEC.md のバージョンが __version__ と違う: %s != %s"
                         % (found.group(1), version))
        if not _DOC_CATEGORY.search(spec_text):
            report.warn("SPEC.md の「概要」に カテゴリ の行が無い")
        if not _DOC_LOCATION.search(spec_text):
            report.warn("SPEC.md の「概要」に 表示場所 の行が無い")
        if "## 実装状況" not in spec_text:
            report.warn("SPEC.md に `## 実装状況` が無い")

    readme = tool_dir / "README.md"
    readme_text = _read(readme)
    if readme_text is None:
        report.missing_asset("README.md")
    else:
        found = _DOC_VERSION_LINE.search(readme_text)
        if not found:
            report.error("README.md の「概要」に `- バージョン: x.y.z` の行が無い")
        elif version and found.group(1) != version:
            report.error("README.md のバージョンが __version__ と違う: %s != %s"
                         % (found.group(1), version))

    changelog_text = _read(tool_dir / "CHANGELOG.md")
    if changelog_text is None:
        report.missing_asset("CHANGELOG.md")
    elif version and version not in _CHANGELOG_HEADING.findall(changelog_text):
        report.warn("CHANGELOG.md に現行バージョン %s の見出しが無い" % (version,))

    if not (tool_dir / "tests").is_dir():
        report.missing_asset("tests/（Maya 非依存の回帰テスト）")
    elif not (tool_dir / "tests" / "_bootstrap.py").is_file():
        report.warn("tests/_bootstrap.py が無い（maya スタブ）")

    # --- ルート README の一覧表 ---------------------------------------------
    row = readme_rows.get(name)
    if row is None:
        report.error("ルート README.md の一覧表に %s の行が無い" % (name,))
    else:
        if version and len(row) > 2 and row[2] != version:
            report.error("ルート README.md のバージョンが違う: %s != %s"
                         % (row[2], version))
        if spec_text:
            category = _DOC_CATEGORY.search(spec_text)
            if category and len(row) > 1 and row[1] != category.group(1):
                report.warn("ルート README.md のカテゴリが SPEC.md と違う: "
                            "%s != %s" % (row[1], category.group(1)))
            maya_spec = _DOC_MAYA_LINE.search(spec_text)
            if maya_spec and len(row) > 3 and maya_spec.group(1) not in row[3]:
                report.warn("ルート README.md の対応Maya が SPEC.md と違う: "
                            "%s != %s+" % (row[3], maya_spec.group(1)))

    return report


# --------------------------------------------------------------------------- #
# 実行
# --------------------------------------------------------------------------- #

def _candidate_dirs():
    return sorted(p for p in REPO_ROOT.iterdir()
                  if p.is_dir()
                  and not p.name.startswith(".")
                  and p.name not in EXCLUDED_DIRS)


def _has_standard_set(path):
    """標準セットを適用済みか（`install.py` か同名パッケージがあるか）。"""
    return (path / "install.py").is_file() or (path / path.name / "__init__.py").is_file()


def discover_tools():
    return [p for p in _candidate_dirs() if _has_standard_set(p)]


def discover_legacy():
    """標準セット化前の既存スクリプト（検査対象外）。"""
    return [p for p in _candidate_dirs() if not _has_standard_set(p)]


def _print_legacy(legacy):
    """標準セット化前のフォルダを一覧するだけ（検査はしない）。

    黙って無視すると存在ごと忘れられるので、毎回名前だけ出す。
    """
    if not legacy:
        return
    print("\n標準セット未適用（検査対象外・`/scaffold <名前>` で載せる）: %d 件"
          % (len(legacy),))
    for path in legacy:
        print("  - %s" % (path.name,))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tool", nargs="?", help="検査するツール名（省略で全部）")
    parser.add_argument("--list-missing", action="store_true",
                        help="標準セットの充足状況だけ出す")
    parser.add_argument("--strict", action="store_true",
                        help="WARN も終了コード 1 にする")
    args = parser.parse_args(argv)

    tools = discover_tools()
    legacy = discover_legacy()

    if args.tool:
        tools = [p for p in tools if p.name == args.tool]
        if not tools:
            if any(p.name == args.tool for p in legacy):
                print("%s は標準セット化前の既存スクリプトで、検査対象外。\n"
                      "`/scaffold %s` で標準セットに載せてから検査できる。"
                      % (args.tool, args.tool))
                return 0
            print("ツールが見つからない: %s" % (args.tool,))
            return 2

    readme_rows = _root_readme_rows()
    reports = [check_tool(p, readme_rows) for p in tools]

    if args.list_missing:
        for report in reports:
            state = ", ".join(report.missing) if report.missing else "揃っている"
            print("%-32s %s" % (report.name, state))
        _print_legacy(legacy)
        return 0

    if not reports:
        print("標準セットを適用したツールはまだ無い（`/new-tool <名前>` で作る）。")
        _print_legacy(legacy)
        return 0

    total_errors = total_warns = 0
    for report in reports:
        total_errors += len(report.errors)
        total_warns += len(report.warns)
        mark = "ERROR" if report.errors else ("warn" if report.warns else "ok")
        print("\n[%s] %s" % (mark, report.name))
        for message in report.errors:
            print("  ERROR  %s" % (message,))
        for message in report.warns:
            print("  warn   %s" % (message,))

    print("\n%d tool(s): %d error, %d warn"
          % (len(reports), total_errors, total_warns))
    _print_legacy(legacy)
    if total_errors:
        return 1
    if args.strict and total_warns:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
