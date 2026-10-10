## Validation Report: Hide herdr console window on Windows
**Date**: 2026-10-10
**Commit**: (this commit)
**Status**: PASSED

### Problem
The `herdr-resurrect-save` scheduled task runs `cli.py save` under `pythonw.exe`
every 5 minutes. `pythonw` has no console, so each `herdr.exe` child (a console
program) got a new visible console window that flashed and took focus from
the foreground app. `herdr-resurrect-autorestore` (every 30s for an hour after
logon) did the same.

### Change
`herdr_api._run` passes `creationflags=subprocess.CREATE_NO_WINDOW` (via
`getattr(..., 0)` so Linux/macOS are unaffected). It is the only subprocess
call site in the sub-project.

### Phase 3: Tests
- Test suite: `python -m unittest discover -s tests` (pytest not installed in the available interpreter)
- Results: 54 passing, 0 failing
- Manual check: enumerated visible top-level console windows while a
  `pythonw` probe ran `herdr session list --json` three times.
  Without the flag: 2 visible console windows. With the flag: 0.
- Live check: `pythonw cli.py save` exits 0 with the change.
- Status: ✓ PASSED

### Phase 4: Code Quality
- Dead code: None found
- Duplication: None found
- Encapsulation: Single call site, no change needed
- Status: ✓ PASSED

### Phase 5: Security Review
- Dependencies: stdlib only, no new dependencies
- OWASP Top 10: No new input handling; argv list form, no shell
- Anti-patterns: None
- Status: ✓ PASSED

### Phase 5.5: Release Safety
- Change type: Code-only
- Rollback plan: Revert commit; or `Disable-ScheduledTask herdr-resurrect-save` / `herdr-resurrect-autorestore`
- Status: ✓ PASSED

### Overall
- All gates passed: YES
