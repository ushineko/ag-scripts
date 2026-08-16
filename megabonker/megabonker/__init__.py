"""Megabonker - Megabonk save editor and key-recovery toolkit.

Re-exports the pieces callers normally want so that:
    from megabonker import SaveFile, derive
works without reaching into submodules.
"""

from megabonker.config import ConfigManager  # noqa: F401
from megabonker.crypto import DecryptError, decrypt, encrypt, try_decrypt  # noqa: F401
from megabonker.derive import DeriveError, DeriveResult, derive, find_game_dir  # noqa: F401
from megabonker.keys import KNOWN_KEYS, SaveKey, load_keyring, save_key  # noqa: F401
from megabonker.savefile import SaveError, SaveFile, find_profiles  # noqa: F401

__version__ = "1.0.0"
