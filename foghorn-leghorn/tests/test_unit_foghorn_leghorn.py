"""Unit tests for foghorn_leghorn core logic."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from foghorn_leghorn import (
    ConfigManager,
    MainWindow,
    TimerData,
    TimerEngine,
    SoundPlayer,
    format_seconds,
    DEFAULT_CONFIG,
    BUILTIN_SOUNDS,
    SOUNDS_DIR,
    __version__,
)


# ---------------------------------------------------------------------------
# format_seconds
# ---------------------------------------------------------------------------

class TestFormatSeconds:
    """Tests for the format_seconds helper."""

    def test_zero(self):
        assert format_seconds(0) == "00:00"

    def test_negative_clamps_to_zero(self):
        assert format_seconds(-10) == "00:00"

    def test_seconds_only(self):
        assert format_seconds(45) == "00:45"

    def test_minutes_and_seconds(self):
        assert format_seconds(125) == "02:05"

    def test_exactly_one_hour(self):
        assert format_seconds(3600) == "1:00:00"

    def test_hours_minutes_seconds(self):
        assert format_seconds(3661) == "1:01:01"

    def test_large_value(self):
        assert format_seconds(36000) == "10:00:00"


# ---------------------------------------------------------------------------
# TimerData
# ---------------------------------------------------------------------------

class TestTimerData:
    """Tests for the TimerData dataclass."""

    def test_default_values(self):
        td = TimerData()
        assert td.name == "Timer"
        assert td.duration_seconds == 300
        assert td.remaining_seconds == 300
        assert td.sound_key == "Foghorn"
        assert td.custom_sound_path == ""
        assert td.is_running is False
        assert td.is_paused is False
        assert len(td.id) == 8

    def test_unique_ids(self):
        t1 = TimerData()
        t2 = TimerData()
        assert t1.id != t2.id

    def test_to_dict(self):
        td = TimerData(id="test1", name="My Timer", duration_seconds=60)
        d = td.to_dict()
        assert d["id"] == "test1"
        assert d["name"] == "My Timer"
        assert d["duration_seconds"] == 60

    def test_from_dict(self, sample_timer_dict):
        td = TimerData.from_dict(sample_timer_dict)
        assert td.id == "abc12345"
        assert td.name == "Test Timer"
        assert td.duration_seconds == 300
        assert td.remaining_seconds == 150
        assert td.is_running is True

    def test_from_dict_ignores_unknown_keys(self, sample_timer_dict):
        sample_timer_dict["unknown_field"] = "should be ignored"
        td = TimerData.from_dict(sample_timer_dict)
        assert td.name == "Test Timer"

    def test_roundtrip(self):
        td = TimerData(name="Roundtrip", duration_seconds=600, sound_key="Air Horn")
        restored = TimerData.from_dict(td.to_dict())
        assert restored.name == td.name
        assert restored.duration_seconds == td.duration_seconds
        assert restored.sound_key == td.sound_key
        assert restored.id == td.id


# ---------------------------------------------------------------------------
# ConfigManager
# ---------------------------------------------------------------------------

class TestConfigManager:
    """Tests for ConfigManager."""

    def test_defaults_when_no_file(self, temp_config_file):
        cm = ConfigManager(temp_config_file)
        assert cm.get("font_size") == 48
        assert cm.get("sound_enabled") is True
        assert cm.get("timers") == []

    def test_save_and_load(self, temp_config_file):
        cm = ConfigManager(temp_config_file)
        cm.set("font_size", 24)
        cm.save()

        cm2 = ConfigManager(temp_config_file)
        assert cm2.get("font_size") == 24

    def test_save_creates_directory(self, temp_config_file):
        assert not temp_config_file.parent.exists()
        cm = ConfigManager(temp_config_file)
        cm.save()
        assert temp_config_file.exists()

    def test_save_and_load_timers(self, temp_config_file):
        cm = ConfigManager(temp_config_file)
        t1 = TimerData(name="Timer A", duration_seconds=60)
        t2 = TimerData(name="Timer B", duration_seconds=120)
        cm.save_timers([t1, t2])

        cm2 = ConfigManager(temp_config_file)
        loaded = cm2.load_timers()
        assert len(loaded) == 2
        assert loaded[0].name == "Timer A"
        assert loaded[1].name == "Timer B"

    def test_load_corrupted_json(self, temp_config_file):
        temp_config_file.parent.mkdir(parents=True, exist_ok=True)
        temp_config_file.write_text("{invalid json")
        cm = ConfigManager(temp_config_file)
        assert cm.get("font_size") == DEFAULT_CONFIG["font_size"]

    def test_load_timers_skips_invalid(self, temp_config_file):
        temp_config_file.parent.mkdir(parents=True, exist_ok=True)
        data = dict(DEFAULT_CONFIG)
        data["timers"] = [
            {"id": "good1", "name": "Good", "duration_seconds": 60, "remaining_seconds": 60,
             "sound_key": "Foghorn", "custom_sound_path": "", "is_running": False, "is_paused": False},
            "not a dict",
        ]
        temp_config_file.write_text(json.dumps(data))
        cm = ConfigManager(temp_config_file)
        timers = cm.load_timers()
        assert len(timers) == 1
        assert timers[0].name == "Good"

    def test_get_default(self, temp_config_file):
        cm = ConfigManager(temp_config_file)
        assert cm.get("nonexistent", "fallback") == "fallback"


# ---------------------------------------------------------------------------
# TimerEngine
# ---------------------------------------------------------------------------

class TestTimerEngine:
    """Tests for TimerEngine (non-GUI tick logic)."""

    @pytest.fixture
    def engine(self, qapp):
        e = TimerEngine()
        return e

    def test_add_timer(self, engine):
        td = TimerData(name="T1", duration_seconds=10, remaining_seconds=10, is_running=True)
        engine.add_timer(td)
        assert len(engine.timers) == 1
        assert engine.timers[0].name == "T1"

    def test_remove_timer(self, engine):
        td = TimerData(name="T1")
        engine.add_timer(td)
        engine.remove_timer(td.id)
        assert len(engine.timers) == 0

    def test_get_timer(self, engine):
        td = TimerData(id="findme", name="Find Me")
        engine.add_timer(td)
        found = engine.get_timer("findme")
        assert found is not None
        assert found.name == "Find Me"

    def test_get_timer_not_found(self, engine):
        assert engine.get_timer("nonexistent") is None

    def test_tick_decrements(self, engine):
        td = TimerData(name="Counting", duration_seconds=10, remaining_seconds=5, is_running=True)
        engine.add_timer(td)
        engine._tick()
        assert td.remaining_seconds == 4

    def test_tick_paused_no_decrement(self, engine):
        td = TimerData(name="Paused", remaining_seconds=5, is_running=True, is_paused=True)
        engine.add_timer(td)
        engine._tick()
        assert td.remaining_seconds == 5

    def test_tick_stopped_no_decrement(self, engine):
        td = TimerData(name="Stopped", remaining_seconds=5, is_running=False)
        engine.add_timer(td)
        engine._tick()
        assert td.remaining_seconds == 5

    def test_tick_emits_expired(self, engine):
        td = TimerData(name="Expiring", remaining_seconds=1, is_running=True)
        engine.add_timer(td)
        expired_ids = []
        engine.timer_expired.connect(lambda tid: expired_ids.append(tid))
        engine._tick()
        assert expired_ids == [td.id]
        assert td.is_running is False
        assert td.remaining_seconds == 0

    def test_tick_does_not_go_negative(self, engine):
        td = TimerData(name="Zero", remaining_seconds=0, is_running=True)
        engine.add_timer(td)
        engine._tick()
        assert td.remaining_seconds == 0

    def test_multiple_timers_independent(self, engine):
        t1 = TimerData(name="A", remaining_seconds=10, is_running=True)
        t2 = TimerData(name="B", remaining_seconds=3, is_running=True)
        t3 = TimerData(name="C", remaining_seconds=5, is_running=True, is_paused=True)
        engine.add_timer(t1)
        engine.add_timer(t2)
        engine.add_timer(t3)
        engine._tick()
        assert t1.remaining_seconds == 9
        assert t2.remaining_seconds == 2
        assert t3.remaining_seconds == 5


# ---------------------------------------------------------------------------
# SoundPlayer
# ---------------------------------------------------------------------------

class TestSoundPlayer:
    """Tests for SoundPlayer."""

    def test_play_nonexistent_file_no_crash(self):
        sp = SoundPlayer()
        sp.play("/nonexistent/path/sound.wav")

    def test_builtin_sounds_exist(self):
        for name, path in BUILTIN_SOUNDS.items():
            assert path.exists(), f"Missing bundled sound: {name} at {path}"

    def test_play_calls_paplay(self, tmp_path):
        sp = SoundPlayer()
        dummy = tmp_path / "test.wav"
        dummy.write_bytes(b"RIFF" + b"\x00" * 40)
        with patch("foghorn_leghorn.subprocess.Popen") as mock_popen:
            sp.play(str(dummy))
            mock_popen.assert_called_once()
            args = mock_popen.call_args[0][0]
            assert args[0] == "paplay"
            assert args[1] == str(dummy)

    def test_play_falls_back_to_aplay(self, tmp_path):
        sp = SoundPlayer()
        dummy = tmp_path / "test.wav"
        dummy.write_bytes(b"RIFF" + b"\x00" * 40)
        with patch("foghorn_leghorn.subprocess.Popen", side_effect=[FileNotFoundError, None]) as mock_popen:
            sp.play(str(dummy))
            assert mock_popen.call_count == 2
            args = mock_popen.call_args_list[1][0][0]
            assert args[0] == "aplay"


# ---------------------------------------------------------------------------
# Bundled sounds
# ---------------------------------------------------------------------------

class TestBundledSounds:
    """Verify bundled sound files are present and valid WAV."""

    def test_sounds_dir_exists(self):
        assert SOUNDS_DIR.exists()

    def test_all_sounds_present(self):
        expected = ["foghorn.wav", "wilhelm_scream.wav", "air_horn.wav"]
        for name in expected:
            assert (SOUNDS_DIR / name).exists(), f"Missing: {name}"

    def test_sounds_are_wav(self):
        import wave
        for name in ["foghorn.wav", "wilhelm_scream.wav", "air_horn.wav"]:
            path = SOUNDS_DIR / name
            with wave.open(str(path), 'r') as wf:
                assert wf.getnchannels() == 1
                assert wf.getsampwidth() == 2
                assert wf.getframerate() == 44100
                assert wf.getnframes() > 0


# ---------------------------------------------------------------------------
# GUI startup smoke tests
# ---------------------------------------------------------------------------

class TestGUIStartup:
    """Smoke tests to verify the GUI initializes without errors."""

    def test_main_window_creates(self, qapp, tmp_path):
        """MainWindow initializes without exceptions."""
        config = ConfigManager(tmp_path / "config.json")
        engine = TimerEngine()
        sound_player = SoundPlayer()
        window = MainWindow(config, engine, sound_player)
        assert window.windowTitle() == f"Foghorn Leghorn v{__version__}"
        window.close()

    def test_main_window_has_always_on_top(self, qapp, tmp_path):
        """Window has the stay-on-top flag set."""
        from PyQt6.QtCore import Qt
        config = ConfigManager(tmp_path / "config.json")
        engine = TimerEngine()
        window = MainWindow(config, engine, SoundPlayer())
        flags = window.windowFlags()
        assert flags & Qt.WindowType.WindowStaysOnTopHint
        window.close()

    def test_main_window_shows_and_hides(self, qapp, tmp_path):
        """Window can show and hide without errors."""
        config = ConfigManager(tmp_path / "config.json")
        engine = TimerEngine()
        window = MainWindow(config, engine, SoundPlayer())
        window.show()
        assert window.isVisible()
        window.hide()
        assert not window.isVisible()
        window.close()

    def test_add_timer_via_engine(self, qapp, tmp_path):
        """Adding a timer to the engine and rebuilding works."""
        config = ConfigManager(tmp_path / "config.json")
        engine = TimerEngine()
        window = MainWindow(config, engine, SoundPlayer())
        td = TimerData(name="Smoke", duration_seconds=60, remaining_seconds=60, is_running=True)
        engine.add_timer(td)
        window._add_row(td)
        assert window.list_widget.count() == 1
        window.close()

    def test_timer_tick_updates_display(self, qapp, tmp_path):
        """A tick updates the display without errors."""
        config = ConfigManager(tmp_path / "config.json")
        engine = TimerEngine()
        window = MainWindow(config, engine, SoundPlayer())
        td = TimerData(name="Ticking", duration_seconds=10, remaining_seconds=5, is_running=True)
        engine.add_timer(td)
        window._add_row(td)
        engine._tick()
        assert td.remaining_seconds == 4
        window.close()

    def test_timer_expiry_fires_notification(self, qapp, tmp_path):
        """An expiring timer triggers notification without crash."""
        config = ConfigManager(tmp_path / "config.json")
        engine = TimerEngine()
        window = MainWindow(config, engine, SoundPlayer())
        td = TimerData(name="Expiry", duration_seconds=1, remaining_seconds=1, is_running=True)
        engine.add_timer(td)
        window._add_row(td)
        with patch("foghorn_leghorn.subprocess.Popen"):
            engine._tick()
        assert td.remaining_seconds == 0
        assert not td.is_running
        window.close()

    def test_save_and_restore_timers(self, qapp, tmp_path):
        """Timers persist through config save/load cycle."""
        config_path = tmp_path / "config.json"
        config = ConfigManager(config_path)
        engine = TimerEngine()
        window = MainWindow(config, engine, SoundPlayer())
        td = TimerData(name="Persist", duration_seconds=120, remaining_seconds=90, is_running=True)
        engine.add_timer(td)
        window._add_row(td)
        window._save_state()
        window.close()

        config2 = ConfigManager(config_path)
        loaded = config2.load_timers()
        assert len(loaded) == 1
        assert loaded[0].name == "Persist"
        assert loaded[0].remaining_seconds == 90

    def test_geometry_persists(self, qapp, tmp_path):
        """Window geometry is saved to config."""
        config_path = tmp_path / "config.json"
        config = ConfigManager(config_path)
        engine = TimerEngine()
        window = MainWindow(config, engine, SoundPlayer())
        window.setGeometry(200, 150, 600, 500)
        window._save_state()
        window.close()

        config2 = ConfigManager(config_path)
        assert config2.get("window_x") == 200
        assert config2.get("window_y") == 150
        assert config2.get("window_width") == 600
        assert config2.get("window_height") == 500
