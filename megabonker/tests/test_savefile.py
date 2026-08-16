#!/usr/bin/env python3
"""Tests for loading and writing save files.

Everything here works on copies in a temp directory; the installed saves are
only ever read. See specs/001-save-editor.md.
"""

import json
import os
import shutil
import tempfile
import unittest

from megabonker.crypto import try_decrypt
from megabonker.savefile import ENCRYPTED_NAMES, SaveError, SaveFile, find_profiles


class TestSaveFile(unittest.TestCase):
    def setUp(self):
        profiles = find_profiles()
        if not profiles:
            self.skipTest("no Megabonk save profiles installed")
        source = os.path.join(profiles[0][1], "progression.json")
        if not os.path.exists(source):
            self.skipTest("progression.json not present")
        self.tmp = tempfile.mkdtemp(prefix="megabonker-test-")
        self.path = os.path.join(self.tmp, "progression.json")
        shutil.copy2(source, self.path)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_load_decrypts_into_dict(self):
        save = SaveFile(self.path)
        save.load()
        self.assertIsInstance(save.data, dict)
        self.assertIsNotNone(save.key)

    def test_edit_and_save_persists_value(self):
        """An edited value survives a write/reload cycle."""
        save = SaveFile(self.path)
        save.load()
        original = save.data.get("gold", 0)
        save.data["gold"] = original + 1234
        save.save(make_backup=False)

        reloaded = SaveFile(self.path)
        reloaded.load()
        self.assertEqual(reloaded.data["gold"], original + 1234)

    def test_save_output_is_readable_by_the_game_format(self):
        """What we write back decrypts to valid JSON with the same key."""
        save = SaveFile(self.path)
        save.load()
        save.data["gold"] = 42
        save.save(make_backup=False)
        plaintext, _ = try_decrypt(open(self.path, "rb").read())
        self.assertEqual(json.loads(plaintext)["gold"], 42)

    def test_backup_is_created_and_matches_pre_edit_content(self):
        """The backup holds the bytes that were on disk before the write."""
        before = open(self.path, "rb").read()
        save = SaveFile(self.path)
        save.load()
        save.data["gold"] = 99
        backup = save.save(make_backup=True)
        self.assertTrue(os.path.exists(backup))
        self.assertEqual(open(backup, "rb").read(), before)

    def test_unwritable_target_raises_saveerror(self):
        """A failed write surfaces as SaveError, not a bare OSError."""
        save = SaveFile(self.path)
        save.load()
        os.chmod(self.tmp, 0o500)
        try:
            with self.assertRaises(SaveError):
                save.save(make_backup=False)
        finally:
            os.chmod(self.tmp, 0o700)

    def test_corrupt_file_reports_saveerror(self):
        """Garbage in place of a save is reported rather than crashing."""
        with open(self.path, "wb") as f:
            f.write(b"not base64 at all !!!")
        save = SaveFile(self.path)
        with self.assertRaises(SaveError):
            save.load()


class TestDiscovery(unittest.TestCase):
    def test_find_profiles_returns_dirs_with_saves(self):
        for steamid, path in find_profiles():
            self.assertTrue(os.path.isdir(path))
            self.assertTrue(
                any(os.path.exists(os.path.join(path, n)) for n in ENCRYPTED_NAMES)
            )


if __name__ == "__main__":
    unittest.main()
