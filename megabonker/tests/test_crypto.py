#!/usr/bin/env python3
"""Contract tests for the save encryption layer.

See specs/001-save-editor.md.
"""

import json
import os
import unittest

from megabonker.crypto import (DecryptError, decrypt, encrypt, round_trip_ok,
                               try_decrypt)
from megabonker.keys import KNOWN_KEYS, SaveKey
from megabonker.savefile import ENCRYPTED_NAMES, find_profiles

KEY = KNOWN_KEYS[0]


class TestCrypto(unittest.TestCase):
    """Encrypt/decrypt must be exact inverses, including padding."""

    def test_round_trip_arbitrary_json(self):
        """Any JSON survives encrypt->decrypt unchanged."""
        payload = json.dumps({"gold": 1, "nested": {"a": [1, 2, 3]}}).encode()
        self.assertEqual(decrypt(encrypt(payload, KEY), KEY), payload)

    def test_round_trip_at_block_boundary(self):
        """A plaintext that is an exact multiple of 16 still round-trips.

        PKCS7 appends a whole extra block in that case; getting it wrong here is
        the classic off-by-one that corrupts saves.
        """
        payload = b"x" * 32
        self.assertEqual(decrypt(encrypt(payload, KEY), KEY), payload)

    def test_encryption_is_deterministic(self):
        """The hardcoded IV means identical plaintext yields identical output."""
        payload = b'{"gold": 5}'
        self.assertEqual(encrypt(payload, KEY), encrypt(payload, KEY))

    def test_wrong_key_does_not_decrypt(self):
        """A bad key must fail loudly, not return garbage."""
        wrong = SaveKey(key="00" * 32, iv=KEY.iv, label="wrong")
        blob = encrypt(b'{"gold": 5}', KEY)
        with self.assertRaises(Exception):
            decrypt(blob, wrong)

    def test_try_decrypt_reports_when_no_key_works(self):
        """An unopenable file raises DecryptError naming the recovery path."""
        wrong = SaveKey(key="00" * 32, iv="11" * 16, label="wrong")
        blob = encrypt(b'{"gold": 5}', KEY)
        with self.assertRaises(DecryptError) as ctx:
            try_decrypt(blob, [wrong])
        self.assertIn("derive-key", str(ctx.exception))

    def test_non_block_aligned_ciphertext_rejected(self):
        """Truncated input is reported rather than crashing the cipher."""
        import base64
        with self.assertRaises(DecryptError):
            decrypt(base64.b64encode(b"short"), KEY)


class TestRealSaves(unittest.TestCase):
    """Exercise the real installed save files, read-only."""

    def setUp(self):
        profiles = find_profiles()
        if not profiles:
            self.skipTest("no Megabonk save profiles installed")
        self.profile = profiles[0][1]

    def test_installed_saves_decrypt_to_json(self):
        """Every shipped encrypted save opens with a known key."""
        checked = 0
        for name in ENCRYPTED_NAMES:
            path = os.path.join(self.profile, name)
            if not os.path.exists(path):
                continue
            plaintext, _ = try_decrypt(open(path, "rb").read())
            self.assertIsInstance(json.loads(plaintext), dict)
            checked += 1
        self.assertGreater(checked, 0, "no encrypted saves found to check")

    def test_installed_saves_round_trip_byte_identical(self):
        """Re-encrypting an untouched save reproduces the original bytes.

        This is the safety property the editor relies on before writing.
        """
        for name in ENCRYPTED_NAMES:
            path = os.path.join(self.profile, name)
            if not os.path.exists(path):
                continue
            raw = open(path, "rb").read()
            plaintext, key = try_decrypt(raw)
            self.assertTrue(round_trip_ok(raw, plaintext, key), f"{name} did not round-trip")


if __name__ == "__main__":
    unittest.main()
