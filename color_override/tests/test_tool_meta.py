# -*- coding: utf-8 -*-
"""ツールのメタ情報と配布設定の回帰テスト（ツール非依存）。

このファイルはどのツールにもそのままコピーできる。 対象ツールは `_bootstrap`
がフォルダ構成から自動判別するので設定項目は無い。

## 何を担保しているか

1. `__version__` があり `x.y.z` 形式で、`SPEC.md` / `README.md` /
   `CHANGELOG.md` の表記と一致している（CLAUDE.md の同期ルールの機械化）
2. **ハブ `install.py` が拾える形になっている**（`<名前>/<名前>/__init__.py`）。
   配布リストの宣言は無く、ハブが tree API で列挙するので、`_REMOTE_FILES` の
   追記忘れ（`docs/MAYA_HOT_UPDATE_PATTERNS.md` §1-10）はもう起きない。
   代わりに「ハブの探索規則から外れていないか」をここで見る
3. ハブ `install.py` と `dev_tools.py` の GitHub 座標（owner / repo / branch）と
   `NAMESPACE` が食い違っていない
4. ウィンドウ名が `<NAMESPACE>_<モジュール名>Win`（ハブの
   `_close_existing_window` がこの規則で古いウィンドウを閉じる）
5. `core.py` が `maya` を import していない（自宅でテストできる範囲を守る）
6. すべての `.py` が **Python 3.10 の構文**で解析できる（Maya 2024 の Python。
   2025 は 3.11 なので、下限の 2024 に合わせておけば両方で動く）
7. import から `show()` までを一往復させて、ウィンドウが生成され、undo チャンクが
   閉じられ、`deleteUI` で後片付けできる

## 何を担保していないか

実 Maya でのノード操作・UI の見た目・`cmds` の実挙動。 スタブは「呼ばれたこと」
しか知らないので、**これが通っても実機で動く保証にはならない**。 実機確認は
別途必要で、報告では必ずそう書く。

なお `install.py` は**このテストから実行しない**。 スタブ環境でも
`from maya import cmds` が通ってしまい、末尾の自動実行が本当に GitHub へ
取りに行くため。 静的解析だけで検査している。 ハブ自体のロジック
（探索規則・配布対象の拡張子）はリポジトリ直下の `tests/` で検査する。
"""

from __future__ import annotations

import ast
import re
import unittest

import _bootstrap  # noqa: F401  （maya スタブの注入。 他の import より前）


_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_DOC_VERSION_LINE = re.compile(r"^-\s*バージョン:\s*(\d+(?:\.\d+)*)", re.M)
_CHANGELOG_HEADING = re.compile(r"^##\s*(\d+\.\d+\.\d+)", re.M)

_TARGET_PYTHON = (3, 10)   # Maya 2024（下限）。 CLAUDE.md「環境」と揃える


# --- 静的解析のヘルパー ------------------------------------------------------

def _parse(path):
    source = path.read_text(encoding="utf-8")
    return ast.parse(source, str(path)), source


def _module_constants(path):
    """モジュール直下の `NAME = <リテラル>` を dict で返す（import せずに読む）。"""
    tree, _ = _parse(path)
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
            pass   # 式で組み立てている定数は対象外
    return consts


def _imported_roots(path):
    """そのファイルが import しているトップレベルのモジュール名の集合。"""
    tree, _ = _parse(path)
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


def _optionvar_literals(path):
    """`cmds.optionVar(...)` に直接渡されている文字列キーを集める。

    `sv=("key", value)` の形はタプルの**先頭だけ**がキー。 2 番目まで見ると
    値のほうを誤検出する。 定数を組み立てて渡している形は追わない。
    """
    tree, _ = _parse(path)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Attribute)
                and node.func.attr == "optionVar"):
            continue
        keys = []
        for operand in list(node.args) + [kw.value for kw in node.keywords]:
            if isinstance(operand, (ast.Tuple, ast.List)):
                if operand.elts:
                    keys.append(operand.elts[0])
            else:
                keys.append(operand)
        for operand in keys:
            if isinstance(operand, ast.Constant) and isinstance(operand.value, str):
                found.append(operand.value)
    return found


def _read_doc(name):
    path = _bootstrap.TOOL_DIR / name
    return path.read_text(encoding="utf-8") if path.is_file() else None


# --- テスト ------------------------------------------------------------------

class VersionCase(unittest.TestCase):
    """`__version__` を唯一の情報源とした版数の一致。"""

    def setUp(self):
        self.consts = _module_constants(_bootstrap.PACKAGE_DIR / "__init__.py")

    def test_version_is_defined_and_semver(self):
        version = self.consts.get("__version__")
        self.assertIsNotNone(version, "__init__.py に __version__ が無い")
        self.assertRegex(version, _SEMVER,
                         "__version__ は x.y.z 形式にする: %r" % (version,))

    def test_spec_version_matches(self):
        self._assert_doc_version("SPEC.md")

    def test_readme_version_matches(self):
        self._assert_doc_version("README.md")

    def test_changelog_has_current_version(self):
        text = _read_doc("CHANGELOG.md")
        if text is None:
            self.skipTest("CHANGELOG.md が無い")
        headings = _CHANGELOG_HEADING.findall(text)
        self.assertIn(self.consts["__version__"], headings,
                      "CHANGELOG.md に現行バージョンの見出しが無い")

    def _assert_doc_version(self, name):
        text = _read_doc(name)
        if text is None:
            self.skipTest("%s が無い" % (name,))
        found = _DOC_VERSION_LINE.search(text)
        self.assertIsNotNone(
            found, "%s の「概要」に `- バージョン: x.y.z` の行が無い" % (name,))
        self.assertEqual(found.group(1), self.consts["__version__"],
                         "%s のバージョンが __version__ と食い違っている" % (name,))


class DistributionCase(unittest.TestCase):
    """配布 — ここがずれると実機だけで壊れる。

    配布は**リポジトリ直下のハブ 1 本**が行う。 ハブは
    `<名前>/<名前>/__init__.py` という形のフォルダを tree API で探して
    中身を全部配るので、ツール側が守るべきことは「その形になっていること」と
    「ハブと定数が食い違っていないこと」の 2 つだけ。
    """

    def setUp(self):
        self.installer = _bootstrap.installer_path()
        if not self.installer.is_file():
            self.skipTest("リポジトリ直下に install.py が無い")
        self.consts = _module_constants(self.installer)

    def test_layout_matches_the_hub_discovery_rule(self):
        """ハブが拾える形か。 外れると**丸ごと配布されない**。"""
        self.assertEqual(_bootstrap.PACKAGE_DIR.name, _bootstrap.TOOL_DIR.name,
                         "パッケージ名はツールフォルダ名と同じにする "
                         "（ハブは <名前>/<名前>/ の形だけを探す）")
        self.assertTrue((_bootstrap.PACKAGE_DIR / "__init__.py").is_file(),
                        "パッケージに __init__.py が無い（ハブが拾わない）")

    def test_no_per_tool_installer_left_behind(self):
        """ツールごとの install.py は廃止済み。 残っていると二重管理になる。"""
        self.assertFalse(
            (_bootstrap.TOOL_DIR / "install.py").is_file(),
            "ツールフォルダに install.py が残っている "
            "（配布はリポジトリ直下のハブ 1 本に集約した）")

    def test_shelf_label_is_defined_and_short(self):
        """ハブがシェルフボタンに出す名前。 長いとボタンから溢れる。"""
        label = _module_constants(
            _bootstrap.PACKAGE_DIR / "__init__.py").get("SHELF_LABEL")
        self.assertIsNotNone(label, "__init__.py に SHELF_LABEL が無い "
                                    "（ハブがシェルフボタンに出す短い名前）")
        self.assertTrue(0 < len(label) <= 10,
                        "SHELF_LABEL は 10 文字以内にする: %r" % (label,))

    def test_github_coordinates_agree_with_dev_tools(self):
        dev_tools = _bootstrap.PACKAGE_DIR / "dev_tools.py"
        if not dev_tools.is_file():
            self.skipTest("dev_tools.py が無い")
        theirs = _module_constants(dev_tools)
        for key in ("_GITHUB_OWNER", "_GITHUB_REPO", "_GITHUB_BRANCH"):
            self.assertEqual(
                self.consts.get(key), theirs.get(key),
                "%s がハブ install.py と dev_tools.py で食い違っている" % (key,))

    def test_namespace_agrees_with_package(self):
        """ハブの `_NAMESPACE` とパッケージの `NAMESPACE` は同じ値。

        ずれると `_close_existing_window()` が別名のウィンドウを探すので、
        更新後に古いウィンドウが residual として残る。
        """
        init_py = _bootstrap.PACKAGE_DIR / "__init__.py"
        theirs = _module_constants(init_py).get("NAMESPACE")
        self.assertIsNotNone(theirs, "__init__.py に NAMESPACE が無い")
        self.assertEqual(self.consts.get("_NAMESPACE"), theirs,
                         "NAMESPACE がハブとパッケージで食い違っている")

    def test_installer_defines_dropped_hook(self):
        tree, _ = _parse(self.installer)
        names = {n.name for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef)}
        self.assertIn("onMayaDroppedPythonFile", names,
                      "ドラッグ&ドロップの入口が無い")
        self.assertIn("install", names)


class LayoutCase(unittest.TestCase):
    """命名規則とレイヤ分離。"""

    def test_window_name_follows_convention(self):
        ui = _bootstrap.PACKAGE_DIR / "ui.py"
        if not ui.is_file():
            self.skipTest("ui.py が無い")
        module = _bootstrap.import_tool()
        window = getattr(module.ui, "WINDOW", None)
        expected = "%s_%sWin" % (module.NAMESPACE, _bootstrap.PACKAGE_NAME)
        self.assertEqual(window, expected,
                         "ウィンドウ名は <NAMESPACE>_<モジュール名>Win にする "
                         "（install.py が古いウィンドウを閉じられなくなる）")

    def test_runtime_identifiers_are_namespaced(self):
        """optionVar / scriptJob は Maya 全体で 1 つの空間を共有する。

        接頭辞の無いキーは他人のツールと**後勝ちで静かに衝突する**ので、
        `<NAMESPACE>_<モジュール名>` で始まっていることを機械で確かめる。
        """
        module = _bootstrap.import_tool()
        prefix = "%s_%s" % (module.NAMESPACE, _bootstrap.PACKAGE_NAME)
        for path in _bootstrap.tool_source_files():
            for key in _optionvar_literals(path):
                with self.subTest(key=key):
                    self.assertTrue(
                        key.startswith(prefix),
                        "optionVar のキー %r が名前空間に入っていない。 "
                        "%r で始めるか `_NS` から組み立てる（%s）"
                        % (key, prefix + "_", path.name))

    def test_core_does_not_import_maya(self):
        core = _bootstrap.PACKAGE_DIR / "core.py"
        if not core.is_file():
            self.skipTest("core.py が無い")
        self.assertNotIn("maya", _imported_roots(core),
                         "core.py は Maya 非依存に保つ "
                         "（ここが自宅でテストできる唯一の範囲）")

    def test_sources_parse_as_target_python(self):
        """Maya の Python バージョンで解析できるか（新しい構文の混入を防ぐ）。"""
        targets = list(_bootstrap.tool_source_files())
        installer = _bootstrap.installer_path()
        if installer.is_file():
            targets.append(installer)
        for path in targets:
            with self.subTest(path=path.name):
                source = path.read_text(encoding="utf-8")
                try:
                    ast.parse(source, str(path),
                              feature_version=_TARGET_PYTHON)
                except SyntaxError as exc:
                    self.fail("Python %d.%d で解析できない: %s"
                              % (_TARGET_PYTHON[0], _TARGET_PYTHON[1], exc))


class RoundTripCase(unittest.TestCase):
    """import → show() → deleteUI の一往復。"""

    def setUp(self):
        _bootstrap.reset_registry()
        self.module = _bootstrap.reload_tool()

    def test_show_is_callable(self):
        self.assertTrue(callable(getattr(self.module, "show", None)),
                        "パッケージ直下に show() が無い "
                        "（シェルフボタンの起動コマンドが呼ぶ入口）")

    def test_show_creates_and_deletes_window(self):
        window = self.module.ui.WINDOW
        self.module.show()
        self.assertIn(window, _bootstrap.WINDOWS,
                      "show() でウィンドウが生成されていない")
        self.assertTrue(_bootstrap.WINDOWS[window]["_shown"],
                        "showWindow() が呼ばれていない")

        from maya import cmds
        cmds.deleteUI(window)
        self.assertNotIn(window, _bootstrap.WINDOWS)

    def test_show_twice_does_not_leak_windows(self):
        self.module.show()
        self.module.show()
        self.assertEqual(len(_bootstrap.WINDOWS), 1,
                         "show() を 2 回呼ぶとウィンドウが増える "
                         "（既存を deleteUI してから作る）")

    def test_show_leaves_no_open_undo_chunk(self):
        self.module.show()
        self.assertEqual(_bootstrap.UNDO_CHUNKS, [],
                         "undo チャンクが開きっぱなし "
                         "（以降の undo が壊れ、Maya 再起動まで直らない）")

    def test_footer_shows_version(self):
        """バージョン表示は必須。 実機で更新が届いたか確かめる唯一の手段。"""
        self.module.show()
        labels = [kwargs.get("l") or kwargs.get("label") or ""
                  for name, args, kwargs in _bootstrap.CALLS
                  if name == "text"]
        self.assertTrue(
            any(self.module.__version__ in str(label) for label in labels),
            "UI にバージョンが表示されていない")


if __name__ == "__main__":
    unittest.main()
