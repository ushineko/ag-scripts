"""Identifier vocabulary harvested from the installed game and from Steam.

Used to sanity-check ids typed into a save. The game silently ignores an
unrecognised id - it persists it, changes nothing, and gives no feedback - so a
misspelling looks exactly like a feature that does not work. Catching it at edit
time is the difference between a five-second fix and a wasted test cycle.

Two sources, unioned:
  * string literals in global-metadata.dat - covers unlockable/character ids
  * Steam's achievement schema cache      - covers the a_* achievement ids

Neither is complete on its own (some ids are built at runtime or live in asset
bundles), so this is advisory. Callers should only warn about ids the *user*
added, never about ids the game itself wrote - see validate.py.
"""

import os
import re
import subprocess

from megabonker.derive import APPID_DEFAULT, find_game_dir, load_metadata_strings

STEAM_STATS_DIRS = (
    "~/.steam/steam/appcache/stats",
    "~/.local/share/Steam/appcache/stats",
)

_ID_RE = re.compile(r"[A-Za-z0-9_]{2,64}")
_cache: dict[str, set[str]] = {}


def steam_schema_path(appid: str = APPID_DEFAULT) -> str | None:
    """Locate Steam's cached achievement schema for the game."""
    for directory in STEAM_STATS_DIRS:
        path = os.path.join(os.path.expanduser(directory), f"UserGameStatsSchema_{appid}.bin")
        if os.path.exists(path):
            return path
    return None


def _schema_ids(appid: str = APPID_DEFAULT) -> set[str]:
    """Achievement ids from Steam's binary schema cache.

    The file is Valve KeyValues binary; the ids are plain NUL-delimited ASCII
    inside it, so they can be lifted without a full parser.
    """
    path = steam_schema_path(appid)
    if not path:
        return set()
    try:
        data = open(path, "rb").read()
    except OSError:
        return set()
    out = set()
    for chunk in data.split(b"\x00"):
        try:
            text = chunk.decode("ascii")
        except UnicodeDecodeError:
            continue
        if text.startswith("a_") and _ID_RE.fullmatch(text):
            out.add(text)
    return out


def known_ids(game_dir: str | None = None, appid: str = APPID_DEFAULT) -> set[str]:
    """Every identifier we can prove the game knows about.

    Result is cached per game directory; the underlying files only change when
    the game updates.
    """
    game_dir = game_dir or find_game_dir() or ""
    key = f"{game_dir}|{appid}"
    if key in _cache:
        return _cache[key]
    ids: set[str] = set()
    if game_dir:
        try:
            ids |= {s.decode("latin1", "replace") for s in load_metadata_strings(game_dir)}
        except Exception:
            pass
    ids |= _schema_ids(appid)
    _cache[key] = ids
    return ids


def steam_is_running() -> bool:
    """True if the Steam client is up.

    Matters because the CloudDir saves are Steam Cloud synced: editing while
    Steam is running risks the cloud copy winning and silently reverting.
    """
    try:
        return subprocess.run(["pgrep", "-x", "steam"], capture_output=True).returncode == 0
    except FileNotFoundError:
        return False
