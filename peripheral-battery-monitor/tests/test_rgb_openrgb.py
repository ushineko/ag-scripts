"""Spec 023: OpenRGB device parsing, scope, and per-device mode resolution.

Fixtures are trimmed captures of `openrgb --client --list-detailed` on
njv-cachyos (2026-09-16).
"""

import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, PROJECT_DIR)

import rgb_openrgb  # noqa: E402


DETAILED = """0: MSI GeForce RTX 4090 Suprim Liquid X
  Type:           GPU
  Modes: [Off] Direct 'Rainbow Wave' Magic 'Color Cycle' Breathing Flashing
  Zones: GPU

1: G502 X PLUS
  Type:           Mouse
  Modes: [Direct] Off Static Breathing 'Spectrum Cycle'
  Zones: 'Mouse LEDs'

2: NZXT Kraken 2024 ELITE Series RGB
  Type:           LED Strip
  Modes: [Direct] Static Fading 'Rainbow Wave' Marquee Breathing
  Zones: 'Hue 2 Channel 1' 'Hue 2 Channel 2'

3: ASUS ROG MAXIMUS Z790 HERO
  Type:           Motherboard
  Modes: [Direct] Off Static Breathing Flashing 'Spectrum Cycle' Rainbow
  Zones: 'Aura Mainboard' 'Addressable RGB Header 1'
"""

SIMPLE = """0: MSI GeForce RTX 4090 Suprim Liquid X
1: G502 X PLUS
2: NZXT Kraken 2024 ELITE Series RGB
"""

# A server that has rescanned lists every device twice.
DUPLICATED = SIMPLE + """3: MSI GeForce RTX 4090 Suprim Liquid X
4: G502 X PLUS
5: NZXT Kraken 2024 ELITE Series RGB
"""


class TestDeviceParsing(unittest.TestCase):
    """023 AC3."""

    def test_simple_list(self):
        devices = rgb_openrgb.parse_devices(SIMPLE)
        self.assertEqual([d["name"] for d in devices][:1],
                         ["MSI GeForce RTX 4090 Suprim Liquid X"])
        self.assertEqual(len(devices), 3)

    def test_duplicates_are_collapsed(self):
        """A rescanned server repeats devices; commands must not double."""
        devices = rgb_openrgb.parse_devices(DUPLICATED)
        self.assertEqual(len(devices), 3)
        self.assertEqual([d["index"] for d in devices], [0, 1, 2])

    def test_accepts_bytes(self):
        self.assertEqual(len(rgb_openrgb.parse_devices(SIMPLE.encode())), 3)

    def test_empty_and_garbage(self):
        for bad in (None, "", b"", "no devices here"):
            with self.subTest(bad=bad):
                self.assertEqual(rgb_openrgb.parse_devices(bad), [])


class TestModeParsing(unittest.TestCase):
    """023 AC4 — the active mode is how a write is confirmed."""

    def test_active_mode_is_the_bracketed_one(self):
        modes, active = rgb_openrgb.parse_modes(
            "[Off] Direct 'Rainbow Wave' Breathing")
        self.assertEqual(active, "Off")
        self.assertIn("Direct", modes)

    def test_quoted_multiword_modes(self):
        modes, _ = rgb_openrgb.parse_modes("[Direct] 'Rainbow Wave' 'Color Cycle'")
        self.assertIn("Rainbow Wave", modes)
        self.assertIn("Color Cycle", modes)

    def test_no_active_mode(self):
        modes, active = rgb_openrgb.parse_modes("Direct Static")
        self.assertIsNone(active)
        self.assertEqual(modes, ["Direct", "Static"])

    def test_empty(self):
        self.assertEqual(rgb_openrgb.parse_modes(""), ([], None))


class TestDetailedParsing(unittest.TestCase):
    def setUp(self):
        self.devices = rgb_openrgb.parse_detailed(DETAILED)

    def test_all_devices(self):
        self.assertEqual(len(self.devices), 4)

    def test_types_and_modes(self):
        gpu = self.devices[0]
        self.assertEqual(gpu["type"], "GPU")
        self.assertEqual(gpu["active_mode"], "Off")
        self.assertIn("Direct", gpu["modes"])
        self.assertNotIn("Static", gpu["modes"])

    def test_kraken_has_static_but_no_off(self):
        kraken = next(d for d in self.devices if "Kraken" in d["name"])
        self.assertIn("Static", kraken["modes"])
        self.assertNotIn("Off", kraken["modes"])


class TestScope(unittest.TestCase):
    """023 AC6 — case interior by default, peripherals untouched."""

    def setUp(self):
        self.devices = rgb_openrgb.parse_detailed(DETAILED)

    def test_default_scope_is_case_interior(self):
        names = [d["name"] for d in rgb_openrgb.scoped_devices(self.devices)]
        self.assertIn("NZXT Kraken 2024 ELITE Series RGB", names)
        self.assertIn("MSI GeForce RTX 4090 Suprim Liquid X", names)
        self.assertIn("ASUS ROG MAXIMUS Z790 HERO", names)

    def test_mouse_is_in_scope(self):
        """032/035: the mouse joined the default scope.

        Solaar cannot set its colour - its CLI takes the effect name and drops
        the colour - so OpenRGB drives it like every other device.
        """
        names = [d["name"] for d in rgb_openrgb.scoped_devices(self.devices)]
        self.assertIn("G502 X PLUS", names)

    def test_keyboard_stays_out_of_scope(self):
        """Per-application lighting; a scene should not fight it."""
        names = [d["name"] for d in rgb_openrgb.scoped_devices(self.devices)]
        self.assertNotIn("Keychron K4 HE", names)

    def test_custom_scope(self):
        names = [d["name"] for d in
                 rgb_openrgb.scoped_devices(self.devices, ("g502",))]
        self.assertEqual(names, ["G502 X PLUS"])


class TestModeResolution(unittest.TestCase):
    """023 AC4 — the GPU going dark is why this is not optional."""

    def test_gpu_solid_is_direct_not_static(self):
        gpu = rgb_openrgb.parse_detailed(DETAILED)[0]
        self.assertEqual(rgb_openrgb.resolve_mode(gpu["modes"], "solid"), "Direct")

    def test_kraken_solid_is_static(self):
        kraken = next(d for d in rgb_openrgb.parse_detailed(DETAILED)
                      if "Kraken" in d["name"])
        self.assertEqual(rgb_openrgb.resolve_mode(kraken["modes"], "solid"), "Static")

    def test_kraken_off_falls_back_to_direct(self):
        """No Off mode, so off is expressed as a solid black."""
        kraken = next(d for d in rgb_openrgb.parse_detailed(DETAILED)
                      if "Kraken" in d["name"])
        self.assertEqual(rgb_openrgb.resolve_mode(kraken["modes"], "off"), "Direct")

    def test_returns_the_devices_own_spelling(self):
        self.assertEqual(rgb_openrgb.resolve_mode(["Static"], "solid"), "Static")

    def test_unsupported_intent_is_none_not_a_guess(self):
        self.assertIsNone(rgb_openrgb.resolve_mode(["Rainbow"], "solid"))

    def test_empty_modes(self):
        self.assertIsNone(rgb_openrgb.resolve_mode([], "solid"))


class TestArgv(unittest.TestCase):
    """023 AC2 — always --client, never the detecting form."""

    def test_uses_client_mode(self):
        for argv in (rgb_openrgb.list_argv(), rgb_openrgb.detail_argv(),
                     rgb_openrgb.set_color_argv("Kraken", "Static", (255, 0, 0))):
            with self.subTest(argv=argv):
                self.assertIn("--client", argv)

    def test_colour_is_uppercase_hex(self):
        argv = rgb_openrgb.set_color_argv("Kraken", "Static", (255, 136, 0))
        self.assertEqual(argv[-1], "FF8800")

    def test_addresses_by_name(self):
        argv = rgb_openrgb.set_color_argv("NZXT Kraken", "Static", (1, 2, 3))
        self.assertIn("NZXT Kraken", argv)

    def test_short_names_rejected(self):
        """OpenRGB needs 3+ chars; a shorter name matches unpredictably."""
        self.assertIsNone(rgb_openrgb.set_color_argv("ab", "Static", (1, 2, 3)))

    def test_mode_without_colour_is_allowed(self):
        argv = rgb_openrgb.set_color_argv("Kraken", "Off")
        self.assertNotIn("--color", argv)

    def test_bad_inputs(self):
        self.assertIsNone(rgb_openrgb.set_color_argv(None, "Static"))
        self.assertIsNone(rgb_openrgb.set_color_argv(-1, "Static"))
        self.assertIsNone(rgb_openrgb.set_color_argv("Kraken", ""))
        self.assertIsNone(rgb_openrgb.set_color_argv("Kraken", "Static", (300, 0, 0)))

    def test_argv_is_a_list_never_a_shell_string(self):
        argv = rgb_openrgb.set_color_argv("Kraken", "Static", (0, 0, 0))
        self.assertTrue(all(isinstance(a, str) for a in argv))


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()


class TestSolidModeOverrides(unittest.TestCase):
    """032 — Static does not drive the ASUS ARGB headers; Direct does."""

    AURA_MODES = ["Direct", "Off", "Static", "Breathing", "Flashing",
                  "Spectrum Cycle", "Rainbow", "Chase Fade", "Chase"]

    def test_aura_board_gets_direct_although_it_advertises_static(self):
        """The fault: Static lights only the onboard LED, headers go dark."""
        self.assertEqual(
            rgb_openrgb.resolve_mode(self.AURA_MODES, "solid",
                                     "ASUS ROG MAXIMUS Z790 HERO"),
            "Direct")

    def test_override_matches_case_insensitively(self):
        self.assertEqual(
            rgb_openrgb.resolve_mode(self.AURA_MODES, "solid",
                                     "asus rog maximus z790 hero"),
            "Direct")

    def test_gpu_still_prefers_static_when_it_offers_both(self):
        """Regression guard: static-first exists because the 4090 rejects it.

        A device outside the override list must not be dragged onto Direct by
        this change.
        """
        both = ["Static", "Direct"]
        self.assertEqual(rgb_openrgb.resolve_mode(both, "solid",
                                                  "MSI GeForce RTX 4090"),
                         "Static")

    def test_no_device_name_keeps_the_default_order(self):
        self.assertEqual(rgb_openrgb.resolve_mode(["Static", "Direct"], "solid"),
                         "Static")

    def test_overridden_device_with_only_static_still_gets_static(self):
        """The override is a preference, not a requirement."""
        self.assertEqual(
            rgb_openrgb.resolve_mode(["Static"], "solid",
                                     "ASUS ROG MAXIMUS Z790 HERO"),
            "Static")

    def test_overridden_device_with_neither_is_none(self):
        self.assertIsNone(
            rgb_openrgb.resolve_mode(["Rainbow"], "solid",
                                     "ASUS ROG MAXIMUS Z790 HERO"))

    def test_off_intent_is_unchanged_by_the_override(self):
        self.assertEqual(
            rgb_openrgb.resolve_mode(self.AURA_MODES, "off",
                                     "ASUS ROG MAXIMUS Z790 HERO"),
            "Off")

    def test_solid_modes_for_is_data_driven(self):
        self.assertEqual(rgb_openrgb.solid_modes_for("ASUS Aura thing"),
                         ("direct", "static"))
        self.assertEqual(rgb_openrgb.solid_modes_for("Some Other Device"),
                         rgb_openrgb.SOLID_MODES)
        self.assertEqual(rgb_openrgb.solid_modes_for(None),
                         rgb_openrgb.SOLID_MODES)
