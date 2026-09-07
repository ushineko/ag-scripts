"""AIO section widget.

A self-contained QFrame showing liquid-cooler thermals from the OpenLinkHub
daemon: CPU temperature, coolant temperature (with a 5-minute sparkline), and
fan/pump speeds. Owns its own QTimer. All parsing lives in `aio_reader`; this
module is UI and state only.

Public API
----------
- `AioSection(initial_settings, parent)`: construct
- `set_visible(visible: bool)`: user-facing toggle (context menu)
- `update_style(opacity_alpha, font_scale)`
- `render_snapshot(snapshot: dict)`: render an `aio_reader` snapshot

Transport is `QNetworkAccessManager`, not `urllib` on the GUI thread and not a
QThread. Two blocking HTTP calls per poll would freeze the widget for up to
2x the timeout whenever the daemon hangs, and a QThread + QObject worker carries
the lifetime hazards that produced the spec 010 crash. QNAM is event-loop
native — nothing to orphan.

Read-only by design: fan and pump duty writes are silently discarded by
Commander ST firmware 2.x, so a control here would report success and change
nothing. See the AIO runbook in ~/git/sysadmin/runbooks/.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QPointF, Qt, QTimer, QUrl
from PyQt6.QtGui import QColor, QPainter, QPen, QPolygonF
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

import aio_reader

_log = logging.getLogger(__name__)

# Poll cadence. 5 s gives a 5-minute sparkline over SPARKLINE_SAMPLES points and
# is cheap: two localhost GETs against a daemon already polling the HID device.
# With nothing to show we back off hard rather than retrying every 5 s forever.
POLL_INTERVAL_MS = 5000
IDLE_POLL_INTERVAL_MS = 30000
REQUEST_TIMEOUT_MS = 2000

SPARKLINE_SAMPLES = 60

# Coolant bands, from the observed behaviour of this cooler: the pump-head
# over-temperature alarm tripped at 57.1 C and cleared near 50 C, and the
# runbook calls 55 C the start of the warning band. CPU temperature is not
# graded — an i9-14900K boosting to 100 C is normal here and colouring it red
# would cry wolf on every compile.
COOLANT_WARN_C = 50.0
COOLANT_ALARM_C = 55.0

COLOR_OK = "#4caf50"
COLOR_WARN = "#ff9800"
COLOR_ALARM = "#f44336"
COLOR_DIM = "#666666"

# Sparkline never renders a span narrower than this, so an idle flat line stays
# flat instead of amplifying 0.1 C of sensor jitter into a mountain range.
SPARKLINE_MIN_SPAN_C = 5.0


def coolant_color(temp_c: float | None) -> str:
    """Colour for a coolant temperature, or the dim colour when unknown."""
    if temp_c is None:
        return COLOR_DIM
    if temp_c >= COOLANT_ALARM_C:
        return COLOR_ALARM
    if temp_c >= COOLANT_WARN_C:
        return COLOR_WARN
    return COLOR_OK


class Sparkline(QWidget):
    """Fixed-capacity line plot of one series, drawn with QPainter.

    Keeps the last `capacity` samples and auto-scales vertically to them. No
    axes, no grid — at this width anything more is noise.
    """

    def __init__(self, capacity: int = SPARKLINE_SAMPLES, parent: QWidget | None = None):
        super().__init__(parent)
        self._capacity = capacity
        self._samples: list[float] = []
        self._color = QColor(COLOR_OK)
        self.setMinimumHeight(24)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def samples(self) -> list[float]:
        return list(self._samples)

    def add_sample(self, value: float):
        self._samples.append(float(value))
        if len(self._samples) > self._capacity:
            del self._samples[: len(self._samples) - self._capacity]
        self.update()

    def clear(self):
        self._samples.clear()
        self.update()

    def set_color(self, color: str):
        new = QColor(color)
        if new != self._color:
            self._color = new
            self.update()

    def set_height(self, height: int):
        self.setMinimumHeight(height)
        self.setMaximumHeight(height)

    def paintEvent(self, event):  # noqa: N802 (Qt naming)
        if len(self._samples) < 2:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        lo = min(self._samples)
        hi = max(self._samples)
        span = hi - lo
        if span < SPARKLINE_MIN_SPAN_C:
            # Centre the series inside the minimum span.
            mid = (hi + lo) / 2.0
            lo = mid - SPARKLINE_MIN_SPAN_C / 2.0
            span = SPARKLINE_MIN_SPAN_C

        # Right-anchored: a partially filled buffer grows leftward from "now"
        # rather than stretching a handful of samples across the full width.
        step = w / max(1, self._capacity - 1)
        first_x = w - step * (len(self._samples) - 1)

        points = QPolygonF()
        for i, value in enumerate(self._samples):
            x = first_x + i * step
            y = h - 1 - ((value - lo) / span) * (h - 2)
            points.append(QPointF(x, y))

        pen = QPen(self._color)
        pen.setWidthF(1.5)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawPolyline(points)
        painter.end()


class _MetricRow:
    """One label/value line. The row is a real QWidget so its size hint
    propagates immediately — see the same note in bandwidth_section.
    """

    def __init__(self, title: str, value_object_name: str, parent: QWidget):
        self.widget = QWidget(parent)
        layout = QHBoxLayout(self.widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.name_lbl = QLabel(title, self.widget)
        self.name_lbl.setObjectName("AioName")

        self.value_lbl = QLabel("--", self.widget)
        self.value_lbl.setObjectName(value_object_name)
        self.value_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        layout.addWidget(self.name_lbl)
        layout.addStretch(1)
        layout.addWidget(self.value_lbl)

    def set_value(self, text: str):
        self.value_lbl.setText(text)

    def set_color(self, color: str | None):
        self.value_lbl.setStyleSheet(f"color: {color};" if color else "")

    def show(self):
        self.widget.show()

    def hide(self):
        self.widget.hide()

    def is_visible(self) -> bool:
        return not self.widget.isHidden()


class AioSection(QFrame):
    """AIO section frame. See the module docstring for the public API."""

    def __init__(self, initial_settings: dict | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("AioSection")

        settings = initial_settings or {}
        self._user_enabled = bool(settings.get("aio_section_enabled", True))
        # True once a snapshot has ever been displayable. Until then the section
        # stays hidden, so a machine without OpenLinkHub sees no change at all.
        self._data_ever = False
        self._degraded = False
        self._inflight: dict | None = None
        self._font_scale = 1.0
        self._last_coolant: float | None = None

        self._root_layout = QVBoxLayout(self)
        self._root_layout.setContentsMargins(15, 8, 15, 10)
        self._root_layout.setSpacing(4)

        self._header_lbl = QLabel("AIO", self)
        self._header_lbl.setObjectName("AioTitle")
        self._root_layout.addWidget(self._header_lbl)

        self._rows_container = QVBoxLayout()
        self._rows_container.setSpacing(2)
        self._root_layout.addLayout(self._rows_container)

        self.cpu_row = _MetricRow("CPU", "AioValue", self)
        self.coolant_row = _MetricRow("Coolant", "AioCoolant", self)
        self.fan_row = _MetricRow("Fans", "AioValue", self)
        for row in (self.cpu_row, self.coolant_row, self.fan_row):
            self._rows_container.addWidget(row.widget)
            row.hide()

        self.sparkline = Sparkline(parent=self)
        self.sparkline.hide()
        self._root_layout.addWidget(self.sparkline)

        self._nam = QNetworkAccessManager(self)

        self._timer = QTimer(self)
        self._timer.setInterval(IDLE_POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)

        self._apply_visibility()
        if self._user_enabled:
            self._timer.start()
            # Poll once immediately so the section appears on the first tick
            # rather than after a full idle interval.
            QTimer.singleShot(0, self._poll)

    # ---- public API ----

    def set_visible(self, visible: bool):
        """User-facing toggle. Availability still gates actual visibility."""
        self._user_enabled = bool(visible)
        if self._user_enabled:
            if not self._timer.isActive():
                self._timer.start()
            self._poll()
        else:
            self._timer.stop()
        self._apply_visibility()

    def update_style(self, alpha: int, font_scale: float):
        self._font_scale = font_scale
        title_size = int(11 * font_scale)
        name_size = int(11 * font_scale)
        value_size = int(11 * font_scale)

        def s(base, lo=1):
            return max(lo, int(round(base * font_scale)))

        self._root_layout.setContentsMargins(s(15, 6), s(8, 3), s(15, 6), s(10, 4))
        self._root_layout.setSpacing(s(4, 1))
        self._rows_container.setSpacing(s(2, 0))
        self.sparkline.set_height(s(26, 14))

        self.setStyleSheet(f"""
            QFrame#AioSection {{
                background-color: rgba(35, 35, 35, {alpha});
                border: 1px solid rgba(255, 255, 255, 15);
                border-radius: 8px;
                margin-top: 4px;
            }}
            QLabel {{
                color: #e0e0e0;
                background: transparent;
            }}
            QLabel#AioTitle {{
                color: #aaaaaa;
                font-weight: bold;
                font-size: {title_size}px;
            }}
            QLabel#AioName {{
                color: #cccccc;
                font-size: {name_size}px;
            }}
            QLabel#AioValue {{
                color: #e0e0e0;
                font-size: {value_size}px;
                font-family: monospace;
            }}
            QLabel#AioCoolant {{
                font-size: {value_size}px;
                font-family: monospace;
            }}
        """)
        # The parent sheet resets the coolant colour; reapply the band.
        self._apply_coolant_color(self._last_coolant)

    def render_snapshot(self, snapshot: dict):
        """Render an `aio_reader` snapshot and adjust the poll cadence."""
        available = bool(snapshot.get("available"))

        if available:
            self._data_ever = True
            self._degraded = False
            self._render_available(snapshot)
            self._set_interval(POLL_INTERVAL_MS)
        elif self._data_ever:
            # Was working, now isn't: keep the last values but dim them, so a
            # blip doesn't make the window jump around.
            self._degraded = True
            self._apply_dimming()
            self._set_interval(POLL_INTERVAL_MS)
        else:
            self._set_interval(IDLE_POLL_INTERVAL_MS)

        self._header_lbl.setText("AIO  (unavailable)" if self._degraded else "AIO")
        self._apply_visibility()

    # ---- internals ----

    def _render_available(self, snapshot: dict):
        cpu = snapshot.get("cpu_temp_c")
        if cpu is None:
            self.cpu_row.hide()
        else:
            self.cpu_row.set_value(f"{cpu:.1f} °C")
            self.cpu_row.set_color(None)
            self.cpu_row.show()

        coolant = snapshot.get("coolant_temp_c")
        self._last_coolant = coolant
        if coolant is None:
            self.coolant_row.hide()
            self.sparkline.hide()
        else:
            self.coolant_row.set_value(f"{coolant:.1f} °C")
            self.coolant_row.show()
            self.sparkline.add_sample(coolant)
            self.sparkline.show()
        self._apply_coolant_color(coolant)

        fans = snapshot.get("fans") or []
        avg = aio_reader.average_fan_rpm(fans)
        pump = snapshot.get("pump_rpm")
        if avg is None and pump is None:
            self.fan_row.hide()
        else:
            parts = []
            if avg is not None:
                suffix = f" ×{len(fans)}" if len(fans) > 1 else ""
                parts.append(f"{avg} rpm{suffix}")
            if pump is not None:
                parts.append(f"pump {pump}")
            self.fan_row.set_value("  ".join(parts))
            self.fan_row.set_color(None)
            self.fan_row.show()

    def _apply_coolant_color(self, coolant: float | None):
        color = COLOR_DIM if self._degraded else coolant_color(coolant)
        self.coolant_row.set_color(color)
        self.sparkline.set_color(color)

    def _apply_dimming(self):
        self.cpu_row.set_color(COLOR_DIM)
        self.fan_row.set_color(COLOR_DIM)
        self._apply_coolant_color(self._last_coolant)

    def _apply_visibility(self):
        should_show = self._user_enabled and self._data_ever
        if should_show == (not self.isHidden()):
            return
        self.setVisible(should_show)
        self._relayout_window()

    def _relayout_window(self):
        """Recompute the parent window size now, not on the next paint — the
        same deferred-size-hint problem the bandwidth section documents.
        """
        self.updateGeometry()
        top = self.window()
        if top is not None and top is not self:
            top.adjustSize()

    def _set_interval(self, interval_ms: int):
        if self._timer.interval() != interval_ms:
            self._timer.setInterval(interval_ms)

    def _poll(self):
        if self._inflight is not None:
            # A previous poll is still outstanding (hung daemon). Skip rather
            # than queueing requests behind it.
            return
        urls = aio_reader.endpoint_urls()
        self._inflight = {"cpu": None, "devices": None, "pending": 2}
        for key, url in urls.items():
            self._request(url, key)

    def _request(self, url: str, key: str):
        request = QNetworkRequest(QUrl(url))
        request.setTransferTimeout(REQUEST_TIMEOUT_MS)
        request.setAttribute(
            QNetworkRequest.Attribute.CacheLoadControlAttribute,
            QNetworkRequest.CacheLoadControl.AlwaysNetwork,
        )
        reply = self._nam.get(request)
        reply.finished.connect(lambda r=reply, k=key: self._on_reply(r, k))

    def _on_reply(self, reply: QNetworkReply, key: str):
        payload = None
        if reply.error() == QNetworkReply.NetworkError.NoError:
            payload = aio_reader.decode_payload(bytes(reply.readAll()))
        else:
            _log.debug("aio_reply_failed key=%s err=%s", key, reply.errorString())
        reply.deleteLater()

        state = self._inflight
        if state is None:
            return
        state[key] = payload
        state["pending"] -= 1
        if state["pending"] > 0:
            return

        self._inflight = None
        try:
            snapshot = aio_reader.build_snapshot(state["cpu"], state["devices"])
        except Exception:
            # Best-effort: a parse failure must not kill the timer.
            _log.warning("aio_snapshot_failed", exc_info=True)
            return
        self.render_snapshot(snapshot)
