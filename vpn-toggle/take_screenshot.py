#!/usr/bin/env python3
"""
Take a screenshot of the VPN Toggle v3.0 GUI with synthetic metrics data.

This script creates a standalone window that mimics the real application layout
with synthetic data loaded into the graph to produce an interesting screenshot.
"""
import sys
import os
import random
import math
from datetime import datetime, timedelta
from tempfile import mkdtemp

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QCheckBox, QTextEdit, QScrollArea,
    QFrame, QGroupBox, QSplitter
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from pathlib import Path

from vpn_toggle.metrics import MetricsCollector, DataPoint, AssertDetail
from vpn_toggle.graph import MetricsGraphWidget


def generate_synthetic_data(collector: MetricsCollector):
    """Generate realistic-looking synthetic metrics data for two VPNs."""
    random.seed(42)
    now = datetime.now()
    base = now - timedelta(hours=6)

    vpn_configs = [
        {"name": "work-vpn", "base_latency": 820, "jitter": 150},
        {"name": "personal-vpn", "base_latency": 450, "jitter": 80},
    ]

    for vpn in vpn_configs:
        for i in range(80):
            ts = base + timedelta(minutes=i * 4.5)

            # Simulate realistic latency with occasional spikes
            latency = vpn["base_latency"] + random.gauss(0, vpn["jitter"])
            # Add periodic slow-wave pattern
            latency += 60 * math.sin(i / 10.0)
            # Occasional spikes
            if random.random() < 0.08:
                latency += random.uniform(300, 600)
            latency = max(100, latency)

            # Determine success/failure
            success = True
            bounce = False

            # Cluster failures in a couple of spots
            if vpn["name"] == "work-vpn" and 30 <= i <= 33:
                success = random.random() < 0.3
                if not success and i == 32:
                    bounce = True
                    latency = 5000 + random.uniform(0, 500)
            elif vpn["name"] == "personal-vpn" and 55 <= i <= 57:
                success = random.random() < 0.4
                if not success and i == 56:
                    bounce = True
                    latency = 4200 + random.uniform(0, 300)

            if not success:
                latency = max(latency, 3000 + random.uniform(0, 2000))

            # Build assert details
            dns_latency = latency * 0.05 + random.gauss(0, 10)
            geo_latency = latency * 0.95 + random.gauss(0, 20)

            dp = DataPoint(
                timestamp=ts.isoformat(),
                vpn_name=vpn["name"],
                latency_ms=round(latency, 1),
                success=success,
                bounce_triggered=bounce,
                assert_details=[
                    AssertDetail(type="dns_lookup", latency_ms=round(max(5, dns_latency), 1), success=success),
                    AssertDetail(type="geolocation", latency_ms=round(max(50, geo_latency), 1), success=success),
                ],
            )
            collector.record(dp)


class MockVPNWidget(QFrame):
    """Simplified VPN widget for screenshot purposes."""

    def __init__(self, name: str, connected: bool, info_text: str, info_color: str,
                 stats_text: str):
        super().__init__()
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        layout = QVBoxLayout()

        # Header
        header = QHBoxLayout()
        dot = QLabel("\u25cf")
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

        # Stats row
        if stats_text:
            stats = QLabel(stats_text)
            stats.setStyleSheet("color: #888888; font-size: 10px;")
            layout.addWidget(stats)

        # Buttons
        btn_layout = QHBoxLayout()
        for label in ["Connect", "Disconnect", "Bounce", "Configure"]:
            btn = QPushButton(label)
            btn_layout.addWidget(btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.setLayout(layout)


class ScreenshotWindow(QMainWindow):
    def __init__(self, metrics_collector: MetricsCollector):
        super().__init__()
        self.setWindowTitle("VPN Monitor v3.0")
        self.resize(1100, 650)

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

        # Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: VPN list
        vpn_group = QGroupBox("VPN Connections")
        vpn_layout = QVBoxLayout()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_inner = QVBoxLayout()

        # Work VPN stats from synthetic data
        work_stats = metrics_collector.get_stats("work-vpn")
        personal_stats = metrics_collector.get_stats("personal-vpn")

        scroll_inner.addWidget(MockVPNWidget(
            "Work VPN", True,
            "\u2713 All checks passing | Last check: 2m ago", "green",
            f"Avg: {work_stats.avg_latency_ms:.0f}ms | Total failures: {work_stats.total_failures} | Uptime: {work_stats.uptime_pct:.1f}%"
            if work_stats else "No data"
        ))
        scroll_inner.addWidget(MockVPNWidget(
            "Personal VPN", True,
            "\u2713 All checks passing | Last check: 1m ago", "green",
            f"Avg: {personal_stats.avg_latency_ms:.0f}ms | Total failures: {personal_stats.total_failures} | Uptime: {personal_stats.uptime_pct:.1f}%"
            if personal_stats else "No data"
        ))
        scroll_inner.addStretch()
        scroll_widget.setLayout(scroll_inner)
        scroll.setWidget(scroll_widget)
        vpn_layout.addWidget(scroll)
        vpn_group.setLayout(vpn_layout)
        splitter.addWidget(vpn_group)

        # Right: Graph
        metrics_group = QGroupBox("Metrics")
        metrics_layout = QVBoxLayout()
        self.graph_widget = MetricsGraphWidget(metrics_collector)
        metrics_layout.addWidget(self.graph_widget)
        metrics_group.setLayout(metrics_layout)
        splitter.addWidget(metrics_group)

        splitter.setSizes([440, 660])
        main_layout.addWidget(splitter)

        # Activity log
        log_group = QGroupBox("Activity Log")
        log_layout = QVBoxLayout()
        log_text = QTextEdit()
        log_text.setReadOnly(True)
        log_text.setMaximumHeight(120)
        log_text.append("[14:30:05] Monitor thread started")
        log_text.append("[14:30:05] Monitoring enabled")
        log_text.append("[14:32:05] Work VPN: Checking 2 assert(s)...")
        log_text.append("[14:32:06] Work VPN: DNS check PASSED: myip.opendns.com resolves to 100.64.1.5 [PASSED]")
        log_text.append("[14:32:06] Work VPN: Geolocation check PASSED: city='Las Vegas' [PASSED]")
        log_text.append("[14:34:10] Personal VPN: Checking 2 assert(s)...")
        log_text.append("[14:34:11] Personal VPN: DNS check PASSED [PASSED]")
        log_text.append("[14:34:11] Personal VPN: Geolocation check PASSED: city='New York' [PASSED]")
        log_layout.addWidget(log_text)
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)

        central.setLayout(main_layout)


def main():
    app = QApplication(sys.argv)

    # Use temp directory for metrics so we don't pollute real data
    tmp_dir = Path(mkdtemp(prefix="vpn-toggle-screenshot-"))
    collector = MetricsCollector(metrics_dir=tmp_dir)
    generate_synthetic_data(collector)

    win = ScreenshotWindow(collector)
    win.show()

    def take_screenshot():
        script_dir = os.path.dirname(os.path.abspath(__file__))
        filepath = os.path.join(script_dir, "vpn-toggle-screenshot.png")
        pixmap = win.grab()
        pixmap.save(filepath, "PNG")
        print(f"Saved: {filepath}")

        # Clean up temp metrics
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

        app.quit()

    # Wait for rendering
    QTimer.singleShot(1000, take_screenshot)
    app.exec()


if __name__ == "__main__":
    main()
