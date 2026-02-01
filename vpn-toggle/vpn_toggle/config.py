"""
Configuration management for VPN Toggle
"""
import copy
import json
import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List

from .utils import get_config_file

logger = logging.getLogger('vpn_toggle.config')


DEFAULT_CONFIG = {
    "version": "2.0.0",
    "monitor": {
        "enabled": False,
        "check_interval_seconds": 120,
        "grace_period_seconds": 15,
        "failure_threshold": 3
    },
    "vpns": [],
    "window": {
        "geometry": {
            "x": None,
            "y": None,
            "width": 800,
            "height": 600
        },
        "always_on_top": False
    },
    "logging": {
        "level": "INFO",
        "file": "~/.config/vpn-toggle/vpn-toggle.log"
    }
}


class ConfigManager:
    """
    Thread-safe configuration manager for VPN Toggle.

    Handles loading, saving, and accessing configuration data stored in JSON format.
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize ConfigManager.

        Args:
            config_path: Optional path to config file (defaults to ~/.config/vpn-toggle/config.json)
        """
        self.config_path = Path(config_path) if config_path else get_config_file()
        self.config = None
        self._lock = threading.RLock()  # Use RLock for reentrant locking
        self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """
        Load configuration from file.

        Returns:
            Configuration dictionary

        If file doesn't exist or is invalid, returns default configuration.
        """
        with self._lock:
            if not self.config_path.exists():
                logger.info(f"Config file not found at {self.config_path}, using defaults")
                self.config = copy.deepcopy(DEFAULT_CONFIG)
                self.save_config()  # Now safe with RLock
                return self.config

            try:
                with open(self.config_path, 'r') as f:
                    loaded_config = json.load(f)

                # Merge with defaults (in case new fields were added)
                self.config = self._merge_with_defaults(loaded_config)
                logger.info(f"Loaded configuration from {self.config_path}")
                return self.config

            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to load config from {self.config_path}: {e}")
                logger.info("Falling back to default configuration")
                self.config = copy.deepcopy(DEFAULT_CONFIG)
                return self.config

    def save_config(self) -> None:
        """
        Save configuration to file.

        Creates parent directories if they don't exist.
        """
        with self._lock:
            if self.config is None:
                logger.warning("No configuration to save")
                return

            try:
                self.config_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.config_path, 'w') as f:
                    json.dump(self.config, f, indent=2)
                logger.debug(f"Saved configuration to {self.config_path}")
            except IOError as e:
                logger.error(f"Failed to save config to {self.config_path}: {e}")

    def get_config(self) -> Dict[str, Any]:
        """
        Get the full configuration dictionary.

        Returns:
            Configuration dictionary
        """
        with self._lock:
            return copy.deepcopy(self.config) if self.config else copy.deepcopy(DEFAULT_CONFIG)

    def get_monitor_settings(self) -> Dict[str, Any]:
        """
        Get monitor configuration.

        Returns:
            Monitor settings dictionary
        """
        with self._lock:
            return self.config.get('monitor', DEFAULT_CONFIG['monitor']).copy()

    def update_monitor_settings(self, **kwargs) -> None:
        """
        Update monitor settings.

        Args:
            **kwargs: Monitor settings to update (enabled, check_interval_seconds, etc.)
        """
        with self._lock:
            if 'monitor' not in self.config:
                self.config['monitor'] = copy.deepcopy(DEFAULT_CONFIG['monitor'])

            for key, value in kwargs.items():
                if key in self.config['monitor']:
                    self.config['monitor'][key] = value
                    logger.debug(f"Updated monitor setting: {key}={value}")

            self.save_config()

    def get_vpn_config(self, vpn_name: str) -> Optional[Dict[str, Any]]:
        """
        Get configuration for a specific VPN.

        Args:
            vpn_name: Name of the VPN connection

        Returns:
            VPN configuration dictionary or None if not found
        """
        with self._lock:
            vpns = self.config.get('vpns', [])
            for vpn in vpns:
                if vpn.get('name') == vpn_name:
                    return vpn.copy()
            return None

    def get_all_vpns(self) -> List[Dict[str, Any]]:
        """
        Get all VPN configurations.

        Returns:
            List of VPN configuration dictionaries
        """
        with self._lock:
            return [vpn.copy() for vpn in self.config.get('vpns', [])]

    def update_vpn_config(self, vpn_name: str, vpn_config: Dict[str, Any]) -> None:
        """
        Update or add a VPN configuration.

        Args:
            vpn_name: Name of the VPN connection
            vpn_config: VPN configuration dictionary
        """
        with self._lock:
            if 'vpns' not in self.config:
                self.config['vpns'] = []

            # Find and update existing VPN, or append new one
            found = False
            for i, vpn in enumerate(self.config['vpns']):
                if vpn.get('name') == vpn_name:
                    self.config['vpns'][i] = vpn_config
                    found = True
                    break

            if not found:
                self.config['vpns'].append(vpn_config)

            logger.debug(f"Updated VPN config for: {vpn_name}")
            self.save_config()

    def remove_vpn_config(self, vpn_name: str) -> bool:
        """
        Remove a VPN configuration.

        Args:
            vpn_name: Name of the VPN connection

        Returns:
            True if VPN was removed, False if not found
        """
        with self._lock:
            if 'vpns' not in self.config:
                return False

            original_length = len(self.config['vpns'])
            self.config['vpns'] = [vpn for vpn in self.config['vpns'] if vpn.get('name') != vpn_name]

            if len(self.config['vpns']) < original_length:
                logger.debug(f"Removed VPN config for: {vpn_name}")
                self.save_config()
                return True

            return False

    def update_window_geometry(self, x: int, y: int, width: int, height: int) -> None:
        """
        Update window geometry settings.

        Args:
            x: Window X position
            y: Window Y position
            width: Window width
            height: Window height
        """
        with self._lock:
            if 'window' not in self.config:
                self.config['window'] = copy.deepcopy(DEFAULT_CONFIG['window'])

            self.config['window']['geometry'] = {
                'x': x,
                'y': y,
                'width': width,
                'height': height
            }

            logger.debug(f"Updated window geometry: {x},{y} {width}x{height}")
            self.save_config()

    def get_window_geometry(self) -> Dict[str, Optional[int]]:
        """
        Get window geometry settings.

        Returns:
            Dictionary with x, y, width, height keys
        """
        with self._lock:
            return self.config.get('window', {}).get('geometry', DEFAULT_CONFIG['window']['geometry']).copy()

    def _merge_with_defaults(self, loaded_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge loaded configuration with defaults to handle missing fields.

        Args:
            loaded_config: Configuration loaded from file

        Returns:
            Merged configuration
        """
        merged = copy.deepcopy(DEFAULT_CONFIG)

        # Deep merge for nested dictionaries
        for key, value in loaded_config.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = {**merged[key], **value}
            else:
                merged[key] = value

        return merged
