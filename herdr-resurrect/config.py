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
    "cmdline_patterns": [],        # regexes on full cmdline (capture by command, not name)
    "history": 3,                  # snapshots to keep in history/
    # Declarative label -> command restore. For each live pane whose herdr label
    # matches a key (exact, or the bare suffix after the last ':'), restore runs
    # the command when the pane is idle. Independent of the snapshot: it needs no
    # capture, so it works where herdr's Windows process-info can't report what's
    # running. e.g. {"panel:yazi": "yazi", "panel:usage": "python -m src.main --tui"}
    "label_commands": {},
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
