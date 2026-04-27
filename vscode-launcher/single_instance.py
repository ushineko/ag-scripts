"""Session-bus singleton + show-main-window IPC.

The first vscode-launcher process to call `SingletonGuard.claim()` registers
the well-known D-Bus name `org.kde.vscode_launcher` and gets back the
"singleton" role. Subsequent processes find the name taken; their
`claim()` returns False and they call `signal_show_main_window()` to ask
the existing daemon to surface its main window, then exit.

KGlobalAccel already prevents duplicate hotkey registration, but it can't
*reach into* the existing daemon to surface its UI — that's what this
D-Bus surface is for. Without it, a second `vscode-launcher` invocation
would either fail silently or pop a fresh duplicate window.
"""

from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import QObject, pyqtSlot
from PyQt6.QtDBus import QDBusConnection, QDBusInterface

SERVICE_NAME = "org.kde.vscode_launcher"
OBJECT_PATH = "/"
INTERFACE_NAME = "org.kde.vscode_launcher"


class _ShowMainWindowAdaptor(QObject):
    """Tiny QObject whose only job is to expose `ShowMainWindow` to D-Bus.

    We export this rather than the MainWindow itself so that QMainWindow's
    inherited slots (close, raise_, hide, …) don't accidentally become
    remotely callable. Parented to the daemon's MainWindow so its lifetime
    matches; do not free it explicitly.
    """

    def __init__(
        self, on_show_main_window: Callable[[], None], parent: QObject
    ) -> None:
        super().__init__(parent)
        self._callback = on_show_main_window

    @pyqtSlot()
    def ShowMainWindow(self) -> None:
        try:
            self._callback()
        except Exception:
            # A misbehaving callback must not poison the D-Bus thread.
            pass


class SingletonGuard:
    """Owns the session-bus name claim. Two-phase API:

    1. `claim()` — try to grab the well-known name. Returns True if we're
       the singleton.
    2. If claim returned True: call `export(parent, callback)` once the
       MainWindow exists, so the adaptor can be parented and registered.
    3. If claim returned False: call `signal_show_main_window()` and exit.

    Survives missing/dead session bus by treating "no bus" as "we're the
    only instance" — single-instance enforcement is best-effort, not a
    correctness guarantee.
    """

    def __init__(self) -> None:
        self._bus = QDBusConnection.sessionBus()
        self._claimed = False
        self._adaptor: _ShowMainWindowAdaptor | None = None

    def claim(self) -> bool:
        if not self._bus.isConnected():
            # No D-Bus = no IPC. Caller proceeds as if singleton.
            return True
        self._claimed = self._bus.registerService(SERVICE_NAME)
        return self._claimed

    def signal_show_main_window(self) -> Optional[str]:
        """Tell the existing daemon to show its main window. Returns None
        on success or an error string for diagnostics. Safe to call when
        no daemon exists (returns the error text)."""
        if not self._bus.isConnected():
            return "session bus unreachable"
        iface = QDBusInterface(SERVICE_NAME, OBJECT_PATH, INTERFACE_NAME, self._bus)
        if not iface.isValid():
            return "no daemon registered"
        reply = iface.call("ShowMainWindow")
        msg = reply.errorMessage()
        return msg if msg else None

    def export(
        self, parent: QObject, on_show_main_window: Callable[[], None]
    ) -> bool:
        """Register the adaptor object on the bus. Call only after a
        successful `claim()`. Returns True on success."""
        if not self._claimed or not self._bus.isConnected():
            return False
        self._adaptor = _ShowMainWindowAdaptor(on_show_main_window, parent)
        return self._bus.registerObject(
            OBJECT_PATH,
            INTERFACE_NAME,
            self._adaptor,
            QDBusConnection.RegisterOption.ExportAllSlots,
        )
