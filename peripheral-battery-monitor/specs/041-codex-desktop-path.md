# Spec 041: Codex desktop-path discovery

**Issue:** [#17](https://github.com/ushineko/ag-scripts/issues/17)

## Context

The desktop-launched peripheral monitor cannot see a Miniforge-installed Codex
CLI because its PATH is intentionally smaller than an interactive shell's.

## Requirements

- Mirror the standalone provider's expanded executable discovery.
- Detect Codex without modifying the desktop environment globally.
- Verify the installed process after restart.

## Acceptance Criteria

- The section is created when Codex exists under `~/miniforge3/bin`.
- App-server launches through the resolved absolute path.
- Provider files remain byte-identical.

## Risks

- None beyond maintaining the small candidate list.

## Alternatives Considered

- Editing the launcher PATH was rejected as machine-specific configuration.

## Technical Notes

The implementation remains in the shared provider module.

## Executive Summary

Allow the installed desktop monitor to find the same Codex CLI as the TUI.

## Status

Complete.
