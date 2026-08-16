# Spec 003: Edit Safety and Identifier Validation

**Status**: COMPLETE
**Implementation Date**: 2026-08-15

> **Note**: This work has no associated issue tracker ticket. It is a personal
> utility in a script monorepo.

## Overview

Three failures surfaced while using megabonker to reverse-engineer Megabonk's
unlock system. Each is addressed here.

1. **Stale buffer.** The editor was left open across a play session. It still
   held the pre-session save, and its Save button would have written that back,
   silently reverting a character unlock, a weapon, and 3,430 silver. The editor
   serialises its whole in-memory document, so a stale write is a full revert.
2. **False-positive game detection.** `game_is_running()` used
   `pgrep -f "Megabonk"`, which matches any process whose *command line*
   mentions the game - including a shell running the check itself. It reported
   the game as running when it was not.
3. **Silently wrong identifiers.** `SniperRifle` was added to `purchases` when
   the game's actual id is `Sniper`. The game persists unrecognised ids and
   ignores them forever, so a typo is indistinguishable from "editing this field
   does not work". This produced a false negative that misdirected two rounds of
   investigation.

## Requirements

### Functional

1. Detect the save file changing on disk after it was loaded.
2. While stale, block saving and explain why, offering Reload or Keep mine.
3. Keep mine must require explicit confirmation naming what would be lost.
4. Re-baseline after the editor's own writes, so saving never self-triggers.
5. Detect the game by executable, not command line.
6. Warn when Steam is running, since CloudDir is cloud-synced.
7. Flag identifiers the user adds that the game does not appear to recognise.
8. Never flag identifiers the game itself wrote.
9. Warn before saving edits that add achievement ids, which reach Steam.

### Technical

10. Vocabulary is the union of `global-metadata.dat` string literals and Steam's
    cached achievement schema.
11. Validation is advisory and never blocks a save.
12. Staleness polling must not block the UI.

## Implementation Details

- `savefile.py` - `SaveFile.original` snapshot and `.mtime`; `is_stale()`;
  re-baselining in `save()`; `game_is_running()` rewritten to `pgrep -x` plus a
  `/proc/*/exe` fallback scoped to the install directory.
- `gamedata.py` - `known_ids()` unions metadata literals with Steam schema ids,
  cached per game directory; `steam_is_running()`.
- `validate.py` - `added_entries()`, `unknown_additions()`, `describe()`,
  `touches_steam_achievements()`.
- `gui/json_editor.py` - `mark_suspects()` highlights offending leaves, leaving
  container rows styled as they were.
- `gui/main_window.py` - stale banner with Reload / Keep mine, a 2 s
  `QTimer` watchdog, save blocked while stale, validation in the status line,
  and a Steam-achievement confirmation on save.

**Why only additions are validated**: the game writes ids absent from every
vocabulary we can harvest - composite ones like `SantaHat_hat`, internal-only
achievements like `a_skin_foxKills`. Validating the whole file flags 12 entries
on an untouched save, which trains the user to ignore the warning. Validating
only what this session added flags zero on an untouched save and still catches
the real mistake.

## Acceptance Criteria

- [x] A freshly loaded save is not stale
- [x] An external write marks it stale
- [x] The editor's own save does not mark it stale
- [x] A deleted file is not reported as stale
- [x] `original` does not alias `data`
- [x] Stale state shows a banner naming the affected files
- [x] Save is blocked while stale
- [x] Keep mine re-baselines and re-enables saving
- [x] Game detection matches the executable, not the command line
- [x] The editor's own interpreter cannot match the install marker
- [x] Steam running is reported in the status line
- [x] A mistyped added id is flagged and highlighted red
- [x] A correct added id is not flagged
- [x] An untouched save produces no warnings
- [x] No vocabulary available means no warnings, not universal warnings
- [x] Reordering a list is not treated as an addition
- [x] Achievement additions trigger the Steam-profile warning
- [x] Non-achievement edits do not trigger it

## Testing

`tests/test_safety.py` - 20 tests covering staleness, process detection and
validation. Full suite: 57 tests passing. Verified end to end against the live
save with the GUI offscreen: a novel mistyped id is flagged and marked red, the
correct id clears it, an external write raises the banner and disables saving,
and Keep mine restores it.

## Notes

The Steam-achievement warning is not hypothetical. Adding `a_sniperRifle` to the
local list during the unlock investigation resulted in that achievement
appearing on the user's Steam profile without being earned.
