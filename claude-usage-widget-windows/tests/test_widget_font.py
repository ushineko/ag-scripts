"""GUI tests for the floating widget's font-size control.

Runs the Qt widget under the offscreen platform. Skipped if PySide6 isn't
installed (keeps the pure-logic suite runnable without Qt).
"""

import os
from unittest import mock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from src.widget import FloatingWidget, FONT_PRESETS, DEFAULT_FONT_SIZE, _BASE_WIDTH


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def widget(qapp):
    # Patch persistence so tests never touch the real config file.
    with mock.patch("src.config.set_setting"):
        w = FloatingWidget(font_size=DEFAULT_FONT_SIZE)
        yield w
        w.deleteLater()


def test_default_font_size_uses_base_width(widget):
    assert widget._font_size == DEFAULT_FONT_SIZE
    assert widget.width() == _BASE_WIDTH


def test_larger_font_increases_width(widget):
    widget.set_font_size(20)
    assert widget._font_size == 20
    assert widget.width() == round(_BASE_WIDTH * 20 / DEFAULT_FONT_SIZE)


def test_title_renders_two_px_larger(widget):
    widget.set_font_size(13)
    assert "font-size: 15px" in widget._title_lbl.styleSheet()
    assert "font-size: 13px" in widget._five_hour_label.styleSheet()


def test_set_font_size_persists(widget):
    with mock.patch("src.config.set_setting") as set_setting:
        widget.set_font_size(16)
        set_setting.assert_called_once_with("font_size", 16)


def test_presets_include_default(widget):
    assert DEFAULT_FONT_SIZE in FONT_PRESETS
