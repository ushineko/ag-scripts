"""
Main window for VPN Toggle
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QCheckBox, QTextEdit,
    QScrollArea, QGroupBox, QDialog, QSplitter,
    QMessageBox, QApplication,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QTextCursor, QIcon

from .config import ConfigManager
from .vpn_manager import VPNManager
from .monitor import MonitorThread
from .metrics import MetricsCollector, DataPoint, AssertDetail
from .graph import MetricsGraphWidget
from .widgets import VPNWidget
from .dialogs import SettingsDialog
from .tray import TrayManager

logger = logging.getLogger('vpn_toggle.gui')


class VPNToggleMainWindow(QMainWindow):
    """Main window for VPN Toggle application"""

    MAX_LOG_LINES = 500

    def __init__(self, config_manager: ConfigManager, vpn_manager: VPNManager,
                 app_icon: Optional[QIcon] = None, icon_path: Optional[Path] = None):
        super().__init__()
        self.config_manager = config_manager
        self.vpn_manager = vpn_manager
        self.monitor_thread = None
        self.vpn_widgets: dict[str, VPNWidget] = {}
        self.metrics_collector = MetricsCollector()
        self.graph_widget = None
        self._app_icon = app_icon or QIcon()
        self._icon_path = icon_path
        self._quitting = False

        from . import __version__
        self.setWindowTitle(f"VPN Monitor v{__version__}")
        self.setup_ui()
        self.setup_monitor()
        self.tray = TrayManager(self, vpn_manager, self.monitor_checkbox,
                                self._app_icon, self._icon_path)
        self.restore_geometry()
        self._restore_vpn_connections()

        # Setup status update timer
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_all_vpn_status)
        self.status_timer.start(5000)

        # 1-second timer for real-time connection time counters
        self.connection_time_timer = QTimer()
        self.connection_time_timer.timeout.connect(self._update_connection_times)
        self.connection_time_timer.start(1000)

    def setup_ui(self):
        """Setup the main window UI with horizontal split (VPN list | Graph)"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()

        # Top control bar
        control_layout = QHBoxLayout()

        self.monitor_checkbox = QCheckBox("Monitor Mode")
        monitor_settings = self.config_manager.get_monitor_settings()
        self.monitor_checkbox.setChecked(monitor_settings.get('enabled', False))
        self.monitor_checkbox.stateChanged.connect(self.on_monitor_toggled)
        control_layout.addWidget(self.monitor_checkbox)

        control_layout.addStretch()

        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self.on_settings_clicked)
        control_layout.addWidget(settings_btn)

        quit_btn = QPushButton("Quit")
        quit_btn.clicked.connect(self.quit_application)
        control_layout.addWidget(quit_btn)

        main_layout.addLayout(control_layout)

        # Horizontal splitter: VPN list (left) | Graph (right)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel: VPN Connections
        vpn_group = QGroupBox("VPN Connections")
        vpn_layout = QVBoxLayout()

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_widget = QWidget()
        self.vpn_list_layout = QVBoxLayout()

        self.populate_vpn_list()

        scroll_widget.setLayout(self.vpn_list_layout)
        scroll_area.setWidget(scroll_widget)
        vpn_layout.addWidget(scroll_area)

        vpn_group.setLayout(vpn_layout)
        self.splitter.addWidget(vpn_group)

        # Right panel: Metrics graph
        metrics_group = QGroupBox("Metrics")
        metrics_layout = QVBoxLayout()

        self.graph_widget = MetricsGraphWidget(self.metrics_collector)
        metrics_layout.addWidget(self.graph_widget)

        metrics_group.setLayout(metrics_layout)
        self.splitter.addWidget(metrics_group)

        self.splitter.setSizes([440, 660])

        main_layout.addWidget(self.splitter)

        # Activity log (full width, below splitter)
        log_group = QGroupBox("Activity Log")
        log_layout = QVBoxLayout()

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        log_layout.addWidget(self.log_text)

        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)

        central_widget.setLayout(main_layout)

    def populate_vpn_list(self):
        """Populate the VPN list from available VPNs, sorted by saved order."""
        vpns = self.vpn_manager.list_vpns()

        if not vpns:
            label = QLabel("No VPN connections found")
            label.setStyleSheet("color: gray; padding: 20px;")
            self.vpn_list_layout.addWidget(label)
            return

        # Sort by saved order; unknown VPNs go to the end
        saved_order = self.config_manager.get_config().get('vpn_order', [])
        order_map = {name: i for i, name in enumerate(saved_order)}
        vpns.sort(key=lambda v: order_map.get(v.name, len(saved_order)))

        # Track ordered names for button state
        self._vpn_order = [vpn.name for vpn in vpns]

        for vpn in vpns:
            vpn_config = self.config_manager.get_vpn_config(vpn.name)

            display_name = vpn.name
            if vpn_config:
                display_name = vpn_config.get('display_name', vpn.name)

            widget = VPNWidget(vpn.name, display_name, self.vpn_manager,
                             self.config_manager, self.monitor_thread,
                             self.metrics_collector,
                             backend_type=vpn.connection_type)
            widget.move_requested.connect(self._on_vpn_move)
            self.vpn_widgets[vpn.name] = widget
            self.vpn_list_layout.addWidget(widget)

        self.vpn_list_layout.addStretch()
        self._update_move_buttons()

    def _on_vpn_move(self, vpn_name: str, direction: int):
        """Handle a VPN card move request (direction: -1=up, +1=down)."""
        idx = self._vpn_order.index(vpn_name)
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(self._vpn_order):
            return

        # Swap in order list
        self._vpn_order[idx], self._vpn_order[new_idx] = (
            self._vpn_order[new_idx], self._vpn_order[idx]
        )

        # Rebuild the layout (remove all widgets, re-add in new order)
        # Remove stretch item too
        while self.vpn_list_layout.count():
            item = self.vpn_list_layout.takeAt(0)
            # Don't delete the widgets, just remove from layout
            if item.widget():
                item.widget().setParent(None)

        for name in self._vpn_order:
            self.vpn_list_layout.addWidget(self.vpn_widgets[name])
        self.vpn_list_layout.addStretch()

        self._update_move_buttons()
        self._save_vpn_order()

    def _update_move_buttons(self):
        """Enable/disable up/down buttons based on position."""
        for i, name in enumerate(self._vpn_order):
            widget = self.vpn_widgets[name]
            widget.move_up_btn.setEnabled(i > 0)
            widget.move_down_btn.setEnabled(i < len(self._vpn_order) - 1)

    def _save_vpn_order(self):
        """Persist the current VPN order to config."""
        config = self.config_manager.get_config()
        config['vpn_order'] = list(self._vpn_order)
        self.config_manager.config = config
        self.config_manager.save_config()

    def setup_monitor(self):
        """Setup the monitor thread"""
        self.monitor_thread = MonitorThread(self.config_manager, self.vpn_manager)

        self.monitor_thread.log_message.connect(self.append_log)
        self.monitor_thread.assert_result.connect(self.on_assert_result)
        self.monitor_thread.vpn_disabled.connect(self.on_vpn_disabled)
        self.monitor_thread.check_completed.connect(self.on_check_completed)

        for widget in self.vpn_widgets.values():
            widget.monitor_thread = self.monitor_thread
            widget.metrics_collector = self.metrics_collector

        monitor_settings = self.config_manager.get_monitor_settings()
        if monitor_settings.get('enabled', False):
            self.monitor_thread.enable_monitoring()
            self.monitor_thread.start()
            self.append_log("Monitor thread started")

    def _restore_vpn_connections(self):
        """Restore VPN connections from the saved restore list on startup."""
        import threading

        startup = self.config_manager.get_startup_settings()
        if not startup.get('restore_connections', False):
            return

        restore_list = self.config_manager.get_restore_vpns()
        if not restore_list:
            return

        self.append_log(f"Restoring {len(restore_list)} VPN connection(s)...")

        def restore_worker():
            for vpn_name in restore_list:
                if self.vpn_manager.is_vpn_active(vpn_name):
                    QTimer.singleShot(0, lambda n=vpn_name: self.append_log(
                        f"Restoring VPN: {n}... Already active"))
                    continue

                success, message = self.vpn_manager.connect_vpn(vpn_name)
                if success:
                    QTimer.singleShot(0, lambda n=vpn_name: self.append_log(
                        f"Restoring VPN: {n}... Connected"))
                    if self.monitor_thread:
                        self.monitor_thread.reset_vpn_state(vpn_name)
                else:
                    QTimer.singleShot(0, lambda n=vpn_name, m=message: self.append_log(
                        f"Restoring VPN: {n}... Failed: {m}"))

        threading.Thread(target=restore_worker, daemon=True).start()

    def quit_application(self):
        """Fully quit the application."""
        self._quitting = True
        self.save_geometry()

        if self.monitor_thread and self.monitor_thread.isRunning():
            self.monitor_thread.stop()
            logger.info("Monitor thread stopped")

        self.tray.hide()
        QApplication.quit()

    def on_monitor_toggled(self, state):
        """Handle monitor toggle"""
        enabled = state == Qt.CheckState.Checked.value

        if enabled:
            if not self.monitor_thread.isRunning():
                self.monitor_thread.start()
            self.monitor_thread.enable_monitoring()
            self.append_log("Monitoring enabled")
        else:
            self.monitor_thread.disable_monitoring()
            self.append_log("Monitoring disabled")

    def on_settings_clicked(self):
        """Handle settings button click"""
        dialog = SettingsDialog(self.config_manager, self)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            settings = dialog.get_settings()
            self.config_manager.update_monitor_settings(**settings)

            startup_settings = dialog.get_startup_settings()
            self.config_manager.update_startup_settings(**startup_settings)
            dialog.apply_autostart()

            self.append_log(f"Settings updated")

            if self.monitor_thread and self.monitor_thread.isRunning():
                self.monitor_thread.notify_config_changed()

    def on_assert_result(self, vpn_name: str, success: bool, message: str):
        """Handle assert result signal"""
        status = "PASSED" if success else "FAILED"
        display_name = vpn_name
        if vpn_name in self.vpn_widgets:
            display_name = self.vpn_widgets[vpn_name].display_name

        self.append_log(f"{display_name}: {message} [{status}]")

        if vpn_name in self.vpn_widgets:
            self.vpn_widgets[vpn_name].update_status()

    def on_vpn_disabled(self, vpn_name: str, reason: str):
        """Handle VPN disabled signal"""
        QMessageBox.warning(
            self,
            "VPN Disabled",
            f"VPN '{vpn_name}' has been disabled due to:\n{reason}\n\n"
            "Please check the VPN configuration and re-enable monitoring when ready."
        )

        if vpn_name in self.vpn_widgets:
            self.vpn_widgets[vpn_name].update_status()

    def on_check_completed(self, vpn_name: str, data_point_dict: dict):
        """Handle check_completed signal — record metrics and update graph."""
        assert_details = [
            AssertDetail(
                type=a['type'],
                latency_ms=a['latency_ms'],
                success=a['success'],
            )
            for a in data_point_dict.get('assert_details', [])
        ]
        data_point = DataPoint(
            timestamp=data_point_dict['timestamp'],
            vpn_name=data_point_dict['vpn_name'],
            latency_ms=data_point_dict['latency_ms'],
            success=data_point_dict['success'],
            bounce_triggered=data_point_dict['bounce_triggered'],
            assert_details=assert_details,
        )

        self.metrics_collector.record(data_point)

        if self.graph_widget:
            self.graph_widget.add_data_point(data_point)

        if vpn_name in self.vpn_widgets:
            self.vpn_widgets[vpn_name].update_status()

    def _update_connection_times(self):
        """Tick all VPN connection time counters (called every second)."""
        for widget in self.vpn_widgets.values():
            widget.update_connection_time()

    def update_all_vpn_status(self):
        """Update status for all VPN widgets"""
        for widget in self.vpn_widgets.values():
            widget.update_status()
        self.tray.update_tooltip(self.vpn_widgets)

    def append_log(self, message: str):
        """Append message to activity log, pruning oldest lines beyond MAX_LOG_LINES"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")

        doc = self.log_text.document()
        excess = doc.blockCount() - self.MAX_LOG_LINES
        if excess > 0:
            cursor = QTextCursor(doc)
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            for _ in range(excess):
                cursor.movePosition(QTextCursor.MoveOperation.Down, QTextCursor.MoveMode.KeepAnchor)
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock, QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            cursor.deleteChar()

        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def restore_geometry(self):
        """Restore window geometry from config.

        Uses kdotool windowmove/windowsize on KDE Wayland since
        QWidget.move() is ignored by the compositor.
        """
        geometry = self.config_manager.get_window_geometry()

        if geometry['width'] and geometry['height']:
            self.resize(geometry['width'], geometry['height'])

        # Defer kdotool move until after the window is shown and has a window ID
        if geometry['x'] is not None and geometry['y'] is not None:
            self._pending_geometry = geometry
            QTimer.singleShot(200, self._apply_kdotool_geometry)

    def _apply_kdotool_geometry(self):
        """Move window to saved position via kdotool (KDE Wayland)."""
        geometry = getattr(self, '_pending_geometry', None)
        if not geometry:
            return

        import subprocess
        try:
            # Find our window by title
            result = subprocess.run(
                ['kdotool', 'search', '--name', self.windowTitle()],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode != 0 or not result.stdout.strip():
                return

            win_id = result.stdout.strip().splitlines()[0]

            subprocess.run(
                ['kdotool', 'windowmove', win_id,
                 str(geometry['x']), str(geometry['y'])],
                capture_output=True, timeout=2
            )
            subprocess.run(
                ['kdotool', 'windowsize', win_id,
                 str(geometry['width']), str(geometry['height'])],
                capture_output=True, timeout=2
            )
            logger.debug(f"Restored geometry via kdotool: {geometry}")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.debug("kdotool not available, skipping window positioning")
        finally:
            self._pending_geometry = None

    def save_geometry(self):
        """Save window geometry to config.

        Uses kdotool getwindowgeometry for accurate position on KDE Wayland,
        falling back to Qt's geometry() if kdotool isn't available.
        """
        import subprocess

        x, y, width, height = None, None, None, None

        try:
            result = subprocess.run(
                ['kdotool', 'search', '--name', self.windowTitle()],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0 and result.stdout.strip():
                win_id = result.stdout.strip().splitlines()[0]
                geo_result = subprocess.run(
                    ['kdotool', 'getwindowgeometry', win_id],
                    capture_output=True, text=True, timeout=2
                )
                if geo_result.returncode == 0:
                    for line in geo_result.stdout.splitlines():
                        if 'Position:' in line:
                            pos = line.split('Position:')[1].strip()
                            parts = pos.split(',')
                            if len(parts) == 2:
                                x = int(float(parts[0]))
                                y = int(float(parts[1]))
                        elif 'Geometry:' in line:
                            size = line.split('Geometry:')[1].strip()
                            parts = size.split('x')
                            if len(parts) == 2:
                                width = int(float(parts[0]))
                                height = int(float(parts[1]))
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
            pass

        # Fallback to Qt geometry
        if x is None:
            geo = self.geometry()
            x, y = geo.x(), geo.y()
            width, height = geo.width(), geo.height()

        self.config_manager.update_window_geometry(x, y, width, height)

    def closeEvent(self, event):
        """Handle window close event — hide to tray if available, otherwise quit."""
        if self.tray.available and not self._quitting:
            self.save_geometry()
            self.hide()
            self.tray.update_show_action_text(False)
            event.ignore()
        else:
            self.save_geometry()
            if self.monitor_thread and self.monitor_thread.isRunning():
                self.monitor_thread.stop()
                logger.info("Monitor thread stopped")
            self.tray.hide()
            event.accept()
