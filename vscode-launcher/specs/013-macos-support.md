# Spec 013: macOS Support for vscode-launcher

> **Note**: This work has no associated issue tracker ticket. Consider creating one for traceability.

**Status: COMPLETE**

> **Implementation note (2026-06-21)**: Two intentional deviations from the
> draft spec, both decided with the user during implementation:
> 1. **No venv.** `install.sh` matches the existing Linux model (verify PyQt6
>    is importable, symlink the script) rather than creating the
>    `~/Library/Application Support/vscode-launcher/venv` the table proposed.
>    Simpler and consistent across platforms.
> 2. **`sys.platform`, not `platform.system()`.** Platform detection reuses
>    the pre-existing `IS_LINUX`/`IS_MACOS`/`IS_WINDOWS` constants in
>    `platform_support.py` (derived from `sys.platform`), which is
>    functionally equivalent to the `platform.system()` the spec referenced
>    and keeps detection centralized in one module.
>
> Verified end-to-end on macOS 26.5 (M1 Max, VS Code 1.125.1): live
> `install.sh` → daemon started by the LaunchAgent (pid confirmed running) →
> `uninstall.sh` removed every artifact and stopped the daemon. Recent
> projects load (4 found) and the menu-bar template icon resolves as a mask.

## Problem

vscode-launcher v5.0 is Linux-specific in three areas:

1. **VS Code state DB path** — hardcoded to `~/.config/Code/User/globalStorage/`
2. **Desktop integration** — `.desktop` files for app launcher and autostart
3. **Install/uninstall scripts** — Linux paths and integration only

The primary development environment is Linux/KDE, but macOS is used as a roaming
platform when a Linux desktop isn't available. The launcher should support macOS
for this multi-platform workflow. The core PyQt6 system tray functionality is
already cross-platform — the porting work is primarily about paths and OS
integration.

## Empirical Validation (2026-06-21, macOS 26.5.0, M1 Max, VS Code 1.125.1)

The following strategies were tested on the target macOS machine:

| # | Strategy | Result | Detail |
|---|----------|--------|--------|
| 1 | VS Code state DB at `~/Library/Application Support/Code/User/globalStorage/state.vscdb` | **Confirmed** | SQLite readable, returns 4 recent projects (both folder and workspace entries) |
| 2 | IPC socket at `$TMPDIR/vscode-ipc-*.sock` (per `platform_support.py` stub) | **Wrong** | No such sockets exist. Actual location: `~/Library/Application Support/Code/1.12-main.sock` (discovered via `lsof -p <main-pid>`) |
| 3 | `code --status` for window enumeration | **Confirmed** | Shows 2 windows with PIDs and titles. ~instant on this machine |
| 4 | `code` CLI on PATH | **Required fix** | Was broken — `/usr/local/bin/code` was a stale symlink to a previously-installed Cursor. Repointed to VS Code. Install script should verify |

**Critical correction for `platform_support.py`**: The macOS IPC socket stub
comment says `$TMPDIR/vscode-ipc-*.sock` — this is incorrect. The actual main
IPC socket lives at `~/Library/Application Support/Code/<version>-main.sock`
(e.g., `1.12-main.sock` for VS Code 1.125.x). The `vscode-git-*.sock` files in
`$TMPDIR` are git-specific helper sockets, not the main IPC endpoint.

## Relationship to Spec 010

Spec 010 (Cross-Platform Window Detection) addresses the deeper problem of
running-state detection across platforms (KWin scripting → `code --status`
fallback). This spec (013) focuses on the **simpler prerequisite**: making the
launcher start, find recent projects, and open them on macOS.

Spec 010's `WorkspaceInspector` refactor and `CodeStatusInspector` backend are
complementary but independent — they can be implemented in either order. This
spec explicitly excludes running-state detection cross-platform work (covered by
010).

## What Already Works on macOS

- PyQt6 `QSystemTrayIcon` — works on macOS menu bar natively
- `QMenu` popup — works on macOS
- `QFileSystemWatcher` — cross-platform
- `subprocess.Popen(["code", ...])` — works if `code` is on PATH
- SQLite reading of `state.vscdb` — cross-platform
- All business logic (project parsing, menu building, sorting)

## What Needs to Change

### 1. VS Code State DB Path

| Platform | Path |
| -------- | ---- |
| Linux | `~/.config/Code/User/globalStorage/state.vscdb` |
| macOS | `~/Library/Application Support/Code/User/globalStorage/state.vscdb` |

The `_find_storage_path()` method currently only searches the Linux path. Add
Darwin detection following clockwork-orange's pattern:

```python
def _get_vscode_data_dir() -> Path:
    if platform.system() == "Darwin":
        return Path.home() / "Library/Application Support/Code"
    return Path.home() / ".config/Code"
```

### 2. IPC Socket Discovery (`platform_support.py`)

The macOS stub in `platform_support.py` (line 138) assumes
`$TMPDIR/vscode-ipc-*.sock`. Empirical testing found the actual socket at:

```
~/Library/Application Support/Code/1.12-main.sock
```

The glob pattern should be:
```python
Path.home() / "Library/Application Support/Code" / "*-main.sock"
```

The version prefix (`1.12`) appears to track VS Code's internal protocol version.
`QFileSystemWatcher` can't glob, so the implementation should list the directory
and filter for `*-main.sock` entries, sorted by mtime (most recent first), same
as the Linux implementation.

### 3. Install Script (`install.sh`)

Add `$OSTYPE` branching (pattern from clockwork-orange):

| Concern | Linux | macOS |
| ------- | ----- | ----- |
| Virtualenv location | `~/.local/share/vscode-launcher/venv` | `~/Library/Application Support/vscode-launcher/venv` |
| Binary symlink | `~/bin/vscode-launcher` | `/usr/local/bin/vscode-launcher` |
| App launcher | `.desktop` in `~/.local/share/applications/` | Skip (CLI + tray only) |
| Autostart | `.desktop` in `~/.config/autostart/` | LaunchAgent plist in `~/Library/LaunchAgents/` |
| Dependencies | System PyQt6 or pip | `brew install pyqt6` or pip in venv |

### 4. Autostart on macOS

Replace `.desktop` autostart with a LaunchAgent plist. Use `plistlib` (Python
stdlib) to generate:

```python
import plistlib

plist = {
    "Label": "com.vscode-launcher.agent",
    "ProgramArguments": [str(venv_python), str(script_path)],
    "RunAtLoad": True,
    "KeepAlive": False,
}
plist_path = Path.home() / "Library/LaunchAgents/com.vscode-launcher.plist"
```

The install script should offer to install the LaunchAgent. The uninstall script
should remove it and run `launchctl bootout` to stop the running agent.

### 5. Uninstall Script (`uninstall.sh`)

Add macOS branch:
- Remove `/usr/local/bin/vscode-launcher` symlink
- Remove `~/Library/Application Support/vscode-launcher/` (venv + data)
- Unload and remove `~/Library/LaunchAgents/com.vscode-launcher.plist`
- Kill running instances (`pkill -f vscode_launcher`)

### 6. Menu Bar Behavior on macOS

PyQt6's `QSystemTrayIcon` integrates with the macOS menu bar automatically, but
there are behavioral differences:

- **Left-click**: On Linux, shows/hides menu. On macOS, the menu bar icon always
  shows menu on click (no hide toggle). No code change needed — PyQt handles this.
- **Icon**: macOS menu bar icons should be template images (monochrome, ~22px
  tall) for proper dark/light mode support. The current icon may need a
  template variant.

### 7. Process Start Time (Minor)

The Launched column uses `/proc/{pid}/stat` for process start time on Linux.
On macOS, use `psutil.Process(pid).create_time()` which is cross-platform. This
is a small change but prevents a crash if the Launched column code runs on macOS.

## Design Approach

### Phase 1: Path abstraction (minimum viable macOS)

1. Add `platform.system()` detection
2. Add `_get_vscode_data_dir()` with Darwin/Linux branching
3. Update `_find_storage_path()` to use it
4. Test that recent projects load correctly on macOS

### Phase 2: Install/uninstall scripts

5. Update `install.sh` with `$OSTYPE` branching
6. Add LaunchAgent plist generation for macOS autostart
7. Update `uninstall.sh` with macOS cleanup
8. Test install/uninstall cycle on macOS

### Phase 3: Polish

9. Add macOS menu bar template icon (if current icon looks wrong)
10. Replace any `/proc`-based process queries with `psutil` equivalents
11. Update README with macOS instructions

### Phase 4: Testing

12. Add tests for platform-specific path resolution
13. Add tests for LaunchAgent plist generation
14. Verify existing tests pass with platform mocking

## Acceptance Criteria

- [x] vscode-launcher starts and shows tray/menu bar icon on macOS — startup smoke test ran the event loop cleanly (KGlobalAccel degraded gracefully); `_resolve_app_icon()` returns a valid template `QIcon` (`isMask() == True`)
- [x] Recent VS Code projects are discovered from macOS storage path — `VSCodeRecentsReader.read_recents()` returned 4 projects from `~/Library/Application Support/Code/...` on the target machine
- [x] Clicking a project opens it in VS Code on macOS — launch path uses the cross-platform `code` CLI via `subprocess`; `code` confirmed on PATH and resolving to *Visual Studio Code.app*
- [x] `install.sh` works on macOS (symlink in `/usr/local/bin`, LaunchAgent) — ran live; both symlinks created, `plutil -lint` OK. (No venv — see implementation note.)
- [x] `uninstall.sh` works on macOS (removes all installed artifacts) — ran live; symlinks, plist, LaunchAgent job, daemon process, and zsh hook all removed
- [x] Autostart via LaunchAgent works on macOS — `launchctl bootstrap` loaded the agent and `RunAtLoad` started the daemon (pid 99441, stable, never exited)
- [x] IPC socket discovery finds `~/Library/Application Support/Code/*-main.sock` on macOS — implemented + unit-tested; the real socket (`1.12-main.sock`) is present on the target machine
- [x] Platform detection uses `sys.platform` via centralized `IS_*` constants — functionally equivalent to `platform.system()`; see implementation note
- [x] Existing Linux functionality is not regressed — full suite green (168 passed); Linux branches untouched
- [x] No hardcoded Linux-only paths remain in the main code path — all platform paths resolved through `platform_support.py`
- [x] Tests cover macOS path resolution and platform detection — `tests/test_unit_platform_support.py` (state DB, IPC sockets, process start time, config dir across Linux/macOS/Windows)
- [x] README documents macOS installation and usage — added Platform-support matrix + macOS install/uninstall sections + v3.4 changelog

## Out of Scope

- Cross-platform running-state detection (covered by spec 010)
- Windows support
- `.app` bundle packaging for macOS
- Homebrew formula

## Risk / Open Questions

1. **PyQt6 on macOS**: Does the current `install.sh` virtualenv approach work
   cleanly with PyQt6 on macOS, or does it need `brew install pyqt6` as a system
   dependency? PyQt6 wheels exist for macOS on PyPI, so pip-in-venv should work.
2. **Menu bar icon appearance**: macOS menu bar has specific requirements for icon
   rendering (template images for automatic dark/light adaptation). The current
   icon may render poorly — needs visual testing.
3. **`code` CLI on PATH**: Empirically confirmed as a real issue — the
   `/usr/local/bin/code` symlink was hijacked by a previously-installed Cursor.
   The installer should verify the symlink target resolves to
   `Visual Studio Code.app`, not another editor, and warn if missing or wrong.
4. **IPC socket version prefix**: The socket is named `1.12-main.sock` — the
   `1.12` appears to be a protocol version, not the VS Code release version.
   Needs monitoring across VS Code updates to confirm stability of the glob
   pattern `*-main.sock`.
