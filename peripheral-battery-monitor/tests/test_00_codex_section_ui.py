"""Real-Qt checks for Codex section style and geometry wiring."""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

pytest.importorskip("PyQt6", reason="PyQt6 is only present on the system python")

from PyQt6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

from codex_section import CodexSection  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_section_inherits_opaque_frame_and_scaled_geometry(app):
    parent = QWidget()
    parent.setStyleSheet("""
        QFrame#ClaudeSection, QFrame#CodexSection {
            background-color: rgba(35, 35, 35, 255);
            border: 1px solid rgba(255, 255, 255, 15);
            border-radius: 8px;
        }
    """)
    section = CodexSection(parent)
    section.apply_layout_metrics({
        "claude_margin_h": 15,
        "claude_margin_top": 8,
        "claude_margin_bottom": 10,
        "claude_header_spacing": 8,
    })
    section.resize(360, 110)
    section.show()
    app.processEvents()

    assert section.section_layout.contentsMargins().left() == 15
    assert section.section_layout.contentsMargins().top() == 8
    assert section.header_layout.spacing() == 8
    assert section.findChild(QWidget, "CodexTitle") is not None
    assert section.findChild(QWidget, "CodexRefreshBtn") is not None

    image = QImage(section.size(), QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    section.render(painter)
    painter.end()

    center = image.pixelColor(section.width() // 2, section.height() // 2)
    assert center.alpha() == 255
    assert (center.red(), center.green(), center.blue()) == (35, 35, 35)
