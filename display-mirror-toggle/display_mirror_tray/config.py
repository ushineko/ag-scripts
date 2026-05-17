"""Persistent config for the display-mirror tray.

JSON-on-disk under ~/.config/display-mirror-toggle/. Schema is small:
the source/replica connector pair, the optional global hotkey, and
window/UI niceties.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger("display_mirror_tray.config")


DEFAULT_SOURCE = "HDMI-A-1"
DEFAULT_REPLICA = "DP-3"
DEFAULT_HOTKEY = ""  # empty = no hotkey registered

DEFAULT_CONFIG: dict[str, Any] = {
    "version": "1.1.0",
    "source": DEFAULT_SOURCE,
    "replica": DEFAULT_REPLICA,
    "global_hotkey": DEFAULT_HOTKEY,
    "poll_interval_seconds": 5,
}


def config_dir() -> Path:
    return Path(os.path.expanduser("~/.config/display-mirror-toggle"))


def config_file() -> Path:
    return config_dir() / "config.json"


class ConfigManager:
    """Thread-safe JSON config manager.

    The schema is intentionally flat — the tray has very few tunables
    and there's no migration story worth setting up yet.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config_file()
        self._lock = threading.RLock()
        self.data: dict[str, Any] = copy.deepcopy(DEFAULT_CONFIG)
        self.load()

    def load(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                self.data = copy.deepcopy(DEFAULT_CONFIG)
                self.save()
                return self.data
            try:
                with self.path.open("r") as f:
                    loaded = json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                logger.error(f"Failed to load config from {self.path}: {e}")
                self.data = copy.deepcopy(DEFAULT_CONFIG)
                return self.data

            merged = copy.deepcopy(DEFAULT_CONFIG)
            merged.update(loaded if isinstance(loaded, dict) else {})
            self.data = merged
            return self.data

    def save(self) -> None:
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("w") as f:
                    json.dump(self.data, f, indent=2)
            except OSError as e:
                logger.error(f"Failed to save config to {self.path}: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self.data[key] = value
            self.save()

    def update(self, **kwargs: Any) -> None:
        with self._lock:
            self.data.update(kwargs)
            self.save()
