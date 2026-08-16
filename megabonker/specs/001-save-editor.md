# Spec 001: Megabonk Save Editor

**Status**: COMPLETE
**Implementation Date**: 2026-08-15

> **Note**: This work has no associated issue tracker ticket. It is a personal
> utility in a script monorepo.

## Overview

A PyQt6 editor for Megabonk save files. The encrypted saves
(`progression.json`, `stats.json`) are stored as
`base64(AES-256-CBC(PKCS7(JSON)))`; the editor decrypts them, presents the JSON
as an editable tree, and writes them back in a form the game accepts.

## Requirements

### Functional

1. Discover Megabonk save profiles under `~/.config/unity3d/Ved/Megabonk/Saves`.
2. Decrypt and open both encrypted saves plus the plain `LocalDir/config.json`.
3. Present each file as an editable tree with key, value and type columns.
4. Preserve the JSON type of every edited value; reject input that cannot be
   converted back to the original type.
5. Filter tree rows by key or value substring.
6. Track unsaved changes per file and write only modified files.
7. Take a timestamped backup before every write.
8. Warn before writing while Megabonk is running.
9. Provide a CLI for `list`, `decrypt` and `encrypt`.

### Technical

10. PyQt6 with fully scoped enums, matching ag-scripts house style.
11. System Python (`/usr/bin/python3`); no conda dependency.
12. Preferences persist to `~/.config/megabonker/config.json` via a
    `ConfigManager` mirroring `audio-source-switcher`.
13. Writes are atomic (temp file plus rename).
14. Refuse to open any file that does not survive a byte-exact round-trip.

## Implementation Details

- `crypto.py` — `encrypt`/`decrypt`/`try_decrypt`/`round_trip_ok`.
- `savefile.py` — `find_profiles`, `SaveFile` (load, backup, atomic save),
  `game_is_running`.
- `gui/json_editor.py` — `JsonTreeWidget`, bound to a live dict, with `coerce`
  handling the bool-is-a-subclass-of-int ordering trap.
- `gui/main_window.py` — profile combo, one `SaveTab` per file, dirty tracking.
- `cli.py` — argparse front end; no arguments launches the GUI.

## Acceptance Criteria

- [x] Profiles under the save root are discovered and listed
- [x] `progression.json` and `stats.json` decrypt to valid JSON
- [x] `LocalDir/config.json` opens as plain JSON alongside them
- [x] Editing a scalar writes back into the underlying dict
- [x] Edited ints stay ints; invalid input is rejected and the cell reverts
- [x] Nested object and array elements are editable
- [x] Container rows are not editable
- [x] Filtering hides non-matching rows and clearing restores them
- [x] Dirty files are marked and enable the save button
- [x] A write produces a backup matching the pre-edit bytes
- [x] Written files decrypt back to the edited values
- [x] An unwritable target raises `SaveError` rather than a bare `OSError`
- [x] A corrupt save is reported, not crashed on
- [x] Round-trip verification refuses unsafe files
- [x] CLI `list`, `decrypt` and `encrypt` work, and encrypt is byte-identical

## Testing

`tests/test_crypto.py`, `tests/test_savefile.py`, `tests/test_gui.py` —
37 tests total across this spec and spec 002, all passing. GUI tests run under
`QT_QPA_PLATFORM=offscreen`. File tests operate on temp copies; no test writes
to a real save.

## Notes

The fixed IV makes encryption deterministic, which is what allows the
round-trip check to be exact. Megabonk reports to leaderboards, so edited
progression may propagate there.
