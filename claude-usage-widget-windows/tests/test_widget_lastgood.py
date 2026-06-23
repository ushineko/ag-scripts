"""Last-known-good rendering for the floating widget.

On a transient error the widget keeps showing the last successful reading,
marked stale, instead of blanking — only with no cached reading does it show
the error state. Runs under the offscreen Qt platform.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from src.widget import FloatingWidget

GOOD = {
    "five_hour": {"utilization": 12.0, "resets_at": ""},
    "seven_day": {"utilization": 5.0},
}


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def widget(qapp):
    w = FloatingWidget()
    yield w
    w.deleteLater()


def test_success_caches_and_renders(widget):
    widget.update_usage(GOOD)
    assert widget._last_good == GOOD
    assert widget._showing_cached is False
    assert "12%" in widget._five_hour_label.text()
    assert widget._status_label.isHidden()


def test_transient_error_keeps_cached_reading(widget):
    widget.update_usage(GOOD)
    widget.update_usage({"error": "rate_limited"})
    assert widget._showing_cached is True
    # last-known value is still shown, not blanked to "--"
    assert "12%" in widget._five_hour_label.text()
    assert not widget._status_label.isHidden()
    assert "rate limited" in widget._status_label.text()


def test_error_without_cache_shows_error_state(widget):
    widget.update_usage({"error": "api_error"})
    assert widget._showing_cached is False
    assert widget._five_hour_label.text() == "5h: --"
    assert not widget._status_label.isHidden()


def test_none_without_cache_shows_not_logged_in(widget):
    widget.update_usage(None)
    assert "logged in" in widget._status_label.text().lower()


def test_none_after_success_keeps_cached(widget):
    widget.update_usage(GOOD)
    widget.update_usage(None)
    assert widget._showing_cached is True
    assert "12%" in widget._five_hour_label.text()
