# Spec 001: macOS Support for vscode-gather

> **Note**: This work has no associated issue tracker ticket. Consider creating one for traceability.

**Status: COMPLETE**

## Problem

vscode-gather v1.0 gathers all VS Code windows onto a single monitor and
maximizes them. It is built entirely on KDE Plasma 6 / Wayland infrastructure:
KWin scripting via D-Bus for window manipulation, and `kscreen-doctor` for
monitor detection. None of these exist on macOS.

The primary development environment is Linux/KDE, but macOS is used as a roaming
platform when a Linux desktop isn't available. The tool should support macOS for
this multi-platform workflow, providing equivalent functionality: consolidate
scattered VS Code windows onto one display and maximize them.

## What vscode-gather Does Today (Linux/KDE)

1. **Detect primary monitor**: Parse `kscreen-doctor --outputs` for priority-1 output
2. **Generate KWin JS snippet**: Iterate `workspace.windowList()`, filter by
   `resourceClass`, call `workspace.sendClientToScreen()` + `setMaximize()`
3. **Execute via D-Bus**: `qdbus6 org.kde.KWin /Scripting loadScript` → `run` → `unloadScript`

Every step is KDE-specific. A macOS port requires replacing all three mechanisms.

## Empirical Validation (2026-06-21, macOS 26.5.0, M1 Max, VS Code 1.125.1)

The following strategies were tested on the target macOS machine:

| # | Strategy | Result | Detail |
|---|----------|--------|--------|
| 1 | `system_profiler SPDisplaysDataType -json` | **Confirmed** | Returns JSON with display name (`Color LCD`), resolution, and `spdisplays_main: spdisplays_yes` flag for primary detection |
| 2 | AppleScript window manipulation via `osascript` | **Blocked** | `osascript is not allowed assistive access` (error -25211). Requires Accessibility permission granted to the calling terminal app. Strategy is sound but untestable in sandboxed contexts |
| 3 | VS Code process name on macOS | **Confirmed** | Main process is `Code` (PID visible via `pgrep -la Code`). AppleScript filter `name is "Code"` is correct |
| 4 | `code --status` for window enumeration | **Confirmed** | Shows per-window info: `window [1] (Research MacOS support f… — ag-scripts (Workspace))`, `window [2] (Claude Code — clockwork-orange (Workspace))`. Useful as secondary validation tool |
| 5 | `code` CLI on PATH | **Required fix** | Was broken — `/usr/local/bin/code` was a stale symlink to a previously-installed Cursor. Repointed to `/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code`. Install script should verify this and warn |

**Note on Accessibility permissions**: Error -25211 confirms that `osascript`
(and by extension any terminal app calling it) must be listed in System Settings
→ Privacy & Security → Accessibility. This is a hard gate — the script will fail
without it. The install script must detect and guide the user through this.

## Research: macOS Window Management Approaches

### Option A: AppleScript / JXA (Recommended)

macOS has first-party scripting for window management via AppleScript or
JavaScript for Automation (JXA), accessed through `osascript`.

**Monitor detection**:
```bash
# List displays via system_profiler
system_profiler SPDisplaysDataType -json
```
Or use AppKit via Python:
```python
from AppKit import NSScreen
screens = NSScreen.screens()
main_screen = NSScreen.mainScreen()
```

**Window enumeration + manipulation**:
```applescript
tell application "System Events"
    set vscodeProcs to every process whose name is "Code"
    repeat with proc in vscodeProcs
        set allWindows to every window of proc
        repeat with w in allWindows
            -- Move to target display position and resize to fill
            set position of w to {targetX, targetY}
            set size of w to {targetWidth, targetHeight}
        end repeat
    end repeat
end tell
```

**Pros**: Ships with macOS, no dependencies, well-documented, stable API.
**Cons**: Requires Accessibility permissions (System Settings → Privacy &
Security → Accessibility). AppleScript is verbose; JXA (JavaScript) is cleaner.

**Accessibility permission**: The script (or Terminal.app / iTerm) must be granted
Accessibility access. This is a one-time user action. The install script should
detect and prompt for this.

### Option B: yabai (Third-party tiling WM)

[yabai](https://github.com/koekeishiya/yabai) is a tiling window manager for
macOS with a CLI for window queries and manipulation. Could replicate the
gather-and-maximize behavior with `yabai -m query --windows` and
`yabai -m window --display`.

**Pros**: Powerful, scriptable, JSON output.
**Cons**: Requires installation (not built-in), requires SIP partial disable for
full functionality, heavy dependency for a simple gather script.

### Option C: Hammerspoon (Lua scripting)

[Hammerspoon](https://www.hammerspoon.org/) exposes macOS Accessibility APIs via
Lua. Could enumerate windows and move/resize them.

**Pros**: Capable, good API.
**Cons**: Requires installation, Lua runtime, overkill for this use case.

### Recommendation

**Option A (AppleScript/JXA)** — zero dependencies, ships with macOS. The script
is simple enough that AppleScript's verbosity isn't a problem. Use `osascript`
from the bash script, mirroring how the Linux version uses `qdbus6`.

## Design Approach

### Architecture: Platform-branching in gather.sh

Keep a single `gather.sh` entry point with platform detection at the top. The
script's structure maps cleanly to platform-specific implementations:

```
gather.sh
├── detect_primary_output()
│   ├── Linux: kscreen-doctor --outputs (existing)
│   └── macOS: system_profiler or NSScreen via osascript
├── generate + run window manipulation
│   ├── Linux: KWin JS via qdbus6 (existing)
│   └── macOS: AppleScript via osascript
└── debug output
    ├── Linux: journalctl (existing)
    └── macOS: echo/log (direct output)
```

### Phase 1: Platform detection + macOS monitor detection

1. Add `PLATFORM` detection at script top (`uname -s` → `Darwin` vs `Linux`)
2. Branch `detect_primary_output()`:
   - Linux: existing `kscreen-doctor` implementation (unchanged)
   - macOS: Parse `system_profiler SPDisplaysDataType` or use main display
     coordinates. On macOS, the "main" display is the one with the menu bar —
     `system_profiler` marks it. For multi-monitor use, `--output` flag can
     accept a display name or index.

### Phase 2: macOS window gathering via AppleScript

3. Add `gather_macos()` function using `osascript` with AppleScript/JXA:
   - Enumerate VS Code windows via System Events
   - Get target display bounds (position + size)
   - Move each window to target display origin
   - Resize each window to target display dimensions (simulates maximize)
   - Print status for each window (matches Linux output style)
4. Wire into main flow: Linux path calls existing `generate_kwin_script` +
   `run_kwin_script`; macOS path calls `gather_macos`
5. Dry-run on macOS: print the AppleScript that would be executed

### Phase 3: Install/uninstall scripts

6. Update `install.sh` with platform branching:
   - Linux: `~/bin` symlink (unchanged)
   - macOS: `/usr/local/bin` symlink
   - macOS: Check for Accessibility permissions and warn if not granted
7. Update `uninstall.sh` with matching macOS cleanup

### Phase 4: Testing + docs

8. Test on macOS: verify window gathering works with multiple displays
9. Test on macOS: verify single-display case (gather = maximize all VS Code windows)
10. Update README with macOS requirements and usage notes
11. Note Accessibility permission requirement prominently

## macOS-Specific Considerations

### Accessibility Permissions

AppleScript window manipulation requires the calling app (Terminal.app, iTerm2,
etc.) to have Accessibility access. Without it, the script silently fails or
throws `-1719` errors.

The install script should:
1. Check if Accessibility is granted (heuristic: try a test AppleScript command)
2. If not, print instructions: "Grant Accessibility access to your terminal app
   in System Settings → Privacy & Security → Accessibility"
3. Optionally open the pref pane: `open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"`

### "Maximize" on macOS

macOS has no true "maximize" in the Linux/KDE sense. The closest equivalents:
- **Resize to screen bounds**: Set window position to display origin and size to
  display dimensions (minus menu bar and dock). This is what we want.
- **Green button / fullscreen**: Enters macOS full-screen mode (separate Space).
  This is NOT what we want — it hides other windows and changes Spaces.

The AppleScript approach (set position + set size) achieves the resize-to-fill
behavior without entering fullscreen mode.

### Display Identification

macOS identifies displays differently from Linux:
- Linux: output names like `DP-2`, `HDMI-1`
- macOS: display names from `system_profiler` (e.g., "Built-in Retina Display",
  "DELL U2723QE") or display IDs (numeric)

The `--output` flag on macOS should accept display names as shown by
`system_profiler`. Add a `--list-outputs` convenience flag to show available
display names on both platforms.

## Acceptance Criteria

- [x] `gather.sh` detects platform (`uname -s`) and branches accordingly (`PLATFORM`, `case` dispatch)
- [x] On macOS, detects the primary (main) display (`detect_primary_output_macos` via `NSScreen.mainScreen`; verified: "Built-in Retina Display (PRIMARY)")
- [x] On macOS, gathers all VS Code windows to the target display using AppleScript (`gather_macos` / `generate_applescript`)
- [x] On macOS, "maximizes" windows by resizing to fill display bounds (not macOS fullscreen) — sets position+size to `NSScreen.visibleFrame`
- [x] `--output` flag works on macOS (accepts display name; `get_display_bounds` matches `localizedName`, falls back to main). Note: matched against `NSScreen.localizedName` rather than `system_profiler`; names align. Help text corrected (the unimplemented "display index" form was removed).
- [x] `--class` flag works on macOS (mapped to process name; default `code` → `Code`)
- [x] `--dry-run` prints the AppleScript that would execute (verified; reordered so it no longer requires Accessibility)
- [x] `--debug` prints diagnostic info on macOS (display bounds + post-gather window positions)
- [x] `install.sh` handles macOS: `/usr/local/bin` symlink, Accessibility permission check (opens the pref pane if missing)
- [x] `uninstall.sh` handles macOS cleanup (removes the `/usr/local/bin` symlink)
- [x] Existing Linux/KDE functionality is not regressed (Linux KWin/D-Bus path unchanged)
- [x] README documents macOS requirements (Accessibility permissions) and usage (Requirements, macOS Notes, support matrix, changelog v2.0)

## Out of Scope

- Windows support
- Non-KDE Linux desktop environments (covered by vscode-launcher spec 010)
- Tiling/arrangement beyond gather-and-maximize
- Integration with yabai, Hammerspoon, or other third-party WMs

## Risk / Open Questions

1. **Accessibility permission UX**: First-time setup requires manual permission
   grant. There's no way to programmatically request it — the user must do it in
   System Settings. Empirically confirmed: error -25211 without it. The install
   script should prominently warn and offer to open the preference pane.
2. ~~**VS Code process name**~~: **Resolved** — confirmed as `Code` on macOS via
   `pgrep -la Code`. AppleScript filter `name is "Code"` is correct.
3. **Multi-display coordinates**: macOS uses a global coordinate space where the
   primary display's origin is (0,0) and other displays have positive/negative
   offsets. The AppleScript needs to correctly map display bounds. Needs testing
   with an external monitor.
4. **Dock and menu bar**: Window resize should account for dock position/size and
   menu bar height to avoid windows sliding under them. System Events may handle
   this via "visible area" vs "full area" bounds.
5. **`code` CLI on PATH**: May not be present by default — VS Code requires the
   user to run "Shell Command: Install 'code' command in PATH" from the command
   palette. Additionally, other editors (Cursor) can hijack the `/usr/local/bin/code`
   symlink. The install script should verify the symlink target points into
   `Visual Studio Code.app`.
