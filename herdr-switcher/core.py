"""Core switch orchestration, shared by the CLI harness and the daemon.

Given a chosen space, bring its session's terminal window to the front (maximized)
and focus the space inside herdr. If the session is running but detached (no
window), spawn a terminal that attaches it; the user positions that window.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

import herdr_api
from herdr_api import Space
from session_windows import session_to_terminal_pid
from window_actions import activate_and_maximize


@dataclass
class SwitchResult:
    ok: bool
    detail: str
    terminal_pid: int | None = None
    spawned: bool = False


def _spawn_attach(session: str, terminal: str) -> None:
    """Open a terminal that attaches `session` (detached-session case)."""
    if session in ("", "default"):
        attach = [herdr_api.HERDR_BIN]
    else:
        attach = [herdr_api.HERDR_BIN, "session", "attach", session]
    cmd = [terminal, "-e", *attach]
    # Strip herdr's recursion-guard vars: if the daemon was launched from inside
    # a herdr session, an inherited HERDR_ENV makes the new `herdr` refuse to
    # start ("nested herdr is disabled"). The fresh terminal must look like a
    # clean, non-nested context.
    env = os.environ.copy()
    for var in ("HERDR_ENV", "HERDR_SESSION"):
        env.pop(var, None)
    subprocess.Popen(
        cmd,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )


def switch_to_space(
    space: Space, *, terminal: str = "alacritty", dry_run: bool = False
) -> SwitchResult:
    terminal_pid = session_to_terminal_pid().get(space.session)

    if dry_run:
        if terminal_pid is not None:
            return SwitchResult(
                True, f"would activate terminal pid {terminal_pid} then focus "
                f"{space.session}/{space.workspace_id}", terminal_pid
            )
        return SwitchResult(
            True, f"session {space.session!r} detached; would spawn "
            f"`{terminal} -e herdr ...` then focus {space.workspace_id}", None, True
        )

    spawned = False
    if terminal_pid is not None:
        activated = activate_and_maximize(terminal_pid)
        if not activated:
            # Non-fatal: still focus the space so herdr is correct even if the
            # compositor declined to raise the window.
            detail_window = f"window pid {terminal_pid} (activation unconfirmed)"
        else:
            detail_window = f"window pid {terminal_pid} raised+maximized"
    else:
        _spawn_attach(space.session, terminal)
        spawned = True
        detail_window = f"spawned terminal attaching {space.session!r}"

    try:
        herdr_api.focus(space.session, space.workspace_id)
    except herdr_api.HerdrError as exc:
        return SwitchResult(False, f"{detail_window}; focus failed: {exc}",
                            terminal_pid, spawned)

    return SwitchResult(
        True, f"{detail_window}; focused {space.session}/{space.workspace_id}",
        terminal_pid, spawned
    )
