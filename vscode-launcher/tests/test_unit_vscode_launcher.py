"""Unit tests for vscode-launcher core logic.

Covers behavioral contracts — config round-trip, v1→v2 migration, VSCode
recents parsing, tmux session discovery, and launch command/env assembly.
GUI widgets are only exercised via smoke tests.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
from unittest.mock import patch

import pytest

from vscode_launcher import (
    CONFIG_VERSION,
    VSCODE_RECENTS_KEY,
    ConfigManager,
    Launcher,
    TmuxClient,
    VSCodeRecentsReader,
    Workspace,
    WorkspaceTableWidget,
    build_code_command,
    format_relative_time,
    label_for_path,
    uri_to_path,
)


# ---------------------------------------------------------------------------
# URI / label helpers
# ---------------------------------------------------------------------------


class TestUriToPath:
    def test_simple_file_uri(self):
        assert uri_to_path("file:///home/user/project") == "/home/user/project"

    def test_percent_encoded_uri(self):
        assert uri_to_path("file:///home/user/with%20space") == "/home/user/with space"

    def test_non_file_scheme_returns_empty(self):
        assert uri_to_path("vscode-vfs://github/org/repo") == ""

    def test_empty_returns_empty(self):
        assert uri_to_path("") == ""


class TestFormatRelativeTime:
    def test_none_returns_em_dash(self):
        assert format_relative_time(None) == "—"

    def test_just_now(self):
        assert format_relative_time(1000.0, now=1030.0) == "just now"

    def test_minutes(self):
        assert format_relative_time(1000.0, now=1000.0 + 5 * 60) == "5m ago"

    def test_hours(self):
        assert format_relative_time(1000.0, now=1000.0 + 3 * 3600 + 1) == "3h ago"

    def test_days(self):
        assert format_relative_time(1000.0, now=1000.0 + 2 * 86400 + 1) == "2d ago"


class TestLabelForPath:
    def test_folder_label_is_basename(self):
        assert label_for_path("/home/u/git/ag-scripts", False) == "ag-scripts"

    def test_workspace_file_label_has_suffix(self):
        assert (
            label_for_path("/home/u/ws/platform-backend.code-workspace", True)
            == "platform-backend (Workspace)"
        )


# ---------------------------------------------------------------------------
# VSCode recents reader
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_vscode_db(tmp_path):
    db_path = tmp_path / "state.vscdb"

    def _build(entries: list[dict]) -> None:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS ItemTable (key TEXT PRIMARY KEY, value BLOB)"
            )
            conn.execute(
                "INSERT OR REPLACE INTO ItemTable (key, value) VALUES (?, ?)",
                (VSCODE_RECENTS_KEY, json.dumps({"entries": entries})),
            )
            conn.commit()
        finally:
            conn.close()

    return db_path, _build


class TestVSCodeRecentsReader:
    def test_missing_db_returns_empty(self, tmp_path):
        reader = VSCodeRecentsReader(db_path=tmp_path / "missing.vscdb")
        assert reader.read_recents() == []

    def test_folder_uri_entry(self, fake_vscode_db):
        db_path, build = fake_vscode_db
        build([{"folderUri": "file:///home/u/git/proj"}])
        reader = VSCodeRecentsReader(db_path=db_path)
        recents = reader.read_recents()
        assert len(recents) == 1
        assert recents[0].path == "/home/u/git/proj"
        assert recents[0].label == "proj"
        assert recents[0].is_workspace_file is False

    def test_workspace_file_entry(self, fake_vscode_db):
        db_path, build = fake_vscode_db
        build(
            [
                {
                    "workspace": {
                        "id": "abc",
                        "configPath": "file:///home/u/ws/syadmin.code-workspace",
                    }
                }
            ]
        )
        reader = VSCodeRecentsReader(db_path=db_path)
        recents = reader.read_recents()
        assert len(recents) == 1
        assert recents[0].path == "/home/u/ws/syadmin.code-workspace"
        assert recents[0].label == "syadmin (Workspace)"
        assert recents[0].is_workspace_file is True

    def test_mixed_entries_preserve_order(self, fake_vscode_db):
        db_path, build = fake_vscode_db
        build(
            [
                {"folderUri": "file:///home/u/a"},
                {"workspace": {"configPath": "file:///home/u/b.code-workspace"}},
                {"folderUri": "file:///home/u/c"},
            ]
        )
        reader = VSCodeRecentsReader(db_path=db_path)
        recents = reader.read_recents()
        assert [w.path for w in recents] == [
            "/home/u/a",
            "/home/u/b.code-workspace",
            "/home/u/c",
        ]

    def test_non_file_scheme_entries_skipped(self, fake_vscode_db):
        db_path, build = fake_vscode_db
        build(
            [
                {"folderUri": "vscode-vfs://github/foo/bar"},
                {"folderUri": "file:///home/u/valid"},
                {},  # garbage
            ]
        )
        reader = VSCodeRecentsReader(db_path=db_path)
        recents = reader.read_recents()
        assert len(recents) == 1
        assert recents[0].path == "/home/u/valid"

    def test_bad_json_returns_empty(self, tmp_path):
        db_path = tmp_path / "state.vscdb"
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value BLOB)")
            conn.execute(
                "INSERT INTO ItemTable VALUES (?, ?)",
                (VSCODE_RECENTS_KEY, "{ not json"),
            )
            conn.commit()
        finally:
            conn.close()
        reader = VSCodeRecentsReader(db_path=db_path)
        assert reader.read_recents() == []

    def test_missing_key_returns_empty(self, tmp_path):
        db_path = tmp_path / "state.vscdb"
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value BLOB)")
            conn.commit()
        finally:
            conn.close()
        reader = VSCodeRecentsReader(db_path=db_path)
        assert reader.read_recents() == []


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class TestConfigManager:
    def test_load_missing_file_returns_default_v2(self, tmp_path):
        cm = ConfigManager(tmp_path / "workspaces.json")
        data = cm.load()
        assert data["version"] == CONFIG_VERSION
        assert data["tmux_mappings"] == {}
        assert data["hidden_paths"] == []

    def test_load_invalid_json_returns_default(self, tmp_path):
        path = tmp_path / "workspaces.json"
        path.write_text("{ not json", encoding="utf-8")
        cm = ConfigManager(path)
        data = cm.load()
        assert data["tmux_mappings"] == {}

    def test_save_then_load_round_trip(self, tmp_path):
        path = tmp_path / "workspaces.json"
        cm = ConfigManager(path)
        cm.load()
        cm.save(
            tmux_mappings={"/home/u/a": "session-a", "/home/u/b": "session-b"},
            hidden_paths=["/home/u/c"],
            window_geometry={"x": 50, "y": 60, "w": 700, "h": 500},
        )

        cm2 = ConfigManager(path)
        data = cm2.load()
        assert data["tmux_mappings"] == {
            "/home/u/a": "session-a",
            "/home/u/b": "session-b",
        }
        assert data["hidden_paths"] == ["/home/u/c"]
        assert data["window_geometry"] == {"x": 50, "y": 60, "w": 700, "h": 500}

    def test_save_preserves_unknown_keys(self, tmp_path):
        path = tmp_path / "workspaces.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 2,
            "tmux_mappings": {},
            "hidden_paths": [],
            "window_geometry": {"x": 0, "y": 0, "w": 100, "h": 100},
            "future_feature": {"enabled": True},
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
        cm = ConfigManager(path)
        cm.load()
        cm.save({}, [], {"x": 1, "y": 2, "w": 3, "h": 4})
        reloaded = json.loads(path.read_text(encoding="utf-8"))
        assert reloaded["future_feature"] == {"enabled": True}

    def test_v1_migration(self, tmp_path):
        """v1 config with workspaces list must migrate path -> tmux_session pairs into tmux_mappings."""
        path = tmp_path / "workspaces.json"
        v1_payload = {
            "version": 1,
            "workspaces": [
                {
                    "id": "a",
                    "label": "proj",
                    "path": "/home/u/proj",
                    "tmux_session": "proj-session",
                },
                {
                    "id": "b",
                    "label": "other",
                    "path": "/home/u/other",
                    "tmux_session": "",  # empty session — should not migrate
                },
                {
                    "id": "c",
                    "label": "third",
                    "path": "",  # empty path — should not migrate
                    "tmux_session": "bogus",
                },
            ],
            "window_geometry": {"x": 10, "y": 20, "w": 800, "h": 600},
        }
        path.write_text(json.dumps(v1_payload), encoding="utf-8")
        cm = ConfigManager(path)
        data = cm.load()
        assert data["version"] == CONFIG_VERSION
        assert data["tmux_mappings"] == {"/home/u/proj": "proj-session"}
        assert data["hidden_paths"] == []
        assert "workspaces" not in data  # v1 key dropped

        # And a save round-trip keeps the migrated form
        cm.save(
            tmux_mappings=data["tmux_mappings"],
            hidden_paths=data["hidden_paths"],
            window_geometry=data["window_geometry"],
        )
        reloaded = json.loads(path.read_text(encoding="utf-8"))
        assert reloaded["version"] == CONFIG_VERSION
        assert "workspaces" not in reloaded
        assert reloaded["tmux_mappings"] == {"/home/u/proj": "proj-session"}


# ---------------------------------------------------------------------------
# Tmux
# ---------------------------------------------------------------------------


class TestTmuxClient:
    def test_list_sessions_no_tmux_binary(self):
        with patch("vscode_launcher.shutil.which", return_value=None):
            assert TmuxClient.list_sessions() == []

    def test_list_sessions_no_server_returns_empty(self):
        fake_result = subprocess.CompletedProcess(
            args=["tmux"], returncode=1, stdout="", stderr="no server running"
        )
        with patch("vscode_launcher.shutil.which", return_value="/usr/bin/tmux"), patch(
            "vscode_launcher.subprocess.run", return_value=fake_result
        ):
            assert TmuxClient.list_sessions() == []

    def test_list_sessions_parses_output(self):
        fake_result = subprocess.CompletedProcess(
            args=["tmux"],
            returncode=0,
            stdout="platform-backend\nag-scripts\n\naiqtool\n",
            stderr="",
        )
        with patch("vscode_launcher.shutil.which", return_value="/usr/bin/tmux"), patch(
            "vscode_launcher.subprocess.run", return_value=fake_result
        ):
            assert TmuxClient.list_sessions() == [
                "platform-backend",
                "ag-scripts",
                "aiqtool",
            ]


# ---------------------------------------------------------------------------
# Launch command / env
# ---------------------------------------------------------------------------


class TestBuildCodeCommand:
    def test_uses_new_window_flag(self):
        assert build_code_command("/home/u/proj") == [
            "code",
            "--new-window",
            "/home/u/proj",
        ]

    def test_preserves_path_with_spaces(self):
        cmd = build_code_command("/home/u/with space/proj")
        assert cmd[-1] == "/home/u/with space/proj"


class TestLauncher:
    def test_launch_workspace_no_code_binary(self):
        launcher = Launcher()
        with patch("vscode_launcher.shutil.which", return_value=None):
            result = launcher.launch_workspace(
                Workspace(label="x", path="/tmp", tmux_session="s")
            )
        assert result is None

    def test_launch_workspace_spawns_subprocess(self):
        launcher = Launcher()
        ws = Workspace(label="x", path="/tmp/project", tmux_session="sess")
        with patch("vscode_launcher.shutil.which", return_value="/usr/bin/code"), patch(
            "vscode_launcher.subprocess.Popen"
        ) as popen:
            launcher.launch_workspace(ws)
        popen.assert_called_once()
        call_args = popen.call_args
        assert call_args.args[0] == ["code", "--new-window", "/tmp/project"]
        assert call_args.kwargs["start_new_session"] is True

    def test_run_gather_missing_binary_returns_false(self):
        launcher = Launcher()
        with patch("vscode_launcher.shutil.which", return_value=None):
            assert launcher.run_gather() is False

    def test_run_gather_invokes_binary(self):
        launcher = Launcher()
        fake_result = subprocess.CompletedProcess(args=["vscode-gather"], returncode=0)
        with patch(
            "vscode_launcher.shutil.which", return_value="/usr/bin/vscode-gather"
        ), patch(
            "vscode_launcher.subprocess.run", return_value=fake_result
        ) as run:
            assert launcher.run_gather() is True
        assert run.call_args.args[0] == ["vscode-gather"]


# ---------------------------------------------------------------------------
# MainWindow smoke + integration with recents + tmux mappings
# ---------------------------------------------------------------------------


class TestMainWindowSmoke:
    def test_constructs_with_empty_recents(self, qapp, tmp_path):
        from vscode_launcher import MainWindow

        cm = ConfigManager(tmp_path / "workspaces.json")
        launcher = Launcher()
        reader = VSCodeRecentsReader(db_path=tmp_path / "absent.vscdb")
        window = MainWindow(cm, launcher, reader)
        assert window.list_widget.rowCount() == 0
        # Widget visibility is only reflected by isVisible() once the parent is shown;
        # check explicit hidden state + message content instead.
        assert window.list_widget.isHidden()
        assert "VSCode state database not found" in window.empty_label.text()

    def test_list_reflects_vscode_recents_with_tmux_mapping(
        self, qapp, tmp_path, fake_vscode_db
    ):
        from vscode_launcher import MainWindow

        db_path, build = fake_vscode_db
        build(
            [
                {"folderUri": "file:///home/u/git/ag-scripts"},
                {"workspace": {"configPath": "file:///home/u/ws/syadmin.code-workspace"}},
            ]
        )
        # Seed a pre-existing tmux mapping for one entry
        config_path = tmp_path / "workspaces.json"
        config_path.write_text(
            json.dumps(
                {
                    "version": 2,
                    "tmux_mappings": {"/home/u/git/ag-scripts": "ag-scripts-sess"},
                    "hidden_paths": [],
                    "window_geometry": {"x": 0, "y": 0, "w": 600, "h": 400},
                }
            ),
            encoding="utf-8",
        )
        cm = ConfigManager(config_path)
        launcher = Launcher()
        reader = VSCodeRecentsReader(db_path=db_path)

        window = MainWindow(cm, launcher, reader)
        assert window.list_widget.rowCount() == 2
        # Mapped session should flow into the Workspace object
        mapped = [w for w in window.workspaces if w.path == "/home/u/git/ag-scripts"]
        assert mapped and mapped[0].tmux_session == "ag-scripts-sess"

    def test_hidden_path_is_filtered(self, qapp, tmp_path, fake_vscode_db):
        from vscode_launcher import MainWindow

        db_path, build = fake_vscode_db
        build(
            [
                {"folderUri": "file:///home/u/git/a"},
                {"folderUri": "file:///home/u/git/b"},
            ]
        )
        config_path = tmp_path / "workspaces.json"
        config_path.write_text(
            json.dumps(
                {
                    "version": 2,
                    "tmux_mappings": {},
                    "hidden_paths": ["/home/u/git/b"],
                    "window_geometry": {"x": 0, "y": 0, "w": 600, "h": 400},
                }
            ),
            encoding="utf-8",
        )
        cm = ConfigManager(config_path)
        window = MainWindow(cm, Launcher(), VSCodeRecentsReader(db_path=db_path))
        assert window.list_widget.rowCount() == 1
        assert window.workspaces[0].path == "/home/u/git/a"

    def test_running_workspaces_sort_first_preserving_mru(
        self, qapp, tmp_path, fake_vscode_db
    ):
        """Ordering contract: running group first in MRU order, then non-running
        in MRU order. Python's stable sort guarantees this."""
        from vscode_launcher import MainWindow

        db_path, build = fake_vscode_db
        # VSCode recents are stored most-recent-first. Interleave running/not.
        build(
            [
                {"folderUri": "file:///home/u/git/a"},  # not running (MRU 1)
                {"folderUri": "file:///home/u/git/b"},  # RUNNING (MRU 2)
                {"folderUri": "file:///home/u/git/c"},  # not running (MRU 3)
                {"folderUri": "file:///home/u/git/d"},  # RUNNING (MRU 4)
                {"folderUri": "file:///home/u/git/e"},  # not running (MRU 5)
            ]
        )
        cm = ConfigManager(tmp_path / "workspaces.json")

        class FakeScanner:
            def list_vscode_captions(self):
                return [
                    "file.py - b - Visual Studio Code",
                    "other.py - d - Visual Studio Code",
                ]

        window = MainWindow(
            cm,
            Launcher(),
            VSCodeRecentsReader(db_path=db_path),
            window_scanner=FakeScanner(),
        )
        paths = [w.path for w in window.workspaces]
        # Running first in MRU order (b before d), then non-running in MRU order (a, c, e).
        assert paths == [
            "/home/u/git/b",
            "/home/u/git/d",
            "/home/u/git/a",
            "/home/u/git/c",
            "/home/u/git/e",
        ]
        assert [w.is_running for w in window.workspaces] == [
            True,
            True,
            False,
            False,
            False,
        ]

    def test_row_buttons_reflect_running_state(
        self, qapp, tmp_path, fake_vscode_db
    ):
        """Running rows show Activate + Stop; non-running rows show only Start."""
        from PyQt6.QtWidgets import QPushButton

        from vscode_launcher import MainWindow, WorkspaceTableWidget

        db_path, build = fake_vscode_db
        build(
            [
                {"folderUri": "file:///home/u/git/running-one"},
                {"folderUri": "file:///home/u/git/idle-one"},
            ]
        )

        class FakeScanner:
            def list_vscode_captions(self):
                return ["file.py - running-one - Visual Studio Code"]

        window = MainWindow(
            ConfigManager(tmp_path / "workspaces.json"),
            Launcher(),
            VSCodeRecentsReader(db_path=db_path),
            window_scanner=FakeScanner(),
        )

        def buttons_for_row(i):
            actions_cell = window.list_widget.cellWidget(
                i, WorkspaceTableWidget.COL_ACTIONS
            )
            return [b.text() for b in actions_cell.findChildren(QPushButton)]

        # running-one sorts first; buttons are Activate + Stop
        assert buttons_for_row(0) == ["Activate", "Stop"]
        # idle-one is second; only Start
        assert buttons_for_row(1) == ["Start"]

    def test_launched_column_shows_em_dash_for_non_running(
        self, qapp, tmp_path, fake_vscode_db
    ):
        from PyQt6.QtWidgets import QLabel

        from vscode_launcher import MainWindow

        db_path, build = fake_vscode_db
        build([{"folderUri": "file:///home/u/git/a"}])

        class NoRunningScanner:
            def list_vscode_captions(self):
                return []

        window = MainWindow(
            ConfigManager(tmp_path / "workspaces.json"),
            Launcher(),
            VSCodeRecentsReader(db_path=db_path),
            window_scanner=NoRunningScanner(),
        )
        cell = window.list_widget.cellWidget(0, WorkspaceTableWidget.COL_LAUNCHED)
        label = cell.findChild(QLabel) if not isinstance(cell, QLabel) else cell
        assert label is not None
        assert (label.text() if isinstance(label, QLabel) else cell.text()) == "—"

    def test_tracked_launch_time_takes_precedence_over_proc_fallback(
        self, qapp, tmp_path, fake_vscode_db
    ):
        """When the launcher recorded its own spawn time for a path, that
        timestamp must be used instead of the /proc fallback (which gives
        the same main-VSCode-started time for every window)."""
        from unittest.mock import patch

        from vscode_launcher import MainWindow

        db_path, build = fake_vscode_db
        build([{"folderUri": "file:///home/u/git/a"}])

        class RunningScanner:
            def list_vscode_captions(self):
                return ["file - a - Visual Studio Code"]

            def list_vscode_entries(self):
                return [{"c": "file - a - Visual Studio Code", "p": 99999}]

        # /proc returns a "VSCode-started-9h-ago" fallback; tracked time is
        # "5 minutes ago". Tracked MUST win.
        nine_hours_ago = 1_000_000.0 - 9 * 3600
        five_minutes_ago = 1_000_000.0 - 5 * 60
        with patch(
            "vscode_launcher.get_process_start_time", return_value=nine_hours_ago
        ):
            window = MainWindow(
                ConfigManager(tmp_path / "workspaces.json"),
                Launcher(),
                VSCodeRecentsReader(db_path=db_path),
                window_scanner=RunningScanner(),
            )
            # Seed the tracked dict (as _launch_paths would).
            window._launched_at_by_path["/home/u/git/a"] = five_minutes_ago
            # Re-apply — simulating next scan after the launcher recorded a spawn.
            entries = [{"c": "file - a - Visual Studio Code", "p": 99999}]
            window._apply_running_and_sort(window.workspaces, entries)

        assert window.workspaces[0].launched_at == five_minutes_ago

    def test_tracking_entry_cleared_when_workspace_stops(
        self, qapp, tmp_path, fake_vscode_db
    ):
        """Running → not-running transition must discard our tracked
        timestamp so a relaunch later records a fresh one rather than
        showing the old 'launched at' time."""
        from vscode_launcher import MainWindow

        db_path, build = fake_vscode_db
        build([{"folderUri": "file:///home/u/git/a"}])

        class Scanner:
            def list_vscode_captions(self):
                return []  # nothing running now

            def list_vscode_entries(self):
                return []

        window = MainWindow(
            ConfigManager(tmp_path / "workspaces.json"),
            Launcher(),
            VSCodeRecentsReader(db_path=db_path),
            window_scanner=Scanner(),
        )
        # Pretend we had tracked a spawn before the workspace stopped.
        window._launched_at_by_path["/home/u/git/a"] = 1_000_000.0
        window._apply_running_and_sort(window.workspaces, [])  # empty scan
        assert "/home/u/git/a" not in window._launched_at_by_path

    def test_launched_column_shows_relative_time_for_running(
        self, qapp, tmp_path, fake_vscode_db
    ):
        """When launched_at is populated, the Launched column shows a
        relative-time string. We inject via the Workspace object directly
        (bypasses the /proc lookup which isn't unit-testable)."""
        from unittest.mock import patch

        from PyQt6.QtWidgets import QLabel

        from vscode_launcher import MainWindow

        db_path, build = fake_vscode_db
        build([{"folderUri": "file:///home/u/git/a"}])

        class RunningScanner:
            def list_vscode_captions(self):
                return ["file - a - Visual Studio Code"]

            def list_vscode_entries(self):
                return [{"c": "file - a - Visual Studio Code", "p": 12345}]

        # Fix "now" and return a predictable start time 10 minutes earlier.
        fake_now = 1_000_000.0
        ten_min_ago = fake_now - 600

        with patch(
            "vscode_launcher.get_process_start_time", return_value=ten_min_ago
        ), patch("vscode_launcher.time.time", return_value=fake_now):
            window = MainWindow(
                ConfigManager(tmp_path / "workspaces.json"),
                Launcher(),
                VSCodeRecentsReader(db_path=db_path),
                window_scanner=RunningScanner(),
            )

            cell = window.list_widget.cellWidget(
                0, WorkspaceTableWidget.COL_LAUNCHED
            )
            assert isinstance(cell, QLabel)
            assert cell.text() == "10m ago"
            assert window.workspaces[0].launched_at == ten_min_ago

    def test_checkbox_disabled_for_running_rows(
        self, qapp, tmp_path, fake_vscode_db
    ):
        """Running rows must have a disabled checkbox so bulk launch can't
        accidentally include them. Non-running rows stay enabled."""
        from PyQt6.QtWidgets import QCheckBox

        from vscode_launcher import MainWindow, WorkspaceTableWidget

        db_path, build = fake_vscode_db
        build(
            [
                {"folderUri": "file:///home/u/git/running-one"},
                {"folderUri": "file:///home/u/git/idle-one"},
            ]
        )

        class FakeScanner:
            def list_vscode_captions(self):
                return ["file.py - running-one - Visual Studio Code"]

        window = MainWindow(
            ConfigManager(tmp_path / "workspaces.json"),
            Launcher(),
            VSCodeRecentsReader(db_path=db_path),
            window_scanner=FakeScanner(),
        )

        def checkbox_for_row(i) -> QCheckBox:
            cell = window.list_widget.cellWidget(i, WorkspaceTableWidget.COL_CHECK)
            cb = cell.findChild(QCheckBox, "select_checkbox")
            assert cb is not None
            return cb

        # running-one sorts first → disabled
        assert checkbox_for_row(0).isEnabled() is False
        # idle-one → enabled
        assert checkbox_for_row(1).isEnabled() is True

    def test_launch_paths_skips_running_when_allow_running_false(
        self, qapp, tmp_path, fake_vscode_db
    ):
        """Belt-and-suspenders: even if a caller somehow passes a running path,
        the default bulk-launch path still filters it out."""
        from vscode_launcher import MainWindow

        db_path, build = fake_vscode_db
        build(
            [
                {"folderUri": "file:///home/u/git/running-one"},
                {"folderUri": "file:///home/u/git/idle-one"},
            ]
        )

        class FakeScanner:
            def list_vscode_captions(self):
                return ["file.py - running-one - Visual Studio Code"]

        launched: list[str] = []

        class RecordingLauncher(Launcher):
            def launch_workspace(self_inner, workspace):
                launched.append(workspace.path)
                return None  # don't actually spawn subprocess

        window = MainWindow(
            ConfigManager(tmp_path / "workspaces.json"),
            RecordingLauncher(),
            VSCodeRecentsReader(db_path=db_path),
            window_scanner=FakeScanner(),
        )

        with patch("vscode_launcher.shutil.which", return_value="/usr/bin/code"):
            window._launch_paths(
                ["/home/u/git/running-one", "/home/u/git/idle-one"],
                allow_running=False,
            )
        assert launched == ["/home/u/git/idle-one"]

    def test_launch_paths_forces_running_when_allow_running_true(
        self, qapp, tmp_path, fake_vscode_db
    ):
        """Context-menu Launch forces running workspaces through — used to
        duplicate a window intentionally."""
        from vscode_launcher import MainWindow

        db_path, build = fake_vscode_db
        build([{"folderUri": "file:///home/u/git/running-one"}])

        class FakeScanner:
            def list_vscode_captions(self):
                return ["file.py - running-one - Visual Studio Code"]

        launched: list[str] = []

        class RecordingLauncher(Launcher):
            def launch_workspace(self_inner, workspace):
                launched.append(workspace.path)
                return None

        window = MainWindow(
            ConfigManager(tmp_path / "workspaces.json"),
            RecordingLauncher(),
            VSCodeRecentsReader(db_path=db_path),
            window_scanner=FakeScanner(),
        )

        with patch("vscode_launcher.shutil.which", return_value="/usr/bin/code"):
            window._launch_paths(
                ["/home/u/git/running-one"], allow_running=True
            )
        assert launched == ["/home/u/git/running-one"]

    def test_stop_handler_invokes_scanner_with_close_action(
        self, qapp, tmp_path, fake_vscode_db
    ):
        from vscode_launcher import MainWindow
        from window_scanner import ACTION_CLOSE

        db_path, build = fake_vscode_db
        build([{"folderUri": "file:///home/u/git/a"}])

        calls = []

        class RecordingScanner:
            def list_vscode_captions(self):
                return ["file - a - Visual Studio Code"]

            def perform_window_action(self, label, action):
                calls.append((label, action))
                return True

        window = MainWindow(
            ConfigManager(tmp_path / "workspaces.json"),
            Launcher(),
            VSCodeRecentsReader(db_path=db_path),
            window_scanner=RecordingScanner(),
        )
        window._on_stop_requested("/home/u/git/a")
        assert calls == [("a", ACTION_CLOSE)]

    def test_activate_handler_invokes_scanner_with_activate_action(
        self, qapp, tmp_path, fake_vscode_db
    ):
        from vscode_launcher import MainWindow
        from window_scanner import ACTION_ACTIVATE

        db_path, build = fake_vscode_db
        build([{"folderUri": "file:///home/u/git/a"}])

        calls = []

        class RecordingScanner:
            def list_vscode_captions(self):
                return ["file - a - Visual Studio Code"]

            def perform_window_action(self, label, action):
                calls.append((label, action))
                return True

        window = MainWindow(
            ConfigManager(tmp_path / "workspaces.json"),
            Launcher(),
            VSCodeRecentsReader(db_path=db_path),
            window_scanner=RecordingScanner(),
        )
        window._on_activate_requested("/home/u/git/a")
        assert calls == [("a", ACTION_ACTIVATE)]

    def test_auto_refresh_resorts_on_state_change(
        self, qapp, tmp_path, fake_vscode_db
    ):
        """When the background scan reports flips, the list must re-sort
        running-first (stable sort preserving MRU within each group) and
        rebuild the widget so running rows move to the top."""
        from PyQt6.QtWidgets import QCheckBox, QPushButton

        from vscode_launcher import MainWindow, WorkspaceTableWidget

        db_path, build = fake_vscode_db
        build(
            [
                {"folderUri": "file:///home/u/git/a"},  # not running
                {"folderUri": "file:///home/u/git/b"},  # will become running
                {"folderUri": "file:///home/u/git/c"},  # not running
            ]
        )

        class InitialScanner:
            def list_vscode_captions(self):
                return []  # nothing running at startup

        window = MainWindow(
            ConfigManager(tmp_path / "workspaces.json"),
            Launcher(),
            VSCodeRecentsReader(db_path=db_path),
            window_scanner=InitialScanner(),
        )
        initial_order = [w.path for w in window.workspaces]
        assert initial_order == [
            "/home/u/git/a",
            "/home/u/git/b",
            "/home/u/git/c",
        ]

        # Simulate a background scan result arriving: only `b` is now open.
        window._on_background_scan_done(
            ["file.py - b - Visual Studio Code"]
        )

        # Running-first sort: b moves to row 0, a and c retain their relative
        # order (stable) below it.
        assert [w.path for w in window.workspaces] == [
            "/home/u/git/b",
            "/home/u/git/a",
            "/home/u/git/c",
        ]
        # Widget rebuilt in the new order
        assert window.list_widget.path_at_row(0) == "/home/u/git/b"

        # Row 0 now shows Activate+Stop + disabled checkbox (it's `b`, running)
        actions_0 = window.list_widget.cellWidget(
            0, WorkspaceTableWidget.COL_ACTIONS
        )
        assert [btn.text() for btn in actions_0.findChildren(QPushButton)] == [
            "Activate",
            "Stop",
        ]
        cb_0 = window.list_widget.cellWidget(
            0, WorkspaceTableWidget.COL_CHECK
        ).findChild(QCheckBox, "select_checkbox")
        assert cb_0.isEnabled() is False

    def test_auto_refresh_rereads_recents_so_just_launched_jumps_to_top(
        self, qapp, tmp_path, fake_vscode_db
    ):
        """VSCode updates state.vscdb MRU when it opens a workspace. When
        auto-refresh detects a flip, the list must be rebuilt from freshly-
        read recents so the just-launched workspace bubbles to the top of
        the running group rather than staying at its old MRU position."""
        from vscode_launcher import MainWindow

        db_path, build = fake_vscode_db
        # Initial MRU: A (not running), X (not running), C (not running).
        build(
            [
                {"folderUri": "file:///home/u/git/a"},
                {"folderUri": "file:///home/u/git/x"},
                {"folderUri": "file:///home/u/git/c"},
            ]
        )

        class InitialScanner:
            def list_vscode_captions(self):
                return []  # nothing running at startup

        window = MainWindow(
            ConfigManager(tmp_path / "workspaces.json"),
            Launcher(),
            VSCodeRecentsReader(db_path=db_path),
            window_scanner=InitialScanner(),
        )
        assert [w.path for w in window.workspaces] == [
            "/home/u/git/a",
            "/home/u/git/x",
            "/home/u/git/c",
        ]

        # Simulate: user clicks Start on X → VSCode opens X → state.vscdb
        # updates MRU so X is now first.
        build(
            [
                {"folderUri": "file:///home/u/git/x"},
                {"folderUri": "file:///home/u/git/a"},
                {"folderUri": "file:///home/u/git/c"},
            ]
        )
        # Next background scan picks up X as running
        window._on_background_scan_done(["file.py - x - Visual Studio Code"])

        # X should be at row 0 (running + freshly MRU'd).
        assert [w.path for w in window.workspaces] == [
            "/home/u/git/x",
            "/home/u/git/a",
            "/home/u/git/c",
        ]
        assert window.workspaces[0].is_running is True

    def test_auto_refresh_no_op_when_no_state_changes(
        self, qapp, tmp_path, fake_vscode_db
    ):
        """Pure polling without a flip must not reshuffle the table — no
        scroll / selection disruption when the scan returns 'same as before'."""
        from vscode_launcher import MainWindow

        db_path, build = fake_vscode_db
        build(
            [
                {"folderUri": "file:///home/u/git/a"},
                {"folderUri": "file:///home/u/git/b"},
            ]
        )

        class SteadyScanner:
            def list_vscode_captions(self):
                return ["file - a - Visual Studio Code"]

        window = MainWindow(
            ConfigManager(tmp_path / "workspaces.json"),
            Launcher(),
            VSCodeRecentsReader(db_path=db_path),
            window_scanner=SteadyScanner(),
        )
        starting_order = [w.path for w in window.workspaces]
        # Second scan with the same result → no flips, no re-sort
        window._on_background_scan_done(["file - a - Visual Studio Code"])
        assert [w.path for w in window.workspaces] == starting_order

    def test_auto_refresh_callback_skips_when_scanner_returns_none(
        self, qapp, tmp_path, fake_vscode_db
    ):
        from vscode_launcher import MainWindow

        db_path, build = fake_vscode_db
        build([{"folderUri": "file:///home/u/git/a"}])

        class InitialScanner:
            def list_vscode_captions(self):
                return []

        window = MainWindow(
            ConfigManager(tmp_path / "workspaces.json"),
            Launcher(),
            VSCodeRecentsReader(db_path=db_path),
            window_scanner=InitialScanner(),
        )
        # Flip the state so we can prove None doesn't clobber it
        window.workspaces[0].is_running = True
        window._on_background_scan_done(None)
        assert window.workspaces[0].is_running is True

    def test_trigger_background_scan_skips_when_hidden(
        self, qapp, tmp_path, fake_vscode_db
    ):
        """Don't burn CPU polling while the launcher is minimized."""
        from vscode_launcher import MainWindow

        db_path, build = fake_vscode_db
        build([{"folderUri": "file:///home/u/git/a"}])

        class CountingScanner:
            def __init__(self):
                self.calls = 0

            def list_vscode_captions(self):
                self.calls += 1
                return []

        scanner = CountingScanner()
        window = MainWindow(
            ConfigManager(tmp_path / "workspaces.json"),
            Launcher(),
            VSCodeRecentsReader(db_path=db_path),
            window_scanner=scanner,
        )
        initial = scanner.calls
        # Window was never show()n, so isVisible() is False. Trigger should skip.
        window._trigger_background_scan()
        assert scanner.calls == initial

    def test_scanner_none_result_does_not_break_list(
        self, qapp, tmp_path, fake_vscode_db
    ):
        """If the scanner returns None (KWin/journalctl unavailable), the
        list still renders with no running state."""
        from vscode_launcher import MainWindow

        db_path, build = fake_vscode_db
        build([{"folderUri": "file:///home/u/git/a"}])

        class NullScanner:
            def list_vscode_captions(self):
                return None

        window = MainWindow(
            ConfigManager(tmp_path / "workspaces.json"),
            Launcher(),
            VSCodeRecentsReader(db_path=db_path),
            window_scanner=NullScanner(),
        )
        assert window.list_widget.rowCount() == 1
        assert window.workspaces[0].is_running is False
