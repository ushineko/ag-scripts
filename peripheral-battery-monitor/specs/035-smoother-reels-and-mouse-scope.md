# Spec 035: smoother reels, and the mouse joins the lighting scope

> **Note**: This work has no associated issue tracker ticket. Consider creating one for traceability.

## Executive Summary

Photo-reel crossfades looked "very chunky" — five steps per transition. The cause
was not the 24MB budget but two encoding choices that wasted most of it:
authoring at 480 so the driver upscaled in palette mode, and giving every frame
its own adaptive palette. Fixing both bought roughly 2x, and reels now run 16-28
crossfade steps. Separately, the mouse joins the default lighting scope, through
OpenRGB rather than Solaar. Reviewers should look at `render`/`quantise` in
`build_reels.py`.

## Context

### The reels

`build_reels.py` already did what was wanted architecturally — a source photo
directory in, one animated GIF out — so the fix was in parameters, not design.

Three findings, each measured on `corgis` at otherwise identical settings:

1. **Author at 640, not 480.** The driver resizes every frame to 640x640 *in
   palette mode* (nearest neighbour) and re-encodes. A 480 source therefore saves
   nothing: the upscale invents noise that will not delta-encode. 28.25MB at 480
   against 20.43MB at 640. The previous docstring advised the opposite, having
   measured the file on disk rather than what the driver sends.
2. **One palette per reel, not per frame.** `convert("P", palette=ADAPTIVE)`
   gives each frame its own colour table, so consecutive frames cannot
   delta-encode — exactly what a crossfade needs. 20.43MB to 14.17MB.
3. **Per-frame durations.** Every frame carried the same 180ms, so a fade could
   be made smoother only by making it slower. A held photo is one frame carrying
   the whole hold; each crossfade step carries only `FADE_MS`.

Together: corgis went from 5 crossfade steps to 24 at the same 0.84s transition.

Reels differ in length (three photos to eight), so `build` steps the fade count
down from `MAX_FADE` until it fits rather than taking a fixed value that would
waste headroom on short reels and overrun on long ones.

### The mouse

Requested via Solaar, which is already used here for battery levels. Solaar does
expose the G502's `rgb_zone_1`, but **its CLI accepts only the effect name and
silently drops the colour** in every form tried (`FF0000`, `0xFF0000`, as extra
or subkey). `rgb_zone_1 Static FF0000` sets Static with no colour — black. It
prints "Setting rgb_zone_1 ... to Static" and succeeds while turning the mouse
off, which is how it was discovered.

OpenRGB already enumerates the mouse with Direct/Off/Static/Breathing and eight
LEDs, so it needs no new mechanism: one scope entry, driven exactly like the
MM700.

## Requirements

1. Crossfades must read as a dissolve rather than discrete steps.
2. Each reel uses the smoothest fade its own budget allows.
3. The loop must be seamless.
4. Reels must stay under the driver's assertion, with margin.
5. The mouse follows scenes with every other device.
6. The keyboard stays out of scope.

## Acceptance Criteria

- [x] Frames are authored at the panel's native 640, so the driver's resize is a
      no-op (file and encoded size now match exactly: 19.60MB for corgis).
- [x] All frames of a reel are quantised onto one shared palette.
- [x] Durations are per frame: a held photo carries the full hold, each fade step
      carries `FADE_MS`.
- [x] `build` fits the fade count to each reel's budget, between `MIN_FADE` and
      `MAX_FADE`, and fails loudly if even `MIN_FADE` will not fit.
- [x] All four reels rebuilt: corgis 24, cats 28, puppies 28, everyone 16 steps.
- [x] The loop is seamless, verified by measurement rather than assertion: RMS
      pixel difference across the wrap is smaller than the median difference
      between adjacent frames in all four reels.
- [x] `"g502"` is in `DEFAULT_SCOPE`; a test asserts the mouse is in scope and
      another asserts the keyboard is not.
- [x] The docstring's reversed advice about shrinking the source is corrected.
- [x] Existing tests still pass.

## Risks & Assumptions

- **Smoothness costs upload time.** Push is ~1.5s plus 0.22s/MB with the panel
  blank throughout, so corgis went from ~4.0s to ~5.8s of black per scene change.
  Accepted deliberately; `MAX_FADE` is the dial if it proves annoying.
- **64 colours with Floyd-Steinberg is assumed indistinguishable from 96** at
  640 on dithered photographs. Judged by eye on the panel, not measured.
- **Solaar left a persisted `rgb_zone_1 = Static` on the mouse** from the failed
  attempt. It is inert while nothing replays it — no solaar daemon runs here —
  but it is saved device state this project did not put back.
- **Rollback**: revert the commit and re-run `./build_reels.py`; the previous
  reels are regenerated from the same sources. The mouse leaves scope.

## Alternatives Considered

- Considered driving the mouse through Solaar as asked; rejected on evidence -
  its CLI cannot set a colour at all.
- Considered a fixed fade count for every reel; rejected because reel lengths
  differ by more than 2x, so one value either wastes or overruns.
- Considered dropping to 48 or 32 colours for even more steps; deferred - 64 was
  judged good on the panel, and fewer colours trade a visible risk for a
  diminishing return.

## Status: COMPLETE
