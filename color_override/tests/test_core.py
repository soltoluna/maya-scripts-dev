# -*- coding: utf-8 -*-
"""`core.py` の純ロジックの回帰テスト。

**このワークスペースで「実機と同じ結果が出る」ことを確かめられる唯一の層。**
開発機に Maya が無いので、`cmds` を呼ぶコードは実機に持っていくまで一度も
実行されない。 判断をここに寄せた分だけ、押さえられる範囲が広がる。
"""

from __future__ import annotations

import doctest
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

    def test_format_row(self):
        self.assertEqual(core.format_row(self.records[0]),
                         "head_geo   #FF0000")

    def test_format_row_survives_a_missing_color(self):
        self.assertEqual(core.format_row({"target": "a"}), "a   #000000")

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

    def test_format_row_marks_disabled_records(self):
        record = {"target": "|grp|a", "color": (0.0, 0.0, 1.0),
                  "enabled": False}
        self.assertEqual(core.format_row(record), "a   #0000FF   (off)")


if __name__ == "__main__":
    unittest.main()
