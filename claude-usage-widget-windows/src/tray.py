"""System tray icon using QSystemTrayIcon."""

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

import structlog

from .display import usage_color, format_percentage, COLOR_GRAY

log = structlog.get_logger(__name__)


def create_tray_icon_pixmap(color_hex: str, utilization: float | None = None) -> QPixmap:
    """Generate a 64x64 tray icon: colored circle with pieslice fill."""
    size = 64
    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(QColor(0, 0, 0, 0))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    color = QColor(color_hex)
    border = 4
    inner = 8

    # Outer ring
    pen = painter.pen()
    pen.setColor(color)
    pen.setWidth(border)
    painter.setPen(pen)
    painter.setBrush(QColor(0, 0, 0, 0))
    painter.drawEllipse(border, border, size - 2 * border, size - 2 * border)

    # Filled arc based on utilization
    if utilization and utilization > 0:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        start_angle = 90 * 16  # Qt uses 1/16th degree, 90° = top
        span_angle = -int((utilization / 100) * 360 * 16)  # Negative = clockwise
        painter.drawPie(inner, inner, size - 2 * inner, size - 2 * inner,
                        start_angle, span_angle)

    painter.end()
    return pixmap


class SystemTray:
    """QSystemTrayIcon wrapper for Claude usage display."""

    def __init__(
        self,
        on_toggle_widget: callable = None,
        on_refresh: callable = None,
        on_exit: callable = None,
    ):
        self._on_toggle_widget = on_toggle_widget
        self._on_refresh = on_refresh
        self._on_exit = on_exit

        self._tray = QSystemTrayIcon()
        self._tray.setIcon(QIcon(create_tray_icon_pixmap(COLOR_GRAY)))
        self._tray.setToolTip("Claude Usage Widget")
        self._tray.activated.connect(self._on_activated)

        self._build_menu()
        self._tray.show()
        log.info("tray_created")

    def _build_menu(self) -> None:
        """Build the tray context menu."""
        menu = QMenu()

        show_action = QAction("Show/Hide Widget", menu)
        show_action.triggered.connect(self._toggle_widget)
        menu.addAction(show_action)

        menu.addSeparator()

        refresh_action = QAction("Refresh Now", menu)
        refresh_action.triggered.connect(self._refresh)
        menu.addAction(refresh_action)

        menu.addSeparator()

        exit_action = QAction("Exit", menu)
        exit_action.triggered.connect(self._exit)
        menu.addAction(exit_action)

        self._tray.setContextMenu(menu)

    def _on_activated(self, reason) -> None:
        """Handle tray icon activation (left-click)."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._toggle_widget()

    def _toggle_widget(self) -> None:
        if self._on_toggle_widget:
            self._on_toggle_widget()

    def _refresh(self) -> None:
        if self._on_refresh:
            self._on_refresh()

    def _exit(self) -> None:
        if self._on_exit:
            self._on_exit()

    def update_usage(self, data: dict | None) -> None:
        """Update tray icon and tooltip from usage data."""
        if data is None or data.get("error"):
            self._tray.setIcon(QIcon(create_tray_icon_pixmap(COLOR_GRAY)))
            self._tray.setToolTip("Claude Usage Widget — no data")
            return

        five_hour = data.get("five_hour", {})
        seven_day = data.get("seven_day", {})

        util_5h = five_hour.get("utilization")
        util_7d = seven_day.get("utilization")

        color = usage_color(util_5h)
        pixmap = create_tray_icon_pixmap(color, util_5h)
        self._tray.setIcon(QIcon(pixmap))

        tooltip = f"Claude: 5h {format_percentage(util_5h)} | 7d {format_percentage(util_7d)}"
        self._tray.setToolTip(tooltip)

    def hide(self) -> None:
        """Hide the tray icon."""
        self._tray.hide()
