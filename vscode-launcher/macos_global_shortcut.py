"""Global hotkey for macOS via Carbon's RegisterEventHotKey (ctypes).

Drop-in replacement for `global_shortcut.GlobalShortcut` on macOS: same
`pressed` / `released` signals and `is_available()` / `set_binding()` /
`unregister()` surface, so the launcher can pick a backend by platform
without other changes.

Why Carbon: `RegisterEventHotKey` registers a system-wide hotkey WITHOUT
requiring Accessibility / Input-Monitoring permission (unlike a CGEventTap),
and its `kEventHotKeyPressed` / `kEventHotKeyReleased` events give the
press+release pair the tap-to-cycle popup needs. The handler runs on the
main CFRunLoop — the same loop Qt drives on macOS — so emitting Qt signals
from it is thread-safe.

Everything degrades defensively: any ctypes/Carbon failure leaves
`is_available()` False or `set_binding()` False, exactly like the KDE
backend on a non-KDE box, so the launcher just runs without the popup
hotkey.
"""

from __future__ import annotations

import ctypes
import ctypes.util
from typing import Optional

from PyQt6.QtCore import Qt, QObject, pyqtSignal


def _fourcc(code: str) -> int:
    """Pack a 4-char OSType/code into a UInt32 (big-endian char order)."""
    return (
        (ord(code[0]) << 24)
        | (ord(code[1]) << 16)
        | (ord(code[2]) << 8)
        | ord(code[3])
    )


# --- Carbon framework + symbols (loaded lazily, defensively) ----------------

_carbon = None
try:
    _carbon_path = ctypes.util.find_library("Carbon")
    if _carbon_path:
        _carbon = ctypes.CDLL(_carbon_path)
except OSError:
    _carbon = None


class _EventTypeSpec(ctypes.Structure):
    _fields_ = [("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32)]


class _EventHotKeyID(ctypes.Structure):
    _fields_ = [("signature", ctypes.c_uint32), ("id", ctypes.c_uint32)]


# Carbon callback: OSStatus (*)(EventHandlerCallRef, EventRef, void* userData)
_HANDLER_PROC = ctypes.CFUNCTYPE(
    ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
)

_K_EVENT_CLASS_KEYBOARD = _fourcc("keyb")
_K_EVENT_HOTKEY_PRESSED = 5
_K_EVENT_HOTKEY_RELEASED = 6
_K_EVENT_PARAM_DIRECT_OBJECT = _fourcc("----")
_TYPE_EVENT_HOTKEY_ID = _fourcc("hkid")
_HOTKEY_SIGNATURE = _fourcc("vscl")
_NO_ERR = 0

# Carbon modifier masks (Events.h)
_CMD_KEY = 0x0100
_SHIFT_KEY = 0x0200
_OPTION_KEY = 0x0800
_CONTROL_KEY = 0x1000

# Qt keyboard-modifier bits (portable: Meta == Command on macOS).
_QT_MOD_MASK = (
    int(Qt.KeyboardModifier.ShiftModifier.value)
    | int(Qt.KeyboardModifier.ControlModifier.value)
    | int(Qt.KeyboardModifier.AltModifier.value)
    | int(Qt.KeyboardModifier.MetaModifier.value)
    | int(Qt.KeyboardModifier.KeypadModifier.value)
)

# Qt::Key -> Carbon virtual keycode (kVK_*). Covers the keys a user is
# realistically going to bind a launcher popup to. Unmapped keys make
# set_binding() return False (caller logs and the user picks another combo).
_VK = {
    Qt.Key.Key_A: 0, Qt.Key.Key_S: 1, Qt.Key.Key_D: 2, Qt.Key.Key_F: 3,
    Qt.Key.Key_H: 4, Qt.Key.Key_G: 5, Qt.Key.Key_Z: 6, Qt.Key.Key_X: 7,
    Qt.Key.Key_C: 8, Qt.Key.Key_V: 9, Qt.Key.Key_B: 11, Qt.Key.Key_Q: 12,
    Qt.Key.Key_W: 13, Qt.Key.Key_E: 14, Qt.Key.Key_R: 15, Qt.Key.Key_Y: 16,
    Qt.Key.Key_T: 17, Qt.Key.Key_1: 18, Qt.Key.Key_2: 19, Qt.Key.Key_3: 20,
    Qt.Key.Key_4: 21, Qt.Key.Key_6: 22, Qt.Key.Key_5: 23, Qt.Key.Key_9: 25,
    Qt.Key.Key_7: 26, Qt.Key.Key_8: 28, Qt.Key.Key_0: 29, Qt.Key.Key_O: 31,
    Qt.Key.Key_U: 32, Qt.Key.Key_I: 34, Qt.Key.Key_P: 35, Qt.Key.Key_L: 37,
    Qt.Key.Key_J: 38, Qt.Key.Key_K: 40, Qt.Key.Key_N: 45, Qt.Key.Key_M: 46,
    Qt.Key.Key_Return: 36, Qt.Key.Key_Enter: 36, Qt.Key.Key_Tab: 48,
    Qt.Key.Key_Space: 49, Qt.Key.Key_Escape: 53, Qt.Key.Key_Backtab: 48,
    Qt.Key.Key_F1: 122, Qt.Key.Key_F2: 120, Qt.Key.Key_F3: 99,
    Qt.Key.Key_F4: 118, Qt.Key.Key_F5: 96, Qt.Key.Key_F6: 97,
    Qt.Key.Key_F7: 98, Qt.Key.Key_F8: 100, Qt.Key.Key_F9: 101,
    Qt.Key.Key_F10: 109, Qt.Key.Key_F11: 103, Qt.Key.Key_F12: 111,
    Qt.Key.Key_Left: 123, Qt.Key.Key_Right: 124,
    Qt.Key.Key_Down: 125, Qt.Key.Key_Up: 126,
}


def _configure_symbols() -> bool:
    """Set argtypes/restypes so 64-bit pointers aren't truncated. Returns
    False if Carbon or any symbol is missing."""
    if _carbon is None:
        return False
    try:
        _carbon.GetApplicationEventTarget.restype = ctypes.c_void_p
        _carbon.GetApplicationEventTarget.argtypes = []
        _carbon.InstallEventHandler.restype = ctypes.c_int32
        _carbon.InstallEventHandler.argtypes = [
            ctypes.c_void_p, _HANDLER_PROC, ctypes.c_ulong,
            ctypes.POINTER(_EventTypeSpec), ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        _carbon.RegisterEventHotKey.restype = ctypes.c_int32
        _carbon.RegisterEventHotKey.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32, _EventHotKeyID,
            ctypes.c_void_p, ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        _carbon.UnregisterEventHotKey.restype = ctypes.c_int32
        _carbon.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]
        _carbon.GetEventParameter.restype = ctypes.c_int32
        _carbon.GetEventParameter.argtypes = [
            ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p,
        ]
        _carbon.GetEventKind.restype = ctypes.c_uint32
        _carbon.GetEventKind.argtypes = [ctypes.c_void_p]
        return True
    except AttributeError:
        return False


_SYMBOLS_OK = _configure_symbols()


def _carbon_modifiers(qt_mods: int) -> int:
    mask = 0
    if qt_mods & int(Qt.KeyboardModifier.ShiftModifier.value):
        mask |= _SHIFT_KEY
    if qt_mods & int(Qt.KeyboardModifier.ControlModifier.value):
        mask |= _CONTROL_KEY
    if qt_mods & int(Qt.KeyboardModifier.AltModifier.value):
        mask |= _OPTION_KEY
    if qt_mods & int(Qt.KeyboardModifier.MetaModifier.value):
        mask |= _CMD_KEY
    return mask


class MacGlobalShortcut(QObject):
    """macOS Carbon-backed global hotkey. Mirrors GlobalShortcut's API."""

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
        # The first three args are accepted for interface parity with the KDE
        # backend; Carbon doesn't use component/action identifiers.
        self._hotkey_ref: Optional[ctypes.c_void_p] = None
        self._handler_ref = ctypes.c_void_p()
        self._handler_installed = False
        # Keep strong refs so the CFUNCTYPE trampoline and the event-type array
        # aren't garbage-collected while Carbon holds pointers to them.
        self._handler_proc = _HANDLER_PROC(self._dispatch)
        self._event_types = (_EventTypeSpec * 2)(
            _EventTypeSpec(_K_EVENT_CLASS_KEYBOARD, _K_EVENT_HOTKEY_PRESSED),
            _EventTypeSpec(_K_EVENT_CLASS_KEYBOARD, _K_EVENT_HOTKEY_RELEASED),
        )

    # ------------------------------------------------------------------
    # Public API (matches global_shortcut.GlobalShortcut)
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        return bool(_SYMBOLS_OK)

    def set_binding(self, qt_key_code: Optional[int]) -> bool:
        if not _SYMBOLS_OK or qt_key_code is None:
            return False
        qt_key = qt_key_code & ~_QT_MOD_MASK
        qt_mods = qt_key_code & _QT_MOD_MASK
        try:
            vk = _VK.get(Qt.Key(qt_key))
        except ValueError:
            vk = None
        if vk is None:
            return False
        carbon_mods = _carbon_modifiers(qt_mods)

        if not self._ensure_handler():
            return False
        self._unregister_hotkey()

        hk_id = _EventHotKeyID(_HOTKEY_SIGNATURE, 1)
        ref = ctypes.c_void_p()
        target = _carbon.GetApplicationEventTarget()
        status = _carbon.RegisterEventHotKey(
            ctypes.c_uint32(vk),
            ctypes.c_uint32(carbon_mods),
            hk_id,
            target,
            0,
            ctypes.byref(ref),
        )
        if status != _NO_ERR or not ref.value:
            return False
        self._hotkey_ref = ref
        return True

    def unregister(self) -> None:
        self._unregister_hotkey()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_handler(self) -> bool:
        if self._handler_installed:
            return True
        target = _carbon.GetApplicationEventTarget()
        status = _carbon.InstallEventHandler(
            target,
            self._handler_proc,
            ctypes.c_ulong(len(self._event_types)),
            self._event_types,
            None,
            ctypes.byref(self._handler_ref),
        )
        self._handler_installed = status == _NO_ERR
        return self._handler_installed

    def _unregister_hotkey(self) -> None:
        if self._hotkey_ref is not None and self._hotkey_ref.value:
            try:
                _carbon.UnregisterEventHotKey(self._hotkey_ref)
            except Exception:
                pass
        self._hotkey_ref = None

    def _dispatch(self, _call_ref, event, _user_data) -> int:
        """Carbon event handler trampoline. Runs on the main CFRunLoop."""
        try:
            hk_id = _EventHotKeyID()
            _carbon.GetEventParameter(
                event,
                _K_EVENT_PARAM_DIRECT_OBJECT,
                _TYPE_EVENT_HOTKEY_ID,
                None,
                ctypes.sizeof(hk_id),
                None,
                ctypes.byref(hk_id),
            )
            if hk_id.signature != _HOTKEY_SIGNATURE:
                return _NO_ERR
            kind = _carbon.GetEventKind(event)
            if kind == _K_EVENT_HOTKEY_PRESSED:
                self.pressed.emit()
            elif kind == _K_EVENT_HOTKEY_RELEASED:
                self.released.emit()
        except Exception:
            # A handler must never raise back into Carbon.
            pass
        return _NO_ERR
