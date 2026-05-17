"""Tests for the tray config manager.

Pure Python, no Qt or kscreen-doctor required.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from display_mirror_tray.config import (
    DEFAULT_CONFIG,
    DEFAULT_HOTKEY,
    DEFAULT_REPLICA,
    DEFAULT_SOURCE,
    ConfigManager,
)


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    return tmp_path / "config.json"


def test_first_run_creates_defaults(config_path: Path) -> None:
    cm = ConfigManager(config_path)
    assert cm.get("source") == DEFAULT_SOURCE
    assert cm.get("replica") == DEFAULT_REPLICA
    assert cm.get("global_hotkey") == DEFAULT_HOTKEY
    assert config_path.exists()
    on_disk = json.loads(config_path.read_text())
    assert on_disk["source"] == DEFAULT_SOURCE


def test_round_trip(config_path: Path) -> None:
    cm1 = ConfigManager(config_path)
    cm1.update(source="HDMI-A-2", replica="DP-1", global_hotkey="Meta+Alt+M")
    cm2 = ConfigManager(config_path)
    assert cm2.get("source") == "HDMI-A-2"
    assert cm2.get("replica") == "DP-1"
    assert cm2.get("global_hotkey") == "Meta+Alt+M"


def test_partial_config_merges_defaults(config_path: Path) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({"source": "HDMI-A-3"}))
    cm = ConfigManager(config_path)
    assert cm.get("source") == "HDMI-A-3"
    assert cm.get("replica") == DEFAULT_REPLICA
    assert cm.get("global_hotkey") == DEFAULT_HOTKEY
    assert cm.get("poll_interval_seconds") == DEFAULT_CONFIG["poll_interval_seconds"]


def test_invalid_json_falls_back_to_defaults(config_path: Path) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{not json")
    cm = ConfigManager(config_path)
    assert cm.get("source") == DEFAULT_SOURCE
    assert cm.get("replica") == DEFAULT_REPLICA


def test_set_persists(config_path: Path) -> None:
    cm = ConfigManager(config_path)
    cm.set("global_hotkey", "Ctrl+Alt+M")
    on_disk = json.loads(config_path.read_text())
    assert on_disk["global_hotkey"] == "Ctrl+Alt+M"
