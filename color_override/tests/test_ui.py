# -*- coding: utf-8 -*-
"""`ui.py` のうち、スタブでも意味のある範囲だけを押さえる。

**スタブは「呼ばれたこと」しか知らない。** ノードの生成もシェーダーの割り当ても
何も起きないので、ここで確かめられるのは「対象が無いときに壊れないか」
「後片付けが対称か」「optionVar の往復が成り立つか」まで。

シェーダー割り当てそのものの正しさは**実機でしか確かめられない**（SPEC.md の
「実装状況」に確認項目を残してある）。
"""

from __future__ import annotations

import os
import unittest

import _bootstrap

from color_override import core


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


class ToggleCase(unittest.TestCase):
    """一時解除（peek）の入口。"""

    def setUp(self):
        _bootstrap.reset_registry()
        self.module = _bootstrap.reload_tool()
        self.ui = self.module.ui

    def test_toggle_is_exposed_on_the_package(self):
        """ホットキーから `color_override.toggle()` で呼べること。"""
        self.assertTrue(callable(getattr(self.module, "toggle", None)))
        self.assertIn("toggle", self.module.__all__)

    def test_toggle_without_overrides_warns(self):
        self.module.toggle()
        self.assertTrue(_bootstrap.MESSAGES,
                        "オーバーライドが無いときに警告が出ていない")

    def test_toggle_without_overrides_does_not_touch_undo(self):
        self.module.toggle()
        self.assertEqual(_bootstrap.UNDO_CHUNKS, [])
        self.assertNotIn("undoInfo",
                         [name for name, _a, _k in _bootstrap.CALLS])

    def test_toggle_works_without_a_window(self):
        """ウィンドウを開かずに呼んでも落ちないこと（ホットキー用途）。"""
        self.ui._CTRL.clear()
        self.module.toggle()   # 例外が出なければよい

    def test_enable_and_disable_ignore_records_in_the_wrong_state(self):
        """既にその状態のものは触らない（無駄な cmds.sets を出さない）。"""
        self.assertEqual(self.ui._disable_records([{"enabled": False}]), 0)
        self.assertEqual(self.ui._enable_records([{"enabled": True}]), 0)
        self.assertEqual(self.ui._disable_records([]), 0)
        self.assertEqual(self.ui._enable_records(None), 0)


class ReleaseMembersCase(unittest.TestCase):
    """1 シェイプ = 1 オーバーライド を保つ後始末。

    グループに掛けたあと中の 1 つだけ色を変えたときに、そのシェイプが
    2 つの記録に属したままにならないこと。
    """

    def setUp(self):
        _bootstrap.reset_registry()
        self.module = _bootstrap.reload_tool()
        self.ui = self.module.ui
        self.record = {"shader": "shdA", "sg": "sgA", "target": "|hair_grp",
                       "members": ["|hair_grp|a|aShape", "|hair_grp|b|bShape"],
                       "originals": ["sgHair", "sgSkin"]}
        self.records = [self.record]
        self.index = core.index_by_object(self.records)

    def test_released_member_leaves_the_record(self):
        self.ui._release_members(self.records, self.index,
                                 ["|hair_grp|a|aShape"])
        self.assertEqual(self.record["members"], ["|hair_grp|b|bShape"])
        self.assertIn(self.record, self.records)

    def test_the_remaining_destinations_stay_aligned(self):
        """外したあとに戻し先がずれると、別のマテリアルへ戻して事故になる。"""
        self.ui._release_members(self.records, self.index,
                                 ["|hair_grp|a|aShape"])
        self.assertEqual(self.record["originals"], ["sgSkin"])

    def test_released_member_is_dropped_from_the_index(self):
        self.ui._release_members(self.records, self.index,
                                 ["|hair_grp|a|aShape"])
        self.assertNotIn("|hair_grp|a|aShape", self.index)
        self.assertIn("|hair_grp|b|bShape", self.index)

    def test_a_record_that_loses_everything_is_dropped(self):
        self.ui._release_members(self.records, self.index,
                                 ["|hair_grp|a|aShape",
                                  "|hair_grp|b|bShape"])
        self.assertEqual(self.records, [])
        self.assertEqual(self.index, {},
                         "記録を消したのに索引に残っている")

    def test_untouched_records_are_left_alone(self):
        self.ui._release_members(self.records, self.index, ["|other|xShape"])
        self.assertEqual(self.record["members"],
                         ["|hair_grp|a|aShape", "|hair_grp|b|bShape"])
        self.assertEqual(self.record["originals"], ["sgHair", "sgSkin"])


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

    def test_toggle_button_starts_disabled(self):
        """掛かっていない状態で押せてしまわないこと。"""
        self.module.show()
        ctrl = self.ui._CTRL["toggle"]
        stored = _bootstrap.CONTROLS[ctrl]
        self.assertFalse(stored.get("enable"),
                         "オーバーライドが無いのにトグルが有効になっている")
        self.assertEqual(stored.get("label"), "Hide Colors")

    def test_window_name_is_namespaced(self):
        self.assertTrue(self.ui.WINDOW.startswith(self.module.NAMESPACE + "_"))

    def test_scene_node_prefix_is_namespaced(self):
        """シーンに作るノードにも名前空間を付ける（他人のノードと同居する）。"""
        self.assertTrue(
            self.ui._NODE_PREFIX.startswith(self.module.NAMESPACE + "_"),
            "シーンに作るノードの接頭辞が名前空間に入っていない")
        for attr in (self.ui._ATTR_ORIGINAL, self.ui._ATTR_TARGET,
                     self.ui._ATTR_MEMBERS):
            with self.subTest(attr=attr):
                self.assertTrue(attr.startswith(self.module.NAMESPACE))


class BackupCase(unittest.TestCase):
    """控え（シーンの隣の JSON）の読み書き。

    **`Restore` はシーンからノードを消す。** 控えが書けていないと同じ色分けに
    二度と戻れないので、ここが黙って失敗しないことが要になる。
    """

    def setUp(self):
        import tempfile
        _bootstrap.reset_registry()
        self.module = _bootstrap.reload_tool()
        self.ui = self.module.ui
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "shot.color_override.json")
        self.sets = [{"name": "hair",
                      "items": [{"target": "|a", "color": (1.0, 0.0, 0.0)}]}]

    def test_round_trip_through_a_real_file(self):
        self.ui._write_backup(self.sets, self.path)
        self.assertEqual(self.ui._read_backup(self.path), self.sets)

    def test_reading_a_missing_file_is_empty(self):
        self.assertEqual(self.ui._read_backup(self.path), [])

    def test_a_broken_file_warns_instead_of_raising(self):
        """手で編集して壊れていても、ツールが開けなくならないこと。"""
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("{ this is not json")
        self.assertEqual(self.ui._read_backup(self.path), [])
        self.assertTrue(_bootstrap.MESSAGES, "警告が出ていない")

    def test_no_scene_means_no_backup_path(self):
        """未保存のシーンでは置き場所が決まらない。"""
        self.assertIsNone(self.ui._backup_path())

    def test_nothing_to_back_up_is_not_an_abort(self):
        """`None`（控えなかった）と `False`（中止）を取り違えないこと。"""
        self.assertIsNone(self.ui._backup_sets([]))
        self.assertIsNone(self.ui._backup_sets([{"name": "x", "items": []}]))


class SetRowCase(unittest.TestCase):
    """一覧の行。 **セット単位**で、色はコードでなく見本で出す。"""

    def setUp(self):
        _bootstrap.reset_registry()
        self.module = _bootstrap.reload_tool()
        self.ui = self.module.ui

    def _canvas_colors(self):
        return [kwargs.get("rgbValue") for name, _a, kwargs
                in _bootstrap.CALLS if name == "canvas"]

    def test_a_row_draws_a_swatch_per_distinct_colour(self):
        self.ui._build_swatches([(1.0, 0.0, 0.0), (1.0, 0.0, 0.0),
                                 (0.0, 1.0, 0.0)])
        self.assertEqual(self._canvas_colors(),
                         [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)])

    def test_the_hex_code_stays_in_the_tooltip(self):
        """見本で分かるようにしたが、値そのものも読めるようにしておく。"""
        self.ui._build_swatches([(1.0, 0.0, 0.0)])
        tooltips = [kwargs.get("annotation") for name, _a, kwargs
                    in _bootstrap.CALLS if name == "canvas"]
        self.assertEqual(tooltips, ["#FF0000"])

    def test_no_colour_still_builds_a_row(self):
        self.ui._build_swatches([])          # 例外が出なければよい
        self.assertEqual(self._canvas_colors(), [])

    def test_an_applied_row_offers_hide_and_restore(self):
        self.ui._build_set_row({"name": "hair", "applied": True,
                                "enabled": True, "records": [], "items": [],
                                "colors": [(1.0, 0.0, 0.0)], "count": 3})
        labels = [kwargs.get("label") for name, _a, kwargs
                  in _bootstrap.CALLS if name == "button"]
        self.assertEqual(labels, ["Hide", "Sel", "Restore"])

    def test_a_backup_row_offers_apply(self):
        """Restore All したあとも呼び戻せる、が成立していること。"""
        self.ui._build_set_row({"name": "hair", "applied": False,
                                "enabled": False, "records": [],
                                "items": [{"target": "|a",
                                           "color": (1.0, 0.0, 0.0)}],
                                "colors": [(1.0, 0.0, 0.0)], "count": 1})
        labels = [kwargs.get("label") for name, _a, kwargs
                  in _bootstrap.CALLS if name == "button"]
        self.assertEqual(labels, ["Sel", "Apply"])

    def test_a_disabled_row_offers_show(self):
        self.ui._build_set_row({"name": "hair", "applied": True,
                                "enabled": False, "records": [], "items": [],
                                "colors": [(1.0, 0.0, 0.0)], "count": 1})
        labels = [kwargs.get("label") for name, _a, kwargs
                  in _bootstrap.CALLS if name == "button"]
        self.assertIn("Show", labels)


if __name__ == "__main__":
    unittest.main()
