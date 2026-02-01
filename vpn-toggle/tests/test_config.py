"""
Tests for ConfigManager
"""
import json
import pytest
import tempfile
from pathlib import Path

from vpn_toggle.config import ConfigManager, DEFAULT_CONFIG


@pytest.fixture
def temp_config_file():
    """Fixture to provide a unique temporary config file for each test"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test_config.json"


class TestConfigManager:
    """Test suite for ConfigManager"""

    def test_load_default_config_when_file_missing(self, temp_config_file):
        """Test loading default config when file doesn't exist"""
        manager = ConfigManager(str(temp_config_file))

        config = manager.get_config()

        assert config['version'] == "2.0.0"
        assert 'monitor' in config
        assert 'vpns' in config
        assert 'window' in config
        assert temp_config_file.exists()  # Should be created

    def test_save_and_load_config(self, temp_config_file):
        """Test saving and loading config"""
        manager = ConfigManager(str(temp_config_file))

        # Modify config
        manager.config['monitor']['enabled'] = True
        manager.config['monitor']['check_interval_seconds'] = 60
        manager.save_config()

        # Create new manager to load saved config
        manager2 = ConfigManager(str(temp_config_file))
        config = manager2.get_config()

        assert config['monitor']['enabled'] is True
        assert config['monitor']['check_interval_seconds'] == 60

    def test_update_window_geometry(self, temp_config_file):
        """Test updating window geometry"""
        manager = ConfigManager(str(temp_config_file))

        manager.update_window_geometry(100, 200, 800, 600)

        geometry = manager.get_window_geometry()
        assert geometry['x'] == 100
        assert geometry['y'] == 200
        assert geometry['width'] == 800
        assert geometry['height'] == 600

    def test_get_vpn_config_existing(self, temp_config_file):
        """Test retrieving VPN config that exists"""
        manager = ConfigManager(str(temp_config_file))

        # Add a VPN
        vpn_config = {
            'name': 'test_vpn',
            'display_name': 'Test VPN',
            'enabled': True,
            'asserts': []
        }
        manager.update_vpn_config('test_vpn', vpn_config)

        # Retrieve it
        retrieved = manager.get_vpn_config('test_vpn')
        assert retrieved is not None
        assert retrieved['name'] == 'test_vpn'
        assert retrieved['display_name'] == 'Test VPN'

    def test_get_vpn_config_nonexistent(self, temp_config_file):
        """Test retrieving VPN config that doesn't exist"""
        manager = ConfigManager(str(temp_config_file))

        retrieved = manager.get_vpn_config('nonexistent_vpn')
        assert retrieved is None

    def test_update_vpn_config_new(self, temp_config_file):
        """Test adding a new VPN config"""
        manager = ConfigManager(str(temp_config_file))

        vpn_config = {
            'name': 'new_vpn',
            'display_name': 'New VPN',
            'enabled': True,
            'asserts': [
                {'type': 'dns_lookup', 'hostname': 'example.com', 'expected_prefix': '1.2.'}
            ]
        }
        manager.update_vpn_config('new_vpn', vpn_config)

        all_vpns = manager.get_all_vpns()
        assert len(all_vpns) == 1
        assert all_vpns[0]['name'] == 'new_vpn'

    def test_update_vpn_config_existing(self, temp_config_file):
        """Test updating an existing VPN config"""
        manager = ConfigManager(str(temp_config_file))

        # Add initial VPN
        vpn_config = {'name': 'vpn1', 'display_name': 'VPN One', 'enabled': True, 'asserts': []}
        manager.update_vpn_config('vpn1', vpn_config)

        # Update it
        updated_config = {'name': 'vpn1', 'display_name': 'VPN One Updated', 'enabled': False, 'asserts': []}
        manager.update_vpn_config('vpn1', updated_config)

        all_vpns = manager.get_all_vpns()
        assert len(all_vpns) == 1
        assert all_vpns[0]['display_name'] == 'VPN One Updated'
        assert all_vpns[0]['enabled'] is False

    def test_remove_vpn_config(self, temp_config_file):
        """Test removing a VPN config"""
        manager = ConfigManager(str(temp_config_file))

        # Add VPNs
        manager.update_vpn_config('vpn1', {'name': 'vpn1', 'display_name': 'VPN 1'})
        manager.update_vpn_config('vpn2', {'name': 'vpn2', 'display_name': 'VPN 2'})

        # Remove one
        result = manager.remove_vpn_config('vpn1')
        assert result is True

        all_vpns = manager.get_all_vpns()
        assert len(all_vpns) == 1
        assert all_vpns[0]['name'] == 'vpn2'

    def test_remove_vpn_config_nonexistent(self, temp_config_file):
        """Test removing a VPN that doesn't exist"""
        manager = ConfigManager(str(temp_config_file))

        result = manager.remove_vpn_config('nonexistent')
        assert result is False

    def test_update_monitor_settings(self, temp_config_file):
        """Test updating monitor settings"""
        manager = ConfigManager(str(temp_config_file))

        manager.update_monitor_settings(
            enabled=True,
            check_interval_seconds=90,
            failure_threshold=5
        )

        settings = manager.get_monitor_settings()
        assert settings['enabled'] is True
        assert settings['check_interval_seconds'] == 90
        assert settings['failure_threshold'] == 5

    def test_invalid_json_fallback(self, temp_config_file):
        """Test fallback to defaults on corrupted JSON"""
        # Write invalid JSON
        temp_config_file.write_text("{invalid json")

        manager = ConfigManager(str(temp_config_file))
        config = manager.get_config()

        # Should fall back to defaults
        assert config['version'] == "2.0.0"
        assert 'monitor' in config

    def test_merge_with_defaults(self, temp_config_file):
        """Test that loaded config is merged with defaults"""
        # Write partial config (missing some fields)
        partial_config = {
            "version": "2.0.0",
            "monitor": {
                "enabled": True
                # Missing other monitor fields
            }
            # Missing vpns, window, logging
        }
        temp_config_file.write_text(json.dumps(partial_config))

        manager = ConfigManager(str(temp_config_file))
        config = manager.get_config()

        # Should have defaults filled in
        assert config['monitor']['enabled'] is True
        assert config['monitor']['check_interval_seconds'] == 120  # From defaults
        assert 'vpns' in config
        assert 'window' in config
        assert 'logging' in config

    def test_thread_safety(self, temp_config_file):
        """Test that ConfigManager is thread-safe"""
        import threading

        manager = ConfigManager(str(temp_config_file))

        errors = []

        def update_config(vpn_name):
            try:
                for i in range(10):
                    manager.update_vpn_config(vpn_name, {
                        'name': vpn_name,
                        'display_name': f'{vpn_name}_{i}'
                    })
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=update_config, args=(f'vpn{i}',))
            for i in range(5)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        all_vpns = manager.get_all_vpns()
        assert len(all_vpns) == 5
