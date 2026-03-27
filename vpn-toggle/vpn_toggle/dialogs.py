"""
Configuration, settings, and details dialogs for VPN Toggle
"""
import logging
import shutil
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QVBoxLayout, QFormLayout,
    QLineEdit, QComboBox, QCheckBox, QSpinBox, QGroupBox,
    QLabel, QTextEdit, QTabWidget, QWidget,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from .config import ConfigManager

logger = logging.getLogger('vpn_toggle.dialogs')


class VPNConfigDialog(QDialog):
    """Tabbed dialog for configuring a VPN's display name and health checks."""

    def __init__(self, vpn_name: str, display_name: str, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.vpn_name = vpn_name
        self.display_name = display_name
        self.config_manager = config_manager
        self.setWindowTitle(f"Configure {display_name}")
        self.setMinimumWidth(500)
        self.setup_ui()

    def _find_assert_by_type(self, vpn_config: dict, assert_type: str) -> Optional[dict]:
        for assert_config in vpn_config.get('asserts', []):
            if assert_config.get('type') == assert_type:
                return assert_config
        return None

    def setup_ui(self):
        """Setup tabbed dialog UI"""
        layout = QVBoxLayout()

        vpn_config = self.config_manager.get_vpn_config(self.vpn_name)
        if not vpn_config:
            vpn_config = {
                'name': self.vpn_name,
                'display_name': self.display_name,
                'enabled': True,
                'asserts': []
            }

        # Tab widget
        self.tabs = QTabWidget()

        # --- General tab ---
        general_tab = QWidget()
        general_layout = QVBoxLayout()

        form_layout = QFormLayout()
        self.display_name_edit = QLineEdit(vpn_config.get('display_name', self.display_name))
        form_layout.addRow("Display Name:", self.display_name_edit)

        self.enabled_checkbox = QCheckBox("Enable monitoring for this VPN")
        self.enabled_checkbox.setChecked(vpn_config.get('enabled', True))
        form_layout.addRow("", self.enabled_checkbox)

        general_layout.addLayout(form_layout)
        general_layout.addStretch()
        general_tab.setLayout(general_layout)
        self.tabs.addTab(general_tab, "General")

        # --- Health Checks tab ---
        health_tab = QWidget()
        health_layout = QVBoxLayout()

        # DNS Assert
        dns_group = QGroupBox("DNS Lookup")
        dns_layout = QFormLayout()

        dns_assert = self._find_assert_by_type(vpn_config, 'dns_lookup')

        self.dns_enabled = QCheckBox("Enable DNS lookup check")
        self.dns_enabled.setChecked(dns_assert is not None)
        dns_layout.addRow("", self.dns_enabled)

        self.dns_hostname = QLineEdit(
            dns_assert.get('hostname', 'myip.opendns.com') if dns_assert else 'myip.opendns.com'
        )
        self.dns_hostname.setPlaceholderText("e.g., myip.opendns.com")
        dns_layout.addRow("Hostname:", self.dns_hostname)

        self.dns_prefix = QLineEdit(
            dns_assert.get('expected_prefix', '100.') if dns_assert else '100.'
        )
        self.dns_prefix.setPlaceholderText("e.g., 100. or 10.8.")
        dns_layout.addRow("Expected IP Prefix:", self.dns_prefix)

        dns_group.setLayout(dns_layout)
        health_layout.addWidget(dns_group)

        # Geolocation Assert
        geo_group = QGroupBox("Geolocation")
        geo_layout = QFormLayout()

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

        self.geo_value = QLineEdit(
            geo_assert.get('expected_value', '') if geo_assert else ''
        )
        self.geo_value.setPlaceholderText("e.g., Las Vegas, Nevada, United States")
        geo_layout.addRow("Expected Value:", self.geo_value)

        geo_group.setLayout(geo_layout)
        health_layout.addWidget(geo_group)

        # Ping Assert
        ping_group = QGroupBox("Ping")
        ping_layout = QFormLayout()

        ping_assert = self._find_assert_by_type(vpn_config, 'ping')

        self.ping_enabled = QCheckBox("Enable ping check")
        self.ping_enabled.setChecked(ping_assert is not None)
        ping_layout.addRow("", self.ping_enabled)

        self.ping_host = QLineEdit(
            ping_assert.get('host', '') if ping_assert else ''
        )
        self.ping_host.setPlaceholderText("e.g., 172.16.0.1 or internal-host.local")
        ping_layout.addRow("Host:", self.ping_host)

        self.ping_timeout = QSpinBox()
        self.ping_timeout.setRange(1, 30)
        self.ping_timeout.setValue(
            ping_assert.get('timeout_seconds', 5) if ping_assert else 5
        )
        self.ping_timeout.setSuffix(" seconds")
        ping_layout.addRow("Timeout:", self.ping_timeout)

        ping_group.setLayout(ping_layout)
        health_layout.addWidget(ping_group)

        # Help text
        help_label = QLabel(
            "Tip: Run the VPN and check the Activity Log to see detected DNS IPs and locations.\n"
            "Use partial matches for geolocation (e.g., 'Vegas' matches 'Las Vegas')."
        )
        help_label.setStyleSheet("color: gray; font-size: 10px; padding: 10px;")
        help_label.setWordWrap(True)
        health_layout.addWidget(help_label)

        health_tab.setLayout(health_layout)
        self.tabs.addTab(health_tab, "Health Checks")

        layout.addWidget(self.tabs)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def get_config(self) -> dict:
        """Get the configured VPN settings from all tabs."""
        asserts = []

        if self.dns_enabled.isChecked():
            asserts.append({
                'type': 'dns_lookup',
                'hostname': self.dns_hostname.text().strip(),
                'expected_prefix': self.dns_prefix.text().strip(),
                'description': f"DNS check: {self.dns_hostname.text()} matches {self.dns_prefix.text()}"
            })

        if self.geo_enabled.isChecked() and self.geo_value.text().strip():
            asserts.append({
                'type': 'geolocation',
                'field': self.geo_field.currentText(),
                'expected_value': self.geo_value.text().strip(),
                'description': f"Geolocation: {self.geo_field.currentText()} = {self.geo_value.text()}"
            })

        if self.ping_enabled.isChecked() and self.ping_host.text().strip():
            asserts.append({
                'type': 'ping',
                'host': self.ping_host.text().strip(),
                'timeout_seconds': self.ping_timeout.value(),
                'description': f"Ping: {self.ping_host.text()}"
            })

        return {
            'name': self.vpn_name,
            'display_name': self.display_name_edit.text().strip(),
            'enabled': self.enabled_checkbox.isChecked(),
            'asserts': asserts
        }


class VPNDetailsDialog(QDialog):
    """Read-only dialog showing VPN interface, IP, and routes."""

    def __init__(self, display_name: str, details: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Details: {display_name}")
        self.setMinimumWidth(500)
        self.setMinimumHeight(300)

        layout = QVBoxLayout()

        text = QTextEdit()
        text.setReadOnly(True)
        text.setFont(QFont("monospace", 10))

        if not details:
            text.setPlainText("VPN is not connected or details unavailable.")
        else:
            lines = []
            lines.append(f"Interface:  {details.get('interface', 'N/A')}")
            lines.append(f"IP Address: {details.get('ip', 'N/A')}")
            lines.append("")
            routes = details.get('routes', [])
            if routes:
                lines.append(f"Routes ({len(routes)}):")
                for route in routes:
                    lines.append(f"  {route}")
            else:
                lines.append("Routes: none")
            text.setPlainText('\n'.join(lines))

        layout.addWidget(text)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)


class SettingsDialog(QDialog):
    """Dialog for configuring monitor and startup settings"""

    AUTOSTART_DIR = Path.home() / ".config" / "autostart"
    AUTOSTART_FILE = AUTOSTART_DIR / "vpn-toggle-v2.desktop"

    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setWindowTitle("Settings")
        self.setup_ui()

    def setup_ui(self):
        """Setup dialog UI"""
        layout = QVBoxLayout()

        # Monitor settings group
        monitor_group = QGroupBox("Monitor Settings")
        monitor_layout = QFormLayout()

        monitor_settings = self.config_manager.get_monitor_settings()

        self.interval_spinbox = QSpinBox()
        self.interval_spinbox.setRange(30, 600)
        self.interval_spinbox.setValue(monitor_settings.get('check_interval_seconds', 120))
        self.interval_spinbox.setSuffix(" seconds")
        monitor_layout.addRow("Check Interval:", self.interval_spinbox)

        self.grace_spinbox = QSpinBox()
        self.grace_spinbox.setRange(5, 60)
        self.grace_spinbox.setValue(monitor_settings.get('grace_period_seconds', 15))
        self.grace_spinbox.setSuffix(" seconds")
        monitor_layout.addRow("Grace Period:", self.grace_spinbox)

        self.threshold_spinbox = QSpinBox()
        self.threshold_spinbox.setRange(1, 10)
        self.threshold_spinbox.setValue(monitor_settings.get('failure_threshold', 3))
        monitor_layout.addRow("Failure Threshold:", self.threshold_spinbox)

        monitor_group.setLayout(monitor_layout)
        layout.addWidget(monitor_group)

        # Startup settings group
        startup_group = QGroupBox("Startup Settings")
        startup_layout = QVBoxLayout()

        startup_settings = self.config_manager.get_startup_settings()

        self.autostart_checkbox = QCheckBox("Start VPN Toggle on login")
        self.autostart_checkbox.setChecked(startup_settings.get('autostart', False))
        startup_layout.addWidget(self.autostart_checkbox)

        self.minimized_checkbox = QCheckBox("Start minimized to system tray")
        self.minimized_checkbox.setChecked(startup_settings.get('start_minimized', False))
        self.minimized_checkbox.setEnabled(startup_settings.get('autostart', False))
        startup_layout.addWidget(self.minimized_checkbox)

        self.autostart_checkbox.stateChanged.connect(
            lambda state: self.minimized_checkbox.setEnabled(state == Qt.CheckState.Checked.value)
        )

        self.restore_checkbox = QCheckBox("Restore VPN connections on startup")
        self.restore_checkbox.setChecked(startup_settings.get('restore_connections', False))
        startup_layout.addWidget(self.restore_checkbox)

        startup_group.setLayout(startup_layout)
        layout.addWidget(startup_group)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def get_settings(self) -> dict:
        """Get the configured monitor settings"""
        return {
            'check_interval_seconds': self.interval_spinbox.value(),
            'grace_period_seconds': self.grace_spinbox.value(),
            'failure_threshold': self.threshold_spinbox.value()
        }

    def get_startup_settings(self) -> dict:
        """Get the configured startup settings"""
        return {
            'autostart': self.autostart_checkbox.isChecked(),
            'start_minimized': self.minimized_checkbox.isChecked(),
            'restore_connections': self.restore_checkbox.isChecked(),
        }

    def apply_autostart(self) -> None:
        """Create or remove the XDG autostart desktop file."""
        if self.autostart_checkbox.isChecked():
            self._create_autostart_file()
        else:
            self._remove_autostart_file()

    def _create_autostart_file(self) -> None:
        vpn_toggle_bin = shutil.which("vpn-toggle-v2")
        if not vpn_toggle_bin:
            vpn_toggle_bin = "vpn-toggle-v2"

        exec_line = vpn_toggle_bin
        if self.minimized_checkbox.isChecked():
            exec_line += " --minimized"

        content = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=VPN Toggle\n"
            "Comment=VPN connection manager and health monitor\n"
            f"Exec={exec_line}\n"
            "Icon=vpn-toggle-v2\n"
            "Terminal=false\n"
            "Categories=Network;\n"
            "X-GNOME-Autostart-enabled=true\n"
        )

        self.AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
        self.AUTOSTART_FILE.write_text(content)
        logger.info(f"Created autostart file: {self.AUTOSTART_FILE}")

    def _remove_autostart_file(self) -> None:
        if self.AUTOSTART_FILE.exists():
            self.AUTOSTART_FILE.unlink()
            logger.info(f"Removed autostart file: {self.AUTOSTART_FILE}")
