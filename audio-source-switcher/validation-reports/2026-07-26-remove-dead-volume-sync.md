## Validation Report: Remove dead check_and_sync_volume (v13.1)

**Date**: 2026-07-26
**Version**: 13.1 (unchanged — no user-facing behavior change)
**Spec**: none (Phase 4 dead-code removal, not a feature)

## Summary

Deletes `MainWindow.check_and_sync_volume` (36 lines). It has had no callers since
before spec 009, which already recorded it as unwired dead code. Nothing else changes.

## Changes

- `audio_source_switcher/gui/main_window.py`: removed `check_and_sync_volume`.

No other file touched. No version bump: the method was unreachable, so no observable
behavior changes and the About dialog / README stay at 13.1.

## Why

Beyond ordinary dead-code hygiene, this method was a latent hazard rather than an inert
leftover. It folded the JamesDSP attenuation downstream and reset the filter sink to
full scale:

```python
factor = jdsp_vol / 100.0
new_vol = int(current_target_vol * factor)
self.audio.set_sink_volume(found_target, new_vol)
self.audio.set_sink_volume("jamesdsp_sink", 100)
```

With the current live values (`jamesdsp_sink` 55%, endpoint 43%) that computes
`43 * 0.55 ~= 23%` on the endpoint and drives `jamesdsp_sink` to 100%. Perceived
loudness is roughly preserved, but the headroom moves to *after* the DSP, so the chain
would feed JamesDSP's gain stage at full scale. The user keeps `jamesdsp_sink` below
100% deliberately as clipping headroom, so anything that re-wired this method would
have silently removed that protection.

## Validation

### Phase 3: Tests
- `pytest` in `audio-source-switcher/` (system python 3.14, `QT_QPA_PLATFORM=offscreen`):
  **43 passed**, 0 failed — unchanged from before the removal.
- `python3 -m py_compile` on the modified file: clean.
- No test referenced the removed method, so no test was deleted or weakened.

### Phase 4: Code Quality
- **Deadness verified three ways** before removal: no callers anywhere in the repo
  (only the definition, plus historical mentions in spec 009 and two 2026-01/03
  validation reports, which are records and were left alone); no dynamic dispatch that
  could reach it (the only `getattr` in the package is an unrelated
  `getattr(self, "volume_monitor", None)`, and there is no `QMetaObject.invokeMethod`
  or string-based signal connection); not referenced from any `.desktop`, QML, or shell
  entry point.
- **No orphans created**: `PipeWireController` still has 8 references in the file, so
  the import stays; `get_jamesdsp_outputs` retains 5 other call sites and
  `find_linked_sink` is still used by `pipewire.py:79`.
- `flake8` on the changed file reports only pre-existing findings — long lines in the
  About dialog HTML, and one `E303` that exists identically at HEAD (line 628 there,
  line 592 here, shifted by the 36 removed lines). Nothing introduced, nothing
  pre-existing fixed (surgical-change rule).

### Phase 5: Security
- Deletion only; no new code, no new dependencies, no new `subprocess` calls, no
  change to input handling or file I/O. Attack surface strictly decreases.
- Secrets scan of the diff: nothing (the diff contains no additions at all).
- Dependency posture unchanged since the v13.1 report earlier today; the sole
  environment finding (`msgpack`, pacman-managed, unused by this project) is unaffected.

### Phase 5.5: Release Safety
- **Rollback**: `git revert` restores the method verbatim. Since it was unreachable,
  reverting is also a no-op behaviorally.
- **Blast radius**: none at runtime. The running instance does not call this code path,
  so no restart is required to "apply" the change.
- **Additive/removal check**: this is a removal, but of a private, unreferenced method —
  not part of any public surface, CLI flag, config key, or socket protocol.

## Status

All quality gates passed. No spec to reconcile (not spec-driven work). Ready to commit.
