# -*- coding: utf-8 -*-
"""`core.py`（Maya 非依存）の判定ロジック。"""

from __future__ import annotations

import unittest

import _bootstrap  # noqa: F401

from deselect_static import core


class HasChangeTest(unittest.TestCase):
    def test_constant_values_are_static(self):
        self.assertFalse(core.has_change([1.0, 1.0, 1.0]))

    def test_different_values_change(self):
        self.assertTrue(core.has_change([0.0, 0.0, 0.5]))

    def test_zero_or_one_key_is_static(self):
        self.assertFalse(core.has_change([]))
        self.assertFalse(core.has_change(None))
        self.assertFalse(core.has_change([3.0]))

    def test_within_tolerance_is_static(self):
        self.assertFalse(core.has_change([1.0, 1.00005], tolerance=1e-4))

    def test_beyond_tolerance_changes(self):
        self.assertTrue(core.has_change([1.0, 1.0002], tolerance=1e-4))

    def test_uses_whole_range_not_neighbor_steps(self):
        # 隣同士の差はどれも許容内でも、全体では漂っている
        values = [i * 0.00005 for i in range(10)]
        self.assertTrue(core.has_change(values, tolerance=1e-4))

    def test_zero_tolerance_means_exact(self):
        self.assertFalse(core.has_change([2.0, 2.0], tolerance=0.0))
        self.assertTrue(core.has_change([2.0, 2.0000001], tolerance=0.0))


class NormalizeToleranceTest(unittest.TestCase):
    def test_passes_through_positive(self):
        self.assertEqual(core.normalize_tolerance(0.01), 0.01)

    def test_negative_becomes_absolute(self):
        self.assertEqual(core.normalize_tolerance(-0.5), 0.5)

    def test_unreadable_falls_back_to_default(self):
        self.assertEqual(core.normalize_tolerance(None), core.DEFAULT_TOLERANCE)
        self.assertEqual(core.normalize_tolerance("abc"), core.DEFAULT_TOLERANCE)
        self.assertEqual(core.normalize_tolerance(float("nan")),
                         core.DEFAULT_TOLERANCE)

    def test_string_number_is_read(self):
        self.assertEqual(core.normalize_tolerance("0.001"), 0.001)


class ChooseSourceTest(unittest.TestCase):
    def test_no_key_selection_uses_all_keys(self):
        self.assertEqual(core.choose_source({"a": ["a_tx"]}, []),
                         core.SOURCE_ALL_KEYS)

    def test_key_selection_on_selected_object(self):
        self.assertEqual(core.choose_source({"a": ["a_tx", "a_ty"]}, ["a_ty"]),
                         core.SOURCE_SELECTED_KEYS)

    def test_key_selection_unrelated_falls_back(self):
        # 選択オブジェクトのカーブと重ならないキー選択では全部外さない
        self.assertEqual(core.choose_source({"a": ["a_tx"]}, ["b_tx"]),
                         core.SOURCE_ALL_KEYS)


class SplitByChangeTest(unittest.TestCase):
    def test_splits_and_keeps_order(self):
        values = {
            "c": [[0.0, 1.0]],
            "a": [[1.0, 1.0], [0.0, 2.0]],   # 1 本でも動いていれば changed
            "b": [[5.0, 5.0], [3.0, 3.0]],
        }
        changed, static = core.split_by_change(["c", "a", "b"], values)
        self.assertEqual(changed, ["c", "a"])
        self.assertEqual(static, ["b"])

    def test_object_without_curves_is_static(self):
        changed, static = core.split_by_change(["a", "b"], {"a": [[0, 1]]})
        self.assertEqual(changed, ["a"])
        self.assertEqual(static, ["b"])

    def test_duplicates_are_reported_once(self):
        changed, static = core.split_by_change(["a", "a"], {"a": [[0, 1]]})
        self.assertEqual(changed, ["a"])
        self.assertEqual(static, [])

    def test_tolerance_is_applied(self):
        values = {"a": [[0.0, 0.01]]}
        self.assertEqual(core.split_by_change(["a"], values, 0.1), ([], ["a"]))
        self.assertEqual(core.split_by_change(["a"], values, 0.001),
                         (["a"], []))


class SummaryMessageTest(unittest.TestCase):
    def test_mentions_counts_and_source(self):
        msg = core.summary_message(["a", "b"], ["c"], core.SOURCE_SELECTED_KEYS)
        self.assertIn("選択キー", msg)
        self.assertIn("2", msg)
        self.assertIn("1", msg)
        msg = core.summary_message([], [], core.SOURCE_ALL_KEYS)
        self.assertIn("全キー", msg)


if __name__ == "__main__":
    unittest.main()
