#!/usr/bin/env python3
"""Print '<W> <H> <X> <Y>' (logical coords) for the single portrait monitor.

Exits non-zero with a message on stderr if zero or multiple portrait monitors
are connected — the wrapper needs an unambiguous target.
"""
import sys


def main() -> int:
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    portrait = []
    for screen in app.screens():
        g = screen.geometry()
        if g.height() > g.width():
            portrait.append((g.width(), g.height(), g.x(), g.y()))

    if len(portrait) == 0:
        print("error: no portrait monitor detected", file=sys.stderr)
        return 1
    if len(portrait) > 1:
        print(f"error: expected exactly one portrait monitor, found {len(portrait)}", file=sys.stderr)
        return 1

    print(*portrait[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
