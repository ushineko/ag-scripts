"""Detect herdr server restarts and serialize restores.

herdr rebuilds a restarted server's layout as bare shells and offers no hook for
it, so the programs that were running stay gone until something calls restore.
On Linux the login timer covers a reboot, but nothing covers a server restart
without one, and on macOS nothing covers either (spec 003).

The restart signal is the session's API socket: herdr creates it when the
server starts, so its birth time identifies one server instance. A change since
the last recorded value means the server restarted; the same timestamp doubles
as the server's start time for the clobber guard's grace window.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import time

import config
import snapshot
from snapshot import PaneSnap

FIRST_SEEN = "first"
UNCHANGED = "unchanged"
RESTARTED = "restarted"

# How long a restore waits for a concurrent one before skipping.
LOCK_WAIT_SEC = 10.0


def server_identity(socket_path: str) -> float | None:
    """Start time (epoch seconds) of the server owning `socket_path`, or None
    if there is no socket. Birth time where the platform records it (macOS,
    BSD), else mtime -- herdr does not touch the socket after creating it."""
    if not socket_path:
        return None
    try:
        st = os.stat(socket_path)
    except OSError:
        return None
    return float(getattr(st, "st_birthtime", st.st_mtime))


def load_state() -> dict[str, float]:
    """session -> last recorded server identity. Missing or corrupt == empty."""
    try:
        with open(config.STATE_PATH) as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    servers = data.get("servers", {}) if isinstance(data, dict) else {}
    return {k: float(v) for k, v in servers.items()
            if isinstance(v, (int, float))}


def save_state(servers: dict[str, float]) -> None:
    config.ensure_dir()
    tmp = config.STATE_PATH + ".tmp"
    with open(tmp, "w") as fh:
        json.dump({"version": 1, "servers": servers}, fh, indent=2)
    os.replace(tmp, config.STATE_PATH)


def classify(recorded: float | None, current: float) -> str:
    """Whether `current` is a server we have not seen before. A session with no
    record is FIRST_SEEN, not RESTARTED: on first deploy (or a brand-new
    session) there is no evidence of a restart, so nothing gets relaunched."""
    if recorded is None:
        return FIRST_SEEN
    if recorded == current:
        return UNCHANGED
    return RESTARTED


CORROBORATED = "corroborated"
NOT_CORROBORATED = "not-corroborated"
LAYOUT_PENDING = "layout-pending"


def restart_verdict(snaps: list[PaneSnap], live: list[dict],
                    ratio: float) -> str:
    """Whether a changed socket really left the session's programs gone.

    CORROBORATED when at least `ratio` of `snaps` sit on panes that are back
    but idle -- what a restart leaves behind. NOT_CORROBORATED when the
    programs are still running (e.g. a herdr live handoff that kept pane
    processes) or the snapshot has nothing for the session. LAYOUT_PENDING when
    no entry matches a live pane yet: herdr has not rebuilt the layout, so the
    caller must decide later rather than record the new server and lose the
    restart."""
    if not snaps:
        return NOT_CORROBORATED
    panes = [snapshot.match_live_pane(s, live) for s in snaps]
    matched = [p for p in panes if p is not None]
    if not matched:
        return LAYOUT_PENDING
    idle = sum(1 for p in matched if p.get("_fg") is None)
    return CORROBORATED if idle / len(snaps) >= ratio else NOT_CORROBORATED


@contextlib.contextmanager
def restore_lock(wait_sec: float | None = None, poll_sec: float = 0.2):
    """Exclusive lock across processes for the duration of a restore. Yields
    True when held, False when another restore kept it for `wait_sec`
    (default LOCK_WAIT_SEC) -- the caller then skips, so two callers never
    type one command into the same idle pane."""
    config.ensure_dir()
    fh = open(config.LOCK_PATH, "a+")
    try:
        wait = LOCK_WAIT_SEC if wait_sec is None else wait_sec
        deadline = time.monotonic() + wait
        while not _try_lock(fh):
            if time.monotonic() >= deadline:
                yield False
                return
            time.sleep(poll_sec)
        try:
            yield True
        finally:
            _unlock(fh)
    finally:
        fh.close()


def _try_lock(fh) -> bool:
    if sys.platform.startswith("win"):
        import msvcrt
        try:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    import fcntl
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(fh) -> None:
    if sys.platform.startswith("win"):
        import msvcrt
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl
    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
