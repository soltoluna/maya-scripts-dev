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

    def test_refresh_with_stale_control_names_is_a_no_op(self):
        """閉じたあとも `_CTRL` には名前が残る（`toggle()` はホットキーで走る）。"""
        self.ui._CTRL.clear()
        self.ui._CTRL.update({"rows": "goneRows", "backup_rows": "goneRows2",
                              "backup_frame": "goneFrame",
                              "count": "goneCount", "toggle": "goneToggle"})
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

    def test_a_backup_row_offers_a_restore_button(self):
        """控えに「戻す手段」が見えていること（Apply では復元と読めない）。"""
        self.ui._build_set_row({"name": "hair", "applied": False,
                                "enabled": False, "records": [],
                                "items": [{"target": "|a",
                                           "color": (1.0, 0.0, 0.0)}],
                                "colors": [(1.0, 0.0, 0.0)], "count": 1})
        labels = [kwargs.get("label") for name, _a, kwargs
                  in _bootstrap.CALLS if name == "button"]
        self.assertEqual(labels, ["Sel", "復元"])

    def test_a_disabled_row_offers_show(self):
        self.ui._build_set_row({"name": "hair", "applied": True,
                                "enabled": False, "records": [], "items": [],
                                "colors": [(1.0, 0.0, 0.0)], "count": 1})
        labels = [kwargs.get("label") for name, _a, kwargs
                  in _bootstrap.CALLS if name == "button"]
        self.assertIn("Show", labels)


class FaceAssignmentCase(unittest.TestCase):
    """フェース単位でマテリアルが分かれたシェイプの読み取りと復元。

    スタブは割り当てを持たないので、`listConnections` と `cmds.sets(q=True)`
    を差し替えて**実機が返す形**だけを再現する。 実際に色が乗るかどうかは
    ここでは分からない（確認項目は SPEC.md の「実装状況」）。
    """

    SHAPE = "|a|aShape"

    def setUp(self):
        from maya import cmds
        _bootstrap.reset_registry()
        self.module = _bootstrap.reload_tool()
        self.ui = self.module.ui
        self.cmds = cmds
        self.queried = []

    def _patch(self, name, func):
        setattr(self.cmds, name, func)
        self.addCleanup(lambda: delattr(self.cmds, name))

    def _scene(self, engines, members=None, exists=True, fails=False):
        """割り当てを差し替える。

        `engines` はシェイプにつながっている shadingEngine、`members` は
        `{SG 名: [メンバー...]}`（`cmds.sets(sg, q=True)` が返すもの）。
        """
        def _list_connections(*_a, **_k):
            if fails:
                raise RuntimeError("nope")
            return list(engines)

        self._patch("listConnections", _list_connections)

        table = members or {}
        original = self.cmds.sets

        def _sets(*args, **kwargs):
            if kwargs.get("q") or kwargs.get("query"):
                name = args[0] if args else None
                self.queried.append(name)
                return list(table.get(name, []))
            return original(*args, **kwargs)

        self._patch("sets", _sets)
        self._patch("objExists", lambda *a, **k: exists)

    # -- 読み取り ------------------------------------------------------------

    def test_a_single_destination_needs_no_member_scan(self):
        """**ふつうのシェイプでセットの中身を引かない。**

        `initialShadingGroup` は大きいシーンで数千件返る。 対象ごとに引くと
        掛けるたびに走査することになる。
        """
        self._scene(["lambert2SG"])
        self.assertEqual(self.ui._read_assignment(self.SHAPE),
                         ("lambert2SG", [], True))
        self.assertEqual(self.queried, [], "セットの中身を引いている")

    def test_an_unassigned_shape_falls_back_to_the_maya_default(self):
        self._scene([])
        self.assertEqual(self.ui._read_assignment(self.SHAPE),
                         (self.ui._DEFAULT_SG, [], True))

    def test_face_groups_are_read_with_their_own_destination(self):
        self._scene(["sgA", "sgB"],
                    {"sgA": ["|a|aShape.f[0:2]"],
                     "sgB": ["|a|aShape.f[3:5]", "|a|aShape.f[9]"]})
        base, entries, ok = self.ui._read_assignment(self.SHAPE)
        self.assertTrue(ok)
        self.assertEqual(base, "sgA", "土台が無いときは最初の塊の SG で埋める")
        self.assertEqual(entries, [
            {"sg": "sgA", "components": ["|a|aShape.f[0:2]"]},
            {"sg": "sgB", "components": ["|a|aShape.f[3:5]", "|a|aShape.f[9]"]}])

    def test_a_whole_membership_becomes_the_base(self):
        """シェイプ全体のメンバーがあれば、それが土台（塗り残しの行き先）。"""
        self._scene(["sgBase", "sgB"],
                    {"sgBase": ["|a|aShape"],
                     "sgB": ["|a|aShape.f[3:5]"]})
        base, entries, ok = self.ui._read_assignment(self.SHAPE)
        self.assertEqual(base, "sgBase")
        self.assertEqual([entry["sg"] for entry in entries], ["sgB"])
        self.assertTrue(ok)

    def test_another_shapes_components_are_not_taken(self):
        """**同名シェイプのフェースを取り込まない。**

        `|charA|body|bodyShape` と `|charB|body|bodyShape` が同じ SG に居ると、
        短い名前での照合では他人のフェースを別のマテリアルへ戻してしまう。
        """
        self._scene(["sgA", "sgB"],
                    {"sgA": ["|a|aShape.f[0:2]", "|b|aShape.f[7]"],
                     "sgB": ["|b|aShape.f[0]"]})
        base, entries, _ok = self.ui._read_assignment(self.SHAPE)
        self.assertEqual(entries,
                         [{"sg": "sgA", "components": ["|a|aShape.f[0:2]"]}])
        self.assertEqual(base, "sgB", "自分の塊が無い SG は土台側に回る")

    def test_no_components_at_all_is_reported(self):
        """2 つ以上つながっているのに塊が拾えないなら、黙って 1 色にしない。"""
        self._scene(["sgA", "sgB"])
        base, entries, ok = self.ui._read_assignment(self.SHAPE)
        self.assertEqual((base, entries), ("sgA", []))
        self.assertFalse(ok)

    def test_each_shading_engine_is_queried_once(self):
        """メンバーの引き直しをしない（掛けるたびに数千件を走査しない）。"""
        self._scene(["sgA", "sgB"],
                    {"sgA": ["|a|aShape.f[0]"], "sgB": ["|a|aShape.f[1]"]})
        members_of = self.ui._sg_member_reader()
        for _ in range(3):
            self.ui._read_assignment(self.SHAPE, members_of)
        self.assertEqual(sorted(self.queried), ["sgA", "sgB"])

    def test_reading_never_raises(self):
        """**`_apply_one` の途中で落とさない。** 落ちれば色も乗らない。"""
        self._scene([], fails=True)
        self.assertEqual(self.ui._read_assignment(self.SHAPE),
                         (self.ui._DEFAULT_SG, [], True))

    # -- 掛ける --------------------------------------------------------------

    def _apply(self, node=SHAPE):
        records, index = [], {}
        return self.ui._apply_one(node, (1.0, 0.0, 0.0), "Set 1", records,
                                  index, self.ui._assignment_resolver([]))

    def test_a_shape_whose_faces_cannot_be_read_still_gets_a_colour(self):
        """**主機能を止めない。**

        v0.5.0〜v0.7.1 はここで掛けるのをやめていた（戻せなくなるくらいなら
        掛けない）。 実機ではその判断が働いて色がまったく乗らなくなった。
        """
        self._scene(["sgA", "sgB"])
        self.assertIsNotNone(self._apply(), "色が掛からない")
        self.assertTrue(_bootstrap.MESSAGES, "読めなかったことを知らせていない")

    def test_a_plain_shape_gets_a_colour(self):
        self._scene(["lambert2SG"])
        self.assertIsNotNone(self._apply())

    def test_the_face_groups_are_written_to_the_shader(self):
        """復元の情報源はシーン側。 辞書に持つと開き直した時点で失う。"""
        self._scene(["sgA", "sgB"],
                    {"sgA": ["|a|aShape.f[0:2]"], "sgB": ["|a|aShape.f[3]"]})
        self.assertIsNotNone(self._apply())
        written = [args[1] for name, args, _k in _bootstrap.CALLS
                   if name == "setAttr" and len(args) > 1
                   and str(args[0]).endswith(self.ui._ATTR_FACES)]
        self.assertEqual(len(written), 1, "フェースの控えが書かれていない")
        self.assertEqual(core.decode_faces(written[0]),
                         {self.SHAPE: [
                             {"sg": "sgA", "components": ["|a|aShape.f[0:2]"]},
                             {"sg": "sgB", "components": ["|a|aShape.f[3]"]}]})

    # -- 戻す ----------------------------------------------------------------

    def _force_element_calls(self):
        return [(kwargs.get("forceElement"), args[0])
                for name, args, kwargs in _bootstrap.CALLS
                if name == "sets" and kwargs.get("forceElement")]

    def test_restoring_puts_the_faces_back_after_the_whole_shape(self):
        self._scene([])
        self.ui._return_to_originals([{
            "original": "sgBase", "members": [self.SHAPE],
            "faces": {self.SHAPE: [
                {"sg": "sgA", "components": ["|a|aShape.f[0:2]"]},
                {"sg": "sgB", "components": ["|a|aShape.f[3:5]"]}]}}])
        self.assertEqual(self._force_element_calls(),
                         [("sgBase", [self.SHAPE]),
                          ("sgA", ["|a|aShape.f[0:2]"]),
                          ("sgB", ["|a|aShape.f[3:5]"])])

    def test_hiding_puts_the_faces_back_too(self):
        """**Hide でフェース割り当てが消えた**（実機からの指摘）の回帰。"""
        record = {"shader": "shd", "sg": "ovrSG", "enabled": True,
                  "original": "sgBase", "members": [self.SHAPE],
                  "originals": ["sgBase"],
                  "faces": {self.SHAPE: [
                      {"sg": "sgA", "components": ["|a|aShape.f[0:2]"]},
                      {"sg": "sgB", "components": ["|a|aShape.f[3:5]"]}]}}
        self._scene([])
        self.assertEqual(self.ui._disable_records([record]), 1)
        self.assertEqual(self._force_element_calls(),
                         [("sgBase", [self.SHAPE]),
                          ("sgA", ["|a|aShape.f[0:2]"]),
                          ("sgB", ["|a|aShape.f[3:5]"])])

    def test_a_component_whose_shape_is_gone_is_skipped(self):
        """消えたノードへ戻そうとして操作ごと落ちないこと。"""
        self._scene([], exists=False)
        self.ui._return_to_originals([{
            "original": "sgBase", "members": [self.SHAPE],
            "faces": {self.SHAPE: [
                {"sg": "sgA", "components": ["|a|aShape.f[0:2]"]}]}}])
        self.assertEqual(self._force_element_calls(), [])



def _set_entry(name, applied, enabled=True, count=2):
    """一覧に流す 1 セット分の形。"""
    return {"name": name, "applied": applied, "enabled": enabled,
            "records": [], "items": [{"target": "|a", "color": (1.0, 0.0, 0.0)}],
            "colors": [(1.0, 0.0, 0.0)], "count": count}


class BackupPaneCase(unittest.TestCase):
    """**Restore したセットは上の一覧から消え、「控え」欄に移る。**

    1 つの欄に混ぜると、片付けたセットがその場に残って見えるので
    「片付いたのか」が分からない（実機からの指摘）。
    """

    def setUp(self):
        _bootstrap.reset_registry()
        self.module = _bootstrap.reload_tool()
        self.ui = self.module.ui
        self.module.show()

    def _rows_under(self, key):
        """その欄に直接ぶら下がっている行の数。"""
        parent = self.ui._CTRL.get(key)
        return len([name for name, meta in _bootstrap.CONTROLS.items()
                    if meta.get("_parent") == parent
                    and meta.get("_command") == "rowLayout"])

    def _frame(self):
        return _bootstrap.CONTROLS[self.ui._CTRL["backup_frame"]]

    def test_the_two_panes_get_their_own_rows(self):
        self.ui._all_sets = lambda: [_set_entry("hair", True),
                                     _set_entry("old", False),
                                     _set_entry("older", False)]
        self.ui._refresh_list()
        self.assertEqual(self._rows_under("rows"), 1, "上の一覧の行数が違う")
        self.assertEqual(self._rows_under("backup_rows"), 2,
                         "控え欄の行数が違う")

    def test_the_backup_pane_stays_reachable_when_empty(self):
        """**空でも畳まない。** 「控えたのに 0 件」のときにこそ探しに行きたい。"""
        self.ui._all_sets = lambda: [_set_entry("hair", True)]
        self.ui._refresh_list()
        self.assertIsNot(self._frame().get("manage"), False,
                         "空の控え欄を隠すと「読み込む…」に届かない")
        self.assertIn("backup_path", self.ui._CTRL)

    def test_the_backup_pane_shows_its_count(self):
        self.ui._all_sets = lambda: [_set_entry("old", False)]
        self.ui._refresh_list()
        self.assertIn("1", self._frame().get("label") or "")

    def test_an_unsaved_scene_says_so_instead_of_showing_nothing(self):
        """「0 セット」だけでは、未保存なのか空なのか分からない。"""
        self.ui._all_sets = lambda: []
        self.ui._refresh_list()
        label = _bootstrap.CONTROLS[self.ui._CTRL["backup_path"]].get("label")
        self.assertIn("未保存", label or "")

    def test_rows_are_rebuilt_instead_of_accumulating(self):
        """更新のたびに増えていかないこと。"""
        self.ui._all_sets = lambda: [_set_entry("old", False)]
        self.ui._refresh_list()
        self.ui._refresh_list()
        self.assertEqual(self._rows_under("backup_rows"), 1)

    def test_a_set_that_is_applied_is_not_listed_twice(self):
        """掛け直したセットが上と下に同時に出ないこと。"""
        self.ui._collect_records = lambda: [
            {"shader": "shd", "sg": "sg", "original": "sgA",
             "originals": ["sgA"], "target": "|a", "set": "hair",
             "color": (1.0, 0.0, 0.0), "members": ["|a|aShape"],
             "enabled": True}]
        self.ui._read_backup = lambda path=None: [
            {"name": "hair", "items": [{"target": "|a",
                                        "color": (1.0, 0.0, 0.0)}]}]
        entries = self.ui._all_sets()
        self.assertEqual([entry["name"] for entry in entries], ["hair"])
        self.assertTrue(entries[0]["applied"])


class BackupPathCase(unittest.TestCase):
    """未保存シーンで選んでもらった控えの置き場所。

    **覚えずに捨てると、書き出した控えを読み戻せない**（控えたのに
    一覧にも出ず、復元の手段が無くなる）。
    """

    def setUp(self):
        _bootstrap.reset_registry()
        self.module = _bootstrap.reload_tool()
        self.ui = self.module.ui

    def test_an_unsaved_scene_falls_back_to_the_remembered_path(self):
        self.ui._remember_backup_path("C:/tmp/x.json")
        self.assertEqual(self.ui._backup_path(), "C:/tmp/x.json")

    def test_choosing_a_path_remembers_it(self):
        from maya import cmds
        cmds.fileDialog2 = lambda *a, **k: ["C:/tmp/chosen.json"]
        self.addCleanup(lambda: delattr(cmds, "fileDialog2"))
        self.assertEqual(self.ui._ask_backup_path(), "C:/tmp/chosen.json")
        self.assertEqual(_bootstrap.OPTION_VARS[self.ui._OPTVAR_BACKUP_PATH],
                         "C:/tmp/chosen.json")

    def test_cancelling_the_file_dialog_does_not_remember_anything(self):
        from maya import cmds
        cmds.fileDialog2 = lambda *a, **k: []
        self.addCleanup(lambda: delattr(cmds, "fileDialog2"))
        self.assertFalse(self.ui._ask_backup_path())
        self.assertNotIn(self.ui._OPTVAR_BACKUP_PATH, _bootstrap.OPTION_VARS)

    def test_the_option_var_is_namespaced(self):
        self.assertTrue(
            self.ui._OPTVAR_BACKUP_PATH.startswith(self.module.NAMESPACE + "_"))


class BackupChooserCase(unittest.TestCase):
    """**読み込む控えを選べること。**

    既定（シーンの隣）だけでは届かない場面がある — 未保存シーンで自分で
    置いた控え、別名保存で置いてきた前のシーンの控え、共有フォルダの控え。
    """

    def setUp(self):
        import tempfile
        _bootstrap.reset_registry()
        self.module = _bootstrap.reload_tool()
        self.ui = self.module.ui
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _write(self, name, sets):
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(core.catalog_to_text(sets))
        return path

    def _dialog_returns(self, value):
        from maya import cmds
        cmds.fileDialog2 = lambda *a, **k: value
        self.addCleanup(lambda: delattr(cmds, "fileDialog2"))

    def test_the_scene_neighbour_is_the_default(self):
        self.ui._scene_path = lambda: "C:/work/shot010.ma"
        self.assertEqual(self.ui._backup_path(),
                         "C:/work/shot010.color_override.json")

    def test_a_chosen_backup_wins_over_the_scene_neighbour(self):
        """選んだのに既定を見続けると、選べた意味が無い。"""
        self.ui._scene_path = lambda: "C:/work/shot010.ma"
        self.ui._remember_backup_path("D:/shared/team.json")
        self.assertEqual(self.ui._backup_path(), "D:/shared/team.json")

    def test_the_choice_does_not_follow_you_into_another_scene(self):
        """**新規シーンに前の控えが付いてくる**のを止める（実機からの指摘）。"""
        self.ui._scene_path = lambda: "C:/work/shot010.ma"
        self.ui._remember_backup_path("D:/shared/team.json")

        self.ui._scene_path = lambda: ""          # 新規シーン
        self.assertIsNone(self.ui._chosen_backup_path())
        self.assertIsNone(self.ui._backup_path())

    def test_a_dropped_choice_is_not_asked_about_again(self):
        """持ち越さないと決めたら optionVar も片付ける。"""
        self.ui._scene_path = lambda: "C:/work/shot010.ma"
        self.ui._remember_backup_path("D:/shared/team.json")
        self.ui._scene_path = lambda: "C:/work/other.ma"
        self.ui._chosen_backup_path()
        self.assertNotIn(self.ui._OPTVAR_BACKUP_PATH, _bootstrap.OPTION_VARS)
        self.assertNotIn(self.ui._OPTVAR_BACKUP_SCENE, _bootstrap.OPTION_VARS)

    def test_opening_a_scene_drops_the_choice(self):
        """未保存 → 新規シーンはシーン名では見分けられない（合図を拾う）。"""
        self.ui._scene_path = lambda: ""
        self.ui._remember_backup_path("D:/shared/team.json")
        self.assertEqual(self.ui._backup_path(), "D:/shared/team.json")
        self.ui._on_scene_changed()
        self.assertIsNone(self.ui._chosen_backup_path())

    def test_choosing_a_backup_with_sets_switches_to_it(self):
        path = self._write("team.json",
                           [{"name": "hair",
                             "items": [{"target": "|a",
                                        "color": (1.0, 0.0, 0.0)}]}])
        self._dialog_returns([path])
        self.ui._on_choose_backup()
        self.assertEqual(self.ui._backup_path(), path)

    def test_an_empty_backup_is_not_switched_to(self):
        """切り替えてから空だと、それまで見えていた控えまで見失う。"""
        path = self._write("empty.json", [])
        self._dialog_returns([path])
        self.ui._on_choose_backup()
        self.assertIsNone(self.ui._chosen_backup_path())
        self.assertTrue(_bootstrap.MESSAGES, "警告が出ていない")

    def test_a_broken_file_is_not_switched_to(self):
        path = os.path.join(self.tmp.name, "broken.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{ not json")
        self._dialog_returns([path])
        self.ui._on_choose_backup()
        self.assertIsNone(self.ui._chosen_backup_path())

    def test_cancelling_keeps_the_current_backup(self):
        self.ui._remember_backup_path("D:/shared/team.json")
        self._dialog_returns([])
        self.ui._on_choose_backup()
        self.assertEqual(self.ui._backup_path(), "D:/shared/team.json")

    def test_reset_goes_back_to_the_scene_neighbour(self):
        self.ui._scene_path = lambda: "C:/work/shot010.ma"
        self.ui._remember_backup_path("D:/shared/team.json")
        self.ui._on_reset_backup()
        self.assertIsNone(self.ui._chosen_backup_path())
        self.assertEqual(self.ui._backup_path(),
                         "C:/work/shot010.color_override.json")


class DiagnoseCase(unittest.TestCase):
    """実機から生データを持ち帰るための出力。

    **開発機に Maya が無いので、`listConnections` や `objectGrpCompList` が
    実機で何を返すかは持ち帰るしかない。** 推測で直しては外すのを繰り返した
    反省から入れたもの。
    """

    def setUp(self):
        _bootstrap.reset_registry()
        self.module = _bootstrap.reload_tool()
        self.ui = self.module.ui

    def test_diagnose_is_exposed_on_the_package(self):
        self.assertTrue(callable(getattr(self.module, "diagnose", None)))
        self.assertIn("diagnose", self.module.__all__)

    def test_diagnose_without_a_selection_does_not_raise(self):
        _bootstrap.set_selection([])
        self.module.diagnose()

    def test_diagnose_survives_commands_that_fail(self):
        """**途中で止まらないこと。** 止まると肝心の行が出ない。"""
        from maya import cmds

        def _boom(*_a, **_k):
            raise RuntimeError("nope")

        cmds.listConnections = _boom
        self.addCleanup(lambda: delattr(cmds, "listConnections"))
        _bootstrap.set_selection(["|a|aShape"])
        self.module.diagnose()   # 例外が出なければよい

    def test_reading_an_assignment_never_raises(self):
        """**`_apply_one` の途中で落とさない。** 落ちれば色も乗らない。"""
        from maya import cmds

        def _boom(*_a, **_k):
            raise RuntimeError("nope")

        cmds.listConnections = _boom
        self.addCleanup(lambda: delattr(cmds, "listConnections"))
        self.assertEqual(self.ui._read_assignment("|a|aShape"),
                         (self.ui._DEFAULT_SG, [], True))


class SceneWatchCase(unittest.TestCase):
    """シーンの切り替えを拾って控えの選択を捨てる。"""

    def setUp(self):
        _bootstrap.reset_registry()
        self.module = _bootstrap.reload_tool()
        self.ui = self.module.ui

    def test_show_watches_for_scene_changes(self):
        self.module.show()
        events = [job.get("event") for job in _bootstrap.SCRIPT_JOBS.values()]
        watched = [event[0] for event in events if event]
        self.assertIn("NewSceneOpened", watched)
        self.assertIn("SceneOpened", watched)

    def test_the_jobs_die_with_the_window(self):
        """外し忘れて残り続けないこと（ウィンドウに紐付ける）。"""
        self.module.show()
        parents = [job.get("parent") for job in _bootstrap.SCRIPT_JOBS.values()]
        self.assertEqual(set(parents), {self.ui.WINDOW})


class RenderSetupProbeCase(unittest.TestCase):
    """レンダーセットアップの下調べ（v1.0.0 の判断材料を実機から持ち帰る）。

    **開発機には `maya.app.renderSetup` そのものが無い。** ここで押さえられるのは
    「無い環境で落ちないこと」だけで、API の呼び方は実機の出力を見るしかない。
    """

    def setUp(self):
        _bootstrap.reset_registry()
        self.module = _bootstrap.reload_tool()
        self.ui = self.module.ui

    def test_it_is_exposed_on_the_package(self):
        self.assertTrue(
            callable(getattr(self.module, "probe_render_setup", None)))
        self.assertIn("probe_render_setup", self.module.__all__)

    def test_it_does_not_raise_without_render_setup(self):
        """import できない環境でも、そのことを出して終わること。"""
        self.module.probe_render_setup()

    def test_looking_only_does_not_touch_the_scene(self):
        """**既定はシーンを一切変更しない。** 調べるだけのつもりで壊さない。"""
        self.module.probe_render_setup()
        touched = [name for name, _a, _k in _bootstrap.CALLS
                   if name in ("shadingNode", "setAttr", "connectAttr",
                               "delete", "createRenderLayer")]
        self.assertEqual(touched, [])

    def test_trying_without_a_selection_is_a_no_op(self):
        _bootstrap.set_selection([])
        self.module.probe_render_setup(try_it=True)

    def test_cleanup_does_not_raise(self):
        self.module.probe_render_setup(cleanup=True)

    def test_probe_nodes_carry_the_namespace(self):
        """調査で作るものも他人のノードとぶつからない札を付ける。"""
        self.assertTrue(self.ui._PROBE_SUFFIX)
        self.assertTrue(
            (self.ui._NS + self.ui._PROBE_SUFFIX).startswith(
                self.module.NAMESPACE + "_"))


class _FakeRenderSetup(object):
    """`renderlayer` の差し替え。 **呼ばれた内容だけを記録する。**

    実物は `maya.app.renderSetup` を使うので開発機では動かない。 ここで
    押さえるのは「割り当てを触らないこと」と「呼ぶ順番」まで。
    """

    def __init__(self, fail=False):
        from color_override import renderlayer as real
        self.RenderSetupError = real.RenderSetupError
        self.fail = fail
        self.calls = []
        self.collections = {}
        self.visible = False

    def _log(self, name, *args):
        self.calls.append((name,) + args)

    def available(self):
        return True

    def create_collection(self, layer, name, nodes, engine):
        self._log("create_collection", layer, name, tuple(nodes), engine)
        if self.fail:
            raise self.RenderSetupError("作れません")
        self.collections[name] = {"nodes": list(nodes), "enabled": True}
        return name

    def set_collection_members(self, layer, name, nodes):
        self._log("set_collection_members", layer, name, tuple(nodes))
        self.collections.setdefault(name, {})["nodes"] = list(nodes)
        return True

    def collection_members(self, layer, name):
        return list(self.collections.get(name, {}).get("nodes", []))

    def set_collection_enabled(self, layer, name, enabled):
        self._log("set_collection_enabled", layer, name, enabled)
        self.collections.setdefault(name, {})["enabled"] = enabled
        return True

    def collection_is_enabled(self, layer, name):
        return bool(self.collections.get(name, {}).get("enabled"))

    def delete_collection(self, layer, name):
        self._log("delete_collection", layer, name)
        self.collections.pop(name, None)
        return True

    def collection_count(self, layer):
        return len(self.collections)

    def layer_is_visible(self, layer):
        return self.visible

    def show_layer(self, layer):
        self._log("show_layer", layer)
        self.visible = True
        return "someOtherLayer"

    def show_default_layer(self, previous=""):
        self._log("show_default_layer", previous)
        self.visible = False

    def delete_layer(self, layer):
        self._log("delete_layer", layer)
        return True


class RenderLayerModeCase(unittest.TestCase):
    """**v1.0.0 の核心 — 掛けるときに割り当てを触らない。**

    マテリアルを差し替える方式は、掛けた時点でフェース単位の割り当てを
    落とす。 レンダーセットアップのマテリアルオーバーライドは割り当てを
    触らないので、その問題が起きる構造そのものが無い。
    """

    SHAPE = "|a|aShape"

    def setUp(self):
        from maya import cmds
        _bootstrap.reset_registry()
        self.module = _bootstrap.reload_tool()
        self.ui = self.module.ui
        self.fake = _FakeRenderSetup()
        self.ui.renderlayer = self.fake
        self.ui._mode = lambda: self.ui._MODE_LAYER
        cmds.objExists = lambda *a, **k: True
        self.addCleanup(lambda: delattr(cmds, "objExists"))

    def _apply(self, node=SHAPE):
        records, index = [], {}
        self.records = records
        return self.ui._apply_one(node, (1.0, 0.0, 0.0), "Set 1", records,
                                  index, self.ui._assignment_resolver([]))

    def _force_element_calls(self):
        return [kwargs.get("forceElement") for name, _a, kwargs
                in _bootstrap.CALLS
                if name == "sets" and kwargs.get("forceElement")]

    # -- 掛ける --------------------------------------------------------------

    def test_applying_never_touches_the_assignment(self):
        """**これが v1.0.0 の存在理由。** `forceElement` を一度も呼ばない。"""
        self.assertIsNotNone(self._apply())
        self.assertEqual(self._force_element_calls(), [],
                         "割り当てを書き換えている")

    def test_it_creates_a_collection_for_the_shapes(self):
        self._apply()
        created = [call for call in self.fake.calls
                   if call[0] == "create_collection"]
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0][3], (self.SHAPE,))

    def test_the_collection_name_is_written_to_the_shader(self):
        """記録の情報源はシーン側。 開き直しても戻せるようにする。"""
        self._apply()
        written = [args[1] for name, args, _k in _bootstrap.CALLS
                   if name == "setAttr" and len(args) > 1
                   and str(args[0]).endswith(self.ui._ATTR_COLLECTION)]
        self.assertEqual(len(written), 1)
        self.assertIn(written[0], self.fake.collections)

    def test_applying_shows_the_layer(self):
        """掛けても表示レイヤーが切り替わらなければ、色は出ない。"""
        self._apply()
        self.assertIn("show_layer",
                      [call[0] for call in self.fake.calls])

    def test_a_failure_leaves_no_stray_nodes(self):
        """途中で失敗したときに、使われないシェーダーを残さない。"""
        self.fake.fail = True
        self.assertIsNone(self._apply())
        deleted = [args for name, args, _k in _bootstrap.CALLS
                   if name == "delete"]
        self.assertEqual(len(deleted), 2, "シェーダーと SG を片付けていない")
        self.assertTrue(_bootstrap.MESSAGES, "警告が出ていない")

    # -- 隠す / 戻す ---------------------------------------------------------

    def _record(self, enabled=True):
        return {"shader": "shd", "sg": "sg", "collection": "col",
                "target": self.SHAPE, "members": [self.SHAPE],
                "originals": [""], "faces": {}, "enabled": enabled}

    def test_hiding_only_disables_the_collection(self):
        """**外すときも割り当てを触らない。**"""
        self.fake.collections["col"] = {"nodes": [self.SHAPE], "enabled": True}
        self.ui._collect_records = lambda: []
        self.assertEqual(self.ui._disable_records([self._record()]), 1)
        self.assertEqual(self._force_element_calls(), [])
        self.assertIn(("set_collection_enabled", self.ui._LAYER_NAME, "col",
                       False), self.fake.calls)

    def test_hiding_everything_leaves_the_layer(self):
        """全部外したら元の表示レイヤーへ帰す（表示を奪ったままにしない）。"""
        self.fake.collections["col"] = {"nodes": [self.SHAPE], "enabled": True}
        self.ui._collect_records = lambda: []
        self.ui._disable_records([self._record()])
        self.assertIn("show_default_layer",
                      [call[0] for call in self.fake.calls])

    def test_showing_again_enables_the_collection(self):
        self.fake.collections["col"] = {"nodes": [self.SHAPE], "enabled": False}
        self.assertEqual(self.ui._enable_records([self._record(False)]), 1)
        self.assertIn(("set_collection_enabled", self.ui._LAYER_NAME, "col",
                       True), self.fake.calls)

    def test_restoring_does_not_put_anything_back(self):
        """**戻す先が無い。** 触れば逆に壊す。"""
        self.ui._return_to_originals([self._record()])
        self.assertEqual(self._force_element_calls(), [])

    def test_deleting_removes_the_collection(self):
        self.fake.collections["col"] = {"nodes": [self.SHAPE], "enabled": True}
        self.ui._delete_override(self._record())
        self.assertIn(("delete_collection", self.ui._LAYER_NAME, "col"),
                      self.fake.calls)

    def test_a_released_shape_leaves_the_collection(self):
        """1 シェイプ = 1 オーバーライド。 古いほうに残すと色が不定になる。"""
        record = self._record()
        record["members"] = [self.SHAPE, "|b|bShape"]
        records = [record]
        index = core.index_by_object(records)
        self.ui._release_members(records, index, [self.SHAPE])
        self.assertIn(("set_collection_members", self.ui._LAYER_NAME, "col",
                       ("|b|bShape",)), self.fake.calls)


class ModeCase(unittest.TestCase):
    """掛け方の選択。"""

    def setUp(self):
        _bootstrap.reset_registry()
        self.module = _bootstrap.reload_tool()
        self.ui = self.module.ui

    def test_it_falls_back_when_render_setup_is_missing(self):
        """**開発機にもこの環境にもレンダーセットアップは無い。**

        使えないときに既定がレンダーレイヤーのままだと、色が掛からない。
        """
        self.assertFalse(self.module.renderlayer.available())
        self.assertEqual(self.ui._mode(), self.ui._MODE_SHADER)

    def test_the_choice_is_remembered(self):
        self.ui._set_mode(self.ui._MODE_SHADER)
        self.assertEqual(self.ui._mode(), self.ui._MODE_SHADER)
        self.assertEqual(_bootstrap.OPTION_VARS[self.ui._OPTVAR_MODE],
                         self.ui._MODE_SHADER)

    def test_a_broken_stored_value_falls_back(self):
        from maya import cmds
        cmds.optionVar(sv=(self.ui._OPTVAR_MODE, "nonsense"))
        self.assertEqual(self.ui._mode(), self.ui._MODE_SHADER)

    def test_the_option_var_is_namespaced(self):
        for key in (self.ui._OPTVAR_MODE, self.ui._OPTVAR_PREV_LAYER):
            with self.subTest(key=key):
                self.assertTrue(key.startswith(self.module.NAMESPACE + "_"))

    def test_the_layer_name_is_namespaced(self):
        """シーンに作るレイヤーも他人のものとぶつからない札を付ける。"""
        self.assertTrue(
            self.ui._LAYER_NAME.startswith(self.module.NAMESPACE + "_"))

    def test_the_window_offers_both_modes(self):
        self.module.show()
        self.assertIn("mode", self.ui._CTRL)
        stored = _bootstrap.CONTROLS[self.ui._CTRL["mode"]]
        self.assertEqual(stored.get("numberOfRadioButtons"), 2)

    def test_the_unusable_mode_is_disabled_in_the_window(self):
        """使えない掛け方を選べてしまうと、押しても色が出ない。"""
        self.module.show()
        stored = _bootstrap.CONTROLS[self.ui._CTRL["mode"]]
        self.assertFalse(stored.get("enable1"))


if __name__ == "__main__":
    unittest.main()
