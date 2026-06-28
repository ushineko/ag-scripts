"""Cooperative, daemonless usage cache shared across processes.

Multiple terminal-mode instances (one ``--tui`` strip per herdr project, plus
``--line`` callers) would otherwise each poll the usage API independently,
multiplying requests and 429s. This module coordinates them through a shared
cache file so that — regardless of how many run — only ~1 API request is made
per freshness window.

Coordination uses two things in the cache file:
  * ``next_attempt_at`` — a gate unifying freshness and backoff. Within the gate,
    callers read ``data`` and make no API call; past it, one caller fetches.
  * a non-blocking ``flock`` (``usage.lock``) — avoids a thundering herd at cold
    start. ``flock`` auto-releases on process death, so a crashed holder cannot
    wedge the cache. Where ``fcntl`` is unavailable (Windows) the lock is a
    no-op and the gate alone coordinates.

The cache stores only the last *successful* usage payload (last-known-good) plus
timestamps — no credentials/tokens (those live in the OS credential store, read
by ``oauth.fetch_claude_usage``). A failed fetch never clobbers good data; it
only pushes the gate out (honoring ``Retry-After``), so an outage/429 doesn't
make every pane flap to an error.

Qt-free.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager

import structlog

from .config import get_cache_dir
from .oauth import fetch_claude_usage

log = structlog.get_logger(__name__)


def get_cache_path():
    """Path to the shared usage cache file."""
    return get_cache_dir() / "usage.json"


def _lock_path():
    return get_cache_dir() / "usage.lock"


def read_cache() -> dict | None:
    """Return the parsed cache entry, or None if missing/corrupt/partial."""
    try:
        with open(get_cache_path(), "r", encoding="utf-8") as f:
            entry = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return None
    return entry if isinstance(entry, dict) else None


def _write_cache(entry: dict) -> None:
    """Atomically write the cache entry (tmp + os.replace). Best-effort."""
    try:
        cache_dir = get_cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = get_cache_path()
        tmp = path.parent / f"usage.json.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(entry, f)
        os.replace(tmp, path)
    except OSError as e:
        log.warning("usage_cache_write_failed", error=str(e))


@contextmanager
def _locked():
    """Yield True if the cache lock was acquired (or locking is unavailable),
    False if another process holds it.

    Non-blocking ``flock``; auto-released on close/death. On platforms without
    ``fcntl`` the lock is a no-op (yields True) and coordination relies on the
    gate alone.
    """
    try:
        import fcntl
    except ImportError:
        yield True
        return

    try:
        get_cache_dir().mkdir(parents=True, exist_ok=True)
        fd = os.open(str(_lock_path()), os.O_CREAT | os.O_RDWR, 0o644)
    except OSError:
        # Can't even open the lock file — degrade to gate-only coordination.
        yield True
        return

    acquired = False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError:
            acquired = False
        yield acquired
    finally:
        if acquired:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
        os.close(fd)


def _within_gate(cache: dict | None, now: float) -> bool:
    """True if the attempt gate has not yet passed (use the cache, don't fetch)."""
    return cache is not None and now < cache.get("next_attempt_at", 0)


def fetch_usage_cached(ttl: int) -> tuple[dict | None, float | None]:
    """Return ``(data, fetched_at)`` for the usage reading, coordinating fetches
    across processes so only ~1 API call happens per ``ttl`` window.

    ``data`` is the last successful usage payload when one is available (possibly
    served from cache without any API call), or the live error dict when there is
    no last-known-good. ``fetched_at`` is the epoch time the returned ``data`` was
    obtained (None when there is no good reading), for a consistent staleness age
    across all panes.
    """
    now = time.time()
    cache = read_cache()
    if cache is not None and _within_gate(cache, now):
        return cache.get("data"), cache.get("fetched_at")

    with _locked() as acquired:
        if not acquired:
            # Another instance is fetching right now — use what we have.
            cache = read_cache()
            if cache is not None:
                return cache.get("data"), cache.get("fetched_at")
            return None, None

        # Hold the lock: re-read in case another instance just refreshed.
        cache = read_cache()
        if cache is not None and _within_gate(cache, now):
            return cache.get("data"), cache.get("fetched_at")

        result = fetch_claude_usage()
        if isinstance(result, dict) and not result.get("error"):
            _write_cache({"next_attempt_at": now + ttl, "fetched_at": now, "data": result})
            log.debug("usage_cache_refreshed")
            return result, now

        # Failure: keep last-good, push the gate out (honor Retry-After).
        prev_data = cache.get("data") if cache else None
        prev_fetched = cache.get("fetched_at") if cache else None
        retry = result.get("retry_after") if isinstance(result, dict) else None
        _write_cache({
            "next_attempt_at": now + max(ttl, retry or 0),
            "fetched_at": prev_fetched,
            "data": prev_data,
        })
        log.debug("usage_cache_fetch_failed", error=(result or {}).get("error")
                  if isinstance(result, dict) else None)
        return (prev_data if prev_data is not None else result), prev_fetched
