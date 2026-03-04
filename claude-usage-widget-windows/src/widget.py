"""PySide6 floating widget for Claude usage display.

Layout mirrors the Claude section in peripheral-battery-monitor:
  Row 1: [icon] Claude Code              2h 15m
  Row 2: [████████████░░░░░░░░░░░░░░░░░░]
  Row 3: 5h: 26%                      7d: 31%
"""

from PySide6.QtCore import Qt, QPoint, QSize
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMenu,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from .display import usage_color, format_percentage, error_message, COLOR_GRAY


def _make_terminal_icon(size: int = 16) -> QPixmap:
    """Draw a simple terminal/console icon as a pixmap."""
    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(QColor(0, 0, 0, 0))
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    # Rounded rect body
    p.setPen(QColor("#aaaaaa"))
    p.setBrush(QColor(60, 60, 60, 200))
    p.drawRoundedRect(1, 1, size - 2, size - 2, 3, 3)
    # ">" prompt
    p.setPen(QColor("#e0e0e0"))
    font = p.font()
    font.setPixelSize(int(size * 0.6))
    font.setBold(True)
    p.setFont(font)
    p.drawText(3, 1, size - 4, size - 2, Qt.AlignmentFlag.AlignVCenter, ">_")
    p.end()
    return pixmap


class FloatingWidget(QWidget):
    """Frameless, semi-transparent, always-on-top Claude usage widget."""

    def __init__(
        self,
        on_refresh: callable = None,
        on_exit: callable = None,
        opacity: float = 0.95,
        position: list[int] | None = None,
    ):
        super().__init__()
        self._on_refresh = on_refresh
        self._on_exit = on_exit
        self._drag_pos: QPoint | None = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(opacity)
        self.setFixedWidth(220)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        self._build_ui()

        if position:
            self.move(position[0], position[1])
        else:
            self._position_bottom_right()

    def _position_bottom_right(self) -> None:
        """Position widget in the bottom-right corner of the primary screen."""
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.right() - self.width() - 16
            y = geo.bottom() - 100
            self.move(x, y)

    def _build_ui(self) -> None:
        """Build compact 3-row layout matching peripheral-battery-monitor."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._container = QWidget(self)
        self._container.setObjectName("container")
        self._container.setStyleSheet("""
            #container {
                background-color: rgba(35, 35, 35, 230);
                border-radius: 8px;
                border: 1px solid rgba(255, 255, 255, 20);
            }
        """)

        cl = QVBoxLayout(self._container)
        cl.setContentsMargins(12, 8, 12, 10)
        cl.setSpacing(4)

        # Row 1: [icon] Claude Code              countdown
        header_row = QHBoxLayout()
        header_row.setSpacing(6)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(_make_terminal_icon(16))
        header_row.addWidget(icon_lbl)

        title_lbl = QLabel("Claude Code")
        title_lbl.setStyleSheet("color: #aaaaaa; font-size: 11px; font-weight: bold;")
        header_row.addWidget(title_lbl)

        header_row.addStretch()

        self._countdown_label = QLabel("--")
        self._countdown_label.setStyleSheet("color: #888888; font-size: 9px;")
        header_row.addWidget(self._countdown_label)

        cl.addLayout(header_row)

        # Row 2: thin progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setObjectName("ClaudeProgress")
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(8)
        self._set_bar_color(COLOR_GRAY)
        cl.addWidget(self._progress_bar)

        # Row 3: 5h: XX%                    7d: YY%
        stats_row = QHBoxLayout()

        self._five_hour_label = QLabel("5h: --")
        self._five_hour_label.setStyleSheet("color: #888888; font-size: 9px;")
        stats_row.addWidget(self._five_hour_label)

        stats_row.addStretch()

        self._seven_day_label = QLabel("7d: --")
        self._seven_day_label.setStyleSheet("color: #888888; font-size: 9px;")
        stats_row.addWidget(self._seven_day_label)

        cl.addLayout(stats_row)

        # Status line (errors, stale — hidden unless needed)
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #6b7280; font-size: 9px;")
        self._status_label.setVisible(False)
        cl.addWidget(self._status_label)

        layout.addWidget(self._container)

    def _set_bar_color(self, color_hex: str) -> None:
        """Update the progress bar color."""
        self._progress_bar.setStyleSheet(f"""
            QProgressBar#ClaudeProgress {{
                background-color: rgba(255, 255, 255, 25);
                border: none;
                border-radius: 4px;
            }}
            QProgressBar#ClaudeProgress::chunk {{
                background-color: {color_hex};
                border-radius: 4px;
            }}
        """)

    def update_usage(self, data: dict | None) -> None:
        """Update the widget display with new usage data."""
        if data is None:
            self._show_error("Not logged in \u2014 run `claude login`")
            return

        error = data.get("error")
        if error:
            error_msg = self._error_message(error)
            if error in ("auth_backoff", "offline", "api_error"):
                self._show_stale(error_msg)
            else:
                self._show_error(error_msg)
            return

        five_hour = data.get("five_hour", {})
        seven_day = data.get("seven_day", {})

        util_5h = five_hour.get("utilization")
        util_7d = seven_day.get("utilization")
        resets_at = five_hour.get("resets_at", "")

        # Progress bar
        pct_value = min(100, int(util_5h or 0))
        color = usage_color(util_5h)
        self._progress_bar.setValue(pct_value)
        self._set_bar_color(color)

        # Stats labels
        self._five_hour_label.setText(f"5h: {format_percentage(util_5h)}")

        # Build 7d text with model breakdowns if available
        right_parts = [f"7d: {format_percentage(util_7d)}"]
        for key in ("seven_day_opus", "seven_day_sonnet"):
            bucket = data.get(key)
            if bucket and bucket.get("utilization", 0) > 0:
                label = key.replace("seven_day_", "").capitalize()
                right_parts.append(f"{label}: {bucket['utilization']:.0f}%")
        self._seven_day_label.setText(" | ".join(right_parts))

        # Countdown
        if resets_at:
            from .oauth import get_time_until_reset
            self._countdown_label.setText(f"Resets in {get_time_until_reset(resets_at)}")
        else:
            self._countdown_label.setText("")

        self._status_label.setVisible(False)

    def _show_error(self, message: str) -> None:
        """Display an error/status message, reset bar to empty."""
        self._five_hour_label.setText("5h: --")
        self._progress_bar.setValue(0)
        self._set_bar_color(COLOR_GRAY)
        self._countdown_label.setText("")
        self._seven_day_label.setText("7d: --")
        self._status_label.setText(message)
        self._status_label.setVisible(True)

    def _show_stale(self, message: str) -> None:
        """Show stale data indicator while keeping last-known values."""
        self._status_label.setText(message)
        self._status_label.setVisible(True)

    @staticmethod
    def _error_message(error_code: str) -> str:
        return error_message(error_code)

    def _show_context_menu(self, pos) -> None:
        """Show right-click context menu."""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2b2b2b;
                color: #e0e0e0;
                border: 1px solid #555;
                padding: 4px;
            }
            QMenu::item:selected {
                background-color: #3d3d3d;
            }
        """)

        refresh_action = QAction("Refresh Now", self)
        refresh_action.triggered.connect(self._request_refresh)
        menu.addAction(refresh_action)

        menu.addSeparator()

        minimize_action = QAction("Minimize to Tray", self)
        minimize_action.triggered.connect(self._minimize_to_tray)
        menu.addAction(minimize_action)

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self._request_exit)
        menu.addAction(exit_action)

        menu.exec(self.mapToGlobal(pos))

    def _request_refresh(self) -> None:
        """Trigger a manual refresh."""
        if self._on_refresh:
            self._on_refresh()

    def _minimize_to_tray(self) -> None:
        """Hide the widget (tray icon remains)."""
        self.hide()

    def _request_exit(self) -> None:
        """Request application exit."""
        if self._on_exit:
            self._on_exit()

    # Drag support
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None
        from .config import set_setting
        set_setting("widget_position", [self.x(), self.y()])

    def paintEvent(self, event) -> None:
        """Paint transparent background (container handles its own rounded rect)."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(self.rect().toRectF(), 10, 10)
        painter.fillPath(path, QColor(0, 0, 0, 0))
        painter.end()
