# -*- coding: utf-8 -*-
"""UI のコールバックの往復（スタブ上）。

スタブは blendShape を知らないので、`scene` を差し替えて「シーンにこういう
ノードがある」状態を作り、UI が `core` の検証を通して `scene` を正しく呼ぶか、
undo チャンクを閉じるかだけを見る。 **実機の挙動はここでは分からない。**
"""

from __future__ import annotations

import unittest

import _bootstrap  # noqa: F401  （maya スタブの注入。 他の import より前）


class FakeScene(object):
    """`scene` モジュールの代役。 呼ばれた操作を記録する。"""

    def __init__(self):
        self.targets = [
            {"index": 0, "name": "L_smile", "items": [6000], "inbetweens": []},
            {"index": 1, "name": "R_smile", "items": [6000, 5500], "inbetweens": [0.5]},
            {"index": 2, "name": "jawOpen", "items": [6000], "inbetweens": []},
        ]
        self.calls = []

    def list_blendshapes(self):
        return ["face_BS"]

    def find_blendshapes(self, nodes):
        return ["face_BS"] if nodes else []

    def base_geometry(self, bs):
        return "|face|faceShape"

    def read_targets(self, bs):
        return [dict(t) for t in self.targets]

    def weight_plug(self, bs, index):
        return "%s.weight[%d]" % (bs, index)

    def vertex_count(self, node):
        return 100

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            if name == "mirror_target":
                return {"index": 9, "name": "x", "missing": 0, "replaced": False}
            if name in ("add_targets", "set_weights"):
                return []
            return "face_BS"
        return record


class UiCase(unittest.TestCase):

    def setUp(self):
        _bootstrap.reset_registry()
        self.module = _bootstrap.reload_tool()
        self.ui = self.module.ui
        self.fake = FakeScene()
        self.ui.scene = self.fake
        from maya import cmds
        self.cmds = cmds
        # ノードが存在する扱いにする
        self._orig_exists = type(cmds).objExists
        type(cmds).objExists = lambda _self, name=None, **_k: name == "face_BS"
        self.module.show()

    def tearDown(self):
        type(self.cmds).objExists = self._orig_exists

    def _check(self, *indices):
        for index in indices:
            cb, _ = self.ui._ROWS[index]
            self.cmds.checkBox(cb, e=True, value=True)

    def _called(self, name):
        return [c for c in self.fake.calls if c[0] == name]

    def test_rows_are_built(self):
        self.assertEqual(sorted(self.ui._ROWS), [0, 1, 2])
        self.assertEqual(_bootstrap.UNDO_CHUNKS, [])

    def test_delete_needs_check(self):
        self.ui._on_delete()
        self.assertEqual(self._called("delete_targets"), [])
        self.assertTrue(_bootstrap.DIALOGS)
        self.assertEqual(_bootstrap.UNDO_CHUNKS, [])

    def test_delete_checked(self):
        self._check(2)
        self.ui._on_delete()
        self.assertEqual(self._called("delete_targets")[0][1], ("face_BS", [2]))
        self.assertEqual(_bootstrap.UNDO_CHUNKS, [])

    def test_rename_swap_is_planned(self):
        self._check(0, 1)
        self.cmds.textFieldGrp(self.ui._CTRL["search"], e=True, text="smile")
        self.cmds.textFieldGrp(self.ui._CTRL["replace"], e=True, text="grin")
        self.cmds.textFieldGrp(self.ui._CTRL["prefix"], e=True, text="")
        self.cmds.textFieldGrp(self.ui._CTRL["suffix"], e=True, text="")
        self.ui._on_batch_rename()
        steps = self._called("rename_targets")[0][1][1]
        self.assertEqual(steps, [(0, "L_grin"), (1, "R_grin")])

    def test_rename_duplicate_is_rejected(self):
        self._check(0)
        self.cmds.textFieldGrp(self.ui._CTRL["rename"], e=True, text="jawOpen")
        self.ui._on_rename_one()
        self.assertEqual(self._called("rename_targets"), [])
        self.assertTrue(_bootstrap.DIALOGS)

    def test_inbetween_duplicate_weight_is_rejected(self):
        self._check(1)
        _bootstrap.set_selection(["|ib"])
        self.cmds.floatFieldGrp(self.ui._CTRL["ib_weight"], e=True, value1=0.5)
        self.ui._on_add_inbetween()
        self.assertEqual(self._called("add_inbetween"), [])

    def test_inbetween_added(self):
        self._check(0)
        _bootstrap.set_selection(["|ib"])
        self.cmds.floatFieldGrp(self.ui._CTRL["ib_weight"], e=True, value1=0.5)
        self.ui._on_add_inbetween()
        self.assertEqual(self._called("add_inbetween")[0][1], ("face_BS", 0, "|ib", 0.5))

    def test_mirror_skips_pair(self):
        self._check(0, 1)
        self.cmds.radioButtonGrp(self.ui._CTRL["axis"], e=True, select=1)
        self.cmds.floatFieldGrp(self.ui._CTRL["tolerance"], e=True, value1=0.001)
        self.cmds.checkBox(self.ui._CTRL["overwrite"], e=True, value=True)
        self.ui._on_mirror()
        calls = self._called("mirror_target")
        self.assertEqual([c[1][1] for c in calls], [0])
        self.assertEqual(_bootstrap.UNDO_CHUNKS, [])

    def test_create_from_selection(self):
        _bootstrap.set_selection(["|t1", "|face"])
        self.cmds.textFieldGrp(self.ui._CTRL["new_name"], e=True, text="")
        self.cmds.checkBox(self.ui._CTRL["front"], e=True, value=True)
        self.ui._on_create()
        args, kwargs = self._called("create")[0][1:]
        self.assertEqual(args, ("|face", ["|t1"], "face_BS"))
        self.assertEqual(kwargs, {"front_of_chain": True})

    def test_unexpected_error_closes_chunk(self):
        def boom(*_a, **_k):
            raise RuntimeError("boom")
        self.fake.set_weights = boom
        self._check(0)
        self.ui._set_weight_action(1.0, False)()
        self.assertEqual(_bootstrap.UNDO_CHUNKS, [])
        self.assertTrue(_bootstrap.DIALOGS)


if __name__ == "__main__":
    unittest.main()
