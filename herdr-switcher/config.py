"""Config + paths for herdr-switcher.

Config lives at ~/.config/herdr-switcher/config.json. Unknown keys are preserved
on save (forward compatibility); a `version` key allows future migrations.
"""

from __future__ import annotations

import json
import os
import sys

IS_LINUX = sys.platform.startswith("linux")
IS_MACOS = sys.platform == "darwin"

CONFIG_DIR = os.path.expanduser("~/.config/herdr-switcher")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
STATE_PATH = os.path.join(CONFIG_DIR, "state.json")

CONFIG_VERSION = 1

DEFAULTS: dict = {
    "version": CONFIG_VERSION,
    "hotkey": "Shift+Tab",          # macOS will default to "Alt+Tab" once supported
    "popup_commit_delay_ms": 600,
    "terminal": "alacritty",        # used to attach detached sessions
    "max_rows": 12,
}

COMMIT_DELAY_MIN_MS = 100
COMMIT_DELAY_MAX_MS = 5000


def ensure_dir() -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)


def load() -> dict:
    cfg = dict(DEFAULTS)
    existed = os.path.exists(CONFIG_PATH)
    try:
        with open(CONFIG_PATH) as fh:
            cfg.update(json.load(fh))
    except (OSError, json.JSONDecodeError):
        pass
    # Clamp the commit delay defensively.
    cfg["popup_commit_delay_ms"] = max(
        COMMIT_DELAY_MIN_MS,
        min(COMMIT_DELAY_MAX_MS, int(cfg.get("popup_commit_delay_ms", 600))),
    )
    # Write a template on first run so the file is discoverable/editable.
    if not existed:
        try:
            save(cfg)
        except OSError:
            pass
    return cfg


def save(cfg: dict) -> None:
    ensure_dir()
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(cfg, fh, indent=2)
    os.replace(tmp, CONFIG_PATH)
