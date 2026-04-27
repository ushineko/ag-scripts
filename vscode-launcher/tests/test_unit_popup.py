"""Unit tests for popup.py (WorkspacePopup widget).

Tests the cycle/activate/cancel state machine and row formatting.
Visibility is asserted as side-effect rather than tested via show()
to keep the tests fast and headless-friendly.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from popup import WorkspacePopup


@dataclass
class _Ws:
    """Minimal stand-in for the real Workspace dataclass — popup only
    reads `label` and `is_running`."""

    label: str
    is_running: bool


@pytest.fixture
def popup(qapp):
    w = WorkspacePopup()
    yield w
    w.close()
    w.deleteLater()


@pytest.fixture
def workspaces_running_first():
    return [
        _Ws(label="aiq-agent", is_running=True),
        _Ws(label="ag-scripts", is_running=True),
        _Ws(label="platform-backend", is_running=False),
        _Ws(label="experiments", is_running=False),
    ]


class TestFormatRow:
    def test_running_has_green_dot(self):
        ws = _Ws(label="x", is_running=True)
        assert WorkspacePopup._format_row(ws) == "● x"

    def test_not_running_has_padding(self):
        ws = _Ws(label="x", is_running=False)
        assert WorkspacePopup._format_row(ws) == "  x"


class TestPopulationAndSelection:
    def test_show_with_workspaces_populates_list(self, popup, workspaces_running_first):
        popup.show_with_workspaces(workspaces_running_first)
        assert popup._list.count() == len(workspaces_running_first)
        # First item selected by default
        assert popup._list.currentRow() == 0
        popup.hide()

    def test_empty_list_shows_placeholder(self, popup):
        popup.show_with_workspaces([])
        assert popup._list.count() == 1
        # Placeholder item is non-selectable, so currentRow stays at 0
        # but activate_current must hide cleanly via the empty-workspaces branch.
        popup.hide()


class TestCycle:
    def test_cycle_next_advances(self, popup, workspaces_running_first):
        popup.show_with_workspaces(workspaces_running_first)
        popup.cycle_next()
        assert popup._list.currentRow() == 1
        popup.cycle_next()
        assert popup._list.currentRow() == 2
        popup.hide()

    def test_cycle_next_wraps(self, popup, workspaces_running_first):
        popup.show_with_workspaces(workspaces_running_first)
        for _ in range(len(workspaces_running_first)):
            popup.cycle_next()
        # Wrapped back to 0
        assert popup._list.currentRow() == 0
        popup.hide()

    def test_cycle_prev_wraps_from_zero(self, popup, workspaces_running_first):
        popup.show_with_workspaces(workspaces_running_first)
        popup.cycle_prev()
        assert popup._list.currentRow() == len(workspaces_running_first) - 1
        popup.hide()

    def test_cycle_no_op_for_single_item(self, popup):
        popup.show_with_workspaces([_Ws(label="solo", is_running=False)])
        popup.cycle_next()
        assert popup._list.currentRow() == 0
        popup.cycle_prev()
        assert popup._list.currentRow() == 0
        popup.hide()

    def test_cycle_no_op_for_empty(self, popup):
        popup.show_with_workspaces([])
        # No exception; selection stays where the placeholder put it.
        popup.cycle_next()
        popup.cycle_prev()
        popup.hide()


class TestActivate:
    def test_activate_emits_with_current_workspace(
        self, popup, workspaces_running_first, qapp
    ):
        captured: list[object] = []
        popup.activate_requested.connect(captured.append)
        popup.show_with_workspaces(workspaces_running_first)
        popup.cycle_next()  # row 1: ag-scripts
        popup.activate_current()
        assert len(captured) == 1
        assert captured[0].label == "ag-scripts"
        # Popup hides itself on activation
        assert popup.isVisible() is False

    def test_activate_on_empty_emits_cancelled(self, popup, qapp):
        cancelled: list[None] = []
        activated: list[object] = []
        popup.cancelled.connect(lambda: cancelled.append(None))
        popup.activate_requested.connect(activated.append)
        popup.show_with_workspaces([])
        popup.activate_current()
        assert cancelled == [None]
        assert activated == []
        assert popup.isVisible() is False


class TestMouseMoveSignal:
    """Mouse motion over the popup or its inner list emits `mouse_moved`,
    which the caller uses to restart its auto-commit timer."""

    def test_mouse_move_event_emits_mouse_moved(
        self, popup, workspaces_running_first, qapp
    ):
        from PyQt6.QtCore import QPointF, Qt
        from PyQt6.QtGui import QMouseEvent

        moved: list[None] = []
        popup.mouse_moved.connect(lambda: moved.append(None))
        popup.show_with_workspaces(workspaces_running_first)
        evt = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(10, 10),
            QPointF(10, 10),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        popup.mouseMoveEvent(evt)
        assert moved == [None]

    def test_list_viewport_mouse_move_emits_mouse_moved(
        self, popup, workspaces_running_first, qapp
    ):
        """Real mouse motion over rows reaches the QListWidget's viewport
        child, not the QListWidget itself. Sending a MouseMove there must
        still emit mouse_moved via the popup's eventFilter."""
        from PyQt6.QtCore import QCoreApplication, QPointF, Qt
        from PyQt6.QtGui import QMouseEvent

        moved: list[None] = []
        popup.mouse_moved.connect(lambda: moved.append(None))
        popup.show_with_workspaces(workspaces_running_first)
        evt = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(20, 20),
            QPointF(20, 20),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QCoreApplication.sendEvent(popup._list.viewport(), evt)
        assert moved == [None]


class TestCancel:
    def test_cancel_emits_and_hides(self, popup, workspaces_running_first, qapp):
        cancelled: list[None] = []
        activated: list[object] = []
        popup.cancelled.connect(lambda: cancelled.append(None))
        popup.activate_requested.connect(activated.append)
        popup.show_with_workspaces(workspaces_running_first)
        popup.cancel()
        assert cancelled == [None]
        assert activated == []
        assert popup.isVisible() is False
