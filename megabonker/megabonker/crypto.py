"""Megabonk save-file encryption.

Format:  base64( AES-256-CBC( PKCS7( UTF-8 JSON ) ) )

The IV is a hardcoded constant rather than a per-file random value, so the
transform is deterministic: re-encrypting unmodified plaintext reproduces the
original file byte for byte. round_trip_ok() relies on that and is used as a
safety check before anything is written back to disk.
"""

import base64
import binascii
import json

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

from megabonker.keys import SaveKey, load_keyring


class DecryptError(Exception):
    """Raised when a save file cannot be decrypted with any available key."""


def decrypt(blob: bytes, sk: SaveKey) -> bytes:
    """Decrypt a base64 save blob to raw UTF-8 JSON bytes."""
    ciphertext = base64.b64decode(blob, validate=True)
    if len(ciphertext) == 0 or len(ciphertext) % 16 != 0:
        raise DecryptError(f"ciphertext is {len(ciphertext)} bytes, not a multiple of 16")
    decryptor = Cipher(algorithms.AES(sk.key_bytes), modes.CBC(sk.iv_bytes)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def encrypt(plaintext: bytes, sk: SaveKey) -> bytes:
    """Encrypt raw JSON bytes back into the base64 form the game reads."""
    padder = PKCS7(128).padder()
    encryptor = Cipher(algorithms.AES(sk.key_bytes), modes.CBC(sk.iv_bytes)).encryptor()
    padded = padder.update(plaintext) + padder.finalize()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(ciphertext)


def try_decrypt(blob: bytes, keyring: list[SaveKey] | None = None) -> tuple[bytes, SaveKey]:
    """Decrypt with the first key that yields valid JSON.

    Returns (plaintext, key_used). Raises DecryptError if no key works, which in
    practice means the game updated and the key must be re-derived.
    """
    keyring = keyring if keyring is not None else load_keyring()
    if not keyring:
        raise DecryptError("no keys available")
    for sk in keyring:
        try:
            plaintext = decrypt(blob, sk)
            json.loads(plaintext)
        except (ValueError, binascii.Error, DecryptError):
            continue
        return plaintext, sk
    raise DecryptError(
        f"none of the {len(keyring)} known keys decrypt this file - the game "
        f"has probably updated. Re-derive with: megabonker derive-key"
    )


def round_trip_ok(original_blob: bytes, plaintext: bytes, sk: SaveKey) -> bool:
    """True if re-encrypting untouched plaintext reproduces the original bytes.

    A False here means our understanding of the format is incomplete for this
    file, and writing it back would corrupt the save.
    """
    try:
        return encrypt(plaintext, sk).strip() == original_blob.strip()
    except Exception:
        return False
