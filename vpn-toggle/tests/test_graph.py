"""
Tests for MetricsGraphWidget data handling.

These tests verify the graph widget's data management logic (series creation,
data point addition, clear). Rendering is not tested — that's verified manually.
"""
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from PyQt6.QtWidgets import QApplication

import pyqtgraph as pg

from vpn_toggle.metrics import MetricsCollector, DataPoint, AssertDetail
from vpn_toggle.graph import MetricsGraphWidget, VPN_COLORS


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication for all graph tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def metrics_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "metrics"


@pytest.fixture
def collector(metrics_dir):
    return MetricsCollector(metrics_dir=metrics_dir)


@pytest.fixture
def graph_widget(qapp, collector):
    widget = MetricsGraphWidget(collector)
    return widget


def _make_point(vpn: str = "test-vpn", latency: float = 500.0,
                success: bool = True, bounce: bool = False,
                timestamp: str = "2026-02-12T14:00:00") -> DataPoint:
    return DataPoint(
        timestamp=timestamp,
        vpn_name=vpn,
        latency_ms=latency,
        success=success,
        bounce_triggered=bounce,
        assert_details=[
            AssertDetail(type="dns_lookup", latency_ms=latency * 0.1, success=success),
        ],
    )


class TestSeriesCreation:

    def test_ensure_vpn_series_creates_line(self, graph_widget):
        graph_widget._ensure_vpn_series("vpn-a")

        assert "vpn-a" in graph_widget._vpn_lines
        assert "vpn-a" in graph_widget._vpn_pass_scatter
        assert "vpn-a" in graph_widget._vpn_fail_scatter

    def test_ensure_vpn_series_idempotent(self, graph_widget):
        graph_widget._ensure_vpn_series("vpn-a")
        line1 = graph_widget._vpn_lines["vpn-a"]
        graph_widget._ensure_vpn_series("vpn-a")
        line2 = graph_widget._vpn_lines["vpn-a"]

        assert line1 is line2  # Same object, not recreated

    def test_multiple_vpns_get_different_colors(self, graph_widget):
        graph_widget._ensure_vpn_series("vpn-a")
        graph_widget._ensure_vpn_series("vpn-b")

        assert graph_widget._color_index == 2


class TestDataPointAddition:

    def test_add_single_point(self, graph_widget, collector):
        point = _make_point()
        collector.record(point)
        graph_widget.add_data_point(point)

        assert "test-vpn" in graph_widget._vpn_lines

    def test_add_points_for_multiple_vpns(self, graph_widget, collector):
        p1 = _make_point(vpn="vpn-a")
        p2 = _make_point(vpn="vpn-b")
        collector.record(p1)
        collector.record(p2)
        graph_widget.add_data_point(p1)
        graph_widget.add_data_point(p2)

        assert "vpn-a" in graph_widget._vpn_lines
        assert "vpn-b" in graph_widget._vpn_lines

    def test_add_bounce_point_creates_marker(self, graph_widget, collector):
        point = _make_point(success=False, bounce=True)
        collector.record(point)
        graph_widget.add_data_point(point)

        # Bounce markers are InfiniteLine + TextItem
        assert len(graph_widget._bounce_items) >= 2


class TestClear:

    def test_clear_all_removes_series(self, graph_widget, collector):
        point = _make_point()
        collector.record(point)
        graph_widget.add_data_point(point)

        assert "test-vpn" in graph_widget._vpn_lines

        graph_widget.clear_all()

        assert graph_widget._vpn_lines == {}
        assert graph_widget._vpn_pass_scatter == {}
        assert graph_widget._vpn_fail_scatter == {}
        assert graph_widget._bounce_items == []
        assert graph_widget._color_index == 0

    def test_clear_all_clears_collector(self, graph_widget, collector):
        collector.record(_make_point())
        graph_widget.add_data_point(_make_point())

        graph_widget.clear_all()

        assert collector.get_all_vpn_names() == []


class TestHistoricalDataLoad:

    def test_loads_existing_data_on_init(self, qapp, metrics_dir):
        # Pre-populate collector with data
        collector = MetricsCollector(metrics_dir=metrics_dir)
        collector.record(_make_point(vpn="historical-vpn", timestamp="2026-02-12T10:00:00"))
        collector.record(_make_point(vpn="historical-vpn", timestamp="2026-02-12T10:02:00"))

        # Create new widget — should auto-load historical data
        widget = MetricsGraphWidget(collector)

        assert "historical-vpn" in widget._vpn_lines


class TestDateAxisItem:

    def test_bottom_axis_is_date_axis(self, graph_widget):
        """X-axis uses DateAxisItem for human-readable time labels."""
        bottom_axis = graph_widget._plot_widget.getAxis('bottom')
        assert isinstance(bottom_axis, pg.DateAxisItem)

    def test_x_values_are_epoch_seconds(self, graph_widget, collector):
        """Data points are plotted using Unix epoch timestamps, not relative offsets."""
        p1 = _make_point(timestamp="2026-02-12T14:00:00")
        p2 = _make_point(timestamp="2026-02-12T14:02:00")
        collector.record(p1)
        collector.record(p2)
        graph_widget.add_data_point(p1)
        graph_widget.add_data_point(p2)

        line = graph_widget._vpn_lines["test-vpn"]
        x_data, _ = line.getData()

        # X values should be epoch timestamps (large numbers), not small offsets
        from datetime import datetime
        expected_first = datetime.fromisoformat("2026-02-12T14:00:00").timestamp()
        assert abs(x_data[0] - expected_first) < 1.0
