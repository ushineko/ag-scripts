# Spec 004: Proton Save Paths

**Status**: COMPLETE
**Implementation Date**: 2026-08-15

> **Note**: This work has no associated issue tracker ticket. It is a personal
> utility in a script monorepo.

## Overview

Megabonk ships a native Linux build. Forcing Proton - required to run Cheat
Engine against the game - swaps in the Windows depot and moves the saves from
Unity's Linux path into the Wine prefix. The editor hardcoded the Linux path and
would have found nothing after the switch.

## Requirements

1. Discover saves in both the native Linux root and any Proton prefix.
2. Search every Steam library, since games and prefixes live on other drives.
3. Label profiles by origin when more than one root has saves.
4. Resolve `LocalDir` from the profile, not a global constant, so a Proton
   profile reads that prefix's settings file.
5. Report all roots in `megabonker list`.
6. Preserve the explicit-root argument for callers that pass one.

## Implementation Details

- `derive.steam_library_roots()` extracted from `find_game_dir()` and reused.
- `savefile.NATIVE_SAVE_ROOT` / `PROTON_SAVE_RELPATH`; `SAVE_ROOT` kept as an
  alias so existing callers and tests keep working.
- `savefile.save_roots()` returns `(origin, path)` pairs.
- `savefile.find_profiles()` searches all roots and suffixes labels with the
  origin only when disambiguation is needed.
- `savefile.local_dir_for()` derives LocalDir from a profile path.
- GUI and CLI updated to use them.

The Proton path is `pfx/drive_c/users/steamuser/AppData/LocalLow/Ved/Megabonk/
Saves`, matching Unity's Windows persistent-data layout - confirmed against the
Vampire Survivors (`poncle`) and DRG Survivor (`Funday Games`) prefixes.

## Acceptance Criteria

- [x] Native-only installs are found as before
- [x] A Proton-only install is found
- [x] Both roots are found when both exist
- [x] Labels carry the origin only when more than one root has saves
- [x] No roots yields no profiles rather than an error
- [x] An explicit `save_root` still overrides discovery
- [x] A CloudDir entry with no save files is not treated as a profile
- [x] `local_dir_for()` resolves beside the profile's own CloudDir
- [x] The Proton relpath matches Unity's Windows layout
- [x] `megabonker list` reports every root with its origin

## Testing

`tests/test_paths.py` - 9 tests using a simulated Steam library and prefix, so
they pass whether or not the machine has switched to the Windows build. Full
suite: 66 tests passing.

## Notes

Cheat Engine setup itself lives in dotfiles with the other CE launchers
(`ce-drg.sh`, `ce-lastepoch.sh`, `ce-vs.sh`, `ce-brotato.sh`) rather than here,
so it stows onto a new machine with everything else. The procedure is documented
in `docs/cheat-engine-setup.md`.
