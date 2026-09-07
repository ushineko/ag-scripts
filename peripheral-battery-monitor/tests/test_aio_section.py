"""Spec 017: AioSection rendering, degradation, and menu wiring.

Runs the real Qt widgets on the offscreen platform. No event loop is started
and every section's timer is stopped immediately after construction, so no test
touches the network.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest.mock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Belt and braces: if anything did fire a request, port 1 refuses instantly.
os.environ.setdefault("OPENLINKHUB_API", "http://127.0.0.1:1/api")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

pytest.importorskip("PyQt6", reason="PyQt6 is only present on the system python")

# test_battery_logic.py replaces the PyQt6 namespace with mocks at import time
# and only restores it in its tearDownModule, so any real-Qt module collected
# after it binds mocks instead of Qt. In the normal `pytest tests/` run this
# file is collected first and the check never fires; it exists so an explicit
# out-of-order invocation skips with a reason rather than failing obscurely.
if isinstance(sys.modules.get("PyQt6"), unittest.mock.MagicMock):
    pytest.skip(
        "PyQt6 is mocked by test_battery_logic; run this file before it or on its own",
        allow_module_level=True,
    )

import aio_section  # noqa: E402
from PyQt6.QtGui import QPixmap  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMenu  # noqa: E402

# peripheral-battery.py is loaded at import time, not inside a fixture: another
# test module in this suite swaps PyQt6 for mocks at collection time, and a
# monitor class built on those mocks cannot parent a real QFrame.
_MONITOR_MODULE = None


def _snapshot(**overrides) -> dict:
    snap = {
        "available": True,
        "error": None,
        "timestamp": 0.0,
        "cpu_temp_c": 98.0,
        "coolant_temp_c": 45.8,
        "coolant_label": "H150i ELITE LCD",
        "pump_rpm": 2399,
        "fans": [
            {"name": "Fan 1", "rpm": 1469},
            {"name": "Fan 2", "rpm": 1462},
            {"name": "Fan 3", "rpm": 1451},
            {"name": "Fan 6", "rpm": 1238},
        ],
    }
    snap.update(overrides)
    return snap


UNAVAILABLE = {
    "available": False,
    "error": "openlinkhub unreachable",
    "timestamp": 0.0,
    "cpu_temp_c": None,
    "coolant_temp_c": None,
    "coolant_label": None,
    "pump_rpm": None,
    "fans": [],
}


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def section(qapp):
    s = aio_section.AioSection({})
    s._timer.stop()
    yield s
    s.deleteLater()


class TestRendering:
    def test_renders_snapshot_values(self, section):
        """AC10."""
        section.render_snapshot(_snapshot())
        assert section.cpu_row.value_lbl.text() == "98.0 °C"
        assert section.coolant_row.value_lbl.text() == "45.8 °C"
        # Mean of 1469/1462/1451/1238 = 1405.
        assert section.fan_row.value_lbl.text() == "1405 rpm ×4  pump 2399"
        assert not section.isHidden()

    def test_missing_coolant_hides_row_and_graph(self, section):
        """AC11: the section survives on the rows it does have."""
        section.render_snapshot(_snapshot(coolant_temp_c=None, pump_rpm=None))
        assert section.coolant_row.is_visible() is False
        assert section.sparkline.isHidden()
        assert section.cpu_row.is_visible() is True
        assert section.fan_row.is_visible() is True
        assert not section.isHidden()

    def test_missing_cpu_temp_hides_only_that_row(self, section):
        section.render_snapshot(_snapshot(cpu_temp_c=None))
        assert section.cpu_row.is_visible() is False
        assert section.coolant_row.is_visible() is True

    def test_fan_row_without_pump(self, section):
        section.render_snapshot(_snapshot(pump_rpm=None, fans=[{"name": "Fan 1", "rpm": 900}]))
        assert section.fan_row.value_lbl.text() == "900 rpm"


class TestCoolantBands:
    """AC12: thresholds come from the observed alarm behaviour of this cooler."""

    @pytest.mark.parametrize(
        "temp,expected",
        [
            (44.0, aio_section.COLOR_OK),
            (49.9, aio_section.COLOR_OK),
            (50.0, aio_section.COLOR_WARN),
            (52.0, aio_section.COLOR_WARN),
            (54.9, aio_section.COLOR_WARN),
            (55.0, aio_section.COLOR_ALARM),
            (57.0, aio_section.COLOR_ALARM),
        ],
    )
    def test_band(self, temp, expected):
        assert aio_section.coolant_color(temp) == expected

    def test_band_applied_to_label_and_graph(self, section):
        section.render_snapshot(_snapshot(coolant_temp_c=57.0))
        assert aio_section.COLOR_ALARM in section.coolant_row.value_lbl.styleSheet()
        assert section.sparkline._color.name() == aio_section.COLOR_ALARM

    def test_unknown_temperature_is_dim(self):
        assert aio_section.coolant_color(None) == aio_section.COLOR_DIM


class TestDegradation:
    def test_hidden_until_data_arrives(self, section):
        """AC13: nothing to show costs nothing, and backs off to a slow poll."""
        section.render_snapshot(UNAVAILABLE)
        assert section.isHidden()
        assert section._timer.interval() == aio_section.IDLE_POLL_INTERVAL_MS
        assert section._header_lbl.text() == "AIO"

    def test_appears_when_data_arrives(self, section):
        section.render_snapshot(UNAVAILABLE)
        section.render_snapshot(_snapshot())
        assert not section.isHidden()
        assert section._timer.interval() == aio_section.POLL_INTERVAL_MS

    def test_keeps_last_values_when_daemon_goes_away(self, section):
        """AC14: a blip must not make the window jump around."""
        section.render_snapshot(_snapshot())
        section.render_snapshot(UNAVAILABLE)
        assert not section.isHidden()
        assert section.coolant_row.value_lbl.text() == "45.8 °C"
        assert section._header_lbl.text() == "AIO  (unavailable)"
        assert aio_section.COLOR_DIM in section.cpu_row.value_lbl.styleSheet()
        assert aio_section.COLOR_DIM in section.coolant_row.value_lbl.styleSheet()

    def test_recovery_clears_the_marker(self, section):
        section.render_snapshot(_snapshot())
        section.render_snapshot(UNAVAILABLE)
        section.render_snapshot(_snapshot(coolant_temp_c=46.0))
        assert section._header_lbl.text() == "AIO"
        assert aio_section.COLOR_OK in section.coolant_row.value_lbl.styleSheet()

    def test_gap_is_not_interpolated_into_the_graph(self, section):
        section.render_snapshot(_snapshot(coolant_temp_c=45.0))
        section.render_snapshot(UNAVAILABLE)
        section.render_snapshot(_snapshot(coolant_temp_c=46.0))
        assert section.sparkline.samples() == [45.0, 46.0]


class TestSparkline:
    def test_retains_at_most_capacity_samples(self, section):
        """AC15."""
        for i in range(aio_section.SPARKLINE_SAMPLES + 20):
            section.sparkline.add_sample(float(i))
        samples = section.sparkline.samples()
        assert len(samples) == aio_section.SPARKLINE_SAMPLES
        # Oldest dropped, newest kept.
        assert samples[0] == 20.0
        assert samples[-1] == float(aio_section.SPARKLINE_SAMPLES + 19)

    def test_paints_without_a_display(self, section, qapp):
        for value in (44.0, 45.0, 46.5, 52.0):
            section.sparkline.add_sample(value)
        section.sparkline.resize(200, 26)
        pixmap = QPixmap(200, 26)
        section.sparkline.render(pixmap)  # would raise if paintEvent is broken

    def test_flat_series_paints(self, section):
        for _ in range(5):
            section.sparkline.add_sample(45.0)
        section.sparkline.resize(200, 26)
        section.sparkline.render(QPixmap(200, 26))

    def test_single_sample_is_a_no_op(self, section):
        section.sparkline.add_sample(45.0)
        section.sparkline.resize(200, 26)
        section.sparkline.render(QPixmap(200, 26))


class TestUserToggle:
    def test_disabled_in_settings_stays_hidden(self, qapp):
        """AC16."""
        s = aio_section.AioSection({"aio_section_enabled": False})
        try:
            assert s.isHidden()
            assert not s._timer.isActive()
            # Even with data, the user's choice wins.
            s.render_snapshot(_snapshot())
            assert s.isHidden()
        finally:
            s._timer.stop()
            s.deleteLater()

    def test_toggle_off_stops_polling(self, section):
        section.render_snapshot(_snapshot())
        section.set_visible(False)
        assert section.isHidden()
        assert not section._timer.isActive()


def _load_monitor_module():
    """Import peripheral-battery.py, whose filename is not a valid module name."""
    global _MONITOR_MODULE
    if _MONITOR_MODULE is None:
        spec = importlib.util.spec_from_file_location(
            "peripheral_battery_aio", os.path.join(ROOT, "peripheral-battery.py")
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _MONITOR_MODULE = module
    return _MONITOR_MODULE


# Bind against the real Qt namespace while it is still real.
_load_monitor_module()


@pytest.fixture(scope="module")
def pb(qapp):
    return _load_monitor_module()


class TestContextMenu:
    """AC17: the menu item reflects and persists `aio_section_enabled`."""

    @pytest.fixture
    def monitor(self, pb, qapp, tmp_path, monkeypatch):
        """A monitor with only the pieces contextMenuEvent touches.

        Calling QWidget's initializer directly skips PeripheralMonitor.__init__
        (battery readers, KWin, timers) while still producing a valid Qt object.
        """
        monkeypatch.setattr(pb, "CONFIG_PATH", str(tmp_path / "config.json"))

        class _MenuOnly(pb.PeripheralMonitor):
            def __init__(self):
                super(pb.PeripheralMonitor, self).__init__()
                self.settings = self.load_settings()
                self.bandwidth_section = pb.BandwidthSection(
                    initial_settings=self.settings,
                    on_settings_changed=lambda partial: None,
                    parent=self,
                )
                self.bandwidth_section._timer.stop()
                self.aio_section = aio_section.AioSection(self.settings, parent=self)
                self.aio_section._timer.stop()

        m = _MenuOnly()
        yield m
        m.deleteLater()

    @staticmethod
    def _find_action(monitor, text):
        for menu in monitor.findChildren(QMenu):
            for action in menu.actions():
                if action.text() == text:
                    return action
        return None

    def test_menu_item_present_and_checked_by_default(self, monitor):
        monitor.contextMenuEvent(None)
        action = self._find_action(monitor, "Show AIO Section")
        assert action is not None
        assert action.isCheckable()
        assert action.isChecked()

    def test_toggling_hides_and_persists(self, monitor, pb):
        monitor.aio_section.render_snapshot(_snapshot())
        monitor.contextMenuEvent(None)
        action = self._find_action(monitor, "Show AIO Section")
        # trigger() on a checkable action toggles it first, then emits
        # triggered(newState) — exactly what a real click does.
        action.trigger()

        assert monitor.settings["aio_section_enabled"] is False
        assert monitor.aio_section.isHidden()
        with open(pb.CONFIG_PATH) as f:
            assert json.load(f)["aio_section_enabled"] is False

    def test_menu_reflects_a_disabled_section(self, monitor):
        monitor.settings["aio_section_enabled"] = False
        monitor.contextMenuEvent(None)
        action = self._find_action(monitor, "Show AIO Section")
        assert not action.isChecked()


class TestNoWrites:
    def test_section_issues_only_get_requests(self):
        """AC18, from the UI side: no write verb reaches the daemon."""
        source = open(os.path.join(ROOT, "aio_section.py")).read()
        assert "self._nam.get(" in source
        for verb in ("_nam.post(", "_nam.put(", "_nam.deleteResource(", "_nam.sendCustomRequest("):
            assert verb not in source
