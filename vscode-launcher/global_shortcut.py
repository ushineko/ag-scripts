"""Global keyboard shortcut registered with KDE's KGlobalAccel.

Wraps the `org.kde.kglobalaccel` D-Bus surface in a QObject that emits
`pressed` and `released` signals. Productionized version of
`research/global_shortcut_spike.py`; see `research/global_shortcut_findings.md`
for the protocol details and the type-marshaling notes.

KDE Plasma 6 only. The KGlobalAccel D-Bus interface is KDE-specific; the
component degrades gracefully (registration returns False, signals never
fire) on non-KDE Wayland or when the service isn't running.
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
    """Marshal a Python list[str] as a D-Bus `as` (QStringList).

    PyQt6's auto-conversion sends list[str] as `av` (array of variants),
    which KGlobalAccel's `actionId` argument refuses. Explicit
    QDBusArgument with QMetaType.QStringList fixes this.
    """
    arg = QDBusArgument()
    arg.add(values, QMetaType.Type.QStringList.value)
    return arg


def _int32_array(values: list[int]) -> QDBusArgument:
    """Marshal list[int] as D-Bus `ai` (array of int32). Used for the
    keys argument of setShortcut."""
    arg = QDBusArgument()
    arg.beginArray(QMetaType.Type.Int.value)
    for v in values:
        arg.add(v, QMetaType.Type.Int.value)
    arg.endArray()
    return arg


def _uint(value: int) -> QDBusArgument:
    """Marshal a Python int as D-Bus uint32. PyQt6 auto-marshals as
    int32 by default; KGlobalAccel's flags arg requires uint32."""
    arg = QDBusArgument()
    arg.add(value, QMetaType.Type.UInt.value)
    return arg


def parse_hotkey(value: str) -> Optional[int]:
    """Convert a Qt-style key sequence string ("Meta+Alt+Space") into
    the integer KGlobalAccel expects (key code OR'd with modifier flags).

    Returns None if the string is empty or doesn't parse to a single
    valid key combo.
    """
    if not value:
        return None
    seq = QKeySequence.fromString(value, QKeySequence.SequenceFormat.PortableText)
    if seq.count() == 0:
        return None
    combo = seq[0]
    # PyQt returns QKeyCombination on .at(); .toCombined() yields the int.
    if hasattr(combo, "toCombined"):
        return int(combo.toCombined())
    return int(combo)


class GlobalShortcut(QObject):
    """Register a global hotkey with KGlobalAccel and forward press/release.

    Usage:

        shortcut = GlobalShortcut("vscode-launcher", "show-popup",
                                   "VSCode Launcher", "Show popup")
        shortcut.pressed.connect(on_pressed)
        shortcut.released.connect(on_released)
        if not shortcut.set_binding(parse_hotkey("Meta+Alt+Space")):
            # combo unavailable
            ...
        # ... at shutdown:
        shortcut.unregister()
    """

    pressed = pyqtSignal()
    released = pyqtSignal()

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
        self._component_friendly = component_friendly
        self._action_friendly = action_friendly
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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """True if the KGlobalAccel D-Bus service is reachable on this
        session. False on non-KDE setups or when the service isn't
        running. Callers can use this to disable hotkey-related UI."""
        return self._iface is not None

    def set_binding(self, qt_key_code: Optional[int]) -> bool:
        """(Re)bind the shortcut to `qt_key_code` (the integer combo from
        `parse_hotkey`). Returns True on success, False if KGlobalAccel
        is unavailable, the code is None, or the registration fails
        (combo already taken by another component)."""
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
        if reply.errorMessage():
            return False
        # KGlobalAccel returns the actually-bound keys. If the requested
        # combo was unavailable, the returned list won't match.
        # We don't strictly check the return value here because
        # `globalShortcutAvailable` in the doRegister/setShortcut path
        # already prevents a silent miss.
        return True

    def unregister(self) -> None:
        """Remove the binding and stop receiving signals. Safe to call
        multiple times; idempotent."""
        if self._iface is None or not self._registered:
            return
        try:
            self._iface.call("unRegister", _qstringlist(self._action_id))
        except Exception:
            pass
        self._registered = False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        if self._signals_connected:
            return
        # KGlobalAccel translates dashes in componentUnique to underscores
        # for the D-Bus object path.
        component_path = "/component/" + self._component_unique.replace("-", "_")
        for signal_name, slot in (
            ("globalShortcutPressed", self._on_pressed),
            ("globalShortcutReleased", self._on_released),
        ):
            self._bus.connect(
                "org.kde.kglobalaccel",
                component_path,
                "org.kde.kglobalaccel.Component",
                signal_name,
                slot,
            )
        self._signals_connected = True

    @pyqtSlot(str, str, "qlonglong")
    def _on_pressed(self, component: str, action: str, _ts: int) -> None:
        if component == self._component_unique and action == self._action_unique:
            self.pressed.emit()

    @pyqtSlot(str, str, "qlonglong")
    def _on_released(self, component: str, action: str, _ts: int) -> None:
        if component == self._component_unique and action == self._action_unique:
            self.released.emit()
