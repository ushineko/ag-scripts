"""
System tray icon management for VPN Toggle
"""
import logging
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PyQt6.QtGui import QIcon, QAction

from .vpn_manager import VPNManager

logger = logging.getLogger('vpn_toggle.tray')


class TrayManager:
    """Manages the system tray icon, context menu, and close-to-tray behavior."""

    def __init__(self, parent_window, vpn_manager: VPNManager,
                 monitor_checkbox, app_icon: QIcon,
                 icon_path: Optional[Path] = None):
        self.parent = parent_window
        self.vpn_manager = vpn_manager
        self.monitor_checkbox = monitor_checkbox
        self._available = False
        self.tray_icon = None
        self._show_action = None

        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.info("System tray not available, close-to-tray disabled")
            return

        self._available = True
        self.tray_icon = QSystemTrayIcon(self.parent)

        # Set tray icon from SVG path for reliable KDE/SNI rendering
        if icon_path and icon_path.exists():
            self.tray_icon.setIcon(QIcon(str(icon_path)))
        else:
            self.tray_icon.setIcon(app_icon)

        self.tray_icon.setToolTip("VPN Monitor")
        self.tray_icon.activated.connect(self._on_activated)

        # Context menu
        tray_menu = QMenu()

        self._show_action = QAction("Hide", self.parent)
        self._show_action.triggered.connect(self.toggle_window)
        tray_menu.addAction(self._show_action)

        self._monitor_action = QAction("Monitor Mode", self.parent)
        self._monitor_action.setCheckable(True)
        self._monitor_action.setChecked(monitor_checkbox.isChecked())
        self._monitor_action.toggled.connect(monitor_checkbox.setChecked)
        monitor_checkbox.toggled.connect(self._monitor_action.setChecked)
        tray_menu.addAction(self._monitor_action)

        tray_menu.addSeparator()

        quit_action = QAction("Quit", self.parent)
        quit_action.triggered.connect(self.parent.quit_application)
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

    @property
    def available(self) -> bool:
        return self._available

    def _on_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.toggle_window()

    def toggle_window(self):
        """Toggle main window show/hide."""
        if self.parent.isVisible():
            self.parent.save_geometry()
            self.parent.hide()
            self._show_action.setText("Show")
        else:
            self.parent.show()
            self.parent.raise_()
            self.parent.activateWindow()
            self._show_action.setText("Hide")

    def update_show_action_text(self, visible: bool):
        """Update the show/hide action text based on window visibility."""
        if self._show_action:
            self._show_action.setText("Hide" if visible else "Show")

    def update_tooltip(self, vpn_widgets: dict):
        """Update the tray icon tooltip with current active VPN count."""
        if not self._available:
            return
        active_count = sum(
            1 for w in vpn_widgets.values()
            if self.vpn_manager.is_vpn_active(w.vpn_name)
        )
        self.tray_icon.setToolTip(f"VPN Monitor - {active_count} VPN(s) active")

    def hide(self):
        """Hide the tray icon."""
        if self._available and self.tray_icon:
            self.tray_icon.hide()
