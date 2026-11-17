# -*- coding: utf-8 -*-
"""`core.Checker` / `core.scan` / `core.group_frames` / `core.hud_text` のテスト。

Maya のメッシュの代わりに「時間で動く球」の偽アダプターを使う。 アダプターに
求める形は `core.Checker` の docstring、本物は `scene.MeshAdapter`。
"""

from __future__ import annotations

import math
import unittest

import _bootstrap  # noqa: F401  （maya スタブの注入。 他の import より前）

from penetration_checker import core


class _Clock(object):
    frame = 0.0


class _Sphere(object):
    """`center_fn(frame)` の位置にある半径 `radius` の球。 頂点は 6 方向の極点。"""

    def __init__(self, name, center_fn, radius=1.0, clock=None, closed=True,
                 influence=None):
        self.name = name
        self.center_fn = center_fn
        self.radius = radius
        self.clock = clock
        self.closed = closed
        self.influence = influence
        self.frames_read = []
        self.weight_calls = 0

    def _center(self):
        return self.center_fn(self.clock.frame)

    def begin_frame(self):
        self.frames_read.append(self.clock.frame)

    def points(self):
        c = self._center()
        r = self.radius
        return [(c[0] + r, c[1], c[2]), (c[0] - r, c[1], c[2]),
                (c[0], c[1] + r, c[2]), (c[0], c[1] - r, c[2]),
                (c[0], c[1], c[2] + r), (c[0], c[1], c[2] - r)]

    def bbox(self):
        return core.bbox_of_points(self.points())

    def closest(self, point):
        c = self._center()
        d = [point[i] - c[i] for i in range(3)]
        length = math.sqrt(sum(v * v for v in d)) or 1.0
        n = tuple(v / length for v in d)
        return tuple(c[i] + n[i] * self.radius for i in range(3)), n

    def is_closed(self):
        return self.closed

    def weights(self, _index):
        self.weight_calls += 1
        return None if self.influence is None else {self.influence: 1.0}


def _resolve(node):
    return (node.replace("_jnt", "_ctl"), "controller", [node])


class CheckerTest(unittest.TestCase):

    def setUp(self):
        self.clock = _Clock()
        # body は原点に固定、hand は x 方向へ 1 フレーム 0.5 ずつ近づく
        self.body = _Sphere("|body", lambda f: (0.0, 0.0, 0.0), clock=self.clock,
                            influence="|spine_jnt")
        self.hand = _Sphere("|hand", lambda f: (4.0 - 0.5 * f, 0.0, 0.0),
                            radius=0.5, clock=self.clock, influence="|hand_jnt")
        self.checker = core.Checker([self.body, self.hand], _resolve)

    def test_no_hit_when_apart(self):
        self.clock.frame = 0
        result = self.checker.check_frame()
        self.assertEqual(result["targets"], [])
        self.assertEqual(result["pairs"], 0, "ボックスが離れていれば組にもならない")

    def test_hand_into_body_selects_hand_ctrl(self):
        self.clock.frame = 6     # hand の中心 x=1.0。 -x 極点 (0.5,0,0) が body の中
        result = self.checker.check_frame()
        self.assertEqual(result["targets"][0]["target"], "|hand_ctl")
        self.assertAlmostEqual(result["targets"][0]["depth"], 0.5)

    def test_weights_are_cached_across_frames(self):
        self.clock.frame = 6
        self.checker.check_frame()
        calls = self.hand.weight_calls
        self.checker.check_frame()
        self.assertEqual(self.hand.weight_calls, calls)

    def test_begin_frame_is_called_every_frame(self):
        for f in (0, 1, 2):
            self.clock.frame = f
            self.checker.check_frame()
        self.assertEqual(self.hand.frames_read, [0, 1, 2])

    def test_unskinned_mesh_resolves_itself(self):
        self.hand.influence = None
        self.clock.frame = 6
        result = self.checker.check_frame()
        self.assertEqual(result["targets"][0]["target"], "|hand")

    def test_open_container_is_skipped_with_one_warning(self):
        self.body.closed = False
        self.clock.frame = 6
        self.checker.check_frame()
        self.checker.check_frame()
        self.assertEqual(len(self.checker.warnings), 1)

    def test_broken_mesh_is_warned_and_others_continue(self):
        def boom():
            raise RuntimeError("deleted")
        broken = _Sphere("|gone", lambda f: (0, 0, 0), clock=self.clock)
        broken.begin_frame = boom
        checker = core.Checker([self.body, self.hand, broken], _resolve)
        self.clock.frame = 6
        result = checker.check_frame()
        self.assertEqual(result["targets"][0]["target"], "|hand_ctl")
        self.assertEqual(len(checker.warnings), 1)

    def test_resolve_failure_falls_back(self):
        def bad(_node):
            raise RuntimeError("x")
        checker = core.Checker([self.body, self.hand], bad)
        self.clock.frame = 6
        result = checker.check_frame()
        self.assertEqual(result["targets"][0]["target"], "|hand_jnt")


class ScanTest(unittest.TestCase):

    def setUp(self):
        self.clock = _Clock()
        body = _Sphere("|body", lambda f: (0.0, 0.0, 0.0), clock=self.clock,
                       influence="|spine_jnt")
        # hand は 0→10 で近づき、10→20 で離れる
        hand = _Sphere("|hand", lambda f: (abs(10.0 - f) * 0.5 + 0.8, 0.0, 0.0),
                       radius=0.5, clock=self.clock, influence="|hand_jnt")
        self.checker = core.Checker([body, hand], _resolve)

    def _set(self, frame):
        self.clock.frame = frame

    def test_frame_list(self):
        self.assertEqual(core.frame_list(1, 3), [1.0, 2.0, 3.0])
        self.assertEqual(core.frame_list(3, 1), [1.0, 2.0, 3.0])
        self.assertEqual(core.frame_list(5, 5), [5.0])
        self.assertEqual(core.frame_list(0, 1, 0.5), [0.0, 0.5, 1.0])

    def test_scan_and_group(self):
        results, cancelled = core.scan(self.checker, core.frame_list(0, 20), self._set)
        self.assertFalse(cancelled)
        self.assertEqual(len(results), 21)
        groups = core.group_frames(results)
        self.assertEqual(len(groups), 1)
        g = groups[0]
        self.assertEqual(g["worst_frame"], 10.0, "最も近づくフレームが最深")
        self.assertLess(g["start"], 10.0)
        self.assertGreater(g["end"], 10.0)
        self.assertEqual(g["targets"][0][0], "|hand_ctl")
        self.assertEqual(g["frames"], core.frame_list(g["start"], g["end"]))

    def test_scan_can_be_cancelled(self):
        seen = []

        def progress(done, total, label):
            seen.append(done)
            return done < 3
        results, cancelled = core.scan(self.checker, core.frame_list(0, 20),
                                       self._set, progress)
        self.assertTrue(cancelled)
        self.assertEqual(sorted(results), [0.0, 1.0, 2.0])

    def test_group_splits_on_gap(self):
        hit = {"targets": [{"target": "a", "kind": "joint", "score": 1.0,
                            "depth": 0.1}]}
        miss = {"targets": []}
        results = {1.0: hit, 2.0: hit, 3.0: miss, 4.0: hit, 10.0: hit}
        groups = core.group_frames(results)
        self.assertEqual([(g["start"], g["end"]) for g in groups],
                         [(1.0, 2.0), (4.0, 4.0), (10.0, 10.0)])

    def test_group_ranks_targets_by_total_score(self):
        results = {
            1.0: {"targets": [{"target": "a", "score": 1.0, "depth": 0.9}]},
            2.0: {"targets": [{"target": "b", "score": 0.8, "depth": 0.1},
                              {"target": "a", "score": 0.1, "depth": 0.1}]},
            3.0: {"targets": [{"target": "b", "score": 0.8, "depth": 0.1}]},
        }
        g = core.group_frames(results)[0]
        self.assertEqual([t for t, _k in g["targets"]], ["b", "a"])
        self.assertEqual(g["worst_frame"], 1.0)


class TextTest(unittest.TestCase):

    def test_range_row(self):
        row = core.format_range_row({
            "start": 12.0, "end": 18.0, "frames": core.frame_list(12, 18),
            "worst_frame": 15.0, "depth": 0.83,
            "targets": [("|r|hand_ctl", "controller"), ("|r|x", "joint")],
        }, "cm")
        self.assertEqual(row, "12-18 (7f)  hand_ctl ほか 1  max 0.83cm @15")

    def test_single_frame_range_row(self):
        row = core.format_range_row({
            "start": 3.0, "end": 3.0, "frames": [3.0], "worst_frame": 3.0,
            "depth": 0.5, "targets": [("a", "joint")]}, "", lambda v: v * 2)
        self.assertEqual(row, "3 (1f)  a  max 1 @3")

    def test_hud_text(self):
        self.assertEqual(core.hud_text(None), "-- (not checked)")
        self.assertEqual(core.hud_text({"targets": []}), "OK")
        text = core.hud_text({"targets": [
            {"target": "|r|hand_ctl", "depth": 0.5},
            {"target": "|r|b", "depth": 0.1}]}, "cm")
        self.assertEqual(text, "HIT  hand_ctl  0.5cm  (+1)")
        self.assertTrue(all(ord(ch) < 128 for ch in text), "HUD は ASCII のみ")


if __name__ == "__main__":
    unittest.main()
