"""Tests for the volume OSD feature (spec 009).

Covers the shared smart-volume helpers, the OSD widget's update-in-place +
timer-restart behavior, the subscribe debounce/last-value dedup, and CLI
forward-vs-fallback routing.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from audio_source_switcher import volume as volume_mod  # noqa: E402
from audio_source_switcher.gui import osd as osd_mod  # noqa: E402
from audio_source_switcher.gui.osd import VolumeOSD, osd_title_for_screen  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


# ── Shared smart-volume helpers ──────────────────────────────────────

def test_resolve_active_sink_plain_default():
    audio = MagicMock()
    audio.get_default_sink.return_value = "alsa_output.speakers"
    pw = MagicMock()
    assert volume_mod.resolve_active_sink(audio, pw) == "alsa_output.speakers"
    pw.get_jamesdsp_target.assert_not_called()


def test_resolve_active_sink_follows_jamesdsp():
    audio = MagicMock()
    audio.get_default_sink.return_value = "jamesdsp_sink"
    pw = MagicMock()
    pw.get_jamesdsp_target.return_value = "alsa_output.hw"
    assert volume_mod.resolve_active_sink(audio, pw) == "alsa_output.hw"


def test_adjust_volume_steps_and_reports():
    audio = MagicMock()
    audio.get_default_sink.return_value = "alsa_output.speakers"
    audio.get_sink_volume.return_value = 55
    audio.get_sink_mute.return_value = False
    pw = MagicMock()

    target, new_vol, muted = volume_mod.adjust_volume(audio, pw, "up")

    audio.step_sink_volume.assert_called_once_with("alsa_output.speakers", "up", 5)
    assert (target, new_vol, muted) == ("alsa_output.speakers", 55, False)


def test_adjust_volume_no_sink_returns_none():
    audio = MagicMock()
    audio.get_default_sink.return_value = None
    pw = MagicMock()
    target, new_vol, muted = volume_mod.adjust_volume(audio, pw, "down")
    assert (target, new_vol, muted) == (None, None, False)
    audio.step_sink_volume.assert_not_called()


# ── OSD widget ───────────────────────────────────────────────────────

def test_osd_updates_in_place_and_restarts_timer(qapp):
    osd = VolumeOSD()
    osd.show_volume(30)
    assert osd._volume == 30
    assert osd.isVisible()
    assert osd._hide_timer.isActive()

    # A second show updates the SAME widget (no second window) and restarts timer.
    osd.show_volume(45, muted=True)
    assert osd._volume == 45
    assert osd._muted is True
    assert osd._hide_timer.isActive()
    osd.close()


def test_osd_title_encodes_screen_origin():
    assert osd_title_for_screen(2560, 0) == "ass-volume-osd@2560_0"
    assert osd_title_for_screen(0, 1120).startswith(osd_mod.OSD_TITLE_BASE)


# ── Subscribe debounce / last-value dedup (MainWindow methods) ────────

def _bare_main_window():
    """A MainWindow instance without running __init__ (no GUI/audio init)."""
    from audio_source_switcher.gui.main_window import MainWindow
    win = MainWindow.__new__(MainWindow)
    win.audio = MagicMock()
    win.osd = MagicMock()
    win._last_osd_volume = None
    return win


def test_process_volume_event_shows_on_change(qapp):
    win = _bare_main_window()
    win.audio.get_sink_volume.return_value = 40
    win.audio.get_sink_mute.return_value = False
    with patch("audio_source_switcher.gui.main_window.resolve_active_sink",
               return_value="sinkX"):
        win._process_volume_event()
    win.osd.show_volume.assert_called_once_with(40, False)
    assert win._last_osd_volume == (40, False)


def test_process_volume_event_dedups_unchanged(qapp):
    win = _bare_main_window()
    win.audio.get_sink_volume.return_value = 40
    win.audio.get_sink_mute.return_value = False
    with patch("audio_source_switcher.gui.main_window.resolve_active_sink",
               return_value="sinkX"):
        win._process_volume_event()  # first: shows
        win._process_volume_event()  # second: same state -> no re-show
    assert win.osd.show_volume.call_count == 1


def test_handle_volume_hotkey_shows_new_value(qapp):
    win = _bare_main_window()
    with patch("audio_source_switcher.gui.main_window.adjust_volume",
               return_value=("sinkX", 72, False)):
        win.handle_volume_hotkey("up")
    win.osd.show_volume.assert_called_once_with(72, False)
    assert win._last_osd_volume == (72, False)


# ── CLI forward-vs-fallback routing ──────────────────────────────────

def test_cli_forwards_when_instance_running():
    from audio_source_switcher import cli
    with patch.object(cli, "QCoreApplication"), \
         patch.object(cli, "_forward_to_instance", return_value=True) as fwd, \
         patch.object(cli, "adjust_volume") as adj, \
         patch.object(cli.subprocess, "run") as run:
        cli.handle_volume_command("up")
    fwd.assert_called_once_with(b"VOL_UP")
    adj.assert_not_called()
    run.assert_not_called()


def test_cli_falls_back_to_notify_when_no_instance():
    from audio_source_switcher import cli
    with patch.object(cli, "QCoreApplication"), \
         patch.object(cli, "_forward_to_instance", return_value=False), \
         patch.object(cli, "adjust_volume",
                      return_value=("sinkX", 33, False)) as adj, \
         patch.object(cli.subprocess, "run") as run:
        cli.handle_volume_command("down")
    adj.assert_called_once()
    assert run.call_count == 1
    notify_args = run.call_args[0][0]
    assert notify_args[0] == "notify-send"
    assert "Volume: 33%" in notify_args
