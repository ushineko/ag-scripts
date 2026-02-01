# Spec 008: Display Claude Window Start/End Times

**Status: COMPLETE**

## Description
Display the current charging window's start and end times in 24-hour format (e.g., "02:00 - 06:00") in the Claude Code section. This helps users identify when their configured reset hour or window duration has become de-synced with Claude's actual billing windows, which can vary based on service load.

## Problem Statement
Currently, the Claude section shows only a countdown to reset (e.g., "2h 45m reset"). When window times drift due to Claude service load variations, users have no visual indicator of what window boundaries are currently active. They must mentally calculate from reset hour and window duration settings.

Showing the actual clock times makes de-sync immediately obvious: if the user expects "02:00 - 06:00" but sees "03:00 - 07:00", they know to adjust settings.

## Requirements
- Display window start time in 24H format (e.g., "02:00")
- Display window end time in 24H format (e.g., "06:00")
- Format as "HH:MM - HH:MM" or similar compact representation
- Position in the Claude section where it's visible but doesn't crowd existing stats
- Update when window boundaries change (at reset time)

## Acceptance Criteria
- [x] Window start time displayed in 24H format
- [x] Window end time displayed in 24H format
- [x] Times update correctly when crossing window boundaries
- [x] Display is compact and doesn't break layout on narrow windows
- [x] Times reflect configured reset_hour and window_hours settings
- [x] Tests pass

## Implementation Notes
The `get_session_window()` function already returns `(window_start, window_end)` as datetime objects. Extract `.strftime("%H:%M")` from each.

Suggested placement options:
1. **Replace countdown with times + countdown**: e.g., "02:00-06:00 (2h 45m)"
2. **New row below stats**: dedicated line for window times
3. **Tooltip on countdown**: hover to see full window times

Option 1 is most compact while preserving all info.
