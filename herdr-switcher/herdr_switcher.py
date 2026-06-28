#!/usr/bin/env python3
"""herdr-switcher daemon — alt-tab popup for herdr spaces.

Tray-resident. Registers a global hotkey (Shift+Tab by default) via KGlobalAccel;
on press it shows a frameless alt-tab popup of spaces ordered by recency, and on
commit it raises the hosting terminal and focuses the space.

v1 targets KDE Plasma 6 / Wayland. The hotkey and window-activation backends are
isolated (global_shortcut, window_actions) so a macOS backend can be added later
per the spec.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtGui import QIcon  # noqa: E402
from PyQt6.QtWidgets import (  # noqa: E402
    QApplication,
    QMenu,
    QSystemTrayIcon,
)

import config  # noqa: E402
import herdr_api  # noqa: E402
import mru  # noqa: E402
import session_windows  # noqa: E402
from core import switch_to_space  # noqa: E402
from global_shortcut import GlobalShortcut, parse_hotkey  # noqa: E402
from popup import SpacePopup  # noqa: E402

APP_ID = "herdr-switcher"
ICON_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), "herdr-switcher.svg")


class Daemon:
    def __init__(self, app: QApplication) -> None:
        self.app = app
        self.cfg = config.load()
        self.mru: list[str] = mru.load()

        self.popup = SpacePopup()
        self.popup.activate_requested.connect(self._on_commit)

        self.commit_timer = QTimer()
        self.commit_timer.setSingleShot(True)
        self.commit_timer.setInterval(int(self.cfg["popup_commit_delay_ms"]))
        self.commit_timer.timeout.connect(self._commit_selection)

        self.shortcut = GlobalShortcut(
            APP_ID, "show-popup", "herdr-switcher", "Show space switcher"
        )
        self.shortcut.pressed.connect(self._on_hotkey_pressed)
        self.shortcut.released.connect(self._on_hotkey_released)

        self.tray = self._build_tray()
        self._bind_hotkey()

    # -- tray ---------------------------------------------------------------

    def _icon(self) -> QIcon:
        if os.path.exists(ICON_PATH):
            return QIcon(ICON_PATH)
        return QIcon.fromTheme("preferences-system-windows")

    def _build_tray(self) -> QSystemTrayIcon:
        tray = QSystemTrayIcon(self._icon())
        tray.setToolTip("herdr-switcher")
        menu = QMenu()
        menu.addAction(f"Hotkey: {self.cfg['hotkey']}").setEnabled(False)
        menu.addSeparator()
        menu.addAction("Quit", self.app.quit)
        tray.setContextMenu(menu)
        tray.show()
        return tray

    def _bind_hotkey(self) -> None:
        if not self.shortcut.is_available():
            self._notify("KGlobalAccel unavailable — hotkey not registered")
            return
        if not self.shortcut.set_binding(parse_hotkey(self.cfg["hotkey"])):
            self._notify(
                f"Could not bind {self.cfg['hotkey']} "
                "(already in use by another component?)"
            )

    def _notify(self, msg: str) -> None:
        sys.stderr.write(f"herdr-switcher: {msg}\n")
        if self.tray is not None:
            self.tray.showMessage("herdr-switcher", msg)

    # -- hotkey / popup flow ------------------------------------------------

    def _build_space_list(self) -> tuple[list, int]:
        """Return (ordered spaces, initial_row). Snapshots the current space,
        promotes it in the MRU, then orders all spaces by recency."""
        current = None
        try:
            current = session_windows.current_space()
        except herdr_api.HerdrError:
            pass
        if current is not None:
            self.mru = mru.touch(self.mru, current.key)
            mru.save(self.mru)
        try:
            spaces = herdr_api.all_spaces()
        except herdr_api.HerdrError as exc:
            self._notify(f"failed to list spaces: {exc}")
            return [], 0
        ordered = mru.order_spaces(spaces, self.mru)
        # Alt-tab: if we know where we are, pre-select the *previous* space.
        initial_row = 1 if (current is not None and len(ordered) > 1) else 0
        return ordered, initial_row

    def _on_hotkey_pressed(self) -> None:
        self.commit_timer.stop()
        if self.popup.isVisible():
            self.popup.cycle_next()
        else:
            spaces, initial_row = self._build_space_list()
            self.popup.show_with_spaces(spaces, initial_row=initial_row)

    def _on_hotkey_released(self) -> None:
        if self.popup.isVisible():
            self.commit_timer.start()

    def _commit_selection(self) -> None:
        if self.popup.isVisible():
            self.popup.activate_current()

    def _on_commit(self, space) -> None:
        try:
            result = switch_to_space(space, terminal=self.cfg["terminal"])
        except Exception as exc:  # noqa: BLE001 - never let a switch crash the daemon
            self._notify(f"switch failed: {exc}")
            return
        if not result.ok:
            self._notify(result.detail)
        self.mru = mru.touch(self.mru, space.key)
        mru.save(self.mru)

    def shutdown(self) -> None:
        self.shortcut.unregister()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="herdr-switcher")
    parser.add_argument("--tray", action="store_true",
                        help="run tray-resident (default behavior)")
    parser.parse_args(argv)

    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_ID)
    app.setDesktopFileName(APP_ID)
    app.setQuitOnLastWindowClosed(False)  # popup hide must not quit the daemon

    daemon = Daemon(app)
    app.aboutToQuit.connect(daemon.shutdown)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
