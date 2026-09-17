# Spec 028: the LCD drops a static image but retains a GIF

## Context

Reported: the custom dashboard is flaky, alternating between the rendered image
and the cooler's built-in display every few minutes.

The first explanation offered was wrong. Specs 021/022 documented a *brief*
fallback while liquidctl deletes and rewrites a bucket, so the behaviour was
assumed to be that, plus a high push rate. Measurement contradicted both halves:

- **Coolant is steady** at 39.9 C, so the coolant branch of `should_push` is not
  firing. CPU temperature swings 51-97 C, so its threshold is what triggers the
  observed pushes every 70-100 s.
- **The image disappears with nothing touching the cooler at all.** With the
  monitor stopped — no 5 s status poll, no dashboard pushes, no other liquidctl
  process — a hand-pushed image still reverted to the built-in display on its
  own.

So the device does not retain a host-pushed image indefinitely. Nothing the host
*does* causes the revert; it is what the host *stops* doing. The screen was only
ever staying up because a content change happened to redraw it in time, which is
why it looked intermittent and correlated loosely with activity.

This inverts the design assumption. Specs 021 and 022 treated "write as rarely as
possible" as the goal, because repeated writes provoke liquidctl#774 bucket
failures. That is still true, but it is now in tension with a hard requirement:
below some refresh period the image simply is not on screen. Minimising writes
past that point does not make the dashboard quieter, it makes it absent.

### The fix: push a GIF, not a static image

Measured after the above: with the monitor stopped and nothing touching the
cooler, a pushed **GIF keeps playing indefinitely** where a static image reverted
in 5-10 s. The two take different routes inside liquidctl — `static` decodes the
image and sends raw pixels to a bucket, `gif` sends the GIF file and the firmware
loops it — and only the second is retained.

This was visible in the existing behaviour and missed: the user's GIF *scenes*
(corgis, mandelbrot) had never misbehaved, because the picker routes animated
files through `gif` mode. The dashboard was the only thing on the `static` path,
and the only thing that expired.

So the dashboard now renders to a single-frame GIF. One frame is enough; nothing
is being animated, the point is purely that the firmware retains a GIF. Qt still
draws it, Pillow encodes it because Qt can read GIF but not write it.

A keep-alive was implemented first, at a 4 s interval derived from the measured
retention. It is retained but **defaults to off**: at ~0.7-0.8 s of hidraw time
per push against a 5 s status poll, and straight down the liquidctl#774 path, it
was an expensive answer to a problem that turned out not to need one. It stays
only as an escape hatch for firmware that retains neither format.

## Requirements

1. Use a push mode the firmware actually retains, so the image does not expire.
2. Keep pushing promptly when something meaningful *does* change.
3. Keep the keep-alive interval configurable, since the retention period is a
   device/firmware property that this project cannot pin down from documentation.
4. Do not defeat the existing protections: writes stay serialised, coalesced, and
   subject to the failure ceiling.

## Acceptance Criteria

- [x] The dashboard is written as a single-frame GIF and pushed with `gif` mode,
      not as a PNG via `static`.
- [x] The written file is a real GIF at the panel's native 640x640.
- [x] A keep-alive interval exists, separate from the change-driven minimum
      interval, and is applied even when `should_push` returns False; it defaults
      to off because the GIF fix makes it unnecessary.
- [x] A change that `should_push` accepts still pushes at the minimum interval
      rather than waiting for the keep-alive.
- [x] The keep-alive is selectable from the menu and persists.
- [x] Keep-alive pushes go through the same queue, coalescing and failure-ceiling
      path as any other LCD write; they are not a side channel.
- [x] A keep-alive push is skipped while the dashboard is disabled.
- [x] Successful pushes are logged, so the time between a push and a revert can be
      measured from the log rather than by watching the screen.
- [x] Existing tests still pass.

## Risks & Assumptions

- **The retention period is measured, not documented.** It is a property of this
  firmware; the default is set from observation on this machine and exposed as a
  setting precisely because that is not a safe constant to hardcode for others.
- **More writes means more exposure to liquidctl#774.** That is accepted: an image
  that is not on screen has no value, and the failure ceiling still disables the
  dashboard and falls back to the firmware readout if writes start failing.
- **Each push costs ~0.7-0.8 s of hidraw time**, serialised against a 5 s status
  poll. At a 10 s keep-alive that is a meaningful share of the queue, which is why
  the interval is tunable rather than fixed low.
- **Cooling telemetry and pump alerting are unaffected** either way; the LCD is
  decorative and its failures never touch them.
- **Rollback**: revert the commit. The dashboard returns to change-only pushes and
  to expiring off the screen between them.

## Alternatives Considered

- Considered lowering the CPU push threshold so ordinary fluctuation redraws often
  enough to mask the expiry; rejected as tying refresh to unrelated load, which is
  exactly why the fault looked intermittent.
- Considered the firmware's built-in `liquid` mode instead of a rendered image;
  rejected because it shows only coolant temperature and drops CPU and pump, which
  is the reason the dashboard exists.
- Considered holding the device open to keep the image alive; rejected because the
  monitor drives liquidctl per call by design, and a long-lived handle would
  collide with the status poll and with OpenRGB.

## Status: COMPLETE
