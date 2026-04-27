# Spec 012: Tray-Resident Daemon + Global Quick-Launcher Popup

**Status: COMPLETE**

## Description

Adds an Alt-Tab-style popup to the launcher, triggered by a global hotkey
that fires from any app focus. Pressing the configured combo (default
`Meta+Alt+Space`) shows a centered, frameless list of workspaces with
running ones first. Tab and arrow keys cycle the selection. Releasing
the hotkey activates the highlighted workspace: running workspaces get
focused via the existing KWin-scripting Activate path, non-running
workspaces get launched via the existing `code --new-window` path.

To make press-and-release work from a cold start, the launcher becomes
**tray-resident**. A QSystemTrayIcon keeps the process alive after the
main window closes, the global shortcut stays registered, and the scanner
warm-cache is preserved so the popup renders the latest state with no
visible lag.

## Goals

- One-keystroke jump to any workspace, regardless of which app currently
  has focus
- Both running (focus existing window) and not-running (launch new) cases
  handled in the same flow — quick-launcher behavior, not strict Alt-Tab
- Hotkey is user-configurable from the main window; rebinding takes effect
  immediately without a restart
- Daemon installs at login via XDG autostart so the popup is available
  from session start
- Backward-compatible CLI: `vscode-launcher` with no args still gets the
  user to a working main window

## Non-Goals

- Multi-monitor popup placement strategies beyond "the screen the cursor
  is on"
- Search-as-you-type filtering inside the popup
- Window thumbnails or VSCode icons in the popup rows
- Customizing keys beyond the trigger combo (Tab cycles, Esc cancels,
  Enter activates — these are not configurable)
- Cross-platform daemon support: tray-resident mode is KDE Plasma 6
  specific because the global-shortcut path is KGlobalAccel; macOS and
  Windows would need separate work tracked by spec 010

## Requirements

### Tray-resident daemon mode

- New CLI flag: `--tray`. Starts the launcher with the main window hidden
  but the system tray icon and global shortcut active. This is the mode
  the autostart `.desktop` invokes.
- `vscode-launcher` with no args keeps existing behavior: opens the main
  window, exits when the window closes. No tray, no global shortcut.
  This preserves backward compatibility for users who upgrade and run
  the launcher manually.
- In `--tray` mode, closing the main window via the X button hides it
  to the tray instead of exiting. The tray icon's right-click menu has
  an explicit Quit action.
- Tray icon left-click toggles main-window visibility.

### Single-instance enforcement

- KGlobalAccel naturally refuses to register a duplicate component, so
  a second `--tray` invocation fails when the existing daemon already
  holds the binding. The second process detects the failed registration,
  prints a one-line message to stderr ("vscode-launcher daemon already
  running"), and exits cleanly.
- The non-daemon `vscode-launcher` (no args) does not enforce
  single-instance at all. Two main windows running side by side is
  harmless: both read the same config, both see the same recents.

### Global shortcut

- Productionized version of the spike at
  `research/global_shortcut_spike.py`. Lives at `global_shortcut.py`.
- `GlobalShortcut(QObject)` wraps KGlobalAccel registration with
  signals `pressed` and `released` (both forwarded from
  `org.kde.kglobalaccel.Component`).
- `set_binding(qt_key_code: int) -> bool` registers / re-registers the
  shortcut with KGlobalAccel. Returns False if KGlobalAccel reports
  the combo is unavailable (taken by another component).
- Released signal is the primary activation trigger (KGlobalAccel
  surfaces it natively, no Wayland keyboard grab needed).
- `unregister()` is called from the daemon's shutdown path; verified
  cleanup leaves no entries in `~/.config/kglobalshortcutsrc`.

### Popup widget

- New `popup.py` exposing `WorkspacePopup(QWidget)`.
- Frameless, always-on-top (`Qt.WindowType.Popup | FramelessWindowHint
  | Tool`), centered on the screen containing the mouse cursor.
- Shows a flat list of workspaces:
  - Running workspaces first (matches main window's running-first sort)
  - Each row: status dot (green for running, dim for not), workspace
    label, current selection has a highlighted background
  - No checkboxes, no per-row buttons (popup is single-purpose)
- Keyboard:
  - `Tab`, `Down`, `Right`: next selection (wraps)
  - `Shift+Tab`, `Up`, `Left`: previous selection (wraps)
  - `Enter`: activate current selection
  - `Esc`: cancel, close popup
- Mouse: click on a row activates it.
- Closing semantics:
  - On hotkey-release: activate current selection
  - On Enter: activate current selection
  - On Esc or click outside: dismiss without activation
  - On focus-out: dismiss without activation (covers edge cases like
    user clicking elsewhere mid-popup)
- Activation:
  - Running workspace: `WindowScanner.perform_window_action(label,
    ACTION_ACTIVATE)` (existing path)
  - Not-running workspace: `Launcher.launch_workspace(workspace)` plus
    schedule the existing post-launch `vscode-gather` call
  - In both cases, the launcher's tracked-launch-time dict is updated
    when applicable

### Hotkey configuration

- New config field: `"global_hotkey": "Meta+Alt+Space"` in `workspaces.json`
  (default value). Stored as a `QKeySequence`-parseable string.
- Main-window UI: a new **Settings…** toolbar button opens a small
  modal dialog with a `QKeySequenceEdit` widget for the hotkey. OK
  applies, Cancel discards. Settings dialog is the single home for
  any future tuning.
- Applying a new combo triggers `GlobalShortcut.set_binding(new_combo)`.
  On rebind failure (combo unavailable), the dialog stays open with a
  warning label and the previous binding remains active.
- Daemon-mode launches read the hotkey from config at startup; if the
  config field is missing or the parse fails, fall back to the default
  `Meta+Alt+Space`.
- If the launcher is running in non-daemon mode (no `--tray`), the
  Settings dialog can still edit the hotkey value and persist it, but
  the change only takes effect at the next daemon start. The dialog
  surfaces this with a hint label.

### Autostart

- `install.sh` writes `vscode-launcher.desktop` to
  `~/.config/autostart/` with `Exec=vscode-launcher --tray`.
- `uninstall.sh` removes the autostart file.
- Reuses the same icon as the menu entry.
- `install.sh` does NOT spawn a daemon during installation (avoids
  fighting an already-running launcher). It prints a one-line note
  asking the user to log out and back in for tray mode to take effect.

### Backwards compatibility

- All existing CLI invocations and behaviors continue to work.
- `Refresh`, per-row Stop/Activate/Start, manual launch, tmux mapping,
  hide/unhide all work unchanged.
- Existing config files without a `global_hotkey` key load successfully
  (default applied, no migration warning).

## Acceptance Criteria

(Criteria reflect the as-built design after live testing on Wayland; see
"Post-implementation deltas" below for the changes from the original
spec.)

- [x] `vscode-launcher` starts a tray-resident daemon and shows the main
      window. `vscode-launcher --tray` does the same but starts hidden
      (used by autostart).
- [x] Closing the main window (X button) hides it to the tray instead of
      exiting. Tray right-click → Quit explicitly exits.
- [x] Tray icon left-click toggles main-window visibility.
- [x] Second `vscode-launcher` invocation while a daemon is running calls
      `ShowMainWindow` over D-Bus on the existing daemon (which surfaces
      its main window) and exits with status 0. Second `--tray`
      invocation exits silently (autostart racing manual run).
- [x] Tapping the configured hotkey from any app focus shows the popup
      centered on the active screen.
- [x] Tap-to-cycle: each subsequent tap of the hotkey advances to the
      next entry (wrap-around). Backtab is a separate KGlobalAccel-bound
      shortcut on most KDE setups; arrow keys do not work because Wayland
      blocks keyboard focus on hotkey-triggered popup windows.
- [x] After the configured commit delay (default 600 ms, range 100-5000)
      with no further taps, the popup activates the current selection:
      focus for running workspaces, launch for non-running.
- [x] Mouse-click on a row commits immediately.
- [x] Hotkey and commit delay are read from `workspaces.json`
      (`global_hotkey`, `popup_commit_delay_ms`). Defaults: `Shift+Tab`,
      600 ms.
- [x] Settings dialog edits both fields and applies them live to the
      running daemon (no restart needed) when KGlobalAccel is reachable.
- [x] Rebind to an unavailable combo shows a warning; the previous
      binding remains active and the dialog stays open for retry.
- [x] Activated workspaces (via popup commit, per-row Activate, or
      launch) are tracked per-path and bubble to the top of the running
      group on subsequent renders.
- [x] Auto-refresh runs continuously while the daemon is up (no
      visibility gate), so the popup always sees current `is_running`
      state. Two extra scans are scheduled at 2.5 s and 5 s after a
      launch to catch the new VSCode IPC socket.
- [x] `install.sh` writes the autostart `.desktop`. `uninstall.sh`
      removes it.
- [x] On Quit (closeEvent path with `tray_mode=False`), the global
      shortcut is unregistered cleanly via `KGlobalAccel.unRegister`.
- [x] Full test suite passes (152 tests: baseline plus new tests for
      popup cycle logic, hotkey parsing, KGlobalAccel-unavailable
      fallback, and `popup_commit_delay_ms` config round-trip).

## Post-implementation deltas

Differences between this spec as originally written and what shipped,
recorded for future readers:

1. **Default hotkey: `Shift+Tab`, not `Meta+Alt+Space`.** User preference
   after testing. Configurable via Settings.

2. **Popup uses tap-to-cycle, not hold-and-arrow.** Wayland blocks
   keyboard focus on global-hotkey-triggered windows ("Failed to create
   grabbing popup" with `Qt.WindowType.Popup`; even with `Qt.WindowType.Tool`,
   `activateWindow()` is rejected by the compositor). Arrow / Tab / Enter
   / Esc inside the popup do not reach the widget. The replacement model:
   each press of the hotkey advances the selection; a configurable
   commit delay (default 600 ms) after the last release activates the
   current entry. Mouse-click commits immediately. This is the entire
   reason for the `popup_commit_delay_ms` config field.

3. **Tray-resident is the only mode.** Original spec made it opt-in via
   `--tray` and preserved a no-flag "open main window, exit on close"
   path. After testing, this proved confusing: closing the main window
   either tore down the daemon or hid to tray depending on flag. The new
   model is one mode, one daemon. `--tray` now means "don't auto-show
   the main window on launch" — exclusively used by the autostart entry.

4. **Single-instance via D-Bus, not just KGlobalAccel.** Original spec
   relied on KGlobalAccel's natural duplicate-rejection. That worked but
   left the second invocation with no useful action; the user had to
   click the tray icon. Production version registers
   `org.kde.vscode_launcher` on the session bus and exposes
   `ShowMainWindow`. Second invocation surfaces the existing daemon's
   main window. Implemented in `single_instance.py`.

5. **Activation MRU added.** Original spec preserved VSCode's own MRU
   within the running group. After testing, this felt stale: clicking
   workspace B in the popup wouldn't move B above workspace A on the
   next show. Added per-path `_activated_at_by_path` dict, updated on
   every commit, used as a sort key (running first, then by recent
   activation, then by VSCode-recents order).

6. **Auto-refresh visibility gate dropped.** Original implementation
   gated `_trigger_background_scan` on `self.isVisible()` to avoid
   wasting CPU. Tray-resident default makes the main window hidden most
   of the time, but the popup needs current state. The 5 s scan now
   runs continuously while the daemon is up.

7. **Post-launch scan scheduling.** A launched VSCode window takes 1-3 s
   to bind its IPC socket; the next 5 s auto-refresh tick may miss it.
   Added explicit `QTimer.singleShot(2500, ...)` and
   `QTimer.singleShot(5000, ...)` scans after each launch so the popup
   reflects the new running state quickly.

8. **`popup_commit_delay_ms` is config-driven and Settings-tunable.**
   Original spec had no notion of a commit delay because it relied on
   keyboard focus. The new tap-to-cycle model needs a tunable.

## Architecture

### New modules

- `global_shortcut.py` — `GlobalShortcut(QObject)` class. Wraps the
  KGlobalAccel D-Bus surface (registration, binding, signals).
  Independent of UI; reusable.
- `popup.py` — `WorkspacePopup(QWidget)` class. Pure UI: takes a list
  of `Workspace` instances, emits `activate_requested(workspace)` on
  release/Enter/click and `cancelled()` on Esc/focus-out. No knowledge
  of the scanner or launcher.
- `single_instance.py` — small module with `claim_or_signal()` helper
  that registers the D-Bus service and either returns "you are the
  daemon" or signals an existing daemon to show its window.

### Modified modules

- `vscode_launcher.py`:
  - `main()` parses `--tray` and decides between tray-only / tray-plus-window
  - `MainWindow` gets:
    - System tray integration (`QSystemTrayIcon` + context menu)
    - Hotkey config UI (`QKeySequenceEdit` + Apply button)
    - References to `GlobalShortcut` and `WorkspacePopup`
    - Hotkey-pressed handler: shows popup with current workspace list
    - Hotkey-released handler: forwards activation to popup
  - `closeEvent`: hide-to-tray when in daemon mode
- `install.sh` / `uninstall.sh`: autostart entry management

### Workspace list reused, not duplicated

The popup consumes the same `MainWindow.workspaces` list. On
`pressed`, the daemon snapshots the list (already sorted running-first
by the existing auto-refresh logic), passes it to the popup, and shows
the widget. No new scanning happens at popup-show time — the 5 s
auto-refresh already keeps the data current, and the IPC scan takes
~3 ms anyway, so a fresh scan can be triggered if the cache feels stale
(future tweak; not in v3.0 scope).

### Activation routing

`WorkspacePopup.activate_requested(workspace)` is wired in `MainWindow`
to a new `_launch_or_activate(workspace)` helper. The helper centralizes
the running-vs-not-running branch so the popup, the per-row Start /
Activate buttons, and any future caller (context menu, etc.) all share
one entry point:

- Running workspace: `self.window_scanner.perform_window_action(workspace.label, ACTION_ACTIVATE)`
- Not-running workspace: `self._launch_paths([workspace.path], allow_running=True)`

Both paths already exist; no new launching or activating logic.

## Implementation Notes

- **Single-instance D-Bus service name**: `org.kde.vscode_launcher`.
  Underscore matches the KDE convention for non-namespaced session
  service names. The service exposes one method, `ShowMainWindow()`,
  with no arguments.
- **Hotkey parsing**: `QKeySequence.fromString(string).toCombined()`
  produces the int that `setShortcut` expects. Store the human-readable
  string in config, convert at registration time.
- **Active-screen detection** (for popup centering): `QApplication.screenAt(QCursor.pos())`,
  fall back to `QGuiApplication.primaryScreen()` if None.
- **Popup geometry**: fixed width (e.g., 480 px), height grows with item
  count up to a cap of 60 % of screen height; scrollbar above that.
- **Focus-out handling**: connect to `WorkspacePopup.focusOutEvent` and
  emit `cancelled`. Combined with the explicit Esc key, covers all
  dismissal paths.
- **Shortcut-already-bound failure**: KGlobalAccel's `setShortcut`
  returns the bound keys; if the returned list doesn't match what was
  requested, the combo was already taken. The `set_binding` helper
  surfaces this as a False return value.
- **Hotkey re-registration**: rebind by calling `setShortcut` again
  with the new combo. KGlobalAccel handles the swap atomically; no
  need to `unRegister` first.
- **D-Bus signal connection lifetime**: per the v1.6 lessons memory,
  hold an explicit Python reference to any `QObject` whose signals are
  routed through QtDBus. The spike already does this (the slot is a
  bound method on `self`); production version preserves the pattern.

## Alternatives Considered

- **Timer-based release fallback** (decided in earlier discussion).
  Spike 1 found that KGlobalAccel emits a native `globalShortcutReleased`
  signal, so strict press-and-release works without timers or
  Wayland-grab tricks. Timer kept only as a safety net inside the popup
  (auto-dismiss after N seconds with no input).
- **`org.freedesktop.portal.GlobalShortcuts` instead of KGlobalAccel**.
  More portable in principle, more involved API. KGlobalAccel matches
  the existing "use the KDE-native interface and degrade later" pattern
  in this codebase.
- **Spawning the launcher per-press**. Rejected. Cold-start latency
  (Python + PyQt + scanner warm-up) adds up to enough to make press-and-
  release feel sluggish. Daemon mode is the requirement.
- **Showing main window as the popup**. Rejected. The main window has
  toolbar, columns, scrolling, edit dialogs — too heavy for a press-and-
  release Alt-Tab. A purpose-built popup is faster to render and easier
  to dismiss.
- **Auto-installing autostart by default vs. opt-in via flag**. Decided
  to always install per user preference. `uninstall.sh` removes it.
