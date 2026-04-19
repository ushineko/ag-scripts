"""Unit tests for the tmux_lookup helper.

Verifies the behavioral contract that the zsh hook depends on:
  - Direct PWD match
  - Parent-walk to find the longest ancestor with a mapping
  - .code-workspace folder resolution (both absolute and relative paths)
"""

from __future__ import annotations

import json

import pytest

from tmux_lookup import (
    is_under,
    lookup_session,
    resolve_workspace_folders,
)


class TestIsUnder:
    def test_equal_paths(self):
        assert is_under("/a/b", "/a/b")

    def test_child_under_parent(self):
        assert is_under("/a/b/c", "/a/b")

    def test_sibling_not_under(self):
        assert not is_under("/a/b", "/a/c")

    def test_prefix_but_not_child_rejected(self):
        # /a/bcd starts with /a/b but is NOT a child of /a/b
        assert not is_under("/a/bcd", "/a/b")


class TestResolveWorkspaceFolders:
    def test_relative_paths_resolved_against_workspace_file_dir(self, tmp_path):
        ws_dir = tmp_path / "workspaces"
        ws_dir.mkdir()
        ws_file = ws_dir / "my.code-workspace"
        ws_file.write_text(
            json.dumps(
                {
                    "folders": [
                        {"path": "../git/proj-a"},
                        {"path": "../git/proj-b"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        resolved = resolve_workspace_folders(str(ws_file))
        assert resolved == [
            str(tmp_path / "git" / "proj-a"),
            str(tmp_path / "git" / "proj-b"),
        ]

    def test_absolute_paths_preserved(self, tmp_path):
        ws_file = tmp_path / "my.code-workspace"
        ws_file.write_text(
            json.dumps({"folders": [{"path": "/abs/path"}]}), encoding="utf-8"
        )
        resolved = resolve_workspace_folders(str(ws_file))
        assert resolved == ["/abs/path"]

    def test_missing_file_returns_empty(self, tmp_path):
        assert resolve_workspace_folders(str(tmp_path / "missing.code-workspace")) == []

    def test_invalid_json_returns_empty(self, tmp_path):
        ws = tmp_path / "broken.code-workspace"
        ws.write_text("{ not json", encoding="utf-8")
        assert resolve_workspace_folders(str(ws)) == []

    def test_malformed_entries_skipped(self, tmp_path):
        ws = tmp_path / "mixed.code-workspace"
        ws.write_text(
            json.dumps(
                {
                    "folders": [
                        {"path": "/good"},
                        "not-a-dict",
                        {"path": ""},  # empty
                        {},  # no path key
                    ]
                }
            ),
            encoding="utf-8",
        )
        assert resolve_workspace_folders(str(ws)) == ["/good"]


class TestLookupSession:
    def test_direct_match(self):
        mappings = {"/home/u/git/proj": "proj-sess"}
        assert lookup_session("/home/u/git/proj", mappings) == "proj-sess"

    def test_parent_walk_finds_ancestor(self):
        mappings = {"/home/u/git/proj": "proj-sess"}
        assert (
            lookup_session("/home/u/git/proj/subdir/deeper", mappings) == "proj-sess"
        )

    def test_longest_match_wins(self):
        # Both /a and /a/b are mapped; /a/b/c should hit /a/b, not /a.
        mappings = {"/a": "outer", "/a/b": "inner"}
        assert lookup_session("/a/b/c", mappings) == "inner"
        assert lookup_session("/a/c", mappings) == "outer"

    def test_no_match_returns_none(self):
        assert lookup_session("/no/match", {"/other": "x"}) is None

    def test_empty_pwd_returns_none(self):
        assert lookup_session("", {"/a": "x"}) is None

    def test_sibling_not_matched(self):
        mappings = {"/home/u/git/proj": "proj-sess"}
        # /home/u/git/projected starts with the same letters but is not a child
        assert lookup_session("/home/u/git/projected", mappings) is None

    def test_workspace_folder_resolved(self, tmp_path):
        # Simulate a .code-workspace with relative folder paths, like aiq_agent_go
        ws_dir = tmp_path / "vscode-workspaces"
        ws_dir.mkdir()
        ws_file = ws_dir / "proj.code-workspace"
        ws_file.write_text(
            json.dumps({"folders": [{"path": "../git/proj-a"}]}), encoding="utf-8"
        )
        target_folder = tmp_path / "git" / "proj-a"
        target_folder.mkdir(parents=True)

        mappings = {str(ws_file): "proj-sess"}

        # Direct match on the folder
        assert lookup_session(str(target_folder), mappings) == "proj-sess"
        # And on a subdirectory of the folder
        assert (
            lookup_session(str(target_folder / "sub" / "dir"), mappings) == "proj-sess"
        )

    def test_parent_walk_takes_precedence_over_workspace_lookup(self, tmp_path):
        """If a direct folder mapping exists, prefer it over scanning workspace files."""
        ws_file = tmp_path / "big.code-workspace"
        ws_file.write_text(
            json.dumps({"folders": [{"path": "/home/u/proj"}]}), encoding="utf-8"
        )
        mappings = {
            "/home/u/proj": "direct-sess",
            str(ws_file): "workspace-sess",
        }
        assert lookup_session("/home/u/proj", mappings) == "direct-sess"
