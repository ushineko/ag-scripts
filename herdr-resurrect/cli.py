#!/usr/bin/env python3
"""herdr-resurrect — save/restore the programs running in herdr panes.

  herdr-resurrect save              # snapshot running programs (all sessions)
  herdr-resurrect restore [--dry-run]
  herdr-resurrect status            # last snapshot age + contents
  herdr-resurrect list              # what the snapshot would relaunch
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

import herdr_api  # noqa: E402
import resurrect  # noqa: E402
import snapshot  # noqa: E402


def _age(saved_at: float | None) -> str:
    if not saved_at:
        return "never"
    secs = max(0, int(time.time() - saved_at))
    if secs < 90:
        return f"{secs}s ago"
    if secs < 5400:
        return f"{secs // 60}m ago"
    return f"{secs // 3600}h ago"


def _cmd_save(_a) -> int:
    try:
        snaps = resurrect.save()
    except herdr_api.HerdrError as exc:
        # Timer-friendly: herdr may not be running. Don't fail the unit.
        print(f"herdr-resurrect: skipped save ({exc})", file=sys.stderr)
        return 0
    print(f"saved {len(snaps)} program(s):")
    for s in snaps:
        print(f"  {s.session:8} {s.workspace_label:20} {s.cmdline}")
    return 0


def _cmd_restore(a) -> int:
    try:
        r = resurrect.restore(dry_run=a.dry_run)
    except herdr_api.HerdrError as exc:
        print(f"herdr-resurrect: cannot restore ({exc})", file=sys.stderr)
        return 1
    tag = "would restore" if a.dry_run else "restored"
    print(f"{tag}: {len(r.restored)}   already-running: {len(r.already)}   "
          f"busy: {len(r.busy)}   unmatched: {len(r.unmatched)}")
    for s, pid in r.restored:
        print(f"  [{tag}] {pid:8} {s.cmdline}")
    for s in r.busy:
        print(f"  [skip busy]  {s.pane_id:8} {s.cmdline}")
    for s in r.unmatched:
        print(f"  [no pane]    {s.pane_id:8} {s.cmdline}")
    return 0


def _cmd_status(_a) -> int:
    snaps, saved_at = snapshot.load_snaps()
    print(f"snapshot: {_age(saved_at)}  ({len(snaps)} program(s))")
    return 0


def _cmd_list(_a) -> int:
    snaps, saved_at = snapshot.load_snaps()
    if not snaps:
        print("no snapshot")
        return 1
    for s in snaps:
        print(f"  {s.session:8} {s.workspace_label:20} {s.pane_id:8} {s.cmdline}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="herdr-resurrect")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("save").set_defaults(func=_cmd_save)
    r = sub.add_parser("restore")
    r.add_argument("--dry-run", action="store_true")
    r.set_defaults(func=_cmd_restore)
    sub.add_parser("status").set_defaults(func=_cmd_status)
    sub.add_parser("list").set_defaults(func=_cmd_list)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
