# Browser Router

Routes URLs to different browsers based on domain patterns. Created to work around Chromium/Vivaldi lacking PipeWire camera support on Wayland.

**Version:** 1.1

## Table of Contents

- [Problem](#problem)
- [Solution](#solution)
- [Installation](#installation)
- [Uninstallation](#uninstallation)
- [Configuration](#configuration)
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

Everything else goes to Vivaldi.

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

### v1.1 (2026-02-02)
- Add Office 365 domains: Outlook, SharePoint, OneDrive, office.com

### v1.0 (2026-02-02)
- Initial release
- Routes Teams URLs to Firefox, everything else to Vivaldi
- Install/uninstall scripts with mimeapps.list management
