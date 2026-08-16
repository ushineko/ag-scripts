## Validation Report: Megabonker Initial Release
**Date**: 2026-08-15 21:30
**Spec**: specs/001-save-editor.md, specs/002-key-recovery.md
**Status**: PASSED

### Phase 3: Tests
- Test suite: `QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m pytest tests/ -q`
- Results: 37 passed, 0 failed, 0 skipped (1.48s)
- Coverage: crypto round-trip and padding edge cases, save load/write/backup,
  derive oracle (accept/reject), end-to-end key recovery against the installed
  game, JSON tree editing and type coercion
- Manual verification:
  - CLI `list`, `decrypt`, `encrypt` against real saves; encrypt output is
    byte-identical to the original file
  - `derive-key` recovers the known key and IV blind in 0.89s
  - GUI offscreen smoke test: 3 tabs load (progression, stats, config), edit
    marks the tab dirty and enables save
  - Real save files confirmed unmodified after all testing (sizes unchanged)
- Status: ✓ PASSED

### Phase 4: Code Quality
- Dead code: removed unused `APPID` constant and two unused imports in `cli.py`
  (`SaveFile`, `game_is_running`), found by ruff F401
- Duplication: none significant; `ConfigManager` intentionally mirrors
  `audio-source-switcher` house pattern rather than sharing code across
  independent sub-projects
- Encapsulation: crypto / key storage / file I/O / derivation / GUI are separate
  modules; no module exceeds ~360 lines and no method exceeds 50
- Overcomplication check: the three-phase escalating search in `derive.py` is
  justified — phase 1 covers the observed case in 0.9s, phases 2 and 3 exist
  because the key form can change between builds
- Refactorings: two over-long lines split; `_mostly_printable` replaced by
  `_tail_looks_like_json`
- Linters: `ruff check --select F,E9` clean; `flake8 --max-line-length=100` clean
- Status: ✓ PASSED

### Phase 5: Security Review
- Dependencies: PyQt6 6.11.1, cryptography 49.0.0, numpy 2.5.1 — all distro
  packages from system Python; no new third-party dependency introduced, no
  requirements.txt pinning added, so no CVE scan of vendored deps applies
- Secrets: no credentials in source. The AES key and IV are committed
  deliberately — they are constants extracted from a locally installed game
  binary, are not access credentials, and are the entire point of the tool
- Input handling: all parsing is of local files the user already owns. Metadata
  parsing validates the sanity magic and format version before indexing, and
  refuses unknown versions rather than reading arbitrary offsets. Base64 uses
  `validate=True`; non-block-aligned ciphertext is rejected before reaching the
  cipher
- File writes: confined to the user's own save directory. Writes are atomic
  (temp + `os.replace`) with a timestamped backup taken first
- Subprocess use: `pgrep -f Megabonk` and `xdg-open <dir>` — both fixed argument
  lists, no shell, no user-controlled format strings
- OWASP relevance: no network, no auth, no serialisation of untrusted data
  (`json.loads` only), no injection surface
- Status: ✓ PASSED

### Phase 5.5: Release Safety
- Change type: new self-contained sub-project; no existing project touched
- Rollback plan: `git revert` the commit, or `./uninstall.sh`. The tool creates
  a timestamped `.bak` beside every save it writes, so any edit is reversible by
  copying the backup back
- Blast radius: local only. The one destructive capability is overwriting the
  user's own Megabonk saves, gated behind a backup, an atomic write, a
  round-trip safety check, and a warning when the game is running
- Rollout strategy: immediate; manual invocation only, no daemon or autostart
- Status: ✓ PASSED

### Overall
- All gates passed: YES
- Notes: Both specs reconciled — every acceptance criterion in
  `001-save-editor.md` and `002-key-recovery.md` verified and checked before
  marking COMPLETE. One real bug was caught by the test suite during
  development: the derivation oracle's printability check counted PKCS7 padding
  bytes and passed on the real saves only by coincidence (a 9-byte pad is
  `0x09`, a tab, which the printable set included). It would have rejected the
  correct key for a different plaintext length. Fixed by stripping padding
  before the check; documented in `docs/key-recovery.md`.
