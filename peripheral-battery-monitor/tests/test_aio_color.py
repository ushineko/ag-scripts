"""Spec 019: RGB request builders.

Pure request-shape tests. Nothing here touches the daemon; the ordering
assertions are the point, since the documented failure mode is a correct-looking
sequence in the wrong order that changes no LED.
"""

import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, PROJECT_DIR)

import aio_color  # noqa: E402

DEVICE = "207132833748"
CHANNELS = [0, 1, 2, 3, 4, 5, 6]


class TestParseColor(unittest.TestCase):
    """AC3."""

    def test_every_named_colour_resolves(self):
        for name, expected in aio_color.NAMED_COLORS.items():
            with self.subTest(name=name):
                self.assertEqual(aio_color.parse_color(name), expected)

    def test_matches_the_shell_script_values(self):
        # Both tools must mean the same thing by a colour name.
        self.assertEqual(aio_color.parse_color("orange"), (255, 85, 0))
        self.assertEqual(aio_color.parse_color("teal"), (0, 255, 128))
        self.assertEqual(aio_color.parse_color("off"), (0, 0, 0))

    def test_hex(self):
        self.assertEqual(aio_color.parse_color("#ff8800"), (255, 136, 0))
        self.assertEqual(aio_color.parse_color("ff8800"), (255, 136, 0))
        self.assertEqual(aio_color.parse_color("#FF8800"), (255, 136, 0))

    def test_case_insensitive_names(self):
        self.assertEqual(aio_color.parse_color("RED"), (255, 0, 0))
        self.assertEqual(aio_color.parse_color("  Red  "), (255, 0, 0))

    def test_rejects_junk(self):
        for value in ("nope", "#12345", "#gggggg", "", "   ", None, 42):
            with self.subTest(value=value):
                self.assertIsNone(aio_color.parse_color(value))


class TestSolidRequests(unittest.TestCase):
    """AC4."""

    def setUp(self):
        self.stages = aio_color.solid_requests(DEVICE, CHANNELS, (255, 0, 0))

    def test_two_stages_in_the_order_that_works(self):
        self.assertEqual(len(self.stages), 2)
        self.assertTrue(
            all(path == aio_color.PATH_SET_OVERRIDE for path, _ in self.stages[0])
        )
        self.assertTrue(all(path == aio_color.PATH_COLOR for path, _ in self.stages[1]))

    def test_override_payload(self):
        _path, payload = self.stages[0][0]
        self.assertEqual(payload["deviceId"], DEVICE)
        self.assertEqual(payload["channelId"], 0)
        self.assertEqual(payload["subDeviceId"], 0)
        self.assertIs(payload["enabled"], True)
        red = {"red": 255, "green": 0, "blue": 0}
        self.assertEqual(payload["startColor"], red)
        self.assertEqual(payload["endColor"], red)

    def test_profile_is_static(self):
        _path, payload = self.stages[1][0]
        self.assertEqual(payload["profile"], "static")

    def test_covers_every_channel(self):
        for stage in self.stages:
            self.assertEqual([p["channelId"] for _, p in stage], CHANNELS)


class TestEffectRequests(unittest.TestCase):
    """AC5."""

    def setUp(self):
        self.stages = aio_color.effect_requests(DEVICE, CHANNELS, "rainbow")

    def test_override_is_disabled_before_the_profile(self):
        # An enabled override masks the animation.
        first_path, first_payload = self.stages[0][0]
        self.assertEqual(first_path, aio_color.PATH_SET_OVERRIDE)
        self.assertIs(first_payload["enabled"], False)
        second_path, second_payload = self.stages[1][0]
        self.assertEqual(second_path, aio_color.PATH_COLOR)
        self.assertEqual(second_payload["profile"], "rainbow")


class TestBrightness(unittest.TestCase):
    def test_zero_prepends_a_repair_stage(self):
        """AC6: at level 0 every LED is dark and a colour cannot be seen."""
        stages = aio_color.solid_requests(DEVICE, CHANNELS, (255, 0, 0), brightness=0)
        self.assertEqual(len(stages), 3)
        path, payload = stages[0][0]
        self.assertEqual(path, aio_color.PATH_BRIGHTNESS)
        self.assertEqual(payload["brightness"], aio_color.BRIGHTNESS_REPAIR)

    def test_other_levels_are_left_alone(self):
        for level in (1, 2, 3, None):
            with self.subTest(level=level):
                stages = aio_color.solid_requests(
                    DEVICE, CHANNELS, (255, 0, 0), brightness=level
                )
                self.assertEqual(len(stages), 2)

    def test_effects_get_the_same_repair(self):
        stages = aio_color.effect_requests(DEVICE, CHANNELS, "rainbow", brightness=0)
        self.assertEqual(stages[0][0][0], aio_color.PATH_BRIGHTNESS)

    def test_request_shape(self):
        path, payload = aio_color.brightness_request(DEVICE, 2)
        self.assertEqual(path, "brightness")
        self.assertEqual(payload, {"deviceId": DEVICE, "brightness": 2})

    def test_rejects_out_of_range(self):
        """AC7."""
        for level in (-1, 4, 99, "3", True, None):
            with self.subTest(level=level):
                with self.assertRaises(ValueError):
                    aio_color.brightness_request(DEVICE, level)


class TestEffectsForDevice(unittest.TestCase):
    """AC10: per-device, not the global rgb.json the shell script reads."""

    PAYLOAD = {
        "code": 200,
        "status": 0,
        "data": {
            DEVICE: {
                "device": "iCUE COMMANDER Core",
                "profiles": {"rainbow": {}, "static": {}, "off": {}, "nebula": {}},
            },
            "cluster": {"device": "Cluster", "profiles": {"visor": {}}},
        },
    }

    def test_returns_only_this_device_sorted(self):
        self.assertEqual(
            aio_color.effects_for_device(self.PAYLOAD, DEVICE), ["nebula", "rainbow"]
        )

    def test_excludes_profiles_reachable_from_the_colour_menu(self):
        result = aio_color.effects_for_device(self.PAYLOAD, DEVICE)
        self.assertNotIn("static", result)
        self.assertNotIn("off", result)

    def test_does_not_leak_another_devices_profiles(self):
        self.assertNotIn("visor", aio_color.effects_for_device(self.PAYLOAD, DEVICE))

    def test_unknown_device_and_junk(self):
        for payload, device in (
            (self.PAYLOAD, "nosuch"),
            (self.PAYLOAD, None),
            (None, DEVICE),
            ({}, DEVICE),
            ({"data": None}, DEVICE),
            ({"data": {DEVICE: {"profiles": None}}}, DEVICE),
            ("a string", DEVICE),
        ):
            with self.subTest(device=device, payload=type(payload).__name__):
                self.assertEqual(aio_color.effects_for_device(payload, device), [])


if __name__ == "__main__":
    unittest.main()
