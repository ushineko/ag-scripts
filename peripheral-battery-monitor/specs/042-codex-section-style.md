# Spec 042: Codex section style parity

**Issue:** [#19](https://github.com/ushineko/ag-scripts/issues/19)

## Context

The Codex section rendered outside the peripheral monitor's shared stylesheet.
At transparent window settings, desktop content showed through the frame and
its typography and spacing did not match the adjacent Claude section.

## Requirements

- Share Claude's frame, title, reset, stats, refresh-button, and layout styles.
- Include the same terminal icon and progress-bar colors.
- Respond to opacity and font-scale changes with the rest of the monitor.
- Preserve Codex-specific values and last-good behavior.

## Acceptance Criteria

- Codex and Claude have matching frame backgrounds, borders, radii, margins,
  header spacing, icon treatment, and text hierarchy.
- Codex remains readable when the top-level window is fully transparent.
- Color thresholds match the Claude progress bar.
- Full peripheral tests and an offscreen render pass.

## Risks

- Qt selector grouping must continue to cascade from the parent widget.

## Alternatives Considered

- An independent inline stylesheet was rejected because it had already drifted
  from the monitor's opacity and font-scale settings.

## Technical Notes

Codex keeps its own object names but shares grouped selectors with Claude.

## Executive Summary

Make the Codex section visually indistinguishable from the existing monitor
sections apart from its provider label and data.

## Status

Complete.
