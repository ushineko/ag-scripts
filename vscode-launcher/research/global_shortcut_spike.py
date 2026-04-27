#!/usr/bin/env python3
"""KGlobalAccel global-shortcut registration spike — KDE Plasma 6.

Goal: prove that a Python process can register a global hotkey via
`org.kde.kglobalaccel` and receive notifications when the user presses
it from any app focus, including from outside the launcher.

This is a research artifact, not production code. If the spike works the
production version goes into the launcher itself (probably as
`global_shortcut.py`).

Usage: run, then press Meta+Alt+Space from anywhere. The script prints
a line per activation. Ctrl-C to exit; the script unregisters cleanly.
"""

from __future__ import annotations

import signal
import sys
from typing import Any

from PyQt6.QtCore import QMetaType, QObject, pyqtSlot
from PyQt6.QtDBus import QDBusArgument, QDBusConnection, QDBusInterface
from PyQt6.QtWidgets import QApplication

# KGlobalAccel registers under a 4-string `actionId`:
#   [componentUnique, actionUnique, componentFriendly, actionFriendly]
COMPONENT_UNIQUE = "vscode-launcher-spike"
ACTION_UNIQUE = "show-popup"
COMPONENT_FRIENDLY = "VSCode Launcher Spike"
ACTION_FRIENDLY = "Show popup"
ACTION_ID = [COMPONENT_UNIQUE, ACTION_UNIQUE, COMPONENT_FRIENDLY, ACTION_FRIENDLY]

# Qt key + modifier flags. Meta+Alt+Space:
#   Key_Space        = 0x20
#   MetaModifier     = 0x10000000  (the "Super"/"Windows" key on Linux)
#   AltModifier      = 0x08000000
HOTKEY = 0x20 | 0x10000000 | 0x08000000

# setShortcut flags (from KGlobalAccelD::Registration enum)
#   0x1 = SetPresent     (record this as the current binding)
#   0x2 = NoAutoloading  (don't restore from saved kglobalshortcutsrc)
#   0x4 = IsDefault      (this is also the default)
SET_PRESENT = 0x1
NO_AUTOLOADING = 0x2


def _qstringlist(values: list[str]) -> QDBusArgument:
    """Marshal a Python list[str] as a D-Bus `as` (QStringList)."""
    arg = QDBusArgument()
    arg.add(values, QMetaType.Type.QStringList.value)
    return arg


def _int32_array(values: list[int]) -> QDBusArgument:
    """Marshal a Python list[int] as the D-Bus `ai` (array of int32) type
    that KGlobalAccel uses for keys (one int per key combo)."""
    arg = QDBusArgument()
    arg.beginArray(QMetaType.Type.Int.value)
    for v in values:
        arg.add(v, QMetaType.Type.Int.value)
    arg.endArray()
    return arg


def _uint(value: int) -> QDBusArgument:
    """Marshal a Python int as a D-Bus uint32. Plain ints get sent as int32
    by PyQt6's auto-conversion; KGlobalAccel's `flags` arg is uint32."""
    arg = QDBusArgument()
    arg.add(value, QMetaType.Type.UInt.value)
    return arg


class GlobalShortcutSpike(QObject):
    """Registers Meta+Alt+Space and prints a line on every activation."""

    def __init__(self) -> None:
        super().__init__()
        self.bus = QDBusConnection.sessionBus()
        if not self.bus.isConnected():
            raise RuntimeError("session D-Bus not available")

        self.iface = QDBusInterface(
            "org.kde.kglobalaccel",
            "/kglobalaccel",
            "org.kde.KGlobalAccel",
            self.bus,
        )
        if not self.iface.isValid():
            raise RuntimeError(
                f"KGlobalAccel interface unavailable: {self.iface.lastError().message()}"
            )

        self._register_action()
        self._set_shortcut()
        self._connect_signal()

        print(f"[spike] Registered '{COMPONENT_UNIQUE}/{ACTION_UNIQUE}'")
        print(f"[spike] Shortcut: Meta+Alt+Space (Qt key code 0x{HOTKEY:08x})")
        print("[spike] Press the combo from any app. Ctrl-C to exit.")

    # ------------------------------------------------------------------

    def _register_action(self) -> None:
        reply = self.iface.call("doRegister", _qstringlist(ACTION_ID))
        if reply.errorMessage():
            raise RuntimeError(f"doRegister failed: {reply.errorMessage()}")

    def _set_shortcut(self) -> None:
        reply = self.iface.call(
            "setShortcut",
            _qstringlist(ACTION_ID),
            _int32_array([HOTKEY]),
            _uint(SET_PRESENT | NO_AUTOLOADING),
        )
        if reply.errorMessage():
            raise RuntimeError(f"setShortcut failed: {reply.errorMessage()}")

    def _connect_signal(self) -> None:
        # KGlobalAccel translates dashes in componentUnique to underscores
        # for the D-Bus object path. So `vscode-launcher-spike` becomes
        # `/component/vscode_launcher_spike`.
        component_path = "/component/" + COMPONENT_UNIQUE.replace("-", "_")
        for signal_name, slot in (
            ("globalShortcutPressed", self._on_shortcut_pressed),
            ("globalShortcutReleased", self._on_shortcut_released),
        ):
            ok = self.bus.connect(
                "org.kde.kglobalaccel",
                component_path,
                "org.kde.kglobalaccel.Component",
                signal_name,
                slot,
            )
            if not ok:
                raise RuntimeError(
                    f"failed to connect to {signal_name} at {component_path}"
                )

    @pyqtSlot(str, str, "qlonglong")
    def _on_shortcut_pressed(
        self, component: str, action: str, timestamp: int
    ) -> None:
        print(
            f"[spike] PRESS    component={component!r} action={action!r} "
            f"ts={timestamp}"
        )

    @pyqtSlot(str, str, "qlonglong")
    def _on_shortcut_released(
        self, component: str, action: str, timestamp: int
    ) -> None:
        print(
            f"[spike] RELEASE  component={component!r} action={action!r} "
            f"ts={timestamp}"
        )

    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        try:
            self.iface.call("unRegister", _qstringlist(ACTION_ID))
            print("[spike] unregistered")
        except Exception as e:
            print(f"[spike] cleanup error: {e}")


def main() -> int:
    app = QApplication(sys.argv)
    try:
        spike = GlobalShortcutSpike()
    except RuntimeError as e:
        print(f"[spike] setup failed: {e}", file=sys.stderr)
        return 1

    # Auto-exit after `--seconds N` (default 0 = run forever) so the spike
    # is easier to drive from a non-interactive shell.
    duration = 0
    if "--seconds" in sys.argv:
        try:
            duration = int(sys.argv[sys.argv.index("--seconds") + 1])
        except (ValueError, IndexError):
            duration = 0
    if duration > 0:
        from PyQt6.QtCore import QTimer

        QTimer.singleShot(duration * 1000, app.quit)
        print(f"[spike] auto-exit in {duration}s")

    def _signal_handler(*_: Any) -> None:
        spike.cleanup()
        app.quit()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    rc = app.exec()
    spike.cleanup()
    return rc


if __name__ == "__main__":
    sys.exit(main())
