"""Global keyboard shortcut registered with KDE's KGlobalAccel.

Mirrors the vscode-launcher implementation — wraps `org.kde.kglobalaccel`
in a QObject and emits `triggered` on press. KDE Plasma 6 only; degrades
gracefully (registration returns False, signal never fires) on non-KDE
sessions or when the service isn't running.

See ag-scripts/vscode-launcher/global_shortcut.py for protocol details
and the type-marshaling notes that took a spike to figure out.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QMetaType, QObject, pyqtSignal, pyqtSlot
from PyQt6.QtDBus import QDBusArgument, QDBusConnection, QDBusInterface
from PyQt6.QtGui import QKeySequence

# setShortcut flags (KGlobalAccelD::Registration enum):
#   0x1 = SetPresent     — record this as the current binding
#   0x2 = NoAutoloading  — don't restore from saved kglobalshortcutsrc
_FLAG_SET_PRESENT = 0x1
_FLAG_NO_AUTOLOADING = 0x2


def _qstringlist(values: list[str]) -> QDBusArgument:
    """Marshal list[str] as D-Bus `as` (QStringList). PyQt6's default
    auto-conversion produces `av` which KGlobalAccel rejects."""
    arg = QDBusArgument()
    arg.add(values, QMetaType.Type.QStringList.value)
    return arg


def _int32_array(values: list[int]) -> QDBusArgument:
    arg = QDBusArgument()
    arg.beginArray(QMetaType.Type.Int.value)
    for v in values:
        arg.add(v, QMetaType.Type.Int.value)
    arg.endArray()
    return arg


def _uint(value: int) -> QDBusArgument:
    arg = QDBusArgument()
    arg.add(value, QMetaType.Type.UInt.value)
    return arg


def parse_hotkey(value: str) -> Optional[int]:
    """Convert a Qt-style key sequence string (e.g. "Meta+Alt+M") into
    the integer KGlobalAccel expects. Returns None on empty/unparseable
    input."""
    if not value:
        return None
    seq = QKeySequence.fromString(value, QKeySequence.SequenceFormat.PortableText)
    if seq.count() == 0:
        return None
    combo = seq[0]
    if hasattr(combo, "toCombined"):
        return int(combo.toCombined())
    return int(combo)


class GlobalShortcut(QObject):
    """Register a global hotkey with KGlobalAccel and emit `triggered`
    when fired. KDE Plasma 6 only."""

    triggered = pyqtSignal()

    def __init__(
        self,
        component_unique: str,
        action_unique: str,
        component_friendly: str,
        action_friendly: str,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._component_unique = component_unique
        self._action_unique = action_unique
        self._action_id = [
            component_unique,
            action_unique,
            component_friendly,
            action_friendly,
        ]
        self._registered = False
        self._signals_connected = False

        self._bus = QDBusConnection.sessionBus()
        if not self._bus.isConnected():
            self._iface: Optional[QDBusInterface] = None
            return

        iface = QDBusInterface(
            "org.kde.kglobalaccel",
            "/kglobalaccel",
            "org.kde.KGlobalAccel",
            self._bus,
        )
        self._iface = iface if iface.isValid() else None

    def is_available(self) -> bool:
        """True if KGlobalAccel is reachable. Callers can use this to
        disable hotkey-related UI on non-KDE sessions."""
        return self._iface is not None

    def set_binding(self, qt_key_code: Optional[int]) -> bool:
        """(Re)bind the shortcut. Returns False if KGlobalAccel is
        unavailable, the combo is None, or the call fails."""
        if self._iface is None or qt_key_code is None:
            return False

        if not self._registered:
            reply = self._iface.call("doRegister", _qstringlist(self._action_id))
            if reply.errorMessage():
                return False
            self._registered = True
            self._connect_signals()

        reply = self._iface.call(
            "setShortcut",
            _qstringlist(self._action_id),
            _int32_array([qt_key_code]),
            _uint(_FLAG_SET_PRESENT | _FLAG_NO_AUTOLOADING),
        )
        return not reply.errorMessage()

    def clear_binding(self) -> bool:
        """Drop the shortcut binding but keep the component registered
        so future re-binds skip the doRegister round-trip. Returns True
        on success or when the component was never registered."""
        if self._iface is None or not self._registered:
            return True
        reply = self._iface.call(
            "setShortcut",
            _qstringlist(self._action_id),
            _int32_array([]),
            _uint(_FLAG_SET_PRESENT | _FLAG_NO_AUTOLOADING),
        )
        return not reply.errorMessage()

    def unregister(self) -> None:
        """Remove the binding and stop receiving signals. Idempotent."""
        if self._iface is None or not self._registered:
            return
        try:
            self._iface.call("unRegister", _qstringlist(self._action_id))
        except Exception:
            pass
        self._registered = False

    def _connect_signals(self) -> None:
        if self._signals_connected:
            return
        # KGlobalAccel translates dashes in componentUnique to underscores
        # for the D-Bus object path.
        component_path = "/component/" + self._component_unique.replace("-", "_")
        self._bus.connect(
            "org.kde.kglobalaccel",
            component_path,
            "org.kde.kglobalaccel.Component",
            "globalShortcutPressed",
            self._on_pressed,
        )
        self._signals_connected = True

    @pyqtSlot(str, str, "qlonglong")
    def _on_pressed(self, component: str, action: str, _ts: int) -> None:
        if component == self._component_unique and action == self._action_unique:
            self.triggered.emit()
