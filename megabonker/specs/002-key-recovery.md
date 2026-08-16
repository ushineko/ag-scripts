# Spec 002: Save Key Recovery

**Status**: COMPLETE
**Implementation Date**: 2026-08-15

> **Note**: This work has no associated issue tracker ticket. It is a personal
> utility in a script monorepo.

## Overview

Megabonk's AES-256 key and IV are compile-time constants in the game's IL2CPP
metadata. A game update can rotate them, at which point every stored key stops
working and no save will open. This spec covers recovering the pair from the
installed game files with no debugger and no running game, so the editor
survives updates.

## Requirements

### Functional

1. Locate the Megabonk install via Steam's library folders.
2. Search the game files for a key that decrypts the user's saves.
3. Recover the IV once the key is known.
4. Validate a candidate before offering it, by decrypting to real JSON.
5. Persist recovered keys to a user keyring so recovery happens once per build.
6. Expose recovery from both the CLI (`derive-key`) and the GUI.
7. Run the search off the GUI thread, with progress and cancellation.
8. Document the method well enough to redo by hand if the tool fails.

### Technical

9. Test candidate keys without knowing the IV, via the CBC last-block identity
   `P[n-1] = D_K(C[n-1]) XOR C[n-2]`.
10. Require a candidate to satisfy every supplied save file.
11. Pre-filter candidate windows on byte diversity so the common case is fast.
12. Refuse metadata format versions other than the tested one rather than
    searching wrong byte ranges.

## Implementation Details

- `derive.py` — metadata header parsing, `key_fits` oracle,
  `_entropy_filtered_windows` pre-filter, `recover_iv`, and the `derive` driver
  running three escalating phases (random-looking windows → string derivations
  → exhaustive).
- `keys.py` — `SaveKey`, the built-in `KNOWN_KEYS`, and keyring persistence.
- `gui/derive_dialog.py` — `DeriveWorker(QThread)` with progress and cancel.
- `docs/key-recovery.md` — format, method, and by-hand procedure.

The padding bytes are stripped before the printability test in
`_tail_looks_like_json`. An earlier fixed "14 of 16 printable" threshold passed
only by coincidence (a 9-byte PKCS7 pad is `0x09`, a tab) and would have
rejected the correct key for a different plaintext length.

## Acceptance Criteria

- [x] The Megabonk install is located automatically via Steam library folders
- [x] The oracle accepts the correct key
- [x] The oracle rejects 63 near-miss keys differing in one byte
- [x] The oracle rejects keys of invalid length
- [x] A blind search recovers the known key from the installed game
- [x] The IV is recovered from the key plus known `{` plaintext
- [x] The recovered pair actually decrypts the saves to JSON
- [x] Recovery completes in under a second on the current build
- [x] Recovered keys can be saved to and reloaded from the keyring
- [x] An untested metadata version raises `DeriveError` instead of searching
- [x] `derive-key` is available from the CLI with `--save` and `--exhaustive`
- [x] The GUI dialog runs the search off-thread and can be cancelled
- [x] `docs/key-recovery.md` documents format, method and manual fallback

## Testing

`tests/test_derive.py` — oracle unit tests using synthetic ciphertext built
with a known key, plus end-to-end recovery against the installed game (skipped
when absent). Measured recovery time: 0.89 s.

## Notes

If the game moves to a runtime-derived key, static recovery stops working and
process dumping would be required. That is out of scope and documented as such.
