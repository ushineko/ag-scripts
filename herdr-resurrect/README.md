# herdr-resurrect

Save and restore the **programs running in your herdr panes** — tmux-resurrect for
[herdr](https://herdr.dev).

herdr already restores the pane *layout* (workspaces/tabs/panes/cwd) across a
reboot, but relaunches each pane as a fresh shell, so `btop`/`lazygit`/`yazi`/your
editor are gone. herdr-resurrect snapshots what's running and relaunches it back
into those panes.

> Pure herdr socket API — no compositor/display dependency. Complements herdr's
> own `resume_agents_on_restore` (which covers AI-agent panes; this covers the
> rest). See `specs/001-herdr-resurrect-save-restore-pane-programs.md`.

## How it works

- **save** — walks every running session's panes, reads each pane's foreground
  `argv` + `cwd` (`herdr pane process-info`), keeps the **whitelisted** programs,
  and writes `~/.config/herdr-resurrect/snapshot.json`. Skips idle shells, AI-agent
  panes, and anything not whitelisted. Runs on demand and every ~5 min (systemd
  user timer).
  - **Clobber guard** — a save right after a restart would otherwise capture the
    bare shells and overwrite the snapshot restore depends on. So when a pane
    goes idle because its program vanished (pane still present, program gone) and
    that looks like a restart — within 30 min of boot, or a large fraction of
    captured panes idling at once — save **carries the last-known program
    forward** instead of dropping it. A one-off pane close during steady state is
    dropped normally, so intentionally-closed panels don't get relaunched.
- **restore** — after a reboot, once herdr has restored the layout, matches each
  saved program to its live pane (by `pane_id`, falling back to
  session+workspace+cwd) and, if that pane is an **idle shell**, relaunches the
  program with `herdr pane run`. Never double-launches; never touches a busy pane.
- **autorestore** — what the login timer runs. herdr has no post-restore hook and
  each session's server is spawned lazily, so this polls for herdr readiness and
  retries `restore` across a window (default 15 min), covering sessions attached
  later. Idempotent — repeated passes no-op once programs are back.

## Install

```sh
./install.sh      # symlink CLI + enable the save + auto-restore systemd timers
./uninstall.sh    # remove (add --purge to also delete config + snapshots)
```

Two systemd user timers: `herdr-resurrect-save.timer` (snapshot every N min) and
`herdr-resurrect-autorestore.timer` (restore ~30s after login). After a reboot
your pane programs come back automatically — no keypress.

Requires `python3` and `herdr`. (Periodic auto-save is Linux/systemd; the CLI
itself is cross-platform.)

### Windows

```powershell
.\install.ps1      # launcher + two scheduled tasks + pwsh-profile one-shot
.\uninstall.ps1    # remove (add -Purge to also delete config + snapshots)
```

`install.ps1` is the Windows analogue of `install.sh` (no systemd). It writes a
`%USERPROFILE%\bin\herdr-resurrect.cmd` launcher, registers two per-user
scheduled tasks — `herdr-resurrect-save` (snapshot every N min) and
`herdr-resurrect-autorestore` (at logon, poll for herdr then restore) — and adds
a one-shot restore trigger to the pwsh profile that fires the first time a herdr
server starts (covers herdr launched long after logon; see
`herdr-resurrect-autostart.ps1`). Program names are matched with the `.exe`
suffix stripped (`nvim.exe` → `nvim`) so the whitelist applies on Windows.

> **Capture depends on herdr's Windows `pane process-info` reporting the pane's
> foreground program.** As of herdr 0.7.1-preview this was observed to surface a
> human-launched program (an agent pane) but **not** programs injected via the
> `pane run` socket API in testing — verify on your build by hand-launching a
> whitelisted TUI (`yazi`/`lazygit`) in a normal pane, then `herdr-resurrect
> list`. If nothing is captured, herdr is not yet exposing non-agent pane
> programs on Windows and this tool has nothing to snapshot.

## Usage

```sh
herdr-resurrect save               # snapshot now (all sessions)
herdr-resurrect restore --dry-run  # preview what would relaunch
herdr-resurrect restore            # relaunch into idle panes (auto-run after login)
herdr-resurrect autorestore        # poll-then-restore (what the login timer runs)
herdr-resurrect status             # last snapshot age + program count
herdr-resurrect list               # what the snapshot holds
```

The login timer restores automatically; bind a manual `restore` to a herdr key
via `config.toml` for on-demand use. Pick a **free** chord — herdr already uses
`prefix+r` (resize) and `prefix+R` (reload-config), so use e.g. `prefix+ctrl+r`:
```toml
[[keys.command]]
key = "prefix+ctrl+r"
type = "shell"
command = "herdr-resurrect restore"
```

## Configuration

`~/.config/herdr-resurrect/config.json`:

| Key | Default | Meaning |
|-----|---------|---------|
| `save_interval_min` | `5` | Periodic-save cadence (timer; re-run install.sh to apply) |
| `whitelist_add` | `[]` | Extra program names to capture/restore |
| `whitelist_remove` | `[]` | Default-whitelist names to drop |
| `cmdline_patterns` | `[]` | Regexes on the full command line — capture by command, not name (e.g. `"-m src\\.main --tui"` to catch a `python3 -m …` TUI) |
| `history` | `3` | Snapshots kept under `history/` |

Default whitelist: system monitors (`btop`, `htop`, `nvtop`, `glances`, …), git
TUIs (`lazygit`, `gitui`, `tig`), file managers (`yazi`, `ranger`, `nnn`),
editors (`nvim`, `vim`, `helix`), `k9s`, `watch`, `tail`, `glow`, … Bare shells,
`ssh`, and REPLs are never captured.

## Architecture

| Module | Role |
|--------|------|
| `herdr_api.py` | herdr socket wrapper (sessions, panes, process-info, pane run) |
| `whitelist.py` | foreground-program extraction, idle/agent classification, whitelist |
| `snapshot.py` | `PaneSnap` model, atomic write + history, live-pane matching |
| `resurrect.py` | `save()` (with clobber guard) / `restore()` orchestration |
| `config.py` | config + paths |
| `cli.py` | `save` / `restore` / `autorestore` / `status` / `list` |

## Caveats

- **pane_id stability** — restore matches on `pane_id` first; if herdr reassigns
  ids across a restart, it falls back to session+workspace-label+cwd. Unmatched
  entries are reported, not lost.
- Only the **command line** is restored (like tmux-resurrect), not a program's
  internal state. Scrollback is herdr's `pane_history`.
- A pane must be an **idle shell** to receive its program — a pane you've already
  put to other use is left alone.
