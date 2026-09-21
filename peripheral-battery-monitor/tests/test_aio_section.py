"""Specs 017 and 018: AioSection rendering, degradation, traces, and menu wiring.

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

import aio_reader  # noqa: E402
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


@pytest.fixture(autouse=True)
def _no_live_daemon(monkeypatch):
    """Keep every test in this module off the real OpenLinkHub.

    `aio_reader.DEFAULT_BASE_URL` is bound at its import, which happens before
    this module sets OPENLINKHUB_API, so without this a section whose timer or
    singleShot fires while some other test spins the event loop would poll the
    user's actual daemon. Port 1 refuses instantly.
    """
    monkeypatch.setattr(aio_reader, "DEFAULT_BASE_URL", "http://127.0.0.1:1/api")


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

    def test_missing_coolant_hides_its_row(self, section):
        """017 AC11, as amended by 018 AC6: the coolant row goes, but the graph
        stays as long as the CPU trace has data."""
        section.render_snapshot(_snapshot(coolant_temp_c=None, pump_rpm=None))
        assert section.coolant_row.is_visible() is False
        assert section.sparkline.samples(aio_section.SERIES_COOLANT) == []
        assert not section.sparkline.isHidden()
        assert section.cpu_row.is_visible() is True
        assert section.fan_row.is_visible() is True
        assert not section.isHidden()

    def test_graph_hidden_when_neither_trace_has_data(self, section):
        """018 AC6: no coolant and no CPU means nothing to plot."""
        section.render_snapshot(_snapshot(coolant_temp_c=None, cpu_temp_c=None))
        assert section.sparkline.isHidden()
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
        coolant = section.sparkline._series[aio_section.SERIES_COOLANT]
        assert coolant.color.name() == aio_section.COLOR_ALARM

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
        assert section.sparkline.samples(aio_section.SERIES_COOLANT) == [45.0, 46.0]


class TestSparkline:
    def test_retains_at_most_capacity_samples(self, section):
        """017 AC15."""
        for i in range(aio_section.SPARKLINE_SAMPLES + 20):
            section.sparkline.add_sample(aio_section.SERIES_COOLANT, float(i))
        samples = section.sparkline.samples(aio_section.SERIES_COOLANT)
        assert len(samples) == aio_section.SPARKLINE_SAMPLES
        # Oldest dropped, newest kept.
        assert samples[0] == 20.0
        assert samples[-1] == float(aio_section.SPARKLINE_SAMPLES + 19)

    def test_paints_without_a_display(self, section, qapp):
        for value in (44.0, 45.0, 46.5, 52.0):
            section.sparkline.add_sample(aio_section.SERIES_COOLANT, value)
        for value in (70.0, 95.0, 62.0, 88.0):
            section.sparkline.add_sample(aio_section.SERIES_CPU, value)
        section.sparkline.resize(200, 26)
        pixmap = QPixmap(200, 26)
        section.sparkline.render(pixmap)  # would raise if paintEvent is broken

    def test_flat_series_paints(self, section):
        for _ in range(5):
            section.sparkline.add_sample(aio_section.SERIES_COOLANT, 45.0)
        section.sparkline.resize(200, 26)
        section.sparkline.render(QPixmap(200, 26))

    def test_single_sample_is_a_no_op(self, section):
        section.sparkline.add_sample(aio_section.SERIES_COOLANT, 45.0)
        section.sparkline.resize(200, 26)
        section.sparkline.render(QPixmap(200, 26))


class TestCpuTrace:
    """Spec 018: the CPU trend overlay."""

    def test_plots_a_trailing_mean_not_the_raw_value(self, section):
        """018 AC1: a 100 °C boost spike must not become a 100 °C spike on the
        graph while the window still holds cooler samples."""
        for cpu in (60.0, 60.0, 60.0, 100.0):
            section.render_snapshot(_snapshot(cpu_temp_c=cpu))
        plotted = section.sparkline.samples(aio_section.SERIES_CPU)
        assert plotted == [60.0, 60.0, 60.0, 70.0]
        # The row still shows the real instantaneous reading.
        assert section.cpu_row.value_lbl.text() == "100.0 °C"

    def test_partial_window_averages_what_it_has(self, section):
        """018 AC2: the trace starts on the first sample, not after a minute."""
        section.render_snapshot(_snapshot(cpu_temp_c=80.0))
        assert section.sparkline.samples(aio_section.SERIES_CPU) == [80.0]

    def test_window_slides(self, section):
        """018 AC3: readings older than the window stop counting."""
        window = aio_section.CPU_AVERAGE_WINDOW
        for _ in range(window):
            section.render_snapshot(_snapshot(cpu_temp_c=100.0))
        for _ in range(window):
            section.render_snapshot(_snapshot(cpu_temp_c=50.0))
        plotted = section.sparkline.samples(aio_section.SERIES_CPU)
        assert plotted[window - 1] == 100.0
        assert plotted[-1] == 50.0

    def test_missing_cpu_adds_no_sample(self, section):
        section.render_snapshot(_snapshot(cpu_temp_c=None))
        assert section.sparkline.samples(aio_section.SERIES_CPU) == []

    def test_row_colour_is_the_trace_colour(self, section):
        """018 AC4: the row value is the legend."""
        section.render_snapshot(_snapshot())
        assert aio_section.COLOR_CPU in section.cpu_row.value_lbl.styleSheet()

    def test_traces_scale_independently(self, section):
        """018 AC5: a 35 °C CPU swing must not flatten a 1 °C coolant swing.

        Both series are normalised to their own bounds, so each spans the full
        box height regardless of the other's range.
        """
        cpu = section.sparkline._series[aio_section.SERIES_CPU]
        coolant = section.sparkline._series[aio_section.SERIES_COOLANT]
        cpu.samples[:] = [60.0, 95.0]
        coolant.samples[:] = [45.0, 46.0]

        cpu_lo, cpu_span = cpu.bounds()
        coolant_lo, coolant_span = coolant.bounds()
        assert (cpu_lo, cpu_span) == (60.0, 35.0)
        # Under the 5 °C floor, centred on the pair.
        assert (coolant_lo, coolant_span) == (43.0, 5.0)

    def test_both_traces_paint(self, section):
        section.sparkline.resize(200, 26)
        for i in range(5):
            section.sparkline.add_sample(aio_section.SERIES_CPU, 60.0 + i * 8)
            section.sparkline.add_sample(aio_section.SERIES_COOLANT, 45.0 + i * 0.2)
        section.sparkline.render(QPixmap(200, 26))

    def test_dimmed_and_restored_with_the_daemon(self, section):
        """018 AC7: the CPU trace follows the section's degraded state."""
        section.render_snapshot(_snapshot())
        section.render_snapshot(UNAVAILABLE)
        cpu = section.sparkline._series[aio_section.SERIES_CPU]
        assert cpu.color.name() == aio_section.COLOR_DIM
        section.render_snapshot(_snapshot())
        assert cpu.color.name() == aio_section.COLOR_CPU

    def test_unknown_series_key_is_a_no_op(self, section):
        section.sparkline.add_sample("nope", 1.0)
        section.sparkline.set_color("nope", "#ffffff")
        assert section.sparkline.samples("nope") == []










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


class TestSettle:
    """The poll's own callback, end to end.

    It is here because the removal broke it and the suite did not notice: a
    call to a method that no longer existed sat in `_settle`, every test
    passed, and the widget logged `liquidctl_callback_failed` twice a poll
    until somebody ran it. A unit test that never reaches the callback proves
    nothing about the callback.
    """

    def test_a_completed_poll_renders_and_alerts(self, section):
        section._inflight = {"cpu": None, "gpu": None, "devices": None,
                             "liquid": None, "pending": 1}
        section._settle("cpu", None)

        assert section._inflight is None
        assert section._last_snapshot != {}

    def test_a_completed_poll_writes_nothing(self, section, monkeypatch):
        """Whatever else it does, it must not reach for a write path."""
        posted = []
        monkeypatch.setattr(section._nam, "post",
                            lambda *a, **k: posted.append(a), raising=False)

        section._inflight = {"cpu": None, "gpu": None, "devices": None,
                             "liquid": None, "pending": 1}
        section._settle("cpu", None)

        assert posted == []


class TestNoWrites:
    """039, superseding 019 AC12 and 017 AC18.

    017 forbade every write, which was about fan and pump duty: Commander ST
    fw 2.x silently discards those, so a duty control would report success and
    change nothing. 019 narrowed the guard to speed when RGB writes became a
    feature here.

    They are not a feature here any more. Every write to this cooler and to
    every lit device belongs to hotaru, so the guard widens again -- and this
    time it covers the RGB path too, because "two processes writing one hidraw
    node" is the invariant the whole cutover exists to protect.
    """

    SPEED_ENDPOINTS = (
        "/api/speed",
        "/api/psu/speed",
        "/api/temperatures/new",
        "/api/temperatures/update",
        "/api/temperatures/updateGraph",
        "setSpeed",
    )

    @pytest.mark.parametrize("module", ["aio_reader.py", "aio_section.py"])
    def test_no_speed_write_path(self, module):
        source = open(os.path.join(ROOT, module)).read()
        for endpoint in self.SPEED_ENDPOINTS:
            assert endpoint not in source

    def test_no_rgb_write_path(self):
        """The section reads. It does not post, and it does not shell out.

        Asserted against the source rather than against behaviour on purpose:
        what matters is that no write path exists to be reached by accident,
        which is a property of the file rather than of any one call.
        """
        source = open(os.path.join(ROOT, "aio_section.py")).read()
        assert "self._nam.post(" not in source
        assert "aio_liquid" not in source
        assert "rgb_openrgb" not in source

    @pytest.mark.parametrize("module", [
        "aio_liquid.py", "aio_dashboard.py", "aio_scenes.py", "aio_color.py",
        "rgb_openrgb.py", "scene_service.py", "scene_shortcuts.py",
    ])
    def test_the_write_modules_are_gone(self, module):
        """They moved to hotaru. A file that comes back brings the invariant
        problem back with it, which is worth one assertion."""
        assert not os.path.exists(os.path.join(ROOT, module))

    def test_the_shortcut_installer_is_gone(self):
        """The eighteen numpad keys are hotaru's. While this file existed, the
        monitor reinstalled its KWin script on every start and re-registered
        its claim on those sequences."""
        source = open(os.path.join(ROOT, "peripheral-battery.py")).read()
        assert "scene_shortcuts" not in source
        assert "scene_service" not in source






