"""Configuration management for Claude Usage Widget."""

import json
import os
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)

# Default configuration values
DEFAULTS = {
    "session_budget": 500000,
    "window_hours": 4,
    "reset_hour": 2,
    "token_offset": 0,
    "update_interval_seconds": 30,
    "start_minimized": True,
    "show_on_startup": True,
}


def get_config_dir() -> Path:
    """Get the configuration directory path."""
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        config_dir = Path(appdata) / "claude-usage-widget"
    else:
        # Fallback to user home directory
        config_dir = Path.home() / ".claude-usage-widget"
    log.debug("config_dir", path=str(config_dir))
    return config_dir


def get_config_path() -> Path:
    """Get the configuration file path."""
    return get_config_dir() / "config.json"


def ensure_config_dir() -> None:
    """Ensure the configuration directory exists."""
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    log.debug("ensured_config_dir", path=str(config_dir))


def load_config() -> dict[str, Any]:
    """Load configuration from file, creating defaults if needed."""
    config_path = get_config_path()
    log.debug("loading_config", path=str(config_path))

    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            # Merge with defaults to ensure all keys exist
            merged = {**DEFAULTS, **config}
            log.debug("config_loaded", config=merged)
            return merged
        except (json.JSONDecodeError, IOError) as e:
            log.warning("config_load_error", error=str(e), using="defaults")
            return DEFAULTS.copy()
    else:
        log.info("config_not_found", path=str(config_path), action="creating_defaults")
        save_config(DEFAULTS)
        return DEFAULTS.copy()


def save_config(config: dict[str, Any]) -> None:
    """Save configuration to file."""
    ensure_config_dir()
    config_path = get_config_path()

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    log.debug("config_saved", path=str(config_path))


def get_setting(key: str, default: Any = None) -> Any:
    """Get a single setting value."""
    config = load_config()
    return config.get(key, default if default is not None else DEFAULTS.get(key))


def set_setting(key: str, value: Any) -> None:
    """Set a single setting value."""
    log.info("setting_changed", key=key, value=value)
    config = load_config()
    config[key] = value
    save_config(config)


def get_claude_projects_dir() -> Path:
    """Get the Claude projects directory path."""
    userprofile = os.environ.get("USERPROFILE", "")
    if userprofile:
        projects_dir = Path(userprofile) / ".claude" / "projects"
    else:
        projects_dir = Path.home() / ".claude" / "projects"
    log.debug("claude_projects_dir", path=str(projects_dir))
    return projects_dir


def is_claude_installed() -> bool:
    """Check if Claude CLI appears to be installed."""
    claude_dir = get_claude_projects_dir().parent
    installed = claude_dir.exists()
    log.info("claude_installed_check", claude_dir=str(claude_dir), installed=installed)
    return installed
