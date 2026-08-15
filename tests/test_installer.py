# -*- coding: utf-8 -*-
"""ハブ `install.py` の回帰テスト（Maya 不要）。

配布はリポジトリ直下の `install.py` 1 本が担う。 ツールごとの `install.py` は
廃止し、**配布対象は GitHub の tree API で自動列挙**するようにした。
その結果、`_REMOTE_FILES` の追記忘れ（`docs/MAYA_HOT_UPDATE_PATTERNS.md`
§1-10）は原理的に起きなくなったが、代わりに**探索規則そのもの**が壊れると
全ツールが一斉に配布されなくなる。 ここはその探索規則を守るためのテスト。

## `maya` スタブを入れないこと

`install.py` は末尾で `from maya import cmds` を試し、通ったら `install()` を
自動実行する（Script Editor からの `exec` に対応するため）。 スタブを入れると
これが通ってしまい、**テストが本当に GitHub へ取りに行って実機へ書き込む**。
このディレクトリでは `_bootstrap` を import しない。
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
INSTALLER = REPO_ROOT / "install.py"

EXCLUDED_DIRS = {"docs", "tools", "tests"}


def _load_installer():
    """`install.py` をモジュールとして読み込む。

    `maya` が無い環境なので、末尾の自動実行は `ImportError` で握り潰される。
    """
    assert "maya" not in sys.modules, (
        "maya スタブが入っている状態で install.py を読むと、"
        "末尾の自動実行が本当に GitHub へ取りに行く")
    spec = importlib.util.spec_from_file_location("hub_install", INSTALLER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hub = _load_installer()


def _tool_dirs():
    """リポジトリ直下のツールフォルダ（`check_tools.py` と同じ判定）。"""
    return sorted(p for p in REPO_ROOT.iterdir()
                  if p.is_dir()
                  and not p.name.startswith(".")
                  and p.name not in EXCLUDED_DIRS
                  and (p / p.name / "__init__.py").is_file())


class DiscoveryCase(unittest.TestCase):
    """`<名前>/<名前>/` だけを拾う。 ここが緩むと余計なものを配る。"""

    def test_picks_up_a_tool_folder(self):
        found = hub._discover_tools([
            "my_tool/my_tool/__init__.py",
            "my_tool/my_tool/ui.py",
            "my_tool/SPEC.md",
            "my_tool/tests/test_core.py",
        ])
        self.assertEqual(found, {"my_tool": ["__init__.py", "ui.py"]})

    def test_ignores_folders_without_init(self):
        """`__init__.py` が無ければパッケージではない（＝配らない）。"""
        self.assertEqual(hub._discover_tools(["thing/thing/helper.py"]), {})

    def test_ignores_the_template(self):
        """雛形は `docs/templates/` の下にあるので拾ってはいけない。"""
        found = hub._discover_tools([
            "docs/templates/tool_template/tool_template/__init__.py"])
        self.assertEqual(found, {})

    def test_ignores_legacy_single_file_scripts(self):
        """標準セット化前のフォルダ（同名パッケージが無い）は配らない。"""
        self.assertEqual(
            hub._discover_tools(["PlayblastTool/playblast_tool.py"]), {})

    def test_ignores_pycache(self):
        found = hub._discover_tools([
            "my_tool/my_tool/__init__.py",
            "my_tool/my_tool/__pycache__/__init__.cpython-310.pyc",
        ])
        self.assertEqual(found, {"my_tool": ["__init__.py"]})

    def test_keeps_nested_module_paths(self):
        found = hub._discover_tools([
            "my_tool/my_tool/__init__.py",
            "my_tool/my_tool/parts/widget.py",
        ])
        self.assertEqual(found["my_tool"], ["__init__.py", "parts/widget.py"])


class ConstantCase(unittest.TestCase):

    def test_reads_version_and_namespace(self):
        source = ('__version__ = "1.2.3"\nNAMESPACE = "ntk"\n')
        self.assertEqual(hub._read_constant(source, "__version__"), "1.2.3")
        self.assertEqual(hub._read_constant(source, "NAMESPACE"), "ntk")

    def test_missing_constant_falls_back(self):
        self.assertEqual(hub._read_constant("", "__version__", "?"), "?")

    def test_shelf_label_prefers_the_declared_one(self):
        self.assertEqual(
            hub._shelf_label("my_tool", 'SHELF_LABEL = "MyTool"'), "MyTool")

    def test_shelf_label_falls_back_to_the_module_name(self):
        """宣言が無くてもボタンは貼れる（10 文字以内に収まること）。"""
        label = hub._shelf_label("unload_reference_delete", "")
        self.assertTrue(0 < len(label) <= 10, label)

    def test_shelf_label_is_truncated(self):
        self.assertEqual(
            len(hub._shelf_label("x", 'SHELF_LABEL = "0123456789ABC"')), 10)


class RepositoryCase(unittest.TestCase):
    """**実リポジトリとの突き合わせ。** 配布漏れを止める最後の砦。"""

    def setUp(self):
        self.tools = _tool_dirs()
        if not self.tools:
            self.skipTest("標準セットを適用したツールがまだ無い")

    def test_every_tool_is_discovered(self):
        """`check_tools.py` が見るツールを、ハブも漏れなく拾えること。"""
        found = hub._local_tools(str(REPO_ROOT))
        self.assertEqual(sorted(found), [p.name for p in self.tools])

    def test_every_package_file_would_be_distributed(self):
        """パッケージ内の全ファイルが配布対象の拡張子に入っていること。

        これが **§1-10 の後継**。 対象外の拡張子でリソースを足すと、
        自宅では動くのに実機にだけファイルが届かない。
        """
        found = hub._local_tools(str(REPO_ROOT))
        for tool in self.tools:
            pkg = tool / tool.name
            actual = {p.relative_to(pkg).as_posix()
                      for p in pkg.rglob("*")
                      if p.is_file() and "__pycache__" not in p.parts}
            missing = sorted(actual - set(found.get(tool.name, [])))
            self.assertFalse(
                missing,
                "%s: 配布対象から外れるファイルがある（拡張子を "
                "install.py の _ALLOWED_SUFFIXES に足す）: %s"
                % (tool.name, missing))

    def test_no_per_tool_installer_remains(self):
        for tool in self.tools:
            self.assertFalse((tool / "install.py").is_file(),
                             "%s に install.py が残っている（ハブに集約済み）"
                             % (tool.name,))

    def test_namespace_matches_every_package(self):
        for tool in self.tools:
            source = (tool / tool.name / "__init__.py").read_text(
                encoding="utf-8")
            self.assertEqual(
                hub._read_constant(source, "NAMESPACE"), hub._NAMESPACE,
                "%s の NAMESPACE がハブと違う（更新後に古いウィンドウが残る）"
                % (tool.name,))


class EntryPointCase(unittest.TestCase):

    def test_defines_dropped_hook(self):
        self.assertTrue(callable(getattr(hub, "onMayaDroppedPythonFile", None)))
        self.assertTrue(callable(getattr(hub, "install", None)))

    def test_coordinates_are_not_placeholders(self):
        for key in ("_GITHUB_OWNER", "_GITHUB_REPO", "_GITHUB_BRANCH"):
            value = getattr(hub, key)
            self.assertTrue(value and "YOUR_" not in value, "%s=%r" % (key, value))


if __name__ == "__main__":
    unittest.main()
