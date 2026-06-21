# vscode-launcher

Bulk-launch VSCode workspaces directly from VSCode's own **Recent** list, with automatic window placement and tmux session switching. Primary target is CachyOS / KDE Plasma 6 (Wayland); macOS is supported as a roaming platform (CLI + menu bar, see [Platform support](#platform-support)).

Solves four recurring pain points:

- VSCode opens at a small default size every time. This tool maximizes it on the primary monitor.
- Each workspace has to be opened manually. This tool launches any number at once.
- A shared system-wide tmux server needs a manual `switch-client` after each launch. This tool wires the integrated terminal to the correct session automatically.
- Switching workspaces means alt-tabbing through every VSCode window. This tool surfaces an Alt-Tab-style quick-launcher popup behind a global hotkey, with running workspaces first.

## Table of Contents

- [Features](#features)
- [Platform support](#platform-support)
- [Requirements](#requirements)
- [Installation](#installation)
  - [Building the macOS app](#building-the-macos-app)
- [Usage](#usage)
- [How It Works](#how-it-works)
- [Configuration](#configuration)
- [Uninstallation](#uninstallation)
- [Changelog](#changelog)

## Features

- Reads your workspace list live from VSCode's own Recent history. Nothing to maintain by hand.
- **Tray-resident daemon** with a configurable global hotkey (default `Shift+Tab`). Tap to surface a quick-launcher popup; tap again to cycle through workspaces. Pause to commit. Mouse-click also commits.
- **Shows which workspaces are currently open**, with running ones sorted to the top and a `● running` badge. Activated workspaces bubble to the top of the running group on next view.
- **Per-row Start / Stop / Activate buttons**: Start (non-running) launches the workspace; Activate (running) raises and focuses its VSCode window; Stop (running) closes the window via KWin while leaving the main VSCode process alive.
- **Single-instance**: a second `vscode-launcher` invocation signals the running daemon to surface its main window over D-Bus, instead of starting a duplicate.
- PyQt6 GUI with multi-select checkboxes; bulk-launch with one click.
- Per-workspace tmux-session mapping, editable via a dropdown populated from `tmux list-sessions`.
- Hide / Unhide workspaces you don't want cluttering the launcher.
- Delegates window placement to the sibling [`vscode-gather`](../vscode-gather) tool. Each launched window is moved to the primary monitor and maximized.
- Installs a small zsh hook into `~/.zshrc` so the VSCode integrated terminal attaches to (or switches to) the correct pre-existing tmux session automatically.
- Never creates, kills, or renames tmux sessions. The shared system tmux server is left alone.

## Platform support

Linux/KDE is the primary platform and gets the full feature set. macOS is supported as a roaming platform for when a Linux desktop isn't available — the core PyQt6 tray/menu-bar UI, recent-project discovery, project launching, the quick-launcher popup, and the tmux hook all work. Platform-specific paths and APIs are centralized in `platform_support.py`.

| Capability | Linux/KDE | macOS |
| ---------- | --------- | ----- |
| Tray / menu-bar icon + menu | ✓ | ✓ (monochrome template icon, adapts to light/dark) |
| Recent-project discovery | `~/.config/Code/...` (+ `~/.vscode-shared` on 1.119+) | `~/Library/Application Support/Code/...` (+ `~/.vscode-shared`) |
| Launch / open project | ✓ | ✓ (`code` CLI) |
| Quick-launcher popup + global hotkey | ✓ (KGlobalAccel) | ✓ (Carbon `RegisterEventHotKey`; default `⌘⇧Space`) |
| Running-state detection (IPC socket) | `$XDG_RUNTIME_DIR/vscode-*-main.sock` | `~/Library/Application Support/Code/*-main.sock` |
| Launched column (process start time) | `/proc` | `psutil` (optional; shows `—` if absent) |
| Autostart | XDG autostart `.desktop` | LaunchAgent plist |
| Activate (raise an open window) | ✓ (KWin) | ✓ (via `code <path>`) |
| Per-row Stop, auto window placement | ✓ (KWin) | not available (KDE/KWin-specific) |

## Requirements

- KDE Plasma 6 (Wayland) — primary platform; or macOS (roaming platform, see [Platform support](#platform-support))
- Python 3 with PyQt6
- VSCode. Reads `~/.vscode-shared/sharedStorage/state.vscdb` on 1.119+, falling back to per-profile `globalStorage/state.vscdb` (`~/.config/Code/User/...` on Linux, `~/Library/Application Support/Code/User/...` on macOS) on older releases
- `code` (VSCode CLI) on `PATH`. On macOS, install it via VSCode's *Shell Command: Install 'code' command in PATH* — the installer warns if the `code` symlink has been hijacked by another editor
- `qdbus6` (Linux only, optional — only needed for the per-row Stop / Activate buttons, which use KWin scripting)
- `psutil` (macOS only, optional — powers the Launched column's per-window start time; the column shows `—` without it)
- `pyinstaller` (macOS only, build-time — needed to build the `.app` bundle; not a runtime dependency)
- `tmux` (optional — only needed for session switching)
- `vscode-gather` (Linux only, optional — only needed for auto-placement / maximize)
- zsh (the shell hook targets zsh; bash support could be added later)

## Installation

```bash
./install.sh
```

`install.sh` detects the platform (`$OSTYPE`) and installs accordingly.

**On Linux/KDE**, this:

1. Symlinks `vscode_launcher.py` to `~/.local/bin/vscode-launcher`
2. Symlinks `tmux_lookup.py` to `~/.local/bin/vscl-tmux-lookup` (used by the zsh hook)
3. Installs the SVG icon to `~/.local/share/icons/hicolor/scalable/apps/vscode-launcher.svg` and refreshes the GTK / KDE icon caches
4. Installs a `.desktop` entry in `~/.local/share/applications/` so it shows up in KRunner and the app menu
5. Installs an XDG autostart entry at `~/.config/autostart/vscode-launcher.desktop` with `Exec=vscode-launcher --tray`. The tray daemon will start automatically on next login.
6. Appends the tmux shell hook into `~/.zshrc` (idempotent, bounded by markers)

**On macOS**, vscode-launcher installs as a native `.app` bundle (built with
PyInstaller, following the clockwork-orange pattern). `install.sh`:

1. Builds `dist/vscode-launcher.app` on demand if it isn't already built (see [Building the macOS app](#building-the-macos-app))
2. Copies it to `/Applications/vscode-launcher.app` (falls back to `~/Applications` if `/Applications` isn't writable) — discoverable in Finder and Spotlight
3. Symlinks `vscode-launcher` (→ the installed app binary) and `vscl-tmux-lookup` into `/usr/local/bin`
4. Verifies the `code` CLI resolves to *Visual Studio Code.app* and warns if it has been hijacked by another editor (e.g. Cursor)
5. Installs a LaunchAgent at `~/Library/LaunchAgents/com.vscode-launcher.agent.plist` pointing at the app binary and loads it with `launchctl bootstrap`, so the menu-bar app starts now and on each login
6. Appends the same tmux shell hook into `~/.zshrc`

The `.app` is a **menu-bar agent** (`LSUIElement`) — it lives in the macOS menu bar with no Dock icon, but still appears in `/Applications` and Spotlight so you can launch it like any app. The menu bar uses a monochrome template icon; the Finder/Spotlight icon is the full-color `.icns`.

Open a new zsh session (or `exec zsh`) for the hook to take effect. To start it now without logging out: `open -a vscode-launcher`.

### Building the macOS app

`install.sh` builds the app automatically, but you can build it standalone:

```bash
pip3 install --user pyinstaller     # build-time dependency
./scripts/build_macos.sh            # → dist/vscode-launcher.app
open dist/vscode-launcher.app       # test before installing
```

The build requires a framework build of Python (the system `/usr/bin/python3` qualifies). `scripts/build_macos.sh` regenerates the `.icns` from `vscode-launcher.svg`, then runs PyInstaller against `vscode-launcher.spec`. Build outputs (`build/`, `dist/`, the generated `.icns`) are gitignored; the `.spec` is committed.

## Usage

The launcher runs as a tray-resident daemon. The first invocation starts the daemon and shows the main window; subsequent `vscode-launcher` invocations signal the existing daemon to surface its main window (no duplicate process).

```bash
vscode-launcher          # foreground: start daemon + show main window
vscode-launcher --tray   # autostart: start daemon hidden (no main window)
```

Closing the main window with the X button hides it back to the tray. The tray icon's right-click menu has an explicit Quit action.

The list is populated from VSCode's Recent workspaces. Folders show as `<folder-name>`; multi-root workspace files show as `<stem> (Workspace)`, matching VSCode's own labeling.

### Quick-launcher popup

Tap the configured global hotkey (default `Shift+Tab`) to bring up an Alt-Tab-style popup centered on the active screen. Running workspaces appear first in classic Alt-Tab MRU order: row 0 is the *previously* focused workspace, row 1 is the current one, older activations follow, then never-activated running workspaces in VSCode-recents order, then non-running.

- **Tap the hotkey again** to cycle to the next entry. The popup uses tap-to-cycle rather than hold-and-arrow because Wayland blocks keyboard focus stealing on hotkey-triggered windows.
- **Pause** for the configured commit delay (default 600 ms, tunable in Settings) and the current selection commits: running workspaces are focused, non-running ones are launched.
- **Mouse motion** over the popup restarts the commit timer with a fresh full duration, so reaching for a click doesn't race the keyboard timer. A stationary cursor (or one the popup happens to pop up under) doesn't count — only actual motion.
- **Mouse-click** any row to commit immediately.
- Single tap-and-pause behaves like a two-window Alt-Tab flip: row 0 is your previous workspace, you commit it, and the popup is set up to flip back on the next invocation.

### Settings

Click **Settings…** in the toolbar to change:

- **Global popup hotkey** — any `QKeySequence`-parseable combo. Applies live.
- **Popup commit delay (ms)** — how long after the last tap the popup waits before committing. Lower = faster single-tap activate; higher = more time to tap-cycle. Applies live.

### Assigning a tmux session to a workspace

1. Click a row to select it
2. Click **Set Tmux Session…** (or double-click the row)
3. Pick an existing tmux session from the dropdown, or type a new name (the launcher never creates it — you configure an existing shared session)
4. Click **OK**

The mapping is saved to `~/.config/vscode-launcher/workspaces.json` and keyed by workspace path.

To remove a mapping: open the dialog and clear the field.

### Bulk-launching

1. Tick the checkboxes next to the workspaces you want to launch
2. Click **Launch Selected**

Each ticked workspace opens in a new VSCode window; about 1.5 seconds later `vscode-gather` runs once and moves/maximizes all VSCode windows on the primary monitor. Open an integrated terminal in any launched window — the zsh hook attaches it to the tmux session you configured for that workspace.

**Launch All** ignores the checkboxes and launches every visible (non-hidden) workspace.

### Hiding workspaces

VSCode keeps every workspace you've ever touched in its Recent list. To declutter the launcher:

- Select a row and click **Hide** — it is filtered out of the launcher list (VSCode's own Recent list is unaffected)
- Click **Unhide All** to restore all hidden entries

### Refreshing

The running-state column auto-refreshes in the background every 5 seconds, so opening or closing a VSCode window shows up in the launcher within 5 s without user action. Rows update in place: no scroll or selection loss. Auto-refresh continues to run while the main window is hidden so the popup always reads fresh state.

A launch via the popup or the Start button schedules two extra scans at 2.5 s and 5 s after spawn so the new VSCode window's IPC socket is picked up as soon as it binds.

Click **Refresh** when you want the full pass: re-read VSCode's state DB (to pick up newly-added workspaces) AND re-sort the list so running rows move back to the top.

### Running workspaces

The **Status** column shows `● running` (green) when the workspace is already open in a VSCode window. Running workspaces sort ahead of the rest, and within the running group the most recently activated workspace bubbles to the top. Activation is tracked per-path on every popup commit, every Activate button click, and every launch.

Running rows have their checkbox disabled — you can't accidentally bulk-re-launch something that's already open. Use the **Activate** button to bring the existing window to the front, or **Stop** to close it. If you genuinely want to open a duplicate window, right-click the row and choose **Launch**.

Detection speaks VSCode's internal IPC protocol directly over its Unix domain socket (`$XDG_RUNTIME_DIR/Code <pid>-<token>-main.sock`) — no KWin scripting, no `qdbus6`, no `journalctl` involved in the read path. The Stop and Activate per-row buttons still use KWin scripting and require `qdbus6`. Detection silently degrades (no badges, no button filtering) when no VSCode socket is found.

### Per-row actions

Each row has contextual buttons on the right:

- **Start** (non-running rows) — launches that single workspace (same flow as Launch Selected for one entry)
- **Activate** (running rows) — raises and focuses the existing VSCode window via KWin `workspace.activeWindow = w`
- **Stop** (running rows) — closes the VSCode window via KWin `w.closeWindow()`. VSCode's own "unsaved changes?" dialog still appears if applicable; Stop does not bypass it. The VSCode main process is not killed — other windows stay open.

Stop does not auto-refresh the list because an unsaved-changes prompt may stall the close. Click **Refresh** once you've resolved any save prompt to see updated running state.

## How It Works

### Workspace source

The launcher opens VSCode's `state.vscdb` in SQLite read-only mode (`mode=ro`, so it works even while VSCode is running) and queries:

```sql
SELECT value FROM ItemTable WHERE key = 'history.recentlyOpenedPathsList';
```

It probes two candidate locations in priority order:

1. `~/.vscode-shared/sharedStorage/state.vscdb` — VSCode 1.119+ shared application storage (cross-profile)
2. `~/.config/Code/User/globalStorage/state.vscdb` — per-profile globalStorage, where the recents key lived prior to 1.119

The first candidate that opens cleanly and contains the key wins. Missing files, missing keys, and SQLite errors all fall through to the next candidate, so the launcher works on 1.119+ and older VSCode releases without configuration.

The value is JSON — each entry is either `{"folderUri": "file://..."}` (a folder) or `{"workspace": {"configPath": "file://..."}}` (a `.code-workspace` file). Non-`file://` URIs (e.g., `vscode-vfs://github/...` remote workspaces) are skipped.

### VSCode launch

For each selected workspace, the launcher spawns:

```bash
code --new-window <workspace-path>
```

as a detached subprocess, with `VSCODE_LAUNCHER_TMUX_SESSION=<session-name>` set in the child's environment (when a mapping exists). `--new-window` is required — otherwise VSCode may reuse an existing window and the env var will not propagate to its integrated terminals.

### Window placement

After all workspaces have been spawned, the launcher waits 1.5 s (so windows register with KWin) then runs `vscode-gather`, which uses KWin scripting via D-Bus to move every VSCode window to the primary monitor and maximize it. The launcher never talks to KWin directly.

### Tmux switching

The zsh hook installed into `~/.zshrc` runs on every shell startup. When it detects it's inside a VSCode integrated terminal — checking `VSCODE_INJECTION`, `VSCODE_PID`, or `TERM_PROGRAM=vscode`, since tmux rewrites `TERM_PROGRAM` to `tmux` for nested invocations — it calls a small Python helper `vscl-tmux-lookup "$PWD"` that:

1. Walks up from `$PWD` looking for the longest ancestor path present in `tmux_mappings`
2. If nothing matches directly, scans any `.code-workspace` file keyed in `tmux_mappings`, resolves its `folders[]` array (absolute + relative paths), and checks whether `$PWD` is inside one of those folders

If the lookup returns a session name:

- Outside tmux: `tmux attach -t <session>` attaches the shell to it
- Inside tmux: `tmux switch-client -t <session>` switches the current client
- Missing session or no match: silent no-op — shell starts normally

This PWD-based lookup is used instead of environment-variable propagation because `code --new-window <path>` signals an already-running VSCode process rather than spawning a fresh one, so env vars set by the launcher don't reach the integrated terminal when VSCode is already open.

The hook never creates sessions.

## Configuration

Stored at `~/.config/vscode-launcher/workspaces.json`:

```json
{
  "version": 2,
  "tmux_mappings": {
    "/home/user/git/ag-scripts": "ag-scripts",
    "/home/user/vscode-workspaces/platform-backend.code-workspace": "platform-backend"
  },
  "hidden_paths": [
    "/home/user/git/some-old-project"
  ],
  "window_geometry": {"x": 100, "y": 100, "w": 700, "h": 500},
  "global_hotkey": "Shift+Tab",
  "popup_commit_delay_ms": 600
}
```

- `tmux_mappings` — path → tmux session name (empty / missing = no mapping)
- `hidden_paths` — paths to filter out of the launcher view (VSCode's own Recent list is never modified)
- `global_hotkey` — `QKeySequence`-parseable combo for the global popup. Applied at daemon start; live-rebindable via the Settings dialog.
- `popup_commit_delay_ms` — tap-to-cycle commit timeout, range 100–5000 ms. Applied live by the Settings dialog.
- Unknown top-level keys are preserved on save for forward compatibility

The file is human-readable and safe to edit manually.

### Migrating from v1.0

If you used v1.0 (manual workspace list), the first run of v1.1 automatically:

- Preserves any `tmux_session` mappings from your v1 `workspaces` list as `tmux_mappings`
- Drops the `workspaces` list (VSCode is the source of truth now)
- Writes back the config at `"version": 2`

## Uninstallation

```bash
./uninstall.sh
```

`uninstall.sh` mirrors the platform split and first stops any running instance (matching the script, the installed symlink, and the macOS `.app` binary).

**On Linux/KDE**, it removes:

- Both `~/.local/bin` symlinks (`vscode-launcher` and `vscl-tmux-lookup`)
- The `.desktop` entry in `~/.local/share/applications/`
- The XDG autostart entry in `~/.config/autostart/`
- The SVG icon in `~/.local/share/icons/hicolor/scalable/apps/`
- The zsh hook block from `~/.zshrc` (a backup is written to `~/.zshrc.vscode-launcher.bak`)

The KDE / GTK icon caches are refreshed afterwards.

**On macOS**, it removes:

- The `.app` bundle from `/Applications` (and `~/Applications`)
- Both `/usr/local/bin` symlinks
- The LaunchAgent at `~/Library/LaunchAgents/com.vscode-launcher.agent.plist` (unloaded first with `launchctl bootout`)
- The zsh hook block from `~/.zshrc` (same backup)

On both platforms you are prompted before the config directory at `~/.config/vscode-launcher/` is deleted.

## Changelog

### v3.5.5

- Fix (macOS): invoking the popup hotkey also dragged the launcher's own window to the front. The "show window on app activation" handler (added for Spotlight relaunch) was firing when the popup grabbed focus. It's now suppressed while the popup is up / just after a hotkey press.
- Fix (macOS): activating a running workspace (popup commit or the row "Activate" button) did nothing — it used KWin scripting, which is KDE-only. macOS now focuses the existing VSCode window via the `code` CLI (`code <path>`, matching the exact folder/workspace path so it focuses rather than opening a duplicate).

### v3.5.4

- The Settings hotkey field now accepts Tab-based combos (e.g. `Ctrl+Shift+Tab`). The standard `QKeySequenceEdit` swallows Tab for focus traversal; a small `HotkeyEdit` subclass captures Tab/Backtab so an Alt-Tab-style combo can be bound from the UI. Note: a global Tab combo like `Ctrl+Shift+Tab` overrides that key everywhere (VSCode/browser tab cycling included) while the launcher is running.

### v3.5.3

- macOS global popup hotkey. The hotkey was KGlobalAccel-only (KDE); macOS now has a native backend using Carbon `RegisterEventHotKey` via `ctypes` (`macos_global_shortcut.py`), with the same press/release interface. It needs no Accessibility permission. The macOS default is `⌘⇧Space` (the Linux default `Shift+Tab` is reserved by macOS); a config carried over from Linux is migrated to the macOS default automatically. Rebindable in Settings.

### v3.5.2

- Fix (macOS): running VSCode windows weren't detected (every workspace showed `Start`, never `● running`). The IPC scan works on macOS, but the caption matcher only split window titles on a hyphen (`" - "`), while macOS VSCode renders the separator as an em-dash (`" — "`). The matcher now splits on hyphen, en-dash, and em-dash, so running-state detection works cross-platform.
- Fix: the Workspace name/path column was cut off. The default window was 700px wide, but the five fixed columns total 570px, collapsing the stretchy Workspace column to ~130px. The default window is now 1180px with a 900px minimum, leaving room for the name/path.

### v3.5.1

- Fix (macOS): relaunching the app from Spotlight/Finder when the menu-bar agent was already running did nothing. macOS has no D-Bus to signal the running instance (the Linux mechanism), and LaunchServices delivers a relaunch as an *activation* rather than a new process. The app now surfaces its main window on activation (after a startup settle delay so login autostart stays hidden), so opening it from Spotlight reliably shows the window even if the menu-bar icon is hidden behind the notch.

### v3.5

- macOS `.app` bundle (spec 014). vscode-launcher now installs as a native `/Applications/vscode-launcher.app` — discoverable in Finder and Spotlight — instead of a bare CLI symlink. Built with PyInstaller following the clockwork-orange pattern:
  - `vscode-launcher.spec` produces a **menu-bar agent** (`LSUIElement` — menu bar only, no Dock icon), with a color `.icns` generated from the SVG by `scripts/create_icns.py`.
  - `scripts/build_macos.sh` builds `dist/vscode-launcher.app` (requires `pip3 install --user pyinstaller`, build-time only).
  - `install.sh` builds the app on demand, copies it to `/Applications` (or `~/Applications`), points the LaunchAgent at the bundle binary, and symlinks `vscode-launcher` to it. `uninstall.sh` removes the `.app`.
  - Resource loading is frozen-aware (`sys._MEIPASS`) so the bundled SVG icons resolve inside the `.app`.
  - Fixed: the zsh-hook uninstall now consumes its trailing blank line, so repeated install/uninstall cycles no longer accumulate blank lines in `~/.zshrc`.

### v3.4

- macOS support (roaming platform). The launcher now starts, discovers recent projects, opens them, and shows a menu-bar icon on macOS. Platform-specific paths and APIs live in `platform_support.py`:
  - Recent-project discovery reads `~/Library/Application Support/Code/User/globalStorage/state.vscdb` (with the same `~/.vscode-shared` shared-storage fallback as Linux).
  - Running-state IPC socket discovery finds `~/Library/Application Support/Code/*-main.sock` (the main socket is named e.g. `1.12-main.sock`; the prefix tracks the IPC protocol version, not the VSCode release).
  - The Launched column uses `psutil` for per-window process start time (optional dependency; the column shows `—` when `psutil` is absent).
  - The menu bar uses a bundled monochrome **template** icon (`vscode-launcher-template.svg`) marked via `QIcon.setIsMask`, so it adapts to light/dark mode and the open-menu accent tint.
- `install.sh` / `uninstall.sh` branch on `$OSTYPE`. The macOS branch symlinks into `/usr/local/bin`, verifies the `code` CLI points at *Visual Studio Code.app* (warns on hijack by other editors), and installs/removes a `~/Library/LaunchAgents/com.vscode-launcher.agent.plist` LaunchAgent for autostart.
- Existing Linux functionality is unchanged. The IPC socket tests now pin the platform branch so the full suite passes on both Linux and macOS.

### v3.3

- Fix: running-state detection sticks after VSCode crashes. When VSCode exits abnormally (crash, OOM, SIGKILL) it leaves its IPC socket file on disk; subsequent `connect()` calls return `ECONNREFUSED`. The auto-refresh tick was classifying that as a transient IPC failure and skipping the state update, so the launcher kept showing the dead workspaces as `● running` until the user clicked Refresh. The IPC client now distinguishes a refused-connect (= VSCode not running, return `[]`) from a real transient error (= return `None`).
- The quick-launcher popup now performs a synchronous rescan on each hotkey press before showing. The IPC round-trip is ~3 ms, cheap enough to do every press, and the popup never shows stale running badges between auto-refresh ticks.

### v3.2

- Fix: VSCode 1.119 compatibility. The recently-opened workspaces key (`history.recentlyOpenedPathsList`) was migrated from per-profile `~/.config/Code/User/globalStorage/state.vscdb` to a new shared application database at `~/.vscode-shared/sharedStorage/state.vscdb`. The launcher now probes both locations in priority order (shared first, globalStorage fallback) so it works on 1.119+ and on older releases without configuration. Symptom on the broken release: empty session list after upgrading VSCode.

### v3.1

- Popup ordering now follows classic Alt-Tab MRU. Row 0 is the *previously* focused workspace (single tap-and-pause flips back to it), row 1 is the current one, rows 2+ are older entries in the activation stack, then never-activated running workspaces in VSCode-recents order, then non-running. Two-window flip-flop works exactly like Alt-Tab.
- Mouse-motion-as-activity: the auto-commit timer is restarted on each mouse move over the popup or its inner list rather than on hover-presence. A popup that pops up under a stationary cursor still counts down normally; only intentional motion holds it open.
- Bottom hint rewrite: "Tap hotkey to cycle    Pause or click to commit" (the prior text referenced keys that don't reach the popup on Wayland).
- Style fix: scoped the popup frame's `border: 1px solid` rule to its specific objectName so it stops cascading onto descendant `QLabel`s. Title and hint labels now render flat with their text aligned to the list rows.
- Internal: replaced `_activated_at_by_path` (timestamp dict) with `_mru_stack` (ordered list, no dupes). Cleaner data model for the Alt-Tab semantics; stale entries are skipped at display time rather than eagerly pruned.

### v3.0

- New: **tray-resident daemon with global quick-launcher popup**. A configurable hotkey (default `Shift+Tab`) surfaces an Alt-Tab-style popup centered on the active screen, showing all workspaces with running ones first.
- New: **tap-to-cycle popup**. Each tap of the hotkey advances the selection; pausing for the configured commit delay activates the current entry. Designed for Wayland sessions where global-hotkey-triggered windows can't grab keyboard focus, so arrow-key cycling isn't viable.
- New: **single-instance enforcement** via D-Bus (`org.kde.vscode_launcher`). A second `vscode-launcher` invocation signals the existing daemon to surface its main window instead of starting a duplicate. KGlobalAccel registration provides a second layer of protection on the hotkey itself.
- New: **autostart entry** at `~/.config/autostart/vscode-launcher.desktop` (`Exec=vscode-launcher --tray`). The daemon starts hidden on login.
- New: **Settings dialog** (toolbar button) for the popup hotkey and commit delay. Both apply live without a daemon restart.
- New: **activation MRU** within the running group. Activated workspaces bubble to the top; un-touched workspaces keep their VSCode-recents order.
- Changed: tray-resident is the only mode now. Closing the main window with the X button hides it to the tray; the tray icon's right-click menu has an explicit Quit action. The 5 s auto-refresh continues while the main window is hidden so the popup always reads current state.
- Internal: built on the KGlobalAccel D-Bus surface validated by a research spike (`research/global_shortcut_findings.md`). Productionized into [global_shortcut.py](global_shortcut.py); popup widget in [popup.py](popup.py); D-Bus singleton in [single_instance.py](single_instance.py).

### v2.0

- **Major refactor**: the running-state scanner now speaks VSCode's internal IPC protocol directly instead of going through KWin scripting + journalctl. ~170× faster (3 ms vs 500 ms per scan) and atomic — the entire v1.6/v1.7/v1.8.1 machinery (QProcess state machine, per-scan nonces, journalctl flush-race workaround) is no longer necessary and has been removed.
- New: per-window `launched_at` is now **accurate for every running window**, not just launcher-spawned ones. IPC reports the actual Electron renderer PID per window (KWin could only report the single main-process PID shared by all windows).
- Research writeup in [research/README.md](research/README.md). Protocol module is [vscode_ipc.py](vscode_ipc.py) (general-purpose, reusable outside this launcher).
- Stop / Activate row buttons still use KWin scripting (unchanged) — porting those to IPC is a separate investigation.
- Install script no longer checks for `journalctl` (reads don't use it). `qdbus6` is still needed for the action buttons.

### v1.8.1

- Fix: detecting that VSCode has exited (or been killed) no longer requires a manual Refresh. Each auto-refresh scan now embeds a unique nonce in the KWin log marker; the parser rejects any line from a previous scan that happens to still be inside journalctl's `--since "3 seconds ago"` window when the current scan's line hasn't flushed yet.

### v1.8

- New: **Launched** column between Status and Tmux showing how long ago each running workspace was opened (`5m ago`, `2h ago`, `3d ago`). Non-running rows show an em-dash.
- Precedence: workspaces you open via the launcher's Start button (or context-menu Launch) get an exact, per-window timestamp recorded at spawn time. Workspaces VSCode already had open before the launcher started fall back to the VSCode-main-started time (same for all such windows — a lower bound, since KWin's per-window PID is really the main Electron process).
- Relative times update in place on every 5 s auto-refresh tick without a full list rebuild.

### v1.7

- Refactor: the background auto-refresh introduced in v1.6 is now driven by a `QProcess` state machine instead of a `QThread` + worker. No threads are spawned; each subprocess call is event-driven via Qt's event loop.
- Same 5 s polling cadence and no-UI-freeze guarantee, but with a strictly better failure mode: no PyQt thread/worker GC pitfalls, no `wrapped C/C++ object deleted` class of crash.
- Behavior change: auto-refresh now re-sorts the list running-first when it detects a state change (a row flipping between running and not-running). Polls without state changes still leave the list untouched.
- Internal: `WindowScanner` is now a `QObject` exposing `scan_finished`. The sync `list_vscode_captions()` is kept for the manual Refresh path.

### v1.6

- New: **background auto-refresh of running state** every 5 seconds. The status column, action buttons, and checkbox enablement for each row update without user interaction — open a VSCode window and the launcher reflects it within 5 s.
- Rows update **in place**: no re-sort, no scroll / selection loss. Manual Refresh still does a full re-read + re-sort.
- The scan runs on a background thread so the UI never freezes. No overhead while the launcher window is minimized.

### v1.5

- UI: replaced the single-column list with a 5-column grid — **Checkbox · Workspace · Status · Tmux · Actions**. Values line up cleanly across rows.
- **Status** is now its own column (green `● running` or blank), replacing the inline badge next to the label.
- Checkbox is disabled on running rows — you can't accidentally bulk-re-launch something that's already open. The old "Already running?" 3-button dialog is gone as a result.
- Right-click Launch still works as a manual override if you intentionally want to duplicate a running window.
- `Launch All` silently skips running workspaces.

### v1.4

- New: per-row **Start** (non-running) / **Stop** + **Activate** (running) buttons. Activate raises and focuses the matching VSCode window via KWin `workspace.activeWindow = w`; Stop closes the window via `w.closeWindow()` without killing the shared VSCode main process. Labels are JSON-encoded when injected into the KWin JS source.
- UX: the list widget now uses `ClickFocus`, so no row is highlighted on startup — a row only lights up when the user actively clicks it.

### v1.3

- New: running-workspace detection. The launcher enumerates VSCode windows via KWin scripting, marks each already-open workspace with a `● running` badge, and sorts running ones to the top. MRU order from VSCode's Recent list is preserved within each group (running then non-running, both MRU-ordered).
- New: launching a workspace that is already open now shows a 3-button prompt (Launch Anyway / Skip Running / Cancel) instead of silently producing a duplicate VSCode window.
- Feature degrades silently when `qdbus6` or `journalctl` are unavailable (no badges, no prompt).

### v1.2

- Fixed: tmux switching now works when VSCode is already running. Replaced the brittle `VSCODE_LAUNCHER_TMUX_SESSION` env-var path — which didn't survive `code --new-window` signaling an existing VSCode process — with a PWD-based lookup performed by a new helper, `vscl-tmux-lookup`.
- New: `.code-workspace` files now resolve correctly. The lookup helper parses the `folders[]` array inside the workspace file (with relative-path resolution) and matches the terminal's `$PWD` against any listed folder.
- `vscl-tmux-lookup` is installed as a sibling symlink in `~/.local/bin`.

### v1.1

- List is now sourced from VSCode's own Recent history (`state.vscdb`), not a manually-managed list
- New: **Refresh**, **Set Tmux Session…**, **Hide**, **Unhide All** toolbar actions
- New: double-click a row to set its tmux session
- Removed: Add Workspace / Edit / Remove (VSCode is the source of truth)
- Config schema v2 with automatic migration from v1

### v1.0

- Initial release
- PyQt6 GUI with bulk-launch, add/edit/remove, drag-and-drop reordering
- Tmux session dropdown populated from `tmux list-sessions`
- Zsh hook for automatic tmux attach / switch-client in the VSCode integrated terminal
- Delegates window placement to sibling `vscode-gather`
