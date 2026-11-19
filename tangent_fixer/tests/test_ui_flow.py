# -*- coding: utf-8 -*-
"""`ui.fix()` の流れを、偽のカーブで一往復させる。

偽のカーブは「Linear の角度 = atan(傾き × 倍率)」という**仮定した**実機の
振る舞いを持つ。 ここで確かめるのは、実測した倍率で角度を書くこと・
対象キーだけを書くこと・undo チャンクを閉じること、までで、
**実機の単位が本当にこうなっているかは確かめていない**（`probe()` で持ち帰る）。
"""

from __future__ import annotations

import math
import unittest
from unittest import mock

import _bootstrap

from tangent_fixer import core


class _FakeCurve(object):
    def __init__(self, times, values, scale, selected=None, out_types=None):
        self.times = list(times)
        self.values = list(values)
        self.scale = scale
        self.selected = selected
        n = len(times)
        self.itt = ["auto"] * n
        self.ott = list(out_types or ["auto"] * n)
        self.ia = [0.0] * n
        self.oa = [0.0] * n
        self.lock = [False] * n

    def linear_angle(self, i, side):
        j = i + 1 if side == "out" else i - 1
        s = (self.values[j] - self.values[i]) / (self.times[j] - self.times[i])
        return math.degrees(math.atan(s * self.scale))


class _FakeScene(object):
    def __init__(self, curves, unit="film"):
        self.curves = curves
        self.unit = unit

    def keyframe(self, *args, **kw):
        if kw.get("selected") and kw.get("name"):
            return [n for n, c in self.curves.items() if c.selected] or None
        if kw.get("name"):
            return list(self.curves)
        curve = self.curves[args[0]]
        if kw.get("selected") and kw.get("indexValue"):
            return list(curve.selected or [])
        if kw.get("timeChange"):
            return list(curve.times)
        if kw.get("valueChange"):
            return list(curve.values)
        raise AssertionError("unexpected keyframe %r %r" % (args, kw))

    def keyTangent(self, curve_name, **kw):
        c = self.curves[curve_name]
        if kw.get("q"):
            if kw.get("weightedTangents"):
                return [False]
            if kw.get("outTangentType"):
                return list(c.ott)
            i = kw["index"][0]
            if kw.get("outAngle"):
                return [c.oa[i]]
            if kw.get("inAngle"):
                return [c.ia[i]]
            raise AssertionError("unexpected query %r" % (kw,))
        i = kw["index"][0]
        if kw.get("outTangentType"):
            c.ott[i] = kw["outTangentType"]
            if c.ott[i] == "linear":
                c.oa[i] = c.linear_angle(i, "out")
        if kw.get("inTangentType"):
            c.itt[i] = kw["inTangentType"]
            if c.itt[i] == "linear":
                c.ia[i] = c.linear_angle(i, "in")
        if "inAngle" in kw:
            c.ia[i] = kw["inAngle"]
        if "outAngle" in kw:
            c.oa[i] = kw["outAngle"]
        if "lock" in kw:
            c.lock[i] = kw["lock"]
        return None

    def currentUnit(self, **kw):
        return self.unit

    def patch(self):
        from maya import cmds
        return mock.patch.multiple(cmds, create=True,
                                   keyframe=self.keyframe,
                                   keyTangent=self.keyTangent,
                                   currentUnit=self.currentUnit)


class FixFlowCase(unittest.TestCase):

    def setUp(self):
        _bootstrap.reset_registry()
        self.module = _bootstrap.reload_tool()

    def _expected(self, curve, mode=core.END_FLAT, method=core.METHOD_SMOOTH):
        slopes = core.compute_slopes(curve.times, curve.values, end_mode=mode,
                                     method=method)
        return [math.degrees(math.atan(m * curve.scale)) for m in slopes]

    def test_selected_keys_only_with_measured_scale(self):
        # 倍率を fps(24) と違う値にして、実測値が使われることを確かめる
        curve = _FakeCurve([0, 10, 14, 30], [10.0, 6.0, 4.0, 0.0],
                           scale=0.42, selected=[1, 2])
        scene = _FakeScene({"c1": curve})
        with scene.patch():
            summary = self.module.fix()
        expected = self._expected(curve)
        for i in (1, 2):
            self.assertAlmostEqual(curve.ia[i], expected[i])
            self.assertAlmostEqual(curve.oa[i], expected[i])
            self.assertEqual((curve.itt[i], curve.ott[i]), ("fixed", "fixed"))
            self.assertTrue(curve.lock[i])
        for i in (0, 3):
            self.assertEqual((curve.itt[i], curve.ott[i]), ("auto", "auto"))
        self.assertIn("2 key(s) on 1 curve(s)", summary)
        self.assertEqual(_bootstrap.UNDO_CHUNKS, [])

    def test_whole_curves_of_selected_objects(self):
        curve = _FakeCurve([0, 10, 20], [0.0, 5.0, 10.0], scale=24.0)
        scene = _FakeScene({"c1": curve})
        _bootstrap.set_selection(["pCube1"])
        with scene.patch():
            self.module.fix(end_mode=core.END_NATURAL)
        expected = self._expected(curve, core.END_NATURAL)
        for i in range(3):
            self.assertAlmostEqual(curve.oa[i], expected[i])

    def test_method_is_passed_through(self):
        curve = _FakeCurve([0, 10, 20], [0.0, 0.5, 10.0], scale=24.0,
                           selected=[1])
        scene = _FakeScene({"c1": curve})
        with scene.patch():
            summary = self.module.fix(method=core.METHOD_TANGENT)
        self.assertAlmostEqual(
            curve.oa[1], self._expected(curve, method=core.METHOD_TANGENT)[1])
        self.assertIn("tangent", summary)

    def test_stepped_keys_are_left_alone(self):
        curve = _FakeCurve([0, 10, 20, 30], [0.0, 5.0, 8.0, 10.0], scale=24.0,
                           selected=[0, 1, 2, 3],
                           out_types=["auto", "step", "auto", "auto"])
        scene = _FakeScene({"c1": curve})
        with scene.patch():
            summary = self.module.fix()
        self.assertEqual(curve.ott[1], "step")
        self.assertIn("1 stepped key(s) skipped", summary)

    def test_nothing_selected_warns(self):
        scene = _FakeScene({})
        with scene.patch():
            self.assertIsNone(self.module.fix())
        self.assertTrue(_bootstrap.MESSAGES)
        self.assertEqual(_bootstrap.UNDO_CHUNKS, [])

    def test_failure_on_one_curve_does_not_stop_others(self):
        good = _FakeCurve([0, 10, 20], [0.0, 5.0, 10.0], scale=24.0,
                          selected=[1])
        bad = _FakeCurve([0, 0, 20], [0.0, 5.0, 10.0], scale=24.0,
                         selected=[1])   # 同時刻キーで ValueError
        scene = _FakeScene({"bad": bad, "good": good})
        with scene.patch():
            summary = self.module.fix()
        self.assertIn("1 curve(s) failed", summary)
        self.assertAlmostEqual(good.oa[1], self._expected(good)[1])
        self.assertEqual(_bootstrap.UNDO_CHUNKS, [])


if __name__ == "__main__":
    unittest.main()
