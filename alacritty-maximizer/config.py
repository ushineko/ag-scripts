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


def is_autostart_enabled() -> bool:
    return load_config().get("autostart", False)


def set_autostart(enabled: bool) -> None:
    config = load_config()
    config["autostart"] = enabled
    save_config(config)


AUTOSTART_DIR = Path.home() / ".config" / "autostart"
AUTOSTART_FILE = AUTOSTART_DIR / "alacritty-maximizer.desktop"


def install_autostart_entry(main_script_path: str) -> None:
    AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
    content = (
        "[Desktop Entry]\n"
        "Name=Alacritty Maximizer (Autostart)\n"
        "Comment=Auto-launch Alacritty on saved default monitor\n"
        f"Exec=python3 {main_script_path} --autostart\n"
        "Icon=utilities-terminal\n"
        "Type=Application\n"
        "Categories=Utility;Terminal;\n"
        "Terminal=false\n"
        "X-KDE-autostart-phase=2\n"
    )
    AUTOSTART_FILE.write_text(content)


def remove_autostart_entry() -> None:
    if AUTOSTART_FILE.exists():
        AUTOSTART_FILE.unlink()


def remove_config() -> None:
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()
    if CONFIG_DIR.exists() and not any(CONFIG_DIR.iterdir()):
        CONFIG_DIR.rmdir()
