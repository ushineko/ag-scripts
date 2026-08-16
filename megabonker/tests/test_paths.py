#!/usr/bin/env python3
"""Save-location discovery across the native Linux and Proton builds.

Megabonk ships a native Linux build, but forcing Proton (needed to run Windows
tooling such as Cheat Engine against it) swaps in the Windows depot and moves
the saves into the Wine prefix. The editor has to find both, and has to keep
them distinguishable while a migration is half-done.

See specs/004-proton-save-paths.md.
"""

import os
import shutil
import tempfile
import unittest

from megabonker import savefile
from megabonker.savefile import (ENCRYPTED_NAMES, PROTON_SAVE_RELPATH,
                                 find_profiles, local_dir_for, save_roots)

STEAMID = "76561197971075009"


def _make_save_tree(root: str):
    """Create a minimal CloudDir/LocalDir layout that looks like real saves."""
    profile = os.path.join(root, "CloudDir", STEAMID)
    os.makedirs(profile, exist_ok=True)
    os.makedirs(os.path.join(root, "LocalDir"), exist_ok=True)
    for name in ENCRYPTED_NAMES:
        with open(os.path.join(profile, name), "w") as f:
            f.write("stub")
    return profile


class TestSaveRoots(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="megabonker-paths-")
        self.native = os.path.join(self.tmp, "native", "Saves")
        self.library = os.path.join(self.tmp, "SteamLibrary")
        self.proton = os.path.join(self.library, "steamapps", "compatdata",
                                   "3405340", PROTON_SAVE_RELPATH)
        self._orig_native = savefile.NATIVE_SAVE_ROOT
        self._orig_roots = savefile.steam_library_roots

    def tearDown(self):
        savefile.NATIVE_SAVE_ROOT = self._orig_native
        savefile.steam_library_roots = self._orig_roots
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _patch(self, native=True, library=True):
        savefile.NATIVE_SAVE_ROOT = self.native if native else os.path.join(self.tmp, "absent")
        libs = [self.library] if library else []
        savefile.steam_library_roots = lambda: libs

    def test_native_only(self):
        _make_save_tree(self.native)
        self._patch()
        roots = save_roots()
        self.assertEqual([o for o, _ in roots], ["native"])

    def test_proton_only(self):
        """After switching to the Windows build the native tree may be gone."""
        _make_save_tree(self.proton)
        self._patch(native=False)
        roots = save_roots()
        self.assertEqual([o for o, _ in roots], ["proton"])
        self.assertEqual(find_profiles()[0][0], STEAMID)

    def test_both_roots_are_found_and_labelled(self):
        """Mid-migration both exist; the labels must tell them apart."""
        _make_save_tree(self.native)
        _make_save_tree(self.proton)
        self._patch()
        self.assertEqual([o for o, _ in save_roots()], ["native", "proton"])
        labels = [label for label, _ in find_profiles()]
        self.assertEqual(labels, [f"{STEAMID} (native)", f"{STEAMID} (proton)"])

    def test_single_root_label_is_unadorned(self):
        """A lone root should not clutter the label with an origin suffix."""
        _make_save_tree(self.native)
        self._patch(library=False)
        self.assertEqual(find_profiles()[0][0], STEAMID)

    def test_no_roots_yields_no_profiles(self):
        self._patch(native=False, library=False)
        self.assertEqual(save_roots(), [])
        self.assertEqual(find_profiles(), [])

    def test_explicit_root_overrides_discovery(self):
        _make_save_tree(self.native)
        _make_save_tree(self.proton)
        self._patch()
        self.assertEqual(len(find_profiles(save_root=self.native)), 1)

    def test_empty_profile_dir_is_ignored(self):
        """A CloudDir entry with no save files is not a profile."""
        os.makedirs(os.path.join(self.native, "CloudDir", "empty"), exist_ok=True)
        self._patch(library=False)
        self.assertEqual(find_profiles(), [])


class TestLocalDir(unittest.TestCase):
    def test_localdir_resolves_beside_its_own_clouddir(self):
        """A Proton profile must read the prefix's settings, not the native ones."""
        profile = "/some/root/Saves/CloudDir/76561197971075009"
        self.assertEqual(local_dir_for(profile), "/some/root/Saves/LocalDir")

    def test_proton_relpath_matches_unity_windows_layout(self):
        """Unity on Windows persists to AppData\\LocalLow\\<company>\\<product>."""
        self.assertIn(os.path.join("AppData", "LocalLow", "Ved", "Megabonk"),
                      PROTON_SAVE_RELPATH)
        self.assertTrue(PROTON_SAVE_RELPATH.startswith(os.path.join("pfx", "drive_c")))


if __name__ == "__main__":
    unittest.main()
