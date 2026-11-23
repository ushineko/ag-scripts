## Validation Report: Restore pane programs after a herdr server restart
**Date**: 2026-11-21
**Spec**: `specs/003-restore-after-server-restart.md`
**Commit**: (this commit)
**Status**: PASSED

### Problem
On njv-mbp-m1 the herdr server restarted at 12:38 (SIGTERM, not a reboot) and
no yazi/lazygit panel came back. Nothing invokes restore after a server restart:
macOS has no autorestore, and Linux's runs only at login. `_uptime_sec()`
returned +inf on macOS (`time.CLOCK_BOOTTIME` is absent), so the boot grace was
disabled there.

### Change
- `restart.py` (new): server identity from the session socket's birth time,
  `state.json` persistence, `classify`, `restart_verdict`
  (corroborated / not / layout pending), and a cross-process `restore_lock`
  (`fcntl.flock`; `msvcrt.locking` on Windows).
- `resurrect.save()` restores any session whose server restarted since the last
  save, before capturing. A first-seen session is only recorded. A
  layout-pending session keeps its old record so the next save tries again.
  Logs with a `[restart]` prefix.
- `_merge_preserving` grace is per session, measured from server start
  (`server_age_sec`), falling back to system uptime.
- `_uptime_sec()` reads `sysctl kern.boottime` on macOS.
- `restore()` runs under the lock; `RestoreResult.lock_busy` reports a skip.
- `herdr_api.Session` carries `socket_path`.

### Phase 3: Tests
- Suite: `python3 -m unittest discover -s tests`, run under `/usr/bin/python3`
  (3.9.6) and Homebrew `python3` (3.14).
- Results: 77 passing, 0 failing (54 existing + 23 new in `tests/test_restart.py`).
- Mock boundary: only `herdr_api`, via a stateful `FakeHerdr` whose `pane_run`
  makes the program appear as the pane foreground. State, snapshot, lock and
  socket files are real temp files.
- Live check on njv-mbp-m1 against the running herdr 0.9.5 server: wrote a
  stale identity to `state.json`, ran `herdr-resurrect save`. It logged
  `server restarted; restoring`, relaunched the 4 idle panes (2 yazi, 2
  lazygit), and saved all 6 programs. `state.json` then held the live socket's
  birth time. A second `save` did not restore anything.
- Real restart on njv-mbp-m1 (2026-11-22): the user ran `herdr server stop`
  and relaunched herdr, and the server came back at 15:54:22. The next periodic
  save logged `[restart] session 'default': server restarted; restoring` and
  relaunched all 5 saved programs (3 yazi, 2 lazygit). No keypress was needed.
  `state.json` then recorded the new socket (1795391662.84), and
  `restore --dry-run` showed 5 already running. Restore came up to one save
  interval after the restart, as the spec allows.
- Status: ✓ PASSED

### Phase 3: Test contract quality
The tests check behaviour: programs relaunched into idle panes, which entries
are captured, what `state.json` holds, and whether `pane run` was called. They
don't depend on how the code is structured internally. `TestUptime` is macOS-only
(skipped elsewhere).

### Phase 4: Code Quality
- Dead code: none
- Duplication: capture loop extracted from `save()` into `_capture()`; restore
  pass extracted into `_restore_pass()` so the dry-run and locked paths share it
- Encapsulation: restart detection and locking live in `restart.py`, separate
  from save/restore orchestration
- Linter: ruff not installed; not run
- Status: ✓ PASSED

### Phase 5: Security Review
- Dependencies: stdlib only, no new dependencies. pip-audit not installed and
  not applicable (no third-party packages).
- Secrets: none
- Input handling: `state.json` parse errors and non-numeric values are dropped
  (empty state). `sysctl` is run as a fixed argv list with an absolute path,
  without a shell, and with a timeout.
- Lock and state files are in the user's own `~/.config/herdr-resurrect`.
- Status: ✓ PASSED

### Phase 5.5: Release Safety
- Change type: code + new state file
- Rollback: revert the commit. The snapshot format is unchanged; an older build
  ignores `state.json` and `restore.lock`. To disable restart restore without a
  revert, delete `state.json` before each save (first-seen never restores).
- Status: ✓ PASSED

### Notes
- Windows: if herdr's `socket_path` there is not a stat-able file, identity is
  None and restart restore does not fire. Behaviour then matches the previous
  release (the pwsh-profile trigger still covers server start).

### Overall
- All gates passed: YES
- Spec 003: COMPLETE
