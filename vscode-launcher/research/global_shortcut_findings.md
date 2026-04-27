# Spike 1 findings: KGlobalAccel global shortcut from PyQt

## Test instructions

```bash
/usr/bin/python3 vscode-launcher/research/global_shortcut_spike.py --seconds 30
```

Then press `Meta+Alt+Space` from any application. Expected output per
press-and-release:

```
[spike] PRESS    component='vscode-launcher-spike' action='show-popup' ts=...
[spike] RELEASE  component='vscode-launcher-spike' action='show-popup' ts=...
```

`Ctrl-C` cleanly unregisters before exit.

## Confirmed

- **PyQt6 QtDBus can speak to KGlobalAccel**. `org.kde.kglobalaccel /kglobalaccel`
  exposes the methods we need: `doRegister`, `setShortcut`, `unRegister`.
- **Type marshaling**: PyQt6's auto-conversion gets the `actionId` `QStringList`
  wrong (sends `av`); explicit `QDBusArgument.add(values, QMetaType.Type.QStringList.value)`
  fixes it. Same story for the `ai` key array and the `uint` flags arg.
- **Component object path**: KGlobalAccel translates dashes in the
  componentUnique to underscores. So a registration with
  `vscode-launcher-spike` lives at `/component/vscode_launcher_spike`.
- **Both press AND release signals exist** on the component object:
  - `globalShortcutPressed(componentUnique, actionUnique, timestamp)`
  - `globalShortcutReleased(componentUnique, actionUnique, timestamp)`
- **Cleanup**: calling `unRegister(actionId)` on shutdown removes the
  binding cleanly. No leftover entries in `~/.config/kglobalshortcutsrc`
  after the spike exits.

## Implication for the popup feature

The release signal changes the design. The original plan (per the
"Decisions noted" message in this conversation) was timer-based release
semantics because Wayland keyboard grab + release detection looked hard.

KGlobalAccel hands us the release event natively. **Strict Vivaldi-style
press-and-release is achievable**, with no keyboard grab needed for
release detection. The popup just listens for `globalShortcutReleased`
and activates the current selection.

The timer is still useful as a safety fallback (in case a user releases
the modifier keys without releasing the trigger key in a way KGlobalAccel
captures), but the primary activation path can be release-driven.

## Sketch of the production wire-up

```
GlobalShortcut (QObject)
  signals:
    activated()    # forwarded from globalShortcutPressed
    deactivated()  # forwarded from globalShortcutReleased
  methods:
    set_binding(qt_key_code: int)  # rebind on settings change
    unregister()                    # called from MainWindow.closeEvent
```

`MainWindow` (in tray-resident mode) holds one `GlobalShortcut`,
configured from `workspaces.json` (`global_hotkey: "Meta+Alt+Space"`).
On `activated`, popup is shown; on `deactivated`, current selection
activates and popup hides.

## Implementation notes (carry forward from spike to production)

- `actionId` is a 4-element `QStringList`:
  `[componentUnique, actionUnique, componentFriendly, actionFriendly]`.
  componentFriendly and actionFriendly show up in System Settings →
  Shortcuts so users can remap, which is desirable. Use `"VSCode Launcher"`
  and `"Show popup"`.
- `setShortcut` flags: `SetPresent | NoAutoloading` (`0x1 | 0x2 = 0x3`).
  `SetPresent` records this as the current binding; `NoAutoloading` says
  "don't override what the user has set in `kglobalshortcutsrc` if
  they've remapped it via System Settings".
- Qt key codes for combos: OR the modifier flags with the base key:
  `Qt.Key_Space | Qt.MetaModifier | Qt.AltModifier`.
- `QKeySequence.fromString("Meta+Alt+Space")` parses user-friendly
  strings into a sequence; `.toCombined()` gives the `Qt.Key | mods` int
  we need to pass to `setShortcut`. Useful for converting the config-file
  value into the right wire format.

## Open question for production

Whether to register under a stable component name (`vscode-launcher`)
that survives shortcut config rewrites, or use a versioned name. Stable
is better for users who rebind the shortcut in System Settings — their
binding survives launcher upgrades. `vscode-launcher` it is.
