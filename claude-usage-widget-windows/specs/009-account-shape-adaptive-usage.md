# Spec 009: Account-shape-adaptive usage display (personal vs enterprise)

> **Note**: This work has no associated issue tracker ticket (personal public repo, per project policy).

## Status: COMPLETE

## Problem

On an enterprise/org-provisioned seat the `/api/oauth/usage` response no longer
populates the per-user rate-limit buckets the widget is built around. Every
frontend crashes on the first update:

```
AttributeError: 'NoneType' object has no attribute 'get'
  src/main.py:149  util_5h = five_hour.get("utilization")
```

The cause is `data.get("five_hour", {})`. The `{}` default fires only when the key
is **absent**; the API returns the key **present with value `null`**, so `.get()`
yields `None` and the chained `.get()` raises. Verified live on
`nick.verenini@attackiq.com` (2026-08-25).

Observed response shape on that account:

| field | value |
|---|---|
| `five_hour`, `seven_day`, `seven_day_opus`/`_sonnet`/`_cowork`/`_oauth_apps`/`_omelette` | all `null` |
| `tangelo`, `iguana_necktie`, `omelette_promotional`, `cinder_cove`, `amber_ladder` | all `null` |
| `nimbus_quill` | dict, but `utilization: 0.0` and **every** other field `null` — an empty placeholder, not live data |
| `limits` | `[]` |
| `member_dashboard_available` | `true` |
| `spend` | live — `used.amount_minor: 279`, `limit.amount_minor: 20000`, `percent: 1`, `severity: "normal"` |
| `extra_usage` | live — `used_credits: 279.0`, `monthly_limit: 20000`, `utilization: 1.395` |

The account is a seat on an org plan: `can_purchase_credits: false`,
`can_toggle: false`, `member_dashboard_available: true`. Per-seat rate-limit
windows are not surfaced to members; the only live figure is the member's own
overage spend against an org-provisioned monthly credit cap.

The request is a bare `GET` with `Authorization: Bearer <user token>` and no org
parameter (`src/oauth.py:317`), so the figure is **the individual member's**
spend, not the organization's.

Claude Code's own `/usage` screen already handles this: it renders a
`Usage credits` bar ($2.79 / $200.00, 1% used) and omits the 5h/7d gauges
entirely, because there is nothing to draw. This spec brings the widget to the
same behavior instead of crashing.

## Decision

Probe the response and adapt, rather than branching on account type. Account
type is not directly reported, and the bucket names visibly rotate
(`tangelo`, `nimbus_quill`, `cinder_cove`, … are obfuscated and change), so
**keying on data presence is more durable than keying on identity.**

Three display shapes, resolved in order:

1. **`limits`** — at least one live rate-limit bucket. Render the existing 5h/7d
   gauges. This is today's personal-account behavior, unchanged.
2. **`credits`** — no live buckets, but `spend.enabled` is true. Render a credits
   meter: `$X / $Y spent`, percent, severity-driven color.
3. **`unavailable`** — neither. Render `--` and a non-error "no usage data"
   state. Not an error: the fetch succeeded, there is simply nothing to show.

### Liveness rule for a bucket

A bucket counts as live when it is a dict **and**:

```
bucket.get("utilization") is not None
and (bucket.get("resets_at") is not None or bucket.get("utilization") > 0)
```

The `resets_at` clause is what excludes `nimbus_quill` (`utilization: 0.0`,
`resets_at: null`) — a real rate-limit window always carries a reset timestamp.
The `utilization > 0` escape hatch avoids hiding a genuinely live bucket that
happens to omit its reset time.

This is a heuristic. Log any non-null bucket rejected by it at debug level under
`usage_bucket_rejected` so a future shape change is diagnosable from logs rather
than from a crash.

### Shared helper

Add `src/usage_shape.py` with no Qt or I/O dependency, so it is unit-testable and
copyable verbatim into `peripheral-battery-monitor` (see spec 015 there):

```python
def bucket_is_live(bucket: object) -> bool: ...
def detect_shape(data: dict) -> str:            # "limits" | "credits" | "unavailable"
def live_buckets(data: dict) -> dict[str, dict] # non-null, live buckets by key
def credits_view(data: dict) -> dict | None     # {used, limit, percent, severity, currency, resets_at}
def next_month_reset(now: datetime) -> datetime # first of next month, local tz
```

`credits_view` reads `spend` (not `extra_usage`). Both carry identical numbers,
but `spend` is the better source: it exposes `severity` (maps onto the existing
`usage_color()` logic) and handles currency via explicit `amount_minor` +
`exponent`, rather than requiring reassembly from `used_credits` +
`decimal_places`. Convert with `amount_minor / 10**exponent`.

### Reset date for the credits shape

The payload carries no reset field for the credit cap — a full walk of the
response for `reset`/`expire`/`period`/`month` keys finds only
`nimbus_quill.resets_at: null`. Claude Code displays `Resets Sep 1
(America/Los_Angeles)`, i.e. it computes first-of-next-month in local time.
`next_month_reset()` does the same. Label it as a derived value in code comments
so it is not mistaken for API data.

## Implementation

Null-guard every site first — that alone stops the crash and is independently
revertable:

| file | lines | current |
|---|---|---|
| `src/main.py` | 146–147 | `data.get("five_hour", {})` |
| `src/tray.py` | 136–137 | same |
| `src/widget.py` | 276–277 | same |
| `src/tui.py` | 134–135, 189–190 | same, incl. two chained one-liners |
| `src/tui.py` | 268–271 | **`build_tui_view`** — a different pattern the grep above misses |

Replace `data.get(k, {})` with `data.get(k) or {}` throughout (11 sites).

`build_tui_view` was not in the original survey: it guards with
`if "five_hour" not in data` and then indexes `data["five_hour"]` directly. The
key *is* present (with value `null`), so the guard passes and the index yields
`None`. Found by exercising the function against the enterprise fixture rather
than by grep — a reminder that the `, {}` grep is necessary but not sufficient
for finding this defect class.

Then route each of the four frontends through `detect_shape()`:

- `main.py` (`--no-gui` console) — print gauges, or credits line, or "no usage data".
- `widget.py` (floating GUI) — the primary display.
- `tray.py` (tray tooltip/menu).
- `tui.py` (`--tui`/`--line` herdr strip) — must stay within its one-line budget
  in `--line` mode; credits render as `$2.79/$200 (1%)`.

The cached payload (spec 008) is unaffected — it stores the raw response, and
shape detection happens at display time. A cache written on one account shape and
read on another therefore behaves correctly with no cache versioning.

## Acceptance Criteria

- [x] `python -m src.main --no-gui` exits 0 on the enterprise account and prints the credits line, not a traceback
- [x] `bucket_is_live()` returns `False` for `{"utilization": 0.0, "resets_at": None, ...}` (the `nimbus_quill` placeholder)
- [x] `bucket_is_live()` returns `True` for `{"utilization": 70.0, "resets_at": "2026-02-16T22:00:00+00:00"}`
- [x] `detect_shape()` returns `"credits"` for a captured enterprise payload fixture
- [x] `detect_shape()` returns `"limits"` for a captured personal payload fixture
- [x] `detect_shape()` returns `"unavailable"` when buckets are null and `spend.enabled` is false
- [x] `credits_view()` converts `amount_minor: 279, exponent: 2` to `2.79` and `20000` to `200.00`
- [x] `next_month_reset()` returns Sep 1 local for any instant in August, and Jan 1 of the following year for December
- [x] All four frontends (`--no-gui`, GUI, tray, `--tui`) render without exception against both fixtures
- [x] `--line` credits output fits the single-line budget
- [x] No `data.get("<bucket>", {})` occurrences remain in `src/` (grep clean)
- [x] **Integration**: a real `--fetch-json` against the live `/api/oauth/usage` endpoint returns a payload that `detect_shape()` classifies as `credits` on this account, and the console mode renders it — not a mocked response
- [x] Existing personal-account tests still pass unmodified

## Risks & Assumptions

- **Rollback**: revert the commit. The widget is a user-launched process with no
  persistent state beyond the spec-008 cache, which is raw-payload and
  shape-agnostic — nothing to migrate back.
- **Heuristic risk**: the liveness rule could in principle reject a real bucket
  that reports `utilization: 0` with a null `resets_at`. The debug log line makes
  this visible. Consequence is a missing gauge, not a crash.
- **Bucket names rotate.** `nimbus_quill` and friends are obfuscated and expected
  to change. Nothing in this design hardcodes them; that is the point.
- **Assumption**: `spend` remains the enterprise-facing figure. If Anthropic moves
  members to the dashboard endpoint entirely, `detect_shape()` degrades to
  `unavailable` rather than crashing — acceptable.
- **Not verified**: behavior on a Team (non-enterprise) plan, or on an account
  that has both live buckets and live spend. The ordered resolution means buckets
  win if both are present, which matches Claude Code's display.
- No credential handling changes; `oauth.py` token flow is untouched.

## Alternatives Considered

- **Key on `member_dashboard_available` / `can_toggle` to detect enterprise.**
  Rejected: these are permission flags, not a data contract, and an account could
  plausibly report both a dashboard and live buckets. Presence-based detection
  handles that case without a second rule.
- **Key on `extra_usage` instead of `spend`.** Rejected: identical numbers but a
  weaker shape — no `severity`, and currency requires reassembly from
  `decimal_places`.
- **Treat any non-null bucket as live.** Rejected: `nimbus_quill` would render a
  permanent, meaningless 0% gauge.

## Out of scope (future)

- The member dashboard endpoint implied by `member_dashboard_available: true`.
  That is the only route back to genuine per-user consumption (and therefore to
  leading-indicator limit warnings) on an enterprise seat, but it is a separate
  endpoint with unknown shape and likely different auth scope. Worth a spec of
  its own if the credits meter proves insufficient.
- Deduplicating the OAuth fetch, which is currently copied between this project
  and `peripheral-battery-monitor`. See spec 015 there.
