# slack-presence-toggle

Tray utility for KDE Plasma 6 / Wayland that auto-toggles Slack presence
based on whether the Slack desktop window has focus. When focus leaves
Slack for longer than a configurable grace period, the utility forces
`presence=away` and sets a custom status (default: 🎯 `Heads down`). When
focus returns to Slack, presence is restored to `auto` and the status is
cleared.

## Contents

- [Why](#why)
- [Requirements](#requirements)
- [Setup](#setup)
  - [1. Create a Slack app](#1-create-a-slack-app)
  - [2. Save the OAuth token](#2-save-the-oauth-token)
  - [3. Install](#3-install)
- [Usage](#usage)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Uninstall](#uninstall)
- [Known limitations](#known-limitations)
- [Architecture](#architecture)
- [Development](#development)

## Why

Slack's built-in idle detection waits ~10 minutes of system inactivity
before flipping to away. That's too generous for deep-work mode: typing
in another window keeps the green dot lit, and coworkers reasonably expect
fast replies. This utility tightens the loop by forcing away as soon as
focus leaves Slack for the configured grace period (default 30s), and adds
a custom status text that explains why.

## Requirements

- KDE Plasma 6 / Wayland (other compositors not supported)
- Python 3.11+ with PyQt6 (`python-pyqt6` on Arch / CachyOS)
- `python-dbus` and `python-gobject` (typically already installed by KDE)
- `notify-send` (`libnotify` package; optional but recommended)
- A Slack workspace where you can install custom apps

## Setup

### 1. Create a Slack app

1. Open <https://api.slack.com/apps> and click **Create New App** → **From scratch**.
2. Name it (any name works, e.g. `presence-toggle`) and pick the workspace.
3. In the left sidebar, click **OAuth & Permissions**.
4. Scroll to **User Token Scopes** (not Bot Token Scopes) and add all four:
   - `users:read`
   - `users:write`
   - `users.profile:read`
   - `users.profile:write`
5. Scroll back up and click **Install to Workspace**, then approve the
   prompt.
6. The page now shows a **User OAuth Token** starting with `xoxp-`. You'll
   copy this in the next step.

### 2. Save the OAuth token

The token grants the app permission to set your presence and status. Treat
it like a password.

Save it to `~/.config/slack-presence-toggle/token` with restrictive
permissions, **without** pasting it into terminal scrollback or chat:

```bash
mkdir -p ~/.config/slack-presence-toggle
( umask 077 && cat > ~/.config/slack-presence-toggle/token )
# Paste the token, press Enter, then Ctrl+D
chmod 600 ~/.config/slack-presence-toggle/token
```

Verify with `head -c 5 ~/.config/slack-presence-toggle/token` — should
print `xoxp-`.

If the token leaks (chat history, screenshot, paste in the wrong window),
revoke it via the Slack API and reinstall:

```bash
T=$(tr -d '[:space:]' < ~/.config/slack-presence-toggle/token)
curl -s -X POST -H "Authorization: Bearer $T" https://slack.com/api/auth.revoke
# Then in Slack app config: Reinstall to Workspace, save new token to file.
```

### 3. Install

From this directory:

```bash
./install.sh
```

The installer:

- Installs the KWin script to `~/.local/share/kwin/scripts/slack-focus-monitor/`
  and enables it via `kwriteconfig6` + `qdbus6 ... loadScript`.
- Writes a desktop entry to `~/.local/share/applications/slack-presence-toggle.desktop`.
- Writes an autostart entry to `~/.config/autostart/slack-presence-toggle.desktop`.
- Creates `~/.config/slack-presence-toggle/` (mode 700).

Start the app right away:

```bash
./run.sh
```

Or log out and back in for the autostart entry to fire.

## Usage

The app lives in the system tray. The icon's color reflects state:

| Color | Meaning |
| --- | --- |
| Green | Enabled, API healthy, Slack active |
| Yellow | Enabled, API healthy, Slack away |
| Gray | Disabled (or no data yet) |
| Red | API auth failure (token missing/revoked/missing-scope) |
| Yellow + warning glyph | Enabled, transient API failure (network, rate limit, 5xx) |

Right-click for the menu:

- **Slack: \<status\>** — current presence, mirrored in the tooltip
- **API: \<state\>** — current API health
- **Disable / Enable auto-presence** — quick toggle. On disable, the app
  immediately calls `setPresence(auto)` and clears any custom status it
  set, so you're never stuck looking offline.
- **Reload token from file** (only when auth has failed) — re-reads the
  token file and retries `auth.test`. Use after rotating the token.
- **Configure** — submenu with token path, grace period, status text,
  status emoji, status safety buffer.
- **Quit** — runs the same clear-forced-state sequence as Disable, then
  exits.

The grace period is the time focus must stay off Slack before the utility
forces away. Default 30 seconds. Brief alt-tabs to look something up don't
trigger it; only sustained focus elsewhere does.

## Configuration

`~/.config/slack-presence-toggle/config.toml`. Created on first run with
the defaults below. Changes via the Configure menu are persisted here.

```toml
enabled = true
grace_seconds = 30
token_file = "~/.config/slack-presence-toggle/token"
notifications = true
debug = false
slack_resource_class = "Slack"
status_text = "Heads down"
status_emoji = ":dart:"
status_safety_buffer_seconds = 3600
```

`status_safety_buffer_seconds` is the auto-expiration timestamp Slack uses
to clear the custom status if the utility crashes mid-away. Default 1
hour. Increase if you regularly have deep-work sessions longer than an
hour and don't want the status to disappear partway through.

## Troubleshooting

**Tray icon doesn't appear.** Some KDE setups hide tray icons by default.
Right-click the system tray, choose **Configure System Tray** → **Entries**,
and ensure "Slack Presence Toggle" is set to **Shown**.

**Tray icon is gray and stays gray.** The state machine is disabled, the
token file is missing, or `auth.test` failed. Right-click for the API
state. The notification on startup explains the specific issue.

**Tray icon is red.** API auth failure. Open the menu and click
**Reload token from file** after either regenerating the token in Slack
or fixing scope issues.

**Tray icon stays green when Slack loses focus.** The KWin script may not
be loaded. KDE sometimes drops loaded scripts after Plasma restarts /
log-out cycles, even when the `kwinrc` Plugins entry is intact. The app
auto-heals every 5 minutes (loads the script if files are on disk and
KWin reports `isScriptLoaded=false`), and emits a confirmation
notification when recovery succeeds. To force recovery immediately:

- Right-click the tray icon → **Reload KWin script**

If that does nothing, the script files are missing on disk:

```bash
qdbus6 org.kde.KWin /Scripting isScriptLoaded slack-focus-monitor
journalctl --user -f | grep slack-focus-monitor
```

If `isScriptLoaded` returns `false` and the menu action does not recover
it, run `kwin-script/install.sh` again.

**Slack window class is not "Slack" on my system.** Some Slack distributions
(Flatpak, Snap, dev builds) use different `WM_CLASS` values. Inspect the
actual class with the prototype listener (`prototypes/focus_listener.py`),
then set `slack_resource_class` in the config.

**Stuck appearing as away after the utility crashed.** The custom status
auto-clears at `status_safety_buffer_seconds` (default 1h). Presence does
not auto-clear. Manually toggle in Slack (avatar → "Set yourself as
active") or just relaunch the utility — it will detect the discrepancy on
the next focus event and clear it.

## Uninstall

```bash
./uninstall.sh
```

Stops the running app gracefully (so it releases any forced state in
Slack), removes the KWin script, desktop entries, and autostart. Prompts
before removing the config directory and token file. The token in Slack
remains valid until you revoke it via the API or the Slack app config.

## Known limitations

- **Single Slack workspace per app instance.** The Slack desktop client
  supports multiple workspaces in one window. This utility holds one User
  OAuth Token and sets presence on that one workspace. If you switch to a
  workspace this utility wasn't authed against, the focus-driven presence
  changes won't apply there.
- **Wayland on KDE Plasma 6 only.** X11 and other compositors aren't
  supported because the focus-detection layer is KWin-specific.
- **Browser-based Slack not detected.** Only the Slack desktop client is
  matched. If you use Slack in a browser tab, the utility doesn't see tab
  focus.

## Architecture

The full design and acceptance criteria are in
[`specs/001-tray-focus-presence.md`](specs/001-tray-focus-presence.md).

```text
┌─────────────────┐  D-Bus call    ┌──────────────────┐   HTTPS    ┌─────────┐
│   KWin script   │ ─────────────► │  tray app (Py)   │ ─────────► │ Slack   │
│ (windowActivated│                │  state machine + │            │ API     │
│   handler)      │                │  PyQt6 tray UI   │            │         │
└─────────────────┘                └──────────────────┘            └─────────┘
```

Components:

- `kwin-script/` — KWin JavaScript script that emits a D-Bus call on every
  `workspace.windowActivated` event.
- `slack_presence_toggle/focus_listener.py` — QtDBus service receiving the
  KWin events.
- `slack_presence_toggle/state_machine.py` — pure Python focus state
  machine: hysteresis timer, "we forced away" tracking, user-status
  protection.
- `slack_presence_toggle/slack_client.py` — thin Slack web API wrapper for
  `auth.test`, `users.{set,get}Presence`, `users.profile.{set,get}`.
- `slack_presence_toggle/tray.py` — PyQt6 `QSystemTrayIcon` and menu.
- `slack_presence_toggle/main.py` — orchestrator, wiring the above.

## Development

### Run tests

```bash
pytest
```

48 tests covering the state machine, Slack client (mocked), and config.

### Manual end-to-end test (no UI)

```bash
python3 dev_cli.py
```

Provides a REPL for driving the state machine against the real Slack API.
`status` is read-only; `slack` / `other` / `fire` exercise full transitions
and will set real presence.

### Bus name

The app registers `io.github.ushineko.SlackPresenceToggle` on the session
bus, exposes `WindowActivated(s,s)` at `/FocusMonitor`. Only one instance
runs at a time (second instance fails to register and exits cleanly).

### Prototypes

`prototypes/` holds the validation harness used while designing the
utility. Useful for debugging if the production code stops working —
prototypes A and B isolate the focus-detection and Slack-API layers
respectively.
