"""Unit tests for herdr-resurrect pure logic (no live herdr needed)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

import snapshot  # noqa: E402
import whitelist  # noqa: E402
from snapshot import PaneSnap  # noqa: E402


def _snap(session="default", wid="w1", label="proj", pane="w1:p1",
          cwd="/p", name="btop", argv=None):
    return PaneSnap(session, wid, label, "w1:t1", pane, cwd, name,
                    argv or [name])


class TestWhitelist(unittest.TestCase):
    def test_normalize_login_shell_and_path(self):
        self.assertEqual(whitelist.normalize_name("-zsh"), "zsh")
        self.assertEqual(whitelist.normalize_name("/usr/bin/nvim"), "nvim")

    def test_is_agent_pane(self):
        self.assertFalse(whitelist.is_agent_pane("unknown"))
        self.assertFalse(whitelist.is_agent_pane(""))
        self.assertTrue(whitelist.is_agent_pane("working"))
        self.assertTrue(whitelist.is_agent_pane("done"))

    def test_foreground_program_idle_when_only_shell(self):
        pinfo = {"shell_pid": 10, "foreground_processes": [
            {"pid": 10, "name": "zsh", "argv": ["-zsh"]}]}
        self.assertIsNone(whitelist.foreground_program(pinfo))

    def test_foreground_program_empty_is_idle(self):
        self.assertIsNone(whitelist.foreground_program(
            {"shell_pid": 10, "foreground_processes": []}))

    def test_foreground_program_returns_running(self):
        pinfo = {"shell_pid": 10, "foreground_processes": [
            {"pid": 11, "name": "btop", "argv": ["btop", "-u", "500"]}]}
        self.assertEqual(whitelist.foreground_program(pinfo),
                         ("btop", ["btop", "-u", "500"]))

    def test_effective_whitelist_add_remove(self):
        wl = whitelist.effective_whitelist(
            {"whitelist_add": ["foo"], "whitelist_remove": ["btop"]})
        self.assertIn("foo", wl)
        self.assertNotIn("btop", wl)
        self.assertIn("lazygit", wl)


class TestSnapshot(unittest.TestCase):
    def test_cmdline_quotes_whitespace_args(self):
        self.assertEqual(_snap(name="watch", argv=["watch", "-n", "5"]).cmdline,
                         "watch -n 5")
        self.assertEqual(
            _snap(name="bash", argv=["bash", "-lc", "echo hi there"]).cmdline,
            'bash -lc "echo hi there"')

    def test_match_by_pane_id(self):
        snap = _snap(pane="w1:p1")
        live = [{"_session": "default", "pane_id": "w1:p1",
                 "_workspace_label": "x", "cwd": "/y"}]
        self.assertIs(snapshot.match_live_pane(snap, live), live[0])

    def test_match_fallback_by_label_and_cwd(self):
        snap = _snap(pane="GONE", label="proj", cwd="/p", wid="w1")
        live = [{"_session": "default", "pane_id": "w9:p9",
                 "_workspace_label": "proj", "workspace_id": "w9", "cwd": "/p"}]
        self.assertIs(snapshot.match_live_pane(snap, live), live[0])

    def test_match_respects_session(self):
        snap = _snap(session="work", pane="w1:p1")
        live = [{"_session": "default", "pane_id": "w1:p1",
                 "_workspace_label": "proj", "cwd": "/p"}]
        self.assertIsNone(snapshot.match_live_pane(snap, live))


if __name__ == "__main__":
    unittest.main()
