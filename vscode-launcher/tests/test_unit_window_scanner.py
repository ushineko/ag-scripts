"""Unit tests for window_scanner.

Covers the behavioral contract the rest of the app relies on: caption ->
label token matching, multi-label running-set computation, and the journal
parser. The KWin/D-Bus invocation itself is not unit-tested (it requires a
live compositor); mocked call-sequence coverage is there as a smoke test.
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from window_scanner import (
    LOG_PREFIX,
    WindowScanner,
    caption_matches_label,
    parse_captions_from_journal,
    running_labels,
)


# ---------------------------------------------------------------------------
# caption_matches_label
# ---------------------------------------------------------------------------


class TestCaptionMatchesLabel:
    def test_folder_label_with_file_context(self):
        # Real caption from the user's live KWin dump:
        caption = "Spec vscode-launcher too… - ag-scripts - Visual Studio Code"
        assert caption_matches_label(caption, "ag-scripts")

    def test_workspace_file_label_with_parenthesis(self):
        caption = (
            "Agent QA build for 2026.… - aiq_agent_go (Workspace) - Visual Studio Code"
        )
        assert caption_matches_label(caption, "aiq_agent_go (Workspace)")

    def test_label_alone_matches(self):
        # No file context — caption is just "<label> - Visual Studio Code"
        assert caption_matches_label("ag-scripts - Visual Studio Code", "ag-scripts")

    def test_prefix_not_matched(self):
        """`aiq-ralph` must NOT match a window for `aiq-ralphbox`.

        That's the whole point of token-split matching vs. substring matching.
        """
        caption = "Fix worktree directory c… - aiq-ralphbox - Visual Studio Code"
        assert not caption_matches_label(caption, "aiq-ralph")
        assert caption_matches_label(caption, "aiq-ralphbox")

    def test_empty_inputs(self):
        assert not caption_matches_label("", "ag-scripts")
        assert not caption_matches_label("ag-scripts - Visual Studio Code", "")

    def test_label_appearing_in_filename_not_matched(self):
        """A label that happens to be part of the filename is not a match."""
        caption = "ag-scripts-notes.txt - other-project - Visual Studio Code"
        # `ag-scripts` appears only inside the filename token, not as its own token
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
        result = running_labels(captions, labels)
        assert result == {"ag-scripts", "syadmin (Workspace)"}

    def test_empty_captions_returns_empty(self):
        assert running_labels([], ["a", "b"]) == set()

    def test_empty_labels_returns_empty(self):
        assert running_labels(["whatever"], []) == set()


# ---------------------------------------------------------------------------
# parse_captions_from_journal
# ---------------------------------------------------------------------------


class TestParseCaptionsFromJournal:
    def test_parses_single_line(self):
        journal = (
            "Apr 19 20:37:09 host kwin_wayland[10372]: "
            f'{LOG_PREFIX}["first - a - Visual Studio Code"]\n'
        )
        assert parse_captions_from_journal(journal) == [
            "first - a - Visual Studio Code"
        ]

    def test_picks_most_recent_when_multiple_lines(self):
        journal = "\n".join(
            [
                f"old line {LOG_PREFIX}[\"stale\"]",
                "unrelated entry",
                f"newer line {LOG_PREFIX}[\"recent-1\", \"recent-2\"]",
            ]
        )
        assert parse_captions_from_journal(journal) == ["recent-1", "recent-2"]

    def test_returns_none_when_no_marker(self):
        assert parse_captions_from_journal("only noise\nand more noise\n") is None

    def test_returns_none_on_malformed_json(self):
        journal = f"header {LOG_PREFIX}not-json-here\n"
        assert parse_captions_from_journal(journal) is None

    def test_returns_none_when_payload_is_not_a_list(self):
        journal = f"header {LOG_PREFIX}{{\"key\": \"value\"}}\n"
        assert parse_captions_from_journal(journal) is None

    def test_empty_journal_returns_none(self):
        assert parse_captions_from_journal("") is None


# ---------------------------------------------------------------------------
# WindowScanner — high-level wiring (mocked)
# ---------------------------------------------------------------------------


class TestWindowScanner:
    def test_unavailable_when_tools_missing(self):
        scanner = WindowScanner()
        with patch("window_scanner.shutil.which", return_value=None):
            assert scanner.available() is False
            assert scanner.list_vscode_captions() is None

    def test_returns_captions_on_happy_path(self, tmp_path):
        scanner = WindowScanner()

        def fake_run(cmd, **kwargs):
            joined = " ".join(cmd)
            if "loadScript" in joined:
                return subprocess.CompletedProcess(cmd, 0, stdout="7", stderr="")
            if "journalctl" in joined:
                out = (
                    "Apr 19 host kwin[1]: "
                    f'{LOG_PREFIX}["x - ag-scripts - Visual Studio Code"]\n'
                )
                return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")
            # run / unload / anything else
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch(
            "window_scanner.shutil.which", side_effect=lambda _: "/usr/bin/stub"
        ), patch("window_scanner.subprocess.run", side_effect=fake_run), patch(
            "window_scanner.time.sleep"
        ):
            captions = scanner.list_vscode_captions()

        assert captions == ["x - ag-scripts - Visual Studio Code"]

    def test_returns_none_when_load_fails(self):
        scanner = WindowScanner()
        with patch(
            "window_scanner.shutil.which", side_effect=lambda _: "/usr/bin/stub"
        ), patch(
            "window_scanner.subprocess.run",
            return_value=subprocess.CompletedProcess([], 1, stdout="", stderr="err"),
        ), patch("window_scanner.time.sleep"):
            assert scanner.list_vscode_captions() is None

    def test_returns_none_when_script_id_non_numeric(self):
        scanner = WindowScanner()

        def fake_run(cmd, **kwargs):
            if "loadScript" in " ".join(cmd):
                return subprocess.CompletedProcess(cmd, 0, stdout="nope", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch(
            "window_scanner.shutil.which", side_effect=lambda _: "/usr/bin/stub"
        ), patch("window_scanner.subprocess.run", side_effect=fake_run), patch(
            "window_scanner.time.sleep"
        ):
            assert scanner.list_vscode_captions() is None
