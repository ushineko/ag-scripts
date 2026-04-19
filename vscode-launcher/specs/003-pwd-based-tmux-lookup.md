# Spec 003: PWD-Based Tmux Lookup

**Status: COMPLETE**

## Description

Replaces the `VSCODE_LAUNCHER_TMUX_SESSION` env-var mechanism used in v1.0/v1.1 with a PWD-based lookup performed at shell startup by a new helper script, `vscl-tmux-lookup`.

## Problem

The v1.0/v1.1 flow was:

1. Launcher spawns `code --new-window <path>` with `VSCODE_LAUNCHER_TMUX_SESSION=<session>` in the child's environment
2. VSCode was expected to propagate that env to its integrated terminals
3. The zsh hook would read the var and attach/switch tmux

Confirmed by live observation: when a VSCode instance is already running, `code --new-window` signals the existing VSCode process (via its IPC socket) rather than spawning a fresh one. The new window inherits the *existing* VSCode process's environment, so `VSCODE_LAUNCHER_TMUX_SESSION` set on the `code` CLI invocation is dropped. The hook finds the variable empty and does nothing.

Additionally, even when env-var propagation works, `.code-workspace` files broke the mapping because the terminal's `$PWD` is one of the `folders[]` entries inside the workspace file, not the workspace file's own path.

## Solution

The hook no longer uses env vars at all. Instead:

1. `tmux_lookup.py` (installed as `vscl-tmux-lookup`) reads `~/.config/vscode-launcher/workspaces.json`, takes `$PWD` as an argument, and prints the matching tmux session name.
2. Lookup walks up parents of `$PWD` looking for the longest ancestor present in `tmux_mappings`.
3. If no direct match, it scans any `.code-workspace` keys in the mapping, parses their `folders[]` array (resolving relative paths against the workspace file's directory), and matches `$PWD` against each resolved folder.
4. The zsh hook invokes the helper when `TERM_PROGRAM=vscode`, and attaches or switches tmux clients based on the result.

## Requirements

### `tmux_lookup.py` (a.k.a. `vscl-tmux-lookup`)

- Runs as a CLI: `vscl-tmux-lookup <pwd>`
- Exit 0 + prints the session name if a match is found
- Exit 1 with no output otherwise
- Never raises — all errors swallowed to exit 1 (the script runs inside shell startup; a stack trace would break the shell)
- Reads `~/.config/vscode-launcher/workspaces.json` once per invocation
- Performs direct match + parent walk first (longest ancestor wins)
- Falls back to scanning `.code-workspace` entries and resolving their `folders[]` array
- Handles `.code-workspace` folder entries with:
  - Absolute paths: used as-is
  - Relative paths: resolved against the workspace file's directory
  - Malformed entries (missing `path`, non-dict, empty string): skipped

### Zsh hook

- Runs on shell startup (placed at the end of `~/.zshrc` between BEGIN/END markers)
- Only runs the lookup when `TERM_PROGRAM=vscode` to avoid overhead in non-VSCode terminals
- If `vscl-tmux-lookup` is not on PATH, silently does nothing
- If lookup returns a session name:
  - Outside tmux (`$TMUX` unset): `tmux attach -t <session>` and `return` from rc-file on success
  - Inside tmux: `tmux switch-client -t <session>` (idempotent)
- If lookup returns empty: shell starts normally (no noise)

### Launcher

- No longer sets `VSCODE_LAUNCHER_TMUX_SESSION` in the `code` subprocess env — the var is now unused
- `build_launch_env` helper removed
- Launcher just spawns `code --new-window <path>` as before

### Install / Uninstall

- `install.sh` symlinks `tmux_lookup.py` → `~/.local/bin/vscl-tmux-lookup` (alongside the existing `vscode-launcher` symlink)
- `install.sh` now **replaces** an existing hook block on reinstall (previously it skipped) so users pick up hook fixes without manual editing
- `uninstall.sh` removes the `vscl-tmux-lookup` symlink

## Acceptance Criteria

- [x] `vscl-tmux-lookup /path/to/mapped/folder` prints the session name and exits 0
- [x] `vscl-tmux-lookup /path/to/mapped/folder/subdir` prints the same session (parent walk works)
- [x] `vscl-tmux-lookup /path/to/folder/resolved/from/code-workspace` prints the correct session
- [x] Longest-match wins when both an ancestor and a descendant are mapped
- [x] Siblings (e.g. `/a/bcd` vs. `/a/b`) are not treated as children (no prefix-string bug)
- [x] `vscl-tmux-lookup` returns exit 1 with no output for unmapped paths
- [x] `vscl-tmux-lookup` never raises even on corrupted config, missing file, or missing .code-workspace file
- [x] Zsh hook replaces the prior env-var logic and calls the helper only inside VSCode terminals
- [x] `install.sh` symlinks `vscl-tmux-lookup` and updates the hook block on reinstall
- [x] `uninstall.sh` removes the `vscl-tmux-lookup` symlink
- [x] Launcher no longer sets `VSCODE_LAUNCHER_TMUX_SESSION`; `build_launch_env` is removed
- [x] Full test suite passes (47 tests): all prior behavior + 15 new `tmux_lookup` tests

## Implementation Notes

- `is_under(child, parent)` uses `os.sep`-suffix check to reject sibling prefixes like `/a/bcd` vs. `/a/b`
- `resolve_workspace_folders` tolerates JSON errors, missing files, non-dict entries, and empty `path` strings without raising
- The helper adds ~10–30 ms to shell startup inside VSCode terminals (Python interpreter spin-up + small JSON parse). Negligible for the expected use case.
- `TERM_PROGRAM=vscode` is set by VSCode for all integrated terminals and is reliable across versions

## Alternatives Considered

- **Keep env-var, require VSCode to be killed before launching**: user-hostile, and the launcher explicitly exists to make launching faster
- **`--user-data-dir`** to force a fresh VSCode process per launch: fragments extensions/settings per workspace, bad UX
- **Write `terminal.integrated.env.linux` per workspace** into VSCode's settings: invasive, fragile, hard to clean up
- **Parse `.code-workspace` at launcher time** and write folder-level mappings into config: doable but loses the "config file is user-readable and reflects what they chose" property. The lookup-time resolution is stateless.
