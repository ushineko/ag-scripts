# herdr-switcher

An alt-tab popup for switching between [herdr](https://herdr.dev) **spaces**
(workspaces), across all running herdr sessions. The successor to
`vscode-launcher` now that terminals run herdr instead of tmux.

Press **Ctrl+Meta+Tab** → a popup lists your spaces, most-recently-used first →
pick one → herdr-switcher raises and maximizes the terminal hosting that space's
session and focuses the space.

> **Platform:** KDE Plasma 6 / Wayland only (v1). macOS is a planned follow-up;
> the hotkey and window-activation backends are isolated for that. See
> `specs/001-herdr-switcher-alt-tab-space-switcher.md`.

## How it works

- **Spaces** come from the herdr socket API: `herdr session list --json` →
  `herdr --session <s> workspace list` for each session.
- **Recency** (herdr has no focus-event stream) is maintained locally in
  `~/.config/herdr-switcher/state.json`: the current space (active window →
  session → focused workspace) is promoted at each popup, and the chosen space
  on each switch. The popup pre-selects the *previous* space, so a quick
  tap-release toggles between the last two — classic alt-tab.
- **Switching** maps the target session to its herdr client process, walks
  `/proc` to the hosting terminal's PID, and raises + maximizes that window via
  KWin D-Bus scripting (matched by `window.pid`). It then calls
  `herdr workspace focus`.
- If a session is running but **detached** (its terminal was closed), the
  switcher opens a fresh terminal that attaches it (`alacritty -e herdr session
  attach <name>`); you position the window.

## Install

```sh
./install.sh      # symlinks, desktop + autostart entry, icon, starts the daemon
./uninstall.sh    # remove (add --purge to also delete config + MRU state)
```

Dependencies: `python-pyqt6`, `qt6-tools` (for `qdbus6`), `herdr`, `kdotool`.

## Usage

- **Ctrl+Meta+Tab** — open the popup. Tap again to cycle, release or pause (~0.6s) to
  commit; Enter or click also commit; Esc cancels.
- Tray icon → **Change hotkey…** (capture a new chord; rebinds live and saves)
  or **Quit**.
- Headless CLI (handy for scripting / debugging):
  ```sh
  herdr-switcher-cli list                       # all spaces, * = current
  herdr-switcher-cli current                    # space under the active window
  herdr-switcher-cli sessions                   # session -> terminal window PID
  herdr-switcher-cli switch work w1 [--dry-run] # switch directly
  ```

## Configuration

Change the hotkey from the tray (**Change hotkey…** → press a chord), or edit
`~/.config/herdr-switcher/config.json` directly and restart:

| Key | Default | Meaning |
|-----|---------|---------|
| `hotkey` | `Ctrl+Meta+Tab` | Global shortcut (Qt portable text, e.g. `Shift+Tab`) |
| `popup_commit_delay_ms` | `600` | Pause-to-commit delay |
| `terminal` | `alacritty` | Terminal used to attach detached sessions |
| `max_rows` | `12` | Max visible rows in the popup |

> **Note:** the hotkey is a *global* shortcut — while the daemon runs, that combo
> is captured system-wide. `Ctrl+Meta+Tab` is chosen to avoid clashing with apps
> that reserve plain `Shift+Tab` (e.g. Claude Code). Change `hotkey` if it clashes
> with something on your setup.

## Architecture

| Module | Role |
|--------|------|
| `herdr_api.py` | herdr CLI/socket wrapper; `Space` model |
| `session_windows.py` | herdr client discovery, session→terminal-PID, current-space |
| `window_actions.py` | KWin D-Bus scripting: activate + maximize by PID |
| `core.py` | switch orchestration (shared by CLI + daemon) |
| `global_shortcut.py` | KGlobalAccel backend (shared with vscode-launcher) |
| `popup.py` | PyQt6 frameless alt-tab popup |
| `mru.py` | recency stack (`state.json`) |
| `config.py` | config + paths |
| `herdr_switcher.py` | tray daemon wiring it together |
| `cli.py` | headless CLI / test harness |

## Troubleshooting

- **Hotkey doesn't work / "Could not bind"** — another component owns the combo.
  Pick a different `hotkey`, or check `~/.config/kglobalshortcutsrc`.
- **Switch doesn't raise the window** — confirm KWin sees the terminal:
  `herdr-switcher-cli sessions` should list it. The match relies on KWin's
  `window.pid` equalling the terminal emulator's PID (true for alacritty).
- **Detached session won't open a terminal** — ensure the configured `terminal`
  is on PATH. (herdr's nested-session guard is handled: the spawn strips
  `HERDR_ENV`/`HERDR_SESSION`.)
