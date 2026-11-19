# -*- coding: utf-8 -*-
"""`core`（Steffen 法と単位変換）の回帰テスト。 実機と同じ結果が出る唯一の層。"""

from __future__ import annotations

import math
import unittest

import _bootstrap  # noqa: F401

from tangent_fixer import core


def _catmull_rom(times, values):
    """比較用: Maya の Spline に近い「前後のキーを結ぶ傾き」。"""
    n = len(times)
    out = [0.0] * n
    for i in range(1, n - 1):
        out[i] = (values[i + 1] - values[i - 1]) / (times[i + 1] - times[i - 1])
    return out


class SlopeCase(unittest.TestCase):

    def test_extremes_are_flat(self):
        slopes = core.compute_slopes([0, 10, 20, 30], [0, 10, -5, 3])
        self.assertEqual(slopes[1], 0.0)
        self.assertEqual(slopes[2], 0.0)

    def test_plateau_is_flat(self):
        slopes = core.compute_slopes([0, 10, 20, 30], [0, 5, 5, 10])
        self.assertEqual(slopes[1], 0.0)
        self.assertEqual(slopes[2], 0.0)

    def test_key_on_a_line_keeps_the_line(self):
        slopes = core.compute_slopes([0, 4, 10, 30], [0, 2, 5, 15])
        self.assertAlmostEqual(slopes[1], 0.5)
        self.assertAlmostEqual(slopes[2], 0.5)

    def test_middle_key_between_max_and_min_is_smooth(self):
        """Auto の課題: 山と谷の間のキー。 区間長で重み付けした平均を使う。"""
        times = [0, 10, 14, 30]
        values = [10.0, 6.0, 4.0, 0.0]
        slopes = core.compute_slopes(times, values)
        s0, s1 = -0.4, -0.5
        p = (s0 * 4 + s1 * 10) / 14.0
        self.assertAlmostEqual(slopes[1], p)
        self.assertLess(slopes[1], 0.0)

    def test_no_overshoot_where_spline_overshoots(self):
        """Spline の課題: 急に止まる動きで、キーに無い山ができる。"""
        times = [0, 10, 12, 30]
        values = [0.0, 0.0, 10.0, 10.0]
        spline = _catmull_rom(times, values)
        self.assertGreater(core.max_overshoot(times, values, spline), 0.1)

        fixed = core.compute_slopes(times, values)
        self.assertLessEqual(core.max_overshoot(times, values, fixed), 1e-9)

    def test_never_overshoots_on_random_curves(self):
        import random
        rng = random.Random(1234)
        for _ in range(300):
            n = rng.randint(2, 9)
            times = sorted(rng.sample(range(0, 200), n))
            values = [rng.uniform(-50, 50) for _ in range(n)]
            for mode in core.END_MODES:
                for method in (core.METHOD_SMOOTH, core.METHOD_STRICT):
                    slopes = core.compute_slopes(times, values, end_mode=mode,
                                                 method=method)
                    self.assertLessEqual(
                        core.max_overshoot(times, values, slopes), 1e-7,
                        "overshoot: %r %r %s %s"
                        % (times, values, mode, method))

    def test_tangent_method_is_exact_parabola_tangent(self):
        """v0.2.0: 「タンジェントが接線になってほしい」。 頭打ちしない。"""
        times = [0, 10, 20, 30]
        values = [0.0, 1.0, 9.0, 10.0]
        slopes = core.compute_slopes(times, values,
                                     method=core.METHOD_TANGENT)
        self.assertAlmostEqual(slopes[1],
                               core.parabola_slope(0.1, 0.8, 10, 10))
        self.assertAlmostEqual(slopes[2],
                               core.parabola_slope(0.8, 0.1, 10, 10))

    def test_smooth_keeps_tangent_where_strict_flattens_it(self):
        """片側が緩い区間: 原式（2 倍）は接線を寝かせるが、smooth（3 倍）は保つ。"""
        times = [0, 10, 20]
        values = [0.0, 2.0, 10.0]          # s = 0.2, 0.8 → 接線 0.5
        tangent = core.parabola_slope(0.2, 0.8, 10, 10)
        smooth = core.compute_slopes(times, values, method=core.METHOD_SMOOTH)
        strict = core.compute_slopes(times, values, method=core.METHOD_STRICT)
        self.assertAlmostEqual(smooth[1], tangent)
        self.assertLess(strict[1], tangent)

    def test_smooth_clamps_only_when_tangent_would_overshoot(self):
        times = [0, 10, 20]
        values = [0.0, 0.5, 10.0]          # s = 0.05, 0.95 → 接線 0.5 > 3×0.05
        tangent = core.compute_slopes(times, values,
                                      method=core.METHOD_TANGENT)
        self.assertGreater(core.max_overshoot(times, values, tangent), 0.0)
        smooth = core.compute_slopes(times, values, method=core.METHOD_SMOOTH)
        self.assertAlmostEqual(smooth[1], 0.15)
        self.assertLessEqual(core.max_overshoot(times, values, smooth), 1e-9)

    def test_tangent_method_still_flattens_extremes(self):
        slopes = core.compute_slopes([0, 10, 20, 30], [0, 10, -5, 3],
                                     method=core.METHOD_TANGENT)
        self.assertEqual(slopes[1:3], [0.0, 0.0])

    def test_end_modes(self):
        times, values = [0, 10, 20], [0.0, 10.0, 15.0]
        flat = core.compute_slopes(times, values, end_mode=core.END_FLAT)
        self.assertEqual((flat[0], flat[-1]), (0.0, 0.0))
        nat = core.compute_slopes(times, values, end_mode=core.END_NATURAL)
        self.assertGreater(nat[0], 0.0)
        self.assertGreater(nat[-1], 0.0)
        self.assertLessEqual(nat[0], 2.0)    # 隣の区間の傾き 1.0 の 2 倍まで

    def test_natural_two_keys_is_linear(self):
        self.assertEqual(core.compute_slopes([0, 10], [0, 5], core.END_NATURAL),
                         [0.5, 0.5])

    def test_degenerate_inputs(self):
        self.assertEqual(core.compute_slopes([], []), [])
        self.assertEqual(core.compute_slopes([5], [1.0]), [0.0])
        with self.assertRaises(ValueError):
            core.compute_slopes([0, 0], [1, 2])
        with self.assertRaises(ValueError):
            core.compute_slopes([0, 1], [1])
        with self.assertRaises(ValueError):
            core.compute_slopes([0, 1], [1, 2], end_mode="spline")
        with self.assertRaises(ValueError):
            core.compute_slopes([0, 1], [1, 2], method="spline")

    def test_plan_keeps_neighbours_but_returns_targets_only(self):
        times, values = [0, 10, 20, 30], [0.0, 4.0, 6.0, 10.0]
        whole = core.compute_slopes(times, values)
        plan = core.plan_curve(times, values, [2, 2, 9])
        self.assertEqual(plan, [(2, whole[2])])
        self.assertEqual(len(core.plan_curve(times, values)), 4)


class UnitCase(unittest.TestCase):

    def test_fps_from_time_unit(self):
        self.assertEqual(core.fps_from_time_unit("film"), 24.0)
        self.assertEqual(core.fps_from_time_unit("ntsc"), 30.0)
        self.assertAlmostEqual(core.fps_from_time_unit("29.97fps"), 29.97, 2)
        self.assertEqual(core.fps_from_time_unit("90fps"), 90.0)
        self.assertIsNone(core.fps_from_time_unit("banana"))
        self.assertIsNone(core.fps_from_time_unit(None))

    def test_measurement_roundtrip(self):
        for scale in (1.0, 24.0, 24.0 * math.pi / 180.0):
            slope = 0.37
            angle = math.degrees(math.atan(slope * scale))
            self.assertAlmostEqual(core.scale_from_measurement(angle, slope),
                                   scale)
            self.assertAlmostEqual(core.slope_to_angle(slope, scale), angle)

    def test_measurement_rejects_unusable(self):
        self.assertIsNone(core.scale_from_measurement(10.0, 0.0))
        self.assertIsNone(core.scale_from_measurement(90.0, 1.0))
        self.assertIsNone(core.scale_from_measurement(-10.0, 1.0))  # 符号違い

    def test_pick_calibration_segment(self):
        seg = [0.0, 2.0, -5.0]          # 4 キー
        self.assertEqual(core.pick_calibration_segment(seg, [1]), (1, "out"))
        self.assertEqual(core.pick_calibration_segment(seg, [3]), (3, "in"))
        self.assertEqual(core.pick_calibration_segment(seg, [2]), (2, "out"))
        self.assertIsNone(core.pick_calibration_segment([0.0, 0.0], [0, 1]))
        self.assertEqual(core.segment_for(3, "in"), 2)
        self.assertEqual(core.segment_for(1, "out"), 1)


if __name__ == "__main__":
    unittest.main()
