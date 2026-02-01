"""
GUI for VPN Toggle v2.0
"""
import logging
from datetime import datetime
from typing import Dict, Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QCheckBox, QTextEdit,
    QScrollArea, QFrame, QMessageBox, QSpinBox,
    QGroupBox, QDialog, QDialogButtonBox, QFormLayout,
    QLineEdit, QComboBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

from .config import ConfigManager
from .vpn_manager import VPNManager
from .monitor import MonitorThread

logger = logging.getLogger('vpn_toggle.gui')


class VPNWidget(QFrame):
    """Widget representing a single VPN in the list"""

    def __init__(self, vpn_name: str, display_name: str, vpn_manager: VPNManager,
                 config_manager: ConfigManager, monitor_thread: Optional[MonitorThread] = None):
        super().__init__()
        self.vpn_name = vpn_name
        self.display_name = display_name
        self.vpn_manager = vpn_manager
        self.config_manager = config_manager
        self.monitor_thread = monitor_thread

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

        header_layout.addStretch()

        # Status text
        self.status_label = QLabel("Disconnected")
        header_layout.addWidget(self.status_label)

        layout.addLayout(header_layout)

        # Info row (asserts status, last check)
        info_layout = QHBoxLayout()
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color: gray; font-size: 10px;")
        info_layout.addWidget(self.info_label)
        info_layout.addStretch()
        layout.addLayout(info_layout)

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

        self.configure_btn = QPushButton("Configure")
        self.configure_btn.clicked.connect(self.on_configure)
        button_layout.addWidget(self.configure_btn)

        button_layout.addStretch()
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
        else:
            self.status_indicator.setStyleSheet("color: gray; font-size: 16px;")
            self.status_label.setText("Disconnected")
            self.connect_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(False)
            self.bounce_btn.setEnabled(False)
            self.info_label.setText("")

    def on_connect(self):
        """Handle connect button click"""
        logger.info(f"Connecting to {self.vpn_name}")
        success, message = self.vpn_manager.connect_vpn(self.vpn_name)

        if success and self.monitor_thread:
            self.monitor_thread.reset_vpn_state(self.vpn_name)

        self.update_status()

    def on_disconnect(self):
        """Handle disconnect button click"""
        logger.info(f"Disconnecting from {self.vpn_name}")
        self.vpn_manager.disconnect_vpn(self.vpn_name)
        self.update_status()

    def on_bounce(self):
        """Handle bounce button click"""
        logger.info(f"Bouncing {self.vpn_name}")
        success, message = self.vpn_manager.bounce_vpn(self.vpn_name)

        if success and self.monitor_thread:
            self.monitor_thread.reset_vpn_state(self.vpn_name)

        self.update_status()

    def on_configure(self):
        """Handle configure button click"""
        dialog = VPNConfigDialog(self.vpn_name, self.display_name, self.config_manager, self)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            vpn_config = dialog.get_config()
            self.config_manager.update_vpn_config(self.vpn_name, vpn_config)
            logger.info(f"Updated configuration for {self.vpn_name}")

            # Notify monitor of config change
            if self.monitor_thread and self.monitor_thread.isRunning():
                self.monitor_thread.notify_config_changed()

            self.update_status()


class VPNConfigDialog(QDialog):
    """Dialog for configuring VPN asserts"""

    def __init__(self, vpn_name: str, display_name: str, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.vpn_name = vpn_name
        self.display_name = display_name
        self.config_manager = config_manager
        self.setWindowTitle(f"Configure {display_name}")
        self.setMinimumWidth(500)
        self.setup_ui()

    def _find_assert_by_type(self, vpn_config: Dict, assert_type: str) -> Optional[Dict]:
        """
        Find an assert configuration by type.

        Args:
            vpn_config: VPN configuration dictionary
            assert_type: Type of assert to find (e.g., 'dns_lookup', 'geolocation')

        Returns:
            Assert configuration dict if found, None otherwise
        """
        for assert_config in vpn_config.get('asserts', []):
            if assert_config.get('type') == assert_type:
                return assert_config
        return None

    def setup_ui(self):
        """Setup dialog UI"""
        layout = QVBoxLayout()

        # Get current VPN config or create default
        vpn_config = self.config_manager.get_vpn_config(self.vpn_name)
        if not vpn_config:
            vpn_config = {
                'name': self.vpn_name,
                'display_name': self.display_name,
                'enabled': True,
                'asserts': []
            }

        # Display name
        form_layout = QFormLayout()
        self.display_name_edit = QLineEdit(vpn_config.get('display_name', self.display_name))
        form_layout.addRow("Display Name:", self.display_name_edit)

        # Enabled checkbox
        self.enabled_checkbox = QCheckBox("Enable monitoring for this VPN")
        self.enabled_checkbox.setChecked(vpn_config.get('enabled', True))
        form_layout.addRow("", self.enabled_checkbox)

        layout.addLayout(form_layout)

        # DNS Assert section
        dns_group = QGroupBox("DNS Lookup Assert")
        dns_layout = QFormLayout()

        # Find existing DNS assert
        dns_assert = self._find_assert_by_type(vpn_config, 'dns_lookup')

        self.dns_enabled = QCheckBox("Enable DNS lookup check")
        self.dns_enabled.setChecked(dns_assert is not None)
        dns_layout.addRow("", self.dns_enabled)

        self.dns_hostname = QLineEdit(dns_assert.get('hostname', 'myip.opendns.com') if dns_assert else 'myip.opendns.com')
        self.dns_hostname.setPlaceholderText("e.g., myip.opendns.com")
        dns_layout.addRow("Hostname:", self.dns_hostname)

        self.dns_prefix = QLineEdit(dns_assert.get('expected_prefix', '100.') if dns_assert else '100.')
        self.dns_prefix.setPlaceholderText("e.g., 100. or 10.8.")
        dns_layout.addRow("Expected IP Prefix:", self.dns_prefix)

        dns_group.setLayout(dns_layout)
        layout.addWidget(dns_group)

        # Geolocation Assert section
        geo_group = QGroupBox("Geolocation Assert")
        geo_layout = QFormLayout()

        # Find existing geolocation assert
        geo_assert = self._find_assert_by_type(vpn_config, 'geolocation')

        self.geo_enabled = QCheckBox("Enable geolocation check")
        self.geo_enabled.setChecked(geo_assert is not None)
        geo_layout.addRow("", self.geo_enabled)

        self.geo_field = QComboBox()
        self.geo_field.addItems(['city', 'regionName', 'country'])
        if geo_assert:
            field = geo_assert.get('field', 'city')
            index = self.geo_field.findText(field)
            if index >= 0:
                self.geo_field.setCurrentIndex(index)
        geo_layout.addRow("Location Field:", self.geo_field)

        self.geo_value = QLineEdit(geo_assert.get('expected_value', '') if geo_assert else '')
        self.geo_value.setPlaceholderText("e.g., Las Vegas, Nevada, United States")
        geo_layout.addRow("Expected Value:", self.geo_value)

        geo_group.setLayout(geo_layout)
        layout.addWidget(geo_group)

        # Help text
        help_label = QLabel(
            "Tip: Run the VPN and check the Activity Log to see detected DNS IPs and locations.\n"
            "Use partial matches (e.g., 'Vegas' matches 'Las Vegas')."
        )
        help_label.setStyleSheet("color: gray; font-size: 10px; padding: 10px;")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def get_config(self) -> Dict:
        """Get the configured VPN settings"""
        asserts = []

        # Add DNS assert if enabled
        if self.dns_enabled.isChecked():
            asserts.append({
                'type': 'dns_lookup',
                'hostname': self.dns_hostname.text().strip(),
                'expected_prefix': self.dns_prefix.text().strip(),
                'description': f"DNS check: {self.dns_hostname.text()} matches {self.dns_prefix.text()}"
            })

        # Add geolocation assert if enabled
        if self.geo_enabled.isChecked() and self.geo_value.text().strip():
            asserts.append({
                'type': 'geolocation',
                'field': self.geo_field.currentText(),
                'expected_value': self.geo_value.text().strip(),
                'description': f"Geolocation: {self.geo_field.currentText()} = {self.geo_value.text()}"
            })

        return {
            'name': self.vpn_name,
            'display_name': self.display_name_edit.text().strip(),
            'enabled': self.enabled_checkbox.isChecked(),
            'asserts': asserts
        }


class SettingsDialog(QDialog):
    """Dialog for configuring monitor settings"""

    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setWindowTitle("Monitor Settings")
        self.setup_ui()

    def setup_ui(self):
        """Setup dialog UI"""
        layout = QFormLayout()

        # Get current settings
        monitor_settings = self.config_manager.get_monitor_settings()

        # Check interval
        self.interval_spinbox = QSpinBox()
        self.interval_spinbox.setRange(30, 600)
        self.interval_spinbox.setValue(monitor_settings.get('check_interval_seconds', 120))
        self.interval_spinbox.setSuffix(" seconds")
        layout.addRow("Check Interval:", self.interval_spinbox)

        # Grace period
        self.grace_spinbox = QSpinBox()
        self.grace_spinbox.setRange(5, 60)
        self.grace_spinbox.setValue(monitor_settings.get('grace_period_seconds', 15))
        self.grace_spinbox.setSuffix(" seconds")
        layout.addRow("Grace Period:", self.grace_spinbox)

        # Failure threshold
        self.threshold_spinbox = QSpinBox()
        self.threshold_spinbox.setRange(1, 10)
        self.threshold_spinbox.setValue(monitor_settings.get('failure_threshold', 3))
        layout.addRow("Failure Threshold:", self.threshold_spinbox)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)

        self.setLayout(layout)

    def get_settings(self) -> Dict:
        """Get the configured settings"""
        return {
            'check_interval_seconds': self.interval_spinbox.value(),
            'grace_period_seconds': self.grace_spinbox.value(),
            'failure_threshold': self.threshold_spinbox.value()
        }


class VPNToggleMainWindow(QMainWindow):
    """Main window for VPN Toggle application"""

    def __init__(self, config_manager: ConfigManager, vpn_manager: VPNManager):
        super().__init__()
        self.config_manager = config_manager
        self.vpn_manager = vpn_manager
        self.monitor_thread = None
        self.vpn_widgets: Dict[str, VPNWidget] = {}

        self.setWindowTitle("VPN Monitor v2.0")
        self.setup_ui()
        self.setup_monitor()
        self.restore_geometry()

        # Setup status update timer
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_all_vpn_status)
        self.status_timer.start(5000)  # Update every 5 seconds

    def setup_ui(self):
        """Setup the main window UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()

        # Top control bar
        control_layout = QHBoxLayout()

        # Monitor toggle
        self.monitor_checkbox = QCheckBox("Monitor Mode")
        monitor_settings = self.config_manager.get_monitor_settings()
        self.monitor_checkbox.setChecked(monitor_settings.get('enabled', False))
        self.monitor_checkbox.stateChanged.connect(self.on_monitor_toggled)
        control_layout.addWidget(self.monitor_checkbox)

        control_layout.addStretch()

        # Settings button
        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self.on_settings_clicked)
        control_layout.addWidget(settings_btn)

        main_layout.addLayout(control_layout)

        # VPN list area
        vpn_group = QGroupBox("VPN Connections")
        vpn_layout = QVBoxLayout()

        # Scroll area for VPNs
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_widget = QWidget()
        self.vpn_list_layout = QVBoxLayout()

        # Populate VPN list
        self.populate_vpn_list()

        scroll_widget.setLayout(self.vpn_list_layout)
        scroll_area.setWidget(scroll_widget)
        vpn_layout.addWidget(scroll_area)

        vpn_group.setLayout(vpn_layout)
        main_layout.addWidget(vpn_group)

        # Activity log
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
        """Populate the VPN list from available VPNs"""
        # Get all VPNs from NetworkManager
        vpns = self.vpn_manager.list_vpns()

        if not vpns:
            label = QLabel("No VPN connections found")
            label.setStyleSheet("color: gray; padding: 20px;")
            self.vpn_list_layout.addWidget(label)
            return

        # Create widgets for each VPN
        for vpn in vpns:
            vpn_config = self.config_manager.get_vpn_config(vpn.name)

            # Use display name from config or fallback to connection name
            display_name = vpn.name
            if vpn_config:
                display_name = vpn_config.get('display_name', vpn.name)

            widget = VPNWidget(vpn.name, display_name, self.vpn_manager,
                             self.config_manager, self.monitor_thread)
            self.vpn_widgets[vpn.name] = widget
            self.vpn_list_layout.addWidget(widget)

        self.vpn_list_layout.addStretch()

    def setup_monitor(self):
        """Setup the monitor thread"""
        self.monitor_thread = MonitorThread(self.config_manager, self.vpn_manager)

        # Connect signals
        self.monitor_thread.log_message.connect(self.append_log)
        self.monitor_thread.assert_result.connect(self.on_assert_result)
        self.monitor_thread.vpn_disabled.connect(self.on_vpn_disabled)

        # Update VPN widgets with monitor reference
        for widget in self.vpn_widgets.values():
            widget.monitor_thread = self.monitor_thread

        # Start monitor if enabled
        monitor_settings = self.config_manager.get_monitor_settings()
        if monitor_settings.get('enabled', False):
            self.monitor_thread.enable_monitoring()
            self.monitor_thread.start()
            self.append_log("Monitor thread started")

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
            self.append_log(f"Settings updated: {settings}")

            # Notify monitor of config change
            if self.monitor_thread and self.monitor_thread.isRunning():
                self.monitor_thread.notify_config_changed()

    def on_assert_result(self, vpn_name: str, success: bool, message: str):
        """Handle assert result signal"""
        # Log the result to activity log
        status = "PASSED" if success else "FAILED"
        display_name = vpn_name
        if vpn_name in self.vpn_widgets:
            display_name = self.vpn_widgets[vpn_name].display_name

        self.append_log(f"{display_name}: {message} [{status}]")

        # Update the corresponding VPN widget
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

        # Update VPN widget
        if vpn_name in self.vpn_widgets:
            self.vpn_widgets[vpn_name].update_status()

    def update_all_vpn_status(self):
        """Update status for all VPN widgets"""
        for widget in self.vpn_widgets.values():
            widget.update_status()

    def append_log(self, message: str):
        """Append message to activity log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")

        # Auto-scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def restore_geometry(self):
        """Restore window geometry from config"""
        geometry = self.config_manager.get_window_geometry()

        if geometry['x'] is not None and geometry['y'] is not None:
            self.move(geometry['x'], geometry['y'])

        if geometry['width'] and geometry['height']:
            self.resize(geometry['width'], geometry['height'])

    def save_geometry(self):
        """Save window geometry to config"""
        geo = self.geometry()
        self.config_manager.update_window_geometry(
            geo.x(), geo.y(), geo.width(), geo.height()
        )

    def closeEvent(self, event):
        """Handle window close event"""
        # Save geometry
        self.save_geometry()

        # Stop monitor thread
        if self.monitor_thread and self.monitor_thread.isRunning():
            self.monitor_thread.stop()
            logger.info("Monitor thread stopped")

        event.accept()
