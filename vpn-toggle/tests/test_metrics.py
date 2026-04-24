"""
Tests for MetricsCollector
"""
import json
import pytest
import tempfile
from pathlib import Path

from vpn_toggle.metrics import (
    MetricsCollector, DataPoint, AssertDetail, AggregateStats,
)


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
            AssertDetail(type="geolocation", latency_ms=latency * 0.9, success=success),
        ],
    )


@pytest.fixture
def metrics_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "metrics"


@pytest.fixture
def collector(metrics_dir):
    return MetricsCollector(metrics_dir=metrics_dir)


class TestRecordAndRetrieve:

    def test_record_single_point(self, collector):
        point = _make_point()
        collector.record(point)

        points = collector.get_data_points("test-vpn")
        assert len(points) == 1
        assert points[0].latency_ms == 500.0
        assert points[0].success is True

    def test_record_multiple_points(self, collector):
        for i in range(5):
            collector.record(_make_point(latency=100.0 * (i + 1)))

        points = collector.get_data_points("test-vpn")
        assert len(points) == 5
        assert points[0].latency_ms == 100.0
        assert points[4].latency_ms == 500.0

    def test_record_multiple_vpns(self, collector):
        collector.record(_make_point(vpn="vpn-a", latency=100.0))
        collector.record(_make_point(vpn="vpn-b", latency=200.0))

        assert len(collector.get_data_points("vpn-a")) == 1
        assert len(collector.get_data_points("vpn-b")) == 1

    def test_get_data_points_unknown_vpn_returns_empty(self, collector):
        assert collector.get_data_points("nonexistent") == []

    def test_get_all_vpn_names(self, collector):
        collector.record(_make_point(vpn="alpha"))
        collector.record(_make_point(vpn="beta"))

        names = collector.get_all_vpn_names()
        assert sorted(names) == ["alpha", "beta"]

    def test_get_all_vpn_names_empty(self, collector):
        assert collector.get_all_vpn_names() == []

    def test_assert_details_preserved(self, collector):
        point = _make_point(latency=1000.0)
        collector.record(point)

        retrieved = collector.get_data_points("test-vpn")[0]
        assert len(retrieved.assert_details) == 2
        assert retrieved.assert_details[0].type == "dns_lookup"
        assert retrieved.assert_details[0].latency_ms == 100.0
        assert retrieved.assert_details[1].type == "geolocation"
        assert retrieved.assert_details[1].latency_ms == 900.0

    def test_bounce_triggered_preserved(self, collector):
        collector.record(_make_point(bounce=True, success=False))
        retrieved = collector.get_data_points("test-vpn")[0]
        assert retrieved.bounce_triggered is True
        assert retrieved.success is False


class TestAggregateStats:

    def test_stats_no_data_returns_none(self, collector):
        assert collector.get_stats("nonexistent") is None

    def test_stats_all_passing(self, collector):
        for i in range(10):
            collector.record(_make_point(latency=100.0 * (i + 1)))

        stats = collector.get_stats("test-vpn")
        assert stats.total_checks == 10
        assert stats.total_failures == 0
        assert stats.avg_latency_ms == 550.0
        assert stats.uptime_pct == 100.0

    def test_stats_with_failures(self, collector):
        for i in range(8):
            collector.record(_make_point(latency=500.0, success=True))
        for i in range(2):
            collector.record(_make_point(latency=1500.0, success=False))

        stats = collector.get_stats("test-vpn")
        assert stats.total_checks == 10
        assert stats.total_failures == 2
        assert stats.uptime_pct == 80.0
        # avg = (8*500 + 2*1500) / 10 = 700
        assert stats.avg_latency_ms == 700.0

    def test_stats_single_point(self, collector):
        collector.record(_make_point(latency=42.0))

        stats = collector.get_stats("test-vpn")
        assert stats.total_checks == 1
        assert stats.total_failures == 0
        assert stats.avg_latency_ms == 42.0
        assert stats.uptime_pct == 100.0

    def test_stats_all_failures(self, collector):
        for _ in range(5):
            collector.record(_make_point(success=False))

        stats = collector.get_stats("test-vpn")
        assert stats.total_failures == 5
        assert stats.uptime_pct == 0.0


class TestPersistence:

    def test_save_and_reload(self, metrics_dir):
        collector1 = MetricsCollector(metrics_dir=metrics_dir)
        collector1.record(_make_point(vpn="persist-vpn", latency=123.4))
        collector1.record(_make_point(vpn="persist-vpn", latency=567.8, success=False, bounce=True))

        # Create a new collector that loads from the same directory
        collector2 = MetricsCollector(metrics_dir=metrics_dir)
        points = collector2.get_data_points("persist-vpn")

        assert len(points) == 2
        assert points[0].latency_ms == 123.4
        assert points[0].success is True
        assert points[1].latency_ms == 567.8
        assert points[1].success is False
        assert points[1].bounce_triggered is True

    def test_save_and_reload_assert_details(self, metrics_dir):
        collector1 = MetricsCollector(metrics_dir=metrics_dir)
        collector1.record(_make_point(vpn="detail-vpn", latency=1000.0))

        collector2 = MetricsCollector(metrics_dir=metrics_dir)
        points = collector2.get_data_points("detail-vpn")
        assert len(points[0].assert_details) == 2
        assert points[0].assert_details[0].type == "dns_lookup"

    def test_corrupt_legacy_file_skipped(self, metrics_dir):
        metrics_dir.mkdir(parents=True, exist_ok=True)
        corrupt_file = metrics_dir / "bad.json"
        corrupt_file.write_text("{invalid json")

        collector = MetricsCollector(metrics_dir=metrics_dir)
        assert collector.get_all_vpn_names() == []

    def test_corrupt_lines_in_jsonl_are_skipped(self, metrics_dir):
        metrics_dir.mkdir(parents=True, exist_ok=True)
        good = json.dumps({
            "timestamp": "2026-02-12T14:00:00",
            "vpn_name": "partial-vpn",
            "latency_ms": 100.0,
            "success": True,
            "bounce_triggered": False,
            "assert_details": [],
        })
        (metrics_dir / "partial-vpn.jsonl").write_text(good + "\n{truncated line")

        collector = MetricsCollector(metrics_dir=metrics_dir)
        points = collector.get_data_points("partial-vpn")
        assert len(points) == 1
        assert points[0].latency_ms == 100.0

    def test_empty_dir_loads_cleanly(self, metrics_dir):
        collector = MetricsCollector(metrics_dir=metrics_dir)
        assert collector.get_all_vpn_names() == []

    def test_file_per_vpn(self, metrics_dir):
        collector = MetricsCollector(metrics_dir=metrics_dir)
        collector.record(_make_point(vpn="vpn-a"))
        collector.record(_make_point(vpn="vpn-b"))

        files = sorted(f.name for f in metrics_dir.glob("*.jsonl"))
        assert files == ["vpn-a.jsonl", "vpn-b.jsonl"]

    def test_vpn_name_with_slashes_sanitized(self, metrics_dir):
        collector = MetricsCollector(metrics_dir=metrics_dir)
        collector.record(_make_point(vpn="corp/vpn"))

        files = list(metrics_dir.glob("*.jsonl"))
        assert len(files) == 1
        assert "corp_vpn.jsonl" in files[0].name

    def test_legacy_json_migrated_on_load(self, metrics_dir):
        metrics_dir.mkdir(parents=True, exist_ok=True)
        legacy = {
            "vpn_name": "legacy-vpn",
            "created": "2026-04-01T00:00:00",
            "data_points": [
                {
                    "timestamp": "2026-04-01T00:00:00",
                    "vpn_name": "legacy-vpn",
                    "latency_ms": 42.0,
                    "success": True,
                    "bounce_triggered": False,
                    "assert_details": [],
                },
            ],
        }
        (metrics_dir / "legacy-vpn.json").write_text(json.dumps(legacy))

        collector = MetricsCollector(metrics_dir=metrics_dir)
        points = collector.get_data_points("legacy-vpn")
        assert len(points) == 1
        assert points[0].latency_ms == 42.0
        assert (metrics_dir / "legacy-vpn.jsonl").exists()
        assert not (metrics_dir / "legacy-vpn.json").exists()

    def test_append_only_writes_one_line_per_record(self, metrics_dir):
        collector = MetricsCollector(metrics_dir=metrics_dir)
        for i in range(5):
            collector.record(_make_point(vpn="append-vpn", latency=float(i)))

        path = metrics_dir / "append-vpn.jsonl"
        lines = [ln for ln in path.read_text().splitlines() if ln]
        assert len(lines) == 5
        for i, line in enumerate(lines):
            parsed = json.loads(line)
            assert parsed["latency_ms"] == float(i)

    def test_compaction_rewrites_file_with_bounded_tail(self, metrics_dir, monkeypatch):
        monkeypatch.setattr("vpn_toggle.metrics.MAX_DATA_POINTS", 10)
        monkeypatch.setattr("vpn_toggle.metrics.COMPACT_EVERY_N", 5)

        collector = MetricsCollector(metrics_dir=metrics_dir)
        for i in range(20):
            collector.record(_make_point(vpn="compact-vpn", latency=float(i)))

        path = metrics_dir / "compact-vpn.jsonl"
        lines = [ln for ln in path.read_text().splitlines() if ln]
        # After the last compaction, on-disk size equals in-memory tail (<= MAX_DATA_POINTS)
        assert len(lines) <= 10
        # Freshest points are retained; oldest are dropped
        newest = json.loads(lines[-1])
        assert newest["latency_ms"] == 19.0

    def test_stats_survive_reload(self, metrics_dir):
        collector1 = MetricsCollector(metrics_dir=metrics_dir)
        for i in range(5):
            collector1.record(_make_point(vpn="stats-vpn", latency=100.0 * (i + 1)))

        collector2 = MetricsCollector(metrics_dir=metrics_dir)
        stats = collector2.get_stats("stats-vpn")
        assert stats.total_checks == 5
        assert stats.avg_latency_ms == 300.0


class TestClear:

    def test_clear_all(self, collector, metrics_dir):
        collector.record(_make_point(vpn="vpn-a"))
        collector.record(_make_point(vpn="vpn-b"))

        collector.clear_all()

        assert collector.get_all_vpn_names() == []
        assert collector.get_data_points("vpn-a") == []
        assert collector.get_data_points("vpn-b") == []
        assert list(metrics_dir.glob("*.json")) == []

    def test_clear_vpn(self, collector, metrics_dir):
        collector.record(_make_point(vpn="vpn-a"))
        collector.record(_make_point(vpn="vpn-b"))

        collector.clear_vpn("vpn-a")

        assert collector.get_data_points("vpn-a") == []
        assert len(collector.get_data_points("vpn-b")) == 1
        assert not (metrics_dir / "vpn-a.jsonl").exists()
        assert (metrics_dir / "vpn-b.jsonl").exists()

    def test_clear_nonexistent_vpn_no_error(self, collector):
        collector.clear_vpn("does-not-exist")  # Should not raise

    def test_clear_all_resets_stats(self, collector):
        collector.record(_make_point())
        assert collector.get_stats("test-vpn") is not None

        collector.clear_all()
        assert collector.get_stats("test-vpn") is None


class TestBoundedHistory:

    def test_in_memory_history_bounded_to_max(self, metrics_dir, monkeypatch):
        monkeypatch.setattr("vpn_toggle.metrics.MAX_DATA_POINTS", 50)

        collector = MetricsCollector(metrics_dir=metrics_dir)
        for i in range(75):
            collector.record(_make_point(
                vpn="trim-vpn",
                latency=float(i),
                timestamp=f"2026-02-12T{i:05d}",
            ))

        points = collector.get_data_points("trim-vpn")
        assert len(points) == 50
        # Newest 50 retained (25..74); oldest 25 (0..24) dropped
        assert points[0].latency_ms == 25.0
        assert points[-1].latency_ms == 74.0

    def test_no_drop_under_max(self, collector):
        for i in range(100):
            collector.record(_make_point(latency=float(i)))

        assert len(collector.get_data_points("test-vpn")) == 100
