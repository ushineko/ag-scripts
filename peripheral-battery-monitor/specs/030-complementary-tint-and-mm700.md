# Spec 030: tint the dashboard complementary to the scene, and put the MM700 in scope

> **Note**: This work has no associated issue tracker ticket. Consider creating one for traceability.

## Executive Summary

Two requests from the same sitting. The LCD dashboard now recolours itself from
the active lighting scene, drawn in the complement of the scene colour so the
screen reads as part of the lighting rather than a separate blue panel. The MM700
mousepad joins the default lighting scope, so scenes drive it alongside the
Kraken, GPU and motherboard. Reviewers should look at `complement()` in
`aio_dashboard.py` and at the cadence bypass in `aio_section.py`.

## Context

The dashboard's background was a fixed palette. The scene profiles already drive
every lit device to one colour, so the one surface in the middle of the case that
the user actually reads was the only thing not participating.

Complement rather than match: a background in the *same* hue as the lights makes
the foreground text compete with the case glow, and the metrics are the point of
the screen. Rotating the hue 180 degrees keeps the relationship legible while
leaving the readout high-contrast.

The MM700 was simply missed when scope was established in spec 023. It reports
only Direct mode - no Static, no Off - which the existing per-device mode
resolution already handles: `solid` maps to Direct, and `off` maps to Direct with
black.

## Requirements

1. The dashboard background derives from the active scene colour, not a constant.
2. A scene change repaints the screen promptly, not on the ordinary content
   cadence.
3. An absent, unparseable or black scene colour leaves the dashboard at its
   default appearance rather than rendering black-on-black.
4. The MM700 is driven by scenes with the rest of the scope.

## Acceptance Criteria

- [x] `complement()` returns the same saturation and value with the hue rotated
      180 degrees, and returns its input unchanged for a colour with no defined
      hue (greyscale) or an invalid tuple.
- [x] The dashboard background is generated from the complement of the active
      lighting colour, and the generated background is cached per tint so an
      unchanged tint does not re-render it.
- [x] A tint change bypasses the minimum-interval gate, so a scene change is on
      screen in ~4 s rather than waiting out the ~17 s content cadence.
- [x] `_active_tint()` yields None for a missing, unparseable or black colour, and
      the dashboard falls back to its default palette in that case.
- [x] `"mm700"` is in `DEFAULT_SCOPE` in `rgb_openrgb.py`, and its Direct-only mode
      set resolves correctly for both `solid` and `off`.
- [x] The possible OpenLinkHub conflict on the MM700 is recorded in the scope
      comment rather than left to be rediscovered.
- [x] Existing tests still pass.

## Risks & Assumptions

- **OpenLinkHub also manages the MM700.** Two controllers writing one device can
  fight, and OpenLinkHub may reassert its own colour. If the mousepad ignores
  scenes or reverts, it must be excluded there so OpenRGB owns it. This is
  unverified at the time of writing.
- **The mouse and keyboard stay out of scope** deliberately: their lighting is
  usually per-application, while a mousepad is ambient in the same way the case is.
- **The tint bypass raises the write rate** on a scene change only. Steady-state
  push cadence is unchanged, so exposure to liquidctl#774 does not grow in
  ordinary use.
- **Rollback**: revert the commit. The dashboard returns to its fixed palette and
  the MM700 leaves scope; no state or settings migration is involved.

## Alternatives Considered

- Considered tinting the dashboard to *match* the scene colour; rejected because a
  same-hue background competes with the case glow and costs readout contrast.
- Considered asserting `complement()` is its own inverse in tests; rejected on
  evidence - RGB->HSV->RGB is lossy and drifts a few units. The real contract is
  hue opposition, checked with stdlib `colorsys` so it is immune to the QColor
  mock another module installs at collection time.

## Status: COMPLETE
