"""Known Megabonk save-encryption keys, plus persistence for re-derived ones.

The key and IV are compile-time constants baked into the game's IL2CPP
metadata, so they are stable for a given build and may rotate when the game
updates. Keys recovered by megabonker.derive are appended to a user keyring at
~/.config/megabonker/keys.json so a re-derivation only has to happen once per
game build.

See docs/key-recovery.md for how these were obtained and how to redo it.
"""

import json
import os
from dataclasses import dataclass, asdict

KEYRING_PATH = os.path.expanduser("~/.config/megabonker/keys.json")


@dataclass(frozen=True)
class SaveKey:
    """An AES-256-CBC key/IV pair used for Megabonk save files."""

    key: str          # 64 hex chars (32 bytes)
    iv: str           # 32 hex chars (16 bytes)
    label: str        # human-readable provenance
    build: str = ""   # game build this was recovered from, if known

    @property
    def key_bytes(self) -> bytes:
        return bytes.fromhex(self.key)

    @property
    def iv_bytes(self) -> bytes:
        return bytes.fromhex(self.iv)


# Recovered 2026-08-15 from the Feb-2026 Linux build (appid 3405340) by
# brute-forcing byte-array initialisers in global-metadata.dat against a CBC
# last-block padding oracle. Key sits at fieldAndParameterDefaultValueData
# +195872, IV 104 bytes later at +195976.
KNOWN_KEYS = [
    SaveKey(
        key="d940840d5ae7c7907b092437bc0c5b44aaf70e273e12d0fb4da2b8c767cc911d",
        iv="37864ef15c24bc0acbc60e3978ef1f06",
        label="Megabonk Linux build 2026-02-24",
        build="2026-02-24",
    ),
]


def load_keyring() -> list[SaveKey]:
    """Return the built-in keys followed by any user-saved (re-derived) keys."""
    keys = list(KNOWN_KEYS)
    if not os.path.exists(KEYRING_PATH):
        return keys
    try:
        with open(KEYRING_PATH, "r") as f:
            for entry in json.load(f):
                candidate = SaveKey(**entry)
                if not any(k.key == candidate.key and k.iv == candidate.iv for k in keys):
                    keys.append(candidate)
    except Exception as e:
        print(f"Error loading keyring {KEYRING_PATH}: {e}")
    return keys


def save_key(new_key: SaveKey):
    """Append a re-derived key to the user keyring, ignoring exact duplicates."""
    os.makedirs(os.path.dirname(KEYRING_PATH), exist_ok=True)
    existing = []
    if os.path.exists(KEYRING_PATH):
        try:
            with open(KEYRING_PATH, "r") as f:
                existing = json.load(f)
        except Exception:
            existing = []
    if any(e.get("key") == new_key.key and e.get("iv") == new_key.iv for e in existing):
        return
    existing.append(asdict(new_key))
    with open(KEYRING_PATH, "w") as f:
        json.dump(existing, f, indent=4)
