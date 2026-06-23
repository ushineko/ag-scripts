# Spec 006: macOS Spaces/fullscreen visibility + API rate-limit handling

> **Note**: No associated issue tracker ticket (personal public repo, per project policy).

## Status: COMPLETE

## Problem

Two bugs reported against the running macOS widget:

1. **Doesn't follow across Spaces / fullscreen.** The widget stays on top on the
   Space where it was created, but switching to another Space or a fullscreen
   app hides it. The earlier stay-on-top fix (spec 004 follow-up) set the
   NSWindow level and `hidesOnDeactivate = NO`, but not `collectionBehavior`,
   so the panel is bound to its origin Space and sits under fullscreen windows.

2. **Shows "(API error)" after a short time.** Diagnosed from a controlled
   `--fetch-json` loop: the Anthropic usage endpoint returns **HTTP 429**
   (rate limited) after enough requests. `fetch_claude_usage` mapped every
   non-2xx to `api_error` → the widget displayed "(API error)". With each fetch
   a fresh QProcess (no shared state), there was also no client-side backoff, so
   it kept hammering the endpoint at the fixed 30s cadence.

## Fix

### Bug 1 — collectionBehavior
`FloatingWidget._apply_macos_window_level()` additionally sets
`setCollectionBehavior:` to `NSWindowCollectionBehaviorCanJoinAllSpaces (1<<0) |
NSWindowCollectionBehaviorFullScreenAuxiliary (1<<8)`, so the panel appears on
every Space and over fullscreen apps. (Still ctypes/Obj-C, cocoa-gated.)

### Bug 2 — 429 handling + adaptive backoff
- `src/oauth.py`: HTTP 429 now returns `{"error": "rate_limited", "retry_after":
  N}` (delta-seconds `Retry-After` parsed via `_parse_retry_after`); other
  non-2xx still return `api_error`.
- `src/display.py`: new `rate_limited` → "(rate limited — backing off)".
- `src/main.py`: the GUI (long-lived, unlike the per-fetch child) owns the
  backoff. On `rate_limited` it lengthens the poll interval exponentially
  (`base * 2^level`, honoring `Retry-After`, capped at 30 min); on the next
  success it resets to the base interval. Manual Refresh also resets it.
- `src/config.py`: default `update_interval_seconds` 30 → 60 to lower baseline
  request pressure.

### Last-known-good preservation (per maintainer guidance — mirrors peripheral-battery-monitor)

The original "stale" handling only avoided clearing the widget, and the **tray
reset to a gray "no data" icon on any error**. Adopted peripheral-battery's
proven pattern instead: cache the last successful reading and re-render it on
*any* transient error, only showing an error state when there is no cached
reading.

- `src/widget.py`: caches `_last_good` / `_last_good_time`; on error re-renders
  the cached reading via `_render_usage()` and shows a `(reason · Nm ago)`
  staleness line. A 60s `QTimer` keeps the age and reset countdown fresh during
  long backoffs. Falls back to the error/not-logged-in state only with no cache.
- `src/tray.py`: caches `_last_good`; on error keeps the colored icon and marks
  the tooltip "(stale)"; gray "no data" only with no cache.

## Acceptance Criteria

- [x] macOS widget appears on all Spaces and over fullscreen apps (collectionBehavior set; native call returns ok=True). *Visual confirmation deferred to the user's multi-Space/fullscreen setup.*
- [x] HTTP 429 returns `rate_limited` with parsed `retry_after`; other errors unchanged (unit-tested)
- [x] Widget keeps showing last-known data on `rate_limited` rather than "(API error)"
- [x] Poll interval backs off on 429 and resets on success (verified live: forced 429 → `poll_backoff next_interval_s=300`, honoring server `Retry-After`)
- [x] Default poll interval is 60s
- [x] Both widget and tray preserve the last-known-good reading on any transient error (widget shows `(reason · Nm ago)`; tray keeps colored icon + "(stale)" tooltip); error/gray state only with no cache
- [x] Existing tests pass; new tests cover 429 parsing, the rate-limit path, and widget last-known-good rendering (81 passing)
- [x] Validation report created in `validation-reports/`
