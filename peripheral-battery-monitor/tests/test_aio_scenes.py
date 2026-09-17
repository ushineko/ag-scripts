"""Spec 025: scene defaults, validation and per-slot fallback."""

import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, PROJECT_DIR)

import aio_scenes  # noqa: E402


class TestSlots(unittest.TestCase):
    def test_valid_range(self):
        for slot in list(range(1, 10)) + list(range(11, 20)):
            with self.subTest(slot=slot):
                self.assertTrue(aio_scenes.valid_slot(slot))
                self.assertTrue(aio_scenes.valid_slot(str(slot)))

    def test_invalid(self):
        # 10 and 20 are the gaps between the two banks.
        for bad in (0, 10, 20, -1, None, "x", "", 1.5):
            with self.subTest(bad=bad):
                self.assertFalse(aio_scenes.valid_slot(bad))


class TestValidation(unittest.TestCase):
    def test_every_default_is_valid(self):
        for slot, scene in aio_scenes.DEFAULT_SCENES.items():
            with self.subTest(slot=slot):
                self.assertIsNone(aio_scenes.describe_problem(scene))

    def test_defaults_cover_every_slot_in_both_banks(self):
        expected = [str(n) for n in list(range(1, 10)) + list(range(11, 20))]
        self.assertEqual(sorted(aio_scenes.DEFAULT_SCENES), sorted(expected))

    def test_animation_bank_points_at_files(self):
        """Every animation slot names a path, not a keyword."""
        for slot in range(aio_scenes.ANIM_MIN, aio_scenes.ANIM_MAX + 1):
            with self.subTest(slot=slot):
                lcd = aio_scenes.DEFAULT_SCENES[str(slot)]["lcd"]
                self.assertNotIn(lcd, (aio_scenes.LCD_DASHBOARD,
                                       aio_scenes.LCD_LIQUID))
                self.assertTrue(lcd.endswith(".gif"))

    def test_animation_colours_are_explicit_hex(self):
        """Derived from each animation, so they must be hex, not names."""
        for slot in range(aio_scenes.ANIM_MIN, aio_scenes.ANIM_MAX + 1):
            with self.subTest(slot=slot):
                self.assertTrue(
                    aio_scenes.DEFAULT_SCENES[str(slot)]["color"].startswith("#"))

    def test_colour_only_and_lcd_only_are_valid(self):
        self.assertIsNone(aio_scenes.describe_problem({"color": "red", "lcd": None}))
        self.assertIsNone(aio_scenes.describe_problem({"color": None, "lcd": "liquid"}))

    def test_a_scene_that_changes_nothing_is_rejected(self):
        problem = aio_scenes.describe_problem({"color": None, "lcd": None})
        self.assertIn("changes nothing", problem)

    def test_bad_colour_is_reported_not_raised(self):
        problem = aio_scenes.describe_problem({"color": "chartreuse", "lcd": None})
        self.assertIn("unparseable", problem)

    def test_bad_lcd_keyword_is_reported(self):
        problem = aio_scenes.describe_problem({"color": None, "lcd": "sparkles"})
        self.assertIn("lcd must be", problem)

    def test_relative_lcd_path_rejected(self):
        """A relative path would resolve against whatever cwd the shortcut had."""
        self.assertIsNotNone(
            aio_scenes.describe_problem({"color": None, "lcd": "pic.gif"}))

    def test_unknown_keys_rejected(self):
        problem = aio_scenes.describe_problem(
            {"color": "red", "lcd": None, "brightness": 50})
        self.assertIn("brightness", problem)

    def test_non_dict_rejected(self):
        for bad in (None, [], "red", 5):
            with self.subTest(bad=bad):
                self.assertIsNotNone(aio_scenes.describe_problem(bad))

    def test_hex_colour_accepted(self):
        self.assertIsNone(
            aio_scenes.describe_problem({"color": "#ff8800", "lcd": "dashboard"}))


class TestLoad(unittest.TestCase):
    def test_empty_settings_yields_defaults(self):
        scenes = aio_scenes.load({})
        self.assertEqual(len(scenes), 18)
        self.assertEqual(scenes["1"]["color"],
                         aio_scenes.DEFAULT_SCENES["1"]["color"])

    def test_user_scene_overrides_the_default(self):
        scenes = aio_scenes.load(
            {aio_scenes.SETTINGS_KEY: {"1": {"color": "white", "lcd": "liquid"}}})
        self.assertEqual(scenes["1"], {"color": "white", "lcd": "liquid"})

    def test_one_bad_entry_costs_only_that_slot(self):
        """A hand-edited file with one typo must not break the other eight."""
        scenes = aio_scenes.load(
            {aio_scenes.SETTINGS_KEY: {"3": {"color": "nonsense", "lcd": None}}})
        self.assertEqual(len(scenes), 18)
        self.assertEqual(scenes["3"], aio_scenes.normalise(
            aio_scenes.DEFAULT_SCENES["3"]))

    def test_tilde_paths_are_expanded(self):
        scenes = aio_scenes.load(
            {aio_scenes.SETTINGS_KEY: {"2": {"color": None, "lcd": "~/x.gif"}}})
        self.assertTrue(scenes["2"]["lcd"].startswith(os.path.expanduser("~")))
        self.assertNotIn("~", scenes["2"]["lcd"])

    def test_garbage_settings_value_yields_defaults(self):
        for bad in ("nope", [], 5, None):
            with self.subTest(bad=bad):
                self.assertEqual(len(aio_scenes.load({aio_scenes.SETTINGS_KEY: bad})), 18)


class TestSeed(unittest.TestCase):
    def test_seeds_when_absent(self):
        settings = {}
        self.assertTrue(aio_scenes.seed(settings))
        self.assertEqual(len(settings[aio_scenes.SETTINGS_KEY]), 18)

    def test_never_overwrites_an_existing_slot(self):
        """The point of storing scenes in settings is that they can be retuned."""
        mine = {"color": "white", "lcd": "liquid"}
        settings = {aio_scenes.SETTINGS_KEY: {"1": dict(mine)}}
        aio_scenes.seed(settings)
        self.assertEqual(settings[aio_scenes.SETTINGS_KEY]["1"], mine)

    def test_seed_adds_a_bank_introduced_later(self):
        """A file written before the animation bank existed still gains it."""
        settings = {aio_scenes.SETTINGS_KEY: {
            str(n): dict(aio_scenes.DEFAULT_SCENES[str(n)]) for n in range(1, 10)}}
        self.assertTrue(aio_scenes.seed(settings))
        self.assertIn("11", settings[aio_scenes.SETTINGS_KEY])
        self.assertEqual(len(settings[aio_scenes.SETTINGS_KEY]), 18)

    def test_seed_is_idempotent(self):
        settings = {}
        aio_scenes.seed(settings)
        self.assertFalse(aio_scenes.seed(settings))

    def test_seeds_over_an_empty_dict(self):
        settings = {aio_scenes.SETTINGS_KEY: {}}
        self.assertTrue(aio_scenes.seed(settings))
        self.assertEqual(len(settings[aio_scenes.SETTINGS_KEY]), 18)

    def test_seed_is_a_copy(self):
        settings = {}
        aio_scenes.seed(settings)
        settings[aio_scenes.SETTINGS_KEY]["1"]["color"] = "mutated"
        self.assertNotEqual(aio_scenes.DEFAULT_SCENES["1"]["color"], "mutated")


class TestSummarise(unittest.TestCase):
    def test_shows_colour_and_lcd(self):
        self.assertEqual(aio_scenes.summarise({"color": "red", "lcd": "dashboard"}),
                         "red / dashboard")

    def test_path_shows_basename_only(self):
        out = aio_scenes.summarise({"color": "red", "lcd": "/a/b/spin.gif"})
        self.assertEqual(out, "red / spin.gif")

    def test_nulls_render_as_dashes(self):
        self.assertEqual(aio_scenes.summarise({"color": None, "lcd": None}), "— / —")


if __name__ == "__main__":
    unittest.main()


class TestShortcutLabels(unittest.TestCase):
    """025: the Scenes menu documents the bindings, so it must not drift.

    The menu label and the registered key come from the same function; these
    guard that they stay that way.
    """

    def setUp(self):
        import scene_shortcuts
        self.S = scene_shortcuts

    def test_every_slot_has_a_key(self):
        for slot in self.S.all_slots():
            with self.subTest(slot=slot):
                self.assertTrue(self.S.pretty_key(slot))

    def test_colour_bank_is_unshifted(self):
        for slot in range(aio_scenes.SLOT_MIN, aio_scenes.SLOT_MAX + 1):
            with self.subTest(slot=slot):
                self.assertNotIn("Shift", self.S.pretty_key(slot))

    def test_animation_bank_is_shifted(self):
        for slot in range(aio_scenes.ANIM_MIN, aio_scenes.ANIM_MAX + 1):
            with self.subTest(slot=slot):
                self.assertIn("Shift", self.S.pretty_key(slot))

    def test_numpad_digit_matches_the_slot_within_its_bank(self):
        """Shift+Num 1 must be slot 11, not slot 1 with a stray modifier."""
        self.assertTrue(self.S.pretty_key(11).endswith("Num 1"))
        self.assertTrue(self.S.pretty_key(19).endswith("Num 9"))
        self.assertTrue(self.S.pretty_key(1).endswith("Num 1"))

    def test_pretty_key_matches_the_registered_binding(self):
        for slot in self.S.all_slots():
            with self.subTest(slot=slot):
                self.assertEqual(self.S.pretty_key(slot).replace("Num ", "Num+"),
                                 self.S._key_for(slot))

    def test_every_slot_appears_in_the_generated_script(self):
        js = self.S.build_js()
        for slot in self.S.all_slots():
            with self.subTest(slot=slot):
                self.assertIn(self.S._key_for(slot), js)
