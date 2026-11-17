# -*- coding: utf-8 -*-
"""`core.py`（Maya 非依存）の回帰テスト。 実機と同じ結果が出る唯一の層。"""

from __future__ import annotations

import math
import unittest

import _bootstrap  # noqa: F401  （maya スタブの注入。 他の import より前）

from penetration_checker import core


def _sphere(radius=1.0, center=(0.0, 0.0, 0.0), calls=None):
    """球の最近接点と外向き法線を返す closest_fn。"""
    def closest(point):
        if calls is not None:
            calls.append(point)
        d = [point[i] - center[i] for i in range(3)]
        length = math.sqrt(sum(v * v for v in d)) or 1.0
        n = [v / length for v in d]
        return tuple(center[i] + n[i] * radius for i in range(3)), tuple(n)
    return closest


_UNIT_BOX = (-1.0, -1.0, -1.0, 1.0, 1.0, 1.0)


class BBoxTest(unittest.TestCase):

    def test_bbox_of_points(self):
        self.assertEqual(core.bbox_of_points([(0, 1, 2), (-1, 3, 0)]),
                         (-1, 1, 0, 0, 3, 2))

    def test_bbox_of_no_points_is_none(self):
        self.assertIsNone(core.bbox_of_points([]))

    def test_overlap(self):
        self.assertTrue(core.bbox_overlap(_UNIT_BOX, (0.5, 0.5, 0.5, 2, 2, 2)))
        self.assertTrue(core.bbox_overlap(_UNIT_BOX, (1, -1, -1, 2, 1, 1)),
                        "接しているだけでも候補に残す")
        self.assertFalse(core.bbox_overlap(_UNIT_BOX, (1.5, -1, -1, 2, 1, 1)))
        self.assertTrue(core.bbox_overlap(_UNIT_BOX, (1.5, -1, -1, 2, 1, 1),
                                          margin=0.6))
        self.assertFalse(core.bbox_overlap(None, _UNIT_BOX))

    def test_candidate_pairs_drops_far_apart(self):
        boxes = {
            "b": _UNIT_BOX,
            "a": (0.5, 0.5, 0.5, 2, 2, 2),
            "far": (10, 10, 10, 11, 11, 11),
        }
        self.assertEqual(core.candidate_pairs(boxes), [("a", "b")])


class InsideTest(unittest.TestCase):

    def test_depth_sign(self):
        normal = (0.0, 0.0, 2.0)   # 長さは問わない
        self.assertAlmostEqual(
            core.penetration_depth((0, 0, -0.5), (0, 0, 0), normal), 0.5)
        self.assertAlmostEqual(
            core.penetration_depth((0, 0, 0.5), (0, 0, 0), normal), -0.5)

    def test_depth_with_zero_normal_is_none(self):
        self.assertIsNone(core.penetration_depth((0, 0, 0), (0, 0, 0), (0, 0, 0)))

    def test_find_inside_vertices_on_sphere(self):
        points = [(0, 0, 2.0), (0, 0, 0.5), (0.9, 0, 0), (0, 0, 1.0)]
        hits = core.find_inside_vertices(points, _UNIT_BOX, _sphere())
        self.assertEqual([i for i, _d in hits], [1, 2], "深い順・面上は数えない")
        self.assertAlmostEqual(hits[0][1], 0.5)
        self.assertAlmostEqual(hits[1][1], 0.1)

    def test_tolerance_ignores_shallow(self):
        points = [(0, 0, 0.5), (0.95, 0, 0)]
        hits = core.find_inside_vertices(points, _UNIT_BOX, _sphere(), tolerance=0.1)
        self.assertEqual([i for i, _d in hits], [0])

    def test_points_outside_bbox_are_not_queried(self):
        calls = []
        core.find_inside_vertices([(5, 5, 5), (0, 0, 0.5)], _UNIT_BOX,
                                  _sphere(calls=calls))
        self.assertEqual(calls, [(0, 0, 0.5)])

    def test_failed_query_is_skipped(self):
        hits = core.find_inside_vertices([(0, 0, 0.5)], _UNIT_BOX, lambda _p: None)
        self.assertEqual(hits, [])


class ScoreTest(unittest.TestCase):

    def test_influence_scores_weight_by_depth(self):
        hits = [(0, 1.0), (1, 0.1)]
        weights = {0: {"hand": 1.0}, 1: {"spine": 1.0}}
        scores = core.influence_scores(hits, weights.get)
        ranked = core.rank_scores(scores)
        self.assertEqual(ranked[0][0], "hand")

    def test_many_shallow_can_outweigh_one_deep(self):
        hits = [(0, 0.5)] + [(i, 0.1) for i in range(1, 11)]
        weights = dict((i, {"spine": 1.0}) for i in range(1, 11))
        weights[0] = {"hand": 1.0}
        self.assertEqual(core.rank_scores(
            core.influence_scores(hits, weights.get))[0][0], "spine")

    def test_limit_and_zero_weight(self):
        hits = [(0, 1.0), (1, 1.0)]
        weights = {0: {"a": 0.0, "b": 1.0}, 1: {"c": 1.0}}
        scores = core.influence_scores(hits, weights.get, limit=1)
        self.assertEqual(list(scores), ["b"])

    def test_zero_depth_still_counts(self):
        scores = core.influence_scores([(0, 0.0)], lambda _i: {"a": 1.0})
        self.assertGreater(scores["a"], 0.0)

    def test_rank_ties_by_name(self):
        self.assertEqual(core.rank_scores({"b": 1.0, "a": 1.0, "c": 2.0}),
                         [("c", 2.0), ("a", 1.0), ("b", 1.0)])

    def test_aggregate_targets_merges_same_target(self):
        rows = core.aggregate_targets([
            {"target": "hand_ctl", "kind": "controller", "score": 1.0,
             "mesh": "hand", "other": "body", "count": 3, "depth": 0.2},
            {"target": "spine_ctl", "kind": "controller", "score": 1.5,
             "mesh": "belt", "other": "body", "count": 9, "depth": 0.1},
            {"target": "hand_ctl", "kind": "controller", "score": 1.0,
             "mesh": "hand", "other": "thigh", "count": 2, "depth": 0.4},
        ])
        self.assertEqual([r["target"] for r in rows], ["hand_ctl", "spine_ctl"])
        self.assertEqual(rows[0]["count"], 5)
        self.assertAlmostEqual(rows[0]["depth"], 0.4)
        self.assertEqual(rows[0]["pairs"], [("hand", "body"), ("hand", "thigh")])


class FindControllerTest(unittest.TestCase):

    def _run(self, start, sources, parents, ctrls, **kwargs):
        return core.find_controller(
            start, lambda n: sources.get(n, []), lambda n: parents.get(n),
            lambda n: n in ctrls, **kwargs)

    def test_constraint_to_ctrl(self):
        ctrl, path = self._run("jnt", {"jnt": ["cns"], "cns": ["ctl"]}, {}, {"ctl"})
        self.assertEqual(ctrl, "ctl")
        self.assertEqual(path, ["jnt", "cns", "ctl"])

    def test_matrix_driven_joint_reaches_ctrl_through_locator(self):
        # mGear 型: jnt <- decomposeMatrix <- matrixConstraint <- loc（ctl の子）。
        # ジョイントの親は scene.parent_of が None を返すので辿らない
        sources = {"jnt": ["dm"], "dm": ["mcns"], "mcns": ["loc"]}
        parents = {"loc": "ctl", "ctl": "global_ctl"}
        ctrl, path = self._run("jnt", sources, parents, {"ctl", "global_ctl"})
        self.assertEqual(ctrl, "ctl")
        self.assertEqual(path, ["jnt", "dm", "mcns", "loc", "ctl"])

    def test_shorter_path_wins(self):
        sources = {"jnt": ["cns"], "cns": ["ctl", "other"], "other": ["far_ctl"]}
        ctrl, _ = self._run("jnt", sources, {}, {"ctl", "far_ctl"})
        self.assertEqual(ctrl, "ctl")

    def test_non_ctrl_transform_climbs_to_ancestor_ctrl(self):
        sources = {"jnt": ["dm"], "dm": ["loc"]}
        parents = {"loc": "npo", "npo": "fk_ctl"}
        ctrl, path = self._run("jnt", sources, parents, {"fk_ctl"})
        self.assertEqual(ctrl, "fk_ctl")
        self.assertEqual(path, ["jnt", "dm", "loc", "npo", "fk_ctl"])

    def test_not_found(self):
        self.assertEqual(self._run("jnt", {"jnt": ["anim"]}, {}, set()),
                         (None, ["jnt"]))

    def test_start_is_ctrl(self):
        self.assertEqual(self._run("ctl", {}, {}, {"ctl"}), ("ctl", ["ctl"]))

    def test_cycle_terminates(self):
        sources = {"a": ["b"], "b": ["a"]}
        self.assertEqual(self._run("a", sources, {}, set()), (None, ["a"]))

    def test_max_steps(self):
        sources = dict(("n%d" % i, ["n%d" % (i + 1)]) for i in range(20))
        ctrl, _ = self._run("n0", sources, {}, {"n15"}, max_steps=5)
        self.assertIsNone(ctrl)


class FormatTest(unittest.TestCase):

    def test_short_name(self):
        self.assertEqual(core.short_name("|grp|ns:mesh"), "ns:mesh")

    def test_row(self):
        row = core.format_target_row({
            "target": "|rig|arm_L_ctl", "kind": "controller", "count": 12,
            "depth": 0.83, "pairs": [("|g|hand", "|g|body"), ("|g|hand", "|g|leg")],
        }, "cm")
        self.assertEqual(row, "[CTRL] arm_L_ctl   12 vtx  max 0.83cm  (hand > body ほか 1 組)")

    def test_format_frame(self):
        self.assertEqual(core.format_frame(12.0), "12")
        self.assertEqual(core.format_frame(12.5), "12.5")
        self.assertEqual(core.format_frame(None), "None")


if __name__ == "__main__":
    unittest.main()
