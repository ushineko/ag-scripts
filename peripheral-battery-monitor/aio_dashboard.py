"""LCD dashboard rendering for the Kraken's 640x640 screen (spec 021).

Renders a snapshot into a QImage and writes it to a PNG that `liquidctl set lcd
screen static` can display. Qt is used rather than Pillow because it is already
this project's toolkit; liquidctl pulls in Pillow for its own decoding, but that
is its dependency, not ours.

Two design points worth keeping:

- **`should_push()` gates pushes.** The LCD misbehaves under repeated writes in
  two ways — liquidctl#774 bucket-switch failures, and the firmware readout
  showing through while a bucket is deleted and rewritten — so the cheapest
  mitigation is not writing. Coolant, pump state and alert state are compared at
  displayed precision; CPU temperature, which wanders continuously on this
  hardware and would otherwise defeat the gate entirely, must move
  `CPU_PUSH_DELTA_C` before it justifies a write. A machine at a steady idle
  writes nothing at all.
- **Rendering never raises.** A missing metric draws a placeholder. The LCD is
  decorative; a render failure must not disturb polling or alerting.
"""

from __future__ import annotations

import logging
import math
import os
import random

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (QColor, QFont, QImage, QPainter, QPen, QRadialGradient,
                         QLinearGradient)

_log = logging.getLogger(__name__)

SIZE = 640
_MARGIN = 40

# Dark ground: the panel is viewed in a case, and a mostly-black frame draws far
# less attention than a bright one when the machine is idle.
_BG = QColor(12, 14, 18)
_FG = QColor(236, 239, 244)
_MUTED = QColor(130, 140, 155)
_ACCENT = QColor(120, 190, 255)

# Coolant colour bands, matching the alert thresholds in aio_reader so the
# screen and the notifications never disagree.
_WARN_C = 50.0
_CRIT_C = 60.0
_OK = QColor(126, 200, 140)
_WARN = QColor(230, 180, 90)
_CRIT = QColor(235, 110, 110)

_PLACEHOLDER = "--"


# Starfield background (spec 024).
#
# Rendered once and cached: a field regenerated per frame would shimmer between
# updates, which on a screen that only redraws when something changes would read
# as a fault rather than decoration. The seed is fixed so the sky is the same
# after every restart.
_BG_SEED = 0x5EED
_STAR_COUNT = 420
_NEBULAE = (
    # (cx, cy, radius, rgb) as fractions of SIZE. Placed off-centre and kept
    # dim: the middle of the panel carries the headline number and must stay the
    # darkest part of the image.
    (0.20, 0.22, 0.46, (96, 60, 190)),
    (0.82, 0.30, 0.40, (30, 120, 170)),
    (0.68, 0.84, 0.44, (150, 45, 120)),
    (0.30, 0.78, 0.34, (40, 90, 160)),
)
_background_cache: QImage | None = None


def _background() -> QImage:
    """The starfield, built once per process."""
    global _background_cache
    if _background_cache is None:
        _background_cache = _render_background()
    return _background_cache


def _render_background() -> QImage:
    image = QImage(SIZE, SIZE, QImage.Format.Format_RGB888)
    image.fill(QColor(6, 7, 12))
    p = QPainter()
    if not p.begin(image):
        return image
    try:
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Base gradient: slightly lifted at the top, near-black at the bottom.
        sky = QLinearGradient(0, 0, 0, SIZE)
        sky.setColorAt(0.0, QColor(14, 16, 30))
        sky.setColorAt(0.6, QColor(8, 9, 16))
        sky.setColorAt(1.0, QColor(4, 5, 9))
        p.fillRect(0, 0, SIZE, SIZE, sky)

        # Nebulae: wide, very low-alpha radial washes.
        p.setPen(Qt.PenStyle.NoPen)
        for fx, fy, fr, (r, g, b) in _NEBULAE:
            cx, cy, rad = fx * SIZE, fy * SIZE, fr * SIZE
            grad = QRadialGradient(cx, cy, rad)
            grad.setColorAt(0.0, QColor(r, g, b, 58))
            grad.setColorAt(0.45, QColor(r, g, b, 22))
            grad.setColorAt(1.0, QColor(r, g, b, 0))
            p.setBrush(grad)
            p.drawEllipse(QPointF(cx, cy), rad, rad)

        _draw_stars(p)
        _draw_vignette(p)
    except Exception:
        _log.warning("background_render_failed", exc_info=True)
    finally:
        p.end()
    return image


def _draw_stars(p: QPainter):
    """Scatter stars, thinned towards the centre so the readout stays legible."""
    rng = random.Random(_BG_SEED)
    centre = SIZE / 2.0
    p.setPen(Qt.PenStyle.NoPen)
    for _ in range(_STAR_COUNT):
        x, y = rng.uniform(0, SIZE), rng.uniform(0, SIZE)
        # Distance from centre, 0 at the middle and 1 at the corners.
        d = math.hypot(x - centre, y - centre) / (centre * math.sqrt(2))
        # Reject most stars near the middle rather than dimming them: a faint
        # star behind a glyph still muddies it.
        if rng.random() > 0.12 + d * 1.25:
            continue

        bright = rng.random()
        radius = 0.4 + bright * 1.5
        alpha = int(55 + bright * 190)
        # Faint blue/amber tint on a minority, so it is not a grey pepper field.
        tint = rng.random()
        if tint < 0.18:
            colour = QColor(170, 200, 255, alpha)
        elif tint < 0.30:
            colour = QColor(255, 220, 180, alpha)
        else:
            colour = QColor(235, 240, 250, alpha)
        p.setBrush(colour)
        p.drawEllipse(QPointF(x, y), radius, radius)

        # A handful get a soft halo and a cross flare.
        if bright > 0.93:
            halo = QRadialGradient(x, y, radius * 7)
            halo.setColorAt(0.0, QColor(colour.red(), colour.green(), colour.blue(), 70))
            halo.setColorAt(1.0, QColor(colour.red(), colour.green(), colour.blue(), 0))
            p.setBrush(halo)
            p.drawEllipse(QPointF(x, y), radius * 7, radius * 7)
            p.setPen(QPen(QColor(colour.red(), colour.green(), colour.blue(), 90), 0.7))
            flare = radius * 4.5
            p.drawLine(QPointF(x - flare, y), QPointF(x + flare, y))
            p.drawLine(QPointF(x, y - flare), QPointF(x, y + flare))
            p.setPen(Qt.PenStyle.NoPen)


def _draw_vignette(p: QPainter):
    """Darken the middle so white text on stars stays readable."""
    centre = SIZE / 2.0
    grad = QRadialGradient(centre, centre, SIZE * 0.52)
    grad.setColorAt(0.0, QColor(0, 0, 0, 165))
    grad.setColorAt(0.55, QColor(0, 0, 0, 90))
    grad.setColorAt(1.0, QColor(0, 0, 0, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawRect(0, 0, SIZE, SIZE)


def _coolant_color(value) -> QColor:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return _MUTED
    if value >= _CRIT_C:
        return _CRIT
    if value >= _WARN_C:
        return _WARN
    return _OK


def _fmt_temp(value) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return _PLACEHOLDER
    return f"{value:.0f}"


def _fmt_rpm(value) -> str:
    if not isinstance(value, int) or isinstance(value, bool):
        return _PLACEHOLDER
    return str(value)


# How much a secondary value must move before it justifies an LCD write.
#
# Keying the gate on CPU temperature at whole-degree precision was a design
# error: an idle i9-14900K wanders several degrees continuously, so the key
# changed on essentially every sample and the gate never suppressed anything.
# Coolant, which the gate was designed around, moves under a degree an hour.
#
# The consequence of a threshold is that the CPU figure on screen can lag the
# true value by up to this much. It is never a *wrong* reading — it is a real
# measurement taken at the last push — and CPU is the dashboard's secondary
# metric. Coolant, pump state and alert state are NOT thresholded: those are
# what the screen exists to report, and they change slowly enough to key on
# directly.
CPU_PUSH_DELTA_C = 5.0
# Pump rpm jitters by a few counts at a fixed duty; ignore that, but never
# ignore a transition to or from zero.
PUMP_PUSH_DELTA_RPM = 50


def content_key(snapshot: dict) -> tuple:
    """Identity of what would be drawn, at displayed precision.

    Used for the values that are keyed directly. CPU temperature is compared
    with a threshold instead — see `should_push`.
    """
    if not isinstance(snapshot, dict):
        return (_PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, "ok")
    return (
        _fmt_temp(snapshot.get("coolant_temp_c")),
        _fmt_temp(snapshot.get("cpu_temp_c")),
        _fmt_rpm(snapshot.get("pump_rpm")),
        str(snapshot.get("alert_state") or "ok"),
    )


def _number(value):
    """A real number, or None for anything that is not one."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def should_push(new: dict, last: dict | None) -> bool:
    """True when `new` differs from the last pushed snapshot enough to redraw.

    Not writing is the main mitigation for both LCD problems — liquidctl#774
    bucket-switch failures, and the firmware readout showing through while a
    bucket is deleted and rewritten — so this decides how often the screen is
    touched at all.

    Anything that changes what the screen *says* about cooling pushes
    immediately. Only CPU temperature and small pump jitter are thresholded.
    """
    if not isinstance(new, dict):
        return False
    if last is None:
        return True

    # Coolant and alert state: any change at displayed precision is worth a
    # write. These are the reason the dashboard exists.
    if _fmt_temp(new.get("coolant_temp_c")) != _fmt_temp(last.get("coolant_temp_c")):
        return True
    if str(new.get("alert_state") or "ok") != str(last.get("alert_state") or "ok"):
        return True

    new_pump, last_pump = new.get("pump_rpm"), last.get("pump_rpm")
    # A pump starting or stopping is never jitter, and never suppressed.
    if (new_pump == 0) != (last_pump == 0):
        return True
    # Appearing or disappearing is a real change too.
    if (new_pump is None) != (last_pump is None):
        return True
    a, b = _number(new_pump), _number(last_pump)
    if a is not None and b is not None and abs(a - b) >= PUMP_PUSH_DELTA_RPM:
        return True

    new_cpu, last_cpu = _number(new.get("cpu_temp_c")), _number(last.get("cpu_temp_c"))
    if (new_cpu is None) != (last_cpu is None):
        return True
    if new_cpu is not None and last_cpu is not None:
        if abs(new_cpu - last_cpu) >= CPU_PUSH_DELTA_C:
            return True

    return False


def render_dashboard(snapshot: dict) -> QImage:
    """Draw a snapshot at 640x640. Never raises."""
    image = _background().copy()

    painter = QPainter()
    if not painter.begin(image):
        _log.debug("dashboard_painter_begin_failed")
        return image
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        _draw(painter, snapshot if isinstance(snapshot, dict) else {})
    except Exception:
        # Decorative output: never let a draw error reach the caller.
        _log.warning("dashboard_render_failed", exc_info=True)
    finally:
        painter.end()
    return image


def _draw(p: QPainter, snap: dict):
    coolant = snap.get("coolant_temp_c")
    coolant_col = _coolant_color(coolant)

    # Coolant ring: a single arc carrying the headline value's severity, so the
    # state is legible from across a room without reading the number.
    ring = QRectF(_MARGIN, _MARGIN, SIZE - 2 * _MARGIN, SIZE - 2 * _MARGIN)
    # Translucent: an opaque track cut a grey band through the starfield.
    p.setPen(QPen(QColor(120, 132, 156, 70), 14))
    p.drawArc(ring, 0, 360 * 16)

    if isinstance(coolant, (int, float)) and not isinstance(coolant, bool):
        # Map 20-70 C onto the full sweep, clamped.
        frac = max(0.0, min(1.0, (float(coolant) - 20.0) / 50.0))
        p.setPen(QPen(coolant_col, 14, cap=Qt.PenCapStyle.RoundCap))
        # Start at 12 o'clock, sweep clockwise.
        p.drawArc(ring, 90 * 16, -int(360 * 16 * frac))

    # Headline: coolant temperature. Every band below is centred within an
    # explicit non-overlapping rect — with AlignHCenter alone, Qt top-aligns the
    # glyphs and a 120pt number overruns its box into the unit beneath it.
    _centered(p, _MUTED, 22, QRectF(0, 132, SIZE, 36), "COOLANT")

    big = QFont("sans-serif", 118)
    big.setBold(True)
    p.setPen(coolant_col)
    p.setFont(big)
    p.drawText(QRectF(0, 170, SIZE, 158), Qt.AlignmentFlag.AlignCenter, _fmt_temp(coolant))

    _centered(p, _MUTED, 27, QRectF(0, 330, SIZE, 38), "°C")

    # Secondary row: CPU and pump.
    #
    # CPU is deliberately never colour-graded — an i9-14900K boosting to 100 C
    # is normal here and reddening it would cry wolf on every compile. A pump
    # reading zero is the opposite: it is the single most alarming number this
    # screen can show, and drawing it in the calm accent colour while the rest
    # of the panel turned red was actively misleading.
    pump = snap.get("pump_rpm")
    pump_stopped = isinstance(pump, int) and not isinstance(pump, bool) and pump == 0
    _metric(p, 0, "CPU", _fmt_temp(snap.get("cpu_temp_c")), "°C")
    _metric(p, 1, "PUMP", _fmt_rpm(pump), "RPM",
            color=_CRIT if pump_stopped else None)

    # Alert banner only when something is wrong; a healthy screen stays clean.
    state = snap.get("alert_state")
    if state in ("warning", "critical"):
        col = _CRIT if state == "critical" else _WARN
        text = str(snap.get("alert_reason") or state).upper()
        _centered(p, col, 18, QRectF(90, 372, SIZE - 180, 30), text, bold=True)


def _centered(p: QPainter, color: QColor, size: int, rect: QRectF, text: str,
              bold: bool = False):
    """Draw text centred in both axes within rect.

    Vertical centring is the point: Qt top-aligns by default, which lets a large
    glyph overrun its rect and collide with the band below.
    """
    font = QFont("sans-serif", size)
    font.setBold(bold)
    p.setPen(color)
    p.setFont(font)
    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)


def _metric(p: QPainter, slot: int, label: str, value: str, unit: str,
            color: QColor | None = None):
    """One of the two bottom metrics; slot 0 is left, 1 is right."""
    width = (SIZE - 2 * _MARGIN) / 2
    x = _MARGIN + slot * width

    if color is None:
        color = _ACCENT if value != _PLACEHOLDER else _MUTED
    _centered(p, _MUTED, 18, QRectF(x, 416, width, 28), label)
    _centered(p, color, 44, QRectF(x, 446, width, 66), value, bold=True)
    _centered(p, _MUTED, 16, QRectF(x, 516, width, 26), unit)


def write_png(image: QImage, path: str) -> bool:
    """Save a rendered image. False on any failure; callers skip the push."""
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        return bool(image.save(path, "PNG"))
    except Exception:
        _log.warning("dashboard_write_failed path=%s", path, exc_info=True)
        return False
