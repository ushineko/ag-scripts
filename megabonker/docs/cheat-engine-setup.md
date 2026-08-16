# Running Cheat Engine against Megabonk

Megabonk ships a **native Linux build**, so there is no Wine prefix to attach a
Windows debugger to. Forcing Proton swaps in the Windows depot and gives you a
prefix that Cheat Engine can be installed into and share a process space with
the game — the same arrangement already used on this machine for Last Epoch,
DRG Survivor, Vampire Survivors and Brotato.

This is live memory editing, complementary to save editing: use megabonker for
persistent state (unlocks, currency, stats) and Cheat Engine for in-run values.

## Contents

- [What changes when you switch](#what-changes-when-you-switch)
- [Procedure](#procedure)
- [Where the scripts live](#where-the-scripts-live)
- [DPI settings](#dpi-settings)
- [Reverting to the native build](#reverting-to-the-native-build)

## What changes when you switch

| | Native Linux | Windows via Proton |
| :--- | :--- | :--- |
| Executable | `Megabonk.x86_64` | `Megabonk.exe` |
| Save root | `~/.config/unity3d/Ved/Megabonk/Saves` | `<prefix>/drive_c/users/steamuser/AppData/LocalLow/Ved/Megabonk/Saves` |
| Download | — | re-downloads the Windows depot (~550 MB) |
| Cheat Engine | not possible | attaches to `Megabonk.exe` |

The prefix for appid **3405340** lands under whichever library holds the game —
here `/mnt/Data3/SteamLibrary/steamapps/compatdata/3405340/pfx`.

**megabonker handles both roots automatically** (`savefile.save_roots()`), and
labels profiles with their origin when both exist, so a half-finished migration
stays legible.

## Procedure

### 1. Back up the saves first

Steam Cloud usually carries saves across a platform switch, because it maps
platform-specific paths to the same cloud slot. Usually is not always, and the
native saves are not deleted but also not migrated in place.

```bash
mkdir -p ~/.local/share/megabonker/backups
tar czf ~/.local/share/megabonker/backups/megabonk-saves-$(date +%Y%m%d-%H%M%S).tar.gz \
    -C ~/.config/unity3d/Ved Megabonk
```

### 2. Force Proton

Steam → **Megabonk** → Properties → Compatibility → *Force the use of a specific
Steam Play compatibility tool* → **proton_experimental**.

Steam will re-download the game as the Windows build.

### 3. Launch once

Start Megabonk and quit. This makes Proton build the prefix — the setup script
has nothing to install into until it exists, and will say so.

### 4. Install Cheat Engine into the prefix

```bash
ce-megabonk-setup.sh
```

Expects the installer at `~/Downloads/CheatEngine76.exe`. Click through it, and
**uncheck any bundled extras** the installer offers. The script then sets the
Wine DPI so the CE window is legible on a 4K display, and prints the values it
read back so a silent failure is visible.

The installer throws an unhandled Wine exception (`0x0eedfade`) as it exits,
*after* installing successfully. The script tolerates that and verifies by
checking for the binary — an earlier version aborted on it and skipped the DPI
step entirely.

Cheat Engine reads DPI at startup, so if it is already open, restart it.

### 5. Verify the saves came across

```bash
megabonker list
```

Both roots are reported. If only the native one has saves, Steam Cloud did not
migrate them — copy them in by hand:

```bash
PFX=/mnt/Data3/SteamLibrary/steamapps/compatdata/3405340/pfx
mkdir -p "$PFX/drive_c/users/steamuser/AppData/LocalLow/Ved/Megabonk"
cp -r ~/.config/unity3d/Ved/Megabonk/Saves \
      "$PFX/drive_c/users/steamuser/AppData/LocalLow/Ved/Megabonk/"
```

### 6. Use it

Launch Megabonk, then start Cheat Engine from the **Cheat Engine (Megabonk)**
menu entry (or `ce-megabonk.sh`) and attach to `Megabonk.exe`.

Note the game is Unity **IL2CPP**, not Mono — there is no Mono dissector to lean
on, so this is ordinary value scanning rather than field-name browsing.

## Where the scripts live

Kept with the other Cheat Engine launchers in dotfiles rather than in this repo,
so they stow onto a new machine with everything else:

```
~/git/dotfiles/hosts/njv-cachyos/
├── .local/bin/ce-megabonk-setup.sh          one-time prefix setup
├── .local/bin/ce-megabonk.sh                launcher
└── .local/share/applications/ce-megabonk.desktop
```

Symlinked into `~/.local/bin` and `~/.local/share/applications`, matching
`ce-drg.sh`. Siblings: `ce-drg.sh`, `ce-lastepoch.sh`, `ce-vs.sh`,
`ce-brotato.sh`.

## DPI settings

Cheat Engine's UI is not DPI-aware, so it renders unusably small on a 4K display
without help. The setup script writes `LogPixels` to **two** registry keys:

```
HKCU\Control Panel\Desktop     the Windows-standard location
HKCU\Software\Wine\Fonts        where Wine actually reads font scaling
```

Both are required. `winecfg` writes both, and setting only the Windows-standard
key leaves the UI at 100% — which looks exactly like the setting failing to
apply. This was found the hard way: the first version of the script wrote only
`Control Panel\Desktop` and Cheat Engine launched at original size.

| Value | Hex | Scale |
| ---: | :--- | :--- |
| 96 | `0x60` | 100% (Wine default) |
| 120 | `0x78` | 125% |
| 144 | `0x90` | 150% |
| 192 | `0xc0` | 200% |

As configured on this machine:

| Game | LogPixels | Scale |
| :--- | ---: | :--- |
| Last Epoch | 120 | 125% |
| Vampire Survivors | 144 | 150% |
| Brotato | 192 | 200% |
| DRG Survivor | 192 | 200% |
| **Megabonk** | **192** | **200%** |

Change `DPI_HEX` at the top of `ce-megabonk-setup.sh` and re-run it to adjust;
the step is idempotent and skips the installer if CE is already present.

## Reverting to the native build

Steam → Megabonk → Properties → Compatibility → untick the forced tool. Steam
re-downloads the Linux depot. The prefix and its Cheat Engine install are left
alone, so switching back later costs only the download.

Saves written while on Windows stay in the prefix. `megabonker list` will show
both roots; copy across in whichever direction you need.
