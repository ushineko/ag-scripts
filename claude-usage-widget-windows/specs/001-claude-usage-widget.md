# Spec 001: Claude Usage Widget for Windows

## Overview

A standalone Windows system tray widget that displays Claude Code CLI usage metrics, providing real-time visibility into token consumption within rolling time windows.

## Motivation

The peripheral-battery-monitor project includes Claude usage tracking, but it:
1. Is Linux-specific (uses Linux-only battery/device paths)
2. Is bundled with battery monitoring (unnecessary on many Windows setups)
3. Uses PyQt6 which can be heavy for a simple widget

A dedicated Windows widget provides focused functionality with a lighter footprint.

---

## Requirements

### Data Source

Parse Claude CLI session files from the local projects directory:
- **Windows path**: `%USERPROFILE%\.claude\projects\`
- **File format**: `.jsonl` (JSON Lines)
- **Parsing**: Walk all `.jsonl` files, filter by modification time within session window

### Metrics to Track

| Metric | Source | Display |
|--------|--------|---------|
| Input tokens | `usage.input_tokens` | Combined with output |
| Output tokens | `usage.output_tokens` | Combined with input |
| Cache read tokens | `usage.cache_read_input_tokens` | Informational |
| Cache creation tokens | `usage.cache_creation_input_tokens` | Informational |
| Session tokens | Sum of input + output | Primary display |
| API calls | Count of usage objects | Secondary display |

### Session Window Management

- Configurable window duration: 1, 2, 4, 6, 8, 12 hours
- Configurable reset hour (aligned to Claude's billing window)
- Display format: `HH:MM-HH:MM (Xh Ym until reset)`
- Only process files modified within the current window

### Display

**System Tray Icon**:
- Show usage percentage in icon or tooltip
- Color-coded status: Green (<50%), Yellow (50-80%), Red (>80%)
- Left-click: Show/hide detail popup
- Right-click: Context menu

**Detail Popup**:
```
┌─────────────────────────────────────────┐
│  Claude Code Usage                   ✕  │
├─────────────────────────────────────────┤
│  Window: 02:00 - 06:00  (2h 45m left)   │
│                                         │
│  ████████░░░░░░░░░░░░  42%              │
│                                         │
│  Tokens: 210.5k / 500.0k                │
│  API Calls: 37                          │
│                                         │
│  Cache Read: 45.2k                      │
│  Cache Created: 12.1k                   │
└─────────────────────────────────────────┘
```

### Configuration

**Settings** (stored in `%APPDATA%\claude-usage-widget\config.json`):
```json
{
  "session_budget": 500000,
  "window_hours": 4,
  "reset_hour": 2,
  "token_offset": 0,
  "update_interval_seconds": 30,
  "start_minimized": true,
  "show_on_startup": true
}
```

**Context Menu Options**:
- Budget: Quick presets (250k, 500k, 1M, Custom...)
- Window Duration: 1h, 2h, 4h, 6h, 8h, 12h
- Reset Hour: 0-23 selector
- Calibrate... (opens calibration dialog)
- Settings...
- Exit

### Calibration

**Snap-to-percentage calibration**:
1. User runs `/usage` in Claude CLI to see actual percentage
2. Opens calibration dialog, enters the percentage
3. Widget adjusts budget or offset to match

**Two modes**:
1. **Adjust Budget**: `new_budget = current_tokens / (percentage / 100)`
2. **Adjust Offset**: `offset = (budget * percentage / 100) - current_tokens`

---

## Technical Decisions

### UI Framework Options

| Option | Pros | Cons |
|--------|------|------|
| **PyQt6** | Feature-rich, familiar from Linux version | Heavy dependency (~50MB), complex install |
| **pystray + tkinter** | Lightweight, native tray support | Limited styling, basic widgets |
| **wxPython** | Native look, good tray support | Medium weight, less modern |
| **CustomTkinter** | Modern look, lightweight | No native tray (needs pystray) |

**Recommendation**: `pystray` + `CustomTkinter`
- pystray for system tray (lightweight, Windows-native)
- CustomTkinter for popup window (modern look without Qt overhead)
- Total dependencies: ~5MB vs ~50MB for PyQt6

### Installation

**Options**:
1. Python script with pip dependencies
2. Standalone .exe via PyInstaller
3. Windows installer (MSI/NSIS)

**Initial approach**: Python script with `requirements.txt`, add PyInstaller build later.

### Startup Integration

- Optional Windows startup entry via registry or startup folder
- User-controlled via Settings menu

---

## Acceptance Criteria

- [x] Parses `.jsonl` files from `%USERPROFILE%\.claude\projects\`
- [x] Correctly calculates session window boundaries based on reset hour
- [x] Displays system tray icon with color-coded usage status
- [x] Shows detail popup on left-click with all metrics
- [x] Context menu provides budget, window, and reset hour configuration
- [x] Calibration dialog allows snap-to-percentage adjustment
- [x] Settings persist between sessions
- [x] Updates automatically every 30 seconds (configurable)
- [x] Handles missing Claude installation gracefully (shows "Not installed" state)
- [x] Handles empty/missing projects directory (shows "No activity" state)
- [ ] Works on Windows 10 and Windows 11 (not yet tested on W10)

---

## Out of Scope (v1)

- Web interface usage tracking (only CLI)
- Multi-device aggregation
- Automatic sync with Claude billing API
- Cost calculation (rates change, user can calculate from tokens)
- Historical usage graphs
- Notifications/alerts at usage thresholds

---

## File Structure

```
claude-usage-widget-windows/
├── README.md
├── requirements.txt
├── requirements-dev.txt
├── install.bat
├── uninstall.bat
├── specs/
│   └── 001-claude-usage-widget.md
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   └── test_claude_stats.py
└── src/
    ├── __init__.py
    ├── main.py              # Entry point
    ├── claude_stats.py      # Data parsing logic
    ├── config.py            # Settings management
    ├── tray.py              # System tray integration (icons generated dynamically)
    ├── popup.py             # Detail popup window
    └── calibration.py       # Calibration dialog
```

---

## References

- [peripheral-battery-monitor Claude implementation](../peripheral-battery-monitor/battery_monitor_gui.py) (lines 97-188, 281-460)
- Claude CLI projects directory structure
- pystray documentation: https://pystray.readthedocs.io/
- CustomTkinter documentation: https://customtkinter.tomschimansky.com/

---

## Status

**Status**: COMPLETE

All core functionality implemented and tested. Ready for user testing.
3. Build system tray integration
4. Add popup window
5. Add calibration dialog
6. Add settings persistence
7. Create tests
8. Create installer scripts
