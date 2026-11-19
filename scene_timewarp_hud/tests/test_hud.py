# -*- coding: utf-8 -*-
"""Scene TimeWarp HUD の回帰テスト（core の純ロジック + HUD の付け外し）。

HUD の付け外しは `cmds` をテスト内の小さな偽物に差し替えて見る。
`_bootstrap` の汎用スタブは `headsUpDisplay(remove=True)` や
`scriptJob(exists=n)` を「生成」と解釈してしまうため。
**実 Maya の HUD の見た目・色の反映は実機でしか確かめられない。**
"""

from __future__ import annotations

import unittest
from unittest import mock

import _bootstrap

from scene_timewarp_hud import core


class CoreCase(unittest.TestCase):

    def test_status_text(self):
        self.assertEqual(core.status_text(False, False), "None")
        self.assertEqual(core.status_text(False, True), "None")
        self.assertEqual(core.status_text(True, True), "ON")
        self.assertEqual(core.status_text(True, False), "OFF")

    def test_color_is_red_only_when_enabled(self):
        self.assertEqual(core.color_index(True, True), core.COLOR_INDEX_ON)
        self.assertEqual(core.color_index(True, False), core.COLOR_INDEX_OFF)
        self.assertEqual(core.color_index(False, True), core.COLOR_INDEX_OFF)

    def test_color_indices_are_in_palette_range(self):
        for index in (core.COLOR_INDEX_ON, core.COLOR_INDEX_OFF):
            self.assertTrue(1 <= index <= 24)


class _FakeMaya:
    """HUD と scriptJob と displayColor だけを覚える偽物。"""

    def __init__(self, color=7):
        self.huds = {}
        self.jobs = {}
        self.color = color
        self.next_job = 100

    def headsUpDisplay(self, name=None, **kw):
        if kw.get("exists"):
            return name in self.huds
        if kw.get("remove"):
            self.huds.pop(name, None)
            return None
        if "nextFreeBlock" in kw:
            return 3
        self.huds[name] = kw
        return name

    def scriptJob(self, **kw):
        if "exists" in kw:
            return kw["exists"] in self.jobs
        if "kill" in kw:
            self.jobs.pop(kw["kill"], None)
            return None
        self.next_job += 1
        self.jobs[self.next_job] = kw
        return self.next_job

    def displayColor(self, _name, index=None, **kw):
        if kw.get("query"):
            return self.color
        self.color = index
        return None

    def attributeQuery(self, *_a, **_kw):
        return False     # タイムワープ無し

    def patches(self):
        from maya import cmds
        return [mock.patch.object(cmds, n, getattr(self, n))
                for n in ("headsUpDisplay", "scriptJob", "displayColor",
                          "attributeQuery")]


class HudCase(unittest.TestCase):

    def setUp(self):
        _bootstrap.reset_registry()
        self.module = _bootstrap.reload_tool()
        self.fake = _FakeMaya(color=7)
        for patcher in self.fake.patches():
            patcher.start()
            self.addCleanup(patcher.stop)
        self.module.hud._state().update(job=None, original=None)

    def test_toggle_installs_then_removes(self):
        hud = self.module.hud
        self.assertTrue(hud.toggle())
        self.assertIn(hud.HUD_NAME, self.fake.huds)
        self.assertEqual(len(self.fake.jobs), 1)

        self.assertFalse(hud.toggle())
        self.assertNotIn(hud.HUD_NAME, self.fake.huds)
        self.assertEqual(self.fake.jobs, {}, "scriptJob が残っている")
        self.assertEqual(self.fake.color, 7, "HUD の色が元に戻っていない")

    def test_cleanup_survives_a_hot_update(self):
        """更新でパッケージが `sys.modules` から落ちても後片付けできる。

        scriptJob の番号をモジュール変数に置いていると、更新後に止められない。
        """
        self.module.hud.install()
        updated = _bootstrap.reload_tool()          # ハブの更新と同じ状態
        updated.hud.uninstall()
        self.assertEqual(self.fake.jobs, {}, "更新後に scriptJob を止められない")
        self.assertEqual(self.fake.color, 7)

    def test_reinstall_does_not_stack_jobs(self):
        self.module.hud.install()
        self.module.hud.install()
        self.assertEqual(len(self.fake.jobs), 1)

    def test_show_reports_version(self):
        """ウィンドウが無いので、バージョンは切り替え時のメッセージに出す。"""
        self.module.show()
        messages = [kw.get("amg", "") for name, _a, kw in _bootstrap.CALLS
                    if name == "inViewMessage"]
        self.assertTrue(any(self.module.__version__ in m for m in messages),
                        "切り替え時のメッセージにバージョンが出ていない")

    def test_legacy_entry_points_remain(self):
        """単体スクリプト時代の install() / uninstall() を壊さない。"""
        self.assertTrue(callable(self.module.install))
        self.assertTrue(callable(self.module.uninstall))


if __name__ == "__main__":
    unittest.main()
