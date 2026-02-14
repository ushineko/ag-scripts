"""Tests for the Blue Screen of Delight easter egg."""
import sys

from PyQt6.QtWidgets import QApplication, QWidget, QLabel
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette

# QApplication must exist before any QWidget
app = QApplication.instance() or QApplication(sys.argv)

from fake_screensaver import BlueScreenOfDelight


class TestBlueScreenOfDelight:
    """Test the BSOD overlay widget."""

    def test_starts_hidden(self):
        parent = QWidget()
        bsod = BlueScreenOfDelight(parent)
        assert not bsod.isVisible()

    def test_background_color_is_windows_blue(self):
        parent = QWidget()
        bsod = BlueScreenOfDelight(parent)
        bg = bsod.palette().color(QPalette.ColorRole.Window)
        assert bg == QColor("#0078d7")

    def test_has_smiley_face_label(self):
        parent = QWidget()
        bsod = BlueScreenOfDelight(parent)
        labels = bsod.findChildren(QLabel)
        texts = [label.text() for label in labels]
        assert ":)" in texts

    def test_has_stop_code(self):
        parent = QWidget()
        bsod = BlueScreenOfDelight(parent)
        labels = bsod.findChildren(QLabel)
        texts = [label.text() for label in labels]
        assert any("CRITICAL_PROCESS_HATES_YOU" in t for t in texts)

    def test_has_error_message(self):
        parent = QWidget()
        bsod = BlueScreenOfDelight(parent)
        labels = bsod.findChildren(QLabel)
        texts = [label.text() for label in labels]
        assert any("choir invisible" in t for t in texts)

    def test_cursor_is_hidden(self):
        parent = QWidget()
        bsod = BlueScreenOfDelight(parent)
        assert bsod.cursor().shape() == Qt.CursorShape.BlankCursor
