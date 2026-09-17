"""Spec 021: LCD dashboard rendering and the change-gate that limits pushes."""

import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, PROJECT_DIR)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

import aio_dashboard  # noqa: E402

_app = QApplication.instance() or QApplication([])

HEALTHY = {"coolant_temp_c": 36.8, "cpu_temp_c": 54.0, "pump_rpm": 1727,
           "alert_state": "ok"}
CRITICAL = {"coolant_temp_c": 63.2, "cpu_temp_c": 99.0, "pump_rpm": 0,
            "alert_state": "critical", "alert_reason": "Pump stopped (0 rpm)"}
EMPTY = {"coolant_temp_c": None, "cpu_temp_c": None, "pump_rpm": None,
         "alert_state": "ok"}


class TestRender(unittest.TestCase):
    """021 AC7/AC8."""

    def test_native_lcd_resolution(self):
        image = aio_dashboard.render_dashboard(HEALTHY)
        self.assertEqual((image.width(), image.height()), (640, 640))
        self.assertEqual((image.width(), image.height()), aio_dashboard.SIZE and
                         (aio_dashboard.SIZE, aio_dashboard.SIZE))

    def test_renders_every_state_without_raising(self):
        for snap in (HEALTHY, CRITICAL, EMPTY, {}, None):
            with self.subTest(snap=snap):
                image = aio_dashboard.render_dashboard(snap)
                self.assertFalse(image.isNull())

    def test_missing_values_degrade_to_placeholders(self):
        self.assertEqual(aio_dashboard.content_key(EMPTY)[:3], ("--", "--", "--"))

    def test_writes_png(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "sub", "lcd.png")
            self.assertTrue(aio_dashboard.write_png(
                aio_dashboard.render_dashboard(HEALTHY), path))
            self.assertGreater(os.path.getsize(path), 0)

    def test_write_failure_returns_false(self):
        self.assertFalse(aio_dashboard.write_png(
            aio_dashboard.render_dashboard(HEALTHY), "/proc/nope/lcd.png"))


class TestChangeGate(unittest.TestCase):
    """021 AC9 — the main defence against liquidctl#774 is not writing."""

    def test_subdegree_drift_does_not_change_the_key(self):
        a = dict(HEALTHY)
        b = dict(HEALTHY, coolant_temp_c=36.84, cpu_temp_c=54.4)
        self.assertEqual(aio_dashboard.content_key(a), aio_dashboard.content_key(b))

    def test_a_whole_degree_does_change_the_key(self):
        b = dict(HEALTHY, coolant_temp_c=38.0)
        self.assertNotEqual(aio_dashboard.content_key(HEALTHY),
                            aio_dashboard.content_key(b))

    def test_pump_rpm_change_is_visible(self):
        b = dict(HEALTHY, pump_rpm=0)
        self.assertNotEqual(aio_dashboard.content_key(HEALTHY),
                            aio_dashboard.content_key(b))

    def test_alert_state_change_is_visible(self):
        b = dict(HEALTHY, alert_state="critical")
        self.assertNotEqual(aio_dashboard.content_key(HEALTHY),
                            aio_dashboard.content_key(b))

    def test_non_dict_is_safe(self):
        self.assertEqual(len(aio_dashboard.content_key(None)), 4)


if __name__ == "__main__":
    unittest.main()


class TestPushGate(unittest.TestCase):
    """The gate that decides how often the LCD is written at all.

    Keying on CPU temperature at whole degrees was a design error: an idle
    i9-14900K wanders continuously, so the gate never suppressed anything and
    the screen was rewritten every interval.
    """

    BASE = {"coolant_temp_c": 36.8, "cpu_temp_c": 50.0, "pump_rpm": 1727,
            "alert_state": "ok"}

    def _v(self, **kw):
        return dict(self.BASE, **kw)

    def test_first_push_always_happens(self):
        self.assertTrue(aio_dashboard.should_push(self.BASE, None))

    def test_identical_snapshot_does_not_push(self):
        self.assertFalse(aio_dashboard.should_push(self.BASE, self.BASE))

    # -- the bug this fixes ------------------------------------------------

    def test_small_cpu_wander_does_not_push(self):
        """The actual regression: CPU drifting a few degrees forced a write."""
        for cpu in (51.0, 52.5, 46.0, 54.9):
            with self.subTest(cpu=cpu):
                self.assertFalse(
                    aio_dashboard.should_push(self._v(cpu_temp_c=cpu), self.BASE))

    def test_large_cpu_change_does_push(self):
        self.assertTrue(
            aio_dashboard.should_push(self._v(cpu_temp_c=90.0), self.BASE))

    def test_cpu_threshold_is_compared_against_what_is_on_screen(self):
        """A value creeping up in small steps must still eventually redraw.

        Comparing each sample against the previous *sample* would let CPU walk
        arbitrarily far from the displayed figure without ever tripping.
        """
        last = self.BASE
        for cpu in (52.0, 54.0, 56.0):
            pushed = aio_dashboard.should_push(self._v(cpu_temp_c=cpu), last)
        self.assertTrue(pushed, "56 C is >= 5 C from the displayed 50 C")

    # -- things that must never be suppressed ------------------------------

    def test_coolant_change_always_pushes(self):
        self.assertTrue(
            aio_dashboard.should_push(self._v(coolant_temp_c=37.8), self.BASE))

    def test_subdegree_coolant_drift_does_not_push(self):
        self.assertFalse(
            aio_dashboard.should_push(self._v(coolant_temp_c=36.84), self.BASE))

    def test_alert_state_change_always_pushes(self):
        self.assertTrue(
            aio_dashboard.should_push(self._v(alert_state="critical"), self.BASE))

    def test_pump_stopping_always_pushes(self):
        """The one transition that must never be thresholded away."""
        self.assertTrue(
            aio_dashboard.should_push(self._v(pump_rpm=0), self.BASE))

    def test_pump_starting_always_pushes(self):
        stopped = self._v(pump_rpm=0)
        self.assertTrue(aio_dashboard.should_push(self.BASE, stopped))

    def test_small_pump_jitter_does_not_push(self):
        self.assertFalse(
            aio_dashboard.should_push(self._v(pump_rpm=1740), self.BASE))

    def test_large_pump_change_does_push(self):
        self.assertTrue(
            aio_dashboard.should_push(self._v(pump_rpm=1200), self.BASE))

    # -- appearing / disappearing values -----------------------------------

    def test_value_becoming_unavailable_pushes(self):
        for field in ("cpu_temp_c", "pump_rpm", "coolant_temp_c"):
            with self.subTest(field=field):
                self.assertTrue(
                    aio_dashboard.should_push(self._v(**{field: None}), self.BASE))

    def test_value_becoming_available_pushes(self):
        missing = self._v(cpu_temp_c=None)
        self.assertTrue(aio_dashboard.should_push(self.BASE, missing))

    def test_garbage_new_snapshot_does_not_push(self):
        for bad in (None, "x", 5):
            with self.subTest(bad=bad):
                self.assertFalse(aio_dashboard.should_push(bad, self.BASE))

    def test_booleans_are_not_readings(self):
        self.assertTrue(
            aio_dashboard.should_push(self._v(cpu_temp_c=True), self.BASE))


class TestBackground(unittest.TestCase):
    """Spec 024: the starfield is generated once and never changes."""

    def test_background_is_cached(self):
        first = aio_dashboard._background()
        self.assertIs(aio_dashboard._background(), first)

    def test_background_is_lcd_sized(self):
        bg = aio_dashboard._background()
        self.assertEqual((bg.width(), bg.height()),
                         (aio_dashboard.SIZE, aio_dashboard.SIZE))

    def test_renders_are_pixel_identical_for_identical_input(self):
        """A per-frame starfield would shimmer between updates.

        On a screen that only redraws when something changes, shimmer reads as
        a fault rather than decoration — so the sky must be deterministic.
        """
        a = aio_dashboard.render_dashboard(HEALTHY)
        b = aio_dashboard.render_dashboard(HEALTHY)
        self.assertEqual(a.bits().asstring(a.sizeInBytes()),
                         b.bits().asstring(b.sizeInBytes()))

    def test_background_survives_a_cache_reset(self):
        aio_dashboard._background_cache = None
        self.assertFalse(aio_dashboard._background().isNull())

    def test_render_does_not_mutate_the_cached_background(self):
        """render_dashboard copies; drawing into the cache would accumulate."""
        bg = aio_dashboard._background()
        before = bg.bits().asstring(bg.sizeInBytes())
        aio_dashboard.render_dashboard(CRITICAL)
        after = aio_dashboard._background().bits().asstring(bg.sizeInBytes())
        self.assertEqual(before, after)


class TestSeverityColours(unittest.TestCase):
    """A stopped pump must not be drawn in the calm accent colour."""

    def test_stopped_pump_renders_without_error(self):
        image = aio_dashboard.render_dashboard(CRITICAL)
        self.assertFalse(image.isNull())

    def test_cpu_is_never_graded(self):
        """Deliberate: a 14900K at 100 C is normal and must not read as alarm."""
        hot = dict(HEALTHY, cpu_temp_c=100.0)
        self.assertFalse(aio_dashboard.render_dashboard(hot).isNull())
