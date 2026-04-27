# slack-presence-toggle prototypes

Throwaway scripts for validating the design of the future slack-presence-toggle
utility. None of this gets installed to the standard locations the eventual
sub-project will use — it lives in `prototypes/` precisely so we can rip it out
or rewrite it once we've answered the open questions.

## Prototype A — Focus detection

Validates: can a KWin script reliably detect window focus changes on KDE
Plasma 6 / Wayland and forward them to a Python process?

### Pieces

- `kwin-script/` — minimal KWin JS script that subscribes to
  `workspace.windowActivated` and calls a D-Bus method on every event.
- `focus_listener.py` — Python service that registers the bus name, receives
  the calls, and prints them with timestamps.

### Run it

1. Install the KWin script:

   ```bash
   ./kwin-script/install.sh
   ```

   This copies the script into `~/.local/share/kwin/scripts/`, enables it in
   `kwinrc`, and forces a reload via the `org.kde.KWin /Scripting` D-Bus
   interface.

2. In a terminal, confirm the script is firing:

   ```bash
   journalctl --user -f | grep slack-focus-monitor
   ```

   Alt-tab between a few windows. Lines like
   `slack-focus-monitor: activated rc=firefox ...` should appear.

3. In another terminal, start the listener:

   ```bash
   python3 focus_listener.py
   ```

   Output looks like:

   ```
   [13:44:02] INIT    rc='firefox'              dt= 0.00s  caption='Inbox — Mozilla Firefox'
   [13:44:05] CHANGE  rc='slack'                dt= 2.81s  caption='Slack | general | Anthropic'
   [13:44:09] CHANGE  rc='konsole'              dt= 4.12s  caption='nverenin@cachyos: ~'
   ```

### What we're looking for

- Every focus change fires a `CHANGE` event (no missed events).
- The Slack desktop app's `resourceClass` — record it; that's what the eventual
  utility will match on. Likely `slack` but worth confirming.
- No flapping: a single alt-tab should produce one event, not many.
- Latency: `dt` should be small (<100ms) and reflect actual switch time.

### Uninstall

```bash
./kwin-script/uninstall.sh
```

Removes the script from `~/.local/share/kwin/scripts/`, disables it in
`kwinrc`, and reloads KWin.

## Prototype B — Slack API round-trip

Not yet built. Will land here as `set_presence.py` once you've created a Slack
app with the `users:write` scope and have a User OAuth token (xoxp-...).

## Dependencies

System packages (Arch / CachyOS):

```bash
sudo pacman -S python-dbus python-gobject
```

These are typically already installed by KDE/Plasma. The listener will print a
clear error if they're missing.
