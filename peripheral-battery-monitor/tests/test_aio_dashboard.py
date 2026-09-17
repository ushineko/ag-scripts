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
