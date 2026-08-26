# Spec 016: Multi-account Claude usage rows

> **Note**: This work has no associated issue tracker ticket (personal public repo, per project policy).

## Status: COMPLETE

## Problem

The Claude Code section reads a single credential store (`~/.claude/
.credentials.json`) and renders one progress bar plus one stats row. Claude Code
now supports more than one OAuth login on the same machine, selected by
`CLAUDE_SECURESTORAGE_CONFIG_DIR`, which relocates only the credential store and
leaves the rest of `~/.claude` shared. On this host that yields two profiles,
reached by the `claude-max` and `claude-work` wrappers.

With two logins configured the section reports one account and silently ignores
the other, even though each has independent rate limits and independent spend.

Discovery, account-type labeling and the per-account fetch are shared with the
standalone widget. The rationale and the full acceptance list live once in the
companion spec — see
`../claude-usage-widget-windows/specs/011-multi-account-usage.md`.
`accounts.py` is copied verbatim between the two projects, exactly as
`usage_shape.py` is under spec 015.

## Requirements

1. Autodetect every configured credential store; no configuration step.
2. Render one row per account **inside the existing `ClaudeSection`**. This is
   not a new section, and the section header stays a single "Claude Code" title.
3. Each row identifies its account by profile name and account type
   (Pro / Max / Team / Enterprise / Free). The type is shown as a single letter
   to spend as little of the panel's fixed width as possible; the full type is
   on the row's tooltip.
4. Per-account failures stay local: one account expired or offline must not
   blank the other's row.
5. With a single account configured, the section renders as it does today.

## Acceptance Criteria

- [x] The Claude section renders one row per discovered account, within the
      existing `ClaudeSection` frame
- [x] No new top-level section is added; the "Claude Code" header appears once
- [x] Each row carries a profile-name + one-letter account-type label, with the
      full type available on the tooltip
- [x] A row shows a rate-limit reading or a credits reading according to that
      account's own shape (spec 015 detection, applied per account)
- [x] An error on one account renders in that account's row only
- [x] Per-account OAuth backoff state; the existing backoff warning icon
      reflects any account in backoff
- [x] Rows are rebuilt when the set of discovered accounts changes, without
      restarting the app
- [x] Section height adapts to the row count without clipping the sections
      below it
- [x] With one account configured, the section is visually unchanged
- [x] Acceptance: with the current box state (both stores holding the same
      Enterprise OAuth), the section shows two rows, both labeled Enterprise,
      with identical usage numbers

## Risks & Assumptions

- **Assumption**: profile stores live at `~/.claude-credentials/<name>/
  .credentials.json`, the convention set by the `claude-max` / `claude-work`
  wrappers. `CLAUDE_SECURESTORAGE_CONFIG_DIR` is per-process and cannot be
  enumerated, so the directory layout is the only discoverable source.
- **Risk**: the widget is a fixed-size KDE panel companion. Adding rows changes
  its height; the layout must grow rather than clip neighbours. Verified
  visually as part of acceptance.
- **Risk**: N accounts means N API calls per poll. The existing poll cadence and
  cache are retained per account.
- **Rollback**: display-only change to a user-launched desktop app. Revert the
  commit and relaunch; the section falls back to a single-account read and
  there is no persisted state to unwind.
