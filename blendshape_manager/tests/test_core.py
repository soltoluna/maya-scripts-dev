# -*- coding: utf-8 -*-
"""`core.py`（Maya 非依存）の回帰テスト。 実機と同じ結果が出る唯一の層。"""

from __future__ import annotations

import unittest

import _bootstrap  # noqa: F401  （maya スタブの注入。 他の import より前）

from blendshape_manager import core


class NameCase(unittest.TestCase):

    def test_short_name(self):
        self.assertEqual(core.short_name("|grp|ns:body"), "body")
        self.assertEqual(core.short_name("body"), "body")

    def test_default_node_name(self):
        self.assertEqual(core.default_node_name("|grp|ns:body"), "body_BS")
        self.assertEqual(core.default_node_name("1mesh"), "_1mesh_BS")

    def test_validate_target_name(self):
        self.assertIsNone(core.validate_target_name("smile", ["blink"]))
        self.assertIsNotNone(core.validate_target_name("smile", ["smile"]))
        self.assertIsNotNone(core.validate_target_name("2smile", []))
        self.assertIsNotNone(core.validate_target_name("a b", []))
        self.assertIsNotNone(core.validate_target_name("envelope", []))
        self.assertIsNotNone(core.validate_target_name("", []))

    def test_split_create_selection_uses_last_as_base(self):
        self.assertEqual(core.split_create_selection(["a", "b", "base"]),
                         (["a", "b"], "base"))
        self.assertEqual(core.split_create_selection(["base"]), ([], "base"))
        with self.assertRaises(ValueError):
            core.split_create_selection([])


class TargetListCase(unittest.TestCase):

    def test_parse_alias_list(self):
        flat = ["smile", "weight[0]", "blink", "weight[2]", "other", "envelope"]
        self.assertEqual(core.parse_alias_list(flat), {0: "smile", 2: "blink"})
        self.assertEqual(core.parse_alias_list(None), {})

    def test_target_entries_fills_missing_alias(self):
        self.assertEqual(core.target_entries([0, 1, 3], {0: "a", 3: "c"}),
                         [(0, "a"), (1, "weight[1]"), (3, "c")])

    def test_next_free_index(self):
        self.assertEqual(core.next_free_index([]), 0)
        self.assertEqual(core.next_free_index([0, 1, 5]), 6)

    def test_topology_mismatches(self):
        self.assertEqual(core.topology_mismatches(10, {"a": 10, "b": 9, "c": 11}),
                         ["b", "c"])

    def test_filter_entries(self):
        entries = [(0, "L_smile"), (1, "R_smile"), (2, "jawOpen")]
        self.assertEqual(core.filter_entries(entries, ""), entries)
        self.assertEqual(core.filter_entries(entries, "SMILE"), entries[:2])
        self.assertEqual(core.filter_entries(entries, "l_ jaw"),
                         [(0, "L_smile"), (2, "jawOpen")])


class RenameCase(unittest.TestCase):

    def test_batch_rename(self):
        self.assertEqual(core.batch_rename(["L_smile", "L_blink"], prefix="fc_",
                                           suffix="_t", search="L_", replace="R_"),
                         ["fc_R_smile_t", "fc_R_blink_t"])

    def test_plan_simple(self):
        steps, errors = core.plan_renames([(0, "a"), (1, "b")], {0: "c"})
        self.assertEqual(errors, [])
        self.assertEqual(steps, [(0, "c")])

    def test_plan_unchanged_is_empty(self):
        self.assertEqual(core.plan_renames([(0, "a")], {0: "a"}), ([], []))

    def test_plan_rejects_duplicate_and_invalid(self):
        _steps, errors = core.plan_renames([(0, "a"), (1, "b")], {0: "b"})
        self.assertTrue(errors)
        _steps, errors = core.plan_renames([(0, "a")], {0: "1a"})
        self.assertTrue(errors)
        _steps, errors = core.plan_renames([(0, "a"), (1, "b")], {0: "x", 1: "x"})
        self.assertTrue(errors)

    def _simulate(self, entries, steps):
        names = dict(entries)
        for index, name in steps:
            self.assertNotIn(name, [n for i, n in names.items() if i != index],
                             "途中で同名ができる: %r" % (steps,))
            names[index] = name
        return names

    def test_plan_swap_goes_through_temp_names(self):
        entries = [(0, "L_smile"), (1, "R_smile")]
        steps, errors = core.plan_renames(entries, {0: "R_smile", 1: "L_smile"})
        self.assertEqual(errors, [])
        self.assertEqual(self._simulate(entries, steps), {0: "R_smile", 1: "L_smile"})

    def test_plan_chain(self):
        entries = [(0, "a"), (1, "b")]
        steps, errors = core.plan_renames(entries, {0: "b", 1: "c"})
        self.assertEqual(errors, [])
        self.assertEqual(self._simulate(entries, steps), {0: "b", 1: "c"})


class InbetweenCase(unittest.TestCase):

    def test_conversion(self):
        self.assertEqual(core.weight_to_item_index(0.5), 5500)
        self.assertEqual(core.weight_to_item_index(1.0), 6000)
        self.assertAlmostEqual(core.item_index_to_weight(5250), 0.25)

    def test_inbetween_weights_exclude_full(self):
        self.assertEqual(core.inbetween_weights([6000, 5500, 5250]), [0.25, 0.5])
        self.assertEqual(core.inbetween_weights(None), [])

    def test_validate(self):
        self.assertIsNone(core.validate_inbetween_weight(0.5, [6000]))
        self.assertIsNotNone(core.validate_inbetween_weight(0.5, [6000, 5500]))
        self.assertIsNotNone(core.validate_inbetween_weight(0.0, [6000]))
        self.assertIsNotNone(core.validate_inbetween_weight(1.0, [6000]))
        self.assertIsNotNone(core.validate_inbetween_weight("x", [6000]))


class MirrorNameCase(unittest.TestCase):

    def test_prefix_suffix_word(self):
        self.assertEqual(core.mirror_name("L_smile"), ("R_smile", True))
        self.assertEqual(core.mirror_name("R_smile"), ("L_smile", True))
        self.assertEqual(core.mirror_name("browUp_L"), ("browUp_R", True))
        self.assertEqual(core.mirror_name("eyeBlinkLeft"), ("eyeBlinkRight", True))
        self.assertEqual(core.mirror_name("jawOpen"), ("jawOpen_mirror", False))

    def test_plan_mirror_skips_pair(self):
        self.assertEqual(core.plan_mirror(["L_smile", "R_smile", "L_blink"]),
                         (["L_smile", "L_blink"], ["R_smile"]))


class MirrorShapeCase(unittest.TestCase):
    # 左右対称のベース: 0 と 1 が組、2 は中央、3 は相手がいない
    BASE = [(1.0, 0.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (5.0, 5.0, 5.0)]

    def test_build_mirror_map(self):
        self.assertEqual(core.build_mirror_map(self.BASE, "x", 1e-3), [1, 0, 2, -1])

    def test_build_mirror_map_tolerance(self):
        base = [(1.0, 0.0, 0.0), (-1.0005, 0.0, 0.0)]
        self.assertEqual(core.build_mirror_map(base, "x", 1e-3), [1, 0])
        self.assertEqual(core.build_mirror_map(base, "x", 1e-4), [-1, -1])

    def test_build_mirror_map_other_axis(self):
        base = [(0.0, 2.0, 0.0), (0.0, -2.0, 0.0)]
        self.assertEqual(core.build_mirror_map(base, "y"), [1, 0])

    def test_bad_args(self):
        with self.assertRaises(ValueError):
            core.build_mirror_map(self.BASE, "w")
        with self.assertRaises(ValueError):
            core.build_mirror_map(self.BASE, "x", 0)

    def test_mirror_shape_moves_left_delta_to_right(self):
        # 左（+x）の頂点 0 だけ上に動いたシェイプ
        target = [(1.0, 0.5, 0.0), (-1.0, 0.0, 0.0), (0.2, 1.0, 0.0), (5.0, 6.0, 5.0)]
        mm = core.build_mirror_map(self.BASE, "x")
        points, missing = core.mirror_shape(self.BASE, target, mm, "x")
        self.assertEqual(points[0], [1.0, 0.0, 0.0])      # 左は元に戻る
        self.assertEqual(points[1], [-1.0, 0.5, 0.0])     # 右が上に動く
        self.assertEqual(points[2], [-0.2, 1.0, 0.0])     # 中央は x だけ反転
        self.assertEqual(points[3], [5.0, 5.0, 5.0])      # 相手なし → 動かさない
        self.assertEqual(missing, 1)

    def test_mirror_twice_is_identity(self):
        target = [(1.2, 0.5, 0.1), (-1.0, 0.0, 0.0), (0.2, 1.0, 0.0), (5.0, 5.0, 5.0)]
        mm = core.build_mirror_map(self.BASE, "x")
        once, _ = core.mirror_shape(self.BASE, target, mm, "x")
        twice, _ = core.mirror_shape(self.BASE, once, mm, "x")
        for got, want in zip(twice[:3], target[:3]):
            for a, b in zip(got, want):
                self.assertAlmostEqual(a, b)

    def test_mirror_shape_length_mismatch(self):
        with self.assertRaises(ValueError):
            core.mirror_shape(self.BASE, self.BASE[:2], [0, 1], "x")

    def test_mirror_map_scales_linearly_enough(self):
        # 2 万頂点でも数秒かからない（格子分割が効いているか）
        base = []
        for i in range(100):
            for j in range(100):
                base.append((i * 0.1 + 0.05, j * 0.1, 0.0))
                base.append((-(i * 0.1 + 0.05), j * 0.1, 0.0))
        mm = core.build_mirror_map(base, "x", 1e-4)
        self.assertEqual(mm[:4], [1, 0, 3, 2])
        self.assertNotIn(-1, mm)


if __name__ == "__main__":
    unittest.main()
