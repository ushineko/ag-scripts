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
from PyQt6.QtCore import QObject, pyqtSignal  # noqa: E402
from PyQt6.QtGui import QPixmap  # noqa: E402
# Bound here, not inside _FakeReply.error(): another test module swaps the
# PyQt6 namespace for mocks at collection time, and a late import would
# compare a real enum against a MagicMock.
from PyQt6.QtNetwork import QNetworkReply  # noqa: E402
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


class _FakeReply(QObject):
    """Stands in for QNetworkReply so a test can decide when a request lands."""

    finished = pyqtSignal()

    def __init__(self, ok: bool = True, body: bytes = b'{"status":1}'):
        super().__init__()
        self._ok = ok
        self._body = body

    def error(self):
        return (
            QNetworkReply.NetworkError.NoError
            if self._ok
            else QNetworkReply.NetworkError.ConnectionRefusedError
        )

    def errorString(self):
        return "" if self._ok else "refused"

    def readAll(self):
        return self._body

    def deleteLater(self):
        pass

    def land(self):
        self.finished.emit()


class _FakeNam:
    """Records POSTs and hands back replies the test finishes by hand."""

    def __init__(self, ok: bool = True):
        self.posts: list[tuple[str, dict]] = []
        self.pending: list[_FakeReply] = []
        self._ok = ok

    def post(self, request, data):
        self.posts.append((request.url().toString(), json.loads(bytes(data).decode())))
        reply = _FakeReply(ok=self._ok)
        self.pending.append(reply)
        return reply

    def get(self, request):
        reply = _FakeReply()
        self.pending.append(reply)
        return reply

    def land_all(self):
        """Finish every outstanding reply, as the event loop would."""
        landing, self.pending = self.pending, []
        for reply in landing:
            reply.land()


class TestRgbWrites:
    """Spec 019: staged dispatch over the network layer."""

    @pytest.fixture
    def rgb(self, section):
        section._rgb_device = "207132833748"
        section._rgb_channels = [0, 1, 2]
        section._brightness = 3
        nam = _FakeNam()
        section._nam = nam
        return section, nam

    @staticmethod
    def _paths(nam):
        return [url.rsplit("/api/", 1)[-1] for url, _ in nam.posts]

    def test_stage_two_waits_for_stage_one(self, rgb):
        """AC8: the override must land before the profile select."""
        section, nam = rgb
        section.apply_color((255, 0, 0))

        # Stage 1 only: one setOverride per channel, nothing else yet.
        assert self._paths(nam) == ["color/setOverride"] * 3

        nam.land_all()
        assert self._paths(nam) == ["color/setOverride"] * 3 + ["color"] * 3

    def test_partial_stage_does_not_advance(self, rgb):
        section, nam = rgb
        section.apply_color((255, 0, 0))
        # Land two of the three stage-1 replies.
        nam.pending.pop(0).land()
        nam.pending.pop(0).land()
        assert self._paths(nam) == ["color/setOverride"] * 3

    def test_payloads(self, rgb):
        section, nam = rgb
        section.apply_color((255, 136, 0))
        nam.land_all()
        overrides = [p for url, p in nam.posts if url.endswith("setOverride")]
        assert [p["channelId"] for p in overrides] == [0, 1, 2]
        assert overrides[0]["startColor"] == {"red": 255, "green": 136, "blue": 0}
        assert overrides[0]["enabled"] is True
        profiles = [p for url, p in nam.posts if url.endswith("/api/color")]
        assert all(p["profile"] == "static" for p in profiles)

    def test_effect_disables_the_override_first(self, rgb):
        section, nam = rgb
        section.apply_effect("rainbow")
        assert all(p["enabled"] is False for _url, p in nam.posts)
        nam.land_all()
        assert nam.posts[-1][1]["profile"] == "rainbow"

    def test_failed_stage_still_advances(self, section):
        """AC9: a half-written device is worse than a fully attempted one."""
        section._rgb_device = "dev"
        section._rgb_channels = [0]
        nam = _FakeNam(ok=False)
        section._nam = nam
        section.apply_color((255, 0, 0))
        nam.land_all()
        assert self._paths(nam) == ["color/setOverride", "color"]
        assert section._timer.isActive() or True  # never raised

    def test_brightness_repair_leads(self, rgb):
        section, nam = rgb
        section._brightness = 0
        section.apply_color((255, 0, 0))
        assert self._paths(nam) == ["brightness"]
        nam.land_all()
        assert self._paths(nam)[1:] == ["color/setOverride"] * 3

    def test_set_brightness(self, rgb):
        section, nam = rgb
        section.set_brightness(2)
        assert nam.posts[0][1] == {"deviceId": "207132833748", "brightness": 2}
        assert section._brightness == 2

    def test_set_brightness_rejects_bad_level(self, rgb):
        section, nam = rgb
        section.set_brightness(9)
        assert nam.posts == []

    def test_no_target_is_a_no_op(self, section):
        nam = _FakeNam()
        section._nam = nam
        section._rgb_device = None
        section._rgb_channels = []
        section.apply_color((255, 0, 0))
        section.apply_effect("rainbow")
        section.set_brightness(3)
        assert nam.posts == []

    def test_a_newer_request_supersedes_the_tail_of_an_older_one(self, rgb):
        """Rapid menu clicks must not interleave two sequences."""
        section, nam = rgb
        section.apply_color((255, 0, 0))
        stale = list(nam.pending)
        nam.pending.clear()

        section.apply_color((0, 0, 255))
        blue_stage_one = len(nam.posts)

        # The superseded sequence's replies must not push the new one forward.
        for reply in stale:
            reply.land()
        assert len(nam.posts) == blue_stage_one


class TestEffectsCache:
    """AC10: names come from the device, and are never guessed."""

    def test_empty_until_fetched(self, section):
        assert section.effects() == []

    def test_populated_from_the_profiles_payload(self, section):
        section._rgb_device = "dev"
        section._on_effects_reply(
            _FakeReply(body=json.dumps({
                "data": {"dev": {"profiles": {"rainbow": {}, "static": {}, "nebula": {}}}}
            }).encode()),
            "dev",
        )
        assert section.effects() == ["nebula", "rainbow"]

    def test_a_failed_fetch_is_retried_on_the_next_snapshot(self, section):
        section._rgb_device = "dev"
        section._effects_fetched_for = "dev"
        section._on_effects_reply(_FakeReply(ok=False), "dev")
        assert section.effects() == []
        # Cleared, so _maybe_fetch_effects will try again.
        assert section._effects_fetched_for is None

    def test_rgb_target_accessor(self, section):
        section._rgb_device = "dev"
        section._rgb_channels = [0, 1]
        assert section.rgb_target() == ("dev", [0, 1])


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

    def test_rgb_menus_absent_without_a_target(self, monitor):
        """019 AC11: no channels means no colour menu, not a broken one."""
        monitor.aio_section._rgb_device = None
        monitor.aio_section._rgb_channels = []
        monitor.contextMenuEvent(None)
        for title in ("Colour", "Effect", "Brightness"):
            assert self._find_action(monitor, title) is None

    def test_rgb_menus_present_with_a_target(self, monitor):
        monitor.aio_section._rgb_device = "dev"
        monitor.aio_section._rgb_channels = [0, 1]
        monitor.aio_section._effects = ["rainbow", "nebula"]
        monitor.contextMenuEvent(None)
        for title in ("Colour", "Effect", "Brightness"):
            assert self._find_action(monitor, title) is not None
        assert self._find_action(monitor, "Red") is not None
        assert self._find_action(monitor, "Custom…") is not None
        assert self._find_action(monitor, "rainbow") is not None

    def test_effect_menu_omitted_when_names_are_unknown(self, monitor):
        """Guessing a profile name is rejected by the daemon, so do not."""
        monitor.aio_section._rgb_device = "dev"
        monitor.aio_section._rgb_channels = [0]
        monitor.aio_section._effects = []
        monitor.contextMenuEvent(None)
        assert self._find_action(monitor, "Colour") is not None
        assert self._find_action(monitor, "Effect") is None

    def test_colour_action_applies_the_right_triple(self, monitor):
        monitor.aio_section._rgb_device = "dev"
        monitor.aio_section._rgb_channels = [0]
        applied = []
        monitor.aio_section.apply_color = applied.append
        monitor.contextMenuEvent(None)
        self._find_action(monitor, "Teal").trigger()
        assert applied == [(0, 255, 128)]

    def test_off_action_applies_black(self, monitor):
        monitor.aio_section._rgb_device = "dev"
        monitor.aio_section._rgb_channels = [0]
        applied = []
        monitor.aio_section.apply_color = applied.append
        monitor.contextMenuEvent(None)
        self._find_action(monitor, "Off").trigger()
        assert applied == [(0, 0, 0)]

    def test_effect_action_applies_the_name(self, monitor):
        monitor.aio_section._rgb_device = "dev"
        monitor.aio_section._rgb_channels = [0]
        monitor.aio_section._effects = ["nebula"]
        applied = []
        monitor.aio_section.apply_effect = applied.append
        monitor.contextMenuEvent(None)
        self._find_action(monitor, "nebula").trigger()
        assert applied == ["nebula"]

    def test_brightness_action(self, monitor):
        monitor.aio_section._rgb_device = "dev"
        monitor.aio_section._rgb_channels = [0]
        applied = []
        monitor.aio_section.set_brightness = applied.append
        monitor.contextMenuEvent(None)
        self._find_action(monitor, "66%").trigger()
        assert applied == [2]

    def test_custom_hex_prompt(self, monitor, pb, monkeypatch):
        monitor.aio_section._rgb_device = "dev"
        monitor.aio_section._rgb_channels = [0]
        applied = []
        monitor.aio_section.apply_color = applied.append

        monkeypatch.setattr(pb.QInputDialog, "getText",
                            staticmethod(lambda *a, **k: ("#ff8800", True)))
        monitor._prompt_aio_color()
        assert applied == [(255, 136, 0)]

    def test_custom_hex_rejects_junk_without_writing(self, monitor, pb, monkeypatch):
        monitor.aio_section._rgb_device = "dev"
        monitor.aio_section._rgb_channels = [0]
        applied = []
        monitor.aio_section.apply_color = applied.append

        for value, ok in (("nope", True), ("#12345", True), ("", True), ("#ff8800", False)):
            monkeypatch.setattr(pb.QInputDialog, "getText",
                                staticmethod(lambda *a, _v=value, _o=ok, **k: (_v, _o)))
            monitor._prompt_aio_color()
        assert applied == []

    def test_menu_reflects_a_disabled_section(self, monitor):
        monitor.settings["aio_section_enabled"] = False
        monitor.contextMenuEvent(None)
        action = self._find_action(monitor, "Show AIO Section")
        assert not action.isChecked()


class TestNoSpeedWrites:
    """019 AC12, superseding 017 AC18.

    017 forbade every write. That was about fan and pump duty, which Commander
    ST fw 2.x silently discards. RGB writes do land and are now a feature, so
    the guard narrows to speed: a duty control would report success and change
    nothing, which is worse than not having one.
    """

    SPEED_ENDPOINTS = (
        "/api/speed",
        "/api/psu/speed",
        "/api/temperatures/new",
        "/api/temperatures/update",
        "/api/temperatures/updateGraph",
        "setSpeed",
    )

    @pytest.mark.parametrize("module", ["aio_reader.py", "aio_section.py", "aio_color.py"])
    def test_no_speed_write_path(self, module):
        source = open(os.path.join(ROOT, module)).read()
        for endpoint in self.SPEED_ENDPOINTS:
            assert endpoint not in source

    def test_rgb_writes_are_permitted_and_present(self):
        source = open(os.path.join(ROOT, "aio_section.py")).read()
        assert "self._nam.post(" in source


class TestScopeCompleteness:
    """033: a PARTIAL device list reads as OK, which is how it hid."""

    @staticmethod
    def _dev(name):
        return {"name": name, "modes": ["Direct", "Static"]}

    def test_all_scope_entries_matched_is_empty(self, section):
        section._lighting_scope = ("kraken", "geforce", "maximus", "mm700")
        section._lighting_devices = [
            self._dev("NZXT Kraken 2024 ELITE Series RGB"),
            self._dev("MSI GeForce RTX 4090 Suprim Liquid X"),
            self._dev("ASUS ROG MAXIMUS Z790 HERO"),
            self._dev("Corsair MM700"),
        ]
        assert section.unmatched_scope_entries() == ()

    def test_names_the_entries_that_are_missing(self, section):
        """The real boot failure: only the GPU had enumerated."""
        section._lighting_scope = ("kraken", "geforce", "maximus", "mm700")
        section._lighting_devices = [
            self._dev("MSI GeForce RTX 4090 Suprim Liquid X"),
        ]
        assert set(section.unmatched_scope_entries()) == {
            "kraken", "maximus", "mm700"}

    def test_partial_list_still_reports_lighting_ok(self, section):
        """Why a health check alone could not catch this.

        One matched device is enough for lighting_health to say OK, so the
        monitor had no reason to re-query and cached the partial list for the
        whole session.
        """
        section._lighting_scope = ("kraken", "geforce", "maximus", "mm700")
        section._lighting_devices = [
            self._dev("MSI GeForce RTX 4090 Suprim Liquid X"),
        ]
        # Pin server_alive: lighting_health opens a real socket, so without
        # this the test only passes on a machine where OpenRGB happens to be
        # running - it would assert nothing on CI.
        import rgb_openrgb
        original = rgb_openrgb.server_alive
        rgb_openrgb.server_alive = lambda *a, **k: True
        try:
            state, _reason = section.lighting_health()
        finally:
            rgb_openrgb.server_alive = original
        assert state == section.LIGHTING_OK
        assert section.unmatched_scope_entries()    # but this does catch it

    def test_empty_device_list_reports_every_entry(self, section):
        section._lighting_scope = ("kraken", "geforce")
        section._lighting_devices = []
        assert set(section.unmatched_scope_entries()) == {"kraken", "geforce"}
