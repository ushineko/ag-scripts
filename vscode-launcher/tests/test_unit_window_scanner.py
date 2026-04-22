"""Unit tests for window_scanner (v2.0+).

Covers the parts that remain after the IPC scanner refactor:
  - Pure helpers: caption_matches_label, running_labels, action_succeeded,
    _build_action_script, _ipc_entries_to_legacy_shape
  - WindowScanner.list_vscode_entries — IPC path, mocked via
    vscode_ipc.list_vscode_windows
  - WindowScanner.perform_window_action — KWin action path (mocked subprocess)

The IPC protocol plumbing itself is tested in test_unit_vscode_ipc.py.
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from window_scanner import (
    ACTION_ACTIVATE,
    ACTION_CLOSE,
    ACTION_LOG_PREFIX,
    WindowScanner,
    _build_action_script,
    _ipc_entries_to_legacy_shape,
    action_succeeded,
    caption_matches_label,
    running_labels,
)


# ---------------------------------------------------------------------------
# caption_matches_label
# ---------------------------------------------------------------------------


class TestCaptionMatchesLabel:
    def test_folder_label_with_file_context(self):
        caption = "Spec vscode-launcher too… - ag-scripts - Visual Studio Code"
        assert caption_matches_label(caption, "ag-scripts")

    def test_workspace_file_label_with_parenthesis(self):
        caption = (
            "Agent QA build for 2026.… - aiq_agent_go (Workspace) - Visual Studio Code"
        )
        assert caption_matches_label(caption, "aiq_agent_go (Workspace)")

    def test_label_alone_matches(self):
        assert caption_matches_label("ag-scripts - Visual Studio Code", "ag-scripts")

    def test_prefix_not_matched(self):
        caption = "Fix worktree directory c… - aiq-ralphbox - Visual Studio Code"
        assert not caption_matches_label(caption, "aiq-ralph")
        assert caption_matches_label(caption, "aiq-ralphbox")

    def test_empty_inputs(self):
        assert not caption_matches_label("", "ag-scripts")
        assert not caption_matches_label("ag-scripts - Visual Studio Code", "")

    def test_label_appearing_in_filename_not_matched(self):
        caption = "ag-scripts-notes.txt - other-project - Visual Studio Code"
        assert not caption_matches_label(caption, "ag-scripts")


# ---------------------------------------------------------------------------
# running_labels
# ---------------------------------------------------------------------------


class TestRunningLabels:
    def test_returns_only_matched_labels(self):
        captions = [
            "a.py - ag-scripts - Visual Studio Code",
            "b.py - syadmin (Workspace) - Visual Studio Code",
        ]
        labels = ["ag-scripts", "syadmin (Workspace)", "other-project"]
        assert running_labels(captions, labels) == {
            "ag-scripts",
            "syadmin (Workspace)",
        }

    def test_empty_captions_returns_empty(self):
        assert running_labels([], ["a", "b"]) == set()


# ---------------------------------------------------------------------------
# _ipc_entries_to_legacy_shape
# ---------------------------------------------------------------------------


class TestIPCEntriesToLegacyShape:
    def test_translates_title_and_pid(self):
        ipc = [
            {"id": 1, "pid": 42, "title": "foo - bar - Visual Studio Code", "folderURIs": []},
        ]
        assert _ipc_entries_to_legacy_shape(ipc) == [
            {"c": "foo - bar - Visual Studio Code", "p": 42}
        ]

    def test_handles_missing_pid(self):
        ipc = [{"title": "x - y - Visual Studio Code"}]
        assert _ipc_entries_to_legacy_shape(ipc) == [
            {"c": "x - y - Visual Studio Code", "p": None}
        ]

    def test_none_passes_through(self):
        assert _ipc_entries_to_legacy_shape(None) is None

    def test_empty_list_produces_empty(self):
        assert _ipc_entries_to_legacy_shape([]) == []

    def test_skips_non_dict_entries(self):
        ipc = [{"title": "ok", "pid": 1}, "garbage", None]
        assert _ipc_entries_to_legacy_shape(ipc) == [{"c": "ok", "p": 1}]

    def test_skips_entries_with_no_title(self):
        ipc = [{"pid": 1}, {"title": "ok", "pid": 2}]
        assert _ipc_entries_to_legacy_shape(ipc) == [{"c": "ok", "p": 2}]


# ---------------------------------------------------------------------------
# WindowScanner — scanning (via IPC)
# ---------------------------------------------------------------------------


class TestWindowScannerListEntries:
    def test_delegates_to_ipc(self):
        scanner = WindowScanner()
        with patch(
            "window_scanner.list_vscode_windows",
            return_value=[{"title": "x - a - Visual Studio Code", "pid": 7}],
        ):
            assert scanner.list_vscode_entries() == [
                {"c": "x - a - Visual Studio Code", "p": 7}
            ]

    def test_none_from_ipc_propagates(self):
        scanner = WindowScanner()
        with patch("window_scanner.list_vscode_windows", return_value=None):
            assert scanner.list_vscode_entries() is None

    def test_empty_from_ipc_means_no_windows(self):
        """list_vscode_windows returns [] when VSCode isn't running.
        That must propagate as an empty entry list, NOT as None."""
        scanner = WindowScanner()
        with patch("window_scanner.list_vscode_windows", return_value=[]):
            assert scanner.list_vscode_entries() == []

    def test_list_captions_wrapper(self):
        scanner = WindowScanner()
        with patch(
            "window_scanner.list_vscode_windows",
            return_value=[
                {"title": "x - a - Visual Studio Code", "pid": 1},
                {"title": "y - b - Visual Studio Code", "pid": 2},
            ],
        ):
            assert scanner.list_vscode_captions() == [
                "x - a - Visual Studio Code",
                "y - b - Visual Studio Code",
            ]


# ---------------------------------------------------------------------------
# action_succeeded
# ---------------------------------------------------------------------------


class TestActionSucceeded:
    def test_marker_present(self):
        assert (
            action_succeeded(
                f"Apr 19 host kwin[1]: {ACTION_LOG_PREFIX}any caption here\n"
            )
            is True
        )

    def test_marker_absent(self):
        assert action_succeeded("some other journal content\n") is False

    def test_empty(self):
        assert action_succeeded("") is False


# ---------------------------------------------------------------------------
# _build_action_script
# ---------------------------------------------------------------------------


class TestBuildActionScript:
    def test_close_branch(self):
        js = _build_action_script("ag-scripts", ACTION_CLOSE)
        assert "w.closeWindow()" in js
        assert '"ag-scripts"' in js
        assert ACTION_LOG_PREFIX in js

    def test_activate_branch(self):
        js = _build_action_script("ag-scripts", ACTION_ACTIVATE)
        assert "workspace.activeWindow = w" in js

    def test_label_with_quotes_is_escaped(self):
        js = _build_action_script('weird"label', ACTION_CLOSE)
        assert '"weird\\"label"' in js

    def test_unknown_action_raises(self):
        with pytest.raises(ValueError):
            _build_action_script("x", "nuke")


# ---------------------------------------------------------------------------
# WindowScanner.perform_window_action — KWin action path
# ---------------------------------------------------------------------------


class TestPerformWindowAction:
    def test_unknown_action_raises(self):
        with pytest.raises(ValueError):
            WindowScanner().perform_window_action("x", "launch-nukes")

    def test_unavailable_kwin_returns_false(self):
        scanner = WindowScanner()
        with patch("window_scanner.shutil.which", return_value=None):
            assert scanner.perform_window_action("x", ACTION_CLOSE) is False

    def test_happy_path(self):
        scanner = WindowScanner()

        def fake_run(cmd, **kwargs):
            joined = " ".join(cmd)
            if "loadScript" in joined:
                return subprocess.CompletedProcess(cmd, 0, stdout="11", stderr="")
            if "journalctl" in joined:
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    stdout=(
                        "Apr 19 host kwin[1]: "
                        f"{ACTION_LOG_PREFIX}x - ag-scripts - Visual Studio Code\n"
                    ),
                    stderr="",
                )
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch(
            "window_scanner.shutil.which", side_effect=lambda _: "/usr/bin/stub"
        ), patch("window_scanner.subprocess.run", side_effect=fake_run), patch(
            "window_scanner.time.sleep"
        ):
            assert (
                scanner.perform_window_action("ag-scripts", ACTION_CLOSE) is True
            )

    def test_no_match_returns_false(self):
        scanner = WindowScanner()

        def fake_run(cmd, **kwargs):
            joined = " ".join(cmd)
            if "loadScript" in joined:
                return subprocess.CompletedProcess(cmd, 0, stdout="12", stderr="")
            if "journalctl" in joined:
                return subprocess.CompletedProcess(
                    cmd, 0, stdout="unrelated log line\n", stderr=""
                )
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch(
            "window_scanner.shutil.which", side_effect=lambda _: "/usr/bin/stub"
        ), patch("window_scanner.subprocess.run", side_effect=fake_run), patch(
            "window_scanner.time.sleep"
        ):
            assert (
                scanner.perform_window_action("no-such-label", ACTION_ACTIVATE)
                is False
            )
