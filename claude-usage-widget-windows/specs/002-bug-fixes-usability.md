# Spec 002: Bug Fixes and Usability Improvements

## Overview

Address usability issues and bugs identified during user testing.

## Bug Reports

### Bug 1: Calibration Dialog Cannot Be Closed

**Symptom**: Calibration popup can't be closed or dismissed
**Expected**: Cancel button and X close button should work

### Bug 2: Unclear Calibration Feedback

**Symptom**: Unclear how to apply settings from calibration (or if they are being applied)
**Expected**: Clear visual feedback when settings are applied

### Bug 3: Tuning Options in Wrong Location

**Symptom**: Menu of tuning options attached to tray icon instead of floating window
**Expected**: Settings menu should be accessible from the floating widget directly

### Bug 4: Insufficient Granularity in Settings

**Symptom**: Tuning options for budget/window duration/reset hours not granular enough
**Expected**: More options for all configurable values

---

## Requirements

### Calibration Dialog Fixes

- [x] Cancel button must close the dialog
- [x] X (close) button must close the dialog
- [x] Show clear feedback when calibration is applied (visual confirmation)
- [x] Dialog must be dismissable via Escape key

### Floating Widget Menu

- [x] Add right-click context menu to floating widget
- [x] Include all tuning options: Budget, Window Duration, Reset Hour, Calibrate
- [x] Keep tray icon menu for redundancy but primary access is widget menu

### Enhanced Settings Granularity

**Budget options**:
- [x] More presets: 100k, 200k, 250k, 300k, 400k, 500k, 750k, 1M, 1.5M, 2M
- [x] Custom value input option

**Window Duration options**:
- [x] More presets: 0.5h, 1h, 1.5h, 2h, 3h, 4h, 5h, 6h, 8h, 10h, 12h

**Reset Hour options**:
- [x] All hours 0-23 (currently every 2 hours only)

---

## Acceptance Criteria

- [x] Calibration dialog can be closed via Cancel button
- [x] Calibration dialog can be closed via X button
- [x] Calibration dialog can be closed via Escape key
- [x] Calibration shows confirmation when applied
- [x] Floating widget has right-click context menu
- [x] Widget menu includes Budget, Window, Reset Hour, Calibrate, Exit
- [x] Budget has 10+ preset options (100k-2M)
- [x] Window duration has 11 options (0.5h to 12h)
- [x] Reset hour has all 24 hours available

---

## Status

**Status**: COMPLETE
