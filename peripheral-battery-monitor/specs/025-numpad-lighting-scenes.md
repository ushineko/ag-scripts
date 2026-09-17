# Spec 025: numpad lighting scenes over D-Bus

> Revised twice during implementation: the binding mechanism moved from
> `.desktop` shortcuts to KWin scripting (the former cannot take effect
> until the next login), and a second bank of animation scenes was added
> on `Shift+Ctrl+Alt+Numpad N`.

## Context

Lighting (spec 023) and LCD control (specs 021-024) are reachable only from the
tray context menu. The user wants `Ctrl+Alt+Numpad 1-9` to switch between
preset combinations of lighting colour and LCD mode without opening a menu.

The monitor is always running, so it can own the presets. That is also the only
correct place for them: every liquidctl call on this machine must go through
`LiquidctlQueue`, because the status poll, LCD writes and the OpenRGB server all
touch the same device. A shortcut that shelled out to `liquidctl` directly would
race the poll rather than queue behind it.

**Binding mechanism on this machine**, established by the existing shortcuts
(`audio-source-switcher`, `display-mirror-toggle`, `herdr-switcher`): a
`.desktop` file in `~/.local/share/applications/` plus a
`[services][net.local.<file>.desktop]` entry with `_launch=<key>` in
`kglobalshortcutsrc`, which is stow-managed in dotfiles. KDE writes numpad keys
as `Num+N`, so the bindings are `Ctrl+Alt+Num+1` … `Ctrl+Alt+Num+9`. No
`Ctrl+Alt+Num+*` binding currently exists, so nothing is displaced.

**IPC**: `kwin_window_position.py` already registers a session D-Bus service in
this project, so the pattern is established rather than invented here.

## Requirements

1. A scene sets a lighting colour and an LCD mode. It does **not** touch LCD
   brightness — a shortcut that unexpectedly dimmed the screen would be a
   surprise, and brightness is a preference rather than part of a look.
2. Scenes are seeded with defaults and stored in the existing settings JSON, so
   they can be retuned without a code change.
3. Either half of a scene may be omitted, leaving that aspect untouched.
4. Applying a scene goes through the monitor's existing queue.
5. Triggering costs nothing when the monitor is absent: the CLI fails quietly
   with a clear message rather than hanging or erroring into a notification.
6. The GUI thread is never blocked.

## Scene model

```json
{"color": "red",    "lcd": "dashboard"}
{"color": "#ff8800","lcd": "liquid"}
{"color": "off",    "lcd": null}
{"color": null,     "lcd": "/home/u/Pictures/x.gif"}
```

- `color`: a `NAMED_COLORS` name, `#rrggbb`, `off`, or `null` to leave alone.
- `lcd`: `dashboard` (live render), `liquid` (firmware readout), a path to an
  image or GIF (animated files play), or `null` to leave alone.

## Acceptance Criteria

- [x] `aio_scenes.py` validates a scene dict and reports what is wrong with a
      malformed one, without applying anything.
- [x] Defaults exist for slots 1-9, are written into settings on first run, and
      an existing user-edited set is never overwritten.
- [x] A scene with `color: null` leaves lighting untouched; a scene with
      `lcd: null` leaves the LCD untouched.
- [x] An `lcd` path that is an animated GIF plays; a still image is shown
      statically; a missing file is reported and the colour half still applies.
- [x] The monitor registers a session D-Bus service exposing an apply-by-slot
      method, and applying goes through `LiquidctlQueue`.
- [x] The CLI applies a slot via D-Bus, exits non-zero with a one-line message
      when the monitor is not running, and never blocks longer than a short
      timeout.
- [x] Nine `.desktop` files and nine `kglobalshortcutsrc` entries bind
      `Ctrl+Alt+Num+1` … `Ctrl+Alt+Num+9`, both stow-managed in dotfiles.
- [x] Applying a scene never disturbs cooling telemetry or pump alerting.
- [x] Existing tests still pass.

## Risks & Assumptions

- **D-Bus name collision**: the service name is namespaced under
  `org.agscripts.` like the existing one. A second monitor instance cannot
  register it, which is consistent with the existing `QLockFile` single-instance
  guard.
- **Wayland global shortcuts** are KDE's to dispatch; the app never grabs keys
  itself, so nothing here depends on X11 or on the app having focus.
- **A scene switching the LCD away from the dashboard disables it**, exactly as
  the menu does, and that state persists via the existing `dashboardChanged`
  signal. Numpad 1 (dashboard) turns it back on.
- **Rollback**: remove the `.desktop` files and the kglobalshortcutsrc entries;
  the monitor keeps working and the menu is unaffected.

## Alternatives Considered

- Considered a standalone CLI driving liquidctl/OpenRGB directly, with no
  monitor involvement; rejected because it would bypass the queue that keeps
  concurrent hidraw access safe, which is the one invariant this project has
  been most careful about.
- Considered KDE's `KGlobalAccel` registration from inside the app; rejected
  because PyQt6 does not expose it, and the `.desktop` + kglobalshortcutsrc
  route is what every other custom shortcut on this machine already uses.

## Addendum: animation bank

Slots 11-19, bound to `Shift+Ctrl+Alt+Numpad 1-9`, pair an animated GIF with a
lighting colour **derived from the animation itself** rather than chosen by
hand: frames are sampled, near-black and washed-out pixels discarded, the
dominant hue taken by a vividness-weighted vote, then saturation and value
pushed up because an LED renders a muted screen colour as muddy brown.

Sources are the existing Capellix set plus three downloaded from Wikimedia
Commons — a corgi still rendered into a seamless zoom loop (CC BY-SA 4.0) and
Eadweard Muybridge's galloping dog (public domain). Attribution is recorded in
`~/Pictures/LcdAnimations/ATTRIBUTION.txt`.

## Status: COMPLETE
