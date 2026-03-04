"""Configuration management for Claude Usage Widget."""

import json
import os
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)

DEFAULTS = {
    "update_interval_seconds": 30,
    "opacity": 0.95,
    "widget_position": None,  # None = auto-position bottom-right
}


def get_config_dir() -> Path:
    """Get the configuration directory path."""
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        return Path(appdata) / "claude-usage-widget"
    return Path.home() / ".claude-usage-widget"


def get_config_path() -> Path:
    """Get the configuration file path."""
    return get_config_dir() / "config.json"


def load_config() -> dict[str, Any]:
    """Load configuration from file, creating defaults if needed."""
    config_path = get_config_path()

    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            return {**DEFAULTS, **config}
        except (json.JSONDecodeError, IOError) as e:
            log.warning("config_load_error", error=str(e))
            return DEFAULTS.copy()

    log.info("config_not_found", action="creating_defaults")
    save_config(DEFAULTS)
    return DEFAULTS.copy()


def save_config(config: dict[str, Any]) -> None:
    """Save configuration to file."""
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)

    with open(get_config_path(), "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def get_setting(key: str) -> Any:
    """Get a single setting value."""
    config = load_config()
    return config.get(key, DEFAULTS.get(key))


def set_setting(key: str, value: Any) -> None:
    """Set a single setting value and persist."""
    log.info("setting_changed", key=key, value=value)
    config = load_config()
    config[key] = value
    save_config(config)
