"""Persistence of megabonker preferences."""

import copy
import json
import os

# Defaults for every preference with a meaningful fallback. load_config merges
# the persisted file over a deep copy of this map, so a config written by an
# older version is backfilled with keys added since. Optional keys without a
# sensible default (e.g. "window_geometry") are read with .get() at the call site.
DEFAULTS = {
    "game_dir": "",
    "last_profile": "",
    "backup_on_save": True,
    "warn_if_running": True,
}


class ConfigManager:
    """Handles persistence of megabonker preferences."""

    def __init__(self):
        self.config_dir = os.path.expanduser("~/.config/megabonker")
        self.config_file = os.path.join(self.config_dir, "config.json")
        self.ensure_config_dir()

    def ensure_config_dir(self):
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)

    def load_config(self) -> dict:
        config = copy.deepcopy(DEFAULTS)
        if not os.path.exists(self.config_file):
            return config
        try:
            with open(self.config_file, 'r') as f:
                config.update(json.load(f))
        except Exception as e:
            print(f"Error loading config: {e}")
        return config

    def save_config(self, data: dict):
        try:
            with open(self.config_file, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")
