from __future__ import annotations

import logging

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from PyQt6.QtDBus import QDBusConnection

log = logging.getLogger(__name__)

BUS_NAME = "io.github.ushineko.SlackPresenceToggle"
OBJECT_PATH = "/FocusMonitor"
INTERFACE = "io.github.ushineko.SlackPresenceToggle.FocusMonitor"


class FocusListener(QObject):
    """QtDBus service receiving WindowActivated calls from the KWin script.

    Registers `io.github.ushineko.SlackPresenceToggle` on the session bus and
    exposes `WindowActivated(s, s)` at object path /FocusMonitor. Each
    incoming call emits the `window_activated` Qt signal so the rest of the
    app can handle it on the Qt event loop without touching D-Bus.
    """

    window_activated = pyqtSignal(str, str)  # (resource_class, caption)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)

    def register(self) -> bool:
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            log.error("session D-Bus not connected")
            return False
        if not bus.registerService(BUS_NAME):
            log.error(
                "could not register %s on session bus (another instance running?)",
                BUS_NAME,
            )
            return False
        ok = bus.registerObject(
            OBJECT_PATH,
            INTERFACE,
            self,
            QDBusConnection.RegisterOption.ExportAllSlots,
        )
        if not ok:
            log.error("could not register object at %s", OBJECT_PATH)
            bus.unregisterService(BUS_NAME)
            return False
        log.info("D-Bus listener registered: %s %s", BUS_NAME, OBJECT_PATH)
        return True

    def unregister(self) -> None:
        bus = QDBusConnection.sessionBus()
        bus.unregisterObject(OBJECT_PATH)
        bus.unregisterService(BUS_NAME)

    # Note: the slot signature must match the KWin script's callDBus args.
    @pyqtSlot(str, str)
    def WindowActivated(self, resource_class: str, caption: str) -> None:
        log.debug("WindowActivated rc=%r caption=%r", resource_class, caption)
        self.window_activated.emit(resource_class, caption)
