"""QSystemTrayIcon frontend for display-mirror-toggle.

The tray icon reflects the current mirror state and exposes
toggle/enable/disable actions plus a Settings dialog where the user
configures source/replica connectors and the global hotkey.
"""

from __future__ import annotations

import logging
import shutil
import subprocess

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QAction, QIcon, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QMenu,
    QSystemTrayIcon,
    QVBoxLayout,
)

try:
    from PyQt6.QtGui import QKeySequenceEdit
except ImportError:  # pragma: no cover — Qt 6 always ships this
    from PyQt6.QtWidgets import QKeySequenceEdit  # type: ignore

from .config import ConfigManager, DEFAULT_HOTKEY
from .engine import MirrorEngine, MirrorStatus
from .global_shortcut import GlobalShortcut, parse_hotkey

logger = logging.getLogger("display_mirror_tray.tray")

SHORTCUT_COMPONENT = "display-mirror-toggle"
SHORTCUT_ACTION = "toggle-mirror"
SHORTCUT_COMPONENT_FRIENDLY = "Display Mirror Toggle"
SHORTCUT_ACTION_FRIENDLY = "Toggle display mirror"

ICON_ACTIVE = "video-display-symbolic"
ICON_INACTIVE = "video-single-display-symbolic"
ICON_ERROR = "dialog-warning"

# Fallback icons in case the symbolic ones aren't in the user's theme.
ICON_ACTIVE_FALLBACKS = ["preferences-desktop-display", "video-display"]
ICON_INACTIVE_FALLBACKS = ["preferences-desktop-display-randr", "computer"]


def _pick_icon(primary: str, fallbacks: list[str]) -> QIcon:
    icon = QIcon.fromTheme(primary)
    if not icon.isNull():
        return icon
    for name in fallbacks:
        icon = QIcon.fromTheme(name)
        if not icon.isNull():
            return icon
    return QIcon.fromTheme("preferences-desktop-display")


class SettingsDialog(QDialog):
    """Edit source/replica connectors and the global hotkey.

    Hotkey rebind is live whenever KGlobalAccel is reachable; otherwise
    the value is persisted and applies on next launch.
    """

    def __init__(
        self,
        parent=None,
        *,
        source: str,
        replica: str,
        hotkey: str,
        kglobalaccel_available: bool,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Display Mirror — Settings")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Source connector:"))
        self._source_edit = QLineEdit(source)
        self._source_edit.setPlaceholderText("e.g. HDMI-A-1")
        layout.addWidget(self._source_edit)

        layout.addWidget(QLabel("Replica connector:"))
        self._replica_edit = QLineEdit(replica)
        self._replica_edit.setPlaceholderText("e.g. DP-3")
        layout.addWidget(self._replica_edit)

        layout.addSpacing(8)
        layout.addWidget(QLabel("Global hotkey:"))
        self._key_edit = QKeySequenceEdit(QKeySequence(hotkey))
        layout.addWidget(self._key_edit)

        if kglobalaccel_available:
            hint_text = (
                "Applies immediately. Use Meta (Super), Ctrl, Alt, Shift "
                "with one non-modifier key. Clear the field to disable."
            )
        else:
            hint_text = (
                "KGlobalAccel is not reachable (non-KDE session?). "
                "The value will be saved but no hotkey will be registered."
            )
        hint = QLabel(hint_text)
        hint.setWordWrap(True)
        hint.setStyleSheet("QLabel { color: gray; }")
        layout.addWidget(hint)

        self._error_label = QLabel("")
        self._error_label.setStyleSheet("QLabel { color: #d44; }")
        self._error_label.setVisible(False)
        layout.addWidget(self._error_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_source(self) -> str:
        return self._source_edit.text().strip()

    def selected_replica(self) -> str:
        return self._replica_edit.text().strip()

    def selected_hotkey(self) -> str:
        return self._key_edit.keySequence().toString(
            QKeySequence.SequenceFormat.PortableText
        )

    def show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.setVisible(True)


class TrayApp:
    """Top-level controller. Owns the tray icon, the engine, the
    shortcut, and the poll timer. Not a QObject — pure orchestration."""

    def __init__(self, app: QApplication) -> None:
        self.app = app
        self.config = ConfigManager()
        self.engine = MirrorEngine(
            source=self.config.get("source"),
            replica=self.config.get("replica"),
        )

        self.tray = QSystemTrayIcon()
        self.tray.setToolTip("Display Mirror Toggle")

        self._action_status = QAction("Mirror: …", self.tray)
        self._action_status.setEnabled(False)

        self._action_toggle = QAction("Toggle now", self.tray)
        self._action_toggle.triggered.connect(self.on_toggle)

        self._action_enable = QAction("Enable mirror", self.tray)
        self._action_enable.triggered.connect(self.on_enable)

        self._action_disable = QAction("Disable mirror", self.tray)
        self._action_disable.triggered.connect(self.on_disable)

        self._action_settings = QAction("Settings…", self.tray)
        self._action_settings.triggered.connect(self.on_settings)

        self._action_about = QAction("About", self.tray)
        self._action_about.triggered.connect(self.on_about)

        self._action_quit = QAction("Quit", self.tray)
        self._action_quit.triggered.connect(self.on_quit)

        menu = QMenu()
        menu.addAction(self._action_status)
        menu.addSeparator()
        menu.addAction(self._action_toggle)
        menu.addAction(self._action_enable)
        menu.addAction(self._action_disable)
        menu.addSeparator()
        menu.addAction(self._action_settings)
        menu.addAction(self._action_about)
        menu.addSeparator()
        menu.addAction(self._action_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)

        self._shortcut = GlobalShortcut(
            SHORTCUT_COMPONENT,
            SHORTCUT_ACTION,
            SHORTCUT_COMPONENT_FRIENDLY,
            SHORTCUT_ACTION_FRIENDLY,
        )
        self._shortcut.triggered.connect(self.on_toggle)
        configured_hotkey = self.config.get("global_hotkey", DEFAULT_HOTKEY) or ""
        if configured_hotkey:
            self._apply_hotkey(configured_hotkey, silent=True)

        self._poll_timer = QTimer()
        self._poll_timer.setInterval(
            int(self.config.get("poll_interval_seconds", 5)) * 1000
        )
        self._poll_timer.timeout.connect(self.refresh_status)

    def start(self) -> None:
        self.refresh_status()
        self.tray.show()
        self._poll_timer.start()

    # ── State refresh ─────────────────────────────────────────────────

    def refresh_status(self) -> None:
        status = self.engine.status()
        self._update_ui(status)

    def _update_ui(self, status: MirrorStatus) -> None:
        if status.source_state == "absent" and status.replica_state == "absent":
            label = "Mirror: outputs absent"
            icon = _pick_icon(ICON_ERROR, [])
            tooltip = (
                f"Display Mirror Toggle\n"
                f"Source ({self.engine.source}) and replica "
                f"({self.engine.replica}) not detected."
            )
        elif status.active:
            label = f"Mirror: ON ({self.engine.source} → {self.engine.replica})"
            icon = _pick_icon(ICON_ACTIVE, ICON_ACTIVE_FALLBACKS)
            tooltip = (
                f"Display Mirror Toggle — ACTIVE\n"
                f"{self.engine.source} → {self.engine.replica}"
            )
        else:
            label = f"Mirror: OFF ({self.engine.source} → {self.engine.replica})"
            icon = _pick_icon(ICON_INACTIVE, ICON_INACTIVE_FALLBACKS)
            tooltip = (
                f"Display Mirror Toggle — inactive\n"
                f"{self.engine.source} → {self.engine.replica}"
            )

        self._action_status.setText(label)
        self.tray.setIcon(icon)
        self.tray.setToolTip(tooltip)

        self._action_enable.setEnabled(not status.active)
        self._action_disable.setEnabled(status.active)

    # ── Tray actions ──────────────────────────────────────────────────

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.on_toggle()

    def on_toggle(self) -> None:
        before = self.engine.status().active
        ok, msg = self.engine.toggle()
        self._post_action(ok, msg, before, "Toggle failed")

    def on_enable(self) -> None:
        before = self.engine.status().active
        ok, msg = self.engine.enable()
        self._post_action(ok, msg, before, "Enable failed")

    def on_disable(self) -> None:
        before = self.engine.status().active
        ok, msg = self.engine.disable()
        self._post_action(ok, msg, before, "Disable failed")

    def _post_action(self, ok: bool, msg: str, before_active: bool,
                     fail_title: str) -> None:
        self.refresh_status()
        if not ok:
            self.tray.showMessage(
                fail_title,
                msg or "kscreen-doctor failed.",
                QSystemTrayIcon.MessageIcon.Warning,
                4000,
            )
            return
        after_active = self.engine.status().active
        if after_active != before_active:
            self._notify_state_change(after_active)

    def _notify_state_change(self, active: bool) -> None:
        """Fire notify-send when the mirror actually switched. Idempotent
        no-ops (e.g. --enable when already active) do not notify."""
        if active:
            title = "Display Mirror — ON"
            body = f"{self.engine.source} → {self.engine.replica}"
            icon = "video-display"
        else:
            title = "Display Mirror — OFF"
            body = f"{self.engine.source} disabled"
            icon = "video-single-display"

        notify_send = shutil.which("notify-send")
        if notify_send:
            try:
                subprocess.run(
                    [notify_send,
                     "-a", "Display Mirror Toggle",
                     "-i", icon,
                     "-t", "3000",
                     title, body],
                    check=False,
                )
                return
            except OSError as e:
                logger.warning(f"notify-send failed: {e}")

        # Fallback to a tray balloon if notify-send isn't available.
        self.tray.showMessage(
            title, body, QSystemTrayIcon.MessageIcon.Information, 3000
        )

    # ── Settings ──────────────────────────────────────────────────────

    def on_settings(self) -> None:
        dialog = SettingsDialog(
            None,
            source=self.engine.source,
            replica=self.engine.replica,
            hotkey=self.config.get("global_hotkey", DEFAULT_HOTKEY) or "",
            kglobalaccel_available=self._shortcut.is_available(),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_source = dialog.selected_source() or self.engine.source
        new_replica = dialog.selected_replica() or self.engine.replica
        new_hotkey = dialog.selected_hotkey()

        # Apply hotkey first — if it fails to bind, abort so the dialog
        # state stays consistent with what's actually live.
        if new_hotkey != (self.config.get("global_hotkey") or ""):
            if not self._apply_hotkey(new_hotkey, silent=False):
                dialog.show_error(
                    f"Could not bind {new_hotkey!r}. Combo may be in use."
                )
                return

        self.engine = MirrorEngine(source=new_source, replica=new_replica)
        self.config.update(
            source=new_source, replica=new_replica, global_hotkey=new_hotkey
        )
        self.refresh_status()

    def _apply_hotkey(self, hotkey: str, *, silent: bool) -> bool:
        """Bind (or clear) the global hotkey. Returns False only when a
        non-empty hotkey was requested and the bind failed; clearing
        the hotkey or an unavailable KGlobalAccel both return True."""
        if not hotkey:
            self._shortcut.clear_binding()
            return True
        if not self._shortcut.is_available():
            if not silent:
                logger.warning(
                    "KGlobalAccel unavailable; saving hotkey but not binding."
                )
            return True
        qt_code = parse_hotkey(hotkey)
        if qt_code is None:
            return False
        return self._shortcut.set_binding(qt_code)

    # ── About / Quit ──────────────────────────────────────────────────

    def on_about(self) -> None:
        from . import __version__

        QMessageBox.information(
            None,
            "About Display Mirror Toggle",
            f"<b>Display Mirror Toggle</b> v{__version__}<br><br>"
            f"KDE Plasma 6 / Wayland system-tray frontend for "
            f"toggling a kscreen-doctor display mirror.<br><br>"
            f"Source: <code>{self.engine.source}</code><br>"
            f"Replica: <code>{self.engine.replica}</code><br>"
            f"Global hotkey: "
            f"<code>{self.config.get('global_hotkey') or '(unset)'}</code>",
        )

    def on_quit(self) -> None:
        self._poll_timer.stop()
        self._shortcut.unregister()
        self.tray.hide()
        self.app.quit()
