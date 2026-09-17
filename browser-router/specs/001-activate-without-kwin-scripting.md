# Spec 001: Activate the primary Vivaldi window without KWin scripting

## Status: COMPLETE

> **Note**: This work has no associated issue tracker ticket (ag-scripts is a
> personal repository and uses none).

## Context

The v1.3 Wayland workaround — activate a Vivaldi window on the primary monitor
before forwarding a URL, so Chromium's singleton hand-off has a focusable target
— stopped working. Links opened nothing. Two independent defects, either of which
alone is fatal, and both silent.

**1. The configured connector name no longer exists.** `PRIMARY_OUTPUT` defaulted
to the hardcoded string `HDMI-A-1`. The Philips is now on `DP-3`
(`kscreen-doctor -o` lists only `DP-3` and `DP-2`), so the name matched no output
and the window loop fell through without activating anything. A connector name
describes which *port a cable is in*, not which monitor sits on the desk, so it
changes whenever hardware is moved — it is not a stable identifier for "primary".

**2. KWin's `loadScript` cannot create a script object on this box.** The
activation used the documented `loadScript(path, name)` → `run()` on
`/Scripting/Script<returned id>` pattern. Measured behaviour here: `loadScript`
returns `3` while `/Scripting/Script3` already exists and **no new object is
created**, for any plugin name, including names never loaded before. `run()` then
addresses a pre-existing object belonging to something else (`slack-focus-monitor`
is an enabled KWin script) and is a silent no-op. Confirmed by introspecting
`/Scripting` before and after the load: the child set is unchanged.

This is the third separate incident against KWin's Scripting D-Bus interface on
this machine (see the `silent-failures-are-the-expensive-kind` note: recycled
ids, `unloadScript` not destroying objects, `isScriptLoaded` true for a script
that never ran). Every one of its status channels — returned id, `isScriptLoaded`,
`unloadScript`'s return, `run`'s return — reports success while doing nothing.
The interface is not trustworthy for one-shot use, so the fix stops using it.

`WindowsRunner` (`org.kde.krunner1` on `/WindowsRunner`) plus
`org.kde.KWin.getWindowInfo` do the same job over plain D-Bus with no object
lifetimes to get wrong, at ~8 ms per call.

## Requirements

1. Activation must not use KWin's Scripting interface.
2. The primary output must be resolved at run time, not hardcoded. The default
   (`auto`) is the enabled output with the lowest kscreen `priority`, which is
   what Plasma calls primary.
3. An explicitly configured connector name that is not currently enabled must
   degrade to `auto`, never to doing nothing.
4. Window-to-output matching must compare like with like: kscreen `pos` is
   logical but `size` is not, so the target rectangle is `size / scale`, and
   KWin's `getWindowInfo` geometry is logical.
5. If no Vivaldi window is on the target output, activate any Vivaldi window —
   still better than dropping the URL.
6. Every decision must be traceable via `BROWSER_ROUTER_DEBUG=1`. A handler
   invoked by the desktop has no other way to be observed, which is why this
   stayed broken.
7. Activation stays best-effort: no failure may prevent the URL being forwarded.
8. `install.sh` must not clobber a symlinked target, which is how the live copy
   is deployed here (stow, into dotfiles).

## Acceptance Criteria

- [x] No `org.kde.kwin.Scripting` call remains in the script
- [x] `output_rect auto` returns the priority-1 output's logical rectangle
- [x] `output_rect <name>` returns that output's logical rectangle, and fails
      for a name that is not enabled
- [x] Logical size accounts for scale and rotation, matching `getWindowInfo`
      coordinates (verified against both the landscape and the portrait output)
- [x] A configured-but-absent connector falls back to the primary output
- [x] A Vivaldi window on the target output is activated, verified by
      `org.kde.KWin.activeOutputName` changing to that connector
- [x] The forwarded URL actually opens, verified by the window caption changing
- [x] `BROWSER_ROUTER_DEBUG=1` narrates output resolution, per-window decisions,
      and the activation
- [x] `install.sh` writes through a symlinked target instead of replacing it
- [x] shellcheck clean
- [x] Rect-math tests pass against fixture kscreen JSON

## Risks & Assumptions

- **Rollback**: revert the commit and re-run `install.sh`. No state is migrated;
  the config file keys are unchanged and `PRIMARY_OUTPUT="DP-3"` still works.
- **`WindowsRunner` query**: matching is by the string `vivaldi`, which KWin's
  runner tests against caption, app name and window class. A Vivaldi window is
  always class `vivaldi-stable`, and the class match is what the code filters on
  afterwards, so a caption that happens not to contain "vivaldi" is still found.
- **Assumption**: exactly one Vivaldi window per output. With several on the
  target output the first match wins, which is acceptable — any window on the
  right monitor satisfies the hand-off.
- No integration boundary in the Ralph sense. The D-Bus calls are exercised live
  in the verification below rather than mocked.

## Alternatives Considered

- Just changing the default to `DP-3`: rejected — it fixes only defect 1, leaves
  the silent `loadScript` no-op in place, and re-breaks the next time a cable
  moves.
- Freeing the stuck KWin script id by calling `stop()` on `/Scripting/Script3`:
  rejected — that id has been observed belonging to `slack-focus-monitor`, and
  the interface gives no way to identify an object's owner.

## Verification

```
$ BROWSER_ROUTER_DEBUG=1 ~/.local/bin/browser-router "https://www.iana.org/help/example-domains"
browser-router: routing to vivaldi: https://www.iana.org/help/example-domains
browser-router: target output auto rect=0 1120 2560 1440
browser-router: window {9ff9d859-...} at 0,1120 2560x1440 is on the target output
browser-router: activated 0_{9ff9d859-...}
Opening in existing browser session.

$ qdbus6 org.kde.KWin /KWin getWindowInfo "{9ff9d859-...}" | grep caption
caption: Example Domains - Vivaldi
```
