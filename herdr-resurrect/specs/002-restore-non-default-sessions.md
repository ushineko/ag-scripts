# Spec 002: Restore pane programs in sessions that start after login

## Status: COMPLETE

> **Note**: This work has no associated issue tracker ticket (ag-scripts is a
> personal repository and uses none).

## Context

herdr-resurrect restored pane programs reliably in the `default` session and
never in a named session such as `work`. Two independent defects compounded,
both confirmed against the njv-cachyos journal for the 2026-09-17 09:54:45 boot.

**1. The restore window closes before a named session exists.**
`restore()` reaches only sessions whose server is running: `_annotated_live_panes()`
skips `if not sess.running`. herdr spawns a named session's server lazily, when a
terminal attaches it. The `autorestore` subcommand polled a fixed 900 s window
(`OnStartupSec=30s` + `--window 900`), so it ran 09:55:31 - 10:10:34. The `work`
server did not exist until 15:29:27, five hours after the window had closed.

**2. The snapshot then loses the session's entries entirely.**
`_merge_preserving()` carries an absent pane forward only within
`BOOT_GRACE_SEC` (1800 s) or on a mass drop (>= 50 % of captured panes gone at
once). A session whose server is not running contributes no live panes, so all
of its entries read as "absent". Three `work` entries out of 24 is 12 %, below
the mass-drop ratio, so at 10:26:51 - just past the boot grace - the save went
`24 -> 21 programs` and the `work` entries were dropped for good. Journal:
09:56:46 through 10:21:50 saved 24 (including three `work platform-backend`),
10:26:51 onward saved 21, all `default`.

Defect 2 also disabled the manual escape hatch: after attaching `work` by hand,
`prefix+ctrl+r` had nothing left in the snapshot to restore.

The root confusion is treating "this session reported no panes" as evidence that
its panes were closed. A session that was never scanned yields no evidence at
all, and absence of evidence must not be read as evidence of closure.

## Requirements

1. A snapshot entry belonging to a session that could not be scanned this cycle
   (server not running, or its pane/workspace query failed) is carried forward
   unconditionally, independent of boot grace and of the mass-drop ratio.
2. Unscanned sessions must not distort the mass-drop signal for the sessions
   that *were* scanned: they are excluded from both sides of the ratio.
3. A session that *was* scanned keeps today's steady-state behaviour - a
   deliberately closed pane is still dropped on the next save.
4. `restore()` accepts an optional session filter so a caller can restore one
   session without touching the others.
5. `autorestore` restores each target session once, the first time it is seen
   running, rather than restoring everything inside one fixed clock window.
   Target sessions are those named in the snapshot, plus - only when
   `label_commands` is configured, since those apply to any pane regardless of
   the snapshot - the sessions currently running.
6. Each target gets repeated passes over a short settle window after it first
   appears, so panes that materialise progressively during herdr's own layout
   restore are still filled.
7. `autorestore` exits as soon as every target is done, and otherwise at the
   `--window` cap. The default cap covers a working day, so a session attached
   hours after login is still reached.
8. A session marked done is not restored again by the same `autorestore` run.
   This is what keeps `label_commands` (`monitor:btop`, `panel:yazi`) from
   relaunching a program the user deliberately quit.
9. The systemd unit reflects the new default window and is explicit that the
   service may live for hours.

## Acceptance Criteria

- [x] `_merge_preserving` preserves entries from an unscanned session past the
      boot grace with no mass drop present
- [x] `_merge_preserving` excludes unscanned sessions from the mass-drop ratio,
      so one unscanned session cannot trigger preservation for a scanned one
- [x] `_merge_preserving` still drops a single deliberately-closed pane in a
      scanned session in steady state (existing behaviour unchanged)
- [x] `_annotated_live_panes` reports which sessions it successfully scanned,
      and a session whose pane query raises is reported as unscanned
- [x] `restore(sessions={...})` restores only panes in the named sessions, for
      both snapshot-driven and label-driven restore
- [x] `autorestore` runs a restore pass for a session the first time it is seen
      running, including a session that first appears long after the run started
- [x] `autorestore` stops restoring a session once its settle window has passed
- [x] `autorestore` returns once every target session is done
- [x] `herdr-resurrect-autorestore.service` reflects the new window and is
      explicit that the service may live for hours
- [x] Full test suite passes

## Risks & Assumptions

- **Rollback**: revert the commit; the snapshot file format is unchanged, so an
  older build reads a newer snapshot without migration.
- **Longer-lived unit**: `autorestore` may now sleep for up to `--window`
  (12 h default) instead of 15 min. It is a `Type=oneshot` unit, for which
  systemd's start timeout is already infinity. Cost is one `herdr session list`
  per 30 s (~30 ms), i.e. under a minute of CPU across a full day.
- **A target never attached**: if a snapshot names a session the user does not
  open that day, the run polls to the cap and exits having restored nothing for
  it. Harmless, and bounded.
- **Re-restore after a mid-day herdr server restart** is out of scope: a session
  already marked done is not restored again. `prefix+ctrl+r` covers that, and it
  now works because the snapshot keeps the entries.
- No integration boundary in the Ralph sense (no DB, queue, or external API);
  the herdr CLI is exercised through the existing thin `herdr_api` wrapper.

## Alternatives Considered

- Polling restore forever instead of per-session one-shot: rejected because
  `label_commands` are snapshot-independent, so quitting `btop` in a
  `monitor:btop` pane would see it relaunched on the next pass.
- inotify on `~/.config/herdr/sessions/*/herdr.sock` for event-driven restore:
  rejected to keep the tool stdlib-only and testable headless, as `herdr_api`
  already is.
