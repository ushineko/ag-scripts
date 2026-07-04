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

    def test_cmdline_pattern_captures_generic_program(self):
        wl = whitelist.effective_whitelist({})
        pats = whitelist.cmdline_patterns({"cmdline_patterns": [r"-m src\.main --tui"]})
        # name 'python3' is not whitelisted, but the cmdline matches a pattern
        self.assertFalse("python3" in wl)
        self.assertTrue(whitelist.is_capturable(
            "python3", "/usr/bin/python3 -m src.main --tui", wl, pats))
        # an unrelated python3 invocation is still skipped
        self.assertFalse(whitelist.is_capturable(
            "python3", "/usr/bin/python3 some_other.py", wl, pats))
        # a whitelisted name is captured regardless of patterns
        self.assertTrue(whitelist.is_capturable("btop", "btop -u 500", wl, []))


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


import resurrect  # noqa: E402


def _live(session="default", pane="w1:p1", wid="w1", label="proj", cwd="/p",
          fg=None, tab="w1:t1"):
    """A live-pane dict as _annotated_live_panes() produces it. fg=None == idle."""
    return {"_session": session, "pane_id": pane, "workspace_id": wid,
            "_workspace_label": label, "cwd": cwd, "tab_id": tab, "_fg": fg}


class TestMergePreserving(unittest.TestCase):
    def test_preserves_bare_pane_within_boot_grace(self):
        # Reboot: btop's pane came back idle, so this cycle captured nothing.
        prev = [_snap(pane="w1:p1", name="btop", argv=["btop", "-u", "500"])]
        live = [_live(pane="w1:p1", fg=None)]
        merged = resurrect._merge_preserving([], prev, live, uptime_sec=60)
        self.assertEqual([s.name for s in merged], ["btop"])

    def test_mass_drop_preserves_even_outside_grace(self):
        # herdr server restart long after boot: every captured pane went idle.
        prev = [_snap(pane="w1:p1", name="btop"),
                _snap(pane="w1:p2", name="nvtop")]
        live = [_live(pane="w1:p1", fg=None), _live(pane="w1:p2", fg=None)]
        merged = resurrect._merge_preserving([], prev, live, uptime_sec=99999)
        self.assertEqual(sorted(s.name for s in merged), ["btop", "nvtop"])

    def test_single_close_in_steady_state_is_dropped(self):
        # Steady state: 1 of 4 closed -> ratio 0.25 < 0.5, past grace -> drop it.
        prev = [_snap(pane=f"w1:p{i}", name=n)
                for i, n in enumerate(["btop", "nvtop", "lazygit", "yazi"], 1)]
        new = [s for s in prev if s.name != "yazi"]
        live = [_live(pane=f"w1:p{i}", fg=("x", ["x"])) for i in range(1, 4)]
        live.append(_live(pane="w1:p4", fg=None))  # closed pane now idle
        merged = resurrect._merge_preserving(new, prev, live, uptime_sec=99999)
        self.assertNotIn("yazi", [s.name for s in merged])
        self.assertEqual(len(merged), 3)

    def test_vanished_pane_not_preserved(self):
        # Pane itself is gone (workspace removed) -> nothing to restore into.
        prev = [_snap(pane="w1:p1", name="btop")]
        merged = resurrect._merge_preserving([], prev, live=[], uptime_sec=60)
        self.assertEqual(merged, [])

    def test_running_pane_not_duplicated(self):
        # Program still running this cycle -> present in new, not re-added.
        prev = [_snap(pane="w1:p1", name="btop")]
        new = [_snap(pane="w1:p1", name="btop")]
        live = [_live(pane="w1:p1", fg=("btop", ["btop"]))]
        merged = resurrect._merge_preserving(new, prev, live, uptime_sec=60)
        self.assertEqual(len(merged), 1)

    def test_preserve_refreshes_reassigned_pane_id(self):
        # herdr gave the pane a new id after restart; match by label+cwd, keep prog.
        prev = [_snap(pane="OLD", label="proj", cwd="/p", name="btop")]
        live = [_live(pane="NEW", wid="w1", label="proj", cwd="/p", fg=None)]
        merged = resurrect._merge_preserving([], prev, live, uptime_sec=60)
        self.assertEqual(merged[0].pane_id, "NEW")
        self.assertEqual(merged[0].name, "btop")


if __name__ == "__main__":
    unittest.main()
