# Spec 011: OAuth Refresh Backoff

**Status: COMPLETE**

## Description

Add backoff logic to the Claude OAuth token refresh path so that persistent failures (e.g., revoked tokens, 403) don't spam the token endpoint every 30 seconds indefinitely.

## Problem Statement

When the OAuth access token expires, `fetch_claude_usage()` calls `_refresh_oauth_token()` on every 30-second update cycle. If the refresh consistently fails — as happens with a 403 Forbidden when the refresh token is revoked or invalid — the app hammers the token endpoint indefinitely.

Evidence from the current log: **12,388 consecutive `oauth_refresh_failed` entries**, all `HTTP Error 403: Forbidden`, firing every 30 seconds for hours/days at a time.

This wastes network resources, pollutes the log file (the 5MB rotating log fills primarily with these entries), and provides no useful signal after the first few failures.

## Requirements

### Must

- [ ] After a failed refresh attempt, wait progressively longer before retrying (exponential backoff)
- [ ] Distinguish between transient errors (network timeout, 5xx, DNS failure) and permanent errors (401, 403) — back off more aggressively on permanent errors
- [ ] Cap the maximum backoff interval at a reasonable ceiling (e.g., 30 minutes)
- [ ] Log the first failure and when backoff engages, but suppress repeated identical log entries
- [ ] Reset backoff state when a refresh succeeds
- [ ] "Refresh Now" (manual) must reset backoff and force an immediate retry, bypassing any active backoff timer
- [ ] Show a meaningful status in the UI when auth is in backoff (e.g., "Auth expired" rather than silently showing stale data)
- [ ] Reset backoff state automatically when the credentials file changes on disk (detected via mtime check), so re-authentication via `claude` CLI is picked up on the next 30-second cycle without manual intervention

### Must Not

- [ ] Change the 30-second main update timer — battery data should still refresh normally regardless of OAuth state
- [ ] Persist backoff state to disk — in-memory is sufficient; a fresh app start should retry immediately
- [ ] Change the OAuth endpoint URLs, client ID, or request format

## Proposed Approach

Add module-level backoff state to track refresh failures:

```python
_oauth_backoff_until: float = 0.0   # monotonic timestamp; skip refresh if now < this
_oauth_fail_count: int = 0          # consecutive failures
```

In `fetch_claude_usage()`, before calling `_refresh_oauth_token()`:
1. Check if `time.monotonic() < _oauth_backoff_until` — if so, skip the refresh and return `{"error": "auth_backoff"}` immediately.
2. If not in backoff, attempt the refresh.
3. On failure, increment `_oauth_fail_count` and compute the next backoff delay:
   - Transient errors (timeout, network, 5xx): `min(30 * 2^(fail_count - 1), 300)` seconds (cap at 5 minutes)
   - Permanent errors (401, 403): `min(60 * 2^(fail_count - 1), 1800)` seconds (cap at 30 minutes)
4. On success, reset `_oauth_fail_count = 0` and `_oauth_backoff_until = 0.0`.

To distinguish error types, `_refresh_oauth_token()` should return richer information than just `None` — either raise specific exceptions or return a result object that indicates the HTTP status code.

### Credentials file change detection

Track the mtime of `~/.claude/.credentials.json` via `os.stat()` each time `fetch_claude_usage()` runs. Store the last-seen mtime in a module-level variable (`_oauth_creds_mtime`). If the current mtime is newer, reset backoff state before proceeding. This is one `stat` call per 30-second cycle — negligible cost, no inotify dependency.

### Manual refresh bypass

Expose a `reset_oauth_backoff()` function at module level. The "Refresh Now" context menu action calls this before triggering `update_status()`, so the next `fetch_claude_usage()` call will attempt the refresh immediately regardless of backoff state. This covers the scenario where a user re-authenticates via `claude` CLI and wants the monitor to pick it up without waiting out a 30-minute backoff.

### Log suppression

Log at `warning` level on the first failure and when the backoff interval changes. While in backoff, log at `debug` level only (one line per skipped attempt) to avoid filling the log with repeated warnings.

## Acceptance Criteria

- [ ] A 403 refresh failure triggers backoff; the second attempt is not 30 seconds later
- [ ] After 5 consecutive 403 failures, the retry interval is at least 15 minutes
- [ ] A successful refresh after backoff resets the interval to zero
- [ ] The main battery update cycle is unaffected (battery data refreshes every 30s regardless)
- [ ] Log file does not accumulate thousands of identical warning lines during sustained auth failure
- [ ] "Refresh Now" from the context menu resets backoff and retries immediately
- [ ] If the credentials file is updated on disk (e.g., `claude` CLI re-auth), backoff resets automatically on the next cycle
- [ ] Fresh app startup always attempts one refresh immediately (no persisted backoff)
- [ ] Existing tests pass

## Files Changed

- `peripheral-battery-monitor/peripheral-battery.py` — `_refresh_oauth_token()`, `fetch_claude_usage()`, module-level backoff state
