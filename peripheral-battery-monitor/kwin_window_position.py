"""Reliable window position save/restore on KDE Plasma Wayland.

On Wayland the usual approaches do not work:

- ``QWidget.move()`` is ignored by KWin — clients cannot self-position.
- ``QWidget.pos()`` / ``windowHandle().geometry()`` return a bogus value (a
  screen-origin-ish number, not the true position). The compositor is the only
  source of truth.
- ``QMoveEvent`` does not fire for compositor-driven moves (interactive drags via
  ``startSystemMove()`` included), so it cannot be used as a save trigger.
- KWin ``position`` window rules only select the screen and snap to its origin;
  they do not honor exact intra-screen coordinates.
- Native session restore (``xx-session-management-v1``) needs Qt 6.12+, which is
  not yet packaged, and is opt-in/experimental.

The mechanism that does work is driving KWin's Scripting D-Bus API in-process:

- **Restore**: a KWin JS script sets ``window.frameGeometry`` to the saved x/y.
- **Report**: a KWin JS script reads the true ``frameGeometry`` and calls back
  into this process over D-Bus (``callDBus``) with the coordinates, which the
  caller persists. A loaded KWin script executes only once, so each report is a
  fresh load/run/unload cycle (cheap in-process D-Bus calls).

Windows are matched by ``resourceClass``, i.e. the Wayland ``app_id`` the app sets
via ``QGuiApplication.setDesktopFileName(app_id)``.

This is the repo-wide reference approach for custom apps until Qt 6.12 session
support lands. See CLAUDE.md "KDE Plasma / Wayland Patterns".
"""
import os
import tempfile

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from PyQt6.QtDBus import QDBusConnection, QDBusMessage

_DBUS_IFACE = "org.agscripts.WindowPosition"
_DBUS_PATH = "/WindowPosition"

_KWIN_SERVICE = "org.kde.KWin"
_KWIN_SCRIPTING_PATH = "/Scripting"
_KWIN_SCRIPTING_IFACE = "org.kde.kwin.Scripting"
_KWIN_SCRIPT_IFACE = "org.kde.kwin.Script"


def _sanitize(app_id: str) -> str:
    """Turn an app_id into a valid D-Bus service-name segment."""
    return "".join(c if (c.isalnum() or c == "_") else "_" for c in app_id)


class KWinWindowPosition(QObject):
    """Save/restore a window's on-screen position via the KWin Scripting API.

    Emits ``geometryReported(x, y)`` when a report round-trip returns the window's
    true position. The caller connects that signal to its persistence.
    """

    geometryReported = pyqtSignal(int, int)

    def __init__(self, app_id: str, parent=None):
        super().__init__(parent)
        self.app_id = app_id
        self._service = f"org.agscripts.{_sanitize(app_id)}"
        self._bus = QDBusConnection.sessionBus()
        self._available = self._register_dbus() and self._kwin_present()

    # -- public API ---------------------------------------------------------
    def is_available(self) -> bool:
        """True when running under KWin with the scripting bridge reachable."""
        return self._available

    def restore(self, x: int, y: int) -> None:
        """Move the app's window to (x, y). No-op if unavailable."""
        if self._available:
            self._run_script(self._move_js(int(x), int(y)))

    def request_report(self) -> None:
        """Ask KWin for the window's true position.

        The result is delivered asynchronously via ``geometryReported``.
        """
        if self._available:
            self._run_script(self._report_js())

    # -- D-Bus receive side -------------------------------------------------
    def _register_dbus(self) -> bool:
        if not self._bus.isConnected():
            return False
        # A service-name clash means another instance owns it; single-instance
        # locking upstream should prevent that, but tolerate failure gracefully.
        self._bus.registerService(self._service)
        return self._bus.registerObject(
            _DBUS_PATH,
            _DBUS_IFACE,
            self,
            QDBusConnection.RegisterOption.ExportAllSlots,
        )

    @pyqtSlot(int, int)
    def ReportGeometry(self, x: int, y: int) -> None:
        """D-Bus method invoked by the KWin report script."""
        self.geometryReported.emit(x, y)

    def _kwin_present(self) -> bool:
        iface = self._bus.interface()
        if iface is None:
            return False
        reply = iface.isServiceRegistered(_KWIN_SERVICE)
        return bool(reply.value()) if hasattr(reply, "value") else bool(reply)

    # -- KWin scripting send side (in-process, no subprocess) ---------------
    def _kwin_call(self, path, iface, method, *args):
        msg = QDBusMessage.createMethodCall(_KWIN_SERVICE, path, iface, method)
        if args:
            msg.setArguments(list(args))
        reply = self._bus.call(msg)
        if reply.type() == QDBusMessage.MessageType.ReplyMessage:
            out = reply.arguments()
            return out[0] if out else None
        return None

    def _run_script(self, js: str) -> None:
        """Load a KWin script from an in-memory string, run it once, unload it.

        ``loadScript`` requires a file path, so the JS is written to a private
        temp file for the duration of the load. A loaded script runs only once,
        hence the load/run/unload per call.
        """
        path = None
        try:
            fd, path = tempfile.mkstemp(suffix=".js", prefix="kwinpos_")
            with os.fdopen(fd, "w") as f:
                f.write(js)
            sid = self._kwin_call(_KWIN_SCRIPTING_PATH, _KWIN_SCRIPTING_IFACE,
                                  "loadScript", path)
            if sid is None:
                return
            obj = f"{_KWIN_SCRIPTING_PATH}/Script{int(sid)}"
            self._kwin_call(obj, _KWIN_SCRIPT_IFACE, "run")
            self._kwin_call(_KWIN_SCRIPTING_PATH, _KWIN_SCRIPTING_IFACE,
                            "unloadScript", path)
        except (OSError, ValueError, TypeError):
            pass
        finally:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass

    def _move_js(self, x: int, y: int) -> str:
        return f"""
const list = (typeof workspace.windowList === "function")
    ? workspace.windowList() : workspace.stackingOrder;
for (let i = 0; i < list.length; i++) {{
    const c = list[i];
    if (c.resourceClass == "{self.app_id}") {{
        const g = c.frameGeometry;
        c.frameGeometry = {{ x: {x}, y: {y}, width: g.width, height: g.height }};
        break;
    }}
}}
"""

    def _report_js(self) -> str:
        return f"""
const list = (typeof workspace.windowList === "function")
    ? workspace.windowList() : workspace.stackingOrder;
for (let i = 0; i < list.length; i++) {{
    const c = list[i];
    if (c.resourceClass == "{self.app_id}") {{
        const g = c.frameGeometry;
        callDBus("{self._service}", "{_DBUS_PATH}", "{_DBUS_IFACE}",
                 "ReportGeometry", Math.round(g.x), Math.round(g.y));
        break;
    }}
}}
"""
