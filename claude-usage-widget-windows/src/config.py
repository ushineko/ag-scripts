"""Configuration management for Claude Usage Widget."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import structlog

from .platform_support import IS_MACOS

log = structlog.get_logger(__name__)

DEFAULTS = {
    "update_interval_seconds": 60,
    "opacity": 0.95,
    "widget_position": None,  # None = auto-position bottom-right
    "font_size": 9,  # base label font size in px; title renders +2
}


def get_config_dir() -> Path:
    """Get the configuration directory path.

    macOS: ``~/Library/Application Support/claude-usage-widget`` (native).
    Windows: ``%APPDATA%\\claude-usage-widget``.
    Other: ``~/.claude-usage-widget``.
    """
    if IS_MACOS:
        return Path.home() / "Library" / "Application Support" / "claude-usage-widget"
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        return Path(appdata) / "claude-usage-widget"
    return Path.home() / ".claude-usage-widget"


def get_config_path() -> Path:
    """Get the configuration file path."""
    return get_config_dir() / "config.json"


def get_cache_dir() -> Path:
    """Get the cache directory path (shared across processes).

    macOS: ``~/Library/Caches/claude-usage-widget`` (native).
    Windows: ``%LOCALAPPDATA%\\claude-usage-widget\\cache``.
    Other: ``${XDG_CACHE_HOME:-~/.cache}/claude-usage-widget``.
    """
    if IS_MACOS:
        return Path.home() / "Library" / "Caches" / "claude-usage-widget"
    localappdata = os.environ.get("LOCALAPPDATA", "")
    if localappdata:
        return Path(localappdata) / "claude-usage-widget" / "cache"
    xdg_cache = os.environ.get("XDG_CACHE_HOME", "")
    base = Path(xdg_cache) if xdg_cache else Path.home() / ".cache"
    return base / "claude-usage-widget"


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
