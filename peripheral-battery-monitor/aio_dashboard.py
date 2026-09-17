"""LCD dashboard rendering for the Kraken's 640x640 screen (spec 021).

Renders a snapshot into a QImage and writes it to a PNG that `liquidctl set lcd
screen static` can display. Qt is used rather than Pillow because it is already
this project's toolkit; liquidctl pulls in Pillow for its own decoding, but that
is its dependency, not ours.

Two design points worth keeping:

- **`content_key()` gates pushes.** The LCD's bucket-switching fails
  intermittently under repeated writes (liquidctl#774), so the cheapest
  mitigation is not writing. The key is derived at *displayed* precision, so a
  coolant temperature drifting 36.31 -> 36.34 C produces an identical key and no
  push. A machine at a steady idle writes nothing at all.
- **Rendering never raises.** A missing metric draws a placeholder. The LCD is
  decorative; a render failure must not disturb polling or alerting.
"""

from __future__ import annotations

import logging
import os

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPen

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


def content_key(snapshot: dict) -> tuple:
    """Identity of what would be drawn, at displayed precision.

    Two snapshots with the same key render identically, so the caller can skip
    the push entirely. This is the main defence against liquidctl#774.
    """
    if not isinstance(snapshot, dict):
        return (_PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, "ok")
    return (
        _fmt_temp(snapshot.get("coolant_temp_c")),
        _fmt_temp(snapshot.get("cpu_temp_c")),
        _fmt_rpm(snapshot.get("pump_rpm")),
        str(snapshot.get("alert_state") or "ok"),
    )


def render_dashboard(snapshot: dict) -> QImage:
    """Draw a snapshot at 640x640. Never raises."""
    image = QImage(SIZE, SIZE, QImage.Format.Format_RGB888)
    image.fill(_BG)

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
    p.setPen(QPen(QColor(32, 36, 44), 14))
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
    _metric(p, 0, "CPU", _fmt_temp(snap.get("cpu_temp_c")), "°C")
    _metric(p, 1, "PUMP", _fmt_rpm(snap.get("pump_rpm")), "RPM")

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


def _metric(p: QPainter, slot: int, label: str, value: str, unit: str):
    """One of the two bottom metrics; slot 0 is left, 1 is right."""
    width = (SIZE - 2 * _MARGIN) / 2
    x = _MARGIN + slot * width

    _centered(p, _MUTED, 18, QRectF(x, 416, width, 28), label)
    _centered(p, _ACCENT if value != _PLACEHOLDER else _MUTED, 44,
              QRectF(x, 446, width, 66), value, bold=True)
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
