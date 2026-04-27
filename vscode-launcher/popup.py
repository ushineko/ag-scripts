"""Alt-Tab-style quick-launcher popup for vscode-launcher.

Frameless, always-on-top widget that lists workspaces and emits an
`activate_requested(Workspace)` signal when the user picks one. The
launcher's `MainWindow` owns the popup, populates it on global-hotkey
press, and triggers activation on global-hotkey release.

Pure UI: this module knows about `Workspace` objects but has no opinion
on what activation does (focus running window, launch new window). The
caller wires the signal to its own activation logic.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCursor, QGuiApplication, QKeyEvent
from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)


class WorkspacePopup(QWidget):
    """Frameless, centered popup listing workspaces.

    Signals
    -------
    activate_requested(object)
        Emitted with a `Workspace` instance when the user picks an
        item (release / Enter / mouse click).
    cancelled()
        Emitted when the user dismisses without activating (Esc or
        click outside).
    """

    activate_requested = pyqtSignal(object)
    cancelled = pyqtSignal()

    POPUP_WIDTH = 480
    ROW_HEIGHT = 40
    MAX_VISIBLE_ROWS = 12

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        # NOTE on flags: Qt.WindowType.Popup looks tempting (auto-dismiss on
        # click outside, modal-like) but on Wayland it routes through the
        # xdg_popup protocol, which requires a transientParent that has
        # already received input. A tray-resident daemon has no such parent,
        # and Plasma logs "Failed to create grabbing popup" then refuses to
        # map the surface. Tool + FramelessWindowHint + WindowStaysOnTopHint
        # gives us a frameless, no-taskbar, best-effort always-on-top widget.
        # Dismissal is covered by focusOutEvent + Esc + hotkey-release.
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setStyleSheet(
            "QFrame { background: #2b2b2b; border: 1px solid #555; }"
        )
        outer.addWidget(frame)

        inner = QVBoxLayout(frame)
        inner.setContentsMargins(8, 8, 8, 8)
        inner.setSpacing(4)

        self._title = QLabel("Switch workspace")
        self._title.setStyleSheet(
            "QLabel { color: #aaa; font-size: 11px; padding: 0 4px 4px 4px; }"
        )
        inner.addWidget(self._title)

        self._list = QListWidget()
        self._list.setStyleSheet(
            """
            QListWidget {
                background: #2b2b2b;
                color: #eee;
                border: none;
                outline: 0;
            }
            QListWidget::item {
                padding: 6px 10px;
                border-radius: 3px;
            }
            QListWidget::item:selected {
                background: #1f6feb;
                color: white;
            }
            """
        )
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.itemClicked.connect(self._on_clicked)
        inner.addWidget(self._list)

        # Dim hint at the bottom describing the keys.
        hint = QLabel(
            "Tab / ↑↓ — cycle    Release or Enter — activate    Esc — cancel"
        )
        hint.setStyleSheet(
            "QLabel { color: #777; font-size: 10px; padding: 4px 4px 0 4px; }"
        )
        inner.addWidget(hint)

        self._workspaces: list = []
        self.resize(self.POPUP_WIDTH, 200)

    # ------------------------------------------------------------------
    # Population + show
    # ------------------------------------------------------------------

    def show_with_workspaces(self, workspaces: list) -> None:
        """Populate the popup with `workspaces` (already in the order the
        caller wants displayed — typically running-first), select the
        first item, and show centered on the active screen."""
        self._workspaces = list(workspaces)
        self._list.clear()
        for ws in self._workspaces:
            item = QListWidgetItem(self._format_row(ws))
            self._list.addItem(item)

        if not self._workspaces:
            placeholder = QListWidgetItem("(no workspaces)")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._list.addItem(placeholder)
        else:
            self._list.setCurrentRow(0)

        # Resize to fit content up to the cap.
        rows = max(1, min(len(self._workspaces) or 1, self.MAX_VISIBLE_ROWS))
        height = 80 + rows * self.ROW_HEIGHT  # title + list + hint padding
        self.resize(self.POPUP_WIDTH, height)

        self._center_on_cursor_screen()
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    @staticmethod
    def _format_row(workspace) -> str:
        running_marker = "● " if getattr(workspace, "is_running", False) else "  "
        label = getattr(workspace, "label", "?")
        return f"{running_marker}{label}"

    def _center_on_cursor_screen(self) -> None:
        screen = QGuiApplication.screenAt(QCursor.pos())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geom = screen.geometry()
        x = geom.x() + (geom.width() - self.width()) // 2
        y = geom.y() + (geom.height() - self.height()) // 2
        self.move(x, y)

    # ------------------------------------------------------------------
    # Cycle / activate / cancel
    # ------------------------------------------------------------------

    def cycle_next(self) -> None:
        count = self._list.count()
        if count <= 1:
            return
        row = (self._list.currentRow() + 1) % count
        self._list.setCurrentRow(row)

    def cycle_prev(self) -> None:
        count = self._list.count()
        if count <= 1:
            return
        row = (self._list.currentRow() - 1) % count
        self._list.setCurrentRow(row)

    def activate_current(self) -> None:
        """Emit `activate_requested` for the currently-selected workspace
        and hide. If the list is empty, just hide."""
        idx = self._list.currentRow()
        if 0 <= idx < len(self._workspaces):
            ws = self._workspaces[idx]
            self.hide()
            self.activate_requested.emit(ws)
        else:
            self.hide()
            self.cancelled.emit()

    def cancel(self) -> None:
        self.hide()
        self.cancelled.emit()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Tab, Qt.Key.Key_Down, Qt.Key.Key_Right):
            self.cycle_next()
            event.accept()
            return
        if key in (Qt.Key.Key_Backtab, Qt.Key.Key_Up, Qt.Key.Key_Left):
            self.cycle_prev()
            event.accept()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.activate_current()
            event.accept()
            return
        if key == Qt.Key.Key_Escape:
            self.cancel()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:
        # Click-outside dismissal. Wayland sometimes doesn't deliver this
        # reliably for frameless popup windows; Esc and hotkey-release
        # are the dependable dismissal paths.
        super().focusOutEvent(event)
        if self.isVisible():
            self.cancel()

    def _on_clicked(self, item: QListWidgetItem) -> None:
        # Resolve back to the workspace and activate.
        idx = self._list.row(item)
        if 0 <= idx < len(self._workspaces):
            self._list.setCurrentRow(idx)
            self.activate_current()
