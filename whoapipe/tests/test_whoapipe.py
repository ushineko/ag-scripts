"""Tests for whoapipe core logic."""

import json
import sys
from pathlib import Path

import pytest

# Add parent directory to path so we can import whoapipe
sys.path.insert(0, str(Path(__file__).parent.parent))

from whoapipe import load_config, save_config, parse_desktop_entries, MainWindow


# ---------------------------------------------------------------------------
# Config save/load
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("whoapipe.PROFILES_FILE", tmp_path / "nonexistent.json")
        result = load_config()
        assert result == {"profiles": [], "settings": {}}

    def test_valid_config(self, tmp_path, monkeypatch):
        config = {"profiles": [{"name": "test", "host": "h", "command": "c"}], "settings": {"default_host": "myhost"}}
        f = tmp_path / "profiles.json"
        f.write_text(json.dumps(config))
        monkeypatch.setattr("whoapipe.PROFILES_FILE", f)
        result = load_config()
        assert result == config

    def test_migrate_old_list_format(self, tmp_path, monkeypatch):
        old_data = [{"name": "app1", "host": "h", "command": "c"}]
        f = tmp_path / "profiles.json"
        f.write_text(json.dumps(old_data))
        monkeypatch.setattr("whoapipe.PROFILES_FILE", f)
        result = load_config()
        assert result["profiles"] == old_data
        assert result["settings"] == {}

    def test_corrupt_json(self, tmp_path, monkeypatch):
        f = tmp_path / "profiles.json"
        f.write_text("{invalid json")
        monkeypatch.setattr("whoapipe.PROFILES_FILE", f)
        result = load_config()
        assert result == {"profiles": [], "settings": {}}

    def test_missing_keys_filled(self, tmp_path, monkeypatch):
        f = tmp_path / "profiles.json"
        f.write_text(json.dumps({"profiles": []}))
        monkeypatch.setattr("whoapipe.PROFILES_FILE", f)
        result = load_config()
        assert "settings" in result


class TestSaveConfig:
    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        f = tmp_path / "profiles.json"
        monkeypatch.setattr("whoapipe.PROFILES_FILE", f)
        monkeypatch.setattr("whoapipe.CONFIG_DIR", tmp_path)
        config = {"profiles": [{"name": "firefox", "host": "remote", "command": "firefox"}], "settings": {"default_host": "remote"}}
        save_config(config)
        result = load_config()
        assert result == config

    def test_creates_directory(self, tmp_path, monkeypatch):
        sub = tmp_path / "sub" / "dir"
        monkeypatch.setattr("whoapipe.CONFIG_DIR", sub)
        monkeypatch.setattr("whoapipe.PROFILES_FILE", sub / "profiles.json")
        save_config({"profiles": [], "settings": {}})
        assert (sub / "profiles.json").exists()


# ---------------------------------------------------------------------------
# Desktop entry parsing
# ---------------------------------------------------------------------------


SAMPLE_DESKTOP_OUTPUT = """\
###WHOAPIPE_FILE###/usr/share/applications/firefox.desktop
[Desktop Entry]
Type=Application
Name=Firefox
Exec=firefox %u
Comment=Web Browser
Categories=Network;WebBrowser;
Icon=firefox

###WHOAPIPE_FILE###/usr/share/applications/foot.desktop
[Desktop Entry]
Type=Application
Name=Foot
Exec=foot
Comment=Wayland terminal
Categories=System;TerminalEmulator;
Icon=foot

###WHOAPIPE_FILE###/usr/share/applications/hidden.desktop
[Desktop Entry]
Type=Application
Name=Hidden App
Exec=hidden
NoDisplay=true

###WHOAPIPE_FILE###/usr/share/applications/link.desktop
[Desktop Entry]
Type=Link
Name=Some Link
URL=https://example.com

###WHOAPIPE_FILE###/usr/share/applications/noexec.desktop
[Desktop Entry]
Type=Application
Name=No Exec
"""


class TestParseDesktopEntries:
    def test_basic_parsing(self):
        apps = parse_desktop_entries(SAMPLE_DESKTOP_OUTPUT)
        names = [a["name"] for a in apps]
        assert "Firefox" in names
        assert "Foot" in names

    def test_sorted_by_name(self):
        apps = parse_desktop_entries(SAMPLE_DESKTOP_OUTPUT)
        names = [a["name"] for a in apps]
        assert names == sorted(names, key=str.lower)

    def test_skips_hidden(self):
        apps = parse_desktop_entries(SAMPLE_DESKTOP_OUTPUT)
        names = [a["name"] for a in apps]
        assert "Hidden App" not in names

    def test_skips_non_application(self):
        apps = parse_desktop_entries(SAMPLE_DESKTOP_OUTPUT)
        names = [a["name"] for a in apps]
        assert "Some Link" not in names

    def test_skips_no_exec(self):
        apps = parse_desktop_entries(SAMPLE_DESKTOP_OUTPUT)
        names = [a["name"] for a in apps]
        assert "No Exec" not in names

    def test_cleans_exec_field_codes(self):
        apps = parse_desktop_entries(SAMPLE_DESKTOP_OUTPUT)
        firefox = [a for a in apps if a["name"] == "Firefox"][0]
        assert "%u" not in firefox["exec"]
        assert firefox["exec"] == "firefox"

    def test_preserves_icon(self):
        apps = parse_desktop_entries(SAMPLE_DESKTOP_OUTPUT)
        firefox = [a for a in apps if a["name"] == "Firefox"][0]
        assert firefox["icon"] == "firefox"

    def test_preserves_comment(self):
        apps = parse_desktop_entries(SAMPLE_DESKTOP_OUTPUT)
        firefox = [a for a in apps if a["name"] == "Firefox"][0]
        assert firefox["comment"] == "Web Browser"

    def test_empty_input(self):
        assert parse_desktop_entries("") == []

    def test_garbage_input(self):
        assert parse_desktop_entries("random garbage\nwith no structure") == []


# ---------------------------------------------------------------------------
# ANSI stripping and error detection
# ---------------------------------------------------------------------------


class TestStripAnsi:
    def test_strips_color_codes(self):
        assert MainWindow._strip_ansi("\x1b[0;91mERROR:\x1b[0m something") == "ERROR: something"

    def test_plain_text_unchanged(self):
        assert MainWindow._strip_ansi("hello world") == "hello world"

    def test_multiple_codes(self):
        text = "\x1b[1m\x1b[31mred bold\x1b[0m"
        assert MainWindow._strip_ansi(text) == "red bold"


class TestOutputLooksLikeError:
    def test_detects_error_keyword(self):
        assert MainWindow._output_looks_like_error(["ERROR: something failed"]) is True

    def test_detects_not_found(self):
        assert MainWindow._output_looks_like_error(["command not found"]) is True

    def test_detects_permission_denied(self):
        assert MainWindow._output_looks_like_error(["bash: permission denied"]) is True

    def test_normal_output_not_error(self):
        assert MainWindow._output_looks_like_error(["Starting application...", "Ready."]) is False

    def test_empty_output(self):
        assert MainWindow._output_looks_like_error([]) is False

    def test_ansi_wrapped_error(self):
        assert MainWindow._output_looks_like_error(["\x1b[0;91mERROR:\x1b[0m crash"]) is True

    def test_resource_unavailable(self):
        assert MainWindow._output_looks_like_error(["Resource temporarily unavailable"]) is True


# ---------------------------------------------------------------------------
# Diagnose failure hints
# ---------------------------------------------------------------------------


class TestDiagnoseFailure:
    def test_gpu_hint(self):
        hints = MainWindow._diagnose_failure(1, ["failed to init dmabuf"])
        assert any("--no-gpu" in h for h in hints)

    def test_wayland_display_hint(self):
        hints = MainWindow._diagnose_failure(1, ["error: WAYLAND_DISPLAY not set"])
        assert any("WAYLAND_DISPLAY" in h or "wayland" in h.lower() for h in hints)

    def test_electron_hint(self):
        hints = MainWindow._diagnose_failure(0, ["ozone_platform_x11"])
        assert any("ozone" in h.lower() or "electron" in h.lower() for h in hints)

    def test_command_not_found(self):
        hints = MainWindow._diagnose_failure(127, ["bash: myapp: command not found"])
        assert any("not found" in h.lower() or "command" in h.lower() for h in hints)

    def test_no_specific_hints_for_clean_output(self):
        hints = MainWindow._diagnose_failure(0, ["Application started", "Running..."])
        # Only the generic "check log panel" hint, no specific failure hints
        assert len(hints) == 1
        assert "log panel" in hints[0].lower()
