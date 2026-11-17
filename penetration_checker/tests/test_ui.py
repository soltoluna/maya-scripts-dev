# -*- coding: utf-8 -*-
"""`ui.py` の配線テスト。 `scene`（OpenMaya を使う層）は偽物に差し替える。

スタブの `cmds` は「呼ばれたこと」しか知らないので、ここで確かめるのは
「結果が一覧・HUD・選択に流れるか」「時間と進捗表示を必ず戻すか」
「timeChanged で例外を上げないか」だけ。
"""

from __future__ import annotations

import unittest

import _bootstrap

tool = _bootstrap.import_tool()
ui = tool.ui
core = tool.core


def _frame_result(target="|rig|hand_ctl", depth=0.5):
    if target is None:
        return {"hits": [], "targets": [], "pairs": 1, "cancelled": False}
    return {
        "hits": [{"mesh": "|g|hand", "other": "|g|body",
                  "vertices": [(4, depth), (7, 0.1)]}],
        "targets": [{"target": target, "kind": "controller", "score": 2.0,
                     "count": 2, "depth": depth,
                     "pairs": [("|g|hand", "|g|body")]}],
        "pairs": 1, "cancelled": False,
    }


class _FakeChecker(object):

    def __init__(self, scene):
        self.scene = scene
        self.warnings = []
        self.calls = 0

    def check_frame(self, progress=None):
        self.calls += 1
        if self.scene.fail:
            raise RuntimeError("mesh deleted")
        return self.scene.result_at(self.scene.frame)


class _FakeScene(object):

    def __init__(self):
        self.frame = 1.0
        self.frames_set = []
        self.playing = False
        self.fail = False
        self.made = []
        self.range = (1.0, 10.0, "再生範囲")

    def result_at(self, frame):
        return _frame_result() if 4 <= frame <= 6 else _frame_result(None)

    def make_checker(self, nodes, **kwargs):
        self.made.append((list(nodes), kwargs))
        return _FakeChecker(self), list(nodes), []

    def current_frame(self):
        return self.frame

    def set_frame(self, frame):
        self.frames_set.append(frame)
        self.frame = frame

    def is_playing(self):
        return self.playing

    def time_range(self):
        return self.range

    def ui_unit(self):
        return "cm"

    def to_ui_distance(self, value):
        return value


class UiFlowTest(unittest.TestCase):

    def setUp(self):
        _bootstrap.reset_registry()
        del ui._STATE["targets"][:]
        self.fake = _FakeScene()
        self._orig = ui._scene
        ui._scene = lambda: self.fake
        # スタブの objExists は常に False。 結果のノードは「ある」ことにする
        ui.cmds.objExists = lambda name=None, **k: True
        ui.show()

    def tearDown(self):
        ui._scene = self._orig
        for name in ("objExists", "headsUpDisplay"):
            if name in vars(ui.cmds):
                delattr(ui.cmds, name)
        _bootstrap.WINDOWS.pop(ui.WINDOW, None)

    # -- 補助 ----------------------------------------------------------------

    def _appended(self, ctrl):
        return [c[2]["append"] for c in _bootstrap.CALLS
                if c[0] == "textScrollList" and c[1] and c[1][0] == ui._CTRL[ctrl]
                and "append" in c[2]]

    def _hud_labels(self):
        return [c[2]["label"] for c in _bootstrap.CALLS
                if c[0] == "headsUpDisplay" and c[2].get("edit")]

    def _end_progress_count(self):
        return len([c for c in _bootstrap.CALLS
                    if c[0] == "progressWindow" and c[2].get("endProgress")])

    def _set_check(self, name, value):
        _bootstrap.CONTROLS[ui._CTRL[name]]["value"] = value

    # -- 対象 ----------------------------------------------------------------

    def test_without_targets_or_selection_warns(self):
        ui._on_check_current()
        self.assertEqual(self.fake.made, [])
        self.assertTrue(_bootstrap.MESSAGES)

    def test_selection_is_used_when_list_is_empty(self):
        _bootstrap.set_selection(["|g|hand", "|g|body"])
        ui._on_check_current()
        self.assertEqual(self.fake.made[0][0], ["|g|hand", "|g|body"])

    def test_registered_targets_take_priority(self):
        _bootstrap.set_selection(["|chara_grp"])
        ui._on_add()
        _bootstrap.set_selection(["|other"])
        ui._on_check_current()
        self.assertEqual(self.fake.made[0][0], ["|chara_grp"])

    def test_changing_conditions_rebuilds_checker_and_clears_results(self):
        _bootstrap.set_selection(["|g|hand", "|g|body"])
        self.fake.frame = 5.0
        ui._on_check_current()
        self.assertTrue(ui._STATE["results"])
        ui._on_condition_changed()
        self.assertIsNone(ui._STATE["checker"])
        self.assertEqual(ui._STATE["results"], {})

    def test_remove_and_clear_targets(self):
        _bootstrap.set_selection(["|a", "|b"])
        ui._on_add()
        _bootstrap.CONTROLS[ui._CTRL["targets"]]["selectIndexedItem"] = [1]
        ui._on_remove()
        self.assertEqual(ui._STATE["targets"], ["|b"])
        ui._on_clear_targets()
        self.assertEqual(ui._STATE["targets"], [])

    # -- 現在のフレーム ------------------------------------------------------

    def test_current_frame_selects_top_target(self):
        _bootstrap.set_selection(["|g|hand", "|g|body"])
        self.fake.frame = 5.0
        ui._on_check_current()
        self.assertEqual(_bootstrap._SELECTION, ["|rig|hand_ctl"])
        self.assertTrue(self._appended("detail")[0].startswith("[CTRL] hand_ctl"))
        self.assertEqual(self._end_progress_count(), 1)
        self.assertTrue(self._hud_labels()[-1].startswith("Penetration: HIT"))

    def test_progress_window_is_closed_on_error(self):
        _bootstrap.set_selection(["|g|hand", "|g|body"])
        self.fake.fail = True
        with self.assertRaises(RuntimeError):
            ui._on_check_current()
        self.assertEqual(self._end_progress_count(), 1)

    # -- スキャン ------------------------------------------------------------

    def test_scan_covers_range_and_restores_time(self):
        _bootstrap.set_selection(["|g|hand", "|g|body"])
        self.fake.frame = 2.0
        ui._on_scan()
        self.assertEqual(self.fake.frames_set[:-1], core.frame_list(1, 10))
        self.assertEqual(self.fake.frames_set[-1], 2.0, "元のフレームに戻す")
        self.assertEqual(self.fake.frame, 2.0)
        self.assertEqual(len(ui._STATE["groups"]), 1)
        self.assertTrue(self._appended("ranges")[-1].startswith("4-6 (3f)"))
        self.assertFalse(ui._STATE["busy"])
        self.assertEqual(self._end_progress_count(), 1)

    def test_scan_restores_time_on_error(self):
        _bootstrap.set_selection(["|g|hand", "|g|body"])
        self.fake.frame = 2.0
        self.fake.fail = True
        with self.assertRaises(RuntimeError):
            ui._on_scan()
        self.assertEqual(self.fake.frame, 2.0)
        self.assertFalse(ui._STATE["busy"])
        self.assertEqual(self._end_progress_count(), 1)

    def test_range_click_jumps_to_worst_frame_and_selects(self):
        _bootstrap.set_selection(["|g|hand", "|g|body"])
        ui._on_scan()
        _bootstrap.CONTROLS[ui._CTRL["ranges"]]["selectIndexedItem"] = [1]
        ui._on_range_picked()
        self.assertEqual(self.fake.frame, 4.0)
        self.assertEqual(_bootstrap._SELECTION, ["|rig|hand_ctl"])

    # -- 時間の変化 ----------------------------------------------------------

    def test_time_changed_reads_cache_when_not_live(self):
        _bootstrap.set_selection(["|g|hand", "|g|body"])
        ui._on_scan()
        checker = ui._STATE["checker"]
        calls = checker.calls
        self.fake.playing = True
        self.fake.frame = 5.0
        ui._on_time_changed()
        self.assertEqual(checker.calls, calls, "ライブでなければ調べ直さない")
        self.assertTrue(self._hud_labels()[-1].startswith("Penetration: HIT"))
        self.fake.frame = 8.0
        ui._on_time_changed()
        self.assertEqual(self._hud_labels()[-1], "Penetration: OK")

    def test_live_checks_each_time_change(self):
        _bootstrap.set_selection(["|g|hand", "|g|body"])
        self._set_check("live", True)
        self.fake.playing = True
        for frame in (3.0, 4.0, 5.0):
            self.fake.frame = frame
            ui._on_time_changed()
        self.assertEqual(sorted(ui._STATE["results"]), [3.0, 4.0, 5.0])
        # 再生中は一覧を作り直さない（HUD だけ）
        self.assertEqual(self._appended("ranges"), [])
        self.fake.playing = False
        ui._on_playback_stopped()
        self.assertEqual(len(self._appended("ranges")), 1)

    def test_live_failure_turns_live_off_without_raising(self):
        _bootstrap.set_selection(["|g|hand", "|g|body"])
        self._set_check("live", True)
        self.fake.fail = True
        ui._on_time_changed()       # 例外を上げない
        self.assertFalse(_bootstrap.CONTROLS[ui._CTRL["live"]]["value"])
        self.assertTrue(_bootstrap.MESSAGES)

    def test_time_changed_is_ignored_while_scanning(self):
        _bootstrap.set_selection(["|g|hand", "|g|body"])
        self._set_check("live", True)
        ui._STATE["busy"] = True
        try:
            ui._on_time_changed()
        finally:
            ui._STATE["busy"] = False
        self.assertEqual(self.fake.made, [])

    # -- 後片付け ------------------------------------------------------------

    def test_jobs_are_installed(self):
        jobs = list(_bootstrap.SCRIPT_JOBS.values())
        events = [j["event"][0] for j in jobs if "event" in j]
        self.assertIn("timeChanged", events)
        for job in jobs:
            if "event" in job or "conditionFalse" in job:
                self.assertEqual(job.get("parent"), ui.WINDOW,
                                 "ウィンドウと一緒に消えるよう親子付けする")
        self.assertTrue(any("uiDeleted" in j for j in jobs))

    def test_window_close_removes_hud(self):
        calls = []

        def hud(*args, **kwargs):
            calls.append(kwargs)
            return True if kwargs.get("exists") else None
        ui.cmds.headsUpDisplay = hud
        ui._on_window_closed()
        self.assertTrue(any(k.get("remove") for k in calls))

    def test_scene_change_resets(self):
        _bootstrap.set_selection(["|a", "|b"])
        ui._on_add()
        ui._on_check_current()
        ui._on_scene_changed()
        self.assertEqual(ui._STATE["targets"], [])
        self.assertIsNone(ui._STATE["checker"])
        self.assertEqual(ui._STATE["results"], {})

    def test_select_vertices_of_picked_detail(self):
        _bootstrap.set_selection(["|g|hand", "|g|body"])
        self.fake.frame = 5.0
        ui._on_check_current()
        _bootstrap.CONTROLS[ui._CTRL["detail"]]["selectIndexedItem"] = [1]
        ui._on_select_vertices()
        self.assertEqual(_bootstrap._SELECTION, ["|g|hand.vtx[4]", "|g|hand.vtx[7]"])

    def test_options_are_namespaced(self):
        ui._on_condition_changed()
        self.assertTrue(_bootstrap.OPTION_VARS)
        for key in _bootstrap.OPTION_VARS:
            self.assertTrue(key.startswith("ntk_penetration_checker_"), key)


if __name__ == "__main__":
    unittest.main()
