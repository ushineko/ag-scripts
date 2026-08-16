#!/usr/bin/env python3
"""Tests for key recovery.

The oracle tests are self-contained: they build ciphertext with a key of our
choosing and check the search finds it. The end-to-end test needs the game
installed and is skipped otherwise. See specs/002-key-recovery.md.
"""

import json
import os
import unittest

from megabonker.crypto import encrypt
from megabonker.derive import (derive, find_game_dir, load_metadata_blobs,
                               key_fits, recover_iv)
from megabonker.keys import KNOWN_KEYS, SaveKey
from megabonker.savefile import ENCRYPTED_NAMES, find_profiles

KEY = KNOWN_KEYS[0]


class TestOracle(unittest.TestCase):
    """key_fits must accept the real key and reject everything else."""

    def setUp(self):
        blobs = [
            encrypt(json.dumps({"gold": 1, "pad": "x" * 200}).encode(), KEY),
            encrypt(json.dumps({"stats": list(range(100))}).encode(), KEY),
        ]
        from megabonker.derive import _targets
        self.targets = _targets(blobs)

    def test_accepts_correct_key(self):
        self.assertTrue(key_fits(KEY.key_bytes, self.targets))

    def test_rejects_wrong_keys(self):
        """No near-miss key should pass the two-file padding oracle."""
        for i in range(64):
            wrong = bytes([i]) + KEY.key_bytes[1:]
            if wrong == KEY.key_bytes:
                continue
            self.assertFalse(key_fits(wrong, self.targets), f"accepted wrong key {i}")

    def test_rejects_bad_key_length(self):
        self.assertFalse(key_fits(b"tooshort", self.targets))


class TestDeriveEndToEnd(unittest.TestCase):
    """Recover the real key from the installed game."""

    def setUp(self):
        self.game_dir = find_game_dir()
        if not self.game_dir:
            self.skipTest("Megabonk is not installed")
        profiles = find_profiles()
        if not profiles:
            self.skipTest("no Megabonk save profiles installed")
        self.blobs = []
        for name in ENCRYPTED_NAMES:
            path = os.path.join(profiles[0][1], name)
            if os.path.exists(path):
                self.blobs.append(open(path, "rb").read())
        if not self.blobs:
            self.skipTest("no encrypted saves present")

    def test_finds_the_known_key_and_iv(self):
        """A blind search reproduces the key shipped in megabonker.keys."""
        result = derive(self.game_dir, self.blobs)
        self.assertIsNotNone(result, "derive found nothing")
        self.assertEqual(result.key.hex(), KEY.key)
        self.assertEqual(result.iv.hex(), KEY.iv)

    def test_recover_iv_given_the_key(self):
        """IV recovery works from the key plus the known '{' plaintext."""
        blobs = load_metadata_blobs(self.game_dir)
        found = recover_iv(KEY.key_bytes, self.blobs[0], blobs)
        self.assertIsNotNone(found)
        self.assertEqual(found[0].hex(), KEY.iv)

    def test_derived_key_actually_opens_the_saves(self):
        """The recovered pair is usable, not merely equal to a constant."""
        result = derive(self.game_dir, self.blobs)
        recovered = SaveKey(key=result.key.hex(), iv=result.iv.hex(), label="test")
        from megabonker.crypto import decrypt
        self.assertIsInstance(json.loads(decrypt(self.blobs[0], recovered)), dict)


if __name__ == "__main__":
    unittest.main()
