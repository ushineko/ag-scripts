# Spec 008: Cooperative usage cache (shared across processes)

> **Note**: This work has no associated issue tracker ticket (personal public repo, per project policy).

## Status: COMPLETE

## Problem

Every monitor instance fetches the usage API independently — there is no shared
state (verified: no cache/daemon/IPC in `src/`; the single-instance `QLockFile`
guards only the GUI, not `--tui`/`--line`). Running one `--tui` strip per herdr
project therefore means N independent pollers, ~N requests per interval against
`api.anthropic.com/api/oauth/usage`. That endpoint rate-limits (HTTP 429), and
each process backs off in isolation, so more panes = more 429s. A secondary risk
is concurrent OAuth token refreshes racing on the credential store.

The user runs one strip per herdr project (no global shared pane is possible), so
the count scales with open projects.

## Decision

Add a **daemonless cooperative file cache**: terminal-mode instances coordinate
through a shared cache file so that, regardless of how many run, only ~1 API
request is made per freshness window. This is the "central updater" effect
without a daemon — whichever instance first sees a stale cache does the fetch and
writes it; the rest read the file.

- Coordination is via the cache file's **attempt gate** plus a **non-blocking
  lock** (to avoid a thundering herd at startup).
- The cache stores only the **last successful** usage payload (last-known-good);
  failed fetches push the gate out (honoring `Retry-After`) but never clobber
  good data — so an outage/429 doesn't make every pane flap to an error.
- Default **on** for `--tui` and `--line`; `--no-cache` forces the old
  per-process direct fetch.
- The cache holds usage percentages and reset timestamps only — **no
  credentials/tokens** (those stay in the OS credential store, read by
  `oauth.fetch_claude_usage`).

### Cache file

Location (new `config.get_cache_dir()`, mirroring `get_config_dir`/`get_log_dir`):
macOS `~/Library/Caches/claude-usage-widget/`, Windows
`%LOCALAPPDATA%\claude-usage-widget\cache\`, Linux
`${XDG_CACHE_HOME:-~/.cache}/claude-usage-widget/`. File `usage.json`:

```json
{
  "next_attempt_at": 1751050000.0,   // epoch; no instance fetches before this
  "fetched_at": 1750999940.0,        // when `data` (last good) was obtained; age basis
  "data": { ...usage payload... }    // last SUCCESSFUL payload, or null if never
}
```

A single gate (`next_attempt_at`) unifies freshness and backoff: within the gate,
instances read `data` and make no API call; past it, one instance fetches.

### Coordination algorithm (`fetch_usage_cached(ttl) -> (data, fetched_at)`)

1. Read cache. If present and `now < next_attempt_at` → return `(data, fetched_at)`
   (cache hit, **no API call**).
2. Otherwise try a **non-blocking** exclusive lock (`usage.lock`):
   - **Lock acquired**: re-read the cache (another instance may have just
     refreshed inside the gate — if so, return it). Else call
     `oauth.fetch_claude_usage()`:
     - success → write `{next_attempt_at: now+ttl, fetched_at: now, data: result}`
       atomically; return `(result, now)`.
     - failure → keep prior `data`/`fetched_at`, set
       `next_attempt_at = now + max(ttl, retry_after or 0)`; return the prior
       good `data` if any (so panes keep showing it), else the error dict.
   - **Lock not acquired** (another instance is fetching): return the current
     cached `(data, fetched_at)` (or `(None, None)` if no file yet).

Lock: `fcntl.flock(LOCK_EX | LOCK_NB)` on POSIX (auto-released on process death —
no stale-lock handling needed); where `fcntl` is unavailable (Windows), the lock
is a no-op and coordination falls back to the gate alone (still ~1 fetch/interval
in steady state; only a simultaneous cold start can double-fetch). Writes are
atomic (`tmp` + `os.replace`).

## Implementation

- `src/config.py` — add `get_cache_dir()`.
- `src/usage_cache.py` (new, Qt-free) — `get_cache_path()`, `read_cache()`,
  `_write_cache()` (atomic), a `_locked()` context manager (flock, non-blocking,
  graceful no-op), and `fetch_usage_cached(ttl)` implementing the algorithm above.
- `src/tui.py` —
  - `run_line(color, *, use_cache, ttl)`: `data, _ = fetch_usage_cached(ttl)` (or
    `fetch_claude_usage()` when `--no-cache`); print; exit.
  - `run_tui(interval, color, *, use_cache)`: poll loop calls
    `fetch_usage_cached(interval)`; render `build_tui_view(data, note=...)` where
    the note is `cached {age}` when `now - fetched_at` exceeds ~1.5×interval. The
    per-process exponential backoff in `run_tui` is **removed** — the shared gate
    (with `Retry-After`) subsumes it.
- `src/main.py` — add `--no-cache`; thread it + the resolved TTL/interval into the
  run wrappers.

## Acceptance Criteria

- [x] `fetch_usage_cached(ttl)` returns the cached reading without calling the API when `now < next_attempt_at`; calls the API and writes the cache when the gate has passed (`usage_cache.fetch_usage_cached`; `TestGate.test_fresh_gate_returns_cache_without_fetching` / `test_expired_gate_refetches`)
- [x] Under concurrent callers within one TTL window, only **one** underlying `oauth.fetch_claude_usage()` call happens (others read the cache) — `TestGate.test_single_fetch_under_repeat` (5 calls → 1 fetch); also verified cross-process with the real binary (two `--line` runs share `fetched_at`)
- [x] A held lock makes a caller read the cache instead of fetching (no second API call); the lock auto-releases (flock) so a crashed holder cannot wedge the cache (`_locked`; `TestLock.test_held_lock_reads_cache_instead_of_fetching`)
- [x] A failed fetch does NOT overwrite the last-good `data`; it pushes `next_attempt_at` out by `max(ttl, retry_after)` so failures/429s don't herd; callers still receive the last-good reading (`TestFailure.*`)
- [x] `--tui`/`--line` use the cache by default; `--no-cache` performs a direct per-process fetch (old behavior) (`main.run_*_mode` → `use_cache=not args.no_cache`; `TestCacheWiring`)
- [x] `--tui` shows a consistent staleness note (`cached Xm ago`) derived from the shared `fetched_at` when older than ~1.5×interval; fresh readings show no note (`_staleness_note`; `TestStalenessNote`)
- [x] The cache file contains only usage data — no `accessToken`/`refreshToken`/credentials (`TestIO.test_no_credentials_persisted`)
- [x] Atomic write (`tmp`+`os.replace`); a corrupt/missing/partial cache file is treated as “no cache” (no crash) (`_write_cache`/`read_cache`; `TestIO.test_atomic_round_trip` / `test_corrupt_file_is_treated_as_no_cache` / `test_missing_file_is_none`)
- [x] `get_cache_dir()` returns the platform-correct path (macOS Caches / Windows LOCALAPPDATA / Linux XDG) (`config.get_cache_dir`)
- [x] Tests cover: gate hit (no fetch), single-fetch-under-concurrency, lock-held read path, failure preserves last-good + gate push, `retry_after` honored, `--no-cache` bypass, atomic round-trip + corrupt-file tolerance (`tests/test_usage_cache.py`, `tests/test_tui.py`)
- [x] README updated (Terminal mode: shared-cache behavior + `--no-cache`, CLI table, Changelog) and version bumped (3.1.0 → 3.2.0)
- [x] Validation report created in `validation-reports/`

## Out of scope (future)

- GUI participation: the single-instance GUI still polls independently. Optionally
  `--fetch-json` (its QProcess child) could write the same cache so GUI fetches
  feed the panes — deferred to keep this change focused on the terminal modes.
