# Spec 011: Multi-Account Usage Display

## Context

The usage monitors read a single credential store and render a single reading.
Claude Code now supports more than one OAuth login on the same machine: the
credential store is selected by `CLAUDE_SECURESTORAGE_CONFIG_DIR`, which
relocates only `.credentials.json` and leaves the rest of `~/.claude` shared.
On this host that yields two profiles, launched by `claude-max` (the default
store) and `claude-work` (`~/.claude-credentials/work/`).

With two logins configured, a monitor that reads only `~/.claude` reports one
account and silently ignores the other. Both accounts have independent rate
limits and independent spend, so a single reading is not representative.

Account *type* also matters to the reader: a Max seat reports rate-limit
windows while an Enterprise seat reports only overage spend (spec 009), so two
lines can legitimately show different units. Labeling the type explains why.

## Requirements

1. Discover every configured credential store automatically, with no
   configuration step. Discovery covers the default store (`~/.claude`) and
   every profile directory under `~/.claude-credentials/`.
2. Fetch and render usage independently per discovered account.
3. Render one line per account, each identified by its profile name and its
   account type (Pro / Max / Team / Enterprise / Free). The type is rendered as
   a single letter (`M`, `E`, ...) to keep the label narrow — every tier Claude
   Code reports starts with a distinct letter, so the initial is unambiguous.
4. Per-account failures stay local: one account expired, rate-limited or
   offline must not blank or block the other.
5. A single configured account renders exactly as it does today (no label
   column, no visual regression).

## Acceptance Criteria

- [x] `accounts.discover()` returns both the default store and every
      `~/.claude-credentials/*/` profile that holds a `.credentials.json`
- [x] A profile directory with no `.credentials.json` is skipped, not reported
      as a broken account
- [x] The default store is reported first; remaining profiles follow in
      alphabetical order, so line order is stable between runs
- [x] `subscriptionType` maps to a display label: `pro`→Pro, `max`/`max_5x`/
      `max_20x`→Max, `team`→Team, `enterprise`→Enterprise, `free`→Free
- [x] An unknown or absent `subscriptionType` renders a neutral label rather
      than raising
- [x] OAuth refresh backoff state is tracked per account, so one account in
      backoff does not suppress refresh for another
- [x] Token refresh writes back to the originating account's store, never to
      the default store
- [x] Each line is labeled `<profile> <T>` where `T` is the one-letter type
- [x] `--line` emits one line per account
- [x] `--tui` renders one row per account, each with its own bar/stats
- [x] An error on one account renders that account's line as an error while
      other accounts still render their readings
- [x] With exactly one account configured, output is unchanged from current
      behavior
- [x] Unit tests cover discovery, label mapping, ordering, and per-account
      error isolation
- [x] Acceptance: with the current box state (both stores holding the same
      Enterprise OAuth), `--line` and `--tui` each show two lines, both labeled
      Enterprise, with identical usage numbers

## Risks & Assumptions

- **Assumption**: the profile-directory convention is `~/.claude-credentials/
  <name>/.credentials.json`, established by the `claude-max` / `claude-work`
  wrappers. Discovery keys on that layout; a store placed elsewhere is not
  found. `CLAUDE_SECURESTORAGE_CONFIG_DIR` itself is per-process and cannot be
  enumerated, so a directory convention is the only discoverable source.
- **Assumption**: the default store displays as profile `max`, matching the
  `claude-max` wrapper that reaches it. The store records no name of its own.
- **Risk**: N accounts means N API calls per refresh cycle. Existing per-call
  caching (spec 008) is retained per account so the cadence per account is
  unchanged; total request volume scales with account count.
- **Risk**: token refresh writes to a credential file that Claude Code may also
  be writing. This risk already exists single-account; it is not widened, but
  it now applies to each store.
- **Rollback**: revert the commit. Both frontends fall back to single-account
  reads with no migration or state change.

## Alternatives Considered

- Considered an explicit account list in config; rejected because the request
  is for autodetection and the directory convention already encodes it.
- Considered labeling by account email from `~/.claude.json`; rejected as it
  puts an address on a always-visible desktop widget and is wider than needed.

## Status: COMPLETE
