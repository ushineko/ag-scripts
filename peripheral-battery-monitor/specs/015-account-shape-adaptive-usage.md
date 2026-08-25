# Spec 015: Account-shape-adaptive Claude usage display (personal vs enterprise)

> **Note**: This work has no associated issue tracker ticket (personal public repo, per project policy).

## Status: INCOMPLETE

## Problem

The Claude usage section of the monitor crashes on an enterprise/org-provisioned
seat, for the same reason as the standalone widget. `/api/oauth/usage` returns the
per-user rate-limit buckets as `null`, and the display code assumes dicts:

```
peripheral-battery.py:1319   five_hour = usage_data.get("five_hour", {})
peripheral-battery.py:1322   five_pct  = five_hour.get("utilization", 0)   # AttributeError
```

`data.get(k, {})` only substitutes `{}` when the key is **absent**. The API sends
the key **present with value `null`**, so `five_hour` is `None` and line 1322
raises. Same defect at line 1308 (`self._last_good_usage.get("five_hour", {})
.get("resets_at", "")`), which additionally poisons the last-known-good path.

Lines 1355–1359 (`seven_day_opus` / `seven_day_sonnet`) are already guarded by
`if bucket and ...` and are **not** affected — that guard is the pattern the rest
of the section should adopt.

Full response analysis, the enterprise-seat evidence, and the endpoint scoping
argument are documented once in the companion spec — see
`../claude-usage-widget-windows/specs/009-account-shape-adaptive-usage.md`.
Summary: on this account only `spend` / `extra_usage` carry live figures
($2.79 of a $200.00 monthly credit cap), every rate-limit bucket is `null`, and
`nimbus_quill` is an empty placeholder (`utilization: 0.0`, all other fields
`null`) that must not be mistaken for a live bucket.

This project maintains its **own** copy of the OAuth fetch
(`peripheral-battery.py:58`, `CLAUDE_USAGE_URL`) independent of the widget's
`src/oauth.py`, so the fix has to land here too rather than being inherited.

## Decision

Adopt the same probe-and-adapt model as spec 009, with the identical liveness
rule and resolution order:

1. **`limits`** — at least one live bucket → existing `5h:` / `7d:` labels, unchanged.
2. **`credits`** — no live buckets but `spend.enabled` → credits meter.
3. **`unavailable`** — neither → `5h: --` / `7d: --`, treated as a normal empty
   state rather than an error (the fetch succeeded).

A bucket is live when it is a dict and:

```
bucket.get("utilization") is not None
and (bucket.get("resets_at") is not None or bucket.get("utilization") > 0)
```

Port `usage_shape.py` from the widget project **verbatim** as a module-local
helper (it is deliberately dependency-free — no Qt, no I/O). Do not re-derive
the logic: a second implementation of the same heuristic will drift. If the two
copies diverge later, that is the trigger to extract a shared package, which is
explicitly out of scope here.

### Display mapping

The section has three labels: `claude_five_hour_lbl`, `claude_seven_day_lbl`,
`claude_duration_lbl` (built at lines 711–719, written at 1240–1264 and
1319–1362). Under the `credits` shape:

- `claude_five_hour_lbl` → `$2.79 / $200` (used / cap)
- `claude_seven_day_lbl` → `1% used`
- `claude_duration_lbl` → `Resets Sep 1` (derived, see below)

This reuses the existing widgets and KDE styling rather than adding new ones, so
the layout and `ClaudeStats` object-name styling are untouched.

Color: drive from `spend.severity` (`normal` / elevated tiers) rather than
recomputing a threshold against percent, so the widget matches whatever the API
considers concerning.

### Reset date

The payload carries no reset field for the credit cap; a full key walk finds only
`nimbus_quill.resets_at: null`. Claude Code shows `Resets Sep 1
(America/Los_Angeles)`, computing first-of-next-month locally.
`next_month_reset()` reproduces that. The existing `get_time_until_reset()` /
`get_days_until_reset()` helpers (lines 103–128) take an ISO string and stay in
use for the `limits` shape; feed them the derived timestamp for `credits`.

## Implementation

1. Null-guard first — a standalone, independently revertable change:
   - line 1308 → `(self._last_good_usage.get("five_hour") or {})`
   - line 1319 → `usage_data.get("five_hour") or {}`
   - line 1320 → `usage_data.get("seven_day") or {}`
2. Add `usage_shape.py` alongside `peripheral-battery.py` (ported from spec 009).
3. Branch `_update_claude_labels` (the 1319–1362 block) on `detect_shape()`.
4. Leave the `seven_day_opus` / `seven_day_sonnet` loop as-is — already guarded,
   and it naturally renders nothing when those buckets are null.

## Acceptance Criteria

- [ ] The monitor starts and renders the Claude section on the enterprise account without an exception
- [ ] `bucket_is_live()` rejects `{"utilization": 0.0, "resets_at": None}` (the `nimbus_quill` placeholder)
- [ ] `bucket_is_live()` accepts `{"utilization": 70.0, "resets_at": "2026-02-16T22:00:00+00:00"}`
- [ ] `detect_shape()` returns `"credits"` for an enterprise payload fixture, `"limits"` for a personal one, `"unavailable"` when buckets are null and `spend.enabled` is false
- [ ] Under `credits`, the three labels read `$2.79 / $200`, `1% used`, `Resets Sep 1`
- [ ] Under `limits`, existing tests at `tests/test_battery_logic.py:591-631` still pass unmodified — `5h: 70%` and `7d: 25% (5d left)`
- [ ] The last-known-good path (line 1308) survives a null `five_hour` without raising
- [ ] `spend.severity` drives credit-meter color; no hardcoded percent threshold
- [ ] No `usage_data.get("<bucket>", {})` occurrences remain (grep clean)
- [ ] `usage_shape.py` is byte-identical to the widget project's copy
- [ ] **Integration**: a real fetch against the live `/api/oauth/usage` endpoint classifies as `credits` on this account and the GUI renders it — not a mocked response
- [ ] New unit tests cover both fixtures in `tests/test_battery_logic.py`, alongside the existing usage tests

## Risks & Assumptions

- **Rollback**: revert the commit and restart the monitor. No persistent state,
  no migration. The `.desktop` autostart entry is untouched.
- **Restart is free here**: the monitor is already down, so no live instance has
  to be displaced. `app-peripheral\x2dbattery\x2dmonitor@autostart.service` last
  ran 2026-08-18 and exited on SIGTERM (a clean shutdown, *not* this bug); it has
  been dead since. Verification therefore starts from a cold process.
- **Two autostart units exist for this program** and only one is correct:
  `peripheral-battery-monitor.desktop` (Jul 17) is the real entry;
  `peripheral-battery.desktop` (Jan 24) is a stale duplicate whose unit fails
  after ~553ms with exit 1, consistent with losing the spec-006 single-instance
  race. Out of scope for this spec, but it will make post-fix verification
  confusing — one unit will still show `failed` no matter what this change does.
  Clean it up separately.
- **Reproduction is confirmed, attribution is not.** Both crash sites (`:1308`,
  `:1322`) were replayed against a live `/api/oauth/usage` payload on 2026-08-25
  and both raise `AttributeError`. The bug would crash the monitor on its first
  usage refresh. The 2026-08-18 shutdown recorded in systemd was a SIGTERM and
  cannot be blamed on it; journals from that run have rotated away.
- **Duplication is accepted, deliberately.** Two copies of `usage_shape.py` and
  two copies of the OAuth fetch now exist. Extracting a shared package touches
  packaging for both projects (one of which is PyInstaller-frozen) and is not
  worth it for ~60 lines. Revisit if a third consumer appears.
- **Heuristic risk** and **rotating bucket names**: as spec 009. A rejected
  bucket costs a missing gauge, not a crash.
- No credential handling changes.

## Alternatives Considered

- **Import the helper from the widget project.** Rejected: the two live in
  separate directories with no shared install path, and the widget is frozen with
  PyInstaller — a cross-project import would not survive packaging.
- **Hide the Claude section entirely on enterprise accounts.** Rejected: the
  credits figure does move once plan limits are exhausted (verified — it went
  $0.94 → $2.79 within one session), so it is not inert and is worth surfacing.

## Out of scope (future)

- Extracting the shared OAuth fetch + shape helper into one installable package
  consumed by both projects.
- The member dashboard endpoint (`member_dashboard_available: true`) — see
  spec 009's out-of-scope note.
