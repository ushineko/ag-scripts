"""Spec 021: Kraken RGB/LCD argv construction, dashboard rendering, and the
liquidctl serialisation queue.
"""

import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, PROJECT_DIR)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import aio_liquid  # noqa: E402


class TestColorArgv(unittest.TestCase):
    """021 AC1/AC2/AC3."""

    def test_named_colour(self):
        argv = aio_liquid.solid_color_argv("sync", "red")
        self.assertEqual(argv[-4:], ["sync", "color", "fixed", "ff0000"])

    def test_hex_colour(self):
        argv = aio_liquid.solid_color_argv("ring", "#ff8800")
        self.assertEqual(argv[-1], "ff8800")

    def test_off_uses_off_mode_not_black_fixed(self):
        """`off` is a device mode, not a fixed black — they differ on hardware."""
        argv = aio_liquid.solid_color_argv("sync", "off")
        self.assertEqual(argv[-2:], ["color", "off"])

    def test_colour_vocabulary_matches_spec_019(self):
        import aio_color
        self.assertIs(aio_liquid.NAMED_COLORS, aio_color.NAMED_COLORS)

    def test_rejects_unknown_channel(self):
        self.assertIsNone(aio_liquid.solid_color_argv("nope", "red"))

    def test_rejects_unparseable_colour(self):
        for bad in ("nope", "#12345", ""):
            with self.subTest(bad=bad):
                self.assertIsNone(aio_liquid.solid_color_argv("sync", bad))

    def test_rejects_unknown_mode(self):
        self.assertIsNone(aio_liquid.color_argv("sync", "not-a-mode"))

    def test_rejects_out_of_range_rgb(self):
        self.assertIsNone(aio_liquid.color_argv("sync", "fixed", [(300, 0, 0)]))

    def test_rejects_bool_as_channel_value(self):
        self.assertIsNone(aio_liquid.color_argv("sync", "fixed", [(True, 0, 0)]))

    def test_every_argv_is_a_list_not_a_shell_string(self):
        """No shell involvement anywhere: argv lists only."""
        for argv in (aio_liquid.solid_color_argv("sync", "red"),
                     aio_liquid.lcd_liquid_argv(),
                     aio_liquid.lcd_brightness_argv(50)):
            self.assertIsInstance(argv, list)
            self.assertTrue(all(isinstance(a, str) for a in argv))


class TestEffectModes(unittest.TestCase):
    """021 AC4 — enumerated from the driver, not hardcoded."""

    def test_split_by_whether_a_colour_is_required(self):
        modes = aio_liquid.effect_modes()
        self.assertIn("plain", modes)
        self.assertIn("colored", modes)
        if modes["plain"]:
            # Rainbow variants take no colour.
            self.assertTrue(any("rainbow" in m or "spectrum" in m
                                for m in modes["plain"]))

    def test_menu_excludes_fixed_and_off(self):
        modes = aio_liquid.effect_modes()
        everything = modes["plain"] + modes["colored"]
        self.assertNotIn("fixed", everything)
        self.assertNotIn("off", everything)


class TestLcdArgv(unittest.TestCase):
    """021 AC1/AC2."""

    def test_brightness_bounds(self):
        self.assertIsNotNone(aio_liquid.lcd_brightness_argv(0))
        self.assertIsNotNone(aio_liquid.lcd_brightness_argv(100))
        self.assertIsNone(aio_liquid.lcd_brightness_argv(-1))
        self.assertIsNone(aio_liquid.lcd_brightness_argv(101))
        self.assertIsNone(aio_liquid.lcd_brightness_argv(True))

    def test_orientation_only_accepts_quarter_turns(self):
        for good in (0, 90, 180, 270):
            self.assertIsNotNone(aio_liquid.lcd_orientation_argv(good))
        for bad in (45, 1, 360, -90):
            self.assertIsNone(aio_liquid.lcd_orientation_argv(bad))

    def test_liquid_mode(self):
        self.assertEqual(aio_liquid.lcd_liquid_argv()[-3:],
                         ["lcd", "screen", "liquid"])

    def test_static_requires_a_path(self):
        self.assertIsNone(aio_liquid.lcd_static_argv(""))
        self.assertIsNone(aio_liquid.lcd_static_argv(None))
        self.assertEqual(aio_liquid.lcd_static_argv("/tmp/x.png")[-1], "/tmp/x.png")


class TestCapabilityDetection(unittest.TestCase):
    """021: colour support is measured per device, never assumed.

    The NZXT Kraken 2024 Elite advertises four channel names at class level but
    implements none: liquidctl gives the instance an empty `_color_channels` and
    every colour write returns "operation not supported by the device". The menu
    must gate on the measured value.
    """

    def setUp(self):
        aio_liquid._color_channels_cache = None

    def tearDown(self):
        aio_liquid._color_channels_cache = None

    def test_probe_result_is_cached(self):
        first = aio_liquid.color_channels()
        aio_liquid._color_channels_cache = ["sentinel"]
        self.assertEqual(aio_liquid.color_channels(), ["sentinel"])
        self.assertIsInstance(first, list)

    def test_refresh_bypasses_the_cache(self):
        aio_liquid._color_channels_cache = ["stale"]
        self.assertNotEqual(aio_liquid.color_channels(refresh=True), ["stale"])

    def test_color_supported_follows_the_probe(self):
        aio_liquid._color_channels_cache = []
        self.assertFalse(aio_liquid.color_supported())
        aio_liquid._color_channels_cache = ["ring"]
        self.assertTrue(aio_liquid.color_supported())

    def test_unsupported_channel_is_rejected_when_others_are_known(self):
        aio_liquid._color_channels_cache = ["ring"]
        self.assertIsNone(aio_liquid.color_argv("logo", "fixed", [(255, 0, 0)]))
        self.assertIsNotNone(aio_liquid.color_argv("ring", "fixed", [(255, 0, 0)]))

    def test_empty_probe_does_not_hard_block(self):
        """An empty probe may mean 'probe failed', so the API stays permissive.

        The menu gates on color_supported(); the argv builder does not, so a
        machine where the library probe fails but the binary works is not
        locked out.
        """
        aio_liquid._color_channels_cache = []
        self.assertIsNotNone(aio_liquid.color_argv("sync", "fixed", [(255, 0, 0)]))

    def test_lcd_is_unaffected_by_colour_support(self):
        aio_liquid._color_channels_cache = []
        self.assertIsNotNone(aio_liquid.lcd_liquid_argv())
        self.assertIsNotNone(aio_liquid.lcd_brightness_argv(50))


if __name__ == "__main__":
    unittest.main()
