#!/usr/bin/env python3
"""Phase-1 manual smoke test driver.

Wires up a real SlackClient against ~/.config/slack-presence-toggle/token,
a thread-based scheduler, and the FocusStateMachine. Exposes a REPL so you
can drive the state machine by hand and watch real Slack respond.

WARNING: This sets your actual Slack presence and custom status. Use a
short status_safety_buffer (set in config or override on the command line)
to avoid leaving stale state if you Ctrl+C mid-session.

Commands (type these at the prompt):
  slack            simulate Slack window activated
  other [rc]       simulate non-Slack window activated (default rc=firefox)
  fire             fire any pending grace timer immediately (skip the wait)
  status           show fsm snapshot + live Slack presence + live status
  enable           enable the state machine
  disable          disable (clears any forced state)
  shutdown         run shutdown sequence (also exits)
  quit / exit      shutdown and exit
  help             this help
"""

from __future__ import annotations

import logging
import shlex
import sys
import threading
from pathlib import Path

from slack_presence_toggle.config import Config, DEFAULT_CONFIG_PATH
from slack_presence_toggle.slack_client import SlackClient
from slack_presence_toggle.state_machine import FocusStateMachine


class ThreadingScheduler:
    """Real-time scheduler backed by threading.Timer.

    Single pending handle at a time is enough for the focus state machine.
    Callbacks fire on the timer thread; the state machine does not require
    main-thread execution for its logic, so this is fine for the dev CLI.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._timers: dict[int, tuple[threading.Timer, callable]] = {}
        self._next_id = 0

    def schedule(self, delay, callback):
        with self._lock:
            self._next_id += 1
            handle = self._next_id
            t = threading.Timer(delay, self._fire_wrapped, args=(handle,))
            t.daemon = True
            self._timers[handle] = (t, callback)
            t.start()
        return handle

    def _fire_wrapped(self, handle):
        with self._lock:
            entry = self._timers.pop(handle, None)
        if entry is None:
            return
        _, callback = entry
        try:
            callback()
        except Exception:
            logging.exception("scheduled callback raised")

    def cancel(self, handle):
        with self._lock:
            entry = self._timers.pop(handle, None)
        if entry is not None:
            entry[0].cancel()

    def fire_pending(self) -> bool:
        """Fire and remove the earliest-scheduled pending timer immediately."""
        with self._lock:
            if not self._timers:
                return False
            handle = next(iter(self._timers))
            t, callback = self._timers.pop(handle)
            t.cancel()
        try:
            callback()
        except Exception:
            logging.exception("manual fire callback raised")
        return True


def _load_token(token_file: Path) -> str:
    if not token_file.exists():
        sys.exit(f"token file not found: {token_file}")
    token = token_file.read_text(encoding="utf-8").strip()
    if not token.startswith("xoxp-"):
        sys.exit(f"token in {token_file} does not start with xoxp-")
    return token


def _print_status(fsm: FocusStateMachine, slack: SlackClient) -> None:
    snap = fsm.snapshot
    print(f"  state machine: enabled={snap.enabled} focus={snap.focus.value} "
          f"we_forced_away={snap.we_forced_away} we_forced_status={snap.we_forced_status}")
    health, presence = slack.get_presence()
    if health.ok and presence:
        print(f"  presence:      {presence.presence}  "
              f"manual_away={presence.manual_away} auto_away={presence.auto_away} "
              f"connections={presence.connection_count}")
    else:
        print(f"  presence:      ERROR ({health.error})")
    health, status = slack.get_profile_status()
    if health.ok and status:
        print(f"  status:        text={status.text!r} emoji={status.emoji!r} "
              f"expiration={status.expiration}")
    else:
        print(f"  status:        ERROR ({health.error})")


def _print_transition(label: str, result) -> None:
    parts = []
    for name in ("presence_call", "status_set_call", "status_clear_call"):
        h = getattr(result, name)
        if h is None:
            continue
        parts.append(f"{name}={'ok' if h.ok else h.error}")
    if parts:
        print(f"  {label}: {', '.join(parts)}")


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    config = Config.load(DEFAULT_CONFIG_PATH)
    print(f"Using config: grace={config.grace_seconds}s "
          f"safety_buffer={config.status_safety_buffer_seconds}s "
          f"status_text={config.status_text!r} emoji={config.status_emoji!r}")
    print()
    print("WARNING: this driver makes real Slack API calls (presence + status).")
    print("If you Ctrl+C mid-session, run `python3 dev_cli.py` and type `shutdown` "
          "to release any forced state, or wait for status_safety_buffer to expire.")
    print()

    token = _load_token(Path(config.token_file).expanduser())
    slack = SlackClient(token)
    health, info = slack.auth_test()
    if not health.ok:
        sys.exit(f"auth.test failed: {health.error}")
    print(f"Authenticated as user={info.user} team={info.team}")

    scheduler = ThreadingScheduler()
    fsm = FocusStateMachine(slack=slack, scheduler=scheduler, config=config)
    print("State machine started. Type `help` for commands.\n")

    try:
        while True:
            try:
                line = input("> ").strip()
            except EOFError:
                line = "quit"
            if not line:
                continue
            parts = shlex.split(line)
            cmd, args = parts[0], parts[1:]

            if cmd in ("quit", "exit"):
                _print_transition("shutdown", fsm.shutdown())
                break
            elif cmd == "help":
                print(__doc__)
            elif cmd == "slack":
                _print_transition("slack", fsm.on_window_activated(config.slack_resource_class))
            elif cmd == "other":
                rc = args[0] if args else "firefox"
                _print_transition(f"other({rc})", fsm.on_window_activated(rc))
            elif cmd == "fire":
                fired = scheduler.fire_pending()
                print(f"  fired pending timer: {fired}")
            elif cmd == "status":
                _print_status(fsm, slack)
            elif cmd == "enable":
                _print_transition("enable", fsm.set_enabled(True))
            elif cmd == "disable":
                _print_transition("disable", fsm.set_enabled(False))
            elif cmd == "shutdown":
                _print_transition("shutdown", fsm.shutdown())
                break
            else:
                print(f"unknown command: {cmd!r}; type `help`")
    except KeyboardInterrupt:
        print("\n^C — running shutdown to release any forced state...")
        _print_transition("shutdown", fsm.shutdown())


if __name__ == "__main__":
    main()
