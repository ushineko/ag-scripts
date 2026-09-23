# Spec 014: Multi-provider TUI alignment

**Issue:** [#21](https://github.com/ushineko/ag-scripts/issues/21)

## Context

Each TUI row previously built an independent Rich grid. Different label and
stats widths made Claude and Codex bars begin and end at different columns.

## Requirements

- Render all account and provider rows in one shared table.
- Separate account/provider and allowance-window columns.
- Align progress bars, stats, and reset text across mixed payload shapes.
- Preserve single-row and compact error rendering.

## Acceptance Criteria

- Mixed Claude rate-limit, Claude credits, and Codex bars share a start column.
- Their stats share a start column and reset text remains right-aligned.
- Existing terminal rendering and cache tests pass.
- Alignment is asserted at a representative terminal width.

## Risks

- Very narrow panes may put more pressure on the fixed-content columns.

## Alternatives Considered

- Padding each independent grid was rejected because trailing stats would still
  change bar widths independently.

## Technical Notes

Provider payloads normalize into six shared columns: label, window, bar, stats,
flexible spacer, and reset/staleness.

## Executive Summary

Use one table so mixed Claude and Codex rows read as a single dashboard.

## Status

Complete.
