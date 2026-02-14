#!/usr/bin/env python3
"""Mockup of the NEW vpn-toggle v3.0 layout for spec documentation."""
import sys
import math
import random

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QCheckBox, QTextEdit, QScrollArea,
    QFrame, QGroupBox, QSplitter
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

try:
    import pyqtgraph as pg
    import numpy as np
    HAS_PYQTGRAPH = True
except Exception as e:
    print(f"pyqtgraph import failed: {type(e).__name__}: {e}")
    HAS_PYQTGRAPH = False


class MockVPNWidget(QFrame):
    def __init__(self, name: str, connected: bool, info_text: str,
                 info_color: str, stats_text: str = ""):
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

        # Info row (status + last check)
        if info_text:
            info = QLabel(info_text)
            info.setStyleSheet(f"color: {info_color}; font-size: 10px;")
            layout.addWidget(info)

        # Stats row (avg latency, total failures, uptime)
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


def generate_synthetic_data(n_points: int = 60):
    """Generate synthetic latency data with failures and a bounce event."""
    random.seed(42)
    timestamps = list(range(n_points))
    latencies = []
    successes = []
    bounce_indices = []

    for i in range(n_points):
        base = 600 + 200 * math.sin(i / 8.0)
        noise = random.gauss(0, 50)
        latency = base + noise

        # Inject a failure spike around index 20-22
        if 20 <= i <= 22:
            latency = base + 400 + random.gauss(0, 30)
            successes.append(False)
        # Inject another failure around index 45
        elif i == 45:
            latency = base + 350
            successes.append(False)
        else:
            successes.append(True)

        latencies.append(max(100, latency))

    # Bounce at index 23 (after the failure cluster)
    bounce_indices.append(23)

    return timestamps, latencies, successes, bounce_indices


def generate_vpn2_data(n_points: int = 60):
    """Generate synthetic data for a second VPN (shorter, starts later)."""
    random.seed(99)
    timestamps = list(range(30, 60))
    latencies = []
    successes = []

    for i in range(len(timestamps)):
        base = 400 + 100 * math.sin(i / 6.0)
        noise = random.gauss(0, 30)
        latencies.append(max(80, base + noise))
        successes.append(True)

    return timestamps, latencies, successes, []


class MockNewWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VPN Monitor v3.0 — New Layout")
        self.resize(1100, 600)

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

        # Horizontal splitter: VPN list | Graph
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: VPN Connections
        vpn_group = QGroupBox("VPN Connections")
        vpn_layout = QVBoxLayout()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_inner = QVBoxLayout()

        scroll_inner.addWidget(MockVPNWidget(
            "Work VPN", True,
            "✓ All checks passing | Last check: 5m ago", "green",
            "Avg: 645ms | Total failures: 3 | Uptime: 95.0%"
        ))
        scroll_inner.addWidget(MockVPNWidget(
            "Personal VPN", True,
            "✓ All checks passing | Last check: 2m ago", "green",
            "Avg: 412ms | Total failures: 0 | Uptime: 100%"
        ))
        scroll_inner.addStretch()
        scroll_widget.setLayout(scroll_inner)
        scroll.setWidget(scroll_widget)
        vpn_layout.addWidget(scroll)
        vpn_group.setLayout(vpn_layout)
        splitter.addWidget(vpn_group)

        # Right: Metrics graph
        metrics_group = QGroupBox("Metrics")
        metrics_layout = QVBoxLayout()

        # Graph header with Clear button
        graph_header = QHBoxLayout()
        graph_header.addStretch()
        clear_btn = QPushButton("Clear History")
        clear_btn.setMaximumWidth(100)
        graph_header.addWidget(clear_btn)
        metrics_layout.addLayout(graph_header)

        if HAS_PYQTGRAPH:
            # Create the graph
            pg.setConfigOptions(antialias=True)
            plot_widget = pg.PlotWidget(title="Probe Latency")
            plot_widget.setLabel('left', 'Latency', units='ms')
            plot_widget.setLabel('bottom', 'Time')
            plot_widget.addLegend()
            plot_widget.setBackground('#1e1e1e')
            plot_widget.showGrid(x=True, y=True, alpha=0.3)

            # VPN 1 data
            ts1, lat1, suc1, bounces1 = generate_synthetic_data()
            ts1_arr = np.array(ts1, dtype=float)
            lat1_arr = np.array(lat1, dtype=float)

            # Line
            plot_widget.plot(ts1_arr, lat1_arr, pen=pg.mkPen('#4fc3f7', width=2),
                             name='Work VPN')

            # Pass markers (green dots)
            pass_x = [ts1[i] for i in range(len(ts1)) if suc1[i]]
            pass_y = [lat1[i] for i in range(len(lat1)) if suc1[i]]
            plot_widget.plot(pass_x, pass_y, pen=None,
                             symbol='o', symbolSize=5,
                             symbolBrush='#4caf50', symbolPen=None)

            # Fail markers (red X)
            fail_x = [ts1[i] for i in range(len(ts1)) if not suc1[i]]
            fail_y = [lat1[i] for i in range(len(lat1)) if not suc1[i]]
            plot_widget.plot(fail_x, fail_y, pen=None,
                             symbol='x', symbolSize=12,
                             symbolBrush='#f44336', symbolPen=pg.mkPen('#f44336', width=2))

            # Bounce markers (vertical red dashed lines)
            for b_idx in bounces1:
                bounce_line = pg.InfiniteLine(
                    pos=b_idx, angle=90,
                    pen=pg.mkPen('#f44336', width=2, style=Qt.PenStyle.DashLine)
                )
                plot_widget.addItem(bounce_line)
                bounce_label = pg.TextItem("Bounce", color='#f44336', anchor=(0, 1))
                bounce_label.setPos(b_idx, max(lat1) * 0.95)
                plot_widget.addItem(bounce_label)

            # VPN 2 data
            ts2, lat2, suc2, _ = generate_vpn2_data()
            ts2_arr = np.array(ts2, dtype=float)
            lat2_arr = np.array(lat2, dtype=float)
            plot_widget.plot(ts2_arr, lat2_arr, pen=pg.mkPen('#ffb74d', width=2),
                             name='Personal VPN')
            plot_widget.plot(ts2, lat2, pen=None,
                             symbol='o', symbolSize=5,
                             symbolBrush='#4caf50', symbolPen=None)

            metrics_layout.addWidget(plot_widget)
        else:
            placeholder = QLabel("pyqtgraph not installed — run: pip install pyqtgraph")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet("color: gray; padding: 40px;")
            metrics_layout.addWidget(placeholder)

        metrics_group.setLayout(metrics_layout)
        splitter.addWidget(metrics_group)

        # Set splitter proportions (~40/60)
        splitter.setSizes([440, 660])

        main_layout.addWidget(splitter)

        # Activity Log
        log_group = QGroupBox("Activity Log")
        log_layout = QVBoxLayout()
        log_text = QTextEdit()
        log_text.setReadOnly(True)
        log_text.setMaximumHeight(120)
        log_text.append("[14:30:05] Monitor thread started")
        log_text.append("[14:30:05] Monitoring enabled")
        log_text.append("[14:32:05] Work VPN: Checking 2 assert(s)...")
        log_text.append("[14:32:06] Work VPN: DNS check PASSED [845ms]")
        log_text.append("[14:32:07] Work VPN: Geolocation check PASSED [797ms]")
        log_text.append("[14:34:05] Personal VPN: Checking 1 assert(s)...")
        log_text.append("[14:34:06] Personal VPN: DNS check PASSED [412ms]")
        log_layout.addWidget(log_text)
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)

        central.setLayout(main_layout)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MockNewWindow()
    window.show()
    sys.exit(app.exec())
