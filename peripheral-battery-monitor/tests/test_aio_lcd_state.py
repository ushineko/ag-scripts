"""Spec 022: GIF routing, dashboard state as one source of truth, intervals."""

import os
import sys
import unittest
import unittest.mock

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
        self.section._submit_write = (
            lambda argv, d, **kw: self.calls.append((d, argv)))

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
        self.section._submit_write = lambda argv, d, **kw: True
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
        # 1000 is now a declared diagnostic interval, so it is no longer invalid.
        for bad in (0, 7, -5, None, "30000", 2000):
            with self.subTest(bad=bad):
                self.assertFalse(self.section.set_dashboard_interval(bad))
        self.assertEqual(self.section.dashboard_interval_ms, before)

    def test_only_diagnostic_intervals_beat_the_poll(self):
        """A push cannot carry fresher data than the 5 s poll produces.

        Sub-poll intervals are therefore diagnostic only — they exist to
        measure the load repeated LCD writes generate — and every one of them
        must be declared as such, so a "useful" setting can never quietly be
        added below the poll cadence.
        """
        for ms in aio_section.LCD_PUSH_INTERVALS_MS:
            with self.subTest(ms=ms):
                if ms < aio_section.POLL_INTERVAL_MS:
                    self.assertIn(ms, aio_section.LCD_DIAGNOSTIC_INTERVALS_MS)

    def test_diagnostic_intervals_are_selectable(self):
        for ms in aio_section.LCD_DIAGNOSTIC_INTERVALS_MS:
            with self.subTest(ms=ms):
                self.assertIn(ms, aio_section.LCD_PUSH_INTERVALS_MS)
                self.assertTrue(self.section.set_dashboard_interval(ms))


class TestLightingPersistence(unittest.TestCase):
    """023 AC7 - scope and last-applied colour survive a restart.

    Lives here rather than in test_rgb_openrgb.py because it needs an
    AioSection, and this module already owns the module-level QApplication.
    Creating one per TestCase aborts Qt during teardown.
    """

    def setUp(self):
        import rgb_openrgb
        self.rgb = rgb_openrgb
        self.section = aio_section.AioSection()
        self.section._submit_write = lambda argv, d, **kw: True
        # apply_lighting submits through the queue directly, not _submit_write.
        # Without stubbing this seam the test spawns real openrgb processes and
        # Qt aborts when the section is destroyed while they are still running.
        self.sent = []
        self.section.queue.submit = (
            lambda argv, pri, **k: self.sent.append(argv) or True)
        self.events = []
        self.section.lightingChanged.connect(self.events.append)
        self.detailed = rgb_openrgb.parse_detailed(
            "0: MSI GeForce RTX 4090 Suprim Liquid X\n"
            "  Type:           GPU\n"
            "  Modes: [Off] Direct Breathing\n"
            "2: NZXT Kraken 2024 ELITE Series RGB\n"
            "  Type:           LED Strip\n"
            "  Modes: [Direct] Static Fading\n"
        )

    def test_scope_defaults_to_case_interior(self):
        self.assertEqual(self.section.lighting_scope, self.rgb.DEFAULT_SCOPE)

    def test_scope_can_be_replaced(self):
        self.assertTrue(self.section.set_lighting_scope(("g502",)))
        self.assertEqual(self.section.lighting_scope, ("g502",))

    def test_bad_scope_rejected(self):
        before = self.section.lighting_scope
        for bad in ((), None, ("", "x"), (1, 2)):
            with self.subTest(bad=bad):
                self.assertFalse(self.section.set_lighting_scope(bad))
        self.assertEqual(self.section.lighting_scope, before)

    def test_applying_a_colour_emits_for_persistence(self):
        self.section._lighting_devices = self.detailed
        self.assertGreater(self.section.apply_lighting_color("red"), 0)
        self.assertEqual(self.events, ["red"])
        self.assertEqual(self.section.lighting_last_color, "red")

    def test_failed_apply_does_not_persist(self):
        self.section._lighting_devices = []
        self.assertEqual(self.section.apply_lighting_color("red"), 0)
        self.assertEqual(self.events, [])
        self.assertIsNone(self.section.lighting_last_color)

    def test_per_device_modes_are_used(self):
        """The GPU has no Static; it must get Direct, not a broadcast mode."""
        self.section._lighting_devices = self.detailed
        self.section.apply_lighting_color("red")
        modes = [a[a.index("--mode") + 1] for a in self.sent]
        self.assertIn("Direct", modes)
        self.assertIn("Static", modes)

    def test_restore_seeds_state_without_touching_hardware(self):
        self.section.restore_lighting_state("blue", ("kraken",))
        self.assertEqual(self.section.lighting_last_color, "blue")
        self.assertEqual(self.section.lighting_scope, ("kraken",))
        self.assertEqual(self.sent, [], "restore must not re-apply on startup")

    def test_restore_ignores_an_unparseable_colour(self):
        self.section.restore_lighting_state("not-a-colour")
        self.assertIsNone(self.section.lighting_last_color)


if __name__ == "__main__":
    unittest.main()


class TestLightingHealthAndHonesty(unittest.TestCase):
    """026: the failures that hid behind reported success.

    After a reboot the OpenRGB server had started before its devices were
    enumerable. Every layer then operated correctly on an empty device list and
    reported success, so lighting silently did nothing from the hotkeys, the
    menu and D-Bus alike.
    """

    def setUp(self):
        import rgb_openrgb
        self.rgb = rgb_openrgb
        self.section = aio_section.AioSection()
        self.sent = []
        self.section.queue.submit = (
            lambda argv, pri, **k: self.sent.append((argv, k)) or True)
        self.section._submit_write = lambda argv, d, **kw: True
        self.devices = rgb_openrgb.parse_detailed(
            "0: MSI GeForce RTX 4090 Suprim Liquid X\n"
            "  Type:           GPU\n"
            "  Modes: [Off] Direct Breathing\n"
            "2: NZXT Kraken 2024 ELITE Series RGB\n"
            "  Type:           LED Strip\n"
            "  Modes: [Direct] Static Fading\n"
        )

    # -- health classification ------------------------------------------

    def test_health_reports_no_server(self):
        self.section._lighting_devices = []
        with unittest.mock.patch.object(self.rgb, "server_alive", return_value=False):
            state, reason = self.section.lighting_health()
        self.assertEqual(state, self.section.LIGHTING_NO_SERVER)
        self.assertIn("not reachable", reason)

    def test_health_reports_no_devices(self):
        self.section._lighting_devices = []
        with unittest.mock.patch.object(self.rgb, "server_alive", return_value=True):
            state, _ = self.section.lighting_health()
        self.assertEqual(state, self.section.LIGHTING_NO_DEVICES)

    def test_health_reports_devices_present_but_none_in_scope(self):
        """The real post-reboot state: a server up, but only peripherals found."""
        self.section._lighting_devices = self.rgb.parse_detailed(
            "1: G502 X PLUS\n  Type:           Mouse\n  Modes: [Direct] Static\n")
        with unittest.mock.patch.object(self.rgb, "server_alive", return_value=True):
            state, reason = self.section.lighting_health()
        self.assertEqual(state, self.section.LIGHTING_NO_SCOPED)
        self.assertIn("restart openrgb-server", reason)

    def test_health_ok(self):
        self.section._lighting_devices = self.devices
        with unittest.mock.patch.object(self.rgb, "server_alive", return_value=True):
            state, _ = self.section.lighting_health()
        self.assertEqual(state, self.section.LIGHTING_OK)

    # -- a scene must not claim success it did not achieve ---------------

    def test_scene_with_no_devices_reports_failure(self):
        """The core regression: this returned True over D-Bus with nothing lit."""
        self.section.set_scenes({"1": {"color": "red", "lcd": "dashboard"}})
        self.section._lighting_devices = []
        with unittest.mock.patch.object(self.rgb, "server_alive", return_value=True):
            self.assertFalse(self.section.apply_scene(1))

    def test_scene_succeeds_when_lighting_lands(self):
        self.section.set_scenes({"1": {"color": "red", "lcd": "dashboard"}})
        self.section._lighting_devices = self.devices
        self.assertTrue(self.section.apply_scene(1))

    def test_lcd_only_scene_still_succeeds_without_lighting(self):
        """A scene naming no colour is not a lighting failure."""
        self.section.set_scenes({"1": {"lcd": "dashboard"}})
        self.section._lighting_devices = []
        self.assertTrue(self.section.apply_scene(1))

    def test_apply_lighting_with_no_devices_returns_zero(self):
        self.section._lighting_devices = []
        with unittest.mock.patch.object(self.rgb, "server_alive", return_value=True):
            self.assertEqual(self.section.apply_lighting_color("red"), 0)

    # -- coalescing ------------------------------------------------------

    def test_lighting_writes_coalesce_per_device(self):
        """Rapid scenes must converge on the last, not overflow the queue."""
        self.section._lighting_devices = self.devices
        self.section.apply_lighting_color("red")
        keys = [k.get("coalesce_key") for _, k in self.sent]
        self.assertTrue(all(k and k.startswith("rgb:") for k in keys), keys)
        self.assertEqual(len(set(keys)), len(keys), "one key per device")

    def test_three_scenes_do_not_exceed_one_key_per_device(self):
        self.section._lighting_devices = self.devices
        for colour in ("red", "green", "blue"):
            self.section.apply_lighting_color(colour)
        keys = {k.get("coalesce_key") for _, k in self.sent}
        self.assertEqual(len(keys), 2, "two devices -> two keys regardless of presses")
