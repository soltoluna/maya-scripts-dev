# -*- coding: utf-8 -*-
"""`ui.fix()` の流れを、偽のカーブで一往復させる。

偽のカーブは「Linear の角度 = atan(傾き × 倍率)」という**仮定した**実機の
振る舞いを持ち、倍率はカーブの型ごとに変えられる。 ここで確かめるのは、
一時カーブで実測した倍率で角度を書くこと・対象キーだけを書くこと・
**ユーザーのキーに途中経過の変更を入れないこと**・undo チャンクを閉じること、
までで、**実機の単位や undo の挙動が本当にこうなっているかは確かめていない**
（`probe(try_it=True)` で持ち帰る）。
"""

from __future__ import annotations

import math
import unittest
from unittest import mock

import _bootstrap

from tangent_fixer import core


class _FakeCurve(object):
    def __init__(self, times, values, node_type="animCurveTL", selected=None,
                 out_types=None, locks=None):
        self.times = list(times)
        self.values = list(values)
        self.node_type = node_type
        self.selected = selected
        n = len(times)
        self.itt = ["auto"] * n
        self.ott = list(out_types or ["auto"] * n)
        self.ia = [0.0] * n
        self.oa = [0.0] * n
        self.lock = list(locks if locks is not None else [True] * n)
        self.edits = []      # (index, 変更したフラグ) の履歴

    def add_key(self, t, v):
        self.times.append(t)
        self.values.append(v)
        for col, default in ((self.itt, "auto"), (self.ott, "auto"),
                             (self.ia, 0.0), (self.oa, 0.0), (self.lock, True)):
            col.append(default)


class _FakeScene(object):
    def __init__(self, curves, scales=None, unit="film"):
        self.curves = curves
        self.scales = scales or {"animCurveTL": 24.0}
        self.unit = unit
        self.created = []

    def _linear_angle(self, c, i, side):
        j = i + 1 if side == "out" else i - 1
        s = (c.values[j] - c.values[i]) / (c.times[j] - c.times[i])
        return math.degrees(math.atan(s * self.scales[c.node_type]))

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
            if kw.get("lock"):
                return list(c.lock)
            i = kw["index"][0]
            if kw.get("outAngle"):
                return [c.oa[i]]
            if kw.get("inAngle"):
                return [c.ia[i]]
            raise AssertionError("unexpected query %r" % (kw,))
        i = kw["index"][0]
        changed = sorted(k for k in kw if k not in ("edit", "index", "absolute"))
        c.edits.append((i, tuple(changed)))
        if kw.get("outTangentType"):
            c.ott[i] = kw["outTangentType"]
            if c.ott[i] == "linear":
                c.oa[i] = self._linear_angle(c, i, "out")
        if kw.get("inTangentType"):
            c.itt[i] = kw["inTangentType"]
        if "inAngle" in kw:
            c.ia[i] = kw["inAngle"]
        if "outAngle" in kw:
            c.oa[i] = kw["outAngle"]
        if "lock" in kw:
            c.lock[i] = kw["lock"]
        return None

    def nodeType(self, name):
        return self.curves[name].node_type

    def createNode(self, node_type, **kw):
        name = kw.get("name", "tmp") + str(len(self.created))
        self.created.append(name)
        self.curves[name] = _FakeCurve([], [], node_type=node_type)
        return name

    def setKeyframe(self, name, time, value, **kw):
        self.curves[name].add_key(float(time), float(value))

    def objExists(self, name):
        return name in self.curves

    def delete(self, name):
        self.curves.pop(name)

    def currentUnit(self, **kw):
        return self.unit

    def patch(self):
        from maya import cmds
        return mock.patch.multiple(
            cmds, create=True, keyframe=self.keyframe,
            keyTangent=self.keyTangent, currentUnit=self.currentUnit,
            nodeType=self.nodeType, createNode=self.createNode,
            setKeyframe=self.setKeyframe, objExists=self.objExists,
            delete=self.delete)


class FixFlowCase(unittest.TestCase):

    def setUp(self):
        _bootstrap.reset_registry()
        self.module = _bootstrap.reload_tool()

    def _expected(self, curve, scale, mode=core.END_FLAT,
                  method=core.METHOD_SMOOTH):
        slopes = core.compute_slopes(curve.times, curve.values, end_mode=mode,
                                     method=method)
        return [math.degrees(math.atan(m * scale)) for m in slopes]

    def test_selected_keys_only_with_measured_scale(self):
        # 倍率を fps(24) と違う値にして、実測値が使われることを確かめる
        curve = _FakeCurve([0, 10, 14, 30], [10.0, 6.0, 4.0, 0.0],
                           selected=[1, 2])
        scene = _FakeScene({"c1": curve}, scales={"animCurveTL": 0.42})
        with scene.patch():
            summary = self.module.fix()
        expected = self._expected(curve, 0.42)
        for i in (1, 2):
            self.assertAlmostEqual(curve.ia[i], expected[i])
            self.assertAlmostEqual(curve.oa[i], expected[i])
            self.assertEqual((curve.itt[i], curve.ott[i]), ("fixed", "fixed"))
            self.assertTrue(curve.lock[i])
        for i in (0, 3):
            self.assertEqual((curve.itt[i], curve.ott[i]), ("auto", "auto"))
        self.assertIn("2 key(s) on 1 curve(s)", summary)
        self.assertEqual(_bootstrap.UNDO_CHUNKS, [])

    def test_scale_is_measured_per_curve_type(self):
        tl = _FakeCurve([0, 10, 20], [0.0, 5.0, 10.0], selected=[1])
        ta = _FakeCurve([0, 10, 20], [0.0, 5.0, 10.0], node_type="animCurveTA",
                        selected=[1])
        scene = _FakeScene({"tl": tl, "ta": ta},
                           scales={"animCurveTL": 24.0,
                                   "animCurveTA": 24.0 * math.pi / 180.0})
        with scene.patch():
            self.module.fix()
        self.assertAlmostEqual(tl.oa[1], self._expected(tl, 24.0)[1])
        self.assertAlmostEqual(
            ta.oa[1], self._expected(ta, 24.0 * math.pi / 180.0)[1])
        self.assertEqual(len(scene.created), 2)          # 型ごとに 1 回
        self.assertFalse(any(n in scene.curves for n in scene.created),
                         "一時カーブが残っている")

    def test_user_keys_get_no_intermediate_edits(self):
        """v0.2.1: Ctrl+Z 後に break が残る不具合。

        ユーザーのキーを測定のために Linear にしない。 元からロックされている
        キーのロックには触らない（暗黙の break → undo で戻らない、を避ける）。
        """
        curve = _FakeCurve([0, 10, 20, 30], [0.0, 4.0, 6.0, 10.0],
                           selected=[0, 1, 2, 3],
                           locks=[True, True, False, True])
        scene = _FakeScene({"c1": curve})
        with scene.patch():
            self.module.fix()
        for index, flags in curve.edits:
            self.assertNotIn("linear", (curve.itt[index], curve.ott[index]))
            if index != 2:
                self.assertNotIn("lock", flags,
                                 "元からロックされているキーの lock を触った")
        self.assertIn((2, ("lock",)), curve.edits)        # break だけ明示的に lock
        self.assertEqual(curve.lock, [True] * 4)

    def test_whole_curves_of_selected_objects(self):
        curve = _FakeCurve([0, 10, 20], [0.0, 5.0, 10.0])
        scene = _FakeScene({"c1": curve})
        _bootstrap.set_selection(["pCube1"])
        with scene.patch():
            self.module.fix(end_mode=core.END_NATURAL)
        expected = self._expected(curve, 24.0, core.END_NATURAL)
        for i in range(3):
            self.assertAlmostEqual(curve.oa[i], expected[i])

    def test_method_is_passed_through(self):
        curve = _FakeCurve([0, 10, 20], [0.0, 0.5, 10.0], selected=[1])
        scene = _FakeScene({"c1": curve})
        with scene.patch():
            summary = self.module.fix(method=core.METHOD_LOCAL)
        self.assertAlmostEqual(
            curve.oa[1],
            self._expected(curve, 24.0, method=core.METHOD_LOCAL)[1])
        self.assertIn("local", summary)

    def test_stepped_keys_are_left_alone(self):
        curve = _FakeCurve([0, 10, 20, 30], [0.0, 5.0, 8.0, 10.0],
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
        good = _FakeCurve([0, 10, 20], [0.0, 5.0, 10.0], selected=[1])
        bad = _FakeCurve([0, 0, 20], [0.0, 5.0, 10.0],
                         selected=[1])   # 同時刻キーで ValueError
        scene = _FakeScene({"bad": bad, "good": good})
        with scene.patch():
            summary = self.module.fix()
        self.assertIn("1 curve(s) failed", summary)
        self.assertAlmostEqual(good.oa[1], self._expected(good, 24.0)[1])
        self.assertEqual(_bootstrap.UNDO_CHUNKS, [])

    def test_calibration_failure_falls_back(self):
        curve = _FakeCurve([0, 10, 20], [0.0, 5.0, 10.0], selected=[1])
        scene = _FakeScene({"c1": curve})

        def broken(*_a, **_k):
            raise RuntimeError("no createNode")

        with scene.patch():
            from maya import cmds
            with mock.patch.object(cmds, "createNode", broken):
                self.module.fix()
        self.assertAlmostEqual(curve.oa[1], self._expected(curve, 24.0)[1])
        self.assertEqual(_bootstrap.UNDO_CHUNKS, [])


if __name__ == "__main__":
    unittest.main()
