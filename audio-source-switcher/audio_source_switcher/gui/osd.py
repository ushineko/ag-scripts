"""On-screen volume indicator (OSD).

A single frameless panel, owned by the running tray instance, that appears
centered on the active monitor when the volume changes and updates in place on
rapid repeat operations. Replaces per-keypress ``notify-send`` popups.

The visual style is modelled on KDE's Oxygen theme: a light, glassy gradient
panel with a soft drop shadow, a recessed groove, and a glossy blue fill, using
the system speaker icon (so it picks up the active icon set).

Wayland notes (see spec 009): a parentless ``Qt.ToolTip`` fails to map, and a
Wayland client cannot set its own absolute position or stacking. A frameless
``Qt.Tool`` window maps fine; centering + keep-above come from a KWin rule that
matches this widget by its per-screen window title (``install_kwin_rule.py``).
The Qt frameless/stay-on-top hints and ``move()`` below are best-effort fallbacks
for X11 and non-KWin compositors.
"""

from PyQt6.QtCore import Qt, QTimer, QRectF, QRect
from PyQt6.QtGui import (
    QCursor, QGuiApplication, QPainter, QColor, QFont, QPainterPath,
    QLinearGradient, QIcon,
)
from PyQt6.QtWidgets import QWidget

# Fixed size (including the shadow margin) so per-screen centering math — here and
# in the installer — is exact.
OSD_WIDTH = 380
OSD_HEIGHT = 132

# Space reserved around the panel for the soft drop shadow.
_SHADOW = 14

# Title base; the actual title encodes the screen origin so KWin can force a
# per-monitor centered position. All app windows share one Wayland app_id, so the
# title is the only reliable per-window discriminator for a KWin rule.
OSD_TITLE_BASE = "ass-volume-osd"

# How long the OSD stays visible after the last update.
HIDE_DELAY_MS = 1500

# Oxygen Dark palette (dark charcoal glass, light text, glossy blue fill).
_PANEL_TOP = QColor(0x3B, 0x40, 0x45)
_PANEL_BOTTOM = QColor(0x23, 0x27, 0x2A)
_PANEL_BORDER = QColor(0x14, 0x17, 0x1A)
_PANEL_HILIGHT = QColor(255, 255, 255, 46)      # subtle glass top highlight
_TEXT_PRIMARY = QColor(0xEF, 0xF0, 0xF1)
_TEXT_SECONDARY = QColor(0xB4, 0xB9, 0xBE)
_GROOVE_TOP = QColor(0x1A, 0x1D, 0x20)
_GROOVE_BOTTOM = QColor(0x2A, 0x2E, 0x31)
_GROOVE_BORDER = QColor(0x10, 0x13, 0x15)
_FILL_TOP = QColor(0x8E, 0xC1, 0xEE)
_FILL_MID = QColor(0x4A, 0x90, 0xD9)
_FILL_BOTTOM = QColor(0x2F, 0x6B, 0xB0)
_FILL_HILIGHT = QColor(0xBC, 0xDD, 0xF6)         # 1px gloss line at top of fill
_FILL_LOUD_MID = QColor(0xE2, 0xA1, 0x33)        # amber for >100%
_FILL_LOUD_BOTTOM = QColor(0xB8, 0x78, 0x18)
_FILL_MUTE_MID = QColor(0x6C, 0x71, 0x76)        # grey for muted
_FILL_MUTE_BOTTOM = QColor(0x4C, 0x50, 0x54)


def osd_title_for_screen(screen_x: int, screen_y: int) -> str:
    """Stable per-screen window title, keyed on the screen's origin."""
    return f"{OSD_TITLE_BASE}@{screen_x}_{screen_y}"


def _volume_icon_name(volume: int, muted: bool) -> str:
    if muted or volume == 0:
        return "audio-volume-muted"
    if volume < 34:
        return "audio-volume-low"
    if volume < 67:
        return "audio-volume-medium"
    return "audio-volume-high"


class VolumeOSD(QWidget):
    """Frameless, centered, keep-above volume indicator.

    Call :meth:`show_volume` to display/update it. Repeated calls update the same
    widget and restart a single auto-hide timer, so rapid volume presses coalesce
    into one panel rather than a stack of notifications.
    """

    def __init__(self, parent=None):
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Never steal focus from the app the user is actually working in.
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(OSD_WIDTH, OSD_HEIGHT)

        self._volume = 0
        self._muted = False
        self._icon = QIcon()
        self._screen_token = None  # (x, y) of the screen we last mapped onto

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    # ── Public API ────────────────────────────────────────────────────

    def show_volume(self, volume: int, muted: bool = False):
        """Show or update the OSD with ``volume`` (percent) and mute state."""
        self._volume = max(0, int(volume))
        self._muted = bool(muted)
        self._icon = QIcon.fromTheme(_volume_icon_name(self._volume, self._muted))

        target_screen = (
            QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        )
        geo = target_screen.geometry()
        token = (geo.x(), geo.y())

        # If the active screen changed while visible, re-map so KWin re-evaluates
        # placement for the new monitor's title (Wayland cannot relocate live).
        if self.isVisible() and token != self._screen_token:
            self.hide()

        self._screen_token = token
        self.setWindowTitle(osd_title_for_screen(geo.x(), geo.y()))

        # Best-effort centering for X11 / non-KWin; KWin rule enforces it on Wayland.
        cx = geo.x() + (geo.width() - self.width()) // 2
        cy = geo.y() + (geo.height() - self.height()) // 2
        self.move(cx, cy)

        self.update()
        if not self.isVisible():
            self.show()
            self.move(cx, cy)  # some compositors honor a post-show move
        self.raise_()

        self._hide_timer.start(HIDE_DELAY_MS)

    # ── Painting ──────────────────────────────────────────────────────

    def paintEvent(self, event):  # noqa: N802 (Qt override)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        panel = QRectF(
            _SHADOW, _SHADOW,
            self.width() - 2 * _SHADOW,
            self.height() - 2 * _SHADOW,
        )
        radius = 9.0

        self._paint_shadow(p, panel, radius)
        self._paint_panel(p, panel, radius)
        self._paint_content(p, panel)

        p.end()

    def _paint_shadow(self, p: QPainter, panel: QRectF, radius: float):
        # Soft drop shadow: a few expanding translucent rounded rects.
        steps = _SHADOW
        for i in range(steps, 0, -1):
            alpha = int(46 * (1 - i / steps) ** 2) + 4
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, alpha))
            r = panel.adjusted(-i, -i + 2, i, i + 3)  # bias downward
            path = QPainterPath()
            path.addRoundedRect(r, radius + i, radius + i)
            p.drawPath(path)

    def _paint_panel(self, p: QPainter, panel: QRectF, radius: float):
        grad = QLinearGradient(panel.topLeft(), panel.bottomLeft())
        grad.setColorAt(0.0, _PANEL_TOP)
        grad.setColorAt(1.0, _PANEL_BOTTOM)
        path = QPainterPath()
        path.addRoundedRect(panel, radius, radius)
        p.fillPath(path, grad)

        # Glassy inner top highlight.
        p.setPen(_PANEL_HILIGHT)
        hi = panel.adjusted(1.5, 1.5, -1.5, 0)
        hi_path = QPainterPath()
        hi_path.addRoundedRect(hi, radius - 1, radius - 1)
        p.drawPath(hi_path)

        # Outer border.
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(_PANEL_BORDER)
        p.drawPath(path)

    def _paint_content(self, p: QPainter, panel: QRectF):
        pad = 18
        icon_size = 46
        icon_x = int(panel.left() + pad)
        icon_y = int(panel.center().y() - icon_size / 2)
        if not self._icon.isNull():
            self._icon.paint(
                p, QRect(icon_x, icon_y, icon_size, icon_size),
                Qt.AlignmentFlag.AlignCenter,
            )
            content_left = icon_x + icon_size + 14
        else:
            content_left = icon_x

        content_right = int(panel.right() - pad)

        # Title + percentage row.
        row_y = int(panel.top() + pad)
        row_h = 30
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        p.setFont(font)
        p.setPen(_TEXT_PRIMARY)
        p.drawText(
            content_left, row_y, content_right - content_left, row_h,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "Volume",
        )
        label = "Muted" if self._muted else f"{self._volume}%"
        p.setPen(_TEXT_SECONDARY)
        p.drawText(
            content_left, row_y, content_right - content_left, row_h,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, label,
        )

        # Recessed groove.
        bar_h = 16
        bar_y = int(panel.bottom() - pad - bar_h)
        groove = QRectF(content_left, bar_y, content_right - content_left, bar_h)
        g_grad = QLinearGradient(groove.topLeft(), groove.bottomLeft())
        g_grad.setColorAt(0.0, _GROOVE_TOP)
        g_grad.setColorAt(1.0, _GROOVE_BOTTOM)
        g_path = QPainterPath()
        g_path.addRoundedRect(groove, bar_h / 2, bar_h / 2)
        p.fillPath(g_path, g_grad)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(_GROOVE_BORDER)
        p.drawPath(g_path)

        # Glossy fill.
        frac = min(self._volume, 100) / 100.0
        if frac > 0:
            fill_w = max(bar_h, groove.width() * frac)
            fill = QRectF(groove.left(), groove.top(), fill_w, bar_h)
            f_grad = QLinearGradient(fill.topLeft(), fill.bottomLeft())
            if self._muted:
                f_grad.setColorAt(0.0, _FILL_TOP)
                f_grad.setColorAt(0.5, _FILL_MUTE_MID)
                f_grad.setColorAt(1.0, _FILL_MUTE_BOTTOM)
            elif self._volume > 100:
                f_grad.setColorAt(0.0, _FILL_TOP)
                f_grad.setColorAt(0.5, _FILL_LOUD_MID)
                f_grad.setColorAt(1.0, _FILL_LOUD_BOTTOM)
            else:
                f_grad.setColorAt(0.0, _FILL_TOP)
                f_grad.setColorAt(0.5, _FILL_MID)
                f_grad.setColorAt(1.0, _FILL_BOTTOM)
            f_path = QPainterPath()
            f_path.addRoundedRect(fill, bar_h / 2, bar_h / 2)
            p.fillPath(f_path, f_grad)
            # 1px gloss line near the top of the fill.
            p.setPen(_FILL_HILIGHT)
            p.setBrush(Qt.BrushStyle.NoBrush)
            gloss = fill.adjusted(bar_h / 2, 1.5, -bar_h / 2, -bar_h / 2)
            if gloss.width() > 0:
                p.drawLine(
                    int(gloss.left()), int(gloss.top()),
                    int(gloss.right()), int(gloss.top()),
                )
