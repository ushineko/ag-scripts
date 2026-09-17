# Browser Router

Routes URLs to different browsers based on domain patterns. Created to work around Chromium/Vivaldi lacking PipeWire camera support on Wayland.

**Version:** 1.4

## Table of Contents

- [Problem](#problem)
- [Solution](#solution)
- [Installation](#installation)
- [Uninstallation](#uninstallation)
- [Configuration](#configuration)
- [Primary Window (Vivaldi multi-window Wayland fix)](#primary-window-vivaldi-multi-window-wayland-fix)
- [How It Works](#how-it-works)
- [Adding More Domains](#adding-more-domains)
- [Files](#files)

## Problem

On Linux with Wayland and PipeWire:
- Firefox: Webcam works via native GStreamer/PipeWire integration
- Chromium/Vivaldi: Webcam does not work (PipeWire camera support incomplete upstream)

This is a known Chromium limitation. The `WebRTCPipeWireCapturer` flag handles screen capture but not camera capture.

## Solution

Use a URL router script as the default browser handler:
- URLs matching webcam-dependent sites (Teams, etc.) open in Firefox
- All other URLs open in Vivaldi

This keeps Vivaldi as the effective default browser while routing specific sites to Firefox where the webcam works.

## Installation

```bash
cd ~/git/ag-scripts/browser-router
./install.sh
```

The installer:
1. Copies `browser-router.sh` to `~/.local/bin/browser-router`
2. Installs the desktop file to `~/.local/share/applications/`
3. Sets browser-router as the default handler for `http://` and `https://` URLs
4. Backs up your existing `mimeapps.list`

## Uninstallation

```bash
cd ~/git/ag-scripts/browser-router
./uninstall.sh
```

The uninstaller:
1. Removes the script from `~/.local/bin/`
2. Removes the desktop file
3. Restores Vivaldi as the default browser

## Configuration

Edit `~/.local/bin/browser-router` to customize routing patterns.

Default configuration routes these domains to Firefox:
- `teams.microsoft.com`
- `teams.live.com`
- `outlook.office.com`
- `outlook.office365.com`
- `outlook.live.com`
- `*.sharepoint.com`
- `onedrive.live.com`
- `office.com`
- `app.slack.com`

Everything else goes to Vivaldi.

## Primary Window (Vivaldi multi-window Wayland fix)

### The problem

On Wayland, when Vivaldi is already running and you open a link, the launcher
(`vivaldi-stable <url>`) hands the URL to the existing browser over Chromium's
singleton socket. Vivaldi then tries to open the tab in its internally-tracked
*last-active window*. If that window can't be activated by the client — Wayland
forbids clients from stealing focus, and the xdg-activation token is **not**
relayed across the singleton socket — Vivaldi drops the open entirely. With two
or more Vivaldi windows open (e.g. one per monitor), the target window just
"flashes" and no tab appears; you have to click your main window first, then
retry the link. This is a Vivaldi/Chromium-on-Wayland bug, not a router bug —
the router only forwards one URL and has no say in which window Chromium picks.

### The fix

Before forwarding the URL, the router asks **KWin** (the Plasma compositor) to
activate and raise a Vivaldi window on your primary monitor. KWin is the
compositor, so it is *not* bound by the client focus-stealing restriction — it
can activate any window. Vivaldi then sees that window gain focus, forwards the
URL into it, and it is already on top, which is what you want anyway (read the
page immediately).

It asks over plain D-Bus: `WindowsRunner` for the Vivaldi window ids,
`org.kde.KWin.getWindowInfo` for each one's geometry, then `WindowsRunner.Run`
to activate the one whose centre falls on the target monitor. Two ~8 ms calls
per window.

It deliberately does **not** use KWin's `Scripting` interface. `loadScript`
returns an id that can collide with an already-exposed `/Scripting/ScriptN`
object while creating nothing, after which `run()` on that path is a silent
no-op against somebody else's script. That is what broke v1.3 — see the
changelog.

This runs only on the Vivaldi path, and is best-effort: if the D-Bus tools are
unavailable, or no Vivaldi window exists at all (e.g. cold start), the router
silently falls back to a plain hand-off — identical to prior behavior. If Vivaldi
windows exist but none is on the target monitor, it activates one of them anyway,
which still beats dropping the URL. It adds ~0.4 s to Vivaldi-routed link clicks.

### Configuration

Precedence (lowest to highest):

1. Built-in default: `auto`
2. Config file `~/.config/browser-router/config` (a shell fragment, sourced)
3. Environment variable `BROWSER_ROUTER_PRIMARY_OUTPUT` (wins over both)

Accepted values:

| Value | Meaning |
|---|---|
| `auto` | Resolve Plasma's primary (lowest `priority`) output at run time. The default. |
| `DP-3` or `DP-3,HDMI-A-1` | Explicit KWin connector name(s). A name that is not currently enabled is skipped; if none match, falls back to `auto`. |
| *(empty)* | Disable the behaviour entirely, plain hand-off. |

Find connector names with `kscreen-doctor -o`, but prefer `auto`: a connector
name describes which **port a cable is in**, not which monitor is on your desk,
so moving a cable renames it and an explicit value goes stale.

### Debugging

The router runs as the desktop's `http`/`https` handler, so nothing it prints is
normally visible. To see every decision:

```bash
BROWSER_ROUTER_DEBUG=1 ~/.local/bin/browser-router https://example.com
browser-router: routing to vivaldi: https://example.com
browser-router: target output auto rect=0 1120 2560 1440
browser-router: window {9ff9d859-...} at 0,1120 2560x1440 is on the target output
browser-router: activated 0_{9ff9d859-...}
```

### Tests

`tests/test_output_rect.sh` covers the output-rectangle arithmetic (scale,
rotation, priority, absent and disabled outputs) against a fixture, with no
compositor needed. Run it directly; no framework required.

## How It Works

1. When you click a URL anywhere in the system, `xdg-open` checks `~/.config/mimeapps.list`
2. The `browser-router.desktop` entry is set as the handler for `http://` and `https://`
3. The desktop file launches `browser-router.sh` with the URL as an argument
4. The script checks if the URL matches any Firefox patterns
5. If matched, opens in Firefox; otherwise opens in Vivaldi

## Adding More Domains

Edit `~/.local/bin/browser-router` and extend the if statement:

```bash
# Route webcam-dependent sites to Firefox
if [[ "$url" == *"teams.microsoft.com"* ]] || \
   [[ "$url" == *"teams.live.com"* ]] || \
   [[ "$url" == *"meet.google.com"* ]] || \
   [[ "$url" == *"zoom.us"* ]]; then
    exec firefox "$url"
else
    exec vivaldi-stable "$url"
fi
```

## Files

| File | Purpose |
|------|---------|
| `browser-router.sh` | Main routing script |
| `browser-router.desktop` | XDG desktop entry template |
| `install.sh` | Installation script |
| `uninstall.sh` | Uninstallation script |

## Changelog

### v1.4 (2026-09-17)
- **Fix: primary-window activation had silently stopped working.** Two
  independent defects, either fatal on its own:
  - The default `PRIMARY_OUTPUT` was the hardcoded connector `HDMI-A-1`. Moving
    the monitor to another port renamed it `DP-3`, so the name matched nothing.
    The default is now `auto`, resolved from kscreen's `priority` at run time,
    and an explicit name that is not currently enabled falls back to `auto`
    instead of doing nothing.
  - Activation used KWin's `Scripting` D-Bus interface. On this machine
    `loadScript` returns id `3` while `/Scripting/Script3` already exists and
    creates **no object**, for any plugin name — `run()` then silently addressed
    another script. Replaced with `WindowsRunner` + `getWindowInfo`, which have
    no object lifetimes to get wrong.
- Add `BROWSER_ROUTER_DEBUG=1` tracing. Neither defect was observable before.
- Fall back to any Vivaldi window when none is on the target output.
- `install.sh` writes through a symlinked target instead of replacing it, so a
  stow-deployed live copy no longer diverges from its dotfiles source.
- Add `tests/test_output_rect.sh`.

### v1.3 (2026-07-08)
- Add primary-window activation: on Wayland, activate/raise a Vivaldi window on
  the configured primary monitor (via KWin) before forwarding a URL, working
  around a Vivaldi/Chromium bug that drops the open when its last-active window
  can't be client-activated. Configurable via `~/.config/browser-router/config`
  or `BROWSER_ROUTER_PRIMARY_OUTPUT`; best-effort with plain-hand-off fallback.

### v1.2 (2026-02-02)
- Add Slack (app.slack.com) - Electron app has same PipeWire camera issues

### v1.1 (2026-02-02)
- Add Office 365 domains: Outlook, SharePoint, OneDrive, office.com

### v1.0 (2026-02-02)
- Initial release
- Routes Teams URLs to Firefox, everything else to Vivaldi
- Install/uninstall scripts with mimeapps.list management
