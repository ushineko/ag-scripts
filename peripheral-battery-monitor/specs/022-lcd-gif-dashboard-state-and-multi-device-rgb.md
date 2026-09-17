# Spec 022: animated GIFs, dashboard state, refresh intervals, multi-device RGB

## Context

Four defects and gaps reported against spec 021 after using it.

### 1. Animated GIFs show only their first frame

`aio_liquid.lcd_gif_argv()` was written in spec 021 and **never called**. The
file picker offers `*.gif` and routes every selection to `set_lcd_static`, which
maps to `liquidctl set lcd screen static` — a single-frame path.

Animated GIFs are fully supported by this hardware. Verified on the device:
`liquidctl set lcd screen gif` plays both a synthetic 12-frame GIF and
`~/Pictures/CappelixImages/newtonscradle.gif` (36 frames, 480x480). The driver
only refuses GIFs on product `0x300E` with firmware 2.x; this unit is `0x3012`
on firmware 1.2.0. Purely a routing bug.

### 2. The live dashboard cannot be switched back on

`set_lcd_static()` and `set_lcd_liquid()` call `set_dashboard_enabled(False)` on
the section but never update `settings["aio_lcd_dashboard"]`. The menu checkbox
is built from settings, so after showing an image it still renders **checked**
while the section is off. Clicking it therefore emits `triggered(checked=False)`
and disables an already-disabled dashboard. The user sees the LCD stay on the
built-in readout no matter how many times they click — it takes two clicks, and
the first appears to do nothing.

The root cause is two copies of one piece of state. The section owns whether the
dashboard is running; settings is only durable storage. They are allowed to
disagree, so they do.

### 3. No control over dashboard refresh rate

`LCD_PUSH_INTERVAL_MS` is a module constant. 30 s suits an idle machine, but the
rate should be the user's choice.

### 4. NZXT fan RGB is not addressable

Spec 021 established that the Kraken Elite V2 exposes **no** colour channels, so
its Colour/Effect menus stay hidden. NZXT RGB fans need a separate NZXT RGB
controller, which is not yet on this machine (`lsusb` shows only `1e71:3012`).

The blocker is narrower than "no hardware": `aio_liquid.color_channels()` only
inspects `KrakenX3` instances, and every argv is built with a hardcoded
`--match kraken`. Even with a controller attached, nothing would find it. The
probe and the argv builder must become device-agnostic so the capability appears
by itself when the hardware does.

## Requirements

1. Route animated GIFs to `liquidctl set lcd screen gif`, static images to
   `static`, chosen by what the file actually is.
2. One source of truth for dashboard state; the menu must always reflect reality
   and a single click must always do what it says.
3. User-selectable dashboard refresh interval, persisted.
4. Discover colour-capable devices across all liquidctl drivers, not just
   Kraken, and address each by its own `--match`.

## Acceptance Criteria

- [x] `aio_liquid.is_animated(path)` returns True for a multi-frame GIF, False
      for a single-frame GIF and for non-GIF images, and False (not an
      exception) for a missing or unreadable file.
- [x] `AioSection.set_lcd_image(path)` dispatches to the `gif` mode for an
      animated file and `static` otherwise.
- [x] Selecting an animated GIF from the picker plays it; the previous behaviour
      showed frame one only.
- [x] `AioSection` exposes `dashboard_enabled` as a read-only property and emits
      a signal whenever it changes, including when changed indirectly by
      `set_lcd_static` / `set_lcd_gif` / `set_lcd_liquid` / surrender.
- [x] The menu checkbox is built from the section's live state, not from
      settings, so it can never disagree with the hardware.
- [x] Settings persistence is driven by the signal, so an indirect disable is
      still remembered across a restart.
- [x] After showing an image, one click on "Live dashboard" re-enables it and the
      dashboard resumes drawing.
- [x] Refresh interval is selectable from the menu, persisted, applied without a
      restart, and validated against an allowed set.
- [x] `aio_liquid.color_devices()` returns every liquidctl device reporting
      colour channels, each with its own match token, description and channel
      list — not only Kraken devices.
- [x] Colour argv accepts a match token so a non-Kraken RGB device is addressed
      correctly; the default remains the cooler.
- [x] The Colour/Effect menus appear per colour-capable device and stay hidden
      when none exists, which is the current state of this machine.
- [x] Existing 324 tests still pass.

## Risks & Assumptions

- **The multi-device RGB path cannot be verified on hardware today.** No
  colour-capable device is attached: `liquidctl list` shows the Kraken (no
  channels), the HX1000i and the ASUS Aura controller, none of which offer
  colour channels through liquidctl. The code is exercised by tests with
  synthetic device stubs, and marked as unverified-on-hardware until an NZXT RGB
  controller arrives. This is stated plainly rather than implied to work.
- **The ASUS Aura controller is visible to liquidctl** but reports no colour
  channels, so it will not appear. If a future liquidctl adds Aura colour
  support, it would start appearing in the menu — which is the intended
  behaviour of a capability-driven menu, but worth knowing.
- **GIF size**: the driver asserts under 24 MB after resize. A larger file fails
  with an assertion rather than a clean error; the picker cannot easily predict
  post-resize size, so the failure is surfaced through the existing write-failure
  logging.
- **Rollback**: revert the commit. GIFs return to first-frame, the toggle returns
  to needing two clicks; cooling telemetry and alerting are untouched.

## Alternatives Considered

- Considered keeping settings as the menu's source and syncing it from every
  call site; rejected because that is the bug — every new call site is another
  chance to forget. A signal makes desync structurally impossible.
- Considered deciding gif-vs-static from the file extension alone; rejected
  because a single-frame `.gif` is better served by the static path, and an
  animated file misnamed `.png` should still animate.

## Status: COMPLETE
