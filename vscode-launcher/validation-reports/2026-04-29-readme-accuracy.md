# Validation Report — README Accuracy Pass

**Date**: 2026-04-29
**Scope**: Documentation-only — `vscode-launcher/README.md`
**No source code changed.**

## Summary

Five accuracy issues found by auditing the README against the current implementation (v3.1) and corrected:

1. **"Running workspaces" detection mechanism** — text claimed KWin scripting via D-Bus with `qdbus6` / `journalctl` dependencies. Updated to describe the v2.0 IPC-based detection (Unix domain socket, no `qdbus6` / `journalctl` in the read path). Stop / Activate buttons still use KWin scripting; that distinction is now explicit.
2. **Installation steps** — added the `vscl-tmux-lookup` symlink and the SVG icon install (with cache refresh) to the numbered list.
3. **Tmux hook detection** — updated description to reflect that the hook checks `VSCODE_INJECTION`, `VSCODE_PID`, or `TERM_PROGRAM=vscode` (not just the last), because tmux rewrites `TERM_PROGRAM` for nested invocations.
4. **Uninstallation steps** — expanded the inline summary to enumerate everything `uninstall.sh` actually removes (both symlinks, `.desktop`, autostart entry, icon, zsh hook block) plus the optional config-dir prompt.
5. **Requirements** — added `qdbus6` as an optional requirement scoped to the per-row Stop / Activate buttons (matches the warning in `install.sh`).

No version bump: behavior unchanged.

## Phase 3: Validation

- `pytest tests/` — **154 passed in 0.48 s**
- README rendered locally: TOC anchors and code fences intact.

## Phase 4: Code Quality

N/A — no source changes.

## Phase 5: Security Review

- No code changes → no new attack surface.
- README contains no credentials, tokens, or sensitive paths.
- Dependency surface unchanged.

## Phase 5.5: Release Safety

- **Rollback**: `git revert <commit>` — single commit, doc-only.
- Reversible in seconds with no data implications.

## Status

PASSED. Ready to commit and push.
