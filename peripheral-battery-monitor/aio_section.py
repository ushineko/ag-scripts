"""AIO section widget.

A self-contained QFrame showing liquid-cooler thermals from the OpenLinkHub
daemon: CPU temperature, coolant temperature, and fan/pump speeds, over a
5-minute sparkline carrying two traces. Coolant is plotted raw; CPU is plotted
as a 60-second trailing mean, because raw CPU is too spiky to read at this size.
Owns its own QTimer. All parsing lives in `aio_reader`; this module is UI and
state only.

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

Reads thermals; writes RGB and LCD, never fan or pump duty. The cooler is an
NZXT Kraken Elite V2 driven through `liquidctl`: `aio_liquid` builds the command
lines, `kraken_color` / `kraken_effect` / `set_lcd_*` drive them from the context
menu (spec 021), and `aio_queue.LiquidctlQueue` serialises every invocation
against the status poll so no two liquidctl processes touch the same hidraw node
at once. The OpenLinkHub RGB path (`aio_color`, `apply_color`, spec 019) is
retained for a future OpenLinkHub device but is inert on this hardware.

The LCD can show a live rendered dashboard (`aio_dashboard`). It is off by
default, pushes on a selectable interval (30 s default) and only when the
rendered content actually changed. Writing less is the mitigation for two
separate LCD problems: liquidctl#774 bucket-switch failures, and the visible
fallback to the firmware's readout while a bucket is deleted and rewritten.
Persistent failures disable the dashboard and fall back to that readout, leaving
cooling telemetry unaffected. See the AIO runbook in ~/git/sysadmin/runbooks/.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile

from PyQt6.QtCore import (QElapsedTimer, QPointF, QProcess, Qt, QTimer, QUrl,
                          pyqtSignal)
from PyQt6.QtGui import QColor, QPainter, QPen, QPolygonF
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

import aio_color
import aio_dashboard
import aio_liquid
import aio_queue
import aio_reader
import aio_scenes
import rgb_openrgb

_log = logging.getLogger(__name__)

# Poll cadence. 5 s gives a 5-minute sparkline over SPARKLINE_SAMPLES points and
# is cheap: two localhost GETs against a daemon already polling the HID device.
# With nothing to show we back off hard rather than retrying every 5 s forever.
POLL_INTERVAL_MS = 5000
IDLE_POLL_INTERVAL_MS = 30000
REQUEST_TIMEOUT_MS = 2000

# liquidctl runs out of process (spec 020). It is driven through QProcess rather
# than subprocess for the same reason the HTTP calls use QNetworkAccessManager:
# a blocking call on the GUI thread freezes the widget. Measured at ~0.16 s on
# this hardware, but it opens a hidraw node and contention on this machine has
# produced multi-second stalls, so it gets a hard kill deadline.
LIQUIDCTL_TIMEOUT_MS = 5000

# Alert debounce. A single bad sample is not a cooling failure — liquidctl can
# return a partial read while the device is busy — so a state must persist
# across consecutive polls before it notifies. At a 5 s cadence three samples is
# ~15 s, fast enough to matter for a stopped pump and slow enough to ignore a
# blip. While a condition persists, re-notify at most every REPEAT interval.
ALERT_CONFIRM_SAMPLES = 3
ALERT_REPEAT_MS = 600000  # 10 minutes

# LCD dashboard (spec 021). Deliberately slow: the values move slowly, and the
# LCD's bucket-switching fails intermittently under repeated writes
# (liquidctl#774), so the cheapest mitigation is writing rarely. A push also
# only happens when the rendered content actually changed, so a machine sitting
# at a steady idle writes nothing at all.
LCD_PUSH_INTERVAL_MS = 30000
# Selectable refresh intervals (spec 022, extended 023).
#
# 1 s is a DIAGNOSTIC option, not a sensible setting. It cannot show fresher
# data — the cooler is polled every 5 s, so four pushes in five repaint
# identical values — and a push costs 0.7-0.8 s, so it occupies the hidraw
# queue most of the time. It exists to measure the load that repeated LCD
# writes generate.
#
# Faster intervals also make the built-in readout flash through more often:
# liquidctl's _send_data deletes a bucket before each write, and once all
# buckets are occupied it recycles bucket 0, which may be the one on screen.
# The firmware then has nothing to display and falls back to its own readout
# until the new image lands.
LCD_PUSH_INTERVALS_MS = (1000, 5000, 10000, 30000, 60000, 300000)
LCD_DIAGNOSTIC_INTERVALS_MS = (1000,)

# Keep-alive (spec 028). The cooler does NOT retain a host-pushed image: with the
# monitor stopped and nothing else touching the device, a hand-pushed image still
# reverted to the firmware's built-in display on its own. So the screen must be
# rewritten on a floor, whether or not anything changed — minimising writes past
# this point does not make the dashboard quieter, it makes it absent.
#
# This is in deliberate tension with specs 021/022, which minimised writes to
# avoid liquidctl#774. That risk is unchanged and still bounded by the failure
# ceiling; an image that is not on screen simply has no value to trade against it.
#
# The retention period is a firmware property, measured rather than documented,
# so it is a setting rather than a constant.
# Off by default, and it should stay that way. A static image reverts to the
# built-in display in ~5-10 s on this firmware, which briefly made a sub-5 s
# keep-alive look necessary — at ~0.7-0.8 s of hidraw time per push, against a
# 5 s status poll, and straight down the liquidctl#774 path. Pushing a GIF
# instead removes the need entirely: the firmware retains it. This remains only
# as an escape hatch for firmware that retains neither.
# Devices that do not hold a host-set colour across a sleep/wake cycle, and the
# interval at which their colour is re-sent. The G502 is wireless: OpenRGB sets a
# volatile effect, and the mouse restores onboard state when it wakes, so the
# scene colour is silently lost. Nothing re-asserted it before, which is exactly
# what "keeps reverting to red" was.
#
# Scoped deliberately. Every other lit device here holds its colour indefinitely,
# and re-sending to all of them would be a write per device per minute for no
# gain. The interval sits under the mouse's 5-minute sleep timeout.
LIGHTING_REASSERT_SCOPE = ("g502",)
LIGHTING_REASSERT_MS = 60_000

LCD_KEEPALIVE_MS = 0
LCD_KEEPALIVE_OPTIONS_MS = (0, 3000, 5000, 10000, 30000)
# After this many consecutive push failures, give up, fall back to the
# firmware's own `liquid` readout (which needs no host traffic and cannot blank)
# and tell the user once.
LCD_MAX_FAILURES = 5
LCD_IMAGE_PATH = os.path.join(
    os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir(),
    # .gif, not .png: the firmware drops a static image after ~5-10 s but retains
    # a GIF indefinitely. See aio_dashboard.write_gif and spec 028.
    "peripheral-battery-monitor-lcd.gif",
)

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
# Secondary trace. Muted on purpose: coolant is the primary signal and must stay
# the thing the eye lands on. The CPU row's value label is painted this colour
# too, which is the whole legend — there is no room for a real one.
COLOR_CPU = "#6d9dc5"

# Sparkline never renders a span narrower than this, so an idle flat line stays
# flat instead of amplifying 0.1 C of sensor jitter into a mountain range.
SPARKLINE_MIN_SPAN_C = 5.0

# Raw CPU temperature is unplottable at this size: it spikes to 100 C on any
# compile and swings ~35 C where coolant moves under 1 C. A trailing mean over
# this many samples (12 * 5 s = 60 s) turns it into a trend line.
CPU_AVERAGE_WINDOW = 12

SERIES_CPU = "cpu"
SERIES_COOLANT = "coolant"


def coolant_color(temp_c: float | None) -> str:
    """Colour for a coolant temperature, or the dim colour when unknown."""
    if temp_c is None:
        return COLOR_DIM
    if temp_c >= COOLANT_ALARM_C:
        return COLOR_ALARM
    if temp_c >= COOLANT_WARN_C:
        return COLOR_WARN
    return COLOR_OK


class _Series:
    """One trace: its samples, its colour, and its own vertical scale."""

    def __init__(self, color: str, width: float, min_span: float):
        self.samples: list[float] = []
        self.color = QColor(color)
        self.width = width
        self.min_span = min_span

    def bounds(self) -> tuple[float, float]:
        """(low, span) for this series alone, widened to `min_span`."""
        lo = min(self.samples)
        hi = max(self.samples)
        span = hi - lo
        if span < self.min_span:
            mid = (hi + lo) / 2.0
            lo = mid - self.min_span / 2.0
            span = self.min_span
        return lo, span


class Sparkline(QWidget):
    """Fixed-capacity line plot of one or more series, drawn with QPainter.

    Each series is scaled to its own min/max rather than to a shared axis.
    CPU temperature swings roughly 35 C while coolant moves under 1 C, so a
    shared degrees-Celsius axis would flatten the coolant trace to a couple of
    pixels and destroy the signal this graph exists for. The consequence, worth
    being explicit about: heights are NOT comparable between series. The plot
    carries no axis labels, and the real numbers live in the rows above, so the
    reader takes shape and correlation from here and values from there.

    Series are drawn in registration order, so register the primary one last.
    """

    def __init__(self, capacity: int = SPARKLINE_SAMPLES, parent: QWidget | None = None):
        super().__init__(parent)
        self._capacity = capacity
        self._series: dict[str, _Series] = {}
        self.setMinimumHeight(24)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def add_series(self, key: str, color: str, width: float = 1.5,
                   min_span: float = SPARKLINE_MIN_SPAN_C):
        self._series[key] = _Series(color, width, min_span)

    def samples(self, key: str) -> list[float]:
        series = self._series.get(key)
        return list(series.samples) if series else []

    def add_sample(self, key: str, value: float):
        series = self._series.get(key)
        if series is None:
            return
        series.samples.append(float(value))
        if len(series.samples) > self._capacity:
            del series.samples[: len(series.samples) - self._capacity]
        self.update()

    def has_data(self) -> bool:
        return any(series.samples for series in self._series.values())

    def clear(self):
        for series in self._series.values():
            series.samples.clear()
        self.update()

    def set_color(self, key: str, color: str):
        series = self._series.get(key)
        if series is None:
            return
        new = QColor(color)
        if new != series.color:
            series.color = new
            self.update()

    def set_height(self, height: int):
        self.setMinimumHeight(height)
        self.setMaximumHeight(height)

    def paintEvent(self, event):  # noqa: N802 (Qt naming)
        painter = None
        for series in self._series.values():
            if len(series.samples) < 2:
                continue
            if painter is None:
                painter = QPainter(self)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._draw_series(painter, series)
        if painter is not None:
            painter.end()

    def _draw_series(self, painter: QPainter, series: _Series):
        w = self.width()
        h = self.height()
        lo, span = series.bounds()

        # Right-anchored: a partially filled buffer grows leftward from "now"
        # rather than stretching a handful of samples across the full width.
        step = w / max(1, self._capacity - 1)
        first_x = w - step * (len(series.samples) - 1)

        points = QPolygonF()
        for i, value in enumerate(series.samples):
            x = first_x + i * step
            y = h - 1 - ((value - lo) / span) * (h - 2)
            points.append(QPointF(x, y))

        pen = QPen(series.color)
        pen.setWidthF(series.width)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawPolyline(points)


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
    # Emitted whenever the LCD dashboard turns on or off, including indirectly
    # (showing an image, or surrendering after failures). The menu and settings
    # both follow this rather than tracking the state separately — two copies of
    # one fact is exactly the bug spec 022 fixes.
    dashboardChanged = pyqtSignal(bool)
    # Emitted with the colour name whenever a lighting profile is applied,
    # so settings persistence follows the section rather than each call site.
    lightingChanged = pyqtSignal(str)

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
        # Raw CPU readings behind the plotted trailing mean.
        self._cpu_raw: list[float] = []
        # RGB write target and the device's own effect list (spec 019).
        self._rgb_device: str | None = None
        self._rgb_channels: list[int] = []
        self._brightness: int | None = None
        self._effects: list[str] = []
        self._effects_fetched_for: str | None = None
        # Staged RGB writes. `_write_generation` invalidates the tail of a
        # sequence that a newer request has superseded.
        self._pending_stages: list[list] = []
        self._write_generation = 0

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
        # Registration order is draw order: the primary trace goes last.
        self.sparkline.add_series(SERIES_CPU, COLOR_CPU, width=1.0)
        self.sparkline.add_series(SERIES_COOLANT, COLOR_OK, width=1.5)
        self.sparkline.hide()
        self._root_layout.addWidget(self.sparkline)

        self._nam = QNetworkAccessManager(self)

        # Cooling alert state (spec 020). `_alert_active` is the state currently
        # notified about (None when healthy); `_alert_streak` counts consecutive
        # samples agreeing with `_alert_streak_state` so one bad read cannot fire.
        self._alert_active: str | None = None
        self._alert_active_reason: str | None = None
        self._alert_streak_state: str | None = None
        self._alert_streak = 0
        self._alert_timer = QElapsedTimer()

        # Spec 021: one queue for every liquidctl invocation on this device.
        self.queue = aio_queue.LiquidctlQueue(self)

        # LCD dashboard state. Off by default: a push is a visible hardware
        # change and the LCD's current content cannot be read back, so enabling
        # it is the user's call.
        self._lcd_dashboard_enabled = False
        self._lcd_last_pushed: dict | None = None
        self._lcd_timer = QElapsedTimer()
        self._lcd_failures = 0
        self._lcd_interval_ms = LCD_PUSH_INTERVAL_MS
        self._lcd_keepalive_ms = LCD_KEEPALIVE_MS
        self._last_snapshot: dict = {}
        # OpenRGB device list, populated asynchronously (spec 023).
        self._lighting_devices: list[dict] = []
        self._lighting_scope: tuple = rgb_openrgb.DEFAULT_SCOPE
        self._lighting_last_color: str | None = None
        # Tint currently rendered on the LCD (spec 030). Compared against the
        # active lighting colour so a scene change redraws immediately: the
        # metrics are unchanged at that moment, so should_push() alone would
        # leave the old tint on screen until some value happened to move.
        self._lcd_tint: tuple | None = None
        self._scenes: dict = {}

        self._timer = QTimer(self)
        self._timer.setInterval(IDLE_POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)

        # Re-send the colour to devices that lose it on sleep. Independent of the
        # poll timer: it must keep running whether or not the cooler section is
        # visible, because the mouse forgets its colour regardless.
        self._reassert_timer = QTimer(self)
        self._reassert_timer.setInterval(LIGHTING_REASSERT_MS)
        self._reassert_timer.timeout.connect(self.reassert_lighting)
        self._reassert_timer.start()

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

    def rgb_target(self) -> tuple[str | None, list[int]]:
        """(device_id, channels) the RGB menu would write to."""
        return self._rgb_device, list(self._rgb_channels)

    def effects(self) -> list[str]:
        """Effect names this device implements, empty until they are known."""
        return list(self._effects)

    def apply_color(self, rgb: tuple[int, int, int]):
        """Set every RGB channel to one solid colour."""
        device, channels = self.rgb_target()
        if not device or not channels:
            return
        _log.info("aio_rgb_apply_color rgb=%s channels=%d", rgb, len(channels))
        self._run_stages(
            aio_color.solid_requests(device, channels, rgb, brightness=self._brightness)
        )

    def apply_effect(self, profile: str):
        """Select an animated effect on every RGB channel."""
        device, channels = self.rgb_target()
        if not device or not channels:
            return
        _log.info("aio_rgb_apply_effect profile=%s channels=%d", profile, len(channels))
        self._run_stages(
            aio_color.effect_requests(device, channels, profile, brightness=self._brightness)
        )

    def set_brightness(self, level: int):
        device, _channels = self.rgb_target()
        if not device:
            return
        try:
            request = aio_color.brightness_request(device, level)
        except ValueError:
            _log.warning("aio_rgb_bad_brightness level=%r", level)
            return
        _log.info("aio_rgb_set_brightness level=%s", level)
        self._brightness = level
        self._run_stages([[request]])

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
        # The parent sheet resets the per-row colours; reapply them.
        self._apply_row_colors()

    def render_snapshot(self, snapshot: dict):
        """Render an `aio_reader` snapshot and adjust the poll cadence."""
        available = bool(snapshot.get("available"))

        if available:
            self._data_ever = True
            self._degraded = False
            self.sparkline.set_color(SERIES_CPU, COLOR_CPU)
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
        self._rgb_device = snapshot.get("device_id")
        self._rgb_channels = list(snapshot.get("rgb_channels") or [])
        self._brightness = snapshot.get("brightness")
        self._maybe_fetch_effects()

        cpu = snapshot.get("cpu_temp_c")
        if cpu is None:
            self.cpu_row.hide()
        else:
            self.cpu_row.set_value(f"{cpu:.1f} °C")
            self.cpu_row.show()
            self.sparkline.add_sample(SERIES_CPU, self._ingest_cpu(cpu))

        coolant = snapshot.get("coolant_temp_c")
        self._last_coolant = coolant
        if coolant is None:
            self.coolant_row.hide()
        else:
            self.coolant_row.set_value(f"{coolant:.1f} °C")
            self.coolant_row.show()
            self.sparkline.add_sample(SERIES_COOLANT, coolant)
        # The CPU row's value carries the CPU trace colour. That is the legend;
        # there is no room for a real one.
        self._apply_row_colors()
        self.sparkline.setVisible(self.sparkline.has_data())

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

    def _ingest_cpu(self, cpu: float) -> float:
        """Record a raw CPU reading and return the trailing mean to plot.

        A partial window is averaged as-is, so the trace starts on the first
        sample instead of after a minute of blank graph.
        """
        self._cpu_raw.append(cpu)
        if len(self._cpu_raw) > CPU_AVERAGE_WINDOW:
            del self._cpu_raw[: len(self._cpu_raw) - CPU_AVERAGE_WINDOW]
        return sum(self._cpu_raw) / len(self._cpu_raw)

    def _apply_coolant_color(self, coolant: float | None):
        color = COLOR_DIM if self._degraded else coolant_color(coolant)
        self.coolant_row.set_color(color)
        self.sparkline.set_color(SERIES_COOLANT, color)

    def _apply_row_colors(self):
        """Row value colours. CPU matches its trace, coolant matches its band."""
        self.cpu_row.set_color(COLOR_DIM if self._degraded else COLOR_CPU)
        self._apply_coolant_color(self._last_coolant)

    def _apply_dimming(self):
        self.fan_row.set_color(COLOR_DIM)
        self.sparkline.set_color(SERIES_CPU, COLOR_DIM)
        self._apply_row_colors()

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

    def _maybe_fetch_effects(self):
        """Fetch the device's own effect list once. Names cannot be guessed."""
        device = self._rgb_device
        if not device or self._effects_fetched_for == device:
            return
        self._effects_fetched_for = device
        base = aio_reader.DEFAULT_BASE_URL.rstrip("/")
        request = self._build_request(f"{base}/{aio_color.PATH_PROFILES}")
        reply = self._nam.get(request)
        reply.finished.connect(lambda r=reply, d=device: self._on_effects_reply(r, d))

    def _on_effects_reply(self, reply: QNetworkReply, device: str):
        payload = None
        if reply.error() == QNetworkReply.NetworkError.NoError:
            payload = aio_reader.decode_payload(bytes(reply.readAll()))
        else:
            # Retry on the next snapshot rather than leaving the menu empty
            # forever after one transient failure.
            self._effects_fetched_for = None
            _log.debug("aio_effects_fetch_failed err=%s", reply.errorString())
        reply.deleteLater()
        if payload is None:
            return
        self._effects = aio_color.effects_for_device(payload, device)
        _log.debug("aio_effects_loaded count=%d", len(self._effects))

    def _run_stages(self, stages: list[list]):
        """Dispatch ordered stages, each only after the previous one finishes.

        The ordering is the point: an override written after its profile select
        is the documented silent failure.
        """
        self._write_generation += 1
        self._pending_stages = [list(stage) for stage in stages]
        self._dispatch_next_stage(self._write_generation)

    def _dispatch_next_stage(self, generation: int):
        if generation != self._write_generation or not self._pending_stages:
            return
        stage = self._pending_stages.pop(0)
        if not stage:
            self._dispatch_next_stage(generation)
            return
        remaining = {"count": len(stage)}
        for path, payload in stage:
            self._post(path, payload, remaining, generation)

    def _post(self, path: str, payload: dict, remaining: dict, generation: int):
        base = aio_reader.DEFAULT_BASE_URL.rstrip("/")
        request = self._build_request(f"{base}/{path}")
        request.setHeader(
            QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json"
        )
        reply = self._nam.post(request, json.dumps(payload).encode("utf-8"))
        reply.finished.connect(
            lambda r=reply, p=path: self._on_write_reply(r, p, remaining, generation)
        )

    def _on_write_reply(self, reply: QNetworkReply, path: str, remaining: dict,
                        generation: int):
        if reply.error() != QNetworkReply.NetworkError.NoError:
            _log.warning("aio_rgb_write_failed path=%s err=%s", path, reply.errorString())
        else:
            body = aio_reader.decode_payload(bytes(reply.readAll()))
            if not isinstance(body, dict) or body.get("status") != 1:
                _log.warning("aio_rgb_write_rejected path=%s body=%s", path, body)
        reply.deleteLater()

        remaining["count"] -= 1
        if remaining["count"] > 0:
            return
        # A failed stage still advances: the next stage may well succeed, and
        # stalling would leave the device half-written.
        self._dispatch_next_stage(generation)

    def _poll(self):
        if self._inflight is not None:
            # A previous poll is still outstanding (hung daemon, or a liquidctl
            # blocked on a contended hidraw node). Skip rather than queueing
            # requests behind it.
            return
        urls = aio_reader.endpoint_urls()
        self._inflight = {"cpu": None, "gpu": None, "devices": None,
                          "liquid": None, "pending": 4}
        for key, url in urls.items():
            self._request(url, key)
        self._request_liquidctl()

    def _request_liquidctl(self):
        """Read cooler status through the shared queue (spec 021).

        Spec 020 ran this as its own QProcess. Now that RGB and LCD writes exist
        it goes through `LiquidctlQueue` instead, so a status read can never
        overlap a write on the same hidraw node.

        Any failure — binary missing, non-zero exit, timeout, crash — settles the
        slot with None, so the snapshot still builds from OpenLinkHub alone.
        """
        if not aio_reader.liquidctl_available():
            self._settle("liquid", None)
            return

        def done(ok: bool, out: bytes, err: str):
            if not ok:
                _log.debug("liquidctl_status_failed err=%s", err[:200] if err else "")
            self._settle("liquid", out if ok and out else None)

        accepted = self.queue.submit(
            aio_reader.liquidctl_argv(),
            aio_queue.PRIORITY_READ,
            on_done=done,
            coalesce_key="status",
        )
        if not accepted:
            self._settle("liquid", None)

    @staticmethod
    def _build_request(url: str) -> QNetworkRequest:
        request = QNetworkRequest(QUrl(url))
        request.setTransferTimeout(REQUEST_TIMEOUT_MS)
        request.setAttribute(
            QNetworkRequest.Attribute.CacheLoadControlAttribute,
            QNetworkRequest.CacheLoadControl.AlwaysNetwork,
        )
        return request

    def _request(self, url: str, key: str):
        request = self._build_request(url)
        reply = self._nam.get(request)
        reply.finished.connect(lambda r=reply, k=key: self._on_reply(r, k))

    def _on_reply(self, reply: QNetworkReply, key: str):
        payload = None
        if reply.error() == QNetworkReply.NetworkError.NoError:
            payload = aio_reader.decode_payload(bytes(reply.readAll()))
        else:
            _log.debug("aio_reply_failed key=%s err=%s", key, reply.errorString())
        reply.deleteLater()

        self._settle(key, payload)

    def _settle(self, key: str, payload):
        """Record one source's result; build the snapshot once all have landed.

        Shared by the HTTP replies and the liquidctl process so the "last one in
        builds the snapshot" rule lives in exactly one place.
        """
        state = self._inflight
        if state is None:
            return
        state[key] = payload
        state["pending"] -= 1
        if state["pending"] > 0:
            return

        self._inflight = None
        try:
            snapshot = aio_reader.build_snapshot(
                state["cpu"], state["devices"], state["liquid"], state["gpu"]
            )
        except Exception:
            # Best-effort: a parse failure must not kill the timer.
            _log.warning("aio_snapshot_failed", exc_info=True)
            return
        self._last_snapshot = snapshot
        self._evaluate_alert(snapshot)
        self.render_snapshot(snapshot)
        self._maybe_push_dashboard(snapshot)

    # ------------------------------------------------------------------
    # Cooling alerts (spec 020)
    # ------------------------------------------------------------------

    def _evaluate_alert(self, snapshot: dict):
        """Debounce the snapshot's alert state and notify on confirmed changes.

        The pump that motivated this died silently while the widget showed a
        plausible number, so the alert path deliberately does not depend on
        anyone looking at the widget.
        """
        state = snapshot.get("alert_state", aio_reader.ALERT_OK)
        reason = snapshot.get("alert_reason")

        if state == aio_reader.ALERT_OK:
            if self._alert_active:
                prior = self._alert_active_reason
                self._notify(
                    "Cooling recovered",
                    f"Resolved: {prior}" if prior else "Pump and coolant back to normal",
                    critical=False,
                )
            self._alert_active = None
            self._alert_active_reason = None
            self._alert_streak = 0
            self._alert_streak_state = None
            return

        # Count consecutive samples reporting the same state.
        if state == self._alert_streak_state:
            self._alert_streak += 1
        else:
            self._alert_streak_state = state
            self._alert_streak = 1
        if self._alert_streak < ALERT_CONFIRM_SAMPLES:
            return

        escalated = state != self._alert_active
        elapsed = self._alert_timer.elapsed() if self._alert_timer.isValid() else None
        due = elapsed is None or elapsed >= ALERT_REPEAT_MS
        if not (escalated or due):
            return

        self._alert_active = state
        self._alert_active_reason = reason
        self._alert_timer.restart()
        self._notify(
            "CPU cooling critical" if state == aio_reader.ALERT_CRITICAL
            else "CPU cooling warning",
            reason or state,
            critical=state == aio_reader.ALERT_CRITICAL,
        )

    def _notify(self, summary: str, body: str, critical: bool):
        """Fire a desktop notification. Detached and best-effort by design.

        QProcess.startDetached keeps this off the GUI thread and means a missing
        or hung notify-send cannot stall or crash the poll loop.
        """
        args = [
            "--app-name=peripheral-battery-monitor",
            f"--urgency={'critical' if critical else 'normal'}",
            # Replace rather than stack: a persistent condition should leave one
            # notification, not one per repeat interval.
            "--hint=string:x-canonical-private-synchronous:aio-cooling",
            summary,
            body,
        ]
        try:
            QProcess.startDetached("notify-send", args)
        except Exception:
            _log.debug("aio_notify_failed", exc_info=True)
        _log.warning("aio_alert summary=%s body=%s critical=%s", summary, body, critical)

    # ------------------------------------------------------------------
    # Scenes (spec 025)
    # ------------------------------------------------------------------

    def set_scenes(self, scenes: dict):
        """Install the scene table, normally from settings."""
        self._scenes = dict(scenes or {})

    @property
    def scenes(self) -> dict:
        return dict(self._scenes)

    def apply_scene(self, slot) -> bool:
        """Apply the scene bound to `slot`. True when something was applied.

        Both halves are attempted independently: a scene whose LCD file has been
        moved should still change the lighting rather than doing nothing at all.
        """
        if not aio_scenes.valid_slot(slot):
            _log.warning("scene_bad_slot slot=%r", slot)
            return False
        scene = self._scenes.get(str(int(slot)))
        if scene is None:
            _log.warning("scene_missing slot=%s", slot)
            return False

        _log.warning("scene_apply slot=%s scene=%s", slot, aio_scenes.summarise(scene))
        applied = False

        colour = scene.get("color")
        lit = bool(colour) and bool(self.apply_lighting_color(colour))
        if lit:
            applied = True

        lcd = scene.get("lcd")
        if lcd:
            applied = self._apply_scene_lcd(lcd) or applied

        # A scene naming a colour that reached no device has not been applied,
        # whatever the LCD did. Reporting success there is what let a completely
        # dark lighting stack look healthy from the hotkey, the menu and D-Bus
        # alike. See spec 026.
        if colour and not lit:
            state, reason = self.lighting_health()
            _log.warning("scene_lighting_failed slot=%s state=%s reason=%s",
                         slot, state, reason)
            return False
        return applied

    def _apply_scene_lcd(self, lcd: str) -> bool:
        """The LCD half of a scene."""
        if lcd == aio_scenes.LCD_DASHBOARD:
            self.set_dashboard_enabled(True)
            return True
        if lcd == aio_scenes.LCD_LIQUID:
            return bool(self.set_lcd_liquid())
        if not os.path.exists(lcd):
            # Reported, not fatal: the colour half of the scene still applied.
            _log.warning("scene_lcd_missing path=%s", lcd)
            return False
        return bool(self.set_lcd_image(lcd))

    # ------------------------------------------------------------------
    # Lighting profiles via OpenRGB (spec 023)
    # ------------------------------------------------------------------

    LIGHTING_OK = "ok"
    LIGHTING_NO_SERVER = "no-server"
    LIGHTING_NO_DEVICES = "no-devices"
    LIGHTING_NO_SCOPED = "no-scoped-devices"

    def lighting_health(self) -> tuple[str, str]:
        """Classify the lighting stack. Returns (state, human-readable reason).

        Exists because every layer reported success against an empty device list
        after a reboot: the OpenRGB server had started before its devices were
        enumerable, and since it detects only once, the truncated list was frozen
        for the session. Nothing downstream could tell "no devices" from "nothing
        to do". See spec 026.
        """
        if not rgb_openrgb.server_alive():
            return self.LIGHTING_NO_SERVER, (
                "OpenRGB server is not reachable on "
                f"{rgb_openrgb.OPENRGB_HOST}:{rgb_openrgb.OPENRGB_PORT}")
        if not self._lighting_devices:
            return self.LIGHTING_NO_DEVICES, (
                "OpenRGB server is up but the monitor has no device list yet")
        scoped = rgb_openrgb.scoped_devices(self._lighting_devices,
                                            self._lighting_scope)
        if not scoped:
            return self.LIGHTING_NO_SCOPED, (
                f"OpenRGB reports {len(self._lighting_devices)} device(s) but none "
                "match the lighting scope - the server most likely started before "
                "the RGB hardware was enumerable; restart openrgb-server.service")
        return self.LIGHTING_OK, f"{len(scoped)} device(s) in scope"

    def unmatched_scope_entries(self) -> tuple[str, ...]:
        """Scope entries with no device in the current list.

        A non-empty result during startup means OpenRGB has not finished
        enumerating — the list is *partial*, which `lighting_health` cannot see
        because one matched device already reads as OK. That partial state is
        what made a scene silently skip the motherboard after a reboot.
        """
        return tuple(
            entry for entry in self._lighting_scope
            if not any(rgb_openrgb.in_scope(d.get("name", ""), (entry,))
                       for d in self._lighting_devices)
        )

    def lighting_available(self) -> bool:
        """True when the OpenRGB server is reachable.

        Checked by socket rather than by running a command: with the server
        down, `openrgb --client` silently falls back to a ~9 s local detection
        and still exits 0, so success proves nothing about the server.
        """
        return rgb_openrgb.server_alive()

    def refresh_lighting_devices(self, on_done=None):
        """Re-read the device list, modes included, through the queue."""
        def done(ok: bool, out: bytes, err: str):
            devices = rgb_openrgb.parse_detailed(out) if ok else []
            if not ok:
                _log.warning("lighting_list_failed err=%s", (err or "")[:200])
            self._lighting_devices = devices
            if on_done is not None:
                on_done(devices)

        return self.queue.submit(rgb_openrgb.detail_argv(),
                                 aio_queue.PRIORITY_READ, on_done=done,
                                 coalesce_key="rgb-list")

    @property
    def lighting_devices(self) -> list[dict]:
        return list(self._lighting_devices)

    def apply_lighting(self, intent: str, rgb: tuple[int, int, int] | None = None,
                       scope: tuple[str, ...] | None = None,
                       remember: str | None = None) -> int:
        """Apply one lighting intent across every in-scope device.

        Each device gets the mode *it* supports for the intent, because mode
        vocabularies do not overlap: the RTX 4090 has no `Static` and the Kraken
        has no `Off`. Broadcasting a single mode is how the GPU was switched off
        during investigation — it rejected the mode and went dark regardless. A
        device that cannot express the intent is skipped and logged, rather than
        failing the whole profile.

        Returns how many devices were addressed.
        """
        if not self._lighting_devices:
            # The device list was previously populated only when the Lighting
            # menu was built, so anything driven from outside the UI — a numpad
            # scene, most obviously — silently did nothing: the colour half
            # found no devices while the LCD half succeeded, so the call still
            # reported success. Populate on demand and apply when the list
            # lands. Returns 0 because nothing was addressed *yet*.
            _log.warning("lighting_devices_unknown deferring intent=%s", intent)
            self.refresh_lighting_devices(
                on_done=lambda _devices: self._apply_lighting_now(
                    intent, rgb, scope, remember))
            return 0
        return self._apply_lighting_now(intent, rgb, scope, remember)

    def _apply_lighting_now(self, intent: str, rgb, scope, remember=None) -> int:
        """Apply to the devices already known. Assumes the list is populated."""
        devices = rgb_openrgb.scoped_devices(
            self._lighting_devices, scope or self._lighting_scope)
        if not devices:
            state, reason = self.lighting_health()
            _log.warning("lighting_cannot_apply state=%s reason=%s", state, reason)
            # Re-read the device list so a later attempt can succeed, but do not
            # pretend this one did anything.
            if state in (self.LIGHTING_NO_DEVICES, self.LIGHTING_NO_SCOPED):
                self.refresh_lighting_devices()
            return 0

        sent = 0
        for device in devices:
            if intent == "off" and rgb_openrgb.in_scope(
                    device.get("name", ""), rgb_openrgb.OFF_EXEMPT):
                # Coloured by a scene, never blanked by one - see OFF_EXEMPT.
                continue
            mode = rgb_openrgb.resolve_mode(device.get("modes", []), intent,
                                            device.get("name"))
            if mode is None:
                _log.warning("lighting_intent_unsupported device=%s intent=%s",
                             device.get("name"), intent)
                continue

            colour = rgb
            if intent == "off":
                # A device with no Off mode expresses it as its solid mode set
                # to black; the Kraken is exactly this case.
                colour = (0, 0, 0) if mode.lower() != "off" else None

            argv = rgb_openrgb.set_color_argv(device["name"], mode, colour)
            if argv is None:
                continue
            name = device["name"]
            self.queue.submit(
                argv, aio_queue.PRIORITY_WRITE,
                on_done=lambda ok, out, err, n=name: (
                    None if ok else _log.warning(
                        "lighting_write_failed device=%s err=%s", n, (err or "")[:160])
                ),
                # Lighting is a state, not a sequence. Three scenes pressed in a
                # second is 12 jobs against MAX_PENDING=8, and the overflow path
                # was dropping writes arbitrarily. Keyed per device, a newer scene
                # supersedes the pending one instead, so the result is whatever
                # was asked for last. See spec 026.
                coalesce_key=f"rgb:{name}",
            )
            sent += 1

        if sent and remember:
            # Persist here rather than in the caller, so a deferred apply
            # remembers the colour just as a direct one does.
            self._lighting_last_color = remember
            self.lightingChanged.emit(remember)
        return sent

    def apply_lighting_color(self, value: str,
                             scope: tuple[str, ...] | None = None,
                             remember: bool = True) -> int:
        """Solid colour by name or #rrggbb across the scope; 'off' blanks it.

        `remember=False` applies without persisting or emitting lightingChanged -
        for a periodic re-assert, which is re-sending a colour the user already
        chose rather than a new choice.
        """
        rgb = aio_color.parse_color(value)
        if rgb is None:
            _log.warning("lighting_bad_color value=%r", value)
            return 0
        keep = value if remember else None
        if rgb == (0, 0, 0):
            return self.apply_lighting("off", scope=scope, remember=keep)
        return self.apply_lighting("solid", rgb, scope=scope, remember=keep)

    def reassert_lighting(self) -> int:
        """Re-send the current colour to devices that do not hold it.

        Returns the number of devices written, so a caller (and a test) can tell
        a real re-assert from a no-op.
        """
        value = self._lighting_last_color
        if not value:
            return 0
        # Skip silently when the device list is empty: apply would log a warning
        # and trigger a refresh, and doing that once a minute while OpenRGB is
        # down would bury the log in noise for no benefit.
        if not self._lighting_devices:
            return 0
        return self.apply_lighting_color(
            value, scope=LIGHTING_REASSERT_SCOPE, remember=False)

    @property
    def lighting_last_color(self) -> str | None:
        """Last colour applied, for the menu to mark and settings to persist."""
        return self._lighting_last_color

    @property
    def lighting_scope(self) -> tuple:
        return tuple(self._lighting_scope)

    def set_lighting_scope(self, scope) -> bool:
        """Replace the device scope a profile drives."""
        if not scope or not all(isinstance(t, str) and t for t in scope):
            _log.warning("lighting_bad_scope scope=%r", scope)
            return False
        self._lighting_scope = tuple(scope)
        return True

    def restore_lighting_state(self, last_color: str | None, scope=None):
        """Re-seed remembered state at startup without touching the hardware.

        Deliberately does not re-apply: lighting is physical state that survived
        the restart, and stamping over whatever the devices are showing just
        because the app restarted would be surprising.
        """
        if scope:
            self.set_lighting_scope(scope)
        if last_color and aio_color.parse_color(last_color) is not None:
            self._lighting_last_color = last_color

    # ------------------------------------------------------------------
    # Kraken RGB and LCD control (spec 021)
    # ------------------------------------------------------------------

    def kraken_available(self) -> bool:
        """True when liquidctl reported a cooler on the last poll.

        Menus gate on this, so a machine with no Kraken shows no controls rather
        than offering buttons that invoke nothing.
        """
        return self._last_snapshot.get("cooler_source") == "liquidctl"

    def _submit_write(self, argv, description: str, coalesce_key: str | None = None):
        """Queue a user-initiated write ahead of polling."""
        if not argv:
            _log.warning("aio_write_rejected what=%s", description)
            return False

        def done(ok: bool, _out: bytes, err: str):
            if not ok:
                _log.warning("aio_write_failed what=%s err=%s", description,
                             (err or "")[:200])
        return self.queue.submit(argv, aio_queue.PRIORITY_WRITE, on_done=done,
                                 coalesce_key=coalesce_key)

    def set_lcd_brightness(self, level: int):
        return self._submit_write(
            aio_liquid.lcd_brightness_argv(level), f"lcd brightness {level}")

    def set_lcd_orientation(self, degrees: int):
        return self._submit_write(
            aio_liquid.lcd_orientation_argv(degrees), f"lcd orientation {degrees}")

    def set_lcd_liquid(self):
        """Hand the LCD back to the firmware's own coolant readout."""
        self.set_dashboard_enabled(False)
        return self._submit_write(aio_liquid.lcd_liquid_argv(), "lcd liquid", coalesce_key="lcd")

    def set_lcd_static(self, path: str):
        self.set_dashboard_enabled(False)
        return self._submit_write(
            aio_liquid.lcd_static_argv(path), "lcd static", coalesce_key="lcd")

    def set_lcd_gif(self, path: str):
        self.set_dashboard_enabled(False)
        return self._submit_write(aio_liquid.lcd_gif_argv(path), "lcd gif", coalesce_key="lcd")

    def set_lcd_image(self, path: str):
        """Show an image, animating it when it actually has frames.

        Spec 021 routed every picked file to `static`, so an animated GIF showed
        frame one and nothing else. The choice is made by reading the file, not
        by its extension.
        """
        if aio_liquid.is_animated(path):
            return self.set_lcd_gif(path)
        return self.set_lcd_static(path)

    @property
    def dashboard_enabled(self) -> bool:
        """Live state of the LCD dashboard. The menu reads this, not settings."""
        return self._lcd_dashboard_enabled

    @property
    def dashboard_interval_ms(self) -> int:
        return self._lcd_interval_ms

    @property
    def dashboard_keepalive_ms(self) -> int:
        return self._lcd_keepalive_ms

    def set_dashboard_keepalive(self, interval_ms: int) -> bool:
        """Set the maximum time the screen may go unwritten. 0 disables."""
        if interval_ms not in LCD_KEEPALIVE_OPTIONS_MS:
            _log.warning("aio_lcd_bad_keepalive ms=%r", interval_ms)
            return False
        self._lcd_keepalive_ms = int(interval_ms)
        self._lcd_timer.invalidate()   # let a shortened keep-alive apply now
        return True

    def set_dashboard_interval(self, interval_ms: int) -> bool:
        """Change the push cadence. Applied immediately, no restart."""
        if interval_ms not in LCD_PUSH_INTERVALS_MS:
            _log.warning("aio_lcd_bad_interval ms=%r", interval_ms)
            return False
        self._lcd_interval_ms = int(interval_ms)
        # Let a shortened interval take effect now rather than after the old one.
        self._lcd_timer.invalidate()
        return True

    def set_dashboard_enabled(self, enabled: bool):
        """Turn the live LCD dashboard on or off.

        Emits `dashboardChanged` on any real change so callers never have to
        remember to mirror it — the desync this fixes was caused by exactly that
        kind of remembering.
        """
        enabled = bool(enabled)
        if enabled == self._lcd_dashboard_enabled:
            return
        self._lcd_dashboard_enabled = enabled
        self._lcd_failures = 0
        self._lcd_last_pushed = None
        if enabled:
            # Push immediately rather than waiting out the first interval.
            self._lcd_timer.invalidate()
        else:
            self.queue.clear_idle()
        self.dashboardChanged.emit(enabled)

    def _maybe_push_dashboard(self, snapshot: dict):
        """Render and push the LCD, subject to cadence, change and health gates.

        Cheapest checks first. Writing rarely is still the defence against
        liquidctl#774, but it is now floored by a keep-alive: the device drops a
        host-pushed image on its own, so below some refresh period the dashboard
        is simply not on screen. See spec 028.
        """
        if not self._lcd_dashboard_enabled:
            return
        if snapshot.get("cooler_source") != "liquidctl":
            return
        elapsed = self._lcd_timer.elapsed() if self._lcd_timer.isValid() else None
        # A tint change is a direct user action — they pressed a scene key — so it
        # bypasses the cadence gate. Waiting up to the full interval made the
        # lights change instantly while the screen kept the old tint for another
        # 17 s (measured). Rapid presses cannot spam the device: LCD writes share
        # one coalesce key, so only the newest survives the queue.
        tint = self._active_tint()
        tint_changed = tint != self._lcd_tint
        if (elapsed is not None and elapsed < self._lcd_interval_ms
                and not tint_changed):
            return

        # A keep-alive push happens even when nothing changed, because the device
        # drops the image by itself (spec 028). Zero disables it, restoring the
        # change-only behaviour of specs 021/022.
        keepalive_due = (
            self._lcd_keepalive_ms > 0
            and (elapsed is None or elapsed >= self._lcd_keepalive_ms)
        )

        snapshot = self._lcd_snapshot(snapshot)
        if not keepalive_due and not tint_changed and not aio_dashboard.should_push(
                snapshot, self._lcd_last_pushed):
            # Nothing worth redrawing and the image is not due to expire; restart
            # the clock and write nothing.
            self._lcd_timer.restart()
            return

        image = aio_dashboard.render_dashboard(snapshot, tint)
        if not aio_dashboard.write_gif(image, LCD_IMAGE_PATH):
            return

        argv = aio_liquid.lcd_gif_argv(LCD_IMAGE_PATH)
        if not argv:
            return

        pushed = dict(snapshot)

        def done(ok: bool, _out: bytes, err: str):
            if ok:
                self._lcd_failures = 0
                # Compare future snapshots against what is actually on screen,
                # not against the newest sample: otherwise a value creeping past
                # the threshold in small steps would never trigger a write.
                self._lcd_last_pushed = pushed
                self._lcd_tint = tint
                # Logged because a *successful* push was previously invisible:
                # only failures were recorded, so "the screen reverted" could not
                # be correlated with whether a write had just happened, or with
                # how long the image survived between writes.
                _log.info("aio_lcd_pushed coolant=%s cpu=%s gpu=%s pump=%s",
                          pushed.get("coolant_temp_c"), pushed.get("cpu_temp_c"),
                          pushed.get("gpu_temp_c"), pushed.get("pump_rpm"))
                return
            self._lcd_failures += 1
            _log.warning("aio_lcd_push_failed n=%d err=%s",
                         self._lcd_failures, (err or "")[:200])
            if self._lcd_failures >= LCD_MAX_FAILURES:
                self._surrender_dashboard()

        self._lcd_timer.restart()
        self.queue.submit(argv, aio_queue.PRIORITY_IDLE, on_done=done,
                          coalesce_key="lcd")

    def _lcd_snapshot(self, snapshot: dict) -> dict:
        """The snapshot as the LCD should show it: CPU smoothed, not raw.

        Raw CPU on this chip swings ~45 C between idle and any compile, which
        made the push gate useless — it changed on nearly every sample, so the
        screen was rewritten every interval and the firmware readout flashed
        through constantly.

        The sparkline already plots CPU as a 60 s trailing mean for exactly this
        reason ("raw CPU is too spiky to read at this size"). Reusing that mean
        here keeps the two displays consistent and gives the gate a value that
        actually holds still. The mean is read, never appended to: feeding the
        window from here would double-count every sample.
        """
        raw = getattr(self, "_cpu_raw", None)
        if not raw:
            return snapshot
        smoothed = dict(snapshot)
        smoothed["cpu_temp_c"] = sum(raw) / len(raw)
        return smoothed

    def _active_tint(self):
        """RGB of the current lighting colour, for tinting the dashboard.

        The dashboard is drawn in colours *complementary* to the lights, so the
        screen relates to them without competing. Returns None when no colour has
        been applied, which renders the default palette.
        """
        value = self._lighting_last_color
        if not value:
            return None
        rgb = aio_color.parse_color(value)
        if rgb is None or rgb == (0, 0, 0):
            return None
        return rgb

    def _surrender_dashboard(self):
        """Give up on the dashboard after repeated failures.

        Falls back to the firmware's `liquid` readout, which is drawn by the
        device and needs no host traffic, so it cannot hit the bucket-switch
        failure. Cooling telemetry and alerting are unaffected throughout.
        """
        _log.warning("aio_lcd_dashboard_surrendered failures=%d", self._lcd_failures)
        # Through the setter, not by assignment: it is the only thing that emits
        # dashboardChanged, and a second place mutating this flag is precisely
        # the desync spec 022 removes.
        self.set_dashboard_enabled(False)
        self._submit_write(aio_liquid.lcd_liquid_argv(), "lcd liquid (fallback)")
        self._notify(
            "LCD dashboard disabled",
            "Repeated LCD write failures; reverted to the cooler's built-in "
            "temperature display. Cooling monitoring is unaffected.",
            critical=False,
        )
