# Spec 009: Claude Usage Calibration / Snap-to-Percentage

**Status: COMPLETE**

## Description
Allow users to calibrate the Claude usage display by entering a known percentage from Claude's actual billing. The system adjusts internal values to match, with user control over which parameters stay fixed vs. which get recalculated.

This addresses drift between local tracking and Claude's actual billing windows, which can vary due to service load.

## Problem Statement
The monitor tracks token usage locally by reading session files, but Claude's billing windows may not align perfectly with configured reset times. When drift accumulates, the displayed percentage differs from what Claude reports.

Currently, users must manually guess at budget or window adjustments to realign. A "snap to known value" feature would calculate the correct adjustment automatically.

## Requirements

### Core Calibration Flow
1. User opens calibration dialog (via context menu or keyboard shortcut)
2. User enters the known percentage from Claude's billing (e.g., "25%")
3. User selects which parameter to adjust:
   - **Token budget** (most common - adjust budget so current tokens = target %)
   - **Window duration** (recalculate window size to match %)
   - **Current token count** (override the counted tokens - less common)
4. System calculates and applies the adjustment
5. Display updates to show the calibrated percentage

### Parameter Pinning
When calibrating, some values are "pinned" (held constant):
- If pinning **window times + duration**: Adjust token budget
- If pinning **budget + window times**: Adjust window duration
- If pinning **budget + duration**: Adjust token count (or show as override)

Default: Pin window times and duration, adjust budget.

### Budget Granularity
Current budget options are coarse (10k, 25k, 50k, 100k, 250k, 500k, 1M, Unlimited).

Add:
- Fine-grained input via dialog (any integer value)
- Quick adjustments: +10k, -10k buttons or similar
- Keep preset menu for common values

### UI Approach
Use a popup dialog since this requires:
- Numeric input for target percentage
- Radio buttons or dropdown for "which parameter to adjust"
- Display of calculated result before applying
- Cancel/Apply buttons

## Acceptance Criteria
- [x] Calibration dialog accessible from Claude context menu
- [x] User can enter target percentage (0-100, or >100 for over-budget)
- [x] User can choose which parameter to adjust (budget or token count)
- [x] System calculates correct adjustment to match target percentage
- [x] Calculated values shown before applying (preview)
- [x] Budget can be set to arbitrary integer value (not just presets)
- [x] Existing preset budget menu still works
- [x] Tests pass

## Implementation Notes

### Calculation Logic
Given: `current_tokens`, `current_budget`, `target_percentage`

**Adjust budget** (default):
```python
new_budget = current_tokens / (target_percentage / 100)
```

**Adjust duration** (requires recalculating window boundaries):
```python
# More complex - need to find a window duration that makes current tokens = target %
# This may require iterating or accepting approximate match
```

**Override tokens** (manual correction):
```python
new_tokens = current_budget * (target_percentage / 100)
# Store as offset to apply to calculated count
```

### Dialog Components
- QDialog with:
  - QSpinBox or QLineEdit for percentage (0-200 range?)
  - QComboBox for adjustment mode (Budget / Duration / Token Override)
  - QLabel showing current values and calculated new values
  - Preview calculation updates as user types
  - Apply / Cancel buttons

### Menu Integration
Add to Claude context menu:
```
Claude Code ▸
  ├── Show Session Stats
  ├── Calibrate Usage...    ← NEW (opens dialog)
  ├── ─────────────────
  ├── Session Budget ▸
  │   ├── 10k tokens
  │   ├── ...
  │   └── Custom...         ← NEW (opens budget input)
  ├── Window Duration ▸
  └── Reset Hour ▸
```
