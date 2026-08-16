#!/usr/bin/env python3
"""Tests for the edit-safety layer: staleness detection, process detection and
identifier validation.

These cover three real failures hit while reverse-engineering Megabonk's saves:
a stale editor buffer that would have reverted a play session, a process check
that reported the game running when it was not, and a mistyped identifier that
the game silently ignored for two test cycles.

See specs/003-edit-safety.md.
"""

import json
import os
import shutil
import tempfile
import time
import unittest

from megabonker import savefile
from megabonker.savefile import SaveFile, find_profiles, game_is_running
from megabonker.validate import (added_entries, describe,
                                 touches_steam_achievements, unknown_additions)


class TestStaleness(unittest.TestCase):
    """A buffer must know when the file moved on underneath it."""

    def setUp(self):
        profiles = find_profiles()
        if not profiles:
            self.skipTest("no Megabonk save profiles installed")
        source = os.path.join(profiles[0][1], "progression.json")
        if not os.path.exists(source):
            self.skipTest("progression.json not present")
        self.tmp = tempfile.mkdtemp(prefix="megabonker-stale-")
        self.path = os.path.join(self.tmp, "progression.json")
        shutil.copy2(source, self.path)
        self.save = SaveFile(self.path)
        self.save.load()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_freshly_loaded_is_not_stale(self):
        self.assertFalse(self.save.is_stale())

    def test_external_write_marks_stale(self):
        """A newer mtime means someone else - the game - wrote the file."""
        os.utime(self.path, (time.time() + 10, time.time() + 10))
        self.assertTrue(self.save.is_stale())

    def test_our_own_save_does_not_look_stale(self):
        """Writing through SaveFile re-baselines, so it must not self-trigger."""
        self.save.data["gold"] = 5
        self.save.save(make_backup=False)
        self.assertFalse(self.save.is_stale())

    def test_missing_file_is_not_reported_stale(self):
        """A deleted file is a different error; don't confuse it with staleness."""
        os.unlink(self.path)
        self.assertFalse(self.save.is_stale())

    def test_original_snapshot_is_independent_of_edits(self):
        """`original` must not alias `data`, or addition diffing breaks."""
        before = list(self.save.original["purchases"])
        self.save.data["purchases"].append("SomethingNew")
        self.assertEqual(self.save.original["purchases"], before)


class TestGameDetection(unittest.TestCase):
    def test_matches_executable_not_command_line(self):
        """The old `pgrep -f Megabonk` matched any process merely naming it.

        Regression: a shell whose command line contained the game path made the
        editor believe the game was running.
        """
        self.assertEqual(savefile.GAME_PROCESS, "Megabonk.x86_64")

    def test_returns_bool_and_does_not_raise(self):
        self.assertIsInstance(game_is_running(), bool)

    def test_our_own_interpreter_does_not_match_the_install_marker(self):
        """The fallback keys off the executable path, so ours must not match.

        This is what makes the check immune to the old false positive: a Python
        process running editor code lives nowhere near the game's install dir,
        no matter what its command line mentions.
        """
        import sys
        self.assertNotIn(savefile.GAME_INSTALL_MARKER, os.path.realpath(sys.executable))

    def test_proc_scan_returns_bool(self):
        self.assertIsInstance(savefile._proc_exe_in_install_dir(), bool)


class TestValidation(unittest.TestCase):
    """Only user-added ids get checked, and the check must be precise."""

    def setUp(self):
        self.original = {
            "purchases": ["Sniper", "SantaHat_hat", "FoxIceFox"],
            "achievements": ["a_bush", "a_skin_foxKills"],
            "claimedAchievements": ["a_bush"],
            "inactivated": [],
        }
        self.known = {"Sniper", "Bush", "Amog", "a_bush", "a_sniperRifle"}

    def test_untouched_save_produces_no_warnings(self):
        """Game-written ids we cannot verify must never be flagged."""
        current = json.loads(json.dumps(self.original))
        self.assertEqual(unknown_additions(self.original, current, self.known), {})

    def test_flags_a_mistyped_id(self):
        """The exact mistake made in practice: SniperRifle instead of Sniper."""
        current = json.loads(json.dumps(self.original))
        current["purchases"].append("SniperRifle")
        self.assertEqual(unknown_additions(self.original, current, self.known),
                         {"purchases": ["SniperRifle"]})

    def test_accepts_a_correct_id(self):
        current = json.loads(json.dumps(self.original))
        current["purchases"].append("Bush")
        self.assertEqual(unknown_additions(self.original, current, self.known), {})

    def test_reports_nothing_when_vocabulary_unavailable(self):
        """No game installed means no opinion, rather than flagging everything."""
        current = json.loads(json.dumps(self.original))
        current["purchases"].append("Whatever")
        self.assertEqual(unknown_additions(self.original, current, set()), {})

    def test_added_entries_ignores_reordering(self):
        current = json.loads(json.dumps(self.original))
        current["purchases"].reverse()
        self.assertEqual(added_entries(self.original, current), {})

    def test_describe_is_empty_when_clean(self):
        self.assertEqual(describe({}), "")

    def test_describe_names_the_field_and_value(self):
        text = describe({"purchases": ["SniperRifle"]})
        self.assertIn("purchases", text)
        self.assertIn("SniperRifle", text)

    def test_achievement_additions_are_detected(self):
        """Adding an achievement id can reach the user's Steam profile."""
        current = json.loads(json.dumps(self.original))
        current["achievements"].append("a_sniperRifle")
        self.assertTrue(touches_steam_achievements(self.original, current))

    def test_non_achievement_edits_do_not_trigger_the_steam_warning(self):
        current = json.loads(json.dumps(self.original))
        current["purchases"].append("Bush")
        self.assertFalse(touches_steam_achievements(self.original, current))


class TestVocabulary(unittest.TestCase):
    def test_known_ids_includes_real_game_identifiers(self):
        from megabonker.derive import find_game_dir
        from megabonker.gamedata import known_ids
        if not find_game_dir():
            self.skipTest("Megabonk is not installed")
        ids = known_ids()
        self.assertIn("Sniper", ids)
        self.assertNotIn("SniperRifle", ids)

    def test_steam_schema_contributes_achievement_ids(self):
        from megabonker.gamedata import steam_schema_path, known_ids
        if not steam_schema_path():
            self.skipTest("Steam achievement schema not cached locally")
        self.assertIn("a_sniperRifle", known_ids())


if __name__ == "__main__":
    unittest.main()
