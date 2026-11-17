# -*- coding: utf-8 -*-
"""`ui.py` の配線テスト。 `scene`（OpenMaya を使う層）は偽物に差し替える。

スタブの `cmds` は「呼ばれたこと」しか知らないので、ここで確かめるのは
「scene.check の結果が一覧と選択に流れるか」「後片付けが対称か」だけ。
"""

from __future__ import annotations

import unittest

import _bootstrap

tool = _bootstrap.import_tool()
ui = tool.ui


class _FakeScene(object):

    def __init__(self, result):
        self.result = result
        self.calls = []

    def check(self, nodes, **kwargs):
        self.calls.append((list(nodes), kwargs))
        return self.result

    def ui_unit(self):
        return "cm"

    def to_ui_distance(self, value):
        return value


_RESULT = {
    "meshes": ["|g|hand", "|g|body"],
    "pairs": [("|g|body", "|g|hand")],
    "hits": [{"mesh": "|g|hand", "other": "|g|body",
              "vertices": [(4, 0.5), (7, 0.2)]}],
    "targets": [
        {"target": "|rig|hand_ctl", "kind": "controller", "score": 2.0,
         "count": 2, "depth": 0.5, "pairs": [("|g|hand", "|g|body")]},
        {"target": "|rig|spine_jnt", "kind": "joint", "score": 1.0,
         "count": 1, "depth": 0.1, "pairs": [("|g|belt", "|g|body")]},
    ],
    "warnings": [], "cancelled": False,
}


class UiFlowTest(unittest.TestCase):

    def setUp(self):
        _bootstrap.reset_registry()
        del ui._STATE["targets"][:]
        ui._STATE["result"] = None
        self.fake = _FakeScene(_RESULT)
        self._orig = ui._scene
        ui._scene = lambda: self.fake
        # スタブの objExists は常に False。 結果のノードは「ある」ことにする
        ui.cmds.objExists = lambda name=None, **k: True
        ui.show()

    def tearDown(self):
        ui._scene = self._orig
        if "objExists" in vars(ui.cmds):
            del ui.cmds.objExists
        if ui.WINDOW in _bootstrap.WINDOWS:
            _bootstrap.WINDOWS.pop(ui.WINDOW)

    def _selects(self):
        return [c for c in _bootstrap.CALLS if c[0] == "select"]

    def test_check_without_targets_or_selection_warns(self):
        ui._on_check()
        self.assertEqual(self.fake.calls, [])
        self.assertTrue(_bootstrap.MESSAGES)

    def test_check_uses_selection_when_list_is_empty(self):
        _bootstrap.set_selection(["|g|hand", "|g|body"])
        ui._on_check()
        self.assertEqual(self.fake.calls[0][0], ["|g|hand", "|g|body"])

    def test_registered_targets_take_priority(self):
        _bootstrap.set_selection(["|chara_grp"])
        ui._on_add()
        _bootstrap.set_selection(["|other"])
        ui._on_check()
        self.assertEqual(self.fake.calls[0][0], ["|chara_grp"])

    def test_top_target_is_selected(self):
        _bootstrap.set_selection(["|g|hand", "|g|body"])
        ui._on_check()
        self.assertEqual(_bootstrap._SELECTION, ["|rig|hand_ctl"])

    def test_progress_window_is_closed(self):
        _bootstrap.set_selection(["|g|hand", "|g|body"])
        ui._on_check()
        ends = [c for c in _bootstrap.CALLS
                if c[0] == "progressWindow" and c[2].get("endProgress")]
        self.assertEqual(len(ends), 1)
        self.assertEqual(_bootstrap.UNDO_CHUNKS, [])

    def test_progress_window_is_closed_on_error(self):
        def boom(*_a, **_k):
            raise RuntimeError("boom")
        self.fake.check = boom
        _bootstrap.set_selection(["|g|hand", "|g|body"])
        with self.assertRaises(RuntimeError):
            ui._on_check()
        ends = [c for c in _bootstrap.CALLS
                if c[0] == "progressWindow" and c[2].get("endProgress")]
        self.assertEqual(len(ends), 1)

    def test_results_are_listed(self):
        _bootstrap.set_selection(["|g|hand", "|g|body"])
        ui._on_check()
        appended = [c[2]["append"] for c in _bootstrap.CALLS
                    if c[0] == "textScrollList" and c[1]
                    and c[1][0] == ui._CTRL["results"] and "append" in c[2]]
        self.assertEqual(len(appended), 2)
        self.assertTrue(appended[0].startswith("[CTRL] hand_ctl"))

    def test_select_vertices_of_picked_row(self):
        _bootstrap.set_selection(["|g|hand", "|g|body"])
        ui._on_check()
        _bootstrap.reset_registry()
        _bootstrap.CONTROLS[ui._CTRL["results"]] = {"selectIndexedItem": [1]}
        ui._on_select_vertices()
        self.assertEqual(_bootstrap._SELECTION, ["|g|hand.vtx[4]", "|g|hand.vtx[7]"])

    def test_remove_and_clear_targets(self):
        _bootstrap.set_selection(["|a", "|b"])
        ui._on_add()
        _bootstrap.CONTROLS[ui._CTRL["targets"]]["selectIndexedItem"] = [1]
        ui._on_remove()
        self.assertEqual(ui._STATE["targets"], ["|b"])
        ui._on_clear()
        self.assertEqual(ui._STATE["targets"], [])

    def test_options_are_namespaced(self):
        _bootstrap.set_selection(["|g|hand", "|g|body"])
        ui._on_check()
        for key in _bootstrap.OPTION_VARS:
            self.assertTrue(key.startswith("ntk_penetration_checker_"), key)


if __name__ == "__main__":
    unittest.main()
