"""Thin wrapper over the herdr CLI / socket API for herdr-resurrect.

Stdlib-only so it can be unit-tested and run headless (and from a systemd timer,
where PATH is minimal — hence absolute binary resolution).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass


class HerdrError(RuntimeError):
    """A herdr CLI call failed or returned unparseable output."""


def _resolve_bin(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    for path in (
        os.path.expanduser(f"~/.local/bin/{name}"),
        f"/usr/local/bin/{name}",
        f"/usr/bin/{name}",
    ):
        if os.path.exists(path):
            return path
    return name


HERDR_BIN = _resolve_bin("herdr")


@dataclass(frozen=True)
class Session:
    name: str
    default: bool
    running: bool


def _run(args: list[str], *, timeout: float = 8.0) -> str:
    try:
        proc = subprocess.run(
            [HERDR_BIN, *args],
            capture_output=True, text=True, timeout=timeout, check=False,
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
    return [] if session in ("", "default") else ["--session", session]


def _loads(raw: str, what: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HerdrError(f"unparseable {what}: {raw!r}") from exc


def list_sessions() -> list[Session]:
    data = _loads(_run(["session", "list", "--json"]), "session list")
    return [
        Session(name=s["name"], default=bool(s.get("default")),
                running=bool(s.get("running")))
        for s in data.get("sessions", [])
    ]


def list_workspace_labels(session: str) -> dict[str, str]:
    """workspace_id -> label for one session."""
    data = _loads(_run([*_session_args(session), "workspace", "list"]),
                  f"workspace list ({session})")
    return {
        w["workspace_id"]: w.get("label", w["workspace_id"])
        for w in data.get("result", {}).get("workspaces", [])
    }


def list_panes(session: str) -> list[dict]:
    """Raw pane dicts for one session (pane_id, workspace_id, tab_id, cwd, ...)."""
    data = _loads(_run([*_session_args(session), "pane", "list"]),
                  f"pane list ({session})")
    return data.get("result", {}).get("panes", [])


def pane_process_info(session: str, pane_id: str) -> dict:
    """{'foreground_processes':[{argv,cmdline,name,pid}], 'shell_pid':..}."""
    data = _loads(
        _run([*_session_args(session), "pane", "process-info", "--pane", pane_id]),
        f"pane process-info ({pane_id})",
    )
    return data.get("result", {}).get("process_info", {})


def pane_run(session: str, pane_id: str, command: str) -> None:
    """Type `command` + Enter into an existing pane's shell."""
    _run([*_session_args(session), "pane", "run", pane_id, command])
