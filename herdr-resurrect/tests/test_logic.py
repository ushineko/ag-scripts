"""Unit tests for herdr-resurrect pure logic (no live herdr needed)."""

import argparse
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

import herdr_api  # noqa: E402
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


class TestMergePreservingUnscannedSessions(unittest.TestCase):
    """A session herdr has not started reports no panes. That silence must not
    read as 'its panes were closed' -- the bug that deleted every `work` entry
    from the snapshot ~31 min after each boot (spec 002)."""

    def test_unscanned_session_preserved_past_grace_without_mass_drop(self):
        # 3 work entries out of 24: ratio 0.125, well under the mass-drop
        # threshold, and long past boot grace. Old code dropped them for good.
        prev = ([_snap(session="default", pane=f"w1:p{i}", name="btop")
                 for i in range(1, 22)]
                + [_snap(session="work", pane=f"w1:q{i}", name="yazi")
                   for i in range(1, 4)])
        new = [s for s in prev if s.session == "default"]
        live = [_live(pane=f"w1:p{i}", fg=("btop", ["btop"])) for i in range(1, 22)]
        merged = resurrect._merge_preserving(
            new, prev, live, uptime_sec=99999, scanned_sessions={"default"})
        self.assertEqual(len(merged), 24)
        self.assertEqual(
            sorted(s.pane_id for s in merged if s.session == "work"),
            ["w1:q1", "w1:q2", "w1:q3"])

    def test_unscanned_session_excluded_from_mass_drop_ratio(self):
        # 1 of 4 scanned panes closed (0.25) plus 4 unscanned entries. Counting
        # the unscanned ones would give 5/8 >= 0.5 and wrongly resurrect the
        # deliberately-closed yazi.
        default = [_snap(session="default", pane=f"w1:p{i}", name=n)
                   for i, n in enumerate(["btop", "nvtop", "lazygit", "yazi"], 1)]
        work = [_snap(session="work", pane=f"w1:q{i}", name="btop")
                for i in range(1, 5)]
        prev = default + work
        new = [s for s in default if s.name != "yazi"]
        live = [_live(pane=f"w1:p{i}", fg=("x", ["x"])) for i in range(1, 4)]
        live.append(_live(pane="w1:p4", fg=None))
        merged = resurrect._merge_preserving(
            new, prev, live, uptime_sec=99999, scanned_sessions={"default"})
        self.assertNotIn("yazi", [s.name for s in merged])
        self.assertEqual(len(merged), 7)  # 3 default + 4 work carried forward

    def test_scanned_session_still_drops_a_deliberate_close(self):
        # Unchanged steady-state behaviour for a session we did scan.
        prev = [_snap(session="work", pane=f"w1:q{i}", name=n)
                for i, n in enumerate(["btop", "nvtop", "lazygit", "yazi"], 1)]
        new = [s for s in prev if s.name != "yazi"]
        live = [_live(session="work", pane=f"w1:q{i}", fg=("x", ["x"]))
                for i in range(1, 4)]
        live.append(_live(session="work", pane="w1:q4", fg=None))
        merged = resurrect._merge_preserving(
            new, prev, live, uptime_sec=99999, scanned_sessions={"work"})
        self.assertNotIn("yazi", [s.name for s in merged])

    def test_no_sessions_scanned_preserves_everything(self):
        # herdr up but every pane query failed: nothing was learned, keep all.
        prev = [_snap(session="default", pane="w1:p1", name="btop")]
        merged = resurrect._merge_preserving(
            [], prev, [], uptime_sec=99999, scanned_sessions=set())
        self.assertEqual([s.name for s in merged], ["btop"])

    def test_none_keeps_legacy_all_scanned_behaviour(self):
        prev = [_snap(session="work", pane=f"w1:q{i}", name=n)
                for i, n in enumerate(["btop", "nvtop", "lazygit", "yazi"], 1)]
        new = [s for s in prev if s.name != "yazi"]
        merged = resurrect._merge_preserving(new, prev, [], uptime_sec=99999,
                                             scanned_sessions=None)
        self.assertNotIn("yazi", [s.name for s in merged])


class TestAnnotatedLivePanes(unittest.TestCase):
    def _sessions(self, *specs):
        return [herdr_api.Session(name=n, default=(n == "default"), running=r)
                for n, r in specs]

    def test_reports_scanned_sessions_and_skips_stopped(self):
        with mock.patch.object(resurrect.herdr_api, "list_sessions",
                               return_value=self._sessions(
                                   ("default", True), ("work", False))), \
             mock.patch.object(resurrect.herdr_api, "list_workspace_labels",
                               return_value={"w1": "proj"}), \
             mock.patch.object(resurrect.herdr_api, "list_panes",
                               return_value=[{"pane_id": "w1:p1",
                                              "workspace_id": "w1"}]), \
             mock.patch.object(resurrect.herdr_api, "pane_process_info",
                               return_value={}):
            panes, scanned = resurrect._annotated_live_panes()
        self.assertEqual(scanned, {"default"})
        self.assertEqual([p["_session"] for p in panes], ["default"])

    def test_failed_pane_query_is_unscanned(self):
        with mock.patch.object(resurrect.herdr_api, "list_sessions",
                               return_value=self._sessions(("work", True))), \
             mock.patch.object(resurrect.herdr_api, "list_workspace_labels",
                               side_effect=herdr_api.HerdrError("boom")):
            panes, scanned = resurrect._annotated_live_panes()
        self.assertEqual(scanned, set())
        self.assertEqual(panes, [])


class TestRestoreSessionScope(unittest.TestCase):
    def _restore(self, sessions):
        snaps = [_snap(session="default", pane="w1:p1", name="btop"),
                 _snap(session="work", pane="w1:q1", name="nvtop")]
        live = [_live(session="default", pane="w1:p1", fg=None),
                _live(session="work", pane="w1:q1", fg=None)]
        for p in live:
            p["label"] = "panel:yazi"
            p["_shell_pid"] = 1
            p["agent_status"] = "unknown"
        with mock.patch.object(resurrect.config, "load",
                               return_value={"label_commands": {"panel:yazi": "yazi"}}), \
             mock.patch.object(resurrect.snapshot, "load_snaps",
                               return_value=(snaps, 0.0)), \
             mock.patch.object(resurrect, "_annotated_live_panes",
                               return_value=(live, {"default", "work"})), \
             mock.patch.object(resurrect.pane_busy, "shell_child_names",
                               return_value=set()):
            return resurrect.restore(dry_run=True, sessions=sessions)

    def test_scoped_restore_touches_only_that_session(self):
        r = self._restore({"work"})
        self.assertEqual([s.name for s, _pid in r.restored], ["nvtop"])
        self.assertEqual([pid for _l, pid, _c in r.labels_restored], ["w1:q1"])

    def test_unscoped_restore_touches_both(self):
        r = self._restore(None)
        self.assertEqual(sorted(s.name for s, _pid in r.restored),
                         ["btop", "nvtop"])
        self.assertEqual(len(r.labels_restored), 2)


import cli  # noqa: E402


class TestAutorestoreTargets(unittest.TestCase):
    def test_snapshot_sessions_are_targets(self):
        snaps = [_snap(session="default"), _snap(session="work")]
        with mock.patch.object(cli.snapshot, "load_snaps",
                               return_value=(snaps, 0.0)):
            self.assertEqual(cli._autorestore_targets({"default"}, {}),
                             {"default", "work"})

    def test_label_commands_add_running_sessions_only(self):
        # A stopped session the user may never attach must not be a target, or
        # the run would poll to its full window waiting for it.
        with mock.patch.object(cli.snapshot, "load_snaps", return_value=([], 0.0)):
            self.assertEqual(
                cli._autorestore_targets({"default"}, {"panel:yazi": "yazi"}),
                {"default"})
            self.assertEqual(cli._autorestore_targets({"default"}, {}), set())


class TestAutorestoreLoop(unittest.TestCase):
    """The loop that fixes the real failure: `work` appearing hours after login."""

    def _run(self, session_seq, **kw):
        """Drive _cmd_autorestore over a scripted sequence of running-session
        sets, one per poll. Returns the sessions each restore pass was scoped to."""
        calls: list[set[str]] = []
        clock = {"t": 0.0}
        seq = list(session_seq)

        def fake_list_sessions():
            running = seq.pop(0) if seq else set()
            return [herdr_api.Session(n, n == "default", True) for n in running]

        def fake_restore(*, sessions=None, dry_run=False):
            calls.append(sessions)
            return resurrect.RestoreResult()

        args = argparse.Namespace(window=kw.get("window", 10_000.0),
                                  interval=kw.get("interval", 30.0),
                                  settle=kw.get("settle", 60.0))
        with mock.patch.object(cli.herdr_api, "list_sessions", fake_list_sessions), \
             mock.patch.object(cli.resurrect, "restore", fake_restore), \
             mock.patch.object(cli.config, "load",
                               return_value={"label_commands": {}}), \
             mock.patch.object(cli.snapshot, "load_snaps",
                               return_value=(kw["snaps"], 0.0)), \
             mock.patch.object(cli.time, "monotonic", lambda: clock["t"]), \
             mock.patch.object(cli.time, "sleep",
                               lambda s: clock.__setitem__("t", clock["t"] + s)):
            rc = cli._cmd_autorestore(args)
        return rc, calls

    def test_session_appearing_late_is_still_restored(self):
        # default up from the start; work's server appears on the 4th poll --
        # the exact shape of the 2026-09-17 failure, just compressed.
        snaps = [_snap(session="default"), _snap(session="work")]
        rc, calls = self._run(
            [{"default"}, {"default"}, {"default"},
             {"default", "work"}, {"default", "work"}, {"default", "work"}],
            snaps=snaps, settle=60.0)
        self.assertEqual(rc, 0)
        self.assertIn({"work"}, calls)

    def test_each_session_stops_being_restored_after_settling(self):
        # With settle=0 a session is done after one pass, so it is never
        # restored twice -- what stops label_commands relaunching a quit btop.
        snaps = [_snap(session="default")]
        rc, calls = self._run([{"default"}] * 5, snaps=snaps, settle=0.0)
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [{"default"}])

    def test_settle_window_gives_repeated_passes(self):
        snaps = [_snap(session="default")]
        rc, calls = self._run([{"default"}] * 10, snaps=snaps,
                              settle=60.0, interval=30.0)
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [{"default"}, {"default"}, {"default"}])

    def test_returns_when_all_targets_done(self):
        snaps = [_snap(session="default"), _snap(session="work")]
        rc, calls = self._run([{"default", "work"}] * 5, snaps=snaps, settle=0.0)
        self.assertEqual(rc, 0)
        self.assertEqual(sorted(map(repr, calls)),
                         sorted(map(repr, [{"default"}, {"work"}])))

    def test_window_cap_ends_a_run_whose_target_never_appears(self):
        snaps = [_snap(session="work")]
        rc, calls = self._run([{"default"}] * 50, snaps=snaps,
                              window=90.0, interval=30.0)
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [])

    def test_herdr_down_is_not_fatal(self):
        snaps = [_snap(session="default")]
        clock = {"t": 0.0}
        state = {"n": 0}

        def flaky():
            state["n"] += 1
            if state["n"] < 3:
                raise herdr_api.HerdrError("herdr not up")
            return [herdr_api.Session("default", True, True)]

        args = argparse.Namespace(window=10_000.0, interval=30.0, settle=0.0)
        calls = []
        with mock.patch.object(cli.herdr_api, "list_sessions", flaky), \
             mock.patch.object(cli.resurrect, "restore",
                               lambda **kw: calls.append(kw.get("sessions"))
                               or resurrect.RestoreResult()), \
             mock.patch.object(cli.config, "load",
                               return_value={"label_commands": {}}), \
             mock.patch.object(cli.snapshot, "load_snaps",
                               return_value=(snaps, 0.0)), \
             mock.patch.object(cli.time, "monotonic", lambda: clock["t"]), \
             mock.patch.object(cli.time, "sleep",
                               lambda s: clock.__setitem__("t", clock["t"] + s)):
            rc = cli._cmd_autorestore(args)
        self.assertEqual(rc, 0)
        self.assertEqual(calls, [{"default"}])


if __name__ == "__main__":
    unittest.main()
