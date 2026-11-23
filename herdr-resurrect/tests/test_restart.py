"""Tests for restart-triggered restore (spec 003).

herdr_api is the only mock boundary: a FakeHerdr stands in for the herdr CLI
and keeps pane state, so `pane run` really makes the program show up as the
pane's foreground. Files (state, snapshot, lock, socket) are real, in a temp
config dir.
"""

import math
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

import config  # noqa: E402
import herdr_api  # noqa: E402
import restart  # noqa: E402
import resurrect  # noqa: E402
import snapshot  # noqa: E402
from snapshot import PaneSnap  # noqa: E402


def _snap(session="default", pane="w1:p1", name="lazygit", argv=None, cwd="/p"):
    return PaneSnap(session, "w1", "proj", "w1:t1", pane, cwd, name,
                    argv or [name])


def _live(session="default", pane="w1:p1", fg=None, cwd="/p"):
    return {"_session": session, "pane_id": pane, "workspace_id": "w1",
            "_workspace_label": "proj", "cwd": cwd, "tab_id": "w1:t1", "_fg": fg}


class TempConfigDir(unittest.TestCase):
    """Points every herdr-resurrect path at a fresh temp dir."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        d = self._tmp.name
        paths = {
            (config, "CONFIG_DIR"): d,
            (config, "CONFIG_PATH"): os.path.join(d, "config.json"),
            (config, "STATE_PATH"): os.path.join(d, "state.json"),
            (config, "LOCK_PATH"): os.path.join(d, "restore.lock"),
            (snapshot, "SNAPSHOT_PATH"): os.path.join(d, "snapshot.json"),
            (snapshot, "HISTORY_DIR"): os.path.join(d, "history"),
        }
        for (mod, attr), value in paths.items():
            patcher = mock.patch.object(mod, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)
        self.dir = d


class TestServerIdentity(unittest.TestCase):
    def test_existing_socket_gives_its_creation_time(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "herdr.sock")
            before = time.time()
            open(path, "w").close()
            ident = restart.server_identity(path)
        self.assertIsNotNone(ident)
        self.assertLess(abs(ident - before), 5)

    def test_missing_or_empty_socket_path_is_none(self):
        self.assertIsNone(restart.server_identity("/nonexistent/herdr.sock"))
        self.assertIsNone(restart.server_identity(""))


class TestState(TempConfigDir):
    def test_round_trip(self):
        restart.save_state({"default": 123.5, "work": 456.0})
        self.assertEqual(restart.load_state(), {"default": 123.5, "work": 456.0})

    def test_missing_file_reads_empty(self):
        self.assertEqual(restart.load_state(), {})

    def test_corrupt_file_reads_empty(self):
        with open(config.STATE_PATH, "w") as fh:
            fh.write("{not json")
        self.assertEqual(restart.load_state(), {})

    def test_write_leaves_no_tmp_file(self):
        restart.save_state({"default": 1.0})
        self.assertEqual(sorted(os.listdir(self.dir)), ["state.json"])


class TestClassify(unittest.TestCase):
    def test_no_record_is_first_seen_not_a_restart(self):
        self.assertEqual(restart.classify(None, 100.0), restart.FIRST_SEEN)

    def test_same_identity_is_unchanged(self):
        self.assertEqual(restart.classify(100.0, 100.0), restart.UNCHANGED)

    def test_different_identity_is_a_restart(self):
        self.assertEqual(restart.classify(100.0, 200.0), restart.RESTARTED)


class TestRestartVerdict(unittest.TestCase):
    def test_programs_gone_from_rebuilt_panes_is_corroborated(self):
        snaps = [_snap(pane="w1:p1"), _snap(pane="w1:p2", name="yazi")]
        live = [_live(pane="w1:p1"), _live(pane="w1:p2")]
        self.assertEqual(restart.restart_verdict(snaps, live, 0.5),
                         restart.CORROBORATED)

    def test_programs_still_running_is_not_corroborated(self):
        # A live handoff keeps pane processes: the socket changes, nothing died.
        snaps = [_snap(pane="w1:p1"), _snap(pane="w1:p2", name="yazi")]
        live = [_live(pane="w1:p1", fg=("lazygit", ["lazygit"])),
                _live(pane="w1:p2", fg=("yazi", ["yazi"]))]
        self.assertEqual(restart.restart_verdict(snaps, live, 0.5),
                         restart.NOT_CORROBORATED)

    def test_layout_not_rebuilt_is_pending(self):
        self.assertEqual(restart.restart_verdict([_snap()], [], 0.5),
                         restart.LAYOUT_PENDING)

    def test_nothing_saved_is_not_corroborated(self):
        self.assertEqual(restart.restart_verdict([], [_live()], 0.5),
                         restart.NOT_CORROBORATED)


class FakeHerdr:
    """Minimal stateful herdr: one session, panes that are idle or running."""

    def __init__(self, socket_path, panes):
        self.socket_path = socket_path
        self.panes = panes  # pane_id -> argv list, or None when idle
        self.runs: list[tuple[str, str]] = []

    def list_sessions(self):
        return [herdr_api.Session("default", True, True, self.socket_path)]

    def list_workspace_labels(self, _session):
        return {"w1": "proj"}

    def list_panes(self, _session):
        return [{"pane_id": pid, "workspace_id": "w1", "tab_id": "w1:t1",
                 "cwd": "/p", "agent_status": "unknown"} for pid in self.panes]

    def pane_process_info(self, _session, pane_id):
        procs = [{"pid": 1, "name": "zsh", "argv": ["-zsh"]}]
        argv = self.panes[pane_id]
        if argv:
            procs.append({"pid": 2, "name": argv[0], "argv": argv})
        return {"shell_pid": 1, "foreground_processes": procs}

    def pane_run(self, _session, pane_id, command):
        self.runs.append((pane_id, command))
        self.panes[pane_id] = command.split()

    def patch(self, test):
        for name in ("list_sessions", "list_workspace_labels", "list_panes",
                     "pane_process_info", "pane_run"):
            patcher = mock.patch.object(herdr_api, name, getattr(self, name))
            patcher.start()
            test.addCleanup(patcher.stop)


class TestSaveRestoresAfterRestart(TempConfigDir):
    def setUp(self):
        super().setUp()
        self.sock = os.path.join(self.dir, "herdr.sock")
        open(self.sock, "w").close()
        self.ident = restart.server_identity(self.sock)
        settle = mock.patch.object(resurrect, "RESTART_SETTLE_SEC", 0.0)
        settle.start()
        self.addCleanup(settle.stop)
        snapshot.write_snapshot([_snap(pane="w1:p1", name="lazygit"),
                                 _snap(pane="w1:p2", name="yazi",
                                       argv=["yazi", "/p"])])

    def _herdr(self, panes):
        fake = FakeHerdr(self.sock, panes)
        fake.patch(self)
        return fake

    def test_restarted_server_gets_its_programs_back_and_captured(self):
        restart.save_state({"default": self.ident - 100})
        fake = self._herdr({"w1:p1": None, "w1:p2": None})
        logs: list[str] = []
        snaps = resurrect.save(log=logs.append)
        self.assertEqual(sorted(fake.runs),
                         [("w1:p1", "lazygit"), ("w1:p2", "yazi /p")])
        self.assertEqual(sorted(s.name for s in snaps), ["lazygit", "yazi"])
        self.assertEqual(restart.load_state(), {"default": self.ident})
        self.assertTrue(any("server restarted" in m for m in logs))
        self.assertTrue(any("lazygit" in m and "[restart]" in m for m in logs))

    def test_first_seen_server_only_records(self):
        fake = self._herdr({"w1:p1": None, "w1:p2": None})
        resurrect.save()
        self.assertEqual(fake.runs, [])
        self.assertEqual(restart.load_state(), {"default": self.ident})

    def test_unchanged_server_does_not_restore(self):
        restart.save_state({"default": self.ident})
        fake = self._herdr({"w1:p1": None, "w1:p2": None})
        resurrect.save()
        self.assertEqual(fake.runs, [])

    def test_new_socket_with_programs_running_records_without_restoring(self):
        restart.save_state({"default": self.ident - 100})
        fake = self._herdr({"w1:p1": ["lazygit"], "w1:p2": ["yazi", "/p"]})
        resurrect.save()
        self.assertEqual(fake.runs, [])
        self.assertEqual(restart.load_state(), {"default": self.ident})

    def test_layout_not_rebuilt_keeps_old_record_for_next_save(self):
        restart.save_state({"default": self.ident - 100})
        fake = self._herdr({})
        snaps = resurrect.save()
        self.assertEqual(fake.runs, [])
        self.assertEqual(restart.load_state(), {"default": self.ident - 100})
        # The fresh server is inside its grace window, so nothing is dropped.
        self.assertEqual(sorted(s.name for s in snaps), ["lazygit", "yazi"])


class TestGraceFromServerStart(unittest.TestCase):
    def _four_with_one_closed(self):
        prev = [_snap(pane=f"w1:p{i}", name=n)
                for i, n in enumerate(["btop", "nvtop", "lazygit", "yazi"], 1)]
        new = [s for s in prev if s.name != "yazi"]
        live = [_live(pane=f"w1:p{i}", fg=("x", ["x"])) for i in range(1, 4)]
        live.append(_live(pane="w1:p4", fg=None))
        return new, prev, live

    def test_restart_long_after_boot_still_gets_grace(self):
        # Booted days ago, server restarted a minute ago, and the user has
        # relaunched 3 of 4 by hand: below the mass-drop ratio, but the fourth
        # is kept because the server is fresh.
        new, prev, live = self._four_with_one_closed()
        merged = resurrect._merge_preserving(
            new, prev, live, uptime_sec=300_000,
            server_age_sec={"default": 60})
        self.assertIn("yazi", [s.name for s in merged])

    def test_old_server_drops_a_closed_pane(self):
        new, prev, live = self._four_with_one_closed()
        merged = resurrect._merge_preserving(
            new, prev, live, uptime_sec=60,
            server_age_sec={"default": 300_000})
        self.assertNotIn("yazi", [s.name for s in merged])


class TestUptime(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "darwin", "macOS-specific path")
    def test_uptime_is_finite_on_macos(self):
        up = resurrect._uptime_sec()
        self.assertTrue(math.isfinite(up))
        self.assertGreater(up, 0)


class TestRestoreLock(TempConfigDir):
    def test_concurrent_restore_does_not_run_programs(self):
        snapshot.write_snapshot([_snap(pane="w1:p1")])
        fake = FakeHerdr("", {"w1:p1": None})
        fake.patch(self)
        with mock.patch.object(restart, "LOCK_WAIT_SEC", 0.1), \
             restart.restore_lock() as held:
            self.assertTrue(held)
            r = resurrect.restore()
        self.assertTrue(r.lock_busy)
        self.assertEqual(fake.runs, [])

    def test_restore_runs_once_lock_is_free(self):
        snapshot.write_snapshot([_snap(pane="w1:p1")])
        fake = FakeHerdr("", {"w1:p1": None})
        fake.patch(self)
        r = resurrect.restore()
        self.assertFalse(r.lock_busy)
        self.assertEqual(fake.runs, [("w1:p1", "lazygit")])


if __name__ == "__main__":
    unittest.main()
