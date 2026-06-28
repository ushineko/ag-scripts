"""Most-recently-used stack of spaces, persisted across daemon restarts.

herdr exposes no focus-event stream, so recency is maintained here: the daemon
pushes the current space at each popup and the chosen space on each switch. The
stack is a list of space keys ("session/workspace_id"), most-recent first.
"""

from __future__ import annotations

import json
import os

from config import STATE_PATH, ensure_dir

_MAX = 50


def load() -> list[str]:
    try:
        with open(STATE_PATH) as fh:
            data = json.load(fh)
        keys = data.get("mru", [])
        return [k for k in keys if isinstance(k, str)]
    except (OSError, json.JSONDecodeError):
        return []


def save(keys: list[str]) -> None:
    ensure_dir()
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w") as fh:
        json.dump({"mru": keys[:_MAX]}, fh, indent=2)
    os.replace(tmp, STATE_PATH)


def touch(keys: list[str], key: str) -> list[str]:
    """Return a new MRU list with `key` moved to the front."""
    out = [k for k in keys if k != key]
    out.insert(0, key)
    return out[:_MAX]


def order_spaces(spaces: list, mru_keys: list[str]) -> list:
    """Order `spaces` by MRU (most-recent first), with never-seen spaces after,
    sorted by session then herdr number for stable display."""
    by_key = {s.key: s for s in spaces}
    ordered = [by_key[k] for k in mru_keys if k in by_key]
    seen = set(mru_keys)
    rest = sorted(
        (s for s in spaces if s.key not in seen),
        key=lambda s: (s.session, s.number),
    )
    return ordered + rest
