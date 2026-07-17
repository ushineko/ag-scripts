"""Tests for kwin_window_position (Wayland window position save/restore helper).

The live KWin Scripting round-trip requires a running compositor and is verified
manually against a real session; these tests cover the pure logic and the
graceful-degradation contract (no crashes / no-ops when KWin is absent).

Qt imports are deferred to setUpModule() rather than module top-level: this file
uses the real PyQt6, but test_battery_logic replaces PyQt6 in sys.modules with
mocks during collection. It restores them in its tearDownModule, which runs
before this module's setUpModule, so importing here at run-time sees the real
modules and never re-imports a live Qt C-extension.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, PROJECT_DIR)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Populated by setUpModule() once the real modules are guaranteed present.
kwin_window_position = None
KWinWindowPosition = None
_sanitize = None
_QDBusModule = None
_app = None


def setUpModule():
    global kwin_window_position, KWinWindowPosition, _sanitize, _app
    from PyQt6.QtCore import QCoreApplication
    import kwin_window_position as _kwp
    kwin_window_position = _kwp
    KWinWindowPosition = _kwp.KWinWindowPosition
    _sanitize = _kwp._sanitize
    _app = QCoreApplication.instance() or QCoreApplication(sys.argv)


def _make_mgr(available=None):
    """Construct a manager without touching the real session bus.

    ``__init__`` calls ``QDBusConnection.sessionBus()`` and registers a service,
    which is neither hermetic nor safe alongside the Qt-mocking done by
    test_battery_logic in the same process. Patch it out for unit tests.
    """
    with patch.object(kwin_window_position, "QDBusConnection") as qc:
        qc.sessionBus.return_value = MagicMock()
        with patch.object(KWinWindowPosition, "_register_dbus", return_value=True), \
             patch.object(KWinWindowPosition, "_kwin_present", return_value=True):
            mgr = KWinWindowPosition("peripheral-battery-monitor")
    if available is not None:
        mgr._available = available
    return mgr


class TestSanitize(unittest.TestCase):
    def test_hyphens_become_underscores(self):
        self.assertEqual(_sanitize("peripheral-battery-monitor"),
                         "peripheral_battery_monitor")

    def test_dots_and_specials_become_underscores(self):
        self.assertEqual(_sanitize("org.kde.App v2"), "org_kde_App_v2")

    def test_alnum_preserved(self):
        self.assertEqual(_sanitize("App123"), "App123")


class TestScriptGeneration(unittest.TestCase):
    def setUp(self):
        self.mgr = _make_mgr()

    def test_service_name_derived_from_app_id(self):
        self.assertEqual(self.mgr._service,
                         "org.agscripts.peripheral_battery_monitor")

    def test_move_js_embeds_coordinates_and_app_id(self):
        js = self.mgr._move_js(640, 1550)
        self.assertIn('resourceClass == "peripheral-battery-monitor"', js)
        self.assertIn("x: 640", js)
        self.assertIn("y: 1550", js)
        # width/height are preserved from the live geometry, not hard-coded.
        self.assertIn("width: g.width", js)
        self.assertIn("height: g.height", js)

    def test_report_js_calls_back_over_dbus(self):
        js = self.mgr._report_js()
        self.assertIn('callDBus("org.agscripts.peripheral_battery_monitor"', js)
        self.assertIn('"/WindowPosition"', js)
        self.assertIn('"ReportGeometry"', js)
        self.assertIn("Math.round(g.x)", js)
        self.assertIn("Math.round(g.y)", js)


class TestReportSignal(unittest.TestCase):
    def test_report_geometry_emits_signal(self):
        mgr = _make_mgr()
        received = []
        mgr.geometryReported.connect(lambda x, y: received.append((x, y)))
        mgr.ReportGeometry(101, 202)
        self.assertEqual(received, [(101, 202)])


class TestGracefulDegradation(unittest.TestCase):
    def test_no_kwin_makes_operations_noop(self):
        mgr = _make_mgr()
        # Force the "KWin unavailable" state regardless of the test environment.
        mgr._available = False
        with patch.object(mgr, "_run_script") as run:
            mgr.restore(10, 20)
            mgr.request_report()
            run.assert_not_called()
        self.assertFalse(mgr.is_available())

    def test_available_delegates_to_run_script(self):
        mgr = _make_mgr()
        mgr._available = True
        with patch.object(mgr, "_run_script") as run:
            mgr.restore(10, 20)
            mgr.request_report()
            self.assertEqual(run.call_count, 2)


if __name__ == "__main__":
    unittest.main()
