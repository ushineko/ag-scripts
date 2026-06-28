"""Thin wrapper over the herdr CLI / socket API.

herdr exposes its workspace and session state over a socket via the `herdr`
binary. This module shells out to that binary and returns typed records. It is
stdlib-only so it can be unit-tested and used headless without Qt.

Binaries are resolved to absolute paths on purpose: herdr-switcher runs from a
KDE global shortcut / autostart entry, where PATH is often minimal.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass


class HerdrError(RuntimeError):
    """A herdr CLI call failed or returned unparseable output."""


def _resolve_bin(name: str, extra: tuple[str, ...] = ()) -> str:
    """Resolve a binary to an absolute path (PATH may be minimal under autostart)."""
    found = shutil.which(name)
    if found:
        return found
    candidates = (
        os.path.expanduser(f"~/.local/bin/{name}"),
        f"/usr/local/bin/{name}",
        f"/usr/bin/{name}",
        *extra,
    )
    for path in candidates:
        if os.path.exists(path):
            return path
    return name  # last resort; let the OS raise a clear error


HERDR_BIN = _resolve_bin("herdr")


@dataclass(frozen=True)
class Session:
    name: str
    default: bool
    running: bool
    socket_path: str


@dataclass
class Space:
    """A herdr workspace ("space"), tagged with its owning session."""

    session: str          # session name, e.g. "default" | "work"
    workspace_id: str     # herdr id, e.g. "w1"
    label: str            # human label, e.g. "sysadmin"
    number: int           # herdr's own 1..N ordering within the session
    agent_status: str     # "working" | "idle" | "done" | "blocked" | "unknown"
    focused: bool         # focused within its own session
    last_used: float | None = None  # filled from MRU state for cross-session ordering

    @property
    def key(self) -> str:
        """Stable identity across refreshes (session + workspace id)."""
        return f"{self.session}/{self.workspace_id}"


def _run(args: list[str], *, timeout: float = 5.0) -> str:
    cmd = [HERDR_BIN, *args]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except FileNotFoundError as exc:
        raise HerdrError(f"herdr binary not found at {HERDR_BIN!r}") from exc
    except subprocess.TimeoutExpired as exc:
        raise HerdrError(f"herdr timed out: {' '.join(args)}") from exc
    if proc.returncode != 0:
        raise HerdrError(
            f"herdr {' '.join(args)} failed (rc={proc.returncode}): "
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )
    return proc.stdout


def _session_args(session: str) -> list[str]:
    """`--session <name>` selects which herdr server to talk to.

    The default session is the implicit target, so omit the flag for it to avoid
    any attach/create ambiguity.
    """
    return [] if session in ("", "default") else ["--session", session]


def list_sessions() -> list[Session]:
    raw = _run(["session", "list", "--json"])
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HerdrError(f"unparseable session list: {raw!r}") from exc
    out: list[Session] = []
    for s in data.get("sessions", []):
        out.append(
            Session(
                name=s["name"],
                default=bool(s.get("default")),
                running=bool(s.get("running")),
                socket_path=s.get("socket_path", ""),
            )
        )
    return out


def list_spaces(session: str) -> list[Space]:
    """List spaces (workspaces) for one session."""
    raw = _run([*_session_args(session), "workspace", "list"])
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HerdrError(f"unparseable workspace list for {session!r}: {raw!r}") from exc
    workspaces = data.get("result", {}).get("workspaces", [])
    return [
        Space(
            session=session,
            workspace_id=w["workspace_id"],
            label=w.get("label", w["workspace_id"]),
            number=int(w.get("number", 0)),
            agent_status=w.get("agent_status", "unknown"),
            focused=bool(w.get("focused")),
        )
        for w in workspaces
    ]


def all_spaces() -> list[Space]:
    """Flat list of spaces across every running session."""
    spaces: list[Space] = []
    for sess in list_sessions():
        if not sess.running:
            continue
        try:
            spaces.extend(list_spaces(sess.name))
        except HerdrError:
            # A session may stop between enumeration and query; skip it.
            continue
    return spaces


def focus(session: str, workspace_id: str) -> None:
    """Switch the given session to the given space."""
    _run([*_session_args(session), "workspace", "focus", workspace_id])
