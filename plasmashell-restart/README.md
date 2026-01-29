# Plasmashell Restart

A simple script to restart the KDE Plasma shell without logging out. This is useful when desktop widgets, panels, or the wallpaper get stuck or stop updating.

## Usage

Run the restart script:

```bash
./restart.sh
```

Or call it directly if you're in the directory.

## What it does

1.  Attempts to gracefully quit `plasmashell` using `kquitapp6` (or `kquitapp5`).
2.  Falls back to `killall plasmashell` if graceful exit fails.
3.  Waits a brief moment.
4.  Restarts `plasmashell` using `kstart`.

## Requirements

- KDE Plasma 5 or 6
- `kstart` (part of kde-cli-tools or similar package depending on distro)
