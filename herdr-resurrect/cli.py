#!/usr/bin/env python3
"""herdr-resurrect — save/restore the programs running in herdr panes.

  herdr-resurrect save              # snapshot running programs (all sessions)
  herdr-resurrect restore [--dry-run]
  herdr-resurrect autorestore [--window S] [--interval S]  # poll then restore
  herdr-resurrect status            # last snapshot age + contents
  herdr-resurrect list              # what the snapshot would relaunch
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

import config  # noqa: E402
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
    if r.labels_restored or r.labels_already or r.labels_failed:
        print(f"labels {tag}: {len(r.labels_restored)}   "
              f"already-running: {len(r.labels_already)}   "
              f"failed: {len(r.labels_failed)}")
        for label, pid, cmd in r.labels_restored:
            print(f"  [{tag}] {label:14} {pid:8} {cmd}")
        for label, cmd in r.labels_already:
            print(f"  [skip busy]  {label:14} {cmd}")
        for label, cmd in r.labels_failed:
            print(f"  [failed]     {label:14} {cmd}")
    return 0


def _cmd_autorestore(a) -> int:
    """Poll for herdr readiness after a boot/restart and relaunch pane programs.

    herdr has no systemd unit and no post-restore hook, and each named session's
    server is spawned lazily when its terminal is opened. So rather than fire
    once at a fixed time, poll: retry restore across a window, no-op while herdr
    is down, and re-run so sessions attached later in the window still get filled.
    restore() only fills idle panes, so repeated passes are safe once programs
    are back."""
    interval = max(5, a.interval)
    deadline = time.monotonic() + max(interval, a.window)
    while True:
        try:
            r = resurrect.restore()
            for snap, pid in r.restored:
                print(f"[autorestore] {pid:8} {snap.cmdline}", flush=True)
            for label, pid, cmd in r.labels_restored:
                print(f"[autorestore] {pid:8} {label} -> {cmd}", flush=True)
        except herdr_api.HerdrError:
            pass  # herdr not up yet (or mid-restore); keep polling
        if time.monotonic() >= deadline:
            return 0
        time.sleep(interval)


def _cmd_status(_a) -> int:
    snaps, saved_at = snapshot.load_snaps()
    print(f"snapshot: {_age(saved_at)}  ({len(snaps)} program(s))")
    return 0


def _cmd_list(_a) -> int:
    snaps, _saved_at = snapshot.load_snaps()
    label_commands = config.load().get("label_commands", {}) or {}
    if not snaps and not label_commands:
        print("no snapshot and no label_commands configured")
        return 1
    if snaps:
        print("snapshot:")
        for s in snaps:
            print(f"  {s.session:8} {s.workspace_label:20} {s.pane_id:8} {s.cmdline}")
    if label_commands:
        print("label_commands:")
        for label, cmd in label_commands.items():
            print(f"  {label:20} {cmd}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="herdr-resurrect")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("save").set_defaults(func=_cmd_save)
    r = sub.add_parser("restore")
    r.add_argument("--dry-run", action="store_true")
    r.set_defaults(func=_cmd_restore)
    ar = sub.add_parser("autorestore",
                        help="poll for herdr after boot, then restore (for the timer)")
    ar.add_argument("--window", type=float, default=900.0,
                    help="seconds to keep polling (default 900)")
    ar.add_argument("--interval", type=float, default=30.0,
                    help="seconds between restore attempts (default 30)")
    ar.set_defaults(func=_cmd_autorestore)
    sub.add_parser("status").set_defaults(func=_cmd_status)
    sub.add_parser("list").set_defaults(func=_cmd_list)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
