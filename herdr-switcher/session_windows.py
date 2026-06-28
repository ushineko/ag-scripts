"""Map herdr sessions to the terminal window that hosts them, and resolve the
currently-active space.

herdr uses a handoff model: each running session has at most one attached client
process, which runs inside a terminal emulator window. We identify clients by
their argv, walk /proc to the terminal-emulator ancestor PID, and (via KWin)
match that PID to a window.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

from herdr_api import Space, _resolve_bin, list_spaces

KDOTOOL_BIN = _resolve_bin("kdotool")

# Terminal emulators whose window PID KWin will report. Extend as needed.
TERMINALS = {
    "alacritty",
    "kitty",
    "konsole",
    "wezterm",
    "wezterm-gui",
    "foot",
    "ghostty",
    "xterm",
}


@dataclass
class Client:
    pid: int            # the herdr client process
    session: str        # session name it is attached to ("default" for the bare client)
    terminal_pid: int | None  # PID of the hosting terminal emulator window


def _cmdline(pid: int) -> list[str]:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            parts = fh.read().split(b"\0")
        return [p.decode("utf-8", "replace") for p in parts if p]
    except OSError:
        return []


def _comm(pid: int) -> str:
    try:
        with open(f"/proc/{pid}/comm") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _ppid(pid: int) -> int | None:
    try:
        with open(f"/proc/{pid}/status") as fh:
            for line in fh:
                if line.startswith("PPid:"):
                    return int(line.split()[1])
    except OSError:
        return None
    return None


def _session_from_argv(argv: list[str]) -> str | None:
    """Determine which session a herdr client is attached to from its argv.

    `herdr server ...`            -> not a client (None)
    `herdr`                       -> default session
    `herdr --session NAME ...`    -> NAME
    `herdr session attach NAME`   -> NAME
    """
    if not argv or os.path.basename(argv[0]) != "herdr":
        return None
    rest = argv[1:]
    if rest and rest[0] == "server":
        return None
    if "--session" in rest:
        i = rest.index("--session")
        if i + 1 < len(rest):
            return rest[i + 1]
    if len(rest) >= 3 and rest[0] == "session" and rest[1] == "attach":
        return rest[2]
    if not rest:
        return "default"
    # `herdr session attach` handled above; any other bare/option form -> default
    if rest and rest[0] not in ("session", "--session"):
        return "default"
    return None


def _terminal_ancestor(pid: int, max_depth: int = 8) -> int | None:
    """Walk parents from pid until a known terminal emulator is found."""
    cur: int | None = pid
    for _ in range(max_depth):
        parent = _ppid(cur) if cur else None
        if not parent or parent <= 1:
            return None
        if _comm(parent) in TERMINALS:
            return parent
        cur = parent
    return None


def _iter_pids() -> list[int]:
    return [int(name) for name in os.listdir("/proc") if name.isdigit()]


def find_clients() -> list[Client]:
    """Find all herdr client processes and their hosting terminal PIDs."""
    clients: list[Client] = []
    for pid in _iter_pids():
        if _comm(pid) != "herdr":
            continue
        session = _session_from_argv(_cmdline(pid))
        if session is None:
            continue  # server, not a client
        clients.append(
            Client(pid=pid, session=session, terminal_pid=_terminal_ancestor(pid))
        )
    return clients


def session_to_terminal_pid() -> dict[str, int]:
    """Map each session name to the PID of its hosting terminal window."""
    mapping: dict[str, int] = {}
    for client in find_clients():
        if client.terminal_pid is not None:
            mapping[client.session] = client.terminal_pid
    return mapping


def _kdotool(*args: str, timeout: float = 3.0) -> str:
    try:
        proc = subprocess.run(
            [KDOTOOL_BIN, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def active_window_pid() -> int | None:
    """PID owning the currently-active window (via KWin scripting / kdotool)."""
    win = _kdotool("getactivewindow")
    if not win:
        return None
    pid = _kdotool("getwindowpid", win)
    try:
        return int(pid)
    except (TypeError, ValueError):
        return None


def session_of_terminal_pid(terminal_pid: int) -> str | None:
    """Reverse lookup: which session's client lives in the given terminal PID."""
    for session, tpid in session_to_terminal_pid().items():
        if tpid == terminal_pid:
            return session
    return None


def current_space() -> Space | None:
    """The space the user is currently looking at: active window -> session ->
    that session's focused workspace.
    """
    pid = active_window_pid()
    if pid is None:
        return None
    session = session_of_terminal_pid(pid)
    if session is None:
        return None
    for space in list_spaces(session):
        if space.focused:
            return space
    return None
