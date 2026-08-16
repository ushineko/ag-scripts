# Megabonker

PyQt6 save editor for **Megabonk** (Steam appid 3405340), plus a toolkit for
recovering the game's save-encryption key when a game update rotates it.

Megabonk stores `progression.json` and `stats.json` as
`base64(AES-256-CBC(PKCS7(JSON)))` using a key and IV compiled into the game
binary. Megabonker decrypts them into an editable tree, writes them back in the
exact format the game reads, and can re-derive the key from the game's own files
if it ever changes — so the tool does not go stale after a patch.

*Your saves are yours; this edits them in place with a backup on every write.*

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
  - [GUI](#gui)
  - [Command line](#command-line)
- [Save file locations](#save-file-locations)
- [Key recovery](#key-recovery)
- [Safety](#safety)
- [Project layout](#project-layout)
- [Testing](#testing)
- [Notes](#notes)

## Features

- **Tree editor** for every save file, with type-preserving edits — a field the
  game wrote as an int stays an int, and invalid input is rejected rather than
  silently stringified.
- **Filter box** to find a key or value in `stats.json` without scrolling.
- **Round-trip verification** before any file is opened for editing: if
  re-encrypting the untouched contents does not reproduce the original bytes,
  the file is refused instead of risking corruption.
- **Automatic backups** — every write leaves a timestamped `.bak` beside the save.
- **Key recovery** built in: if a game update changes the key, Tools → Recover
  Save Key searches the installed game and finds it, typically in under a second.
- **Recovered keys persist** to a keyring, so recovery happens once per build.
- **Running-game detection** — warns before writing underneath a live Megabonk,
  which would otherwise discard the edits on exit.
- **Scriptable CLI** for decrypting saves to plain JSON, diffing them, and
  re-encrypting.
- Handles the plain-JSON `LocalDir/config.json` alongside the encrypted files.

## Requirements

- Python 3.12+ (system Python; this project follows the ag-scripts rule of using
  `/usr/bin/python3`, not conda)
- PyQt6
- `cryptography`
- `numpy`

On CachyOS / Arch these are `python-pyqt6`, `python-cryptography` and
`python-numpy`. All three are usually already present on a KDE system.

## Installation

```bash
cd ~/git/ag-scripts/megabonker
./install.sh
```

This installs a `.desktop` entry into `~/.local/share/applications` and a
`megabonker` symlink into `~/.local/bin`. Nothing is copied — the entry points at
this checkout, so `git pull` updates the installed app.

Remove with `./uninstall.sh`.

Running from the checkout without installing works too:

```bash
./megabonker.py
```

## Usage

### GUI

```bash
megabonker                    # or: ./megabonker.py
megabonker gui --profile DIR  # open a specific profile
```

Pick a profile at the top (there is normally one, named after your SteamID64).
Each save file becomes a tab. Edit values in the **Value** column; changed tabs
are marked with `*`. **Save Changes** writes every modified file and takes a
backup of each.

| Menu item | Purpose |
| :--- | :--- |
| File → Reload (`Ctrl+R`) | Re-read from disk, discarding edits |
| File → Save Changes (`Ctrl+S`) | Write modified files, with backups |
| Tools → Recover Save Key | Search the game for the key/IV (see below) |
| Tools → Open Save Folder | Open the profile directory in the file manager |

### Command line

```bash
megabonker list                            # profiles, files, and key status
megabonker decrypt progression.json        # plain JSON to stdout
megabonker decrypt progression.json -o out.json
megabonker encrypt out.json -o progression.json
megabonker derive-key --save               # recover the key and keep it
```

`decrypt` writes JSON to stdout and diagnostics to stderr, so it pipes cleanly:

```bash
megabonker decrypt progression.json | jq .characterProgression
```

Editing round-trip from the shell:

```bash
megabonker decrypt "$SAVE/progression.json" -o /tmp/p.json
$EDITOR /tmp/p.json
megabonker encrypt /tmp/p.json -o "$SAVE/progression.json"
```

## Save file locations

```
~/.config/unity3d/Ved/Megabonk/Saves/
├── CloudDir/<steamid64>/
│   ├── progression.json        encrypted · gold, unlocks, per-character XP
│   ├── stats.json              encrypted · run and lifetime stats
│   └── controller_config.json  plain · Rewired bindings
└── LocalDir/
    └── config.json             plain · video/audio/gameplay settings
```

The game ships as a native Linux build, so there is no Proton prefix — these are
real paths, not something under `steamapps/compatdata`.

`CloudDir` is Steam Cloud synced. Edit with Steam closed where possible;
otherwise Steam may resolve a conflict in favour of the cloud copy and revert
your changes.

## Key recovery

The key and IV are constants compiled into the game, so a game update can
change them. When that happens saves stop opening and every known key fails.

```bash
megabonker derive-key --save
```

or Tools → Recover Save Key in the GUI. The search needs the game installed and
at least one encrypted save; it works blind, without a debugger or a running
game, and normally completes in under a second.

**[docs/key-recovery.md](docs/key-recovery.md)** documents the format, the
search method, and a full by-hand procedure for the case where the automated
search fails — including what to do if the encryption scheme itself changes.

## Safety

- Every write is preceded by a timestamped backup:
  `progression.json.megabonker-20260815-211500.bak`.
- Writes go to a temp file and are then renamed, so an interrupted write cannot
  truncate a save.
- A file that does not survive a byte-exact encrypt/decrypt round-trip is
  refused rather than edited.
- Megabonk reports to leaderboards. Edited progression may end up there; keep
  modified saves off them if that matters to you.

## Project layout

```
megabonker/
├── megabonker.py            thin entry point
├── megabonker/
│   ├── cli.py               argparse front end
│   ├── config.py            preferences in ~/.config/megabonker/
│   ├── crypto.py            AES-256-CBC encrypt/decrypt + round-trip check
│   ├── keys.py              known keys and the user keyring
│   ├── derive.py            blind key/IV recovery from the game files
│   ├── savefile.py          discovery, loading, backups, atomic writes
│   └── gui/
│       ├── main_window.py   profile picker and tabs
│       ├── json_editor.py   editable JSON tree
│       └── derive_dialog.py threaded key recovery
├── docs/key-recovery.md     format and recovery methodology
├── specs/                   feature specs
└── tests/                   unittest suite
```

## Testing

```bash
QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m pytest tests/ -q
```

GUI tests run offscreen so the suite works headless. Tests that need the game or
an installed save skip cleanly when either is absent, and no test ever writes to
a real save — file tests operate on copies in a temp directory.

## Notes

- The IV is a fixed constant rather than random per file, which makes encryption
  deterministic. Megabonker leans on this to verify round-trips, but it is a
  genuine weakness in the game's save protection.
- The encryption is obfuscation, not security: the key must be present on the
  machine for the game to read its own saves.
- Verified against the Feb-2026 Linux build. Other platforms use the same Unity
  save layout under a different root, but only Linux has been tested.
