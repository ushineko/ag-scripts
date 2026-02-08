import json
import pytest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import config


@pytest.fixture(autouse=True)
def temp_config(tmp_path, monkeypatch):
    config_dir = tmp_path / "alacritty-maximizer"
    config_file = config_dir / "config.json"
    autostart_dir = tmp_path / "autostart"
    autostart_file = autostart_dir / "alacritty-maximizer.desktop"
    monkeypatch.setattr(config, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config, "CONFIG_FILE", config_file)
    monkeypatch.setattr(config, "AUTOSTART_DIR", autostart_dir)
    monkeypatch.setattr(config, "AUTOSTART_FILE", autostart_file)
    return config_file


class TestLoadConfig:
    def test_returns_empty_dict_when_no_file(self):
        assert config.load_config() == {}

    def test_returns_saved_config(self, temp_config):
        temp_config.parent.mkdir(parents=True, exist_ok=True)
        temp_config.write_text('{"default_monitor": "pos-0_0"}')
        assert config.load_config() == {"default_monitor": "pos-0_0"}

    def test_returns_empty_dict_on_invalid_json(self, temp_config):
        temp_config.parent.mkdir(parents=True, exist_ok=True)
        temp_config.write_text("not json")
        assert config.load_config() == {}


class TestSaveConfig:
    def test_creates_dir_and_writes_file(self, temp_config):
        config.save_config({"default_monitor": "pos-1440_0"})
        assert temp_config.exists()
        data = json.loads(temp_config.read_text())
        assert data == {"default_monitor": "pos-1440_0"}

    def test_overwrites_existing(self, temp_config):
        config.save_config({"default_monitor": "pos-0_0"})
        config.save_config({"default_monitor": "pos-1440_0"})
        data = json.loads(temp_config.read_text())
        assert data["default_monitor"] == "pos-1440_0"


class TestGetDefaultMonitor:
    def test_returns_none_when_no_config(self):
        assert config.get_default_monitor() is None

    def test_returns_saved_position(self, temp_config):
        config.set_default_monitor("pos-0_0")
        assert config.get_default_monitor() == "pos-0_0"


class TestSetDefaultMonitor:
    def test_saves_position(self, temp_config):
        config.set_default_monitor("pos-1440_0")
        data = json.loads(temp_config.read_text())
        assert data["default_monitor"] == "pos-1440_0"

    def test_preserves_other_keys(self, temp_config):
        config.save_config({"other_key": "value"})
        config.set_default_monitor("pos-0_0")
        data = json.loads(temp_config.read_text())
        assert data["other_key"] == "value"
        assert data["default_monitor"] == "pos-0_0"


class TestClearDefaultMonitor:
    def test_removes_default(self, temp_config):
        config.set_default_monitor("pos-0_0")
        config.clear_default_monitor()
        assert config.get_default_monitor() is None

    def test_noop_when_no_default(self, temp_config):
        config.clear_default_monitor()
        assert config.get_default_monitor() is None

    def test_preserves_other_keys(self, temp_config):
        config.save_config({"default_monitor": "pos-0_0", "other": "val"})
        config.clear_default_monitor()
        data = json.loads(temp_config.read_text())
        assert "default_monitor" not in data
        assert data["other"] == "val"


class TestRemoveConfig:
    def test_removes_file_and_empty_dir(self, temp_config):
        config.save_config({"default_monitor": "pos-0_0"})
        assert temp_config.exists()
        config.remove_config()
        assert not temp_config.exists()
        assert not temp_config.parent.exists()

    def test_noop_when_no_file(self):
        config.remove_config()

    def test_keeps_dir_if_other_files_exist(self, temp_config):
        config.save_config({"default_monitor": "pos-0_0"})
        other_file = temp_config.parent / "other.txt"
        other_file.write_text("keep me")
        config.remove_config()
        assert not temp_config.exists()
        assert temp_config.parent.exists()


class TestAutostart:
    def test_disabled_by_default(self):
        assert config.is_autostart_enabled() is False

    def test_enable_autostart(self):
        config.set_autostart(True)
        assert config.is_autostart_enabled() is True

    def test_disable_autostart(self):
        config.set_autostart(True)
        config.set_autostart(False)
        assert config.is_autostart_enabled() is False

    def test_preserves_other_config(self):
        config.set_default_monitor("pos-0_0")
        config.set_autostart(True)
        assert config.get_default_monitor() == "pos-0_0"
        assert config.is_autostart_enabled() is True


class TestAutostartEntry:
    def test_install_creates_desktop_file(self):
        config.install_autostart_entry("/path/to/main.py")
        assert config.AUTOSTART_FILE.exists()
        content = config.AUTOSTART_FILE.read_text()
        assert "--autostart" in content
        assert "/path/to/main.py" in content
        assert "X-KDE-autostart-phase=2" in content

    def test_remove_deletes_desktop_file(self):
        config.install_autostart_entry("/path/to/main.py")
        assert config.AUTOSTART_FILE.exists()
        config.remove_autostart_entry()
        assert not config.AUTOSTART_FILE.exists()

    def test_remove_noop_when_no_file(self):
        config.remove_autostart_entry()

    def test_install_overwrites_existing(self):
        config.install_autostart_entry("/old/path/main.py")
        config.install_autostart_entry("/new/path/main.py")
        content = config.AUTOSTART_FILE.read_text()
        assert "/new/path/main.py" in content
        assert "/old/path/main.py" not in content
