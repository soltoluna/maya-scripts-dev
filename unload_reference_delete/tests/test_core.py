# -*- coding: utf-8 -*-
"""`core` の仕分けロジックと、`ui.remove_unloaded()` の削除ループの回帰テスト。

`core` は `maya` を import しないので、**ここでの結果は実機と同じ**になる。
`ui` 側は `cmds` スタブ越しなので「正しい引数で呼んだか」までしか担保しない。
"""

from __future__ import annotations

import unittest

import _bootstrap  # noqa: F401  （maya スタブの注入。 他の import より前）

from unload_reference_delete import core, ui


def _entry(node, path="C:/p/a.ma", loaded=False, parent=None):
    return core.ReferenceEntry(reference_node=node, file_path=path,
                               is_loaded=loaded, parent_node=parent)


class PlanRemovalCase(unittest.TestCase):
    """「消すもの / 親ごと消えるもの / 消せないもの」の仕分け。"""

    def test_only_unloaded_are_targets(self):
        entries = [_entry("aRN", loaded=True), _entry("bRN", loaded=False)]
        plan = core.plan_removal(entries)
        self.assertEqual([e.reference_node for e in plan.targets], ["bRN"])
        self.assertEqual(plan.nested, [])
        self.assertEqual(plan.unresolved, [])

    def test_empty_input(self):
        plan = core.plan_removal([])
        self.assertEqual((plan.targets, plan.nested, plan.unresolved),
                         ([], [], []))

    def test_child_of_unloaded_parent_is_nested(self):
        """親を消すと子も消える。 個別に消しにいくとエラーになる。"""
        parent = _entry("parentRN", loaded=False)
        child = _entry("childRN", loaded=False, parent="parentRN")
        plan = core.plan_removal([parent, child])
        self.assertEqual([e.reference_node for e in plan.targets], ["parentRN"])
        self.assertEqual([e.reference_node for e in plan.nested], ["childRN"])

    def test_grandchild_of_unloaded_root_is_nested(self):
        root = _entry("rootRN", loaded=False)
        mid = _entry("midRN", loaded=False, parent="rootRN")
        leaf = _entry("leafRN", loaded=False, parent="midRN")
        plan = core.plan_removal([root, mid, leaf])
        self.assertEqual([e.reference_node for e in plan.targets], ["rootRN"])
        self.assertEqual([e.reference_node for e in plan.nested],
                         ["midRN", "leafRN"])

    def test_child_of_loaded_parent_is_a_target(self):
        parent = _entry("parentRN", loaded=True)
        child = _entry("childRN", loaded=False, parent="parentRN")
        plan = core.plan_removal([parent, child])
        self.assertEqual([e.reference_node for e in plan.targets], ["childRN"])
        self.assertEqual(plan.nested, [])

    def test_unknown_parent_is_treated_as_top_level(self):
        """親が一覧に無い場合は独立した参照として扱う（実機で親を引けない想定）。"""
        child = _entry("childRN", loaded=False, parent="missingRN")
        plan = core.plan_removal([child])
        self.assertEqual([e.reference_node for e in plan.targets], ["childRN"])

    def test_entry_without_reference_node_is_unresolved(self):
        plan = core.plan_removal([_entry("", loaded=False)])
        self.assertEqual(plan.targets, [])
        self.assertEqual(len(plan.unresolved), 1)

    def test_parent_cycle_does_not_hang(self):
        """壊れた親子関係で無限ループしない（実機のデータを信用しきらない）。"""
        a = _entry("aRN", loaded=False, parent="bRN")
        b = _entry("bRN", loaded=True, parent="aRN")
        plan = core.plan_removal([a, b])
        self.assertEqual([e.reference_node for e in plan.targets], ["aRN"])


class LabelCase(unittest.TestCase):
    """パスの表示整形。 Maya は同一ファイルの重複参照に `{n}` を付ける。"""

    def test_split_copy_number(self):
        self.assertEqual(core.split_copy_number("C:/p/char.ma{1}"),
                         ("C:/p/char.ma", 1))
        self.assertEqual(core.split_copy_number("C:/p/char.ma"),
                         ("C:/p/char.ma", None))
        self.assertEqual(core.split_copy_number(""), ("", None))

    def test_file_base_name_handles_both_separators(self):
        self.assertEqual(core.file_base_name("C:/p/char.ma{2}"), "char.ma")
        self.assertEqual(core.file_base_name(r"C:\p\char.ma"), "char.ma")

    def test_display_label_includes_node_and_copy_number(self):
        label = core.display_label(_entry("charRN", "C:/p/char.ma{1}"))
        self.assertIn("char.ma", label)
        self.assertIn("{1}", label)
        self.assertIn("charRN", label)

    def test_display_label_survives_missing_node(self):
        self.assertIn("?", core.display_label(_entry("", "C:/p/char.ma")))


class FormatCase(unittest.TestCase):

    def test_plan_message_warns_about_undo(self):
        """undo できないことを消す前に必ず伝える（このツール唯一の安全装置）。"""
        plan = core.plan_removal([_entry("aRN", "C:/p/a.ma", loaded=False)])
        message = core.format_plan(plan)
        self.assertIn("undo", message)
        self.assertIn("a.ma", message)

    def test_result_message_lists_failures(self):
        entry = _entry("aRN", "C:/p/a.ma")
        text = core.format_result([], [(entry, "RuntimeError: boom")])
        self.assertIn("失敗", text)
        self.assertIn("boom", text)


class RemoveUnloadedCase(unittest.TestCase):
    """`ui.remove_unloaded()` — スタブなので「正しく呼んだか」までの担保。"""

    def setUp(self):
        _bootstrap.reset_registry()
        self._entries = []
        self._original_collect = ui.collect_entries
        ui.collect_entries = lambda: list(self._entries)

    def tearDown(self):
        ui.collect_entries = self._original_collect
        # スタブの `cmds` は __getattr__ で生やしているので、上書きした分は
        # インスタンス辞書から抜けば元に戻る
        from maya import cmds
        cmds.__dict__.pop("file", None)
        cmds.__dict__.pop("confirmDialog", None)

    def _calls(self, name):
        return [(args, kwargs) for called, args, kwargs in _bootstrap.CALLS
                if called == name]

    def test_removes_by_reference_node_not_path(self):
        """パスではなくノードを渡す（重複参照だとパスが曖昧になるため）。"""
        self._entries = [_entry("aRN", "C:/p/a.ma", loaded=False),
                         _entry("bRN", "C:/p/b.ma", loaded=True)]
        removed, failed = ui.remove_unloaded(confirm=False)
        self.assertEqual((removed, failed), (1, 0))
        removals = [kwargs for _args, kwargs in self._calls("file")
                    if kwargs.get("removeReference")]
        self.assertEqual([kwargs["referenceNode"] for kwargs in removals],
                         ["aRN"])

    def test_nothing_to_remove_does_not_touch_the_scene(self):
        self._entries = [_entry("aRN", loaded=True)]
        self.assertEqual(ui.remove_unloaded(confirm=False), (0, 0))
        self.assertEqual(self._calls("file"), [])

    def test_one_failure_does_not_stop_the_rest(self):
        """1 本壊れていても残りは消す（元の実装はそこで止まっていた）。"""
        from maya import cmds

        def _file(*args, **kwargs):
            _bootstrap.CALLS.append(("file", args, kwargs))
            if kwargs.get("referenceNode") == "badRN":
                raise RuntimeError("boom")
            return None

        cmds.file = _file
        self._entries = [_entry("badRN", "C:/p/bad.ma", loaded=False),
                         _entry("okRN", "C:/p/ok.ma", loaded=False)]
        removed, failed = ui.remove_unloaded(confirm=False)
        self.assertEqual((removed, failed), (1, 1))

    def test_cancel_removes_nothing(self):
        from maya import cmds
        cmds.confirmDialog = lambda **kwargs: "Cancel"

        self._entries = [_entry("aRN", "C:/p/a.ma", loaded=False)]
        self.assertEqual(ui.remove_unloaded(confirm=True), (0, 0))
        self.assertEqual(self._calls("file"), [])


if __name__ == "__main__":
    unittest.main()
