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

EXCLUDED_DIRS = {"docs", "tools", "tests", "dist"}


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


class OfflineFallbackCase(unittest.TestCase):
    """GitHub に届かないときの逃げ道。

    社内ネットワークでは TLS 傍受プロキシ・PAC・セキュリティソフトのどれかで
    **Maya の Python だけが外に出られない**ことがある（ブラウザは通る）。
    そのとき生のトレースバックで終わらせると、利用者は詰む。
    """

    def test_without_a_local_checkout_it_explains_the_zip_route(self):
        """install.py 単体を保存した場合。 maya を触る前に諦めること。"""
        import tempfile
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises(RuntimeError) as caught:
                hub._offline_fallback(OSError("ssl handshake failed"), empty)
        message = str(caught.exception)
        self.assertIn("ssl handshake failed", message,
                      "元のエラーが伝わっていない")
        self.assertIn(".zip", message, "ZIP を落とす導線が案内されていない")

    def test_a_missing_folder_is_not_a_crash(self):
        with self.assertRaises(RuntimeError):
            hub._offline_fallback(OSError("boom"),
                                  str(REPO_ROOT / "does_not_exist"))

    def test_the_repo_itself_is_a_valid_offline_source(self):
        """ZIP を展開した形＝このリポジトリの形。 ここから拾えること。"""
        tools = hub._local_tools(str(REPO_ROOT))
        self.assertTrue(tools, "リポジトリ直下からツールを拾えていない")
        self.assertEqual(sorted(tools), [p.name for p in _tool_dirs()])

    def test_the_hint_points_at_the_configured_repo(self):
        self.assertIn(hub._GITHUB_OWNER, hub._OFFLINE_HINT)
        self.assertIn(hub._GITHUB_REPO, hub._OFFLINE_HINT)


class OfflineBundleCase(unittest.TestCase):
    """1 本だけをオフラインで配るバンドル（`tools/make_bundle.py`）。

    ここが壊れると**バンドルなのに GitHub を見に行き、全ツールが入る**。
    渡した相手の環境で起きるので、こちらからは見えない。
    """

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.here = pathlib.Path(self.tmp.name)

    def _make_bundle(self, *names):
        if str(REPO_ROOT / "tools") not in sys.path:
            sys.path.insert(0, str(REPO_ROOT / "tools"))
        import make_bundle
        make_bundle.build(list(names), self.here, make_zip=False)
        return next(p for p in self.here.iterdir() if p.is_dir())

    def test_marker_switches_the_hub_offline(self):
        self.assertIsNone(hub._offline_reason(str(self.here)))
        (self.here / hub._OFFLINE_MARKER).write_text("x", encoding="utf-8")
        self.assertEqual(hub._offline_reason(str(self.here)),
                         hub._OFFLINE_MARKER)

    def test_env_var_still_works(self):
        import os
        os.environ[hub._USE_LOCAL_ENV] = "1"
        self.addCleanup(os.environ.pop, hub._USE_LOCAL_ENV, None)
        self.assertTrue(hub._offline_reason(str(self.here)))

    def test_a_missing_folder_is_not_offline(self):
        self.assertIsNone(
            hub._offline_reason(str(self.here / "does_not_exist")))

    def test_a_bundle_carries_the_marker_and_the_hub(self):
        root = self._make_bundle("color_override")
        self.assertTrue((root / "install.py").is_file())
        self.assertTrue((root / hub._OFFLINE_MARKER).is_file(),
                        "マーカーが無いとバンドルが GitHub を見に行く")
        self.assertEqual(hub._offline_reason(str(root)), hub._OFFLINE_MARKER)

    def test_a_bundle_contains_only_the_requested_tool(self):
        """**1 本だけ渡す**が成立していること。"""
        root = self._make_bundle("color_override")
        self.assertEqual(sorted(hub._local_tools(str(root))),
                         ["color_override"])

    def test_a_bundle_ships_every_file_the_hub_would_install(self):
        root = self._make_bundle("color_override")
        bundled = hub._local_tools(str(root))["color_override"]
        source = hub._local_tools(str(REPO_ROOT))["color_override"]
        self.assertEqual(sorted(bundled), sorted(source),
                         "バンドルに入っていないファイルがある")

    def test_an_unknown_tool_is_refused(self):
        with self.assertRaises(SystemExit):
            self._make_bundle("no_such_tool")


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
