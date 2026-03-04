"""Tests for configuration module."""

import tempfile
from pathlib import Path
from unittest import mock

import pytest

from src.config import DEFAULTS, load_config, save_config, get_setting, set_setting


class TestDefaults:

    def test_has_expected_keys(self):
        assert "update_interval_seconds" in DEFAULTS
        assert "opacity" in DEFAULTS
        assert "widget_position" in DEFAULTS

    def test_old_keys_removed(self):
        assert "session_budget" not in DEFAULTS
        assert "window_hours" not in DEFAULTS
        assert "reset_hour" not in DEFAULTS
        assert "token_offset" not in DEFAULTS


class TestSaveAndLoad:

    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("src.config.get_config_dir", return_value=Path(tmpdir)):
                config = {**DEFAULTS, "opacity": 0.8}
                save_config(config)
                loaded = load_config()
                assert loaded["opacity"] == 0.8

    def test_creates_defaults_when_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("src.config.get_config_dir", return_value=Path(tmpdir)):
                loaded = load_config()
                assert loaded == DEFAULTS

    def test_merges_with_defaults(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("src.config.get_config_dir", return_value=Path(tmpdir)):
                save_config({"opacity": 0.7})
                loaded = load_config()
                assert loaded["opacity"] == 0.7
                assert loaded["update_interval_seconds"] == DEFAULTS["update_interval_seconds"]


class TestGetSetSetting:

    def test_get_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("src.config.get_config_dir", return_value=Path(tmpdir)):
                assert get_setting("update_interval_seconds") == 30

    def test_set_and_get(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("src.config.get_config_dir", return_value=Path(tmpdir)):
                set_setting("opacity", 0.5)
                assert get_setting("opacity") == 0.5

    def test_get_unknown_key_returns_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("src.config.get_config_dir", return_value=Path(tmpdir)):
                assert get_setting("nonexistent") is None
