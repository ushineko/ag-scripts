# Spec 003: Restore pane programs after a herdr server restart

## Status: INCOMPLETE

> **Note**: This work has no associated issue tracker ticket. Consider creating
> one (a GitHub issue on this repository, per `.claude/CLAUDE.md`) for
> traceability.

## Context

On njv-mbp-m1 (macOS) the herdr server was restarted at 2026-11-21 12:38:09
local (`server shutdown initiated reason=SIGTERM`, back at 12:38:34). It was not
a reboot: uptime was 1 day 16 h. herdr rebuilt the layout as bare shells and no
yazi or lazygit panel came back.

The restore machinery itself works; nothing invoked it. Verified the same day:

- The snapshot still held all 6 programs, preserved by the >= 50 % mass-drop
  guard in `_merge_preserving`.
- `restore --dry-run` matched all 6 to their live panes.
- `herdr pane run` started lazygit and yazi in their panes.
- The `prefix+ctrl+r` keybind environment (`$SHELL -lc` with the server's PATH,
  per herdr's `spawn_custom_command`) resolves the 0.9.5 custom `herdr` and
  restores correctly.

Three gaps cause the miss:

**1. Nothing triggers restore after a server restart.** On macOS, `install.sh`
creates no launchd agent. The only agent is the dotfiles-managed
`com.nverenin.herdr-resurrect.plist`, which runs `save` every 5 min. There is no
autorestore at all. On Linux, `herdr-resurrect-autorestore.timer` fires once at
login (`OnStartupSec=30s`), and spec 002 explicitly left "re-restore after a
mid-day herdr server restart" out of scope. On both platforms a server restart
without a reboot depends on the user remembering `prefix+ctrl+r`.

**2. The boot grace window is disabled on macOS.** `_uptime_sec()` calls
`time.clock_gettime(time.CLOCK_BOOTTIME)`. The constant does not exist on macOS
(`hasattr(time, "CLOCK_BOOTTIME")` is `False`), the Windows fallback raises, and
the function returns `+inf`. `BOOT_GRACE_SEC` therefore never applies, and only
the mass-drop ratio protects the snapshot. If the user relaunches more than half
of the programs by hand after a restart, the next save drops the rest
permanently.

**3. The grace window is keyed on the wrong event even where it works.**
On Linux, uptime measures time since the machine booted, not since the herdr
server started. A server restart days after boot gets no grace.

## Requirements

1. **Restart detection.** herdr-resurrect detects that a session's herdr server
   has started since the last time it looked. The signal is the session's API
   socket (`socket_path` from `herdr session list --json`): herdr creates it at
   server start, so its birth time (where available, else mtime) identifies a
   server instance. Each session is tracked separately.
2. **Persisted state.** The last-seen server identity per session is stored in
   `~/.config/herdr-resurrect/state.json`, separate from the snapshot so the
   snapshot format is unchanged. Writes are atomic (tmp file + `os.replace`),
   matching `write_snapshot`.
3. **Restore on restart, inside `save`.** When `save` sees a running session
   whose server identity differs from the recorded one, it runs
   `restore(sessions={that session})` *before* capturing, then records the new
   identity. The save that follows then captures the restored programs. No new
   agent or timer is needed: the existing 5-min save (launchd on macOS, systemd
   timer on Linux) carries it.
4. **First observation does not restore.** If no identity was recorded for a
   session yet (first run after deploy, or a newly created session), `save`
   records it and does not restore. This avoids an unexpected relaunch when the
   feature is first rolled out.
5. **Restart restore only fills panes that look restarted.** The restart-time
   restore runs only when the restart is corroborated: at least
   `RESTART_DROP_RATIO` of that session's snapshot entries match idle panes. If
   the socket changed but most programs are still running (for example after a
   herdr live handoff that kept the pane processes), the restore is skipped
   and the identity is recorded anyway.
6. **Grace window keyed on server start.** The preservation grace in
   `_merge_preserving` uses time since the session's server started (from the
   same socket timestamp), not system uptime. If the server start time cannot
   be determined, it falls back to system uptime, and the uptime lookup works
   on macOS (`sysctl kern.boottime` via `ctypes` or `subprocess`; stdlib only).
7. **No concurrent restores.** `restore()` holds an exclusive lock
   (`fcntl.flock` on a file in `CONFIG_DIR`; `msvcrt.locking` on Windows) for
   its duration. A second caller (the Linux autorestore unit, the keybind, or a
   restart-triggered save) waits briefly, then skips if the lock is still
   held, so two callers never type the same command into one idle pane.
8. **Logging.** A restart-triggered restore prints one line per session and per
   restored program to stdout, in the existing `[autorestore]`-style format with
   a `[restart]` prefix, so it shows in
   `~/Library/Logs/herdr-resurrect-save.log` and the systemd journal.
9. **Existing behaviour unchanged otherwise.** Steady-state saves still drop a
   pane the user deliberately closed. Spec 002's unscanned-session handling is
   unchanged. `autorestore` keeps working on Linux.

## Acceptance Criteria

- [x] A function returns a per-session server identity derived from the
      session's socket timestamp, and returns None for a session whose socket
      is missing
- [x] `state.json` is read and written atomically; a missing or corrupt file
      reads as empty state
- [x] `save` restores a session whose recorded server identity differs from the
      current one, then captures the restored programs in the same run
- [x] `save` does not restore a session seen for the first time; it only records
      the identity
- [x] `save` does not restore when the identity changed but fewer than
      `RESTART_DROP_RATIO` of that session's snapshot entries are on idle panes,
      and still records the new identity
- [x] `_merge_preserving`'s grace uses time since the server started, and a test
      shows a restart long after boot still gets the grace window
- [x] `_uptime_sec()` returns a finite value on macOS
- [x] `restore()` takes an exclusive lock; a concurrent second call does not
      run `pane run`
- [x] A restart-triggered restore logs the session and each restored program
- [ ] Manually verified on njv-mbp-m1: after `herdr server stop` and a restart,
      the yazi and lazygit panels come back within one save interval with no
      keypress
- [x] README documents restart-triggered restore and `state.json`
- [x] Full test suite passes

## Test Strategy

- **Unit (pytest, existing `tests/test_logic.py` style)**: restart detection,
  state round-trip, the first-observation and corroboration rules, and the grace
  calculation are pure functions of (recorded identity, current identity,
  snapshot, live panes, clock). Test them with plain inputs and no mocks.
- **Mock boundary**: `herdr_api` only, as the existing `TestRestoreSessionScope`
  and `TestAutorestoreLoop` tests already do. Socket timestamps come from a real
  temp file created in the test, not a mocked `os.stat`.
- **Lock**: two real `restore()` calls against the same temp `CONFIG_DIR`, with
  the first holding the lock.
- **Manual**: the njv-mbp-m1 restart check in the acceptance criteria. The
  herdr server is not started in tests.

## Risks & Assumptions

- **Rollback**: revert the commit. The snapshot format is unchanged, and
  `state.json` is a new file that an older build ignores.
- **Up to one save interval of latency.** A restart is noticed on the next
  save, up to 5 min later. `prefix+ctrl+r` remains the instant path.
- **Socket timestamp as the identity is an assumption.** It held on
  2026-11-21 (`herdr.sock` birth time 12:38:34 = server start in
  `herdr-server.log`). If a future herdr reuses the socket inode across a
  restart, detection silently stops working and behaviour falls back to
  today's (manual restore). If herdr adds a server PID or start time to
  `herdr status server --json`, prefer that.
- **A program quit just before a restart may be relaunched.** The snapshot can
  be up to one interval old, so a program the user quit in the last 5 min before
  the restart is still listed. This matches what `prefix+ctrl+r` does today.
- **Overlap with Linux autorestore.** After a reboot both the autorestore unit
  and the first save may want to restore. The lock (requirement 7) and the
  idle-pane check prevent duplicate launches; whichever runs first wins.
- No integration boundary in the Ralph sense (no DB, queue, or external API).

## Alternatives Considered

- **A fast-polling autorestore agent on macOS**: rejected. Without a restart
  signal it would relaunch programs the user quit on purpose, which is the same
  reason spec 002 rejected polling restore forever.
- **A launchd `WatchPaths` agent on the socket**: event-driven and lower
  latency, but macOS-only, it fires on any change to the directory, and it adds a
  second agent to deploy. The restart check inside `save` works on all three
  platforms with what is already installed.
- **A herdr startup hook**: herdr 0.9.5 has none for server start.

## Out of Scope

- Making `install.sh` create the macOS launchd save agent (today it lives in
  dotfiles as `hosts/njv-mbp-m1/Library/LaunchAgents/com.nverenin.herdr-resurrect.plist`).
- Capturing the `w4` claude-usage panels: `panel:usage` runs Python, which is
  outside the default whitelist. That is a config change (`cmdline_patterns` or
  `label_commands`), not a code change.
