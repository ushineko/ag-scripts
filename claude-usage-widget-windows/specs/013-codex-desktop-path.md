# Spec 013: Codex desktop-path discovery

**Issue:** [#17](https://github.com/ushineko/ag-scripts/issues/17)

## Context

Desktop launchers provide a smaller PATH than interactive shells. On this
machine Codex is installed under `~/miniforge3/bin`, so the peripheral monitor
hid its Codex section even though terminal viewers found the CLI.

## Requirements

- Resolve an explicit `CODEX_PATH` first, then PATH, then common per-user
  installation directories.
- Use the resolved path for both detection and app-server startup.
- Keep both provider-module copies byte-identical.
- Preserve missing-CLI behavior.

## Acceptance Criteria

- A process whose PATH omits Miniforge still finds `~/miniforge3/bin/codex`.
- Explicit and PATH-based installs retain priority.
- Tests cover each discovery outcome.
- The installed peripheral monitor shows Codex after restart.

## Risks

- Common-directory discovery is necessarily finite. `CODEX_PATH` covers custom
  installations without modifying desktop files.

## Alternatives Considered

- Hard-coding this machine's PATH into the desktop entry would fix one install
  but leave other desktop launchers broken.

## Technical Notes

Executable candidates must exist and be executable. No shell is involved.

## Executive Summary

Make Codex discovery work consistently from terminals and desktop launchers.

## Status

Complete.
