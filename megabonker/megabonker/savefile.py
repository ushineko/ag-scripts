"""Locating, loading and safely writing back Megabonk save files.

Layout under ~/.config/unity3d/Ved/Megabonk/Saves:

    CloudDir/<steamid64>/progression.json   encrypted, Steam Cloud synced
    CloudDir/<steamid64>/stats.json         encrypted, Steam Cloud synced
    LocalDir/config.json                    plain JSON, local only

Only the CloudDir pair is encrypted; this module handles both and records which
is which so the GUI can present them uniformly.
"""

import copy
import json
import os
import shutil
import subprocess
import time

from megabonker.crypto import DecryptError, encrypt, round_trip_ok, try_decrypt
from megabonker.keys import SaveKey

SAVE_ROOT = os.path.expanduser("~/.config/unity3d/Ved/Megabonk/Saves")
ENCRYPTED_NAMES = ("progression.json", "stats.json")
PLAIN_NAMES = ("config.json",)


class SaveError(Exception):
    """Raised when a save file cannot be loaded or written."""


def find_profiles(save_root: str = SAVE_ROOT) -> list[tuple[str, str]]:
    """Return (steamid, directory) for every CloudDir profile present."""
    cloud = os.path.join(save_root, "CloudDir")
    if not os.path.isdir(cloud):
        return []
    profiles = []
    for entry in sorted(os.listdir(cloud)):
        path = os.path.join(cloud, entry)
        if os.path.isdir(path) and any(
            os.path.exists(os.path.join(path, n)) for n in ENCRYPTED_NAMES
        ):
            profiles.append((entry, path))
    return profiles


GAME_PROCESS = "Megabonk.x86_64"
GAME_INSTALL_MARKER = os.path.join("common", "Megabonk")


def game_is_running() -> bool:
    """True if a Megabonk process is live.

    Editing underneath a running game is pointless - it holds state in memory
    and overwrites on exit - so callers warn before proceeding.

    Matches the executable, not a command line. An earlier `pgrep -f Megabonk`
    matched any process merely *mentioning* the game - a shell running a check,
    a launcher passing the install path - and reported the game as running when
    it was not.
    """
    try:
        if subprocess.run(["pgrep", "-x", GAME_PROCESS],
                          capture_output=True).returncode == 0:
            return True
    except FileNotFoundError:
        pass
    return _proc_exe_in_install_dir()


def _proc_exe_in_install_dir() -> bool:
    """Fallback: any process whose executable lives in the game install dir.

    Catches a renamed or differently-packaged binary that `pgrep -x` misses.
    """
    try:
        pids = [p for p in os.listdir("/proc") if p.isdigit()]
    except OSError:
        return False
    for pid in pids:
        try:
            exe = os.readlink(f"/proc/{pid}/exe")
        except OSError:
            continue
        if GAME_INSTALL_MARKER in exe:
            return True
    return False


class SaveFile:
    """One save file, decrypted into an editable dict."""

    def __init__(self, path: str):
        self.path = path
        self.name = os.path.basename(path)
        self.encrypted = self.name in ENCRYPTED_NAMES
        self.raw: bytes = b""
        self.plaintext: bytes = b""
        self.data: dict = {}
        self.key: SaveKey | None = None
        # Snapshot of what was on disk, for staleness detection and for telling
        # user-added ids apart from the game's own.
        self.original: dict = {}
        self.mtime: float | None = None

    def disk_mtime(self) -> float | None:
        try:
            return os.path.getmtime(self.path)
        except OSError:
            return None

    def is_stale(self) -> bool:
        """True if the file changed on disk since we loaded it.

        Writing a stale buffer silently reverts whatever happened in between -
        a play session's worth of progress, currency and unlocks - because the
        editor serialises its whole in-memory document, not a delta.
        """
        if self.mtime is None:
            return False
        current = self.disk_mtime()
        return current is not None and current > self.mtime

    def load(self, keyring: list[SaveKey] | None = None):
        """Read and decrypt the file, leaving JSON in self.data."""
        try:
            self.raw = open(self.path, "rb").read()
        except OSError as e:
            raise SaveError(f"cannot read {self.path}: {e}") from e
        if self.encrypted:
            try:
                self.plaintext, self.key = try_decrypt(self.raw, keyring)
            except DecryptError as e:
                raise SaveError(str(e)) from e
            if not round_trip_ok(self.raw, self.plaintext, self.key):
                raise SaveError(
                    f"{self.name} does not round-trip: re-encrypting the untouched "
                    f"contents does not reproduce the original file, so writing it "
                    f"back is unsafe. Refusing to edit this file."
                )
        else:
            self.plaintext = self.raw
        try:
            self.data = json.loads(self.plaintext)
        except ValueError as e:
            raise SaveError(f"{self.name} did not contain valid JSON: {e}") from e
        self.original = copy.deepcopy(self.data)
        self.mtime = self.disk_mtime()

    def dumps(self) -> bytes:
        """Serialise self.data the way the game writes it (2-space indent)."""
        return json.dumps(self.data, indent=2).encode("utf-8")

    def backup(self) -> str:
        """Copy the current on-disk file to a timestamped sibling."""
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = f"{self.path}.megabonker-{stamp}.bak"
        shutil.copy2(self.path, target)
        return target

    def save(self, make_backup: bool = True) -> str | None:
        """Write self.data back, re-encrypting when required.

        Returns the backup path if one was made. Writes to a temporary file and
        renames, so an interrupted write cannot truncate the save.
        """
        payload = self.dumps()
        if self.encrypted:
            if not self.key:
                raise SaveError("no key available to re-encrypt with")
            payload = encrypt(payload, self.key)
        backup_path = self.backup() if make_backup else None
        tmp = f"{self.path}.megabonker-tmp"
        try:
            with open(tmp, "wb") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except OSError as e:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise SaveError(f"cannot write {self.path}: {e}") from e
        self.raw = payload
        self.original = copy.deepcopy(self.data)
        self.mtime = self.disk_mtime()
        return backup_path
