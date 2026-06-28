#!/usr/bin/env python3
"""Headless CLI for herdr-switcher — useful on its own and as a test harness for
the core (herdr API, window mapping, switch orchestration) without the GUI.

  herdr-switcher-cli list             # all spaces across sessions
  herdr-switcher-cli current          # the space under the active window
  herdr-switcher-cli sessions         # session -> terminal-window PID map
  herdr-switcher-cli switch S W [--dry-run]
"""

from __future__ import annotations

import argparse
import os
import sys

# Allow running both from the source dir and via an absolute-path symlink.
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

import herdr_api  # noqa: E402
import session_windows  # noqa: E402
from core import switch_to_space  # noqa: E402


def _cmd_list(_args) -> int:
    spaces = herdr_api.all_spaces()
    cur = session_windows.current_space()
    cur_key = cur.key if cur else None
    for sp in spaces:
        mark = "*" if sp.key == cur_key else ("." if sp.focused else " ")
        print(f"{mark} {sp.session:10} {sp.workspace_id:4} "
              f"{sp.label:24} [{sp.agent_status}]")
    return 0


def _cmd_current(_args) -> int:
    cur = session_windows.current_space()
    if cur is None:
        print("current space: <unknown> (active window is not a herdr terminal)")
        return 1
    print(f"current space: {cur.session}/{cur.workspace_id}  {cur.label}")
    return 0


def _cmd_sessions(_args) -> int:
    mapping = session_windows.session_to_terminal_pid()
    if not mapping:
        print("no attached herdr clients found")
        return 1
    for sess, pid in mapping.items():
        print(f"{sess:10} -> terminal pid {pid}")
    return 0


def _cmd_switch(args) -> int:
    spaces = herdr_api.all_spaces()
    match = next(
        (s for s in spaces if s.session == args.session
         and s.workspace_id == args.workspace), None
    )
    if match is None:
        print(f"no space {args.session}/{args.workspace}", file=sys.stderr)
        return 2
    result = switch_to_space(match, terminal=args.terminal, dry_run=args.dry_run)
    print(("DRY-RUN: " if args.dry_run else "") + result.detail)
    return 0 if result.ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="herdr-switcher-cli")
    parser.add_argument("--terminal", default="alacritty",
                        help="terminal used to attach detached sessions")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(func=_cmd_list)
    sub.add_parser("current").set_defaults(func=_cmd_current)
    sub.add_parser("sessions").set_defaults(func=_cmd_sessions)
    sw = sub.add_parser("switch")
    sw.add_argument("session")
    sw.add_argument("workspace")
    sw.add_argument("--dry-run", action="store_true")
    sw.set_defaults(func=_cmd_switch)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
