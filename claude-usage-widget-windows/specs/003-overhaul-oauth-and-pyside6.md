# Spec 003: Overhaul Claude Usage Widget — OAuth API + PySide6

## Status: IMPLEMENTED

## Summary

Replace the current JSONL-parsing data source with the Anthropic OAuth usage API (same approach as peripheral-battery-monitor), and replace CustomTkinter with PySide6 for a more native Windows experience. This is a ground-up rewrite of the widget.

---

## Motivation

**Data source problems with current approach**:
- Parses local `.jsonl` files from `%USERPROFILE%\.claude\projects\` — only captures local CLI usage
- Requires manual calibration against `/usage` to stay accurate
- Cannot account for web interface or multi-device usage
- Session window/budget math is fragile (fractional hours bug in boundary calculation)
- The OAuth API returns authoritative utilization percentages directly — no estimation needed

**UI/toolkit problems with current approach**:
- CustomTkinter looks non-native on Windows 11 (tkinter roots show through)
- No built-in system tray support (requires pystray in a separate thread)
- Widget and tray poll independently with no shared state
- Calibration dialog creates orphaned CTk roots (memory leak)
- Dead code: `popup.py` is unused, `start_minimized`/`show_on_startup` config keys are unused

---

## Design Decisions

### Data Source: OAuth API

Adopt the same OAuth usage fetch pattern from `peripheral-battery-monitor/peripheral-battery.py` (lines 30-245):

- **Endpoint**: `GET https://api.anthropic.com/api/oauth/usage`
- **Credentials**: Read from `~/.claude/.credentials.json` (cross-platform: `%USERPROFILE%\.claude\.credentials.json` on Windows)
- **Token refresh**: Auto-refresh expired access tokens via `POST https://console.anthropic.com/api/oauth/token`
- **Backoff**: Exponential backoff on refresh failures (transient: 30s base / 5min cap; permanent 401/403: 60s base / 30min cap)
- **Backoff reset**: On successful refresh, manual "Refresh Now" action, or credentials file mtime change (detects `claude login`)
- **Response**: JSON with `five_hour` and `seven_day` utilization percentages (0.0-1.0), plus `resets_at` ISO 8601 timestamps

This eliminates: JSONL parsing, session window math, budget estimation, token counting, and calibration entirely. The API is the source of truth.

### UI Toolkit: PySide6

**Why PySide6 over alternatives**:

| Option | Verdict | Reason |
|--------|---------|--------|
| CustomTkinter (current) | Replace | Non-native appearance, no built-in tray, threading issues |
| pywebview (WebView2) | Rejected | Transparency broken on Windows 11 ([pywebview#1611](https://github.com/r0x0r/pywebview/issues/1611)), no built-in tray |
| pywin32 (raw Win32) | Rejected | High development effort for UI rendering, dated appearance |
| WPF via pythonnet | Rejected | Awkward Python/.NET bridge, niche community, no natural event binding |
| WinUI 3 | Rejected | No viable Python bindings exist (2026) |
| **PySide6** | **Selected** | Native `QSystemTrayIcon`, reliable frameless+transparent windows, Qt platform styling on Windows, LGPL license, same toolkit family as peripheral-battery-monitor |

**Trade-off**: PySide6 is ~80-150 MB installed vs CustomTkinter's ~5 MB. Acceptable for a personal tool. If distribution size matters later, `pyside6-deploy` or PyInstaller with exclusions can trim it.

---

## Architecture

```
claude-usage-widget-windows/
  src/
    main.py              # Entry point, CLI args, single-instance lock
    oauth.py             # OAuth credential reading, token refresh, usage fetch, backoff
    widget.py            # PySide6 floating widget (QWidget, frameless, translucent)
    tray.py              # QSystemTrayIcon with context menu
    config.py            # Settings persistence (%APPDATA%\claude-usage-widget\config.json)
    logging_config.py    # structlog setup
  tests/
    test_oauth.py        # OAuth logic, backoff, credential reading
    test_widget_logic.py # Display formatting, color thresholds
    test_config.py       # Config persistence
  install.bat
  uninstall.bat
  requirements.txt
  requirements-dev.txt
  README.md
```

### Data Flow

```
QTimer (30s) ──> Worker QThread ──> fetch_claude_usage() via urllib
                                          │
                                    OAuth API response
                                          │
                                    Signal (dict) ──> Main thread
                                          │
                              ┌────────────┴────────────┐
                              │                         │
                         Widget.update()          Tray.update()
                         (progress bar,           (icon color,
                          percentages,             tooltip)
                          countdown)
```

- Single `QTimer` triggers updates — widget and tray share the same data (no duplicate fetches)
- Worker thread prevents UI blocking during network calls
- Signal/slot pattern for thread-safe UI updates (same pattern as peripheral-battery-monitor's `UpdateThread`)

---

## What the Widget Displays

The API response provides these fields (based on peripheral-battery-monitor's usage):

```json
{
  "five_hour": { "utilization": 0.42, "resets_at": "2026-03-04T18:00:00Z" },
  "seven_day": { "utilization": 0.15, "resets_at": "2026-03-10T02:00:00Z" },
  "model_rates": { ... }
}
```

### Widget Layout

```
┌──────────────────────────────┐
│  Claude Usage            ─ × │  ← Draggable title area, minimize to tray, close
├──────────────────────────────┤
│  5h: [████████░░░░░░░] 42%   │  ← Primary progress bar (color-coded)
│  Resets in 2h 15m             │  ← Countdown from resets_at
│                               │
│  7d: 15%                      │  ← Secondary stat (text only)
└──────────────────────────────┘
```

- Frameless, semi-transparent dark background with rounded corners
- Always-on-top (`Qt.WindowStaysOnTopHint`)
- Draggable by title area
- Right-click context menu: Refresh Now, Settings submenu, Minimize to Tray, Exit
- Minimize button (─) hides widget to tray; tray left-click restores it

### Tray Icon

- `QSystemTrayIcon` with dynamically generated icon (colored circle based on 5h utilization)
- Tooltip: "Claude: 5h 42% | 7d 15%"
- Left-click: Toggle widget visibility
- Right-click: Context menu (Show/Hide Widget, Refresh Now, Exit)

### Color Thresholds

| 5h Utilization | Color | Hex |
|---|---|---|
| < 50% | Green | #4caf50 |
| 50-80% | Yellow/Orange | #ff9800 |
| > 80% | Red | #f44336 |
| Error/offline | Gray | #6b7280 |

---

## What Gets Removed

Everything related to the old data source and toolkit:

- `claude_stats.py` — JSONL parsing, session window math, token aggregation
- `calibration.py` — No longer needed (API is authoritative)
- `popup.py` — Dead code (never used)
- All CustomTkinter and pystray dependencies
- Config keys: `session_budget`, `window_hours`, `reset_hour`, `token_offset` (API provides all timing)
- Pillow dependency (PySide6 handles icon generation natively via QPainter)

## What Gets Added

- `oauth.py` — Ported from peripheral-battery-monitor with Windows path adjustments
- PySide6 widget and tray implementation
- Single-instance lock via `QLockFile`

---

## Configuration (Simplified)

`%APPDATA%\claude-usage-widget\config.json`:

```json
{
  "update_interval_seconds": 30,
  "opacity": 0.95,
  "widget_position": [100, 100]
}
```

Budget, window hours, reset hour, and calibration offset are all eliminated — the API handles this.

---

## Error States

| Condition | Widget Display | Tray |
|---|---|---|
| No credentials file | "Not logged in — run `claude login`" | Gray icon |
| Token expired, no refresh token | "Auth expired — run `claude login`" | Gray icon |
| Refresh backoff active | Show last known data + "(stale)" | Last known color |
| Network error / API error | Show last known data + "(offline)" | Last known color |
| API returns valid data | Normal display | Color-coded icon |

---

## Acceptance Criteria

- [ ] Widget reads Claude usage from the OAuth API, not from local JSONL files
- [ ] OAuth token refresh with exponential backoff (matching peripheral-battery-monitor behavior)
- [ ] Backoff resets on: successful refresh, manual Refresh Now, or credentials file change
- [ ] PySide6 floating widget: frameless, semi-transparent, always-on-top, draggable
- [ ] QSystemTrayIcon with color-coded icon, tooltip, and context menu
- [ ] Single QTimer drives both widget and tray updates (no duplicate fetches)
- [ ] Widget shows: 5h utilization progress bar, 5h countdown, 7d utilization
- [ ] Right-click context menu on widget
- [ ] Minimize to tray / restore from tray
- [ ] Single-instance enforcement
- [ ] Structured logging with --debug flag
- [ ] Console mode (--no-gui) that fetches and prints usage, then exits
- [ ] All existing tests replaced with tests for new OAuth and display logic
- [ ] install.bat and uninstall.bat present
- [ ] Old dead code removed (popup.py, calibration.py, claude_stats.py)

---

## Out of Scope

- Linux/macOS support (this is the Windows-specific widget; peripheral-battery-monitor covers Linux)
- PyInstaller packaging (can be added later)
- Model-rate breakdown display (can be added later if the API provides it)
- Auto-start on login (can be added later via Start Menu shortcut or registry)
