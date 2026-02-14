"""
Metrics collection and persistence for VPN health check data.

Records per-check-cycle data points (latency, pass/fail, bounce events),
computes aggregate statistics, and persists history to disk.
"""
import json
import logging
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from .utils import get_config_dir

logger = logging.getLogger('vpn_toggle.metrics')

MAX_DATA_POINTS = 10_000
TRIM_PERCENTAGE = 0.10


@dataclass
class AssertDetail:
    """Latency and result for a single assert within a check cycle."""
    type: str
    latency_ms: float
    success: bool


@dataclass
class DataPoint:
    """One check cycle result for a single VPN."""
    timestamp: str
    vpn_name: str
    latency_ms: float
    success: bool
    bounce_triggered: bool
    assert_details: list[AssertDetail] = field(default_factory=list)


@dataclass
class AggregateStats:
    """Computed statistics for a VPN's metrics history."""
    total_checks: int
    total_failures: int
    avg_latency_ms: float
    uptime_pct: float


class MetricsCollector:
    """
    Thread-safe metrics collector that records, aggregates, and persists
    VPN health check data.

    Storage: one JSON file per VPN in ~/.config/vpn-toggle/metrics/
    """

    def __init__(self, metrics_dir: Optional[Path] = None):
        self._lock = threading.Lock()
        self._metrics_dir = metrics_dir or (get_config_dir() / "metrics")
        self._metrics_dir.mkdir(parents=True, exist_ok=True)

        # In-memory store: vpn_name -> list[DataPoint]
        self._data: dict[str, list[DataPoint]] = {}
        self._load_all()

    # -- Public API --

    def record(self, data_point: DataPoint) -> None:
        """Record a new data point and persist to disk."""
        with self._lock:
            vpn = data_point.vpn_name
            if vpn not in self._data:
                self._data[vpn] = []
            self._data[vpn].append(data_point)
            self._trim(vpn)
            self._save_vpn(vpn)

    def get_data_points(self, vpn_name: str) -> list[DataPoint]:
        """Return a copy of all data points for a VPN."""
        with self._lock:
            return list(self._data.get(vpn_name, []))

    def get_all_vpn_names(self) -> list[str]:
        """Return names of all VPNs that have recorded data."""
        with self._lock:
            return list(self._data.keys())

    def get_stats(self, vpn_name: str) -> Optional[AggregateStats]:
        """Compute aggregate statistics for a VPN. Returns None if no data."""
        with self._lock:
            points = self._data.get(vpn_name, [])
            if not points:
                return None

            total = len(points)
            failures = sum(1 for p in points if not p.success)
            avg_lat = sum(p.latency_ms for p in points) / total
            uptime = (total - failures) / total * 100.0

            return AggregateStats(
                total_checks=total,
                total_failures=failures,
                avg_latency_ms=round(avg_lat, 1),
                uptime_pct=round(uptime, 1),
            )

    def clear_all(self) -> None:
        """Delete all metrics data from memory and disk."""
        with self._lock:
            self._data.clear()
            for f in self._metrics_dir.glob("*.json"):
                try:
                    f.unlink()
                except OSError as e:
                    logger.warning(f"Failed to delete {f}: {e}")
            logger.info("All metrics history cleared")

    def clear_vpn(self, vpn_name: str) -> None:
        """Delete metrics data for a specific VPN."""
        with self._lock:
            self._data.pop(vpn_name, None)
            path = self._vpn_file(vpn_name)
            if path.exists():
                try:
                    path.unlink()
                except OSError as e:
                    logger.warning(f"Failed to delete {path}: {e}")
            logger.info(f"Metrics cleared for {vpn_name}")

    # -- Persistence --

    def _vpn_file(self, vpn_name: str) -> Path:
        safe_name = vpn_name.replace("/", "_").replace("\\", "_")
        return self._metrics_dir / f"{safe_name}.json"

    def _save_vpn(self, vpn_name: str) -> None:
        """Save a single VPN's data to disk. Caller must hold _lock."""
        points = self._data.get(vpn_name, [])
        payload = {
            "vpn_name": vpn_name,
            "created": datetime.now().isoformat(),
            "data_points": [self._point_to_dict(p) for p in points],
        }
        path = self._vpn_file(vpn_name)
        try:
            with open(path, "w") as f:
                json.dump(payload, f, indent=2)
        except OSError as e:
            logger.error(f"Failed to save metrics for {vpn_name}: {e}")

    def _load_all(self) -> None:
        """Load all VPN metrics files from disk. Called once at init."""
        for path in self._metrics_dir.glob("*.json"):
            try:
                with open(path, "r") as f:
                    payload = json.load(f)
                vpn_name = payload["vpn_name"]
                points = [self._dict_to_point(d) for d in payload.get("data_points", [])]
                self._data[vpn_name] = points
                logger.debug(f"Loaded {len(points)} data points for {vpn_name}")
            except (json.JSONDecodeError, KeyError, OSError) as e:
                logger.warning(f"Skipping corrupt metrics file {path}: {e}")

    # -- Trimming --

    def _trim(self, vpn_name: str) -> None:
        """FIFO-trim data if over MAX_DATA_POINTS. Caller must hold _lock."""
        points = self._data.get(vpn_name, [])
        if len(points) > MAX_DATA_POINTS:
            drop = int(MAX_DATA_POINTS * TRIM_PERCENTAGE)
            self._data[vpn_name] = points[drop:]
            logger.debug(f"Trimmed {drop} oldest points for {vpn_name}")

    # -- Serialization helpers --

    @staticmethod
    def _point_to_dict(point: DataPoint) -> dict:
        return {
            "timestamp": point.timestamp,
            "vpn_name": point.vpn_name,
            "latency_ms": point.latency_ms,
            "success": point.success,
            "bounce_triggered": point.bounce_triggered,
            "assert_details": [asdict(a) for a in point.assert_details],
        }

    @staticmethod
    def _dict_to_point(d: dict) -> DataPoint:
        details = [
            AssertDetail(
                type=a["type"],
                latency_ms=a["latency_ms"],
                success=a["success"],
            )
            for a in d.get("assert_details", [])
        ]
        return DataPoint(
            timestamp=d["timestamp"],
            vpn_name=d["vpn_name"],
            latency_ms=d["latency_ms"],
            success=d["success"],
            bounce_triggered=d["bounce_triggered"],
            assert_details=details,
        )
