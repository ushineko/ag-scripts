# Spec 040: Codex usage provider

**Issue:** [#15](https://github.com/ushineko/ag-scripts/issues/15)

## Context

The peripheral monitor already embeds the shared Claude usage tracker. It
should also surface Codex allowance data from the supported Codex app-server.

## Requirements

- Reuse the standalone monitor's Codex client and provider-aware cache.
- Fetch Codex independently in the background update thread.
- Display a Codex section with a utilization bar, true window duration, reset
  countdown, and Business individual-limit percentage when present.
- Preserve the existing Claude section and isolate provider failures.
- Allow the Codex section to be enabled or disabled in settings.

## Acceptance Criteria

- When Codex is installed and signed in, the peripheral monitor shows its main
  allowance as a colored progress bar.
- The displayed reset and window duration match the app-server response.
- Manual refresh bypasses both provider cache gates.
- Disabling the Codex section removes it without affecting Claude.
- Unit tests cover worker results and rendering helpers.

## Risks

- Another external subprocess adds latency to the update worker; caching keeps
  normal polls inexpensive.

## Alternatives Considered

- Folding Codex into Claude account rows was rejected because the providers
  have different window and account shapes.

## Technical Notes

The provider module is mirrored verbatim between the standalone and peripheral
projects, following the existing shared `accounts.py`, `usage_shape.py`, and
`usage_cache.py` arrangement.

## Executive Summary

Add a separately toggleable Codex allowance section that follows the existing
Claude section's visual language.

## Status

Complete. Implementation, tests, live integration, and security review are
complete.
