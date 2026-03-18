import json
import os


class ConfigManager:
    """Handles persistence of device order and preferences."""

    def __init__(self):
        self.config_dir = os.path.expanduser("~/.config/audio-source-switcher")
        self.config_file = os.path.join(self.config_dir, "config.json")
        self.ensure_config_dir()

    def ensure_config_dir(self):
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)

    def load_config(self) -> dict:
        if not os.path.exists(self.config_file):
            return {"device_priority": [], "auto_switch": False, "arctis_idle_minutes": 0, "mic_links": {}}
        try:
            with open(self.config_file, 'r') as f:
                data = json.load(f)
                if "mic_links" not in data:
                    data["mic_links"] = {}
                return data
        except Exception as e:
            print(f"Error loading config: {e}")
            return {"device_priority": [], "auto_switch": False, "arctis_idle_minutes": 0, "mic_links": {}}

    def save_config(self, data: dict):
        try:
            with open(self.config_file, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")
