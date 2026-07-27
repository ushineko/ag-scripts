"""Tests for the OSD and notification toggles (spec 010).

Covers config defaulting/backfill, suppression of the app's own volume OSD, the
informational-vs-failure split in desktop notifications, and the CLI fallback gate.
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(__file__))

from audio_source_switcher.config import DEFAULTS, ConfigManager  # noqa: E402


# ── Config defaults and backfill ──────────────────────────────────────

def _config_mgr(tmp_path):
    """A ConfigManager pointed at a temp file, bypassing the real ~/.config path."""
    mgr = ConfigManager.__new__(ConfigManager)
    mgr.config_dir = str(tmp_path)
    mgr.config_file = str(tmp_path / "config.json")
    return mgr


def test_defaults_enable_both_toggles():
    assert DEFAULTS["osd_enabled"] is True
    assert DEFAULTS["switch_notifications"] is True


def test_load_config_missing_file_returns_defaults(tmp_path):
    config = _config_mgr(tmp_path).load_config()
    assert config["osd_enabled"] is True
    assert config["switch_notifications"] is True


def test_load_config_backfills_old_file_without_toggles(tmp_path):
    """A config written before spec 010 must gain the keys, enabled."""
    mgr = _config_mgr(tmp_path)
    with open(mgr.config_file, "w") as f:
        json.dump({"device_priority": ["bt:AA"], "auto_switch": True}, f)

    config = mgr.load_config()

    assert config["osd_enabled"] is True
    assert config["switch_notifications"] is True
    # Persisted values survive the merge.
    assert config["device_priority"] == ["bt:AA"]
    assert config["auto_switch"] is True


def test_load_config_does_not_override_persisted_false(tmp_path):
    mgr = _config_mgr(tmp_path)
    with open(mgr.config_file, "w") as f:
        json.dump({"osd_enabled": False, "switch_notifications": False}, f)

    config = mgr.load_config()

    assert config["osd_enabled"] is False
    assert config["switch_notifications"] is False


def test_load_config_does_not_alias_mutable_defaults(tmp_path):
    """Two loads must not share the same list/dict objects as DEFAULTS."""
    mgr = _config_mgr(tmp_path)
    first = mgr.load_config()
    first["device_priority"].append("bt:AA")
    first["mic_links"]["x"] = "y"

    second = mgr.load_config()

    assert second["device_priority"] == []
    assert second["mic_links"] == {}
    assert DEFAULTS["device_priority"] == []
    assert DEFAULTS["mic_links"] == {}


def test_load_config_unreadable_file_falls_back_to_defaults(tmp_path):
    mgr = _config_mgr(tmp_path)
    with open(mgr.config_file, "w") as f:
        f.write("{not json")

    config = mgr.load_config()

    assert config["osd_enabled"] is True
    assert config["device_priority"] == []


# ── OSD suppression ───────────────────────────────────────────────────

def _bare_main_window(config: dict):
    """A MainWindow instance without running __init__ (no GUI/audio init)."""
    from audio_source_switcher.gui.main_window import MainWindow
    win = MainWindow.__new__(MainWindow)
    win.audio = MagicMock()
    win.osd = MagicMock()
    win.tray_icon = None
    win.config = config
    win.config_mgr = MagicMock()
    win._last_osd_volume = None
    return win


def test_show_osd_suppressed_when_disabled():
    win = _bare_main_window({"osd_enabled": False})
    win._show_osd(40, False)
    win.osd.show_volume.assert_not_called()


def test_show_osd_still_records_state_when_disabled():
    """Dedup bookkeeping must stay accurate so re-enabling shows fresh values."""
    win = _bare_main_window({"osd_enabled": False})
    win._show_osd(40, False)
    assert win._last_osd_volume == (40, False)


def test_show_osd_shows_when_enabled():
    win = _bare_main_window({"osd_enabled": True})
    win._show_osd(40, False)
    win.osd.show_volume.assert_called_once_with(40, False)


def test_show_osd_defaults_to_shown_when_key_absent():
    win = _bare_main_window({})
    win._show_osd(55, True)
    win.osd.show_volume.assert_called_once_with(55, True)


def test_hotkey_path_respects_osd_toggle():
    """The hotkey path routes through _show_osd, so the toggle covers it too."""
    win = _bare_main_window({"osd_enabled": False})
    with patch("audio_source_switcher.gui.main_window.adjust_volume",
               return_value=("sinkX", 72, False)):
        win.handle_volume_hotkey("up")
    win.osd.show_volume.assert_not_called()


def test_subscribe_path_respects_osd_toggle():
    win = _bare_main_window({"osd_enabled": False})
    win.audio.get_sink_volume.return_value = 40
    win.audio.get_sink_mute.return_value = False
    with patch("audio_source_switcher.gui.main_window.resolve_active_sink",
               return_value="sinkX"):
        win._process_volume_event()
    win.osd.show_volume.assert_not_called()


# ── Notification gating ───────────────────────────────────────────────

def test_informational_notification_suppressed_when_disabled():
    win = _bare_main_window({"switch_notifications": False})
    with patch("audio_source_switcher.gui.main_window.subprocess.run") as run:
        win.send_notification("Audio Switched", "Output: Speakers")
    run.assert_not_called()


def test_informational_notification_sent_when_enabled():
    win = _bare_main_window({"switch_notifications": True})
    with patch("audio_source_switcher.gui.main_window.subprocess.run") as run:
        win.send_notification("Audio Switched", "Output: Speakers")
    run.assert_called_once()
    assert run.call_args[0][0][0] == "notify-send"


def test_failure_notification_sent_even_when_disabled():
    win = _bare_main_window({"switch_notifications": False})
    with patch("audio_source_switcher.gui.main_window.subprocess.run") as run:
        win.send_notification("Switch Failed", "boom", "dialog-error",
                              informational=False)
    run.assert_called_once()
    assert "Switch Failed" in run.call_args[0][0]


def test_notification_defaults_to_sent_when_key_absent():
    win = _bare_main_window({})
    with patch("audio_source_switcher.gui.main_window.subprocess.run") as run:
        win.send_notification("Audio Switched", "Output: Speakers")
    run.assert_called_once()


def test_connect_failure_path_notifies_with_notifications_off():
    """A real failure call site, not just the helper: must still reach the user."""
    win = _bare_main_window({"switch_notifications": False})
    with patch("audio_source_switcher.gui.main_window.subprocess.run") as run:
        with pytest.raises(SystemExit):
            win.on_cli_connect_finished(False, "pairing refused", "bt:AA")
    run.assert_called_once()
    assert "Connection Failed" in run.call_args[0][0]


# ── Settings handlers persist immediately ─────────────────────────────

def test_osd_toggle_handler_persists():
    win = _bare_main_window({"osd_enabled": True})
    win.on_osd_toggled(False)
    assert win.config["osd_enabled"] is False
    win.config_mgr.save_config.assert_called_once_with(win.config)


def test_notification_toggle_handler_persists():
    win = _bare_main_window({"switch_notifications": True})
    win.on_notifications_toggled(False)
    assert win.config["switch_notifications"] is False
    win.config_mgr.save_config.assert_called_once_with(win.config)


# ── CLI fallback gate ─────────────────────────────────────────────────

def test_cli_fallback_skips_notify_when_osd_disabled():
    from audio_source_switcher import cli
    with patch.object(cli, "QCoreApplication"), \
         patch.object(cli, "_forward_to_instance", return_value=False), \
         patch.object(cli, "_osd_enabled", return_value=False), \
         patch.object(cli, "adjust_volume",
                      return_value=("sinkX", 33, False)) as adj, \
         patch.object(cli.subprocess, "run") as run:
        cli.handle_volume_command("down")
    # The volume change still happens; only the indicator is suppressed.
    adj.assert_called_once()
    run.assert_not_called()
