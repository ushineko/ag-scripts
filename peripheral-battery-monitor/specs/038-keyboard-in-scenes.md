# Spec 038: the keyboard joins scenes, reactively

> **Note**: This work has no associated issue tracker ticket. Consider creating one for traceability.

## Executive Summary

The Keychron K4 HE now takes scene colours. It renders them as a *reactive*
effect by default — Solid Splash ripples from each keypress — selectable from the
menu against a flat wash. It is exempt from the `off` intent so a blanking scene
cannot kill the backlight, and its brightness is now asserted by the monitor
rather than inherited. Reviewers should look at `KEYBOARD_EFFECTS` and
`brightness_for`.

## Context

The keyboard was deliberately excluded in spec 035, on the reasoning that its
lighting is per-application and a scene would fight it. The owner asked for it
in, with two conditions that shaped the design.

**It is a QMK/VIA device on USB** (`3434:0e40`), fully driven by OpenRGB, with
~90 per-key LEDs and a large mode list. No new mechanism was needed. It advertises
`Solid Color` rather than `Static`, so the default preference already fell
through to `Direct` correctly.

**Exempt from `off`.** With no `Off` mode, the `off` intent resolves to `Direct`
with black — which kills the backlight on a keyboard someone is typing on rather
than dimming it. Colour scenes still reach it.

**Reactive, not flat.** The board has `Solid Reactive *`, `Splash` and
`Solid Splash`, and these accept a colour from us (verified: sent blue, flared
blue). None of them light a background: every reactive effect here lights only
what is pressed. A dim backdrop with flares on top is not a stock QMK effect and
would need a keystroke listener driving `Direct` per key — a process reading
keystrokes, which is a large and privacy-relevant addition for a lighting effect.

The absent background turned out to be desirable: with surrounding keys dark, an
active indicator such as Caps Lock is far more visible. That is why `splash` is
the default rather than a compromise.

## Requirements

1. The keyboard takes scene colours.
2. A scene's `off` never blanks it.
3. The effect is user-selectable and persists.
4. Brightness is owned by the monitor, not left as stray device state.

## Acceptance Criteria

- [x] `"keychron"` is in `DEFAULT_SCOPE`; tests assert it is in scope and that
      the four case devices still blank on `off` while it does not.
- [x] `OFF_EXEMPT` skips the keyboard for the `off` intent only; a test asserts
      `off` writes to two of three devices and `solid` to all three.
- [x] `KEYBOARD_EFFECTS` maps `splash` -> Solid Splash and `solid` -> Direct,
      defaulting to `splash`; an unknown or missing value falls back rather than
      leaving the keyboard unlit.
- [x] The effect is a checkable submenu under Lighting, persists to settings,
      is restored at startup *before* the first scene, and re-applies to the
      keyboard alone when changed.
- [x] The choice does not affect any other device's mode resolution.
- [x] `brightness_for` asserts 100% on keyboard writes and leaves every other
      device untouched; index-addressed writes assert nothing, having no name.
- [x] Verified live: keyboard forced to dim red (25%) behind the monitor's back,
      then a scene restored both colour and full brightness.
- [x] Existing tests still pass.

## Risks & Assumptions

- **Brightness is a constant, not a setting.** 100% is asserted because the fault
  being fixed was a stray value persisting; if a dimmer keyboard is wanted it
  should become a setting rather than be left to whatever wrote last.
- **`BRIGHTNESS_DEVICES` is scoped to the keyboard**, where persistence was
  observed. Other devices may have the same behaviour unnoticed.
- **The reactive effect leaves unpressed keys dark.** Deliberate, but it means
  the keyboard is unlit while idle - which is a change from a flat backlight.
- **Rollback**: revert the commit. The keyboard leaves scope entirely; nothing
  else changes.

## Alternatives Considered

- Considered a dim background with flares, as originally asked; not available -
  no stock QMK effect on this board lights a background, and synthesising one
  needs a keystroke listener.
- Considered leaving the keyboard out, per spec 035; superseded by the owner's
  request, with the `off` exemption addressing the original concern.
- Considered always sending `--brightness` to every device; rejected as a wider
  change than the evidence supports.

## Status: COMPLETE
