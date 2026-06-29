"""Config + paths for herdr-resurrect."""

from __future__ import annotations

import json
import os

CONFIG_DIR = os.path.expanduser("~/.config/herdr-resurrect")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
SNAPSHOT_PATH = os.path.join(CONFIG_DIR, "snapshot.json")
HISTORY_DIR = os.path.join(CONFIG_DIR, "history")

CONFIG_VERSION = 1

DEFAULTS: dict = {
    "version": CONFIG_VERSION,
    "save_interval_min": 5,        # periodic systemd-timer save cadence
    "whitelist_add": [],           # extra program names to capture/restore
    "whitelist_remove": [],        # default-whitelist names to drop
    "history": 3,                  # snapshots to keep in history/
}


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
