# Spec 018: CPU Trend Overlay on the AIO Sparkline

> **Note**: This work has no associated issue tracker ticket. This is a personal
> public repository with no issue tracker (see `.claude/CLAUDE.md`).

## Status: COMPLETE

## Executive Summary

Adds a second trace to the AIO sparkline: CPU temperature as a 60-second
trailing mean, in muted steel blue beside the raw coolant trace. Raw CPU was
excluded in 1.14.0 because it spikes to 100 °C on any compile; averaged, it
becomes a trend line worth reading against coolant. The two series scale
independently rather than sharing an axis, because CPU swings ~33 °C where
coolant moves under 1 °C and a shared axis would flatten coolant to about 2 px.
Review that trade-off first: heights are not comparable between traces, which is
documented in the README, the `Sparkline` docstring, and the known-limitations
section of the validation report. The graph's visibility rule also changed — it
now shows whenever either trace has data, amending spec 017 AC11.

## Context

Spec 017 shipped the AIO section with a single-series sparkline plotting coolant
temperature. CPU temperature was deliberately excluded: on this i9-14900K it
spikes to 100 °C on any compile, and a raw trace at 26 px tall reads as noise.

A trailing mean removes that objection. Averaged over a minute, CPU temperature
becomes a trend line whose correlation with coolant is the interesting part: CPU
leads, coolant follows, and the lag between them is the loop's thermal inertia.

### The scaling problem

The two series cannot share a vertical axis at this widget size. Measured over
one session:

| Series | Observed range | Swing |
| ------ | -------------- | ----- |
| CPU | 65–98 °C | ~33 °C |
| Coolant | 45.8–46.6 °C | ~0.8 °C |

Roughly 40:1. On a shared axis spanning both, a 3 °C coolant climb occupies
about 2 px of a 26 px box, which destroys the signal the graph exists for.

Each series is therefore normalised to its own bounds. The cost is explicit and
accepted: **heights are not comparable between traces.** The plot carries no
axis labels and never has, and the real numbers are in the rows directly above
it, so the reader takes shape and correlation from the graph and values from the
rows. Plotting ΔT (CPU minus coolant) on a shared axis was considered as the
alternative and is recorded below.

## Requirements

### R1 — CPU trend series

- Plot a trailing mean of CPU temperature over `CPU_AVERAGE_WINDOW` samples
  (12 at the 5 s cadence = 60 s).
- A partial window is averaged as-is, so the trace starts on the first sample
  rather than after a minute of blank graph.
- The CPU **row** keeps showing the instantaneous reading. Only the graph is
  smoothed.
- No sample is recorded when CPU temperature is unavailable.

### R2 — Multi-series sparkline

`Sparkline` takes named series registered with a colour, pen width, and minimum
span. Draw order is registration order, so the primary series registers last and
paints on top. Each series normalises to its own bounds, reusing the existing
5 °C minimum span. Operations on an unregistered key are no-ops rather than
errors.

### R3 — Legend

There is no room for a real legend. The CPU row's value label is painted in the
CPU trace colour, and the coolant row's value already carries its band colour, so
the mapping from row to trace is visible without spending vertical space. The CPU
colour is a muted steel blue: coolant stays the trace the eye lands on.

CPU remains ungraded — the colour identifies the trace, it does not signal
severity. A high boost temperature is normal and grading it would flag every
compile.

### R4 — Graph visibility

The sparkline shows when **any** series has data. This amends spec 017 AC11,
which hid the graph whenever coolant was absent. A fan controller with no cooler
now still gets a CPU trend line.

### R5 — Degraded state

The CPU trace dims with the rest of the section when a working daemon goes away,
and returns to its normal colour on recovery, matching the coolant trace.

### R6 — Docs, version, tests

README section and changelog updated, version bumped in source and README, tests
covering the averaging, the scaling, and the legend.

## Acceptance Criteria

- [x] AC1 — Rendering CPU readings 60, 60, 60, 100 plots 60, 60, 60, **70**,
      while the CPU row still reads `100.0 °C`.
- [x] AC2 — The first CPU reading produces a sample immediately, averaged over
      the partial window.
- [x] AC3 — Readings older than `CPU_AVERAGE_WINDOW` stop contributing: a full
      window of 100 °C followed by a full window of 50 °C ends at exactly 50.
- [x] AC4 — The CPU row's value label carries `COLOR_CPU`.
- [x] AC5 — Series scale independently: CPU samples 60/95 give bounds
      (60.0, 35.0) while coolant samples 45/46 give (43.0, 5.0) under the
      minimum-span floor.
- [x] AC6 — The graph is visible when only the CPU trace has data, and hidden
      only when neither trace does. (Amends 017 AC11.)
- [x] AC7 — The CPU trace dims to `COLOR_DIM` when the daemon goes away and
      returns to `COLOR_CPU` on recovery.
- [x] AC8 — `add_sample` and `set_color` on an unregistered series key are
      no-ops.
- [x] AC9 — Both traces paint together without raising.
- [x] AC10 — Full test suite passes on system python.
- [x] AC11 — README documents the second trace, the smoothing window, and the
      not-comparable-heights caveat; version matches between source and README;
      changelog entry present.
- [x] AC12 — Live run against the daemon shows the CPU row at its instantaneous
      value while the plotted trace holds the smoothed value, with independent
      per-series bounds, captured in the validation report.

## Risks & Assumptions

- **Risk: heights read as comparable.** The chief cost of independent scaling. A
  viewer could infer that a CPU line above a coolant line means CPU is hotter,
  which happens to be true here but is not what the pixels mean. Mitigated by
  the colour-coded rows carrying the real numbers directly above the plot, and
  by documenting the caveat in the README and the class docstring. Not fully
  eliminated.
- **Assumption: 60 s is the right window.** Long enough to flatten compile
  spikes, short enough to still show a sustained load ramp within the 5-minute
  view. Tunable in one constant.
- **Risk: two traces crossing become hard to read.** Mitigated by the muted CPU
  colour and a thinner pen (1.0 vs 1.5), so the coolant trace stays dominant
  where they overlap.
- **Rollback**: revert the commit. No config, no persisted state, no new
  dependency. The sparkline's history is in-memory only.

## Alternatives Considered

- **Shared °C axis.** Honest, and it would show the CPU-to-coolant delta
  directly. Rejected: at the measured 40:1 variance ratio it flattens coolant to
  about 2 px of a 26 px box.
- **Plot ΔT (CPU − coolant) instead of CPU.** Arguably the better diagnostic —
  rising ΔT points at the mount or pump, both rising together points at case
  heat soak — and its small range coexists with coolant on one axis. Rejected as
  less intuitive than a plain CPU trend for the primary at-a-glance use. Worth
  revisiting if the delta ever becomes the question being asked.
- **A second stacked mini-graph.** Rejected: costs vertical space in a widget
  whose whole point is being compact.
