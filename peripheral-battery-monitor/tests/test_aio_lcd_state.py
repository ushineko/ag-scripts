"""Spec 022: GIF routing, dashboard state as one source of truth, intervals."""

import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, PROJECT_DIR)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

import aio_liquid  # noqa: E402
import aio_section  # noqa: E402

_app = QApplication.instance() or QApplication([])


def _gif(path, frames):
    from PIL import Image
    images = [Image.new("RGB", (32, 32), (i * 20 % 255, 0, 0)) for i in range(frames)]
    if frames == 1:
        images[0].save(path)
    else:
        images[0].save(path, save_all=True, append_images=images[1:], duration=50)
    return path


class TestAnimationDetection(unittest.TestCase):
    """022 AC1 — decided by reading the file, not by its extension."""

    def setUp(self):
        import tempfile
        self.dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.dir.cleanup()

    def _p(self, name):
        return os.path.join(self.dir.name, name)

    def test_multi_frame_gif_is_animated(self):
        self.assertTrue(aio_liquid.is_animated(_gif(self._p("a.gif"), 6)))

    def test_single_frame_gif_is_not_animated(self):
        self.assertFalse(aio_liquid.is_animated(_gif(self._p("b.gif"), 1)))

    def test_animated_file_with_a_misleading_extension_still_animates(self):
        self.assertTrue(aio_liquid.is_animated(_gif(self._p("c.png"), 4)))

    def test_missing_file_is_not_an_error(self):
        self.assertFalse(aio_liquid.is_animated("/nonexistent/x.gif"))

    def test_garbage_input_is_not_an_error(self):
        for bad in (None, "", 17, b"x"):
            with self.subTest(bad=bad):
                self.assertFalse(aio_liquid.is_animated(bad))


class TestImageRouting(unittest.TestCase):
    """022 AC2/AC3 — the reported bug: GIFs showed only their first frame."""

    def setUp(self):
        import tempfile
        self.dir = tempfile.TemporaryDirectory()
        self.section = aio_section.AioSection()
        self.calls = []
        self.section._submit_write = lambda argv, d: self.calls.append((d, argv))

    def tearDown(self):
        self.dir.cleanup()

    def test_animated_gif_uses_gif_mode(self):
        path = _gif(os.path.join(self.dir.name, "a.gif"), 8)
        self.section.set_lcd_image(path)
        self.assertEqual(self.calls[0][0], "lcd gif")
        self.assertIn("gif", self.calls[0][1])

    def test_still_image_uses_static_mode(self):
        path = _gif(os.path.join(self.dir.name, "b.gif"), 1)
        self.section.set_lcd_image(path)
        self.assertEqual(self.calls[0][0], "lcd static")
        self.assertIn("static", self.calls[0][1])


class TestDashboardStateIsSingleSourced(unittest.TestCase):
    """022 AC4/AC5/AC6/AC7 — the toggle could not be switched back on."""

    def setUp(self):
        self.section = aio_section.AioSection()
        self.section._submit_write = lambda argv, d: True
        self.events = []
        self.section.dashboardChanged.connect(self.events.append)

    def test_property_reflects_state(self):
        self.assertFalse(self.section.dashboard_enabled)
        self.section.set_dashboard_enabled(True)
        self.assertTrue(self.section.dashboard_enabled)

    def test_signal_fires_on_change_only(self):
        self.section.set_dashboard_enabled(True)
        self.section.set_dashboard_enabled(True)   # no-op
        self.section.set_dashboard_enabled(False)
        self.assertEqual(self.events, [True, False])

    def test_showing_an_image_disables_and_announces_it(self):
        """The regression: this disabled silently, so the menu went stale."""
        self.section.set_dashboard_enabled(True)
        self.events.clear()
        self.section.set_lcd_static("/tmp/x.png")
        self.assertFalse(self.section.dashboard_enabled)
        self.assertEqual(self.events, [False])

    def test_can_re_enable_after_showing_an_image(self):
        """AC7: one click, not two."""
        self.section.set_dashboard_enabled(True)
        self.section.set_lcd_static("/tmp/x.png")
        self.assertFalse(self.section.dashboard_enabled)
        self.section.set_dashboard_enabled(True)
        self.assertTrue(self.section.dashboard_enabled)

    def test_liquid_mode_also_announces(self):
        self.section.set_dashboard_enabled(True)
        self.events.clear()
        self.section.set_lcd_liquid()
        self.assertEqual(self.events, [False])

    def test_surrender_announces(self):
        self.section.set_dashboard_enabled(True)
        self.events.clear()
        self.section._notify = lambda *a, **k: None
        self.section._surrender_dashboard()
        self.assertFalse(self.section.dashboard_enabled)
        self.assertIn(False, self.events)


class TestRefreshInterval(unittest.TestCase):
    """022 AC8."""

    def setUp(self):
        self.section = aio_section.AioSection()

    def test_default_interval(self):
        self.assertEqual(self.section.dashboard_interval_ms,
                         aio_section.LCD_PUSH_INTERVAL_MS)

    def test_accepts_allowed_values(self):
        for ms in aio_section.LCD_PUSH_INTERVALS_MS:
            with self.subTest(ms=ms):
                self.assertTrue(self.section.set_dashboard_interval(ms))
                self.assertEqual(self.section.dashboard_interval_ms, ms)

    def test_rejects_disallowed_values(self):
        before = self.section.dashboard_interval_ms
        for bad in (0, 1000, 7, -5, None, "30000"):
            with self.subTest(bad=bad):
                self.assertFalse(self.section.set_dashboard_interval(bad))
        self.assertEqual(self.section.dashboard_interval_ms, before)

    def test_no_interval_faster_than_the_poll(self):
        """A push cannot carry fresher data than the 5 s poll produces."""
        self.assertGreaterEqual(min(aio_section.LCD_PUSH_INTERVALS_MS),
                                aio_section.POLL_INTERVAL_MS)


class TestMultiDeviceColour(unittest.TestCase):
    """022 AC9/AC10/AC11 — not verifiable on this hardware; stubs stand in."""

    def tearDown(self):
        aio_liquid._color_devices_cache = None

    def test_match_tokens_are_unique(self):
        devices = [
            {"match": None, "description": "NZXT Kraken 2024 Elite RGB", "channels": ["r"]},
            {"match": None, "description": "NZXT RGB & Fan Controller", "channels": ["led1"]},
        ]
        aio_liquid._assign_match_tokens(devices)
        for device in devices:
            hits = sum(1 for d in devices
                       if device["match"] in d["description"].lower())
            self.assertEqual(hits, 1, f"{device['match']!r} must select one device")

    def test_ambiguous_names_fall_back_to_address(self):
        """"NZXT HUE 2" is a substring of "NZXT HUE 2 Ambient"."""
        devices = [
            {"match": None, "address": "/dev/hidraw9",
             "description": "NZXT HUE 2", "channels": ["led"]},
            {"match": None, "address": "/dev/hidraw10",
             "description": "NZXT HUE 2 Ambient", "channels": ["led"]},
        ]
        aio_liquid._assign_match_tokens(devices)
        selector = aio_liquid.device_selector(devices[0])
        self.assertEqual(selector, {"address": "/dev/hidraw9"})
        aio_liquid._color_devices_cache = devices
        argv = aio_liquid.color_argv("led", "fixed", [(255, 0, 0)], **selector)
        self.assertEqual(argv[:3], ["liquidctl", "--address", "/dev/hidraw9"])

    def test_unambiguous_device_uses_match_not_address(self):
        device = {"match": "kraken", "address": "/dev/hidraw1",
                  "ambiguous": False, "description": "NZXT Kraken", "channels": ["ring"]}
        self.assertEqual(aio_liquid.device_selector(device), {"match": "kraken"})


if __name__ == "__main__":
    unittest.main()
