"""Shared fixtures for foghorn-leghorn tests."""

import pytest


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication instance for the test session."""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def temp_config_dir(tmp_path):
    """Provide a temporary config directory."""
    return tmp_path / "config"


@pytest.fixture
def temp_config_file(temp_config_dir):
    """Provide a temporary config file path."""
    return temp_config_dir / "config.json"


@pytest.fixture
def sample_timer_dict():
    """A timer data dict for testing."""
    return {
        "id": "abc12345",
        "name": "Test Timer",
        "duration_seconds": 300,
        "remaining_seconds": 150,
        "sound_key": "Foghorn",
        "custom_sound_path": "",
        "is_running": True,
        "is_paused": False,
    }


@pytest.fixture
def sample_config(sample_timer_dict):
    """A full config dict for testing."""
    return {
        "window_x": 200,
        "window_y": 100,
        "window_width": 600,
        "window_height": 450,
        "font_size": 36,
        "sound_enabled": True,
        "timers": [sample_timer_dict],
    }
