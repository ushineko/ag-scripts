"""Tests for the QProcess-based usage fetcher.

The QProcess round-trip itself needs a Qt event loop and a child process, so it
is exercised by the manual/build smoke tests. Here we cover the pure logic:
command construction (frozen vs source) and stdout JSON parsing.
"""

import sys
from unittest import mock

import pytest

pytest.importorskip("PySide6")  # skip whole module if Qt absent

from src.fetcher import UsageFetcher, fetch_command


class TestFetchCommand:

    def test_from_source_reinvokes_module(self):
        with mock.patch.object(sys, "frozen", False, create=True):
            program, args = fetch_command()
        assert program == sys.executable
        assert args == ["-m", "src.main", "--fetch-json"]

    def test_frozen_reinvokes_executable(self):
        with mock.patch.object(sys, "frozen", True, create=True):
            program, args = fetch_command()
        assert program == sys.executable
        assert args == ["--fetch-json"]


class TestParse:

    def test_valid_json(self):
        assert UsageFetcher._parse('{"five_hour": {"utilization": 3}}') == {
            "five_hour": {"utilization": 3}
        }

    def test_json_null_is_none(self):
        assert UsageFetcher._parse("null") is None

    def test_empty_is_none(self):
        assert UsageFetcher._parse("") is None
        assert UsageFetcher._parse("   ") is None

    def test_garbage_is_none(self):
        assert UsageFetcher._parse("not json at all") is None
