"""Recover Megabonk's save key and IV from the game's own files.

Needed when the game updates and rotates its baked-in constants, at which point
every key in megabonker.keys stops working. The method needs nothing but an
encrypted save file and the game install directory - no debugger, no dumper.

How it works
------------
The key is a compile-time `byte[]` initialiser living in global-metadata.dat's
field/parameter default-value blob, so it never appears as a string and cannot
be found by inspection (the assembly is name-obfuscated too).

Two properties make a blind search cheap:

1. **The IV is not needed to test a key.** In CBC, the final plaintext block is
   D_K(C[n-1]) XOR C[n-2], and both of those ciphertext blocks are in the file.
   So a candidate key can be scored on whether it produces valid PKCS7 padding,
   with no knowledge of the IV. Requiring that across two independent save
   files makes a false positive vanishingly unlikely.

2. **Once the key is known, the IV falls out of known plaintext.** D_K(C[0]) is
   then a constant, and the plaintext starts with '{' (it is JSON), so the IV is
   whichever 16-byte window in the binary XORs that constant into printable
   text starting with a brace.

Candidate keys are pre-filtered on byte diversity: a real AES key looks random,
which rules out the overwhelming majority of windows before any AES is done.

See docs/key-recovery.md for the full write-up.
"""

import base64
import hashlib
import os
import struct
from dataclasses import dataclass

import numpy as np
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from megabonker.keys import SaveKey

# Offsets of the two length/offset pairs we need from the IL2CPP metadata
# header (format version 29). Each section is stored as (offset, size) int32s.
_HDR_STRING_LITERAL = 8
_HDR_STRING_LITERAL_DATA = 16
_HDR_STRING = 24
_HDR_DEFAULT_VALUE_DATA = 8 + 16 * 4

METADATA_RELPATH = os.path.join("Megabonk_Data", "il2cpp_data", "Metadata", "global-metadata.dat")


GAME_INSTALLDIR = "Megabonk"
APPID_DEFAULT = "3405340"

# Steam library roots to probe before falling back to libraryfolders.vdf.
_DEFAULT_STEAM_ROOTS = (
    "~/.steam/steam",
    "~/.local/share/Steam",
)


class DeriveError(Exception):
    """Raised when key recovery cannot proceed (bad paths, unknown metadata)."""


def find_game_dir() -> str | None:
    """Locate the Megabonk install by walking Steam's library folders."""
    roots = []
    for root in _DEFAULT_STEAM_ROOTS:
        expanded = os.path.expanduser(root)
        roots.append(expanded)
        vdf = os.path.join(expanded, "steamapps", "libraryfolders.vdf")
        if not os.path.exists(vdf):
            continue
        try:
            text = open(vdf, "r", errors="replace").read()
        except OSError:
            continue
        # Entries look like:  "path"   "/mnt/Data3/SteamLibrary"
        for line in text.splitlines():
            parts = [p for p in line.split('"') if p.strip()]
            if len(parts) >= 2 and parts[0].strip() == "path":
                roots.append(parts[1].strip())
    for root in roots:
        candidate = os.path.join(root, "steamapps", "common", GAME_INSTALLDIR)
        if os.path.isdir(os.path.join(candidate, "Megabonk_Data")):
            return candidate
    return None


@dataclass
class DeriveResult:
    """A recovered key/IV plus where each was found."""

    key: bytes
    iv: bytes
    key_location: str
    iv_location: str

    def to_save_key(self, build: str = "") -> SaveKey:
        return SaveKey(
            key=self.key.hex(),
            iv=self.iv.hex(),
            label=f"re-derived from {self.key_location}",
            build=build,
        )


# --------------------------------------------------------------------------
# metadata parsing
# --------------------------------------------------------------------------

def _read_pair(data: bytes, offset: int) -> tuple[int, int]:
    return struct.unpack_from("<ii", data, offset)


def load_metadata_blobs(game_dir: str) -> dict[str, bytes]:
    """Return the metadata sections worth searching, keyed by name."""
    path = os.path.join(game_dir, METADATA_RELPATH)
    if not os.path.exists(path):
        raise DeriveError(f"global-metadata.dat not found under {game_dir}")
    data = open(path, "rb").read()
    sanity, version = struct.unpack_from("<Ii", data, 0)
    if sanity != 0xFAB11BAF:
        raise DeriveError(f"bad metadata sanity 0x{sanity:08X} (expected 0xFAB11BAF)")
    if version != 29:
        # Section ordering has shifted between IL2CPP versions before; refuse
        # rather than search the wrong byte ranges and silently find nothing.
        raise DeriveError(
            f"metadata format version {version} is untested (expected 29). "
            f"Verify the header layout before trusting a search."
        )
    lit_off, lit_size = _read_pair(data, _HDR_STRING_LITERAL_DATA)
    dv_off, dv_size = _read_pair(data, _HDR_DEFAULT_VALUE_DATA)
    return {
        # Byte-array initialisers land here; this is where the key actually is.
        "defaultvalues": data[dv_off:dv_off + dv_size],
        "stringliterals": data[lit_off:lit_off + lit_size],
    }


def load_metadata_strings(game_dir: str) -> list[bytes]:
    """Return every string literal and identifier name in the metadata."""
    path = os.path.join(game_dir, METADATA_RELPATH)
    data = open(path, "rb").read()
    lit_tab_off, lit_tab_size = _read_pair(data, _HDR_STRING_LITERAL)
    lit_off, _ = _read_pair(data, _HDR_STRING_LITERAL_DATA)
    str_off, str_size = _read_pair(data, _HDR_STRING)
    out = set()
    for i in range(lit_tab_size // 8):
        length, index = struct.unpack_from("<II", data, lit_tab_off + i * 8)
        out.add(data[lit_off + index:lit_off + index + length])
    out.update(s for s in data[str_off:str_off + str_size].split(b"\x00") if s)
    return [s for s in out if 0 < len(s) <= 128]


# --------------------------------------------------------------------------
# the oracle
# --------------------------------------------------------------------------

def _targets(save_blobs: list[bytes]) -> list[tuple[bytes, bytes]]:
    """Reduce each save file to the (penultimate, final) ciphertext block pair."""
    targets = []
    for blob in save_blobs:
        ct = base64.b64decode(blob, validate=True)
        if len(ct) < 32 or len(ct) % 16:
            raise DeriveError("save file is not a whole number of AES blocks")
        targets.append((ct[-32:-16], ct[-16:]))
    return targets


def _tail_looks_like_json(block: bytes) -> bool:
    """True if a decrypted final block has valid PKCS7 over printable text.

    The padding bytes are stripped before the printability test rather than
    counted: PKCS7 values are 1..16, so with a large pad most of the block is
    legitimately non-printable and a fixed "N of 16 printable" threshold would
    reject the correct key depending only on how long the plaintext happened
    to be.
    """
    n = block[-1]
    if not (1 <= n <= 16 and block[-n:] == bytes([n]) * n):
        return False
    return all(32 <= b <= 126 or b in (9, 10, 13) for b in block[:-n])


def key_fits(key: bytes, targets: list[tuple[bytes, bytes]]) -> bool:
    """True if `key` decrypts the last block of every target sanely.

    Uses the IV-free CBC identity P[n-1] = D_K(C[n-1]) XOR C[n-2], so no IV is
    needed. Requiring this across two independent files makes a chance pass
    vanishingly unlikely.
    """
    if len(key) not in (16, 24, 32):
        return False
    algorithm = algorithms.AES(key)
    for prev, last in targets:
        decryptor = Cipher(algorithm, modes.ECB()).decryptor()
        raw = decryptor.update(last) + decryptor.finalize()
        plain = bytes(a ^ b for a, b in zip(raw, prev))
        if not _tail_looks_like_json(plain):
            return False
    return True


# --------------------------------------------------------------------------
# candidate generation
# --------------------------------------------------------------------------

def _random_looking(window: np.ndarray, min_distinct: int) -> bool:
    return len(np.unique(window)) >= min_distinct


def _entropy_filtered_windows(blob: bytes, size: int):
    """Yield (offset, window) for windows that plausibly hold a random key.

    An AES key is uniformly random, so it has near-maximal byte diversity. Real
    metadata is overwhelmingly ASCII names, zero padding and small integers, so
    this discards well over 99% of positions before any AES work happens.
    """
    if len(blob) < size:
        return
    arr = np.frombuffer(blob, dtype=np.uint8)
    min_distinct = int(size * 0.78)
    # Cheap vectorised pre-pass: a random window has few zero bytes.
    zero_run = np.convolve((arr == 0).astype(np.int16), np.ones(size, dtype=np.int16), mode="valid")
    for offset in np.nonzero(zero_run <= 2)[0]:
        window = arr[offset:offset + size]
        if _random_looking(window, min_distinct):
            yield int(offset), window.tobytes()


def _string_derivations(text: bytes):
    """Yield keys derived from a string the way game code commonly does."""
    for encoded in (text, text.decode("latin1", "ignore").encode("utf-16-le")):
        for candidate in (
            encoded[:16], encoded[:24], encoded[:32],
            hashlib.md5(encoded).digest(),
            hashlib.sha256(encoded).digest(),
            hashlib.sha256(encoded).digest()[:16],
            hashlib.sha1(encoded).digest()[:16],
        ):
            if len(candidate) in (16, 24, 32):
                yield candidate


# --------------------------------------------------------------------------
# IV recovery
# --------------------------------------------------------------------------

def recover_iv(key: bytes, save_blob: bytes, blobs: dict[str, bytes],
               first_char: bytes = b"{") -> tuple[bytes, str] | None:
    """Find the IV given a known key, using the JSON '{' as known plaintext.

    P[0] = D_K(C[0]) XOR IV, and D_K(C[0]) is a constant once the key is known,
    so the IV is any 16-byte window that turns it into printable text opening
    with a brace.
    """
    ciphertext = base64.b64decode(save_blob, validate=True)
    decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    constant = np.frombuffer(
        decryptor.update(ciphertext[:16]) + decryptor.finalize(), dtype=np.uint8
    )
    wanted_first = constant[0] ^ first_char[0]
    for name, blob in blobs.items():
        arr = np.frombuffer(blob, dtype=np.uint8)
        if len(arr) < 16:
            continue
        for offset in np.nonzero(arr[:len(arr) - 16] == wanted_first)[0]:
            plain = arr[offset:offset + 16] ^ constant
            printable = ((plain >= 32) & (plain <= 126)) | np.isin(plain, (9, 10, 13))
            if np.all(printable):
                return arr[offset:offset + 16].tobytes(), f"{name}+{offset}"
    return None


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------

def derive(game_dir: str, save_blobs: list[bytes], progress=None,
           should_cancel=None, exhaustive: bool = False) -> DeriveResult | None:
    """Search the game files for the key/IV that decrypt `save_blobs`.

    progress(stage, done, total) is called periodically for UI feedback, and
    should_cancel() may return True to abort. Supply at least two save files
    for a trustworthy result.
    """
    def report(stage, done, total):
        if progress:
            progress(stage, done, total)

    def cancelled() -> bool:
        return bool(should_cancel and should_cancel())

    targets = _targets(save_blobs)
    blobs = load_metadata_blobs(game_dir)

    # Phase 1: random-looking byte windows. This is where the key has actually
    # lived, so it runs first and normally finishes in seconds.
    for size in (32, 16):
        for name, blob in blobs.items():
            candidates = list(_entropy_filtered_windows(blob, size))
            stage = f"scanning {name} for {size}-byte keys"
            for i, (offset, window) in enumerate(candidates):
                if cancelled():
                    return None
                if i % 256 == 0:
                    report(stage, i, len(candidates))
                if key_fits(window, targets):
                    found = _finish(window, save_blobs[0], blobs, f"{name}+{offset}")
                    if found:
                        return found
            report(stage, len(candidates), len(candidates))

    # Phase 2: keys derived from strings (UTF-8/UTF-16 truncations and hashes).
    strings = load_metadata_strings(game_dir)
    stage = "deriving keys from metadata strings"
    for i, text in enumerate(strings):
        if cancelled():
            return None
        if i % 512 == 0:
            report(stage, i, len(strings))
        for candidate in _string_derivations(text):
            if key_fits(candidate, targets):
                found = _finish(candidate, save_blobs[0], blobs, f"string:{text[:40]!r}")
                if found:
                    return found
    report(stage, len(strings), len(strings))

    # Phase 3: every window, no diversity filter. Slow; opt-in only.
    if exhaustive:
        for size in (32, 16):
            for name, blob in blobs.items():
                stage = f"exhaustive {name} ({size}-byte)"
                total = max(len(blob) - size, 0)
                for offset in range(total):
                    if cancelled():
                        return None
                    if offset % 4096 == 0:
                        report(stage, offset, total)
                    if key_fits(blob[offset:offset + size], targets):
                        found = _finish(blob[offset:offset + size], save_blobs[0], blobs,
                                        f"{name}+{offset}")
                        if found:
                            return found
    return None


def _finish(key: bytes, save_blob: bytes, blobs: dict[str, bytes],
            key_location: str) -> DeriveResult | None:
    """Turn a validated key into a full result by locating its IV."""
    found = recover_iv(key, save_blob, blobs)
    if not found:
        return None
    iv, iv_location = found
    return DeriveResult(key=key, iv=iv, key_location=key_location, iv_location=iv_location)
