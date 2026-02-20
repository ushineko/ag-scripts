#!/usr/bin/env python3
"""DHCP Lease Monitor widget."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime
import json
import logging
import logging.config
from pathlib import Path
import signal
import subprocess
import sys
import time

import faulthandler
from PyQt6.QtCore import (
    QDir,
    QEvent,
    QObject,
    QPoint,
    QLockFile,
    QSocketNotifier,
    QThread,
    QTimer,
    Qt,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import QAction, QActionGroup, QContextMenuEvent, QIcon, QMouseEvent, QGuiApplication, QCursor
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
import structlog

from device_identifier import DeviceIdentifier, display_device_type
from lease_reader import (
    DEFAULT_LEASE_FILE,
    DhcpLease,
    detect_interface_for_leases,
    format_time_remaining,
    load_leases,
)

try:
    from inotify_simple import INotify, flags
except ImportError:  # pragma: no cover - optional runtime dependency
    INotify = None
    flags = None


__version__ = "1.1.1"

APP_ID = "dhcp-lease-monitor"
CONFIG_PATH = Path.home() / ".config" / f"{APP_ID}.json"
STATE_DIR = Path.home() / ".local" / "state" / APP_ID
LOG_PATH = STATE_DIR / "dhcp_lease_monitor.log"
STDERR_LOG_PATH = STATE_DIR / "stderr.log"
CRASH_LOG_PATH = STATE_DIR / "crash.log"

DEFAULT_SETTINGS = {
    "opacity": 0.95,
    "font_scale": 1.0,
    "lease_file": DEFAULT_LEASE_FILE,
    "lease_duration_hours": 24,
    "show_expired": True,
}

_stderr_handle = None
_crash_handle = None


def _ensure_state_dirs() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)


def setup_logging(debug_mode: bool) -> structlog.stdlib.BoundLogger:
    _ensure_state_dirs()
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processor": structlog.processors.JSONRenderer(),
                },
                "console": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processor": structlog.dev.ConsoleRenderer(colors=True),
                },
            },
            "handlers": {
                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "filename": str(LOG_PATH),
                    "maxBytes": 5 * 1024 * 1024,
                    "backupCount": 1,
                    "formatter": "json",
                    "level": "DEBUG",
                },
                "console": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                    "formatter": "console",
                    "level": "DEBUG" if debug_mode else "INFO",
                },
            },
            "root": {
                "handlers": ["file", "console"],
                "level": "DEBUG",
            },
        }
    )

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    return structlog.get_logger()


def redirect_stderr() -> None:
    global _stderr_handle
    _ensure_state_dirs()
    _stderr_handle = open(STDERR_LOG_PATH, "a", encoding="utf-8", buffering=1)
    sys.stderr = _stderr_handle


def enable_fault_handler() -> None:
    global _crash_handle
    _ensure_state_dirs()
    _crash_handle = open(CRASH_LOG_PATH, "a", encoding="utf-8", buffering=1)
    faulthandler.enable(file=_crash_handle, all_threads=True)


def load_settings() -> dict:
    settings = DEFAULT_SETTINGS.copy()
    if CONFIG_PATH.exists():
        try:
            loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                settings.update(loaded)
        except (json.JSONDecodeError, OSError):
            pass
    save_settings(settings)
    return settings


def save_settings(settings: dict) -> None:
    _ensure_state_dirs()
    CONFIG_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def format_local_timestamp(epoch: int | None) -> str:
    if epoch is None:
        return "Not available"
    return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")


class HeaderFrame(QFrame):
    """Header frame that acts as the drag handle."""

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.window().windowHandle()
            if handle is not None:
                handle.startSystemMove()
                event.accept()
                return
        super().mousePressEvent(event)


class LeaseRow(QFrame):
    clicked = pyqtSignal(object, object)  # lease, global_pos
    right_clicked = pyqtSignal(object, object)  # lease, global_pos

    def __init__(self, lease: DhcpLease, font_scale: float, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.lease = lease
        self.font_scale = font_scale
        self._hover = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        line1 = QHBoxLayout()
        line1.setSpacing(8)
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(20, 20)
        icon = QIcon.fromTheme(self.lease.icon_name)
        if icon.isNull():
            icon = QIcon.fromTheme("network-wired")
        self.icon_label.setPixmap(icon.pixmap(20, 20))

        self.name_label = QLabel(self.lease.hostname)
        self.name_label.setObjectName("rowName")
        self.ip_label = QLabel(self.lease.ip)
        self.ip_label.setObjectName("rowIp")

        line1.addWidget(self.icon_label)
        line1.addWidget(self.name_label, 1)
        line1.addWidget(self.ip_label, 0, Qt.AlignmentFlag.AlignRight)

        line2 = QHBoxLayout()
        line2.setSpacing(8)
        self.mac_label = QLabel(self.lease.mac)
        self.mac_label.setObjectName("rowMac")
        self.time_label = QLabel(self._time_text())
        self.time_label.setObjectName("rowTime")
        line2.addWidget(self.mac_label, 1)
        line2.addWidget(self.time_label, 0, Qt.AlignmentFlag.AlignRight)

        line3 = QHBoxLayout()
        line3.setSpacing(8)
        self.reverse_dns_label = QLabel()
        self.reverse_dns_label.setObjectName("rowReverseDns")
        self.reverse_dns_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        line3.addWidget(self.reverse_dns_label, 1)

        layout.addLayout(line1)
        layout.addLayout(line2)
        layout.addLayout(line3)
        self._apply_style()
        self._refresh_reverse_dns_label()

    def _time_text(self) -> str:
        if self.lease.is_static:
            return "FIXED (static)"
        return format_time_remaining(self.lease, include_seconds=False)

    def _reverse_dns_text(self) -> str:
        if self.lease.reverse_dns:
            return f"PTR: {self.lease.reverse_dns}"
        return "PTR: not found"

    def _refresh_reverse_dns_label(self) -> None:
        full_text = self._reverse_dns_text()
        available_width = max(60, self.reverse_dns_label.width())
        metrics = self.reverse_dns_label.fontMetrics()
        elided = metrics.elidedText(full_text, Qt.TextElideMode.ElideRight, available_width)
        self.reverse_dns_label.setText(elided)
        self.reverse_dns_label.setToolTip(full_text if elided != full_text else "")

    def _apply_style(self) -> None:
        base_name_px = max(11, int(14 * self.font_scale))
        meta_px = max(10, int(12 * self.font_scale))
        rdns_px = max(9, int(11 * self.font_scale))

        if self.lease.is_static:
            bg = "rgba(88, 166, 255, 0.14)"
            name_color = "#b7d8ff"
            time_color = "#7dd3fc"
            rdns_color = "#8cb4ff"
        elif self.lease.is_expired:
            bg = "rgba(255, 255, 255, 0.02)"
            name_color = "#7d8590"
            time_color = "#ff6b6b"
            rdns_color = "#6e7681"
        else:
            bg = "rgba(255, 255, 255, 0.03)"
            name_color = "#e6edf3"
            time_color = "#c9d1d9"
            rdns_color = "#8b949e"

        if self._hover:
            bg = "rgba(255, 255, 255, 0.08)"

        expired_extra = "text-decoration: line-through;" if self.lease.is_expired else ""

        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {bg};
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 8px;
            }}
            QLabel#rowName {{
                color: {name_color};
                font-size: {base_name_px}px;
                font-weight: 600;
                {expired_extra}
            }}
            QLabel#rowIp {{
                color: #d0d7de;
                font-size: {meta_px}px;
            }}
            QLabel#rowMac {{
                color: #8b949e;
                font-family: monospace;
                font-size: {meta_px}px;
                {expired_extra}
            }}
            QLabel#rowTime {{
                color: {time_color};
                font-size: {meta_px}px;
                font-weight: 600;
            }}
            QLabel#rowReverseDns {{
                color: {rdns_color};
                font-size: {rdns_px}px;
            }}
            """
        )
        self._refresh_reverse_dns_label()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._refresh_reverse_dns_label()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self._apply_style()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self._apply_style()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        global_pos = event.globalPosition().toPoint()
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.lease, global_pos)
            event.accept()
            return
        if event.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit(self.lease, global_pos)
            event.accept()
            return
        super().mousePressEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        # Prevent parent widget context menu from hijacking row right-click.
        event.accept()


class LeaseDetailPopup(QFrame):
    """Top-level popup frame that dismisses on outside click."""

    def __init__(self) -> None:
        # Qt.Popup is unreliable for custom-positioned widgets on Wayland.
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setObjectName("detailPopup")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._lease: DhcpLease | None = None
        self._lease_duration_hours = 24

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("Lease Details")
        title.setObjectName("popupTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(5)
        layout.addLayout(grid)

        self._value_labels: dict[str, QLabel] = {}
        fields = [
            ("hostname", "Hostname"),
            ("ip", "IP Address"),
            ("reverse_dns", "Reverse DNS"),
            ("mac", "MAC Address"),
            ("mac_type", "MAC Type"),
            ("vendor", "OUI Vendor"),
            ("device_type", "Device Type"),
            ("granted", "Lease Granted"),
            ("expires", "Lease Expires"),
            ("remaining", "Time Remaining"),
            ("client_id", "Client ID"),
        ]

        for row, (key, title_text) in enumerate(fields):
            key_label = QLabel(f"{title_text}:")
            key_label.setObjectName("popupKey")
            value_label = QLabel("")
            value_label.setObjectName("popupValue")
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            if key in {"mac", "client_id"}:
                value_label.setProperty("monospace", True)
            grid.addWidget(key_label, row, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(value_label, row, 1, Qt.AlignmentFlag.AlignTop)
            self._value_labels[key] = value_label

        self.setStyleSheet(
            """
            QFrame#detailPopup {
                background-color: rgba(22, 27, 34, 0.98);
                border: 1px solid rgba(240, 246, 252, 0.2);
                border-radius: 10px;
            }
            QLabel#popupTitle {
                color: #f0f6fc;
                font-size: 13px;
                font-weight: 700;
            }
            QLabel#popupKey {
                color: #8b949e;
                font-size: 11px;
                font-weight: 600;
            }
            QLabel#popupValue {
                color: #c9d1d9;
                font-size: 11px;
            }
            QLabel[monospace="true"] {
                font-family: monospace;
            }
            """
        )

    def show_for_lease(self, lease: DhcpLease, anchor_point: QPoint, lease_duration_hours: int) -> None:
        self._lease = lease
        self._lease_duration_hours = lease_duration_hours
        self._refresh_labels()
        self.adjustSize()

        target_screen = QGuiApplication.screenAt(anchor_point)
        if target_screen is None:
            target_screen = QApplication.primaryScreen()
        if target_screen is None:
            return
        geometry = target_screen.availableGeometry()

        x = anchor_point.x() + 12
        y = anchor_point.y() + 10
        if x + self.width() > geometry.right():
            x = anchor_point.x() - self.width() - 12
        if x < geometry.left():
            x = geometry.left() + 8
        if y + self.height() > geometry.bottom():
            y = geometry.bottom() - self.height() - 8
        if y < geometry.top():
            y = geometry.top() + 8

        self.move(QPoint(x, y))
        self.show()
        self.raise_()
        self._timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        super().hideEvent(event)

    def _on_tick(self) -> None:
        if not self.isVisible() or self._lease is None:
            self._timer.stop()
            return
        self._refresh_labels()

    def _refresh_labels(self) -> None:
        if self._lease is None:
            return

        lease = self._lease
        now = int(time.time())
        hostname_value = lease.hostname if lease.raw_hostname != "*" else "Not provided"
        client_id_value = lease.client_id if lease.client_id else "Not provided"
        reverse_dns_value = lease.reverse_dns if lease.reverse_dns else "No PTR record"

        if lease.is_static:
            expires_text = "Never (static lease)"
            granted_text = "Static lease"
            remaining_text = "Static / infinite"
        else:
            remaining = max(0, lease.expiry - now)
            expires_text = format_local_timestamp(lease.expiry)
            granted_ts = lease.expiry - int(self._lease_duration_hours * 3600)
            granted_text = format_local_timestamp(granted_ts)
            if remaining <= 0:
                remaining_text = "Expired"
            else:
                hours, rem = divmod(remaining, 3600)
                minutes, seconds = divmod(rem, 60)
                remaining_text = f"{hours}h {minutes}m {seconds}s"

        self._value_labels["hostname"].setText(hostname_value)
        self._value_labels["ip"].setText(lease.ip)
        self._value_labels["reverse_dns"].setText(reverse_dns_value)
        self._value_labels["mac"].setText(lease.mac)
        self._value_labels["mac_type"].setText(lease.mac_type)
        self._value_labels["vendor"].setText(lease.vendor)
        self._value_labels["device_type"].setText(f"{display_device_type(lease.device_type)} (inferred)")
        self._value_labels["granted"].setText(granted_text)
        self._value_labels["expires"].setText(expires_text)
        self._value_labels["remaining"].setText(remaining_text)
        self._value_labels["client_id"].setText(client_id_value)


class LeaseRefreshWorker(QObject):
    """Background worker that keeps lease refresh work off the UI thread."""

    refresh_ready = pyqtSignal(int, object, str, bool)  # request_id, leases, interface, include_expired
    refresh_failed = pyqtSignal(int, str)  # request_id, error

    def __init__(self) -> None:
        super().__init__()
        self.log = structlog.get_logger().bind(component="refresh_worker")
        self.identifier = DeviceIdentifier()
        self._pending: tuple[int, str, bool] | None = None
        self._busy = False
        self._reverse_dns_cache: dict[str, tuple[str | None, float]] = {}
        self._reverse_dns_positive_ttl = 600.0
        self._reverse_dns_negative_ttl = 120.0
        self._reverse_dns_timeout = 0.45

    @pyqtSlot(int, str, bool)
    def queue_refresh(self, request_id: int, lease_file: str, include_expired: bool) -> None:
        # Keep only the latest pending request while one refresh is in flight.
        self._pending = (request_id, lease_file, include_expired)
        if not self._busy:
            self._process_pending()

    def _process_pending(self) -> None:
        while self._pending is not None:
            request_id, lease_file, include_expired = self._pending
            self._pending = None
            self._busy = True
            try:
                leases = load_leases(
                    lease_file=lease_file,
                    identifier=self.identifier,
                    include_expired=include_expired,
                )
                leases = self._with_reverse_dns(leases)
                interface = detect_interface_for_leases(leases)
            except Exception as exc:
                self.log.warning(
                    "refresh_failed",
                    request_id=request_id,
                    lease_file=lease_file,
                    error=str(exc),
                )
                self.refresh_failed.emit(request_id, str(exc))
            else:
                self.refresh_ready.emit(request_id, leases, interface, include_expired)
            finally:
                self._busy = False

    def _with_reverse_dns(self, leases: list[DhcpLease]) -> list[DhcpLease]:
        if not leases:
            return leases

        lookups: dict[str, str | None] = {}
        for lease in leases:
            if lease.ip not in lookups:
                lookups[lease.ip] = self._resolve_reverse_dns(lease.ip)

        enriched: list[DhcpLease] = []
        for lease in leases:
            reverse_dns = lookups[lease.ip]
            if lease.reverse_dns == reverse_dns:
                enriched.append(lease)
                continue
            enriched.append(replace(lease, reverse_dns=reverse_dns))
        return enriched

    def _resolve_reverse_dns(self, ip: str) -> str | None:
        now = time.monotonic()
        cached = self._reverse_dns_cache.get(ip)
        if cached is not None:
            value, valid_until = cached
            if now < valid_until:
                return value

        resolved = self._lookup_reverse_dns(ip)
        ttl = self._reverse_dns_positive_ttl if resolved else self._reverse_dns_negative_ttl
        self._reverse_dns_cache[ip] = (resolved, now + ttl)
        return resolved

    def _lookup_reverse_dns(self, ip: str) -> str | None:
        # Keep PTR resolution strictly timeout-bounded in the worker.
        try:
            completed = subprocess.run(
                ["getent", "hosts", ip],
                capture_output=True,
                text=True,
                check=False,
                timeout=self._reverse_dns_timeout,
            )
        except (OSError, subprocess.SubprocessError):
            return None

        if completed.returncode != 0:
            return None

        parts = completed.stdout.split()
        if len(parts) < 2:
            return None

        hostname = parts[1].rstrip(".")
        if hostname and hostname != ip:
            return hostname
        return None


class DhcpLeaseMonitor(QWidget):
    refresh_requested = pyqtSignal(int, str, bool)  # request_id, lease_file, include_expired

    def __init__(self, cli_lease_file: str | None, debug: bool = False) -> None:
        super().__init__()
        self.log = structlog.get_logger().bind(component="widget")
        self.settings = load_settings()
        self.cli_lease_file = cli_lease_file
        self.leases: list[DhcpLease] = []
        self.detail_popup = LeaseDetailPopup()
        self._active_menu: QMenu | None = None
        self._refresh_request_id = 0
        self._menu_stylesheet = """
            QMenu {
                background-color: rgba(22, 27, 34, 0.98);
                color: #c9d1d9;
                border: 1px solid rgba(240, 246, 252, 0.20);
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 18px 6px 10px;
                border-radius: 6px;
            }
            QMenu::item:selected {
                background-color: rgba(255, 255, 255, 0.10);
            }
            QMenu::separator {
                height: 1px;
                background: rgba(240, 246, 252, 0.12);
                margin: 4px 6px;
            }
        """
        self._inotify = None
        self._inotify_notifier: QSocketNotifier | None = None
        self._watched_filename: str | None = None

        self.setWindowTitle("DHCP Lease Monitor")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Qt.Tool windows do not quit the app on close by default.
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, True)
        self.setMinimumWidth(320)
        self.setMaximumHeight(600)
        self.setWindowOpacity(float(self.settings["opacity"]))

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(8, 8, 8, 8)

        self.container = QFrame()
        self.container.setObjectName("container")
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(8, 8, 8, 8)
        container_layout.setSpacing(8)

        self.header = HeaderFrame()
        self.header.setObjectName("header")
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(8, 6, 8, 6)
        header_layout.setSpacing(6)
        self.title_label = QLabel("DHCP Leases (0)")
        self.title_label.setObjectName("title")
        self.interface_label = QLabel("▼ unknown")
        self.interface_label.setObjectName("interface")
        header_layout.addWidget(self.title_label, 1)
        header_layout.addWidget(self.interface_label, 0, Qt.AlignmentFlag.AlignRight)
        container_layout.addWidget(self.header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setObjectName("leaseScroll")
        self.rows_container = QWidget()
        self.rows_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.rows_layout = QVBoxLayout(self.rows_container)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(6)
        self.rows_layout.addStretch(1)
        self.scroll.setWidget(self.rows_container)
        container_layout.addWidget(self.scroll, 1)
        root_layout.addWidget(self.container)

        self._apply_main_style()
        self._update_width_constraints()
        self._setup_refresh_worker()

        self.fallback_timer = QTimer(self)
        self.fallback_timer.setInterval(30_000)
        self.fallback_timer.timeout.connect(self.refresh_leases)
        self.fallback_timer.start()

        self.debounce_timer = QTimer(self)
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.setInterval(500)
        self.debounce_timer.timeout.connect(self.refresh_leases)

        self._setup_inotify()
        self.refresh_leases()

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    @property
    def effective_lease_file(self) -> str:
        return self.cli_lease_file or str(self.settings.get("lease_file", DEFAULT_LEASE_FILE))

    def _apply_main_style(self) -> None:
        scale = float(self.settings.get("font_scale", 1.0))
        title_px = max(11, int(14 * scale))
        meta_px = max(10, int(12 * scale))
        self.setStyleSheet(
            f"""
            QFrame#container {{
                background-color: rgba(13, 17, 23, 0.92);
                border: 1px solid rgba(240, 246, 252, 0.08);
                border-radius: 10px;
            }}
            QFrame#header {{
                background-color: rgba(240, 246, 252, 0.04);
                border: 1px solid rgba(240, 246, 252, 0.08);
                border-radius: 8px;
            }}
            QLabel#title {{
                color: #f0f6fc;
                font-size: {title_px}px;
                font-weight: 700;
            }}
            QLabel#interface {{
                color: #8b949e;
                font-size: {meta_px}px;
                font-weight: 600;
            }}
            QScrollArea#leaseScroll {{
                border: none;
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: rgba(255, 255, 255, 0.04);
                width: 8px;
                margin: 2px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(201, 209, 217, 0.35);
                border-radius: 4px;
                min-height: 25px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            """
        )

    def _clear_rows(self) -> None:
        while self.rows_layout.count() > 0:
            item = self.rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.rows_layout.addStretch(1)

    def _render_rows(self) -> None:
        self._clear_rows()
        scale = float(self.settings.get("font_scale", 1.0))
        if not self.leases:
            empty = QLabel("No leases found")
            empty.setStyleSheet("color: #8b949e; padding: 8px;")
            self.rows_layout.insertWidget(0, empty)
            return

        for lease in self.leases:
            row = LeaseRow(lease, font_scale=scale, parent=self.rows_container)
            row.clicked.connect(self._on_row_clicked)
            row.right_clicked.connect(self._on_row_right_clicked)
            self.rows_layout.insertWidget(self.rows_layout.count() - 1, row)

    def _on_row_clicked(self, lease: DhcpLease, global_pos: QPoint) -> None:
        duration = int(self.settings.get("lease_duration_hours", 24))
        self.detail_popup.show_for_lease(lease, anchor_point=global_pos, lease_duration_hours=duration)

    def _on_row_right_clicked(self, lease: DhcpLease, global_pos: QPoint) -> None:
        self.detail_popup.hide()
        menu = self._build_context_menu(lease)
        self._show_menu(menu, global_pos)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        self.detail_popup.hide()
        menu = self._build_context_menu(None)
        self._show_menu(menu, event.globalPos())

    def _build_context_menu(self, lease: DhcpLease | None) -> QMenu:
        menu = QMenu(self)

        if lease is not None:
            copy_ip = menu.addAction("Copy IP")
            copy_mac = menu.addAction("Copy MAC")
            copy_ip.triggered.connect(lambda _checked=False, ip=lease.ip: QApplication.clipboard().setText(ip))
            copy_mac.triggered.connect(lambda _checked=False, mac=lease.mac: QApplication.clipboard().setText(mac))
            menu.addSeparator()

        opacity_menu = menu.addMenu("Opacity")
        opacity_group = QActionGroup(menu)
        opacity_group.setExclusive(True)
        current_opacity = round(float(self.settings.get("opacity", 0.95)), 2)
        for value, label in [
            (1.00, "100%"),
            (0.95, "95%"),
            (0.90, "90%"),
            (0.80, "80%"),
            (0.70, "70%"),
        ]:
            action = QAction(label, menu, checkable=True)
            action.setChecked(abs(current_opacity - value) < 0.001)
            action.triggered.connect(lambda _checked=False, v=value: self._set_opacity(v))
            opacity_group.addAction(action)
            opacity_menu.addAction(action)

        font_menu = menu.addMenu("Font Size")
        font_group = QActionGroup(menu)
        font_group.setExclusive(True)
        current_scale = float(self.settings.get("font_scale", 1.0))
        for value, label in [
            (0.8, "Small (0.8)"),
            (1.0, "Medium (1.0)"),
            (1.3, "Large (1.3)"),
        ]:
            action = QAction(label, menu, checkable=True)
            action.setChecked(abs(current_scale - value) < 0.001)
            action.triggered.connect(lambda _checked=False, v=value: self._set_font_scale(v))
            font_group.addAction(action)
            font_menu.addAction(action)

        menu.addSeparator()
        refresh_action = menu.addAction("Refresh Now")
        menu.addSeparator()
        quit_action = menu.addAction("Quit")
        refresh_action.triggered.connect(self.refresh_leases)
        quit_action.triggered.connect(self.close)
        return menu

    def _show_menu(self, menu: QMenu, position: QPoint) -> None:
        if self._active_menu is not None:
            self._active_menu.close()
            self._active_menu = None

        self._active_menu = menu

        def _cleanup() -> None:
            if self._active_menu is menu:
                self._active_menu = None
            menu.deleteLater()

        menu.aboutToHide.connect(_cleanup)
        menu.setStyleSheet(self._menu_stylesheet)
        menu.popup(self._resolve_menu_position(position))

    def _resolve_menu_position(self, requested: QPoint) -> QPoint:
        """Guard against bad Wayland global positions by preferring live cursor coords."""
        cursor = QCursor.pos()
        if requested.x() < 0 or requested.y() < 0:
            return cursor

        active_screen = QGuiApplication.screenAt(cursor) or QApplication.primaryScreen()
        if active_screen is None:
            return cursor

        geom = active_screen.availableGeometry()
        if not geom.contains(requested):
            return cursor

        if abs(requested.x() - cursor.x()) > 80 or abs(requested.y() - cursor.y()) > 80:
            return cursor
        return requested

    def _set_opacity(self, value: float) -> None:
        self.settings["opacity"] = float(value)
        save_settings(self.settings)
        self.setWindowOpacity(float(value))

    def _set_font_scale(self, value: float) -> None:
        self.settings["font_scale"] = float(value)
        save_settings(self.settings)
        self._apply_main_style()
        self._update_width_constraints()
        self._render_rows()

    def _update_width_constraints(self) -> None:
        scale = float(self.settings.get("font_scale", 1.0))
        target_width = max(320, int(430 + (scale - 1.0) * 320))
        self.setMinimumWidth(target_width)
        if self.width() < target_width:
            self.resize(target_width, self.height())

    def _setup_refresh_worker(self) -> None:
        self._refresh_thread = QThread(self)
        self._refresh_worker = LeaseRefreshWorker()
        self._refresh_worker.moveToThread(self._refresh_thread)
        self._refresh_thread.finished.connect(self._refresh_worker.deleteLater)
        self.refresh_requested.connect(
            self._refresh_worker.queue_refresh,
            Qt.ConnectionType.QueuedConnection,
        )
        self._refresh_worker.refresh_ready.connect(self._on_refresh_ready)
        self._refresh_worker.refresh_failed.connect(self._on_refresh_failed)
        self._refresh_thread.start()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if self.detail_popup.isVisible():
            event_type = event.type()
            if event_type == QEvent.Type.MouseButtonPress:
                global_pos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else QCursor.pos()
                in_detail = self.detail_popup.isVisible() and self.detail_popup.frameGeometry().contains(global_pos)
                if not in_detail:
                    self.detail_popup.hide()
            elif event_type == QEvent.Type.KeyPress and getattr(event, "key", lambda: None)() == Qt.Key.Key_Escape:
                self.detail_popup.hide()
                return True
        return super().eventFilter(watched, event)

    def refresh_leases(self) -> None:
        lease_file = self.effective_lease_file
        include_expired = bool(self.settings.get("show_expired", True))
        self._refresh_request_id += 1
        request_id = self._refresh_request_id
        self.log.debug(
            "refresh_queued",
            request_id=request_id,
            lease_file=lease_file,
            include_expired=include_expired,
        )
        self.refresh_requested.emit(request_id, lease_file, include_expired)

    def _on_refresh_ready(
        self,
        request_id: int,
        leases: object,
        interface: str,
        include_expired: bool,
    ) -> None:
        if request_id < self._refresh_request_id:
            self.log.debug(
                "refresh_result_stale",
                request_id=request_id,
                latest_request_id=self._refresh_request_id,
            )
            return

        leases_list = leases if isinstance(leases, list) else []
        self.leases = leases_list
        self.title_label.setText(f"DHCP Leases ({len(self.leases)})")
        self.interface_label.setText(f"▼ {interface}")
        self._render_rows()

        self.log.debug(
            "refresh_complete",
            request_id=request_id,
            count=len(self.leases),
            interface=interface,
            include_expired=include_expired,
        )

    def _on_refresh_failed(self, request_id: int, error: str) -> None:
        if request_id < self._refresh_request_id:
            self.log.debug(
                "refresh_error_stale",
                request_id=request_id,
                latest_request_id=self._refresh_request_id,
                error=error,
            )
            return
        self.log.warning("refresh_failed", request_id=request_id, error=error)

    def _setup_inotify(self) -> None:
        if INotify is None or flags is None:
            self.log.warning("inotify_unavailable", mode="timer_only")
            return

        lease_path = Path(self.effective_lease_file)
        watch_dir = lease_path.parent
        self._watched_filename = lease_path.name

        if not watch_dir.exists():
            self.log.warning("watch_dir_missing", watch_dir=str(watch_dir))
            return

        try:
            self._inotify = INotify()
            watch_mask = (
                flags.CLOSE_WRITE
                | flags.MOVED_TO
                | flags.CREATE
                | flags.DELETE
                | flags.ATTRIB
                | flags.MOVE_SELF
                | flags.DELETE_SELF
            )
            self._inotify.add_watch(str(watch_dir), watch_mask)
            self._inotify_notifier = QSocketNotifier(
                self._inotify.fileno(),
                QSocketNotifier.Type.Read,
                self,
            )
            self._inotify_notifier.activated.connect(self._on_inotify_event)
            self.log.info("inotify_enabled", watch_dir=str(watch_dir), filename=self._watched_filename)
        except Exception as exc:
            self.log.warning("inotify_setup_failed", error=str(exc))
            self._inotify = None
            self._inotify_notifier = None

    def _on_inotify_event(self) -> None:
        if self._inotify is None or self._watched_filename is None:
            return
        try:
            events = self._inotify.read(timeout=0)
        except Exception as exc:
            self.log.warning("inotify_read_failed", error=str(exc))
            return

        relevant = False
        for event in events:
            event_name = event.name or ""
            if event_name == self._watched_filename:
                relevant = True
                break

        if relevant:
            self.log.debug("inotify_event", filename=self._watched_filename)
            self.debounce_timer.start()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.detail_popup.close()
        self.fallback_timer.stop()
        self.debounce_timer.stop()
        if self._inotify_notifier is not None:
            self._inotify_notifier.setEnabled(False)
            self._inotify_notifier.deleteLater()
        if self._inotify is not None:
            try:
                self._inotify.close()
            except Exception:
                pass
        if self._refresh_thread.isRunning():
            self._refresh_thread.quit()
            if not self._refresh_thread.wait(1_500):
                self.log.warning("refresh_thread_shutdown_timeout")
        super().closeEvent(event)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DHCP lease monitor widget")
    parser.add_argument("--debug", action="store_true", help="Enable verbose console logging")
    parser.add_argument(
        "--lease-file",
        default=None,
        help="Override lease file path (overrides config)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    log = setup_logging(debug_mode=args.debug)
    redirect_stderr()
    enable_fault_handler()
    log.info("app_start", version=__version__, debug=args.debug, lease_file=args.lease_file)

    app = QApplication(sys.argv)
    app.setApplicationName("DHCP Lease Monitor")
    app.setDesktopFileName(APP_ID)
    app.setQuitOnLastWindowClosed(True)

    lock_path = Path(QDir.tempPath()) / f"{APP_ID}.lock"
    lock = QLockFile(str(lock_path))
    # Auto-recover from stale lock files after crashes.
    lock.setStaleLockTime(30_000)
    if not lock.tryLock(100):
        log.warning("single_instance_blocked", lock_path=str(lock_path))
        print("DHCP Lease Monitor is already running.")
        return 0

    signal.signal(signal.SIGINT, signal.SIG_DFL)

    widget = DhcpLeaseMonitor(cli_lease_file=args.lease_file, debug=args.debug)
    widget.show()

    exit_code = app.exec()
    lock.unlock()
    log.info("app_exit", exit_code=exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
