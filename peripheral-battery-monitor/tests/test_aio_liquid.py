"""Specs 021-023: Kraken LCD argv construction.

The RGB half of specs 021/022 was removed in spec 023: liquidctl exposes no
colour channels for this cooler, so that backend could never have driven it.
Lighting is covered by tests/test_rgb_openrgb.py instead.
"""

import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, PROJECT_DIR)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import aio_liquid  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
