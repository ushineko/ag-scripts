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
    build_code_command,
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
                "CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value BLOB)"
            )
            conn.execute(
                "INSERT INTO ItemTable (key, value) VALUES (?, ?)",
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
        assert window.list_widget.count() == 0
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
        assert window.list_widget.count() == 2
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
        assert window.list_widget.count() == 1
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
        assert window.list_widget.count() == 1
        assert window.workspaces[0].is_running is False
