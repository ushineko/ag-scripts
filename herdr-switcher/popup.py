"""Alt-tab-style popup listing herdr spaces.

Frameless, always-on-top widget; emits `activate_requested(Space)` when the user
picks one. Adapted from vscode-launcher's WorkspacePopup — the Wayland
window-flag and mouse-motion handling are unchanged (see comments); only the row
formatting and the alt-tab initial selection differ.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtGui import QCursor, QGuiApplication, QKeyEvent
from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

# herdr agent_status -> glyph shown at the start of each row.
_STATUS_GLYPH = {
    "working": "●",
    "idle": "○",
    "done": "✓",
    "blocked": "⚠",
    "unknown": "·",
}


class SpacePopup(QWidget):
    activate_requested = pyqtSignal(object)
    cancelled = pyqtSignal()
    mouse_moved = pyqtSignal()

    POPUP_WIDTH = 480
    ROW_HEIGHT = 40
    MAX_VISIBLE_ROWS = 12

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        # See vscode-launcher popup.py: Qt.Popup routes through xdg_popup on
        # Wayland and needs a transient parent a tray daemon doesn't have.
        # Tool + Frameless + StaysOnTop is the working combination; dismissal
        # is handled by focusOut + Esc + hotkey-release.
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        frame = QFrame()
        frame.setObjectName("popupFrame")
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setStyleSheet(
            "QFrame#popupFrame { background: #2b2b2b; border: 1px solid #555; }"
        )
        outer.addWidget(frame)

        inner = QVBoxLayout(frame)
        inner.setContentsMargins(8, 8, 8, 8)
        inner.setSpacing(4)

        self._title = QLabel("Switch herdr space")
        self._title.setStyleSheet(
            "QLabel { color: #aaa; font-size: 11px; padding: 2px 10px 6px 10px; }"
        )
        inner.addWidget(self._title)

        self._list = QListWidget()
        self._list.setStyleSheet(
            """
            QListWidget { background: #2b2b2b; color: #eee; border: none; outline: 0; }
            QListWidget::item { padding: 6px 10px; border-radius: 3px; }
            QListWidget::item:selected { background: #1f6feb; color: white; }
            """
        )
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.setMouseTracking(True)
        self._list.installEventFilter(self)
        self._list.viewport().setMouseTracking(True)
        self._list.viewport().installEventFilter(self)
        self._list.itemClicked.connect(self._on_clicked)
        inner.addWidget(self._list)

        hint = QLabel("Tap hotkey to cycle    Pause or click to commit")
        hint.setStyleSheet(
            "QLabel { color: #777; font-size: 10px; padding: 6px 10px 2px 10px; }"
        )
        inner.addWidget(hint)

        self._spaces: list = []
        self._multi_session = False
        self.resize(self.POPUP_WIDTH, 200)

    def show_with_spaces(self, spaces: list, *, initial_row: int = 0) -> None:
        """Populate (already in display order) and show. `initial_row` selects
        the starting item — pass 1 for alt-tab (pre-select the previous space)."""
        self._spaces = list(spaces)
        self._multi_session = len({getattr(s, "session", "") for s in self._spaces}) > 1
        self._list.clear()
        for sp in self._spaces:
            self._list.addItem(QListWidgetItem(self._format_row(sp)))

        if not self._spaces:
            placeholder = QListWidgetItem("(no spaces)")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._list.addItem(placeholder)
        else:
            self._list.setCurrentRow(min(initial_row, len(self._spaces) - 1))

        rows = max(1, min(len(self._spaces) or 1, self.MAX_VISIBLE_ROWS))
        self.resize(self.POPUP_WIDTH, 80 + rows * self.ROW_HEIGHT)
        self._center_on_cursor_screen()
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def _format_row(self, space) -> str:
        glyph = _STATUS_GLYPH.get(getattr(space, "agent_status", "unknown"), "·")
        label = getattr(space, "label", "?")
        if self._multi_session:
            return f"{glyph}  {label}    [{getattr(space, 'session', '')}]"
        return f"{glyph}  {label}"

    def _center_on_cursor_screen(self) -> None:
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        geom = screen.geometry()
        self.move(
            geom.x() + (geom.width() - self.width()) // 2,
            geom.y() + (geom.height() - self.height()) // 2,
        )

    def cycle_next(self) -> None:
        count = self._list.count()
        if count > 1:
            self._list.setCurrentRow((self._list.currentRow() + 1) % count)

    def cycle_prev(self) -> None:
        count = self._list.count()
        if count > 1:
            self._list.setCurrentRow((self._list.currentRow() - 1) % count)

    def activate_current(self) -> None:
        idx = self._list.currentRow()
        if 0 <= idx < len(self._spaces):
            sp = self._spaces[idx]
            self.hide()
            self.activate_requested.emit(sp)
        else:
            self.hide()
            self.cancelled.emit()

    def cancel(self) -> None:
        self.hide()
        self.cancelled.emit()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Tab, Qt.Key.Key_Down, Qt.Key.Key_Right):
            self.cycle_next(); event.accept(); return
        if key in (Qt.Key.Key_Backtab, Qt.Key.Key_Up, Qt.Key.Key_Left):
            self.cycle_prev(); event.accept(); return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.activate_current(); event.accept(); return
        if key == Qt.Key.Key_Escape:
            self.cancel(); event.accept(); return
        super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        if self.isVisible():
            self.cancel()

    def mouseMoveEvent(self, event) -> None:
        self.mouse_moved.emit()
        super().mouseMoveEvent(event)

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.MouseMove and obj in (
            self._list, self._list.viewport()
        ):
            self.mouse_moved.emit()
        return super().eventFilter(obj, event)

    def _on_clicked(self, item: QListWidgetItem) -> None:
        idx = self._list.row(item)
        if 0 <= idx < len(self._spaces):
            self._list.setCurrentRow(idx)
            self.activate_current()
