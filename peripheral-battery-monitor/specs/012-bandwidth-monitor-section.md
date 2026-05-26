# Spec 012: Bandwidth Monitor Section

> **Note**: This work has no associated issue tracker ticket. ag-scripts is a personal public GitHub repository and does not use an issue tracker.

## Status: COMPLETE

## Context

The peripheral-battery-monitor widget shows battery levels (top, 2x2 grid) and Claude Code usage (bottom). The user wants a new section between the two that shows real-time and cumulative network bandwidth for an arbitrary, user-configurable set of interfaces, with first-class support for monitoring Tailscale exit-node traffic.

The primary use cases are:

- Watch live traffic on `tailscale0` while routing through an exit node, and see which exit node is currently selected.
- Watch live traffic on a specific physical or virtual interface (e.g., `enp4s0`, `wg0`, `virbr0`).
- Keep a running cumulative byte counter per interface that survives process restarts and can be reset on demand from the context menu.

The existing main loop (`UpdateThread`) polls every 10 minutes, which is too slow for a "realtime" bandwidth display. The bandwidth section needs its own short-interval polling.

The spec also intentionally separates the new functionality into two new files (`bandwidth_reader.py`, `bandwidth_section.py`) to avoid further bloating `peripheral-battery.py` (already ~1300 lines).

## Requirements

### Data layer (`bandwidth_reader.py`)

- Read `/proc/net/dev` for a configurable list of interface names.
- Return JSON-serializable dicts only (no custom dataclasses leaking into the UI layer).
- Output one entry per requested interface with at minimum: `name`, `exists` (bool), `rx_bytes` (int), `tx_bytes` (int), `timestamp` (monotonic float at read time).
- For interface names matching `tailscale*`, optionally enrich with a `metadata` field containing `{ type: "tailscale", backend_state: str, exit_node: str | null, exit_node_online: bool | null }`. The `tailscale status --json` call is opt-in via a flag and is rate-limited so it does not run on every poll.
- Provide a `--json` CLI mode that takes interface names as positional args and prints the JSON document to stdout (logs to stderr), consistent with `battery_reader.py`.
- Provide an importable Python API (`read_interfaces(names: list[str], *, include_tailscale_meta: bool = False) -> dict`) so the UI can poll in-process without subprocess overhead at 2-second cadence.

### UI layer (`bandwidth_section.py`)

- Provide a `BandwidthSection(QFrame)` class that the main monitor inserts between the battery container and the Claude section.
- Render one row per configured interface. Each row shows:
  - Interface name (truncated to ~14 chars), optionally annotated with `→ exit: <hostname>` when the interface is `tailscale*` and an exit node is set.
  - Current rate: down/up arrows with human-readable bytes/sec (e.g., `↓ 1.2 MB/s  ↑ 50 KB/s`).
  - Cumulative total: down/up arrows with human-readable bytes (e.g., `Σ ↓ 1.5 GB  ↑ 200 MB`).
- Compute rate from the difference between consecutive samples (`(curr_bytes - last_bytes) / (curr_ts - last_ts)`). If the kernel counter went backwards (interface re-created, wrap), treat the delta as zero for that sample and reset the baseline.
- Maintain cumulative totals by summing positive deltas. Cumulative values are persisted to the existing settings file and restored on app start. A per-interface "Reset cumulative" menu action zeroes the cumulative and re-anchors the baseline.
- The widget owns its own `QTimer` (2-second interval); it does not piggyback on `UpdateThread`.
- The widget can be hidden via a context-menu toggle; when hidden, the timer stops to avoid wasted polls.
- When no interfaces are configured, the widget shows a single placeholder row ("No interfaces configured — right-click to add") and the frame remains visible (so the user can discover the menu).

### Main monitor integration (`peripheral-battery.py`)

- Insert the bandwidth `QFrame` into `main_layout` between the battery `MainContainer` and the `ClaudeSection`.
- Extend `load_settings()` defaults with:
  - `bandwidth_section_enabled` (default `true`)
  - `bandwidth_interfaces` (default `[]`)
  - `bandwidth_cumulative` (default `{}`; per-interface persisted totals)
- Add a "Bandwidth" submenu to the context menu with:
  - "Show Bandwidth Section" (checkable, toggles visibility)
  - "Add Interface…" — prompts via a simple `QInputDialog` for an interface name (no validation beyond stripping whitespace)
  - For each configured interface, a submenu with "Remove" and "Reset cumulative"
- Style integration: bandwidth frame matches the visual treatment of `ClaudeSection` (same border / background opacity logic from `update_style`).

### Tests (`tests/test_bandwidth_reader.py`)

- Parser test: feed a fixture string mimicking `/proc/net/dev` and confirm the reader extracts the expected `rx_bytes` / `tx_bytes` per interface.
- Missing-interface test: when a requested interface is not present in the fixture, the output entry has `exists: false` and zeroed counters.
- Rate-calculation test (on `bandwidth_section`): two consecutive snapshots N seconds apart yield the expected `rx_bytes_per_sec` / `tx_bytes_per_sec`.
- Counter-reset test: when the second snapshot has lower counters than the first, the rate is reported as 0 and the cumulative is unchanged for that tick.
- JSON contract test: `bandwidth_reader.read_interfaces(...)` output is round-trippable through `json.dumps` / `json.loads` without any custom object handling.

## Acceptance Criteria

- [x] `bandwidth_reader.py` exists with a `read_interfaces(names, *, include_tailscale_meta=False)` function returning a JSON-serializable dict with the shape described under "Data layer".
- [x] `bandwidth_reader.py --json eth0 tailscale0` prints a JSON document to stdout and exits 0 even when one of the requested interfaces is missing.
- [x] When `include_tailscale_meta=True` and a `tailscale*` interface is requested, the entry's `metadata` field includes `backend_state`, `exit_node`, and `exit_node_online`. `tailscale status --json` failures degrade gracefully (metadata becomes `{ type: "tailscale", backend_state: "unknown", exit_node: null, exit_node_online: null }`, no exception bubbles up).
- [x] `bandwidth_section.py` exists with a `BandwidthSection(QFrame)` class exposing `add_interface(name)`, `remove_interface(name)`, `reset_cumulative(name)`, `set_visible(bool)`, and `update_style(alpha, font_scale)`. (Spec originally proposed `update_settings(settings)`; the implemented API uses a push-only `on_settings_changed` callback for state and `update_style` for styling, which is the cleaner shape.)
- [x] The `BandwidthSection` widget owns a `QTimer` at 2-second cadence that calls `bandwidth_reader.read_interfaces(...)` in-process and updates the row labels with the new rate + cumulative.
- [x] Cumulative totals persist to `~/.config/peripheral-battery-monitor.json` under the `bandwidth_cumulative` key and are restored on next start.
- [x] Counter wrap / interface re-creation is detected (current raw counter < last raw counter) and handled by zeroing the delta for that tick and re-anchoring; no negative rates or cumulative regressions appear in the UI.
- [x] `peripheral-battery.py` inserts the `BandwidthSection` between the battery `MainContainer` and the Claude section in `main_layout`, controlled by the `bandwidth_section_enabled` setting.
- [x] The context menu has a "Bandwidth" submenu with: a "Show Bandwidth Section" checkable toggle, an "Add Interface…" action, and per-interface "Remove" / "Reset cumulative" entries.
- [x] When the bandwidth section is hidden, its `QTimer` is stopped (verifiable via `self._timer.isActive() == False` after `set_visible(False)`).
- [x] For `tailscale*` interfaces, the row subtitle shows `→ exit: <hostname>` when an exit node is selected and renders no subtitle when no exit node is set.
- [x] Tests in `tests/test_bandwidth_reader.py` exist and pass; coverage includes the parser, missing-interface, rate-calculation, counter-reset, and JSON-round-trip cases listed under "Tests".
- [x] Running the full pytest suite (`cd peripheral-battery-monitor && python -m pytest tests/`) passes with no regressions.
- [x] `peripheral-battery.py` `__version__` is bumped to `1.6.0` (proposed during implementation; user to confirm during finalization).
- [x] `README.md` is updated with a Bandwidth Monitoring section describing configuration, supported sources, and the Tailscale exit-node display.

## Risks & Assumptions

- **Assumption**: `/proc/net/dev` is available and parseable on the target system (Linux with procfs). Documented limitation; not targeting non-Linux hosts.
- **Assumption**: `tailscale status --json` schema (`BackendState`, `ExitNodeStatus`, `Peer{}.HostName`) is stable across 1.x versions. If the schema changes, the metadata becomes `unknown`; the bandwidth rows still work because byte counters come from `/proc`.
- **Risk**: 2-second polling in-process means `/proc/net/dev` is read on the Qt main thread. This is a single open/read/close per poll (well under 1ms on modern hardware) and is safe to keep on the main thread; revisit only if profiling shows otherwise.
- **Risk**: Cumulative counters persisted to the JSON settings file mean settings is written more often (every ~30s while the section is visible). The file is a single small JSON document; write amplification is negligible for SSDs.
- **Risk**: Adding the section grows the window vertically. Mitigation: the section is hideable via menu toggle (existing `claude_section_enabled` pattern).
- **Rollback**: revert the commit. New files (`bandwidth_reader.py`, `bandwidth_section.py`, the spec, the test) are additive. The patch to `peripheral-battery.py` is small and localized to `initUI()`, the context menu, and `load_settings` defaults. No migrations, no shared state changes.

## Alternatives Considered

- **Use `ip -j -s link show` instead of `/proc/net/dev`**: gives the same counters in JSON form with no parsing, but adds a subprocess per poll. Rejected because `/proc/net/dev` parsing is trivial (8 lines) and avoids subprocess overhead at 2s cadence.
- **Use a long-running `bandwidth_reader.py --watch` subprocess streaming JSON lines**: cleaner separation but adds a pipe, a worker thread to read it, and lifecycle complexity (process death, restart). Rejected for v1 in favor of importable in-process API. The `--json` one-shot mode remains for CLI testing.
- **Bundle bandwidth UI into `peripheral-battery.py`**: rejected explicitly per the user request not to keep growing the main file.

## Executive Summary

Adds a configurable bandwidth section between the existing battery grid and Claude Code section. Two new files keep the new code out of `peripheral-battery.py`: `bandwidth_reader.py` (a JSON data layer over `/proc/net/dev` with optional Tailscale metadata enrichment) and `bandwidth_section.py` (a self-contained `QFrame` owning its own 2-second `QTimer`, per-interface rate/cumulative state, and a context-menu API for add/remove/reset). Tailscale support is intentionally narrow for v1: it tags `tailscale*` rows with the currently selected exit-node hostname via `tailscale status --json` (rate-limited to one call/minute) — byte counters always come from `/proc`. Reviewers should focus on the rate-and-cumulative math in `_InterfaceRow.ingest_sample` (counter-wrap handling is the easiest place to introduce regressions) and the placement of the new frame inside `initUI` of `peripheral-battery.py`.
