"""
VPN card widget for displaying a single VPN connection
"""
import logging
import threading
from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QDialog,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import QTimer, pyqtSignal

from .config import ConfigManager
from .vpn_manager import VPNManager
from .monitor import MonitorController
from .metrics import MetricsCollector

logger = logging.getLogger('vpn_toggle.widgets')


class VPNWidget(QFrame):
    """Widget representing a single VPN in the list"""

    move_requested = pyqtSignal(str, int)  # vpn_name, direction (-1=up, +1=down)

    def __init__(self, vpn_name: str, display_name: str, vpn_manager: VPNManager,
                 config_manager: ConfigManager, monitor_thread: Optional[MonitorController] = None,
                 metrics_collector: Optional[MetricsCollector] = None,
                 backend_type: str = "vpn"):
        super().__init__()
        self.vpn_name = vpn_name
        self.display_name = display_name
        self.vpn_manager = vpn_manager
        self.config_manager = config_manager
        self.monitor_thread = monitor_thread
        self.metrics_collector = metrics_collector
        self.backend_type = backend_type

        self._connected_since: Optional[datetime] = None

        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        self.setup_ui()
        self.update_status()

    def setup_ui(self):
        """Setup the widget UI"""
        layout = QVBoxLayout()

        # Header with VPN name and status
        header_layout = QHBoxLayout()

        # Status indicator (colored dot)
        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet("color: gray; font-size: 16px;")
        header_layout.addWidget(self.status_indicator)

        # VPN name
        name_label = QLabel(self.display_name)
        name_font = QFont()
        name_font.setBold(True)
        name_label.setFont(name_font)
        header_layout.addWidget(name_label)

        # Backend type label
        backend_label_text = "NM" if self.backend_type != "openvpn3" else "OV3"
        backend_label = QLabel(backend_label_text)
        backend_label.setStyleSheet(
            "color: #888888; font-size: 9px; border: 1px solid #555555; "
            "border-radius: 3px; padding: 1px 4px;"
        )
        header_layout.addWidget(backend_label)

        header_layout.addStretch()

        # Status text
        self.status_label = QLabel("Disconnected")
        header_layout.addWidget(self.status_label)

        # Connection time counter (DD:HH:MM:SS)
        self.connection_time_label = QLabel("")
        self.connection_time_label.setStyleSheet(
            "color: #aaaaaa; font-size: 10px; font-family: monospace;"
        )
        header_layout.addWidget(self.connection_time_label)

        layout.addLayout(header_layout)

        # Info row (asserts status, last check)
        info_layout = QHBoxLayout()
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color: gray; font-size: 10px;")
        info_layout.addWidget(self.info_label)
        info_layout.addStretch()
        layout.addLayout(info_layout)

        # Stats row (avg latency, total failures, uptime)
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color: #888888; font-size: 10px;")
        layout.addWidget(self.stats_label)

        # Control buttons
        button_layout = QHBoxLayout()

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.on_connect)
        button_layout.addWidget(self.connect_btn)

        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.clicked.connect(self.on_disconnect)
        button_layout.addWidget(self.disconnect_btn)

        self.bounce_btn = QPushButton("Bounce")
        self.bounce_btn.clicked.connect(self.on_bounce)
        button_layout.addWidget(self.bounce_btn)

        self.details_btn = QPushButton("Details")
        self.details_btn.clicked.connect(self.on_details)
        self.details_btn.setEnabled(False)
        button_layout.addWidget(self.details_btn)

        self.configure_btn = QPushButton("Configure")
        self.configure_btn.clicked.connect(self.on_configure)
        button_layout.addWidget(self.configure_btn)

        button_layout.addStretch()

        # Ordering buttons
        self.move_up_btn = QPushButton("\u25B2")  # ▲
        self.move_up_btn.setMaximumWidth(30)
        self.move_up_btn.setToolTip("Move up")
        self.move_up_btn.clicked.connect(lambda: self.move_requested.emit(self.vpn_name, -1))
        button_layout.addWidget(self.move_up_btn)

        self.move_down_btn = QPushButton("\u25BC")  # ▼
        self.move_down_btn.setMaximumWidth(30)
        self.move_down_btn.setToolTip("Move down")
        self.move_down_btn.clicked.connect(lambda: self.move_requested.emit(self.vpn_name, 1))
        button_layout.addWidget(self.move_down_btn)

        layout.addLayout(button_layout)

        self.setLayout(layout)

    def update_status(self):
        """Update the VPN status display"""
        is_active = self.vpn_manager.is_vpn_active(self.vpn_name)

        if is_active:
            self.status_indicator.setStyleSheet("color: green; font-size: 16px;")
            self.status_label.setText("Connected")
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(True)
            self.bounce_btn.setEnabled(True)
            self.details_btn.setEnabled(True)

            # Track connection start time (fetch from NM once, then cache)
            if self._connected_since is None:
                self._connected_since = (
                    self.vpn_manager.get_connection_timestamp(self.vpn_name)
                    or datetime.now()
                )
                # Track as active in restore list
                self.config_manager.add_restore_vpn(self.vpn_name)
            self.update_connection_time()

            # Get assert status if monitor is running
            if self.monitor_thread:
                monitor_status = self.monitor_thread.get_vpn_status(self.vpn_name)
                failure_count = monitor_status['failure_count']
                last_check = monitor_status['last_check']

                if last_check:
                    time_ago = datetime.now() - last_check
                    minutes_ago = int(time_ago.total_seconds() / 60)
                    if minutes_ago == 0:
                        time_str = "just now"
                    else:
                        time_str = f"{minutes_ago}m ago"

                    if failure_count > 0:
                        self.info_label.setText(f"⚠ {failure_count} failures | Last check: {time_str}")
                        self.info_label.setStyleSheet("color: orange; font-size: 10px;")
                    else:
                        self.info_label.setText(f"✓ All checks passing | Last check: {time_str}")
                        self.info_label.setStyleSheet("color: green; font-size: 10px;")
                else:
                    self.info_label.setText("Monitoring active")
                    self.info_label.setStyleSheet("color: gray; font-size: 10px;")

            # Update stats from metrics collector
            if self.metrics_collector:
                stats = self.metrics_collector.get_stats(self.vpn_name)
                if stats:
                    self.stats_label.setText(
                        f"Avg: {stats.avg_latency_ms:.0f}ms | "
                        f"Total failures: {stats.total_failures} | "
                        f"Uptime: {stats.uptime_pct:.1f}%"
                    )
                else:
                    self.stats_label.setText("No data")
            else:
                self.stats_label.setText("")
        else:
            self.status_indicator.setStyleSheet("color: gray; font-size: 16px;")
            self.status_label.setText("Disconnected")
            self.connect_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(False)
            self.bounce_btn.setEnabled(False)
            self.details_btn.setEnabled(False)
            self.info_label.setText("")
            self.stats_label.setText("")
            self._connected_since = None
            self.connection_time_label.setText("")

    def update_connection_time(self):
        """Update the connection time counter display (DD:HH:MM:SS)."""
        if self._connected_since is None:
            self.connection_time_label.setText("")
            return

        total_seconds = int((datetime.now() - self._connected_since).total_seconds())
        if total_seconds < 0:
            total_seconds = 0
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        self.connection_time_label.setText(
            f"{days:02d}:{hours:02d}:{minutes:02d}:{seconds:02d}"
        )

    def _set_buttons_busy(self, busy: bool):
        """Disable/enable buttons during async operations."""
        self.connect_btn.setEnabled(not busy)
        self.disconnect_btn.setEnabled(not busy)
        self.bounce_btn.setEnabled(not busy)
        if busy:
            self.status_label.setText("Awaiting authentication...")

    def _run_in_thread(self, func, callback):
        """Run func in a background thread, call callback(result) on the GUI thread."""
        def worker():
            result = func()
            # Schedule callback on the main thread via a single-shot timer
            QTimer.singleShot(0, lambda: callback(result))

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def on_connect(self):
        """Handle connect button click"""
        logger.info(f"Connecting to {self.vpn_name}")
        self._set_buttons_busy(True)

        def do_connect():
            return self.vpn_manager.connect_vpn(self.vpn_name)

        def on_done(result):
            success, message = result
            if success:
                if self.monitor_thread:
                    self.monitor_thread.reset_vpn_state(self.vpn_name)
                self.config_manager.add_restore_vpn(self.vpn_name)
            self.update_status()

        self._run_in_thread(do_connect, on_done)

    def on_disconnect(self):
        """Handle disconnect button click"""
        logger.info(f"Disconnecting from {self.vpn_name}")
        self.vpn_manager.disconnect_vpn(self.vpn_name)
        self.config_manager.remove_restore_vpn(self.vpn_name)
        self.update_status()

    def on_bounce(self):
        """Handle bounce button click"""
        logger.info(f"Bouncing {self.vpn_name}")
        self._set_buttons_busy(True)

        def do_bounce():
            return self.vpn_manager.bounce_vpn(self.vpn_name)

        def on_done(result):
            success, message = result
            if success and self.monitor_thread:
                self.monitor_thread.reset_vpn_state(self.vpn_name)
            self.update_status()

        self._run_in_thread(do_bounce, on_done)

    def on_details(self):
        """Handle details button click — show VPN interface/routes."""
        from .dialogs import VPNDetailsDialog

        details = self.vpn_manager.get_vpn_details(self.vpn_name)
        dialog = VPNDetailsDialog(self.display_name, details, self)
        dialog.exec()

    def on_configure(self):
        """Handle configure button click"""
        from .dialogs import VPNConfigDialog

        dialog = VPNConfigDialog(self.vpn_name, self.display_name, self.config_manager, self)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            vpn_config = dialog.get_config()
            self.config_manager.update_vpn_config(self.vpn_name, vpn_config)
            logger.info(f"Updated configuration for {self.vpn_name}")

            # Notify monitor of config change
            if self.monitor_thread and self.monitor_thread.isRunning():
                self.monitor_thread.notify_config_changed()

            self.update_status()
