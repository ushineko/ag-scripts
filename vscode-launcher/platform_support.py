"""Platform-specific paths and low-level APIs used by the launcher.

Centralizes every place the Linux-only assumptions of v2.0 would need to
change for a macOS or Windows port. Callers import named helpers from this
module instead of open-coding `sys.platform` branches or hardcoding `/proc`
paths.

Status matrix:

  | Helper                           | Linux | macOS | Windows |
  | -------------------------------- | ----- | ----- | ------- |
  | `vscode_state_db_path()`         |  ✓    |  stub |  stub   |
  | `vscode_ipc_socket_candidates()` |  ✓    |  stub |  stub   |
  | `process_start_time(pid)`        |  ✓    |  —    |  —      |
  | `launcher_config_dir()`          |  ✓    |  ✓    |  stub   |

"Stub" means the helper returns `None` / `[]` on the non-implemented
platform so callers degrade gracefully (e.g., "no VSCode socket found"
looks the same as "VSCode not running"). Porting is additive: drop the
implementation into the matching branch, delete the TODO.

KWin action plumbing (Close / Activate) is intentionally NOT abstracted
here — it's KDE-specific and already feature-gates on qdbus6/journalctl
availability inside `window_scanner.py`. A cross-platform port would
replace it wholesale with a different mechanism (IPC-based, native API).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

IS_LINUX = sys.platform.startswith("linux")
IS_MACOS = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"


# ---------------------------------------------------------------------------
# VSCode globalStorage / state.vscdb
# ---------------------------------------------------------------------------


def vscode_state_db_path() -> Path | None:
    """Return VSCode's `state.vscdb` path for this platform, or None when
    we don't know where to look. Callers should handle None by degrading
    (the recents list becomes empty)."""
    if IS_LINUX:
        return (
            Path.home()
            / ".config"
            / "Code"
            / "User"
            / "globalStorage"
            / "state.vscdb"
        )
    if IS_MACOS:
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Code"
            / "User"
            / "globalStorage"
            / "state.vscdb"
        )
    if IS_WINDOWS:
        appdata = os.environ.get("APPDATA")
        if appdata:
            return (
                Path(appdata)
                / "Code"
                / "User"
                / "globalStorage"
                / "state.vscdb"
            )
    return None


# ---------------------------------------------------------------------------
# VSCode IPC socket discovery
# ---------------------------------------------------------------------------


def vscode_ipc_socket_candidates() -> list[Path]:
    """Return candidate VSCode main-IPC sockets, most-recently-modified first.

    Linux: scans `$XDG_RUNTIME_DIR/vscode-*-main.sock` (fallback
    `/run/user/<uid>`). macOS / Windows are stubs — see module docstring
    for the porting plan. Empty list means "no socket found, VSCode not
    running here".
    """
    if IS_LINUX:
        runtime_dir = Path(
            os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
        )
        if not runtime_dir.is_dir():
            return []
        try:
            candidates = list(runtime_dir.glob("vscode-*-main.sock"))
        except OSError:
            return []
        try:
            return sorted(
                candidates, key=lambda p: p.stat().st_mtime, reverse=True
            )
        except OSError:
            return candidates

    if IS_MACOS:
        # TODO(macos): VSCode's main socket lives at
        # `$TMPDIR/vscode-ipc-*.sock`. Same AF_UNIX wire protocol; only
        # the discovery path changes.
        return []

    if IS_WINDOWS:
        # TODO(windows): VSCode uses named pipes at
        # `\\.\pipe\vscode-ipc-*.sock`. The socket layer in vscode_ipc.py
        # also needs a named-pipe backend (win32pipe / pywin32).
        return []

    return []


# ---------------------------------------------------------------------------
# Process start time
# ---------------------------------------------------------------------------


def process_start_time(pid: int) -> float | None:
    """Return the Unix timestamp when `pid` started, or None on any
    failure (bad pid, race, permission, not-implemented-for-platform).

    Used for the Launched column's per-window fallback — we prefer the
    in-memory timestamp the launcher records at spawn, but for VSCode
    windows that were already open, this /proc-based lookup gives us an
    accurate per-window value (since IPC reports real renderer PIDs).
    """
    if IS_LINUX:
        return _linux_process_start_time(pid)
    # macOS / Windows: no bundled dep. `psutil.Process(pid).create_time()`
    # is the cleanest path on both, but adding the dep is a separate
    # decision. Return None so the Launched column just shows em-dash
    # for pre-existing windows on those platforms until we add support.
    return None


def _linux_process_start_time(pid: int) -> float | None:
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            data = f.read()
    except OSError:
        return None
    try:
        # `comm` may contain spaces / parens — rsplit on the last ')' is
        # the safe cut. Fields after comm start with `state`.
        close_paren = data.rindex(b")")
    except ValueError:
        return None
    after_comm = data[close_paren + 2 :].split()
    try:
        # Field 22 overall (starttime in clock ticks since boot);
        # after stripping pid and (comm), it's at index 19 in after_comm.
        starttime_ticks = int(after_comm[19])
    except (IndexError, ValueError):
        return None
    try:
        hz = os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError):
        return None
    try:
        with open("/proc/stat", "r") as f:
            btime: int | None = None
            for line in f:
                if line.startswith("btime "):
                    try:
                        btime = int(line.split()[1])
                    except (IndexError, ValueError):
                        return None
                    break
    except OSError:
        return None
    if btime is None:
        return None
    return btime + starttime_ticks / hz


# ---------------------------------------------------------------------------
# Launcher's own config dir
# ---------------------------------------------------------------------------


def launcher_config_dir() -> Path:
    """Return the directory for the launcher's own `workspaces.json`.

    Linux / macOS: `~/.config/vscode-launcher` (XDG convention). Windows
    would use `%APPDATA%\\vscode-launcher\\` — stubbed with the XDG path
    for now so callers don't branch; porting can swap this later.
    """
    if IS_WINDOWS:
        # TODO(windows): use %APPDATA%
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "vscode-launcher"
    return Path.home() / ".config" / "vscode-launcher"
