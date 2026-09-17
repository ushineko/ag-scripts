"""Session D-Bus endpoint for applying scenes (spec 025).

Lets a global keyboard shortcut reach the running monitor. The shortcut must go
*through* the monitor rather than around it: every liquidctl call on this
machine is serialised by `LiquidctlQueue` because the 5 s status poll, LCD
writes and the OpenRGB server all touch the same device. A shortcut that shelled
out to liquidctl directly would race the poll instead of queueing behind it.

D-Bus rather than a socket because `kwin_window_position.py` already registers a
session service in this project, so it is the established pattern here.

Registration failing is not fatal: the monitor keeps working and only the
shortcuts stop, which is logged once.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QObject, pyqtSlot
from PyQt6.QtDBus import QDBusConnection

_log = logging.getLogger(__name__)

SERVICE = "org.agscripts.PeripheralBatteryMonitor"
PATH = "/Scenes"
IFACE = "org.agscripts.Scenes"


class SceneService(QObject):
    """Exposes scene application on the session bus.

    Slots return quickly: they hand work to the section, which queues it. A
    D-Bus method that waited for the hardware would block the caller — and the
    caller is a keypress.
    """

    def __init__(self, section, parent=None):
        super().__init__(parent)
        self._section = section

    @pyqtSlot(int, result=bool)
    def Apply(self, slot: int) -> bool:
        """Apply the scene in `slot` (1-9). True when something was applied."""
        try:
            return bool(self._section.apply_scene(slot))
        except Exception:
            # Never let a bad scene propagate out over the bus.
            _log.warning("scene_apply_failed slot=%s", slot, exc_info=True)
            return False

    @pyqtSlot(result=str)
    def List(self) -> str:
        """Newline-separated "slot: description", for the CLI to show."""
        try:
            import aio_scenes

            scenes = self._section.scenes
            return "\n".join(
                f"{k}: {aio_scenes.summarise(scenes[k])}" for k in sorted(scenes)
            )
        except Exception:
            _log.warning("scene_list_failed", exc_info=True)
            return ""


def register(section, parent=None) -> SceneService | None:
    """Publish the service. None when the bus or the name is unavailable.

    A failure here costs the shortcuts and nothing else, so it is logged rather
    than raised.
    """
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        _log.warning("scene_service_no_session_bus")
        return None

    service = SceneService(section, parent)
    if not bus.registerService(SERVICE):
        # Usually a second instance; the QLockFile guard normally prevents it.
        _log.warning("scene_service_name_taken service=%s", SERVICE)
        return None
    if not bus.registerObject(PATH, IFACE, service,
                              QDBusConnection.RegisterOption.ExportAllSlots):
        _log.warning("scene_service_object_failed path=%s", PATH)
        bus.unregisterService(SERVICE)
        return None

    _log.info("scene_service_ready service=%s path=%s", SERVICE, PATH)
    return service
