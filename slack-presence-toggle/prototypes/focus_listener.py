#!/usr/bin/env python3
"""Prototype D-Bus listener for KWin window-activation events.

Pair with the slack-focus-monitor KWin script in kwin-script/. Run this in a
terminal, alt-tab between Slack/browser/other apps, and watch the output.

Goals of this prototype:
  1. Confirm KWin -> Python D-Bus path works on Plasma 6 / Wayland.
  2. Discover the resourceClass that the Slack desktop client reports.
  3. Watch for missed events, flapping, or weird transient activations.

Dependencies (Arch / CachyOS):
  sudo pacman -S python-dbus python-gobject
"""

from __future__ import annotations

import sys
import time

try:
    import dbus
    import dbus.service
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import GLib
except ImportError as e:
    print(f"Missing dependency: {e}", file=sys.stderr)
    print(
        "Install on Arch / CachyOS:\n"
        "  sudo pacman -S python-dbus python-gobject",
        file=sys.stderr,
    )
    sys.exit(1)


BUS_NAME = "io.github.ushineko.SlackFocusMonitor"
OBJECT_PATH = "/SlackFocusMonitor"
INTERFACE = "io.github.ushineko.SlackFocusMonitor"


class FocusMonitor(dbus.service.Object):
    def __init__(self, bus: dbus.SessionBus, path: str) -> None:
        super().__init__(bus, path)
        self._last_rc: str | None = None
        self._last_at: float = 0.0

    @dbus.service.method(INTERFACE, in_signature="ss", out_signature="")
    def WindowActivated(self, resource_class: str, caption: str) -> None:
        now = time.monotonic()
        ts = time.strftime("%H:%M:%S")
        # Cast dbus.String -> str so repr() shows clean quotes, not dbus.String('...')
        rc = str(resource_class) or "<none>"
        cap = str(caption) or "<empty>"

        # Highlight transitions vs. duplicates so flapping is easy to spot.
        if self._last_rc is None:
            tag = "INIT  "
        elif rc == self._last_rc:
            tag = "REPEAT"
        else:
            tag = "CHANGE"

        delta = now - self._last_at if self._last_at else 0.0
        print(f"[{ts}] {tag}  rc={rc!r:<32} dt={delta:5.2f}s  caption={cap!r}")

        self._last_rc = rc
        self._last_at = now


def main() -> int:
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()

    # The BusName object MUST stay alive for the duration of the program —
    # if it gets garbage-collected the bus name is released. Keep a local
    # reference; do not inline.
    try:
        bus_name = dbus.service.BusName(BUS_NAME, bus, do_not_queue=True)
    except dbus.exceptions.NameExistsException:
        print(
            f"Another listener is already registered on {BUS_NAME}. "
            "Stop it first.",
            file=sys.stderr,
        )
        return 1

    monitor = FocusMonitor(bus, OBJECT_PATH)
    _ = (bus_name, monitor)  # explicit keepalive, silence linters

    print(f"Listening on {BUS_NAME} {OBJECT_PATH}")
    print("Switch focus between windows. Ctrl+C to stop.\n")

    loop = GLib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
