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

    スタブは割り当てを持たないので、`listConnections` / `getAttr` を
    差し替えて実機の**接続の形**だけを再現する。 実際に色が乗るかどうかは
    ここでは分からない（実機確認の項目として SPEC.md に残してある）。
    """

    SHAPE = "|a|aShape"

    def setUp(self):
        from maya import cmds
        _bootstrap.reset_registry()
        self.module = _bootstrap.reload_tool()
        self.ui = self.module.ui
        self.cmds = cmds

    def _patch(self, name, func):
        setattr(self.cmds, name, func)
        self.addCleanup(lambda: delattr(self.cmds, name))

    def _scene(self, connections, components=None, exists=True,
               paired_fails=False, simple=None):
        """割り当てを差し替える。 `connections` は `[(局所プラグ, SG プラグ)]`。

        `paired_fails` で「詳しい読み方（connections=True）だけ通らない」
        環境を再現する（簡易読み取りへの逃げ道が効くかを見るため）。
        """
        flat = [part for pair in connections for part in pair]

        def _list_connections(*_a, **kwargs):
            if kwargs.get("connections"):
                if paired_fails:
                    raise RuntimeError("flag not supported")
                return list(flat)
            return list(simple or [])

        self._patch("listConnections", _list_connections)
        table = components or {}

        def _get_attr(plug, *_a, **_k):
            if plug.endswith(".objectGrpCompList"):
                if plug[:-len(".objectGrpCompList")] not in table:
                    raise RuntimeError("no such attribute")
                return list(table[plug[:-len(".objectGrpCompList")]])
            return None

        self._patch("getAttr", _get_attr)
        self._patch("objExists", lambda *a, **k: exists)

    # -- 読み取り ------------------------------------------------------------

    def test_a_plain_shape_reads_as_a_single_destination(self):
        self._scene([("aShape.instObjGroups[0]", "lambert2SG.dagSetMembers[0]")])
        self.assertEqual(self.ui._read_assignment(self.SHAPE),
                         ("lambert2SG", [], True))

    def test_an_unassigned_shape_falls_back_to_the_maya_default(self):
        self._scene([])
        self.assertEqual(self.ui._read_assignment(self.SHAPE),
                         (self.ui._DEFAULT_SG, [], True))

    def test_face_groups_are_read_with_their_own_destination(self):
        self._scene(
            [("aShape.instObjGroups[0].objectGroups[0]", "sgA.dagSetMembers[0]"),
             ("aShape.instObjGroups[0].objectGroups[1]", "sgB.dagSetMembers[1]")],
            {"aShape.instObjGroups[0].objectGroups[0]": ["f[0:2]"],
             "aShape.instObjGroups[0].objectGroups[1]": ["f[3:5]", "f[9]"]})
        base, entries, ok = self.ui._read_assignment(self.SHAPE)
        self.assertTrue(ok)
        self.assertEqual(base, "sgA", "土台が無いときは最初の塊の SG で埋める")
        self.assertEqual(entries, [
            {"sg": "sgA", "components": ["|a|aShape.f[0:2]"]},
            {"sg": "sgB", "components": ["|a|aShape.f[3:5]", "|a|aShape.f[9]"]}])

    def test_the_pair_order_from_maya_is_not_assumed(self):
        """向きを取り違えるとシェイプ名を SG として控えてしまう。"""
        self._scene([("lambert2SG.dagSetMembers[0]", "aShape.instObjGroups[0]")])
        self.assertEqual(self.ui._read_assignment(self.SHAPE),
                         ("lambert2SG", [], True))

    def test_a_connection_that_is_not_an_assignment_is_ignored(self):
        self._scene([("aShape.message", "sgA.someAttr")])
        self.assertEqual(self.ui._read_assignment(self.SHAPE),
                         (self.ui._DEFAULT_SG, [], True))

    def test_a_junk_component_list_is_filtered(self):
        """変な名前を混ぜたまま戻すと `cmds.sets` が落ちる。 拾わない。"""
        self._scene(
            [("aShape.instObjGroups[0].objectGroups[0]", "sgA.dagSetMembers[0]")],
            {"aShape.instObjGroups[0].objectGroups[0]":
                [["f[0:2]"], "", None, "f[7]"]})
        self.assertEqual(
            self.ui._read_assignment(self.SHAPE)[1],
            [{"sg": "sgA", "components": ["|a|aShape.f[0:2]",
                                          "|a|aShape.f[7]"]}])

    def test_an_object_group_without_components_is_a_whole_assignment(self):
        """**`objectGroups` はフェース専用ではない。**

        オブジェクト全体のメンバーシップでも経由し、そのときコンポーネントは
        空になる。 v0.5.0 はこれを読み取り失敗と見なし、ふつうのシェイプにまで
        「掛けない」判断が働いて**色がまったく掛からなくなった**。
        """
        self._scene(
            [("aShape.instObjGroups[0].objectGroups[0]", "sgA.dagSetMembers[0]")],
            {"aShape.instObjGroups[0].objectGroups[0]": []})
        self.assertEqual(self.ui._read_assignment(self.SHAPE),
                         ("sgA", [], True))

    def test_such_a_shape_still_gets_a_colour(self):
        """上の判定が効いていることを、掛ける側からも押さえる。"""
        self._scene(
            [("aShape.instObjGroups[0].objectGroups[0]", "sgA.dagSetMembers[0]")],
            {"aShape.instObjGroups[0].objectGroups[0]": []})
        self.assertIsNotNone(self._apply(), "ふつうのシェイプに色が掛からない")

    def test_a_reader_that_cannot_run_falls_back_instead_of_refusing(self):
        """**色が塗れないほうが害が大きい。** 読めないなら簡易読み取りに落とす。"""
        self._scene([], paired_fails=True, simple=["lambert2SG"])
        self.assertEqual(self.ui._read_assignment(self.SHAPE),
                         ("lambert2SG", [], True))
        self.assertIsNotNone(self._apply())

    def test_an_empty_pair_list_falls_back_too(self):
        """ペアで返ってこない環境でも「掛からない」にはしない。"""
        self._scene([], simple=["lambert2SG"])
        self.assertEqual(self.ui._read_assignment(self.SHAPE),
                         ("lambert2SG", [], True))

    def test_an_unreadable_face_group_is_reported_as_not_readable(self):
        """塊が読めないなら「読めた」と言わない（掛けない判断の根拠になる）。"""
        self._scene(
            [("aShape.instObjGroups[0].objectGroups[0]", "sgA.dagSetMembers[0]")])
        self.assertFalse(self.ui._read_assignment(self.SHAPE)[2])

    # -- 掛ける --------------------------------------------------------------

    def _apply(self, node=SHAPE):
        records, index = [], {}
        return self.ui._apply_one(node, (1.0, 0.0, 0.0), "Set 1", records,
                                  index, self.ui._assignment_resolver([]))

    def test_a_shape_whose_faces_cannot_be_read_still_gets_a_colour(self):
        """**主機能を止めない。**

        v0.5.0〜v0.7.1 はここで掛けるのをやめていた（戻せなくなるくらいなら
        掛けない）。 実機ではその判断が働いて**色がまったく乗らなくなった**。
        読めないなら警告だけ出して、v0.4.0 と同じ挙動に落ちる。
        """
        self._scene(
            [("aShape.instObjGroups[0].objectGroups[0]", "sgA.dagSetMembers[0]")])
        self.assertIsNotNone(self._apply(), "色が掛からない")
        self.assertTrue(_bootstrap.MESSAGES, "読めなかったことを知らせていない")

    def test_the_face_groups_are_written_to_the_shader(self):
        """復元の情報源はシーン側。 Python の辞書に持つと開き直した時点で失う。"""
        self._scene(
            [("aShape.instObjGroups[0].objectGroups[0]", "sgA.dagSetMembers[0]")],
            {"aShape.instObjGroups[0].objectGroups[0]": ["f[0:2]"]})
        self.assertIsNotNone(self._apply())
        written = [args[1] for name, args, _k in _bootstrap.CALLS
                   if name == "setAttr" and len(args) > 1
                   and str(args[0]).endswith(self.ui._ATTR_FACES)]
        self.assertEqual(len(written), 1, "フェースの控えが書かれていない")
        self.assertEqual(core.decode_faces(written[0]),
                         {self.SHAPE: [{"sg": "sgA",
                                        "components": ["|a|aShape.f[0:2]"]}]})

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


if __name__ == "__main__":
    unittest.main()
