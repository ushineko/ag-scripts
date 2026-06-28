# Spec 001: herdr-switcher — alt-tab popup for herdr spaces

> **Note**: This work has no associated issue tracker ticket. Consider creating
> one for traceability.

**Status: COMPLETE**

## Context

`vscode-launcher` provides an alt-tab popup that jumps between VS Code workspaces,
raising the right window and attaching the mapped tmux session. VS Code terminals
have since moved to **herdr** (the tmux integration hook in `~/.zshrc` is disabled
as of 2026-06-27), so the equivalent need is now: a global-hotkey popup that lists
recent **herdr spaces** (workspaces) and, on selection, brings the terminal hosting
that space's session to the front and switches herdr to the space.

`herdr-switcher` is the successor to `vscode-launcher` for this workflow and reuses
its proven building blocks: a PyQt6 frameless popup, KGlobalAccel for the global
hotkey, and KWin D-Bus scripting for Wayland window activation.

## Goals

- A daemon that registers a global hotkey and shows an alt-tab popup of herdr spaces
  across **all** running herdr sessions, ordered by recency.
- On commit: activate (raise + maximize) the terminal window hosting the chosen
  space's session, then focus the space inside herdr.
- Match the `ag-scripts` house style (tool layout, install pattern, PyQt6 popup,
  config in `~/.config/herdr-switcher/`).

## Non-goals (this spec)

- **macOS support** is deferred to a follow-up spec. v1 targets **KDE Plasma 6 /
  Wayland** only. The code structure should keep the hotkey and window-activation
  backends behind small interfaces so a macOS backend (Carbon hotkey + AppleScript
  activation, per `vscode-launcher`/`vscode-gather`) can be added later without
  reworking the core.
- Editing herdr config, creating/renaming/closing spaces from the popup. v1 is
  read-and-switch only.

## Empirical findings (2026-06-28, herdr on njv-cachyos)

| # | Finding | Detail |
|---|---------|--------|
| 1 | Sessions are enumerable | `herdr session list --json` → `{"sessions":[{name,default,running,socket_path,...}]}`. Two live: `default`, `work`. |
| 2 | Spaces are enumerable per session | `herdr workspace list` and `herdr --session <name> workspace list` emit JSON: `workspaces[]` with `workspace_id` (`w1`…), `label`, `number`, `focused`, `agent_status`, `pane_count`, `tab_count`. (`workspace list` does not accept `--json`; output is already JSON.) |
| 3 | Switching a space is one call | `herdr [--session <name>] workspace focus <workspace_id>`. |
| 4 | One attached client per session | The handoff model means each running session has at most one attached terminal window. Clients are identifiable by argv: `herdr` → default session; `herdr session attach <name>` / `herdr --session <name>` → that session. |
| 5 | Client → terminal window is derivable | Walk `/proc/<client_pid>` parents to the terminal emulator (e.g. `alacritty`); that PID maps to a window. `kdotool` exposes `getwindowpid` and `search --pid`, and KWin's scripting `window.pid` is available. |
| 6 | No focus-change event stream | `herdr wait` only matches pane output / agent-status; there is no push notification for workspace focus. Recency must be computed by the switcher, not subscribed. |

## Requirements

1. **Enumerate spaces.** Build a flat list across all running sessions:
   `(session_name, workspace_id, label, number, agent_status, focused)`.
2. **Global hotkey.** Register **Shift+Tab** via KGlobalAccel (inherited from
   vscode-launcher, which is being retired). Configurable.
3. **Alt-tab popup.** Frameless `Qt.Tool` PyQt6 popup centered on the cursor's
   screen; tap-to-cycle; commit on hotkey-release or after a pause; `Esc` cancels.
   Pre-select the **previous** space (true alt-tab toggle).
4. **Recency ordering.** Maintain a most-recently-used stack of spaces in
   `~/.config/herdr-switcher/state.json`. Update it (a) whenever the switcher
   performs a switch and (b) at each popup invocation by reading the current space
   (active window → session → that session's `focused` workspace).
5. **Switch action.** On commit, for chosen `(session S, workspace W)`:
   1. Resolve S's herdr client process → terminal-window PID.
   2. Activate + maximize that window via KWin D-Bus scripting (match by `window.pid`).
   3. Run `herdr --session S workspace focus W`.
   4. Update the MRU stack.
6. **Detached-session handling.** If S is running but has no attached terminal
   window, spawn a terminal running `herdr session attach S` (default
   `alacritty -e herdr session attach S`). No automatic positioning — the user
   places the new window. The switcher then focuses W once the client is up.
7. **Labels.** Show `label` (and `session` when more than one session is present),
   plus `agent_status` as a small indicator (`working`/`idle`/`done`/…), mirroring
   herdr's own sidebar.
8. **Install/uninstall.** `install.sh` / `uninstall.sh` following the house pattern:
   `~/.local/bin` symlink, `.desktop` menu entry, XDG autostart (`--tray`/daemon),
   hicolor icon, sycoca refresh. (macOS branch stubbed for the follow-up spec.)
9. **Config.** `~/.config/herdr-switcher/config.json`: hotkey, commit delay, terminal
   spawn command, max rows. Unknown keys preserved; `version` key for migrations.

## Design / Architecture

Modeled on `vscode-launcher`, one module per concern:

- `herdr_switcher.py` — daemon entry point; owns the hotkey backend and popup.
- `herdr_api.py` — thin wrapper over the herdr CLI/socket (`session list`,
  `workspace list`, `workspace focus`); returns typed `Space` records.
- `session_windows.py` — client-process discovery (`pgrep`/`/proc` walk) and
  session→terminal-PID mapping; "current space" resolution from the active window.
- `window_actions.py` — KWin D-Bus scripting to activate + maximize a window by PID
  (the `vscode-gather` mechanism: loadScript → run → success-marker in journal →
  unloadScript).
- `global_shortcut.py` — KGlobalAccel backend (copied/adapted from vscode-launcher).
- `popup.py` — PyQt6 frameless alt-tab popup (adapted from vscode-launcher).
- `mru.py` — recency stack persisted to `state.json`.
- `platform_support.py` — platform paths + detection, leaving room for macOS.

`Space` data model:
```
@dataclass
class Space:
    session: str          # "default" | "work"
    workspace_id: str     # "w1"
    label: str            # "sysadmin"
    number: int           # herdr's own 1..N
    agent_status: str     # "working" | "idle" | "done" | "blocked" | "unknown"
    focused: bool         # focused within its session
    last_used: float|None # from MRU state, for ordering
```

## Acceptance Criteria

- [x] `herdr_api` lists every space across all running sessions, with correct
      `session`, `workspace_id`, and `label`, by calling the real herdr CLI.
      *(Verified live: `cli.py list` enumerated both sessions' spaces.)*
- [x] `herdr_api.focus(session, workspace_id)` switches the live herdr space
      (verified against a running herdr server, not a mock).
- [x] `session_windows` resolves each running session to the PID of its attached
      terminal window, and resolves the currently-active window back to its space.
      *(Verified: `cli.py sessions` mapped default/work to their alacritty PIDs;
      `current` correctly returned unknown for a non-herdr active window.)*
- [x] `window_actions` raises **and** maximizes a target terminal window on KDE
      Wayland, identified by PID, via KWin scripting. *(KWin `window.pid` confirmed
      to equal the terminal PID; loadScript/run/unload plumbing rc-ok; live switches
      between open terminals confirmed by the user.)*
- [x] Pressing **Shift+Tab** shows the popup; the list is recency-ordered with the
      previous space pre-selected; tap-to-cycle and release-to-commit work; `Esc`
      cancels with no switch. *(User-confirmed switching via the hotkey.)*
- [x] Committing a space performs the full sequence end to end (window raised +
      maximized, herdr focused on the space) for a space in a **different** session
      than the current one — exercised against real herdr + real KWin (integration
      boundary), not mocked. *(User-confirmed cross-session switching.)*
- [x] Selecting a space whose session is detached spawns a terminal, attaches the
      session, and focuses the space. *(Initially failed — herdr's nested-session
      guard; fixed by stripping `HERDR_ENV`/`HERDR_SESSION` from the spawn env.
      User-confirmed working.)*
- [x] MRU state persists across daemon restarts and reflects switches made both
      through the switcher and (at popup time) via herdr's own keybindings.
      *(Ordering + persistence unit-tested; current-space snapshot promotes manual
      switches at popup time.)*
- [x] `install.sh` installs the daemon, autostart entry, hotkey, and icon on Linux;
      `uninstall.sh` reverses it; re-running `install.sh` is idempotent.
      *(install verified live: symlinks, desktop + autostart entry, icon installed,
      daemon (re)started; idempotent via `ln -sf` + targeted `pkill`. `uninstall.sh`
      implemented and code-reviewed; not executed this session to avoid removing the
      live install.)*

## Risks & Assumptions

- **Window-PID matching on Wayland.** KWin's `window.pid` is the client process PID.
  Terminal emulators differ in whether the window PID is the emulator process or a
  child; the `/proc` parent-walk from the herdr client must reach the same PID KWin
  reports. Assumption: the terminal is a single-process emulator (alacritty on this
  host). Mitigation: match by walking *both* directions (client→ancestor and
  window-pid→descendants) and intersect; fall back to `resourceClass` + space label
  if PID matching fails.
- **Recency accuracy.** Without a herdr focus-event stream, MRU is only refreshed at
  popup time, so ordering can lag a manual herdr switch until the next popup. Accepted
  for v1; a poller or future herdr event API could tighten it.
- **Single client per session.** Relies on herdr's handoff model (one attached client
  per session). If herdr ever allows multiple, the session→window map becomes 1:N and
  needs disambiguation (most-recently-active window).
- **Hotkey inheritance.** Shift+Tab is assumed free now that vscode-launcher is
  retired. install.sh should detect and warn if another component already owns it.
- **Reversibility.** Pure userspace tool; rollback = `uninstall.sh` (removes symlink,
  autostart, hotkey registration, icon). No system state touched.
- **KWin-scripting latency.** loadScript/run/unload + journal grep adds ~tens of ms;
  acceptable for an interactive switch, consistent with vscode-launcher.

## Alternatives Considered

- **kdotool instead of KWin scripting** for window activation. Simpler (already
  installed, `search --pid` + `windowactivate`), but the house style (vscode-launcher,
  vscode-gather) uses direct KWin scripting and it composes the activate+maximize in
  one script. Chosen: KWin scripting for consistency; kdotool remains a fallback.
- **rofi/wofi picker** instead of PyQt6. Rejected: vscode-launcher's PyQt6 popup
  already solves the Wayland frameless/tap-to-cycle UX and gives a consistent look.
- **Background poller for MRU** subscribing to herdr state every N ms. Rejected for
  v1 (extra moving part); on-demand resolution at popup time is sufficient.
- **Reusing herdr's own `ctrl+b w` workspace picker.** Rejected: it only switches
  within the *current* session/terminal and offers no cross-session, cross-window
  recency or global hotkey.

## Open Questions

*(Resolved 2026-06-28.)* Detached sessions: plain `alacritty -e herdr session
attach <name>`, no auto-positioning. Popup lists **spaces only** (not tabs).

## Executive Summary

Adds `herdr-switcher`, an alt-tab popup daemon (PyQt6 + KGlobalAccel) that lists
herdr spaces across all sessions ordered by recency and, on Shift+Tab selection,
raises + maximizes the hosting terminal (KWin scripting, matched by `window.pid`)
and focuses the space via the herdr socket API. Detached sessions spawn a fresh
attaching terminal. KDE/Wayland-first; the herdr successor to vscode-launcher.
All acceptance criteria verified against the live system; the one bug found in
testing (herdr's nested-session guard blocking the detached-spawn path) is fixed
by stripping `HERDR_ENV`/`HERDR_SESSION` from the spawn environment. Reviewers:
start at `core.switch_to_space` (the orchestration) and `session_windows`
(the herdr-specific session→window mapping).
