# -*- coding: utf-8 -*-
"""`ui.py` のうち、スタブでも意味のある範囲だけを押さえる。

**スタブは「呼ばれたこと」しか知らない。** ノードの生成もシェーダーの割り当ても
何も起きないので、ここで確かめられるのは「対象が無いときに壊れないか」
「後片付けが対称か」「optionVar の往復が成り立つか」まで。

シェーダー割り当てそのものの正しさは**実機でしか確かめられない**（SPEC.md の
「実装状況」に確認項目を残してある）。
"""

from __future__ import annotations

import unittest

import _bootstrap


class EmptySelectionCase(unittest.TestCase):
    """対象が無いときに黙って壊れないこと。"""

    def setUp(self):
        _bootstrap.reset_registry()
        self.module = _bootstrap.reload_tool()
        self.ui = self.module.ui

    def test_apply_warns_instead_of_raising(self):
        _bootstrap.set_selection([])
        self.ui._on_apply_selected()
        self.assertTrue(_bootstrap.MESSAGES,
                        "選択が空のときに警告が出ていない")

    def test_apply_does_not_open_an_undo_chunk(self):
        """何もしない操作で undo 履歴を汚さないこと。"""
        _bootstrap.set_selection([])
        self.ui._on_apply_selected()
        self.assertEqual(_bootstrap.UNDO_CHUNKS, [],
                         "undo チャンクが開きっぱなし")
        self.assertNotIn("undoInfo", [name for name, _a, _k
                                      in _bootstrap.CALLS])

    def test_restore_with_nothing_overridden_warns(self):
        _bootstrap.set_selection([])
        self.ui._on_restore_all()
        self.assertTrue(_bootstrap.MESSAGES,
                        "戻す対象が無いときに警告が出ていない")
        self.assertEqual(_bootstrap.UNDO_CHUNKS, [])

    def test_refresh_without_a_window_is_a_no_op(self):
        """ウィンドウを開かずに呼んでも落ちないこと。"""
        self.ui._CTRL.clear()
        self.ui._refresh_list()   # 例外が出なければよい


class LastColorCase(unittest.TestCase):
    """前回使った色の記憶（optionVar）。"""

    def setUp(self):
        _bootstrap.reset_registry()
        self.module = _bootstrap.reload_tool()
        self.ui = self.module.ui

    def test_defaults_when_nothing_is_stored(self):
        self.assertEqual(self.ui._load_last_color(), self.ui._DEFAULT_COLOR)

    def test_round_trips_through_option_var(self):
        self.ui._CTRL.clear()          # UI 無しで optionVar だけを見る
        self.ui._set_color((1.0, 0.0, 0.0))
        self.assertEqual(_bootstrap.OPTION_VARS[self.ui._OPTVAR_LAST_COLOR],
                         "#FF0000")
        self.assertEqual(self.ui._load_last_color(), (1.0, 0.0, 0.0))

    def test_falls_back_when_the_stored_value_is_broken(self):
        """手で optionVar を壊されても既定色で起動できること。"""
        from maya import cmds
        cmds.optionVar(sv=(self.ui._OPTVAR_LAST_COLOR, "not a color"))
        self.assertEqual(self.ui._load_last_color(), self.ui._DEFAULT_COLOR)


class WindowCase(unittest.TestCase):
    """ウィンドウの組み立て。"""

    def setUp(self):
        _bootstrap.reset_registry()
        self.module = _bootstrap.reload_tool()
        self.ui = self.module.ui

    def test_show_builds_the_expected_controls(self):
        self.module.show()
        for key in ("color", "hex", "list", "count"):
            with self.subTest(control=key):
                self.assertIn(key, self.ui._CTRL,
                              "%s のコントロールが作られていない" % (key,))

    def test_show_resets_control_handles(self):
        """開き直したときに古いコントロール名が残らないこと。"""
        self.module.show()
        first = dict(self.ui._CTRL)
        self.module.show()
        self.assertNotEqual(first, self.ui._CTRL,
                            "2 回目の show() で古いコントロール名が残っている")

    def test_window_name_is_namespaced(self):
        self.assertTrue(self.ui.WINDOW.startswith(self.module.NAMESPACE + "_"))

    def test_scene_node_prefix_is_namespaced(self):
        """シーンに作るノードにも名前空間を付ける（他人のノードと同居する）。"""
        self.assertTrue(
            self.ui._NODE_PREFIX.startswith(self.module.NAMESPACE + "_"),
            "シーンに作るノードの接頭辞が名前空間に入っていない")
        for attr in (self.ui._ATTR_ORIGINAL, self.ui._ATTR_TARGET):
            with self.subTest(attr=attr):
                self.assertTrue(attr.startswith(self.module.NAMESPACE))


if __name__ == "__main__":
    unittest.main()
