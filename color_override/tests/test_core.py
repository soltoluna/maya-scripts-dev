# -*- coding: utf-8 -*-
"""`core.py` の純ロジックの回帰テスト。

**このワークスペースで「実機と同じ結果が出る」ことを確かめられる唯一の層。**
開発機に Maya が無いので、`cmds` を呼ぶコードは実機に持っていくまで一度も
実行されない。 判断をここに寄せた分だけ、押さえられる範囲が広がる。
"""

from __future__ import annotations

import doctest
import json
import unittest

import _bootstrap  # noqa: F401  （maya スタブの注入。 他の import より前）

from color_override import core


def load_tests(loader, tests, ignore):
    """docstring の使用例も実行する（例が古くなるのを防ぐ）。"""
    tests.addTests(doctest.DocTestSuite(core))
    return tests


class ClampCase(unittest.TestCase):

    def test_clamps_both_ends(self):
        self.assertEqual(core.clamp01(-0.5), 0.0)
        self.assertEqual(core.clamp01(1.5), 1.0)
        self.assertEqual(core.clamp01(0.25), 0.25)

    def test_accepts_int(self):
        self.assertEqual(core.clamp01(1), 1.0)
        self.assertIsInstance(core.clamp01(0), float)


class ColorCase(unittest.TestCase):

    def test_color_is_stable_for_the_same_index(self):
        """掛け直しても色が入れ替わらないこと（乱数を使わない理由そのもの）。"""
        self.assertEqual(core.color_at(7), core.color_at(7))

    def test_channels_stay_in_range(self):
        for index in range(0, 64):
            for channel in core.color_at(index):
                self.assertGreaterEqual(channel, 0.0)
                self.assertLessEqual(channel, 1.0)

    def test_negative_index_is_rejected(self):
        with self.assertRaises(ValueError):
            core.color_at(-1)

    def test_many_colors_do_not_repeat(self):
        """等間隔だと周期で色が戻る。 黄金比でずらす理由の検査。"""
        colors = core.distinct_colors(64)
        self.assertEqual(len(colors), 64)
        self.assertEqual(len(set(colors)), 64)

    def test_neighbours_are_far_apart_in_hue(self):
        """隣り合うオブジェクトの色が似ないこと（貫通の判別が目的）。"""
        colors = core.distinct_colors(12)
        for first, second in zip(colors, colors[1:]):
            distance = sum(abs(a - b) for a, b in zip(first, second))
            self.assertGreater(distance, 0.3,
                               "隣り合う色が近すぎる: %r / %r" % (first, second))

    def test_start_index_shifts_the_sequence(self):
        """既に色が付いているものと重ならない色から続けられること。"""
        self.assertEqual(core.distinct_colors(3, start_index=2),
                         core.distinct_colors(5)[2:])

    def test_zero_count_is_empty(self):
        self.assertEqual(core.distinct_colors(0), [])

    def test_negative_count_is_rejected(self):
        with self.assertRaises(ValueError):
            core.distinct_colors(-1)


class HexCase(unittest.TestCase):

    def test_parses_with_and_without_hash(self):
        self.assertEqual(core.parse_hex("#FF0000"), core.parse_hex("ff0000"))

    def test_ignores_surrounding_spaces(self):
        self.assertEqual(core.parse_hex("  #00FF00  "), (0.0, 1.0, 0.0))

    def test_rejects_bad_input(self):
        for bad in ("", None, "#FFF", "#GGGGGG", "1234567", "red"):
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    core.parse_hex(bad)

    def test_round_trips(self):
        for text in ("#000000", "#FFFFFF", "#123456", "#AABBCC"):
            with self.subTest(value=text):
                self.assertEqual(core.to_hex(core.parse_hex(text)), text)

    def test_to_hex_clamps_out_of_range(self):
        self.assertEqual(core.to_hex((2.0, -1.0, 0.5)), "#FF0080")

    def test_to_hex_rejects_wrong_length(self):
        for bad in ((1.0, 0.0), (1.0, 0.0, 0.0, 1.0), None, ()):
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    core.to_hex(bad)


class NameCase(unittest.TestCase):

    def test_short_name_strips_the_dag_path(self):
        self.assertEqual(core.short_name("|grp|sub|pSphere1"), "pSphere1")
        self.assertEqual(core.short_name("pSphere1"), "pSphere1")
        self.assertEqual(core.short_name(None), "")

    def test_sanitize_replaces_namespace_and_path(self):
        """`:` や `|` を残したまま shadingNode(name=...) に渡すと実機で落ちる。"""
        self.assertEqual(core.sanitize_identifier("|grp|char:body_geo"),
                         "char_body_geo")

    def test_sanitize_avoids_leading_digit(self):
        self.assertEqual(core.sanitize_identifier("123abc"), "_123abc")

    def test_sanitize_falls_back_when_nothing_is_left(self):
        self.assertEqual(core.sanitize_identifier(""), "node")
        self.assertEqual(core.sanitize_identifier("::"), "node")
        self.assertEqual(core.sanitize_identifier("x", fallback="geo"), "x")

    def test_override_node_names_are_namespaced(self):
        shader, shading_set = core.override_node_names("ntk_color_override",
                                                       "|grp|pSphere1")
        self.assertEqual(shader, "ntk_color_override_pSphere1_SHD")
        self.assertEqual(shading_set, "ntk_color_override_pSphere1_SG")
        self.assertNotEqual(shader, shading_set)


class RecordCase(unittest.TestCase):

    def setUp(self):
        self.records = [
            {"target": "|grp|head_geo", "color": (1.0, 0.0, 0.0)},
            {"target": "|grp|body_geo", "color": (0.0, 1.0, 0.0)},
        ]

    def test_unique_keeps_order(self):
        self.assertEqual(core.unique(["b", "a", "b", "c", "a"]),
                         ["b", "a", "c"])
        self.assertEqual(core.unique(None), [])

    def test_match_by_full_path(self):
        found = core.match_records(self.records, ["|grp|body_geo"])
        self.assertEqual([rec["target"] for rec in found], ["|grp|body_geo"])

    def test_match_by_short_name(self):
        """ビューポート選択とアウトライナ選択で `cmds.ls` の返す形が変わる。"""
        found = core.match_records(self.records, ["body_geo"])
        self.assertEqual([rec["target"] for rec in found], ["|grp|body_geo"])

    def test_match_keeps_record_order(self):
        found = core.match_records(self.records, ["body_geo", "head_geo"])
        self.assertEqual([rec["target"] for rec in found],
                         ["|grp|head_geo", "|grp|body_geo"])

    def test_empty_selection_matches_nothing(self):
        self.assertEqual(core.match_records(self.records, []), [])
        self.assertEqual(core.match_records(self.records, None), [])

    def test_unknown_selection_matches_nothing(self):
        self.assertEqual(core.match_records(self.records, ["nope"]), [])

    def test_next_start_index(self):
        self.assertEqual(core.next_start_index(self.records), 2)
        self.assertEqual(core.next_start_index([]), 0)
        self.assertEqual(core.next_start_index(None), 0)


class PeekCase(unittest.TestCase):
    """一時解除（peek）の判断まわり。"""

    def test_members_round_trip(self):
        members = ["|grp|a|aShape", "|grp|b|bShape"]
        self.assertEqual(core.split_members(core.join_members(members)),
                         members)

    def test_members_drop_empty_entries(self):
        self.assertEqual(core.join_members(["a", "", None, "b"]), "a;b")
        self.assertEqual(core.split_members(";;a;;b;"), ["a", "b"])
        self.assertEqual(core.split_members(None), [])

    def test_any_enabled_defaults_to_true(self):
        """v0.1.0 で作られた記録を解除済みと誤判定しないこと。"""
        self.assertTrue(core.any_enabled([{"target": "a"}]))

    def test_any_enabled(self):
        self.assertTrue(core.any_enabled([{"enabled": False},
                                          {"enabled": True}]))
        self.assertFalse(core.any_enabled([{"enabled": False}]))
        self.assertFalse(core.any_enabled([]))
        self.assertFalse(core.any_enabled(None))

    def test_group_by_original_merges_the_same_destination(self):
        """戻し先が同じものが 1 回の cmds.sets にまとまること。"""
        grouped = core.group_by_original([
            {"original": "sgA", "members": ["a1", "a2"]},
            {"original": "sgB", "members": ["b1"]},
            {"original": "sgA", "members": ["a3"]},
        ])
        self.assertEqual(grouped, [("sgA", ["a1", "a2", "a3"]),
                                   ("sgB", ["b1"])])

    def test_group_by_original_skips_empty_groups(self):
        self.assertEqual(core.group_by_original([{"original": "sgA"}]), [])
        self.assertEqual(core.group_by_original([]), [])
        self.assertEqual(core.group_by_original(None), [])

    def test_index_finds_a_record_by_every_name(self):
        record = {"target": "|grp|body", "members": ["|grp|body|bodyShape"]}
        index = core.index_by_object([record])
        for key in ("|grp|body", "body", "|grp|body|bodyShape", "bodyShape"):
            with self.subTest(key=key):
                self.assertIs(index[key], record)

    def test_index_ignores_unknown_names(self):
        index = core.index_by_object([{"target": "a"}])
        self.assertNotIn("b", index)

    def test_index_of_nothing_is_empty(self):
        self.assertEqual(core.index_by_object([]), {})
        self.assertEqual(core.index_by_object(None), {})

    def test_index_keeps_the_first_record_for_a_duplicate_short_name(self):
        """別グループに同名がある場合、フルパスでは必ず正しく引けること。"""
        first = {"target": "|a|body", "members": []}
        second = {"target": "|b|body", "members": []}
        index = core.index_by_object([first, second])
        self.assertIs(index["|a|body"], first)
        self.assertIs(index["|b|body"], second)
        self.assertIs(index["body"], first)

    def test_align_pairs_members_with_their_own_destination(self):
        """グループの中身がばらばらのマテリアルでも戻せること。"""
        self.assertEqual(core.align_originals(["a", "b"], ["sgA", "sgB"]),
                         [("a", "sgA"), ("b", "sgB")])

    def test_align_falls_back_for_old_scenes(self):
        """v0.2.0 までのシーンには originals が無い（旧形式の単一値で埋める）。"""
        self.assertEqual(core.align_originals(["a", "b"], [], fallback="sgX"),
                         [("a", "sgX"), ("b", "sgX")])

    def test_align_falls_back_when_lengths_disagree(self):
        """食い違ったまま zip すると、無関係な SG へ戻して事故になる。"""
        self.assertEqual(core.align_originals(["a", "b"], ["sgA"],
                                              fallback="sgX"),
                         [("a", "sgX"), ("b", "sgX")])

    def test_align_of_nothing(self):
        self.assertEqual(core.align_originals(None, None), [])

    def test_group_splits_a_record_across_destinations(self):
        """1 件の記録の中でも戻し先が違えば分かれること（グループ対応の核心）。"""
        grouped = core.group_by_original([
            {"members": ["hair1", "hair2", "skin1"],
             "originals": ["sgHair", "sgHair", "sgSkin"]},
        ])
        self.assertEqual(grouped, [("sgHair", ["hair1", "hair2"]),
                                   ("sgSkin", ["skin1"])])

    def test_group_still_handles_the_old_single_original(self):
        grouped = core.group_by_original([{"original": "sgA",
                                           "members": ["a", "b"]}])
        self.assertEqual(grouped, [("sgA", ["a", "b"])])

    def test_match_finds_a_group_record_from_a_child_shape(self):
        """子を選んで Restore しても、それを抱えている記録が見つかること。"""
        record = {"target": "|hair_grp",
                  "members": ["|hair_grp|a|aShape", "|hair_grp|b|bShape"]}
        self.assertEqual(core.match_records([record], ["|hair_grp|b|bShape"]),
                         [record])
        self.assertEqual(core.match_records([record], ["bShape"]), [record])

    def test_match_does_not_return_a_record_twice(self):
        record = {"target": "|g", "members": ["|g|a|aShape"]}
        found = core.match_records([record], ["|g", "|g|a|aShape"])
        self.assertEqual(found, [record])


class SetCase(unittest.TestCase):
    """セット — まとめて掛けたものを 1 行に畳む単位。"""

    def test_new_name_counts_up_from_the_highest(self):
        """空き番号を埋めると、片付けたセットと同名の別物ができる。"""
        self.assertEqual(core.new_set_name([]), "Set 1")
        self.assertEqual(core.new_set_name(["Set 1", "Set 3"]), "Set 4")

    def test_new_name_ignores_renamed_sets(self):
        self.assertEqual(core.new_set_name(["hair", "body 2"]), "Set 1")

    def test_normalize_collapses_whitespace(self):
        self.assertEqual(core.normalize_set_name("  hair   check "),
                         "hair check")

    def test_normalize_falls_back(self):
        self.assertEqual(core.normalize_set_name(""), core.UNNAMED_SET)
        self.assertEqual(core.normalize_set_name(None, "Set 9"), "Set 9")

    def test_normalize_caps_the_length(self):
        self.assertLessEqual(len(core.normalize_set_name("x" * 200)), 64)

    def test_group_counts_members_not_records(self):
        """1 行に「何オブジェクトか」を出すため。"""
        sets = core.group_by_set([
            {"set": "a", "members": ["x", "y"], "color": (1.0, 0.0, 0.0)},
            {"set": "a", "members": ["z"], "color": (1.0, 0.0, 0.0)},
        ])
        self.assertEqual(len(sets), 1)
        self.assertEqual(sets[0]["count"], 3)

    def test_records_without_a_set_go_to_unnamed(self):
        """v0.3.0 以前に掛けたものを開いても行方不明にしない。"""
        sets = core.group_by_set([{"members": ["x"], "color": (0, 0, 0)}])
        self.assertEqual(sets[0]["name"], core.UNNAMED_SET)

    def test_group_keeps_first_seen_order(self):
        sets = core.group_by_set([{"set": "b", "members": ["1"]},
                                  {"set": "a", "members": ["2"]},
                                  {"set": "b", "members": ["3"]}])
        self.assertEqual([s["name"] for s in sets], ["b", "a"])

    def test_a_set_is_enabled_when_any_record_shows(self):
        sets = core.group_by_set([{"set": "a", "members": [], "enabled": False},
                                  {"set": "a", "members": ["x"],
                                   "enabled": True}])
        self.assertTrue(sets[0]["enabled"])

    def test_items_drop_records_without_a_target(self):
        self.assertEqual(core.set_items_from_records([{"color": (1, 0, 0)}]),
                         [])

    def test_swatches_collapse_a_single_colour(self):
        """12 個に 1 色を掛けたセットは見本 1 個で足りる。"""
        shown, overflow = core.swatch_colors([(1.0, 0.0, 0.0)] * 12)
        self.assertEqual((shown, overflow), ([(1.0, 0.0, 0.0)], 0))

    def test_swatches_report_the_overflow(self):
        colors = core.distinct_colors(20)
        shown, overflow = core.swatch_colors(colors, limit=8)
        self.assertEqual((len(shown), overflow), (8, 12))

    def test_swatches_reject_a_useless_limit(self):
        with self.assertRaises(ValueError):
            core.swatch_colors([(1, 0, 0)], limit=0)


class CatalogCase(unittest.TestCase):
    """控え（シーンの隣に置く JSON）。"""

    def setUp(self):
        self.sets = [{"name": "hair",
                      "items": [{"target": "|a", "color": (1.0, 0.0, 0.0)},
                                {"target": "|b", "color": (0.0, 0.5, 1.0)}]}]

    def test_round_trip(self):
        text = core.catalog_to_text(self.sets, scene="C:/x/s.ma",
                                    tool_version="0.4.0")
        self.assertEqual(core.catalog_from_text(text), self.sets)

    def test_the_file_is_readable_by_a_human(self):
        text = core.catalog_to_text(self.sets)
        self.assertIn("\n", text, "1 行に潰れている（手で直せない）")
        self.assertIn('"hair"', text)

    def test_broken_items_are_dropped_but_the_rest_survives(self):
        """人が手で編集しうるファイルなので、1 か所壊れても捨てない。"""
        text = core.catalog_to_text(
            [{"name": "s", "items": [{"target": "|a", "color": (1, 0, 0)}]}])
        payload = json.loads(text)
        payload["sets"][0]["items"].append({"target": "|b", "color": [1, 0]})
        payload["sets"][0]["items"].append({"target": "", "color": [1, 0, 0]})
        payload["sets"][0]["items"].append("nonsense")
        parsed = core.catalog_from_text(json.dumps(payload))
        self.assertEqual([i["target"] for i in parsed[0]["items"]], ["|a"])

    def test_a_set_with_no_usable_item_is_dropped(self):
        parsed = core.catalog_from_text(json.dumps(
            {"tool": "color_override", "sets": [{"name": "x", "items": []}]}))
        self.assertEqual(parsed, [])

    def test_another_tools_file_is_refused(self):
        with self.assertRaises(ValueError):
            core.catalog_from_text('{"tool": "something_else", "sets": []}')

    def test_a_newer_format_is_refused(self):
        """読めない形式を黙って無視すると、控えを消したように見える。"""
        with self.assertRaises(ValueError):
            core.catalog_from_text('{"format": 99, "sets": []}')

    def test_garbage_is_refused(self):
        for bad in ("", "not json", "[]", "3"):
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    core.catalog_from_text(bad)

    def test_merge_replaces_by_name_and_appends_the_rest(self):
        merged = core.merge_catalog(
            [{"name": "a", "items": [1]}, {"name": "b", "items": [2]}],
            [{"name": "b", "items": [3]}, {"name": "c", "items": [4]}])
        self.assertEqual([s["name"] for s in merged], ["a", "b", "c"])
        self.assertEqual(merged[1]["items"], [3])

    def test_merge_of_nothing(self):
        self.assertEqual(core.merge_catalog(None, None), [])

    def test_backup_path_sits_next_to_the_scene(self):
        self.assertEqual(core.backup_path_for("C:/work/shot010.ma"),
                         "C:/work/shot010.color_override.json")

    def test_backup_path_normalises_separators(self):
        self.assertEqual(core.backup_path_for("C:\\work\\shot010.mb"),
                         "C:/work/shot010.color_override.json")

    def test_backup_path_needs_a_saved_scene(self):
        self.assertIsNone(core.backup_path_for(""))
        self.assertIsNone(core.backup_path_for(None))


if __name__ == "__main__":
    unittest.main()
