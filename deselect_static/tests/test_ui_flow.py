# -*- coding: utf-8 -*-
"""`ui.deselect_static()` の流れを、偽の `cmds.keyframe` で一往復させる。

ここで確かめるのは「集めた値を core に渡し、結果どおりに select する・
undo チャンクを閉じる・選択キーで判定したときはキー選択を戻す」まで。
**実機の `cmds.keyframe` が本当にこの形で値を返すかは確かめていない。**
"""

from __future__ import annotations

import unittest
from unittest import mock

import _bootstrap

from deselect_static import core


class _FakeScene(object):
    """`{obj: {curve: [(value, selected), ...]}}` を持つ偽のシーン。"""

    def __init__(self, scene):
        self.scene = scene
        self.select_key_calls = []

    def _curve(self, name):
        for curves in self.scene.values():
            if name in curves:
                return curves[name]
        return None

    def keyframe(self, *args, **kwargs):
        target = args[0] if args else None
        selected = kwargs.get("selected")
        if target is None:
            # cmds.keyframe(q=True, selected=True, name=True)
            return [c for curves in self.scene.values()
                    for c, keys in curves.items()
                    if any(sel for _, sel in keys)] or None
        if target in self.scene:
            # cmds.keyframe(obj, q=True, name=True)
            return list(self.scene[target]) or None
        keys = self._curve(target)
        if keys is None:
            return None
        rows = [(i, v) for i, (v, sel) in enumerate(keys)
                if (sel or not selected)]
        if kwargs.get("indexValue"):
            return [i for i, _ in rows]
        if kwargs.get("valueChange"):
            return [v for _, v in rows]
        return None

    def selectKey(self, *args, **kwargs):
        self.select_key_calls.append((args, kwargs))


class DeselectStaticFlowTest(unittest.TestCase):
    def setUp(self):
        _bootstrap.reset_registry()
        self.tool = _bootstrap.import_tool()
        self.ui = self.tool.ui

    def _run(self, scene, selection, tolerance=None):
        fake = _FakeScene(scene)
        _bootstrap.set_selection(selection)
        with mock.patch.object(self.ui.cmds, "keyframe", fake.keyframe,
                               create=True), \
                mock.patch.object(self.ui.cmds, "selectKey", fake.selectKey,
                                  create=True):
            result = self.ui.deselect_static(tolerance)
        return result, fake

    def test_all_keys_mode_keeps_only_animated(self):
        scene = {
            "|moving": {"moving_tx": [(0.0, False), (1.0, False)]},
            "|still": {"still_tx": [(2.0, False), (2.0, False)]},
            "|nokeys": {},
        }
        (changed, static), fake = self._run(
            scene, ["|moving", "|still", "|nokeys"])
        self.assertEqual(changed, ["|moving"])
        self.assertEqual(static, ["|still", "|nokeys"])
        self.assertEqual(_bootstrap._SELECTION, ["|moving"])
        self.assertEqual(_bootstrap.UNDO_CHUNKS, [])
        # 全キーで判定したときはキー選択に触らない
        self.assertEqual(fake.select_key_calls, [])

    def test_selected_keys_mode_judges_only_selected_keys(self):
        scene = {
            # 全体では動くが、選択した 2 キーは同じ値 → static
            "|a": {"a_tx": [(0.0, False), (5.0, True), (5.0, True)]},
            # 選択キーで値が動く → changed
            "|b": {"b_tx": [(1.0, True), (3.0, True)]},
            # キーが 1 つも選択されていない → static
            "|c": {"c_tx": [(0.0, False), (9.0, False)]},
        }
        (changed, static), fake = self._run(scene, ["|a", "|b", "|c"])
        self.assertEqual(changed, ["|b"])
        self.assertEqual(static, ["|a", "|c"])
        self.assertEqual(_bootstrap.UNDO_CHUNKS, [])
        # 残したオブジェクトのキー選択だけを戻す
        restored = [(a, k) for a, k in fake.select_key_calls if a]
        self.assertEqual(restored, [
            (("b_tx",), {"add": True, "index": (0, 0)}),
            (("b_tx",), {"add": True, "index": (1, 1)}),
        ])

    def test_nothing_changed_clears_selection(self):
        scene = {"|s": {"s_tx": [(1.0, False), (1.0, False)]}}
        (changed, static), _ = self._run(scene, ["|s"])
        self.assertEqual(changed, [])
        self.assertEqual(_bootstrap._SELECTION, [])
        self.assertEqual(_bootstrap.UNDO_CHUNKS, [])

    def test_empty_selection_warns_and_does_nothing(self):
        (changed, static), _ = self._run({}, [])
        self.assertEqual((changed, static), ([], []))
        self.assertTrue(any(kind == "warning"
                            for kind, _ in _bootstrap.MESSAGES))
        self.assertFalse(any(c[0] == "select" for c in _bootstrap.CALLS))

    def test_tolerance_from_argument(self):
        scene = {"|t": {"t_tx": [(0.0, False), (0.01, False)]}}
        (changed, _), _ = self._run(scene, ["|t"], tolerance=0.1)
        self.assertEqual(changed, [])
        (changed, _), _ = self._run(scene, ["|t"], tolerance=0.001)
        self.assertEqual(changed, ["|t"])

    def test_apply_button_saves_tolerance(self):
        self.ui.show()
        ctrl = self.ui._CTRL["tolerance"]
        _bootstrap.CONTROLS[ctrl]["value1"] = 0.5
        _bootstrap.set_selection([])
        self.ui._on_apply()
        self.assertEqual(_bootstrap.OPTION_VARS[self.ui._OPTVAR_TOLERANCE], 0.5)
        self.assertEqual(self.ui._load_tolerance(), 0.5)
        self.assertEqual(core.normalize_tolerance(
            _bootstrap.OPTION_VARS[self.ui._OPTVAR_TOLERANCE]), 0.5)


if __name__ == "__main__":
    unittest.main()
