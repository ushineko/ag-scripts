import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "alacritty-maximizer"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(config: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2) + "\n")


def get_default_monitor() -> str | None:
    return load_config().get("default_monitor")


def set_default_monitor(position_id: str) -> None:
    config = load_config()
    config["default_monitor"] = position_id
    save_config(config)


def clear_default_monitor() -> None:
    config = load_config()
    config.pop("default_monitor", None)
    save_config(config)


def remove_config() -> None:
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()
    if CONFIG_DIR.exists() and not any(CONFIG_DIR.iterdir()):
        CONFIG_DIR.rmdir()
