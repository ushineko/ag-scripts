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
- **restore** — after a reboot, once herdr has restored the layout, matches each
  saved program to its live pane (by `pane_id`, falling back to
  session+workspace+cwd) and, if that pane is an **idle shell**, relaunches the
  program with `herdr pane run`. Never double-launches; never touches a busy pane.

## Install

```sh
./install.sh      # symlink CLI + enable the periodic-save systemd user timer
./uninstall.sh    # remove (add --purge to also delete config + snapshots)
```

Requires `python3` and `herdr`. (Periodic auto-save is Linux/systemd; the CLI
itself is cross-platform.)

## Usage

```sh
herdr-resurrect save               # snapshot now (all sessions)
herdr-resurrect restore --dry-run  # preview what would relaunch
herdr-resurrect restore            # relaunch into idle panes (run after a reboot)
herdr-resurrect status             # last snapshot age + program count
herdr-resurrect list               # what the snapshot holds
```

Bind `save`/`restore` to a herdr key via `config.toml` if you like:
```toml
[[keys.command]]
key = "prefix+R"
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
| `resurrect.py` | `save()` / `restore()` orchestration |
| `config.py` | config + paths |
| `cli.py` | `save` / `restore` / `status` / `list` |

## Caveats

- **pane_id stability** — restore matches on `pane_id` first; if herdr reassigns
  ids across a restart, it falls back to session+workspace-label+cwd. Unmatched
  entries are reported, not lost.
- Only the **command line** is restored (like tmux-resurrect), not a program's
  internal state. Scrollback is herdr's `pane_history`.
- A pane must be an **idle shell** to receive its program — a pane you've already
  put to other use is left alone.
