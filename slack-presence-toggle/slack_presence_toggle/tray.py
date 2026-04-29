from __future__ import annotations

import logging
from dataclasses import replace
from typing import Optional

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QInputDialog, QMenu, QSystemTrayIcon

from .config import Config
from .slack_client import ApiHealth, PresenceState, ProfileStatus
from .state_machine import FocusState, StateSnapshot

log = logging.getLogger(__name__)

# Icon palette
COLOR_GRAY = QColor("#888888")
COLOR_GREEN = QColor("#2ecc71")
COLOR_YELLOW = QColor("#f1c40f")
COLOR_RED = QColor("#e74c3c")


class TrayApp(QObject):
    """System-tray UI. Stateless on its own; the main app feeds it updates.

    Signals out:
      enable_toggle_requested(bool)  — user wants enabled state to change to bool
      reload_token_requested()       — user clicked Reload token from file
      config_change_requested(str, object)  — user changed a config field
      quit_requested()               — user clicked Quit
    """

    enable_toggle_requested = pyqtSignal(bool)
    reload_token_requested = pyqtSignal()
    reload_kwin_script_requested = pyqtSignal()
    config_change_requested = pyqtSignal(str, object)
    quit_requested = pyqtSignal()

    def __init__(self, *, config: Config, parent: QObject | None = None):
        super().__init__(parent)
        self._config = config

        self._tray = QSystemTrayIcon(parent=self)
        self._menu = QMenu()
        self._build_menu()
        self._tray.setContextMenu(self._menu)
        # Refresh display before user sees the menu so it's never stale.
        self._menu.aboutToShow.connect(self._on_menu_about_to_show)

        # Cached state used to render the menu / icon.
        self._snapshot: StateSnapshot | None = None
        self._presence: PresenceState | None = None
        self._profile: ProfileStatus | None = None
        self._health: ApiHealth = ApiHealth.success()
        self._user_label: str | None = None

        self._refresh_about_to_show: callable | None = None

    # ------------------------------------------------------------------ life
    def show(self) -> None:
        self._tray.show()
        self._refresh_icon_and_tooltip()

    def hide(self) -> None:
        self._tray.hide()

    @property
    def system_tray(self) -> QSystemTrayIcon:
        return self._tray

    # --------------------------------------------------------------- updates
    def update_config(self, config: Config) -> None:
        self._config = config
        self._refresh_menu_text()

    def update_state(
        self,
        *,
        snapshot: StateSnapshot,
        presence: PresenceState | None,
        profile: ProfileStatus | None,
    ) -> None:
        self._snapshot = snapshot
        self._presence = presence
        self._profile = profile
        self._refresh_menu_text()
        self._refresh_icon_and_tooltip()

    def update_health(self, health: ApiHealth) -> None:
        self._health = health
        self._refresh_menu_text()
        self._refresh_icon_and_tooltip()

    def update_user(self, user: str, team: str) -> None:
        self._user_label = f"{user} @ {team}"
        self._refresh_menu_text()

    def set_pre_show_refresh(self, callback) -> None:
        """Caller's hook to refresh status data right before the menu is shown."""
        self._refresh_about_to_show = callback

    # --------------------------------------------------------- menu building
    def _build_menu(self) -> None:
        # Header: status (disabled action used as label)
        self._action_status = QAction("Slack: ?")
        self._action_status.setEnabled(False)
        self._menu.addAction(self._action_status)

        self._action_health = QAction("API: connected")
        self._action_health.setEnabled(False)
        self._menu.addAction(self._action_health)

        self._action_user = QAction("")
        self._action_user.setEnabled(False)
        self._action_user.setVisible(False)
        self._menu.addAction(self._action_user)

        self._menu.addSeparator()

        self._action_toggle = QAction("Disable auto-presence")
        self._action_toggle.triggered.connect(self._on_toggle_clicked)
        self._menu.addAction(self._action_toggle)

        self._action_reload_token = QAction("Reload token from file")
        self._action_reload_token.triggered.connect(self.reload_token_requested.emit)
        self._action_reload_token.setVisible(False)  # only show on auth failure
        self._menu.addAction(self._action_reload_token)

        self._action_reload_kwin = QAction("Reload KWin script")
        self._action_reload_kwin.triggered.connect(self.reload_kwin_script_requested.emit)
        self._menu.addAction(self._action_reload_kwin)

        self._menu.addSeparator()

        self._configure_menu = QMenu("Configure")
        self._menu.addMenu(self._configure_menu)

        self._action_token_file = QAction("Token file...")
        self._action_token_file.triggered.connect(self._prompt_token_file)
        self._configure_menu.addAction(self._action_token_file)

        self._action_grace = QAction("Grace period...")
        self._action_grace.triggered.connect(self._prompt_grace)
        self._configure_menu.addAction(self._action_grace)

        self._action_status_text = QAction("Status text...")
        self._action_status_text.triggered.connect(self._prompt_status_text)
        self._configure_menu.addAction(self._action_status_text)

        self._action_status_emoji = QAction("Status emoji...")
        self._action_status_emoji.triggered.connect(self._prompt_status_emoji)
        self._configure_menu.addAction(self._action_status_emoji)

        self._action_safety_buffer = QAction("Status safety buffer...")
        self._action_safety_buffer.triggered.connect(self._prompt_safety_buffer)
        self._configure_menu.addAction(self._action_safety_buffer)

        self._menu.addSeparator()

        self._action_about = QAction("About")
        self._action_about.triggered.connect(self._show_about)
        self._menu.addAction(self._action_about)

        self._action_quit = QAction("Quit")
        self._action_quit.triggered.connect(self.quit_requested.emit)
        self._menu.addAction(self._action_quit)

    # ----------------------------------------------------- menu text refresh
    def _refresh_menu_text(self) -> None:
        # Status header
        self._action_status.setText(f"Slack: {self._status_string()}")

        # Health header
        self._action_health.setText(f"API: {self._health_string()}")

        # User label (only show once we know it)
        if self._user_label:
            self._action_user.setVisible(True)
            self._action_user.setText(self._user_label)

        # Enable toggle text
        if self._snapshot is not None:
            if self._snapshot.enabled:
                self._action_toggle.setText("Disable auto-presence")
            else:
                self._action_toggle.setText("Enable auto-presence")

        # Reload token visibility
        auth_failed = self._health.error in ("invalid_auth", "token_revoked", "account_inactive", "missing_scope")
        self._action_reload_token.setVisible(auth_failed)

        # Configure submenu — show current values inline so the user knows
        # what they're changing.
        self._action_grace.setText(f"Grace period... (currently {self._config.grace_seconds}s)")
        self._action_status_text.setText(f"Status text... (currently {self._config.status_text!r})")
        self._action_status_emoji.setText(f"Status emoji... (currently {self._config.status_emoji!r})")
        self._action_safety_buffer.setText(
            f"Status safety buffer... (currently {self._config.status_safety_buffer_seconds}s)"
        )

    def _status_string(self) -> str:
        if self._presence is None or self._snapshot is None:
            return "Unknown"
        if self._presence.presence == "active":
            return "Active"
        # presence == "away"
        if self._presence.manual_away:
            if self._snapshot.we_forced_away and self._profile and self._profile.text == self._config.status_text:
                return f'Away (forced by us) — "{self._profile.text}"'
            return "Away (manual)"
        if self._presence.auto_away:
            return "Away (Slack idle)"
        return "Away"

    def _health_string(self) -> str:
        if self._health.ok:
            return "connected"
        e = self._health.error or "unknown"
        if e == "missing_scope":
            return f"token missing scope: {self._health.needed_scope}"
        if e == "rate_limited":
            return f"rate limited (retry in {self._health.retry_after_seconds}s)"
        if e == "network":
            return "network error"
        if e == "server_error":
            return "Slack server error"
        return e

    # ----------------------------------------------------------- icon render
    def _refresh_icon_and_tooltip(self) -> None:
        color = self._icon_color()
        warning = (not self._health.ok) and self._health.error not in (
            "invalid_auth", "token_revoked", "account_inactive", "missing_scope"
        )
        self._tray.setIcon(_make_icon(color, warning_overlay=warning))
        self._tray.setToolTip(f"Slack Presence Toggle\n{self._action_status.text()}\n{self._action_health.text()}")

    def _icon_color(self) -> QColor:
        if self._snapshot is None:
            return COLOR_GRAY
        if not self._snapshot.enabled:
            return COLOR_GRAY
        if self._health.error in ("invalid_auth", "token_revoked", "account_inactive", "missing_scope"):
            return COLOR_RED
        if self._presence is None:
            return COLOR_GRAY
        if self._presence.presence == "active":
            return COLOR_GREEN
        return COLOR_YELLOW

    # ---------------------------------------------------------- menu actions
    def _on_toggle_clicked(self) -> None:
        if self._snapshot is None:
            return
        self.enable_toggle_requested.emit(not self._snapshot.enabled)

    def _on_menu_about_to_show(self) -> None:
        if self._refresh_about_to_show:
            self._refresh_about_to_show()

    def _prompt_token_file(self) -> None:
        text, ok = QInputDialog.getText(
            None, "Token file path", "Path to file containing the xoxp- token:",
            text=self._config.token_file,
        )
        if ok and text:
            self.config_change_requested.emit("token_file", text)

    def _prompt_grace(self) -> None:
        n, ok = QInputDialog.getInt(
            None, "Grace period",
            "Seconds focus must stay away from Slack before forcing away (0–600):",
            value=self._config.grace_seconds, min=0, max=600,
        )
        if ok:
            self.config_change_requested.emit("grace_seconds", n)

    def _prompt_status_text(self) -> None:
        text, ok = QInputDialog.getText(
            None, "Status text",
            "Custom status text to display while focused away from Slack:",
            text=self._config.status_text,
        )
        if ok:
            self.config_change_requested.emit("status_text", text)

    def _prompt_status_emoji(self) -> None:
        text, ok = QInputDialog.getText(
            None, "Status emoji",
            "Slack emoji shortcode (e.g. :dart:) or empty:",
            text=self._config.status_emoji,
        )
        if ok:
            self.config_change_requested.emit("status_emoji", text)

    def _prompt_safety_buffer(self) -> None:
        n, ok = QInputDialog.getInt(
            None, "Status safety buffer",
            "Seconds before Slack auto-clears our status if the utility crashes (60–86400):",
            value=self._config.status_safety_buffer_seconds, min=60, max=86400,
        )
        if ok:
            self.config_change_requested.emit("status_safety_buffer_seconds", n)

    def _show_about(self) -> None:
        from .version import __version__
        about_lines = [
            f"Slack Presence Toggle v{__version__}",
            "",
            "Auto-toggles Slack presence based on Slack window focus.",
            "https://github.com/ushineko/ag-scripts",
        ]
        # Use a notification rather than a modal dialog to stay tray-app-y.
        from .notifications import notify, Urgency
        notify("About", "\n".join(about_lines), urgency=Urgency.LOW, tray=self._tray)


def _make_icon(color: QColor, *, warning_overlay: bool = False) -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    # Background circle
    painter.setBrush(color)
    painter.setPen(QColor("#222222"))
    painter.drawEllipse(2, 2, 60, 60)
    # "S" letter
    painter.setPen(QColor("white"))
    font = QFont()
    font.setBold(True)
    font.setPointSize(36)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "S")
    if warning_overlay:
        # Small yellow triangle in the bottom-right
        painter.setBrush(QColor("#f39c12"))
        painter.setPen(QColor("#222222"))
        points = [
            (44, 64),
            (64, 64),
            (54, 44),
        ]
        from PyQt6.QtCore import QPoint
        from PyQt6.QtGui import QPolygon
        painter.drawPolygon(QPolygon([QPoint(x, y) for x, y in points]))
        painter.setPen(QColor("white"))
        font2 = QFont()
        font2.setBold(True)
        font2.setPointSize(10)
        painter.setFont(font2)
        painter.drawText(48, 60, "!")
    painter.end()
    return QIcon(pixmap)
