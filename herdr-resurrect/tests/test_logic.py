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

    def test_normalize_strips_windows_exe_suffix_and_path(self):
        # herdr on Windows reports foreground names with the .exe suffix; the
        # whitelist lists bare names, so normalize must strip it (case-insensitive)
        # for is_capturable to match. Also handle Windows-style paths.
        self.assertEqual(whitelist.normalize_name("nvim.exe"), "nvim")
        self.assertEqual(whitelist.normalize_name("BTOP.EXE"), "BTOP")
        self.assertEqual(whitelist.normalize_name("lazygit.cmd"), "lazygit")
        self.assertEqual(
            whitelist.normalize_name(r"C:\Program Files\nvim\nvim.exe"), "nvim")

    def test_windows_exe_name_is_capturable(self):
        wl = whitelist.effective_whitelist({})
        # "nvim.exe" would fail a bare-name lookup; normalization makes it match.
        self.assertTrue(whitelist.is_capturable(
            whitelist.normalize_name("nvim.exe"), "nvim.exe", wl, []))

    def test_pwsh_is_recognized_as_shell(self):
        self.assertTrue(whitelist.is_shell("pwsh.exe"))
        self.assertTrue(whitelist.is_shell("powershell.exe"))
        self.assertTrue(whitelist.is_shell("cmd.exe"))

    def test_foreground_program_idle_when_only_pwsh_by_name(self):
        # A pwsh sub-shell whose pid != shell_pid must still read as idle.
        pinfo = {"shell_pid": 10, "foreground_processes": [
            {"pid": 11, "name": "pwsh.exe", "argv": ["pwsh.exe"]}]}
        self.assertIsNone(whitelist.foreground_program(pinfo))

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

    def test_unmaterialized_layout_preserved_within_boot_grace(self):
        # Reboot: the periodic save (OnBootSec=2min) fired before herdr rebuilt
        # the layout, so live is empty. The program must still be carried forward
        # -- dropping it here is what clobbers the restore source. restore() will
        # harmlessly skip it if the pane never returns.
        prev = [_snap(pane="w1:p1", name="btop")]
        merged = resurrect._merge_preserving([], prev, live=[], uptime_sec=60)
        self.assertEqual([s.name for s in merged], ["btop"])

    def test_unmatched_pane_dropped_in_steady_state(self):
        # Long past boot, single pane vanished (workspace removed): not a restart
        # signature (ratio 0.25 < 0.5) -> dropped so it doesn't linger.
        prev = [_snap(pane=f"w1:p{i}", name=n)
                for i, n in enumerate(["btop", "nvtop", "lazygit", "yazi"], 1)]
        new = [s for s in prev if s.name != "yazi"]
        live = [_live(pane=f"w1:p{i}", fg=("x", ["x"])) for i in range(1, 4)]
        # yazi's pane is gone entirely (not in live).
        merged = resurrect._merge_preserving(new, prev, live, uptime_sec=99999)
        self.assertNotIn("yazi", [s.name for s in merged])
        self.assertEqual(len(merged), 3)

    def test_busy_pane_not_shadowed(self):
        # Pane came back running a different (non-whitelisted) program: don't
        # carry forward the old one over it.
        prev = [_snap(pane="w1:p1", name="btop")]
        live = [_live(pane="w1:p1", fg=("vim", ["vim"]))]
        merged = resurrect._merge_preserving([], prev, live, uptime_sec=60)
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


from unittest import mock  # noqa: E402


def _labelpane(label="panel:yazi", pane="w1:p1", shell_pid=100, fg=None,
               agent_status="unknown", session="default"):
    """A live-pane dict with a pane label + shell pid, as label restore reads it."""
    return {"_session": session, "pane_id": pane, "label": label,
            "_shell_pid": shell_pid, "_fg": fg, "agent_status": agent_status}


class TestLabelMatch(unittest.TestCase):
    def test_exact_label_match(self):
        self.assertEqual(
            resurrect.match_label_command("panel:yazi", {"panel:yazi": "yazi"}),
            "yazi")

    def test_bare_suffix_match(self):
        # Config keyed on the bare name still matches a "panel:yazi" label.
        self.assertEqual(
            resurrect.match_label_command("panel:lazygit", {"lazygit": "lazygit"}),
            "lazygit")

    def test_no_match_and_empty_label(self):
        self.assertIsNone(resurrect.match_label_command("panel:btop", {"yazi": "y"}))
        self.assertIsNone(resurrect.match_label_command("", {"yazi": "y"}))


class TestCommandProgram(unittest.TestCase):
    def test_extracts_normalized_program(self):
        self.assertEqual(resurrect._command_program("yazi"), "yazi")
        self.assertEqual(
            resurrect._command_program(r"C:\miniforge3\python.exe -m src.main"),
            "python")
        self.assertEqual(resurrect._command_program("lazygit.exe --path ."),
                         "lazygit")


class TestLabelPaneBusy(unittest.TestCase):
    def test_busy_only_when_target_program_is_a_child(self):
        # Target program running -> busy.
        with mock.patch.object(resurrect.pane_busy, "shell_child_names",
                               return_value={"yazi"}):
            self.assertTrue(resurrect._label_pane_busy(_labelpane(), "yazi"))

    def test_transient_prompt_child_is_not_busy(self):
        # An idle shell momentarily has oh-my-posh as a child; target is yazi.
        with mock.patch.object(resurrect.pane_busy, "shell_child_names",
                               return_value={"oh-my-posh", "git"}):
            self.assertFalse(resurrect._label_pane_busy(_labelpane(), "yazi"))

    def test_no_children_is_not_busy(self):
        with mock.patch.object(resurrect.pane_busy, "shell_child_names",
                               return_value=set()):
            self.assertFalse(resurrect._label_pane_busy(_labelpane(), "yazi"))

    def test_falls_back_to_fg_when_os_unknown(self):
        with mock.patch.object(resurrect.pane_busy, "shell_child_names",
                               return_value=None):
            self.assertTrue(resurrect._label_pane_busy(
                _labelpane(fg=("yazi", ["yazi"])), "yazi"))
            self.assertFalse(resurrect._label_pane_busy(
                _labelpane(fg=None), "yazi"))
            # fg is a different program -> not busy for this label.
            self.assertFalse(resurrect._label_pane_busy(
                _labelpane(fg=("btop", ["btop"])), "yazi"))


class TestRestoreFromLabels(unittest.TestCase):
    def _run(self, live, label_commands, child_names, dry_run=True):
        result = resurrect.RestoreResult(dry_run=dry_run)
        with mock.patch.object(resurrect.pane_busy, "shell_child_names",
                               return_value=child_names):
            resurrect._restore_from_labels(label_commands, live, result,
                                           dry_run=dry_run)
        return result

    def test_idle_labeled_pane_is_restored(self):
        live = [_labelpane(label="panel:yazi", pane="w1:p1")]
        r = self._run(live, {"panel:yazi": "yazi"}, child_names=set())
        self.assertEqual(r.labels_restored, [("panel:yazi", "w1:p1", "yazi")])
        self.assertEqual(r.labels_already, [])

    def test_busy_labeled_pane_is_skipped(self):
        live = [_labelpane(label="panel:yazi")]
        r = self._run(live, {"panel:yazi": "yazi"}, child_names={"yazi"})
        self.assertEqual(r.labels_restored, [])
        self.assertEqual(r.labels_already, [("panel:yazi", "yazi")])

    def test_idle_with_prompt_child_is_restored(self):
        # oh-my-posh child present but the target (yazi) is not -> still restore.
        live = [_labelpane(label="panel:yazi", pane="w1:p1")]
        r = self._run(live, {"panel:yazi": "yazi"}, child_names={"oh-my-posh"})
        self.assertEqual(r.labels_restored, [("panel:yazi", "w1:p1", "yazi")])

    def test_unconfigured_label_ignored(self):
        live = [_labelpane(label="panel:htop")]
        r = self._run(live, {"panel:yazi": "yazi"}, child_names=set())
        self.assertEqual(r.labels_restored, [])

    def test_agent_pane_skipped(self):
        live = [_labelpane(label="panel:yazi", agent_status="working")]
        r = self._run(live, {"panel:yazi": "yazi"}, child_names=set())
        self.assertEqual(r.labels_restored, [])

    def test_non_dry_run_invokes_pane_run(self):
        live = [_labelpane(label="panel:usage", pane="w1:p2")]
        with mock.patch.object(resurrect.herdr_api, "pane_run") as pr, \
                mock.patch.object(resurrect.pane_busy, "shell_child_names",
                                  return_value=set()):
            result = resurrect.RestoreResult(dry_run=False)
            resurrect._restore_from_labels({"panel:usage": "py -m app"}, live,
                                           result, dry_run=False)
        pr.assert_called_once_with("default", "w1:p2", "py -m app")
        self.assertEqual(result.labels_restored,
                         [("panel:usage", "w1:p2", "py -m app")])


if __name__ == "__main__":
    unittest.main()
