## Validation Report: Proton Save Paths + Cheat Engine Setup
**Date**: 2026-08-15 23:00
**Spec**: specs/004-proton-save-paths.md
**Status**: PASSED

### Phase 3: Tests
- Test suite: `QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m pytest tests/ -q`
- Results: 66 passed, 0 failed (1.62s); 9 new in tests/test_paths.py
- Path tests use a simulated Steam library and prefix, so they pass regardless
  of whether this machine has switched to the Windows build yet
- Manual: `megabonker list` reports the native root with its origin label and
  still decrypts both save files
- Shell: `bash -n` on both new scripts; symlinks resolve
- Status: ✓ PASSED

### Phase 4: Code Quality
- Dead code: none; `steam_library_roots()` extracted from `find_game_dir()`
  and now has two callers
- Duplication: removed - library enumeration existed only inside find_game_dir
- Encapsulation: path policy in savefile, Steam layout knowledge in derive
- Backwards compatibility: `SAVE_ROOT` kept as an alias; `find_profiles()`
  still accepts an explicit root
- Linters: ruff (F,E9) clean; flake8 --max-line-length=100 clean
- Status: ✓ PASSED

### Phase 5: Security Review
- Dependencies: unchanged
- Secrets: none
- New reads: libraryfolders.vdf (already parsed for key derivation) and
  compatdata directory probing - existence checks only
- The setup script runs a user-supplied installer under Proton via protontricks.
  This is the established pattern for the four existing CE installs on this
  machine; the installer path is a fixed local file, not fetched at runtime
- No new network access, no elevated privileges
- Status: ✓ PASSED

### Phase 5.5: Release Safety
- Change type: additive discovery plus new standalone scripts
- Rollback plan: `git revert`; the scripts are symlinks that can be removed
- Blast radius: the editor now looks in more places, which cannot break the
  existing path. The build switch itself is a Steam UI action the user performs,
  and is reversible by unticking the compatibility override
- Saves backed up to ~/.local/share/megabonker/backups before any of this
- Status: ✓ PASSED

### Overall
- All gates passed: YES
- Notes: DPI values were read from the existing prefixes rather than assumed -
  they vary (Last Epoch 125%, Vampire Survivors 150%, Brotato and DRG 200%), so
  the setup script exposes DPI_HEX rather than hardcoding one answer.
