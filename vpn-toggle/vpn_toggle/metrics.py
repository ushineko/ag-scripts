"""
Metrics collection and persistence for VPN health check data.

Records per-check-cycle data points (latency, pass/fail, bounce events),
computes aggregate statistics, and persists history to disk.

Storage format: one JSON-Lines (.jsonl) file per VPN in ~/.config/vpn-toggle/metrics/.
Each line is a single serialized DataPoint. Writes are append-only (O(1)).
The file is periodically compacted to the bounded in-memory tail so disk
usage stays capped.

A crash mid-append at worst truncates the final (partial) line, not the
whole file. Compaction writes to a temp file and renames atomically.
"""
import json
import logging
import os
import threading
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from .utils import get_config_dir

logger = logging.getLogger('vpn_toggle.metrics')

MAX_DATA_POINTS = 10_000
# Compact the on-disk file every N appends. Keeps on-disk growth bounded
# to ~(MAX_DATA_POINTS + COMPACT_EVERY_N) lines between compactions.
COMPACT_EVERY_N = 500


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

    Storage: one .jsonl file per VPN in ~/.config/vpn-toggle/metrics/.
    """

    def __init__(self, metrics_dir: Optional[Path] = None):
        self._lock = threading.Lock()
        self._metrics_dir = metrics_dir or (get_config_dir() / "metrics")
        self._metrics_dir.mkdir(parents=True, exist_ok=True)

        self._data: dict[str, deque[DataPoint]] = {}
        self._appends_since_compact: dict[str, int] = {}
        self._load_all()

    # -- Public API --

    def record(self, data_point: DataPoint) -> None:
        """Record a new data point: append to disk, update in-memory tail."""
        with self._lock:
            vpn = data_point.vpn_name
            if vpn not in self._data:
                self._data[vpn] = deque(maxlen=MAX_DATA_POINTS)
                self._appends_since_compact[vpn] = 0
            self._data[vpn].append(data_point)

            self._append_line(vpn, data_point)

            self._appends_since_compact[vpn] += 1
            if self._appends_since_compact[vpn] >= COMPACT_EVERY_N:
                self._compact(vpn)
                self._appends_since_compact[vpn] = 0

    def get_data_points(self, vpn_name: str) -> list[DataPoint]:
        """Return a copy of all data points for a VPN."""
        with self._lock:
            return list(self._data.get(vpn_name, ()))

    def get_all_vpn_names(self) -> list[str]:
        """Return names of all VPNs that have recorded data."""
        with self._lock:
            return list(self._data.keys())

    def get_stats(self, vpn_name: str) -> Optional[AggregateStats]:
        """Compute aggregate statistics for a VPN. Returns None if no data."""
        with self._lock:
            points = self._data.get(vpn_name)
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
            self._appends_since_compact.clear()
            for pattern in ("*.jsonl", "*.json"):
                for f in self._metrics_dir.glob(pattern):
                    try:
                        f.unlink()
                    except OSError as e:
                        logger.warning(f"Failed to delete {f}: {e}")
            logger.info("All metrics history cleared")

    def clear_vpn(self, vpn_name: str) -> None:
        """Delete metrics data for a specific VPN."""
        with self._lock:
            self._data.pop(vpn_name, None)
            self._appends_since_compact.pop(vpn_name, None)
            for path in (self._vpn_file(vpn_name), self._legacy_vpn_file(vpn_name)):
                if path.exists():
                    try:
                        path.unlink()
                    except OSError as e:
                        logger.warning(f"Failed to delete {path}: {e}")
            logger.info(f"Metrics cleared for {vpn_name}")

    # -- Persistence --

    def _vpn_file(self, vpn_name: str) -> Path:
        safe_name = vpn_name.replace("/", "_").replace("\\", "_")
        return self._metrics_dir / f"{safe_name}.jsonl"

    def _legacy_vpn_file(self, vpn_name: str) -> Path:
        safe_name = vpn_name.replace("/", "_").replace("\\", "_")
        return self._metrics_dir / f"{safe_name}.json"

    def _append_line(self, vpn_name: str, point: DataPoint) -> None:
        """Append one record as a JSON line. Caller must hold _lock."""
        path = self._vpn_file(vpn_name)
        try:
            line = json.dumps(self._point_to_dict(point))
            with open(path, "a") as f:
                f.write(line + "\n")
        except OSError as e:
            logger.error(f"Failed to append metrics for {vpn_name}: {e}")

    def _compact(self, vpn_name: str) -> None:
        """Rewrite the .jsonl with only the in-memory (bounded) tail.

        Writes to a temp file and renames atomically so a crash mid-compact
        leaves the original file intact.
        """
        path = self._vpn_file(vpn_name)
        tmp = path.with_suffix(".jsonl.tmp")
        points = list(self._data[vpn_name])
        try:
            with open(tmp, "w") as f:
                for p in points:
                    f.write(json.dumps(self._point_to_dict(p)) + "\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
            logger.debug(f"Compacted {vpn_name}: {len(points)} points retained")
        except OSError as e:
            logger.error(f"Failed to compact metrics for {vpn_name}: {e}")
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass

    def _load_all(self) -> None:
        """Load all VPN metrics files from disk. Called once at init.

        Prefers .jsonl; if only a legacy .json exists for a VPN, migrate it.
        Skips any individual corrupt line rather than discarding the file.
        """
        for path in self._metrics_dir.glob("*.jsonl"):
            vpn_name = self._vpn_name_from_path(path)
            self._data[vpn_name] = self._load_jsonl(path)
            self._appends_since_compact[vpn_name] = 0

        for path in self._metrics_dir.glob("*.json"):
            vpn_name = self._vpn_name_from_path(path)
            if vpn_name in self._data:
                try:
                    path.unlink()
                except OSError:
                    pass
                continue
            migrated = self._migrate_legacy_json(path, vpn_name)
            if migrated is not None:
                self._data[vpn_name] = migrated
                self._appends_since_compact[vpn_name] = 0

    @staticmethod
    def _vpn_name_from_path(path: Path) -> str:
        return path.stem

    def _load_jsonl(self, path: Path) -> "deque[DataPoint]":
        """Read a .jsonl file, skipping blank or corrupt lines."""
        tail: deque[DataPoint] = deque(maxlen=MAX_DATA_POINTS)
        skipped = 0
        try:
            with open(path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        tail.append(self._dict_to_point(json.loads(line)))
                    except (json.JSONDecodeError, KeyError, TypeError):
                        skipped += 1
        except OSError as e:
            logger.warning(f"Failed to read {path}: {e}")
            return tail
        if skipped:
            logger.warning(f"Skipped {skipped} corrupt line(s) in {path.name}")
        logger.debug(f"Loaded {len(tail)} data points for {path.stem}")
        return tail

    def _migrate_legacy_json(self, legacy_path: Path, vpn_name: str) -> Optional["deque[DataPoint]"]:
        """Convert a legacy {vpn}.json file to {vpn}.jsonl and delete the old file."""
        try:
            with open(legacy_path, "r") as f:
                payload = json.load(f)
            raw_points = payload.get("data_points", [])
        except (json.JSONDecodeError, KeyError, OSError) as e:
            logger.warning(f"Skipping corrupt legacy metrics file {legacy_path}: {e}")
            return None

        tail: deque[DataPoint] = deque(maxlen=MAX_DATA_POINTS)
        for d in raw_points:
            try:
                tail.append(self._dict_to_point(d))
            except (KeyError, TypeError):
                continue

        new_path = self._vpn_file(vpn_name)
        try:
            with open(new_path, "w") as f:
                for p in tail:
                    f.write(json.dumps(self._point_to_dict(p)) + "\n")
            legacy_path.unlink()
            logger.info(f"Migrated {legacy_path.name} → {new_path.name} ({len(tail)} points)")
        except OSError as e:
            logger.warning(f"Failed to migrate {legacy_path}: {e}")
            return None
        return tail

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
