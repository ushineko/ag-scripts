"""PySide6 floating widget for Claude usage display.

Layout mirrors the Claude section in peripheral-battery-monitor:
  Row 1: [icon] Claude Code              2h 15m
  Row 2: [████████████░░░░░░░░░░░░░░░░░░]
  Row 3: 5h: 26%                      7d: 31%
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QPoint, QSize
from PySide6.QtGui import QAction, QActionGroup, QColor, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMenu,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

import structlog

from .display import usage_color, format_percentage, error_message, COLOR_GRAY
from .platform_support import IS_MACOS

log = structlog.get_logger(__name__)

# Selectable base font sizes (px) offered in the context menu. The title row
# renders 2px larger than the base; the widget width scales with the base so
# larger fonts don't clip. 9 is the original/default size.
FONT_PRESETS = (9, 11, 13, 16, 20)
DEFAULT_FONT_SIZE = 9
_BASE_WIDTH = 220  # widget width at the default font size

# Shared dark styling for context menus (and submenus, which don't inherit it).
_MENU_STYLE = """
    QMenu {
        background-color: #2b2b2b;
        color: #e0e0e0;
        border: 1px solid #555;
        padding: 4px;
    }
    QMenu::item:selected {
        background-color: #3d3d3d;
    }
"""


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
        font_size: int = DEFAULT_FONT_SIZE,
    ):
        super().__init__()
        self._on_refresh = on_refresh
        self._on_exit = on_exit
        self._drag_pos: QPoint | None = None
        self._font_size = font_size
        self._macos_level_applied = False

        # Qt.Tool keeps the widget off the taskbar and, on macOS, makes it an
        # NSPanel that floats above normal windows. On macOS that panel also
        # hides whenever the (background menu-bar agent) app loses focus, which
        # made the widget vanish — _apply_macos_window_level() fixes that after
        # the native window exists (see showEvent).
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(opacity)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        self._build_ui()
        self._apply_font_size()

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

        self._icon_lbl = QLabel()
        header_row.addWidget(self._icon_lbl)

        self._title_lbl = QLabel("Claude Code")
        header_row.addWidget(self._title_lbl)

        header_row.addStretch()

        self._countdown_label = QLabel("--")
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
        stats_row.addWidget(self._five_hour_label)

        stats_row.addStretch()

        self._seven_day_label = QLabel("7d: --")
        stats_row.addWidget(self._seven_day_label)

        cl.addLayout(stats_row)

        # Status line (errors, stale — hidden unless needed)
        self._status_label = QLabel("")
        self._status_label.setVisible(False)
        cl.addWidget(self._status_label)

        layout.addWidget(self._container)

    def _apply_font_size(self) -> None:
        """Apply the current font size to all labels and scale the widget width."""
        base = self._font_size
        title = base + 2
        self._title_lbl.setStyleSheet(
            f"color: #aaaaaa; font-size: {title}px; font-weight: bold;"
        )
        self._countdown_label.setStyleSheet(f"color: #888888; font-size: {base}px;")
        self._five_hour_label.setStyleSheet(f"color: #888888; font-size: {base}px;")
        self._seven_day_label.setStyleSheet(f"color: #888888; font-size: {base}px;")
        self._status_label.setStyleSheet(f"color: #6b7280; font-size: {base}px;")
        self._icon_lbl.setPixmap(_make_terminal_icon(base + 7))
        self.setFixedWidth(round(_BASE_WIDTH * base / DEFAULT_FONT_SIZE))
        self.adjustSize()

    def set_font_size(self, size: int) -> None:
        """Change the widget font size and persist it to config."""
        self._font_size = size
        self._apply_font_size()
        from .config import set_setting
        set_setting("font_size", size)

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
        menu.setStyleSheet(_MENU_STYLE)

        refresh_action = QAction("Refresh Now", self)
        refresh_action.triggered.connect(self._request_refresh)
        menu.addAction(refresh_action)

        font_menu = menu.addMenu("Font Size")
        font_menu.setStyleSheet(_MENU_STYLE)
        font_group = QActionGroup(self)
        font_group.setExclusive(True)
        for size in FONT_PRESETS:
            size_action = QAction(f"{size} px", self)
            size_action.setCheckable(True)
            size_action.setChecked(size == self._font_size)
            size_action.triggered.connect(lambda _=False, s=size: self.set_font_size(s))
            font_group.addAction(size_action)
            font_menu.addAction(size_action)

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

    def showEvent(self, event) -> None:
        """Apply the macOS always-visible window tweak once the native window exists."""
        super().showEvent(event)
        # Only on the native cocoa backend — under offscreen/other QPA platforms
        # winId() is not an NSView and poking it via objc_msgSend would crash.
        if (
            IS_MACOS
            and not self._macos_level_applied
            and QApplication.platformName() == "cocoa"
        ):
            self._macos_level_applied = self._apply_macos_window_level()
            log.info("macos_window_level_applied", ok=self._macos_level_applied)

    def _apply_macos_window_level(self) -> bool:
        """Keep the widget visible above other windows on macOS.

        A Qt.Tool window is an NSPanel that, for a background (accessory) app,
        hides whenever the app loses focus. Using the Objective-C runtime via
        ctypes (no extra dependency), set ``hidesOnDeactivate = NO`` and a
        floating window level so the widget stays put and on top. Best-effort:
        any failure leaves the default Qt behavior unchanged.
        """
        try:
            import ctypes
            import ctypes.util

            libobjc = ctypes.util.find_library("objc")
            if not libobjc:
                return False
            objc = ctypes.cdll.LoadLibrary(libobjc)
            objc.sel_registerName.restype = ctypes.c_void_p
            objc.sel_registerName.argtypes = [ctypes.c_char_p]

            def msg(receiver, selector, *args, argtypes=(), restype=ctypes.c_void_p):
                objc.objc_msgSend.restype = restype
                objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p, *argtypes]
                return objc.objc_msgSend(receiver, objc.sel_registerName(selector), *args)

            view = ctypes.c_void_p(int(self.winId()))
            if not view.value:
                return False
            window = msg(view, b"window")
            if not window:
                return False
            window = ctypes.c_void_p(window)

            msg(window, b"setHidesOnDeactivate:", ctypes.c_bool(False),
                argtypes=(ctypes.c_bool,), restype=None)
            # NSFloatingWindowLevel = 3 (above normal windows).
            msg(window, b"setLevel:", ctypes.c_long(3),
                argtypes=(ctypes.c_long,), restype=None)
            return True
        except Exception:
            return False
