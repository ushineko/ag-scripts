"""
Metrics graph widget using pyqtgraph for real-time VPN latency visualization.

Displays a unified time-series chart with color-coded lines per VPN,
pass/fail markers, and bounce event annotations.
"""
import logging
from datetime import datetime

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QMessageBox
from PyQt6.QtCore import Qt

import pyqtgraph as pg
import numpy as np

from .metrics import MetricsCollector, DataPoint, AssertDetail

logger = logging.getLogger('vpn_toggle.graph')

# Distinct colors for VPN lines (up to 6 VPNs before cycling)
VPN_COLORS = [
    '#4fc3f7',  # light blue
    '#ffb74d',  # orange
    '#81c784',  # green
    '#ce93d8',  # purple
    '#e57373',  # red
    '#4db6ac',  # teal
]

DEFAULT_VISIBLE_POINTS = 100


class MetricsGraphWidget(QWidget):
    """
    Widget containing the pyqtgraph chart and a Clear History button.

    Renders a unified latency time-series for all VPNs with pass/fail
    markers and bounce event vertical lines.
    """

    def __init__(self, metrics_collector: MetricsCollector, parent=None):
        super().__init__(parent)
        self.metrics_collector = metrics_collector
        self.visible_points = DEFAULT_VISIBLE_POINTS

        # Track per-VPN plot items for updates
        self._vpn_lines: dict[str, pg.PlotDataItem] = {}
        self._vpn_pass_scatter: dict[str, pg.PlotDataItem] = {}
        self._vpn_fail_scatter: dict[str, pg.PlotDataItem] = {}
        self._bounce_items: list = []  # InfiniteLines + TextItems for bounces
        self._color_index = 0

        self._setup_ui()
        self._load_historical_data()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # Header with Clear button
        header = QHBoxLayout()
        header.addStretch()
        self._clear_btn = QPushButton("Clear History")
        self._clear_btn.setMaximumWidth(110)
        self._clear_btn.clicked.connect(self._on_clear)
        header.addWidget(self._clear_btn)
        layout.addLayout(header)

        # pyqtgraph plot widget
        pg.setConfigOptions(antialias=True)
        self._plot_widget = pg.PlotWidget(title="Probe Latency")
        self._plot_widget.setLabel('left', 'Latency', units='ms')
        self._plot_widget.setLabel('bottom', 'Time')
        self._plot_widget.setBackground('#1e1e1e')
        self._plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self._legend = self._plot_widget.addLegend()

        layout.addWidget(self._plot_widget)
        self.setLayout(layout)

    def _next_color(self) -> str:
        color = VPN_COLORS[self._color_index % len(VPN_COLORS)]
        self._color_index += 1
        return color

    def _ensure_vpn_series(self, vpn_name: str) -> None:
        """Create plot items for a VPN if they don't exist yet."""
        if vpn_name in self._vpn_lines:
            return

        color = self._next_color()

        # Latency line
        line = self._plot_widget.plot(
            [], [], pen=pg.mkPen(color, width=2), name=vpn_name,
        )
        self._vpn_lines[vpn_name] = line

        # Pass markers (green dots)
        pass_scatter = self._plot_widget.plot(
            [], [], pen=None,
            symbol='o', symbolSize=5,
            symbolBrush='#4caf50', symbolPen=None,
        )
        self._vpn_pass_scatter[vpn_name] = pass_scatter

        # Fail markers (red X)
        fail_scatter = self._plot_widget.plot(
            [], [], pen=None,
            symbol='x', symbolSize=12,
            symbolBrush='#f44336',
            symbolPen=pg.mkPen('#f44336', width=2),
        )
        self._vpn_fail_scatter[vpn_name] = fail_scatter

    def add_data_point(self, data_point: DataPoint) -> None:
        """Add a single new data point and update the graph."""
        vpn_name = data_point.vpn_name
        self._ensure_vpn_series(vpn_name)

        # Get all points for this VPN and rebuild the series
        points = self.metrics_collector.get_data_points(vpn_name)
        self._update_vpn_plot(vpn_name, points)

    def _update_vpn_plot(self, vpn_name: str, points: list[DataPoint]) -> None:
        """Rebuild a VPN's line and markers from its data points."""
        if not points:
            return

        # Convert timestamps to sequential x values (seconds from first point)
        base_time = self._parse_ts(points[0].timestamp)
        x_vals = []
        y_vals = []
        pass_x, pass_y = [], []
        fail_x, fail_y = [], []

        for p in points:
            t = (self._parse_ts(p.timestamp) - base_time).total_seconds()
            x_vals.append(t)
            y_vals.append(p.latency_ms)
            if p.success:
                pass_x.append(t)
                pass_y.append(p.latency_ms)
            else:
                fail_x.append(t)
                fail_y.append(p.latency_ms)

        x_arr = np.array(x_vals, dtype=float)
        y_arr = np.array(y_vals, dtype=float)

        self._vpn_lines[vpn_name].setData(x_arr, y_arr)
        self._vpn_pass_scatter[vpn_name].setData(pass_x, pass_y)
        self._vpn_fail_scatter[vpn_name].setData(fail_x, fail_y)

        # Clear old bounce markers and re-add all
        self._clear_bounce_markers()
        self._add_bounce_markers(points, base_time, y_arr)

        # Auto-scroll to show latest data
        if len(x_vals) > self.visible_points:
            x_min = x_vals[-self.visible_points]
            x_max = x_vals[-1]
            padding = (x_max - x_min) * 0.05
            self._plot_widget.setXRange(x_min - padding, x_max + padding)

    def _add_bounce_markers(self, points: list[DataPoint], base_time: datetime,
                            y_arr: np.ndarray) -> None:
        """Add vertical dashed lines for bounce events."""
        y_max = float(y_arr.max()) if len(y_arr) > 0 else 1000.0

        for p in points:
            if not p.bounce_triggered:
                continue
            t = (self._parse_ts(p.timestamp) - base_time).total_seconds()

            line = pg.InfiniteLine(
                pos=t, angle=90,
                pen=pg.mkPen('#f44336', width=2, style=Qt.PenStyle.DashLine),
            )
            self._plot_widget.addItem(line)
            self._bounce_items.append(line)

            label = pg.TextItem("Bounce", color='#f44336', anchor=(0, 1))
            label.setPos(t, y_max * 0.95)
            self._plot_widget.addItem(label)
            self._bounce_items.append(label)

    def _clear_bounce_markers(self) -> None:
        for item in self._bounce_items:
            self._plot_widget.removeItem(item)
        self._bounce_items.clear()

    def _load_historical_data(self) -> None:
        """Populate graph from persisted metrics on startup."""
        for vpn_name in self.metrics_collector.get_all_vpn_names():
            self._ensure_vpn_series(vpn_name)
            points = self.metrics_collector.get_data_points(vpn_name)
            if points:
                self._update_vpn_plot(vpn_name, points)

    def clear_all(self) -> None:
        """Clear all graph data and reset the plot."""
        self.metrics_collector.clear_all()

        # Remove all plot items and reset
        for vpn in list(self._vpn_lines.keys()):
            self._plot_widget.removeItem(self._vpn_lines[vpn])
            self._plot_widget.removeItem(self._vpn_pass_scatter[vpn])
            self._plot_widget.removeItem(self._vpn_fail_scatter[vpn])
        self._vpn_lines.clear()
        self._vpn_pass_scatter.clear()
        self._vpn_fail_scatter.clear()
        self._clear_bounce_markers()
        self._color_index = 0

        # Clear and re-add legend
        self._legend.clear()

        logger.info("Graph cleared")

    def _on_clear(self):
        reply = QMessageBox.question(
            self, "Clear History",
            "Clear all metrics history for all VPNs?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.clear_all()

    @staticmethod
    def _parse_ts(ts_str: str) -> datetime:
        return datetime.fromisoformat(ts_str)
