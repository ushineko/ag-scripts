#!/usr/bin/env python3
"""Mockup of the CURRENT vpn-toggle layout for spec documentation."""
import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QCheckBox, QTextEdit, QScrollArea,
    QFrame, QGroupBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class MockVPNWidget(QFrame):
    def __init__(self, name: str, connected: bool, info_text: str, info_color: str):
        super().__init__()
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        layout = QVBoxLayout()

        # Header
        header = QHBoxLayout()
        dot = QLabel("●")
        color = "green" if connected else "gray"
        dot.setStyleSheet(f"color: {color}; font-size: 16px;")
        header.addWidget(dot)

        name_label = QLabel(name)
        font = QFont()
        font.setBold(True)
        name_label.setFont(font)
        header.addWidget(name_label)
        header.addStretch()

        status = QLabel("Connected" if connected else "Disconnected")
        header.addWidget(status)
        layout.addLayout(header)

        # Info row
        if info_text:
            info = QLabel(info_text)
            info.setStyleSheet(f"color: {info_color}; font-size: 10px;")
            layout.addWidget(info)

        # Buttons
        btn_layout = QHBoxLayout()
        for label in ["Connect", "Disconnect", "Bounce", "Configure"]:
            btn = QPushButton(label)
            btn_layout.addWidget(btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.setLayout(layout)


class MockCurrentWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VPN Monitor v2.1 — Current Layout")
        self.resize(800, 600)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout()

        # Control bar
        control = QHBoxLayout()
        monitor_cb = QCheckBox("Monitor Mode")
        monitor_cb.setChecked(True)
        control.addWidget(monitor_cb)
        control.addStretch()
        control.addWidget(QPushButton("Settings"))
        main_layout.addLayout(control)

        # VPN Connections
        vpn_group = QGroupBox("VPN Connections")
        vpn_layout = QVBoxLayout()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_inner = QVBoxLayout()

        scroll_inner.addWidget(MockVPNWidget(
            "Work VPN", True,
            "✓ All checks passing | Last check: 5m ago", "green"
        ))
        scroll_inner.addWidget(MockVPNWidget(
            "Personal VPN", False, "", "gray"
        ))
        scroll_inner.addStretch()
        scroll_widget.setLayout(scroll_inner)
        scroll.setWidget(scroll_widget)
        vpn_layout.addWidget(scroll)
        vpn_group.setLayout(vpn_layout)
        main_layout.addWidget(vpn_group)

        # Activity Log
        log_group = QGroupBox("Activity Log")
        log_layout = QVBoxLayout()
        log_text = QTextEdit()
        log_text.setReadOnly(True)
        log_text.setMaximumHeight(150)
        log_text.append("[14:30:05] Monitor thread started")
        log_text.append("[14:30:05] Monitoring enabled")
        log_text.append("[14:32:05] Work VPN: Checking 2 assert(s)...")
        log_text.append("[14:32:06] Work VPN: DNS check PASSED: myip.opendns.com resolves to 100.64.1.5 [PASSED]")
        log_text.append("[14:32:06] Work VPN: Geolocation check PASSED: city='Las Vegas' [PASSED]")
        log_layout.addWidget(log_text)
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)

        central.setLayout(main_layout)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MockCurrentWindow()
    window.show()
    sys.exit(app.exec())
