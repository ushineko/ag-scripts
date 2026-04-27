# slack-presence-toggle: tray utility, focus-driven Slack presence

## Status: INCOMPLETE

## Overview

A KDE Plasma 6 / Wayland tray utility that automatically toggles the user's
Slack presence between `auto` (active) and `away` based on whether the Slack
desktop client window has focus. Intended for deep-work mode: when the user
is not actively in Slack, coworkers see them as away rather than mistaking
auto-active status for "available right now."

The utility is a stricter overlay on top of Slack's built-in idle detection.
Slack's default idle threshold is roughly 10 minutes of system inactivity;
this utility forces away the moment the user stops looking at Slack
specifically (after a configurable grace period).

## Background

Both halves of the design were validated by prototypes in
`prototypes/`:

- **Prototype A** (focus detection): a KWin JavaScript script subscribes to
  `workspace.windowActivated` on Plasma 6 and forwards each event to a
  Python D-Bus listener. Slack's `resourceClass` is `Slack`. One event per
  alt-tab, no flapping.
- **Prototype B** (Slack API): `users.setPresence` accepts `auto` and `away`
  with a `users:write` scope on a User OAuth token (`xoxp-`). With
  `users:read` added, `users.getPresence` returns rich diagnostic data:
  `presence`, `manual_away`, `auto_away`, `connection_count`,
  `last_activity`. The full design also requires `users.profile:write`
  (for `users.profile.set`, used to set the custom status text/emoji
  alongside presence).

## Scope

### In scope (v1)

- KDE Plasma 6 / Wayland focus detection via KWin script + D-Bus
- Slack desktop client only (matches `resourceClass == "Slack"`)
- Single workspace (one User OAuth token)
- Tray icon with right-click menu
- Configurable grace period before forcing away
- Status display in menu and tooltip
- API health indicator with recovery actions for auth failures
- Quick-disable that releases Slack from forced state
- Persistent enabled/disabled state across restarts
- Installer and uninstaller scripts

### Out of scope (deferred)

- Multi-workspace support (one token at a time only)
- Browser-based Slack (`app.slack.com` tab focus)
- X11 / GNOME / other compositors
- Configuration GUI beyond text-input dialogs
- Auto-token-refresh flows (token rotation is manual)

## Architecture

```text
┌─────────────────┐  D-Bus call    ┌──────────────────┐
│   KWin script   │ ─────────────► │  tray app (Py)   │
│ (windowActivated│                │                  │
│   handler)      │                │  ┌────────────┐  │
└─────────────────┘                │  │ focus FSM  │  │
                                   │  └─────┬──────┘  │
                                   │        │         │
                                   │  ┌─────▼──────┐  │
                                   │  │ presence   │  │  HTTPS
                                   │  │ controller ├──┼──────► slack.com/api
                                   │  └────────────┘  │
                                   │                  │
                                   │  ┌────────────┐  │
                                   │  │ tray UI    │  │
                                   │  │ (PyQt6)    │  │
                                   │  └────────────┘  │
                                   └──────────────────┘
```

Components:

- **KWin script** (`slack-focus-monitor`): JavaScript script installed at
  `~/.local/share/kwin/scripts/slack-focus-monitor/`. Subscribes to
  `workspace.windowActivated` and emits a D-Bus method call on every
  activation event. Same script body as the Prototype A version.
- **Tray app**: PyQt6 application with `QSystemTrayIcon`. Receives D-Bus
  events from the KWin script, runs the focus state machine, talks to
  Slack's API (`users.setPresence`, `users.getPresence`,
  `users.profile.set`, `users.profile.get`, `auth.test`), and renders the
  menu.
- **Token storage**: plain text file at
  `~/.config/slack-presence-toggle/token` (mode 600).
- **Config storage**: TOML or JSON file at
  `~/.config/slack-presence-toggle/config.toml` for runtime settings.

## Behavior

### Focus state machine

States: `slack_focused`, `other_focused`, `other_focused_pending_away` (during
grace period).

Transitions:

| From | Trigger | To | API calls |
| --- | --- | --- | --- |
| any | Slack window activated | `slack_focused` | clear forced state (see below) |
| `slack_focused` | non-Slack window activated | `other_focused_pending_away` (start timer) | none |
| `other_focused_pending_away` | Slack window activated | `slack_focused` | cancel timer; clear forced state |
| `other_focused_pending_away` | grace timer expires | `other_focused` | apply forced state (see below) |
| `other_focused` | Slack window activated | `slack_focused` | clear forced state |

**Apply forced state** (focus has been off Slack longer than the grace
period):

1. `users.setPresence(presence="away")`
2. `users.profile.set(profile={"status_text": <configured>, "status_emoji":
   <configured>, "status_expiration": <now + safety_buffer_seconds>})` — the
   safety buffer (default 3600s / 1h) is how long the status persists if
   the utility crashes before clearing it. Slack auto-clears at expiration.

**Clear forced state** (focus returned to Slack):

1. Read `users.profile.get` to check current status.
2. If current status text equals our configured text *and* the
   `we_forced_status` flag is true: call
   `users.profile.set(profile={"status_text": "", "status_emoji": "",
   "status_expiration": 0})`. Otherwise leave the status alone (the user
   set their own status while we were away — respect it).
3. `users.setPresence(presence="auto")`, also gated by a `we_forced_away`
   flag so we don't override a user's manual away state.

Both API calls in each direction are independent: if one fails (e.g.,
`users.profile.set` rate-limited but `users.setPresence` succeeds), the
state machine logs the partial-success state and lets the API health
indicator surface it. No rollback attempts; the next transition will
re-establish the correct state.

**Optimizations**:

- Skip `setPresence(auto)` if `we_forced_away` is false (we never set it
  away, no need to clear it).
- Skip `users.profile.set` clear if `we_forced_status` is false.
- Cache last-known presence/status from `getPresence`/`profile.get` polls
  to avoid redundant set calls when state already matches.

### Hysteresis

- **Focus gain (Slack)**: instant, no delay. Coworker pings should see the
  user active immediately.
- **Focus loss (Slack)**: configurable grace period, default 30 seconds.
  Allows brief context switches (look up a URL in browser, glance at a
  terminal) without flapping presence.

### Quick-disable

Tray menu has a top-level item `Disable auto-presence`. Clicking it:

1. Cancels any pending grace timer.
2. Performs the full **clear forced state** sequence (clear status if we
   set it, then `setPresence(auto)` if we forced away). One or both calls
   may be skipped per the optimization gates.
3. Stops responding to focus events (D-Bus listener stays registered, but
   handler short-circuits).
4. Updates menu to show `Enable auto-presence` in place of disable.
5. Persists the disabled state to the config file.

Re-enabling reverses these steps and triggers a one-shot KWin script reload
so the app receives a fresh `windowActivated` event for the current focus.

### Status display

Tray menu has a non-clickable header item showing the user's current Slack
status. Computed from the cached `users.getPresence` and
`users.profile.get` responses:

| `presence` | `manual_away` | `auto_away` | `status_text` | Display |
| --- | --- | --- | --- | --- |
| `active` | false | false | (any) | `Slack: Active` |
| `away` | true | * | matches our configured text | `Slack: Away (forced by us) — "<status_text>"` |
| `away` | true | * | other / empty | `Slack: Away (manual)` |
| `away` | false | true | (any) | `Slack: Away (Slack idle)` |
| (any) | (any) | (any) | (any) | `Slack: Unknown` if no successful poll yet |

Tray icon tooltip mirrors this string on hover.

The "forced by us" detection uses two flags:

- `we_forced_away`: set true on our `setPresence(away)` call, cleared on
  our `setPresence(auto)` call.
- `we_forced_status`: set true on our `users.profile.set` with non-empty
  text, cleared on our clear-status call.

Both flags are also cleared if a poll reveals state we didn't expect (e.g.,
`status_text` equals neither our configured text nor empty — the user set
something else, so we shouldn't pretend ownership).

### Notifications

A desktop notification fires every time the utility itself successfully
changes Slack state. The "apply forced state" and "clear forced state"
sequences each produce a single notification covering the combined
result of their two API calls (presence + status). Notifications do *not*
fire for state inferred from poll responses (e.g., the user toggling away
in Slack manually) or for no-op API calls.

| Transition | Notification body |
| --- | --- |
| Apply forced state succeeds | "Slack: Away — focus left Slack for {grace_seconds}s" |
| Clear forced state on focus return | "Slack: Active — focus returned to Slack" |
| Clear forced state on quick-disable | "Slack: Active — auto-presence disabled" |
| Clear forced state on quit/uninstall | none (avoid noise on shutdown) |
| Either sequence partially fails | `"Slack: {state} (warning: {which API call failed})"` with urgency=normal |

Implementation pattern follows
[foghorn-leghorn](../../foghorn-leghorn/foghorn_leghorn.py): use
`QSystemTrayIcon.showMessage` for tray-integrated notifications *and* a
fire-and-forget `subprocess.Popen` of `notify-send --app-name="Slack
Presence Toggle" --urgency=low --icon=<name>` for richer KDE delivery.
Wrap the `notify-send` call in `try / except FileNotFoundError: pass` so
systems without the binary still work.

Icons:

- `user-online` for active transitions
- `user-away` for away transitions

Config option `notifications = true` (default) lets the user silence them
without disabling the utility. Errors that change API health (token
revoked, etc.) get their own urgency=critical notification regardless of
this setting, since silent breakage would defeat the health indicator.

### Status refresh

`users.getPresence` is polled:

- On tray menu open (`aboutToShow` signal)
- Immediately after every `setPresence` call we make
- Never on a periodic timer (no constant polling)

Stale status between menu opens is acceptable.

### API health indicator

Tray menu has a dedicated item showing one of:

| State | Display | Tray icon overlay |
| --- | --- | --- |
| Last call ok | `API: connected` | none |
| `invalid_auth` / `token_revoked` / `account_inactive` | `API: token <reason>` | warning glyph |
| Network error | `API: network error (last ok: 2m ago)` | warning glyph |
| HTTP 429 | `API: rate limited (retrying in Ns)` | warning glyph |
| HTTP 5xx | `API: server error (retrying)` | warning glyph |

When in an auth-failure state, the menu also shows a recovery action:
`Reload token from file`. Clicking re-reads the token file and retries
`auth.test`. If successful, health returns to `connected`.

Transient failures (network, 429, 5xx) auto-retry with exponential backoff.
The state machine pauses presence-setting until the API is healthy again
(focus events still tracked locally; the next state change after recovery
applies the correct presence).

### Initial state on startup

1. Read config (enabled state, grace period, token file path).
2. Read token; call `auth.test`. Set API health based on result.
3. If enabled and API healthy:
   - Trigger one-shot KWin script reload via `org.kde.KWin /Scripting`
     (unloadScript + loadScript) to receive a fresh `windowActivated`
     event for the current focus.
   - State machine handles the event normally.
4. If disabled or API unhealthy: no state-machine action, but listener
   still registered.

### Shutdown behavior

On normal app quit (tray menu Quit, SIGTERM):

1. Cancel any pending grace timer.
2. Best-effort `setPresence(auto)` call to release Slack from any forced
   state. Don't block shutdown if it fails.
3. Unregister D-Bus listener.

The KWin script keeps running and emitting events to a now-dead listener,
which is harmless. `callDBus` to a non-existent name fails silently. The
script gets unloaded only on uninstall.

## Tray menu structure

```text
┌──────────────────────────────────────┐
│  Slack: Active                       │  (header, disabled)
│  API: connected                      │  (header, disabled)
│  ──────────────────────────────────  │
│  Disable auto-presence               │  (toggle)
│  ──────────────────────────────────  │
│  Configure                           │  (submenu)
│    Token file...                     │
│    Grace period (currently 30s)...   │
│    Reload token from file            │  (only when auth failed)
│  ──────────────────────────────────  │
│  About                               │
│  Quit                                │
└──────────────────────────────────────┘
```

## Configuration

`~/.config/slack-presence-toggle/config.toml`:

```toml
enabled = true
grace_seconds = 30
token_file = "~/.config/slack-presence-toggle/token"
notifications = true
debug = false
slack_resource_class = "Slack"

# Custom status applied alongside presence=away.
# status_emoji is the Slack emoji shortcode (with colons) or empty string.
# status_safety_buffer_seconds is the auto-expiration timestamp Slack uses
# to clear the status if the utility crashes while away. Should be longer
# than the longest expected away period to avoid premature clearing during
# normal use.
status_text = "Heads down"
status_emoji = ":dart:"
status_safety_buffer_seconds = 3600
```

Defaults if file missing or fields absent: as shown above. Missing config
file is normal on first run; the app writes one out with defaults.

## File layout

```text
slack-presence-toggle/
├── README.md                 # User-facing documentation
├── install.sh                # Top-level installer (calls KWin install + creates desktop entry)
├── uninstall.sh              # Top-level uninstaller (reverses install + sets presence to auto)
├── slack_presence_toggle.py  # Main app entry point
├── slack_presence_toggle/    # Source package
│   ├── __init__.py
│   ├── focus_listener.py     # D-Bus service receiving KWin events
│   ├── slack_client.py       # users.setPresence / users.getPresence / auth.test
│   ├── state_machine.py      # focus FSM with grace timer
│   ├── tray.py               # PyQt6 tray icon and menu
│   ├── config.py             # Config loader/saver
│   └── version.py
├── kwin-script/              # KWin script package (mostly identical to prototype)
│   ├── metadata.json
│   ├── contents/code/main.js
│   ├── install.sh
│   └── uninstall.sh
├── tests/
│   ├── test_state_machine.py
│   ├── test_slack_client.py  # mocked HTTP
│   └── test_config.py
└── specs/
    └── 001-tray-focus-presence.md  # this file
```

Installed locations:

- `~/.local/share/kwin/scripts/slack-focus-monitor/` (from KWin install.sh)
- `~/.local/share/applications/slack-presence-toggle.desktop`
- `~/.config/autostart/slack-presence-toggle.desktop` (autostart on login)
- `~/.config/slack-presence-toggle/{token,config.toml}` (created at runtime)

## Failure modes

| Mode | Detection | Recovery |
| --- | --- | --- |
| Token revoked / invalid | API call returns `error: invalid_auth` or `token_revoked` | Menu shows `Reload token from file`. User regenerates token externally, overwrites file, clicks reload. |
| Token missing one of the required scopes (`users:read`, `users:write`, `users.profile:write`) | API call returns `error: missing_scope` with `needed: <scope>` field | Menu shows `Token missing scope: <scope>`; user adds scope in Slack app config, reinstalls, reloads token. |
| Custom status set succeeds but presence set fails (or vice versa) | One API call returns `ok: false`, the other `ok: true` | State machine records partial-success; next transition re-applies the missing half; notification shows which call failed. |
| Token file missing | Read fails on startup | API health shows `token file missing`. Menu offers `Configure → Token file...` |
| KWin script not loaded | `qdbus6 org.kde.KWin /Scripting isScriptLoaded slack-focus-monitor` returns false | Tray icon overlay; menu offers `Reinstall KWin script` (runs `kwin-script/install.sh`) |
| D-Bus listener cannot register | `BusName(...)` raises `NameExistsException` | App shows error dialog and exits. User kills the other instance. |
| Slack rate limit (429) | HTTP status | Honor `Retry-After`; pause API calls; show in health item |
| Network error | Exception or non-200 | Exponential backoff (1s, 2s, 4s, 8s, 16s, max 60s); pause state machine until recovery |
| Config file corrupt | TOML parse error | Log warning; use defaults; do not overwrite the corrupt file (preserve for inspection) |
| User runs `setPresence` manually in Slack while utility enabled | Detected on next `getPresence` poll: `manual_away=true` and `we_forced_away=false` | Display `Slack: Away (manual)`; do not override |

## Testing

Unit tests (with mocked time and mocked Slack client):

- Focus state machine: every transition table row above
- Grace timer: cancel-on-return, expire-on-stay, multiple rapid switches
- API health state: each failure mode → correct display string
- "Forced by us" tracking: setPresence(away) sets flag, setPresence(auto)
  clears it, external manual_away=true with we_forced_away=false reads as
  manual

Integration / manual tests (in spec, not automated):

- Install KWin script + start app, alt-tab between Slack and other windows,
  observe Slack web client status changes correctly.
- Quick-disable: verify Slack returns to auto status immediately and stays
  there even when Slack loses focus.
- Token revocation: revoke token via API, observe API health update on
  next call, reload token from file, observe recovery.

## Implementation phases

Suggested order; each phase produces a working but limited binary:

1. **Slack client + state machine** (no UI, no D-Bus): library code with
   tests. CLI driver for manual end-to-end test.
2. **D-Bus integration**: wire focus_listener to state machine. Run as
   daemon, log to stderr. No UI yet.
3. **Tray UI minimal**: icon + status header + Quit. Menu opens.
4. **Tray UI full**: enable/disable toggle, API health item, configure
   submenu, recovery actions.
5. **Installer / uninstaller / autostart / desktop entry**.
6. **Validation report and finalization** (per project CLAUDE.md
   finalization checklist).

## Acceptance criteria

- [x] App starts, registers `io.github.ushineko.SlackPresenceToggle` (or
      similar) on the session bus, and shows a tray icon.
- [x] Right-click tray menu shows: status header, API health header,
      enable/disable toggle, Configure submenu, About, Quit.
- [ ] Status header updates correctly for each combination of
      `presence` × `manual_away` × `auto_away`.
- [ ] When enabled and Slack window focused: presence is `auto` and any
      utility-set custom status is cleared within 1 second of focus event.
- [x] When enabled and Slack loses focus: presence becomes `away` *and*
      custom status is set to configured `status_text` + `status_emoji`
      with `status_expiration = now + status_safety_buffer_seconds`,
      after `grace_seconds` (default 30) of continuous non-Slack focus.
- [x] If the user has set a non-empty custom status before our utility
      activates, the utility leaves it alone and only updates presence.
- [x] On focus return, custom status is cleared only if the current status
      text matches our configured text (do not clobber user-set statuses).
- [x] When focus returns to Slack within the grace period: no API call,
      timer cancelled.
- [x] When focus returns to Slack after grace expired: presence is `auto`
      within 1 second.
- [ ] Quick-disable: clicking immediately calls `setPresence(auto)` and
      stops responding to focus events. Menu updates.
- [ ] Quick-enable: clicking starts focus tracking and computes initial
      state from current focus.
- [x] API health shows `connected` when `auth.test` succeeds.
- [ ] API health shows `token revoked` (or `invalid_auth`) on auth
      failure; tray icon overlay appears.
- [ ] In auth-failure state, menu shows `Reload token from file` action.
- [ ] After reloading a valid token: API health returns to `connected`,
      tray icon overlay disappears, state machine resumes.
- [ ] Network error: API health shows transient warning; state machine
      pauses; recovery on next successful call.
- [ ] Configure → Token file: opens dialog, saves chosen path to config.
- [ ] Configure → Grace period: accepts 0–600, saves to config, applies
      immediately to next transition.
- [ ] Configure → Status text and emoji: text input + emoji shortcode
      input. Saves to config. Applies on next transition.
- [ ] Configure → Status safety buffer: accepts 60–86400 seconds. Default
      3600.
- [ ] Enabled/disabled state persists across app restarts.
- [ ] On clean quit (menu or SIGTERM): final clear-forced-state sequence
      runs (clear status if set by us, then `setPresence(auto)` if forced
      by us); failures are logged but do not block shutdown.
- [x] Successful `setPresence` calls trigger a desktop notification (tray
      `showMessage` + `notify-send --app-name="Slack Presence Toggle"`);
      no notification fires for no-op API calls or `getPresence`-inferred
      changes.
- [ ] Auth-failure transitions trigger an urgency=critical notification
      regardless of `notifications` config.
- [ ] Setting `notifications = false` in config silences informational
      notifications but not the auth-failure ones.
- [x] Top-level `install.sh` installs the KWin script, copies the desktop
      entry, sets up autostart, and creates the config directory.
- [ ] Top-level `uninstall.sh` removes the KWin script, desktop entries,
      autostart, and (after one final `setPresence(auto)` call) the
      config directory and token file (with confirmation prompt for the
      token).
- [x] Unit tests pass for state machine, slack client (mocked),
      configuration loader.
- [x] README documents installation, configuration, troubleshooting (token
      regeneration steps), and known limitations (Wayland-only, single
      workspace).
- [x] Validation report committed in `validation-reports/` per project
      CLAUDE.md.

## Tray icon design

Simple `S` glyph rendered programmatically (so it can be recolored without
shipping multiple icon assets). Color encodes app + Slack state:

| Condition | Color | Notes |
| --- | --- | --- |
| Disabled | gray | Takes precedence over Slack state; we're not doing anything |
| API unhealthy | red | Takes precedence over Slack state; user attention needed |
| Enabled, API ok, Slack active | green | Normal active state |
| Enabled, API ok, Slack away (any reason) | yellow | Normal away state |
| Initial state, no API poll yet | gray | Same as disabled visually; resolves on first poll |

The warning glyph overlay described in the API Health section is composed
on top of the base icon when API health is degraded. Specifically, for
transient (non-auth) failures the icon stays its current color with the
warning glyph; for auth failures the icon turns red.

Implementation: render via `QPixmap` + `QPainter` at app start and on every
state change. No external icon files. Ensures the icon survives theme
changes.

## Known limitations

- **Single Slack workspace per app instance**. The Slack desktop client
  supports multiple workspaces in one window; this utility holds one User
  OAuth token and sets presence on that workspace only. If the user is
  active in workspace A but the utility was authed against workspace B,
  workspace B's presence reflects Slack-window focus rather than activity
  on workspace B specifically. Documented in README; multi-workspace is
  out of scope for v1.
- **`connection_count`**: displayed as-is from Slack's response. The
  utility does not special-case `connection_count == 0` (Slack desktop
  not running). The status header just shows whatever Slack reports in
  that case.
- **Wayland on KDE Plasma 6 only**. X11, GNOME, and other compositors are
  not supported; the focus-detection mechanism is KWin-specific.
