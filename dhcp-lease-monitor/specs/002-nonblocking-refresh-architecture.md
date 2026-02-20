# Spec 002: Non-Blocking Refresh Architecture

**Status**: COMPLETE
**Date**: 2026-02-20

## Overview

The DHCP lease monitor must keep the PyQt UI responsive while lease updates are processed. Refresh work (lease parsing, route/interface detection, and reverse-DNS enrichment) was previously executed on the main/UI thread and could stall input/rendering during slow resolver calls or bursty update events.

This spec moves refresh execution to a background worker thread and keeps only UI rendering/state-application on the main thread.

## Problem Statement

Observed behavior:
- Widget intermittently hangs or becomes unresponsive.
- Refresh triggers can happen from multiple sources (manual refresh, inotify, fallback timer).
- Reverse-DNS lookup latency can cause blocking if done on the UI thread.

## Goals

1. Prevent lease refresh operations from blocking the UI event loop.
2. Preserve existing refresh triggers (inotify, debounce, fallback timer, manual refresh).
3. Keep result application deterministic when multiple refreshes are queued.
4. Bound DNS/PTR lookup latency so refresh work does not accumulate indefinitely.

## Non-Goals

- Changing visual layout or UX behavior.
- Adding write operations to network/system state.
- Introducing new external dependencies.

## Requirements

1. **Background refresh worker**
   - Refresh work executes in a dedicated `QThread` worker (`LeaseRefreshWorker`).
   - Worker owns parsing, enrichment, and interface detection.

2. **Request coalescing**
   - While work is active, only the latest pending refresh request is retained.
   - Avoid redundant repeated refresh execution under rapid inotify bursts.

3. **Stale result protection**
   - UI applies results only if they match the latest issued request id.
   - Older completions are ignored.

4. **Bounded reverse-DNS**
   - Reverse-DNS lookup uses timeout-bounded `getent hosts`.
   - Positive and negative cache TTL behavior remains in place.

5. **Clean shutdown**
   - Worker thread must be quit/joined in widget close lifecycle.

## Design

- Add `LeaseRefreshWorker(QObject)` with:
  - `queue_refresh(request_id, lease_file, include_expired)`
  - local pending queue slot (`_pending`) + `_busy` flag
  - `refresh_ready` and `refresh_failed` signals
- In `DhcpLeaseMonitor`:
  - add `refresh_requested` signal to dispatch refresh jobs to worker via queued connection
  - convert `refresh_leases()` into enqueue-only logic
  - add `_on_refresh_ready()` and `_on_refresh_failed()` handlers with request-id staleness checks
  - stop worker thread in `closeEvent`

## Acceptance Criteria

1. UI does not execute lease file parse/interface detection/reverse-DNS directly.
2. Existing timers and inotify triggers still cause refresh updates.
3. Under rapid trigger bursts, stale results are discarded and only latest state is rendered.
4. Project tests pass and syntax checks pass.
5. Security posture remains read-only; no privileged/system-modifying behavior introduced.

## Changed Files

- `dhcp-lease-monitor/dhcp-lease-monitor.py`
