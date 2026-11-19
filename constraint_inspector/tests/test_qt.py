# -*- coding: utf-8 -*-
"""PySide2 / PySide6 両対応の回帰テスト。

このツールの目的のひとつが「Maya 2024 と 2025 の両方で開くこと」。 自宅には
PySide が無いので Qt の実挙動は確かめられないが、**import の経路**は確かめられる:

1. shim（`qt.py`）が PySide6 を優先し、無ければ PySide2 に落ちる
2. パッケージ内で `PySide2` / `PySide6` / `shiboken*` を直接 import している
   のは `qt.py` だけ（1 箇所でも漏れると 2025 で import に失敗する）
3. Qt5 → Qt6 で消えた / 移った API を使っていない
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
import types
import unittest

import _bootstrap
import _qt_stub  # noqa: F401


_QT_ROOTS = {"PySide2", "PySide6", "shiboken2", "shiboken6"}

# Qt6 で消えた・移った API（CLAUDE.md「PySide2/6 両対応 shim」）
_QT6_PITFALLS = [
    (re.compile(r"QtWidgets\.QAction\b"), "QAction は Qt6 で QtGui へ移った"),
    (re.compile(r"QtWidgets\.QActionGroup\b"), "QActionGroup は Qt6 で QtGui へ移った"),
    (re.compile(r"QtWidgets\.QShortcut\b"), "QShortcut は Qt6 で QtGui へ移った"),
    (re.compile(r"\.exec_\("), "exec_() は exec() に寄せる"),
    (re.compile(r"\bQRegExp\b"), "QRegExp は Qt6 で廃止（QRegularExpression）"),
    (re.compile(r"\bQDesktopWidget\b"), "QDesktopWidget は Qt6 で廃止"),
    (re.compile(r"\.setMargin\("), "setMargin() は Qt6 で廃止（setContentsMargins）"),
]


def _load_shim_with(available):
    """`available` に挙げた Qt だけがある状態で `qt.py` を読み込む。"""
    saved = {k: sys.modules[k] for k in list(sys.modules)
             if k.split(".")[0] in _QT_ROOTS}
    for key in saved:
        sys.modules.pop(key)
    try:
        for root in available:
            binding = types.ModuleType(root)
            for sub in ("QtCore", "QtGui", "QtWidgets"):
                module = types.ModuleType("%s.%s" % (root, sub))
                module.binding = root
                if sub == "QtCore":
                    module.Qt = type("Qt", (), {})
                setattr(binding, sub, module)
                sys.modules["%s.%s" % (root, sub)] = module
            sys.modules[root] = binding
            shiboken = types.ModuleType(
                "shiboken6" if root == "PySide6" else "shiboken2")
            shiboken.wrapInstance = lambda *_a, _root=root: _root
            sys.modules[shiboken.__name__] = shiboken

        spec = importlib.util.spec_from_file_location(
            "_shim_under_test", _bootstrap.PACKAGE_DIR / "qt.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for key in [k for k in list(sys.modules)
                    if k.split(".")[0] in _QT_ROOTS]:
            sys.modules.pop(key)
        sys.modules.update(saved)


class ShimCase(unittest.TestCase):

    def test_prefers_pyside6_for_maya_2025(self):
        shim = _load_shim_with(["PySide6", "PySide2"])
        self.assertEqual(shim.QtWidgets.binding, "PySide6")
        self.assertEqual(shim.wrapInstance(), "PySide6")

    def test_falls_back_to_pyside2_for_maya_2024(self):
        shim = _load_shim_with(["PySide2"])
        self.assertEqual(shim.QtWidgets.binding, "PySide2")
        self.assertEqual(shim.wrapInstance(), "PySide2")

    def test_exposes_qt_namespace(self):
        shim = _load_shim_with(["PySide2"])
        self.assertIs(shim.Qt, shim.QtCore.Qt)


class ImportDisciplineCase(unittest.TestCase):

    def test_only_the_shim_imports_qt(self):
        for path in _bootstrap.tool_source_files():
            if path.name == "qt.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots = {a.name.split(".")[0] for a in node.names}
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    roots = {(node.module or "").split(".")[0]}
                else:
                    continue
                with self.subTest(path=path.name, line=node.lineno):
                    self.assertFalse(
                        roots & _QT_ROOTS,
                        "%s:%d が Qt を直接 import している。 `.qt` から "
                        "import する（2025 で落ちる）" % (path.name, node.lineno))

    def test_no_qt6_removed_apis(self):
        for path in _bootstrap.tool_source_files():
            source = path.read_text(encoding="utf-8")
            for pattern, reason in _QT6_PITFALLS:
                with self.subTest(path=path.name, api=pattern.pattern):
                    self.assertIsNone(pattern.search(source),
                                      "%s: %s" % (path.name, reason))


if __name__ == "__main__":
    unittest.main()
