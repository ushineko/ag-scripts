# Spec 010: Show credit spend alongside the gauges in the `limits` shape

> **Note**: This work has no associated issue tracker ticket (personal public repo, per project policy).

## Status: COMPLETE

## Problem

Spec 009 resolves display shapes in order: live rate-limit buckets win over
credit spend. That is correct at a month boundary — credits reset to $0, so
there is nothing to show — but it creates a blind spot in the middle:

**If buckets are live *and* credits are already spent, the dollar figure
disappears entirely.** That is exactly when it matters most. Verified against
the current code:

```
buckets live + $2.79 spent  ->  shape=limits
  Claude 5h 70% · 7d 25% · reset … · opus 12%      <- no dollar figure anywhere
```

On this account the two are not expected to overlap (once the monthly allowance
is exhausted the buckets go null and stay null until the reset), so this is a
narrow window rather than a daily occurrence. But the failure mode is silent —
the money stops being displayed rather than displaying as zero — which makes it
worth closing.

## Decision

In the `limits` shape, append an optional **credits segment** to the `--tui` /
`--line` output when `credits_view()` reports spend **greater than zero**.

- **Zero spend renders nothing.** At a month boundary the segment is simply
  absent, so the normal personal-account line is byte-identical to today's.
- **Drops first under width pressure.** It goes at the head of `drop_order`, so
  it can never displace an existing segment on a narrow pane. The gauges, reset
  countdown, and per-model breakdown all outrank it.
- **Compact form**: `$25.67` — the used figure only. The cap and percentage are
  already available in the `credits` shape and would crowd a line that is
  simultaneously showing two gauges.
- **Severity-styled**, reusing `_severity_style()` from spec 009, so a
  concerning spend still reads as concerning next to healthy gauges.

The same segment is added to `_stat_segments()`, which feeds the full-width
`--tui` bar view, under the same zero-spend condition.

### Scope

`--tui` / `--line` only. The GUI widget (`widget.py`), the tray tooltip
(`tray.py`), and `peripheral-battery-monitor` share the same blind spot but are
**not** changed here — their layouts are fixed-label rather than
droppable-segment, so closing the gap there is a different design question.
Noted in Out of scope.

## Implementation

`src/tui.py` only:

1. `build_line()` — in the `limits` path, after the `model` segment, append
   `("credits", Text(f"${used:.2f}", style=_severity_style(severity)))` when
   `credits_view(data)` is non-None and `used > 0`.
2. `drop_order` — becomes `["credits", "note", "model", "reset", "7d"]`.
3. `_stat_segments()` — same conditional append for the full `--tui` view.

No changes to `usage_shape.py`, so the byte-identical copy shared with
`peripheral-battery-monitor` (spec 015) stays in sync.

## Acceptance Criteria

- [x] `limits` payload with `spend.used > 0` renders a `$X.XX` segment in `build_line`
- [x] `limits` payload with `spend.used == 0` renders **no** credits segment
- [x] `limits` payload with no `spend` key at all renders no credits segment and does not raise
- [x] The zero-spend / no-spend line is byte-identical to the pre-change output (no regression for personal accounts)
- [x] The credits segment is the **first** thing dropped as width shrinks — a width that fits `7d` + `reset` + `model` without credits still shows all three
- [x] `build_line` output never exceeds the requested width for any shape at widths 100/60/40/24/12
- [x] `_stat_segments` includes the credits figure under the same condition
- [x] The `credits` shape is unchanged — it already leads with the dollar figure
- [x] Existing spec-009 tests pass unmodified

## Risks & Assumptions

- **Rollback**: revert the commit; the strip is relaunched per pane, so nothing persists.
- **Assumption**: `spend` remains populated while buckets are live. If the API
  omits `spend` entirely in that state, the segment simply never appears — the
  guard is presence-based, so this degrades to today's behavior rather than
  raising.
- Dropping first means the figure is invisible on a narrow pane. Accepted: the
  usage strip runs full-width under yazi, and the alternative (displacing a
  gauge) is worse.
- No new dependencies, no network changes, no credential handling.

## Out of scope (future)

- The same blind spot in `widget.py`, `tray.py`, and `peripheral-battery-monitor`.
  Those use fixed labels rather than droppable segments, so showing credits
  there means either a new widget or overloading an existing label — a layout
  decision, not a one-line addition.
