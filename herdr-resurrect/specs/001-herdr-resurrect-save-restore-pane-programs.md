# Spec 001: herdr-resurrect — save/restore the programs running in herdr panes

> **Note**: This work has no associated issue tracker ticket. Consider creating
> one for traceability.

**Status: COMPLETE**

## Context

herdr persists the pane **layout** across a server restart / reboot (workspaces,
tabs, panes, splits, cwd — in `~/.config/herdr/session.json`), but it relaunches
each pane as a **fresh shell**. The programs that were running (`btop`, `lazygit`,
`yazi`, `nvim`, dev servers, …) are gone, so after every reboot the user rebuilds
their working environment by hand. herdr's `resume_agents_on_restore` covers
**AI-agent** panes only; everything else is unhandled.

herdr exposes the socket primitives to close this gap — `pane process-info`
reports each pane's foreground `argv`, and `pane run` injects a command into an
existing pane — so a tmux-resurrect-style save/restore is buildable on top of it.

## Goals

- **save**: snapshot what is running in every pane (across all herdr sessions) to
  a file, on demand and periodically.
- **restore**: after a reboot (once herdr has restored the layout), relaunch the
  saved programs back into their panes — on demand.
- Match the `ag-scripts` house style (tool dir, `install.sh`, CLI, config in
  `~/.config/herdr-resurrect/`).

## Non-goals (this spec)

- **Rebuilding layout.** herdr already restores workspaces/tabs/panes/cwd; this
  tool relaunches *programs into the existing panes*, it does not recreate the
  pane tree. (If a snapshot pane has no matching live pane, it is reported and
  skipped, not recreated. Full-rebuild could be a later spec.)
- **Auto-restore on boot.** v1 restore is manual (CLI / keybind). Auto-restore on
  first post-boot attach is a planned follow-up once the manual path is proven.
- **Restoring program internal state.** Only the command line is re-run (like
  tmux-resurrect); scrollback is covered separately by herdr's `pane_history`.
- **AI-agent panes.** Handled by herdr's `resume_agents_on_restore`; resurrect
  skips panes whose `agent_status` marks them as agents.

## Empirical findings (2026-06-29, herdr on njv-cachyos)

| # | Finding | Detail |
|---|---------|--------|
| 1 | Panes are enumerable with identity + cwd | `herdr pane list` → `panes[]` with `pane_id` (`w2:p1`), `workspace_id`, `tab_id`, `cwd`, `foreground_cwd`, `agent_status`. |
| 2 | Foreground program is reportable | `herdr pane process-info --pane <id>` → `foreground_processes[].argv` / `cmdline` / `name`, plus `shell_pid`. e.g. `["btop","-u","500"]`. |
| 3 | Commands can be injected into a live pane | `herdr pane run <pane_id> <command>` types the command + Enter into the pane's shell. |
| 4 | Layout already persists | `session.json` stores `workspaces`/`panes`/`layout`/`cwd`; herdr restores it on restart (logs `persist.save … workspaces=5`). |
| 5 | Sessions enumerable | `herdr session list --json`; per-session panes via `herdr --session <s> pane list`. |
| 6 | Idle vs busy detectable | A pane whose only foreground process is the shell (`name` == the shell, pid == `shell_pid`) is idle and safe to inject into. |

## Requirements

1. **Snapshot (save).** Enumerate all running sessions → panes; for each pane with
   a whitelisted foreground program, record
   `{session, workspace_id, workspace_label, tab_id, pane_id, cwd, argv, name}`.
   Write atomically to `~/.config/herdr-resurrect/snapshot.json` (keep the last
   snapshot; optionally a short rotation history).
2. **Whitelist.** Only capture/relaunch programs known to be safe to re-run.
   Ship a sensible default set (`btop`, `htop`, `glances`, `lazygit`, `gitui`,
   `yazi`, `ranger`, `nvim`, `vim`, `k9s`, `watch`, `tail`, `less`, `glow`, …),
   extensible/overridable via config. Never capture bare shells, `ssh`, or
   interactive REPLs (`python`, `node`, `psql`).
3. **Restore.** For each snapshot entry, find the matching live pane (by `pane_id`;
   fallback by `session` + `workspace_label` + `cwd`). If that pane is currently an
   **idle shell**, `herdr pane run <pane_id> "<cmdline>"`. Skip panes that are
   missing, already running the target program, or non-idle. Report a summary
   (restored / skipped / unmatched).
4. **Periodic auto-save.** A systemd user timer runs `save` every ~5 min so an
   unplanned reboot still has a recent snapshot. Interval configurable; the timer
   is installed/enabled by `install.sh`.
5. **Manual triggers.** CLI: `herdr-resurrect save | restore | status | list`.
   `status` shows the last snapshot's age and contents; `restore` supports
   `--dry-run`. A herdr keybind can call `save`/`restore`.
6. **All sessions.** Save and restore span every running session, not just the
   attached one.
7. **Install/uninstall.** House pattern: `~/.local/bin` symlinks, systemd user
   timer+service, config dir. `uninstall.sh` reverses it (disables the timer).
8. **Config.** `~/.config/herdr-resurrect/config.json`: whitelist additions/removals,
   save interval, snapshot history depth.

## Design / Architecture

One module per concern (mirrors herdr-switcher):

- `herdr_api.py` — socket wrapper: `list_sessions`, `list_panes(session)`,
  `pane_process_info(session, pane_id)`, `pane_run(session, pane_id, cmd)`,
  `list_workspaces(session)` (for labels). Typed records.
- `snapshot.py` — `Pane` record, capture (save) + matching/whitelist logic.
- `resurrect.py` — `save()` and `restore(dry_run)` orchestration.
- `whitelist.py` — default set + config merge + classification (idle/agent/ssh).
- `config.py` — config + paths.
- `cli.py` — `save | restore [--dry-run] | status | list`.

`Pane` snapshot record:
```
@dataclass
class PaneSnap:
    session: str
    workspace_id: str
    workspace_label: str
    tab_id: str
    pane_id: str
    cwd: str
    name: str          # program name, e.g. "btop"
    argv: list[str]    # full argv, e.g. ["btop","-u","500"]
```

`save`: `list_sessions` → per session `list_panes` + `list_workspaces` (labels) →
`pane_process_info` per pane → keep whitelisted, non-idle, non-agent → write JSON.

`restore`: load snapshot → for each entry, resolve the live pane → if idle shell →
`pane_run`. Match by `pane_id` first; if absent (ids changed across reboot), match
by `(session, workspace_label, cwd)`, preferring an idle pane.

## Acceptance Criteria

- [x] `save` snapshots every running session's panes, recording `argv` + `cwd` +
      identity for whitelisted foreground programs, skipping shells/agents/ssh —
      verified against live herdr. *(Captured 16 programs across both sessions;
      correctly skipped `claude` agent panes, idle shells, and non-whitelisted.)*
- [x] The snapshot is valid JSON written atomically; `status` reports its age and
      a readable summary.
- [x] `restore --dry-run` lists, for the current live panes, exactly which would be
      relaunched, which are skipped (non-idle / already running), and which are
      unmatched — without running anything. *(Dry-run showed 0 restore / 15
      already-running.)*
- [x] `restore` relaunches a saved program into an **idle** matching pane via
      `herdr pane run`, and the program is then reported as that pane's foreground
      process — exercised end to end against real herdr (integration boundary), not
      mocked. *(Controlled test: start btop in an idle pane → save → kill it → idle
      → restore → btop running again.)*
- [x] Restore does **not** double-launch into a pane already running the target
      program, and does not touch non-idle panes. *(15 already-running skipped.)*
- [x] Whitelist is honored and user-extensible via config (add/remove entries).
      *(`nvtop` added to defaults and then captured; `effective_whitelist` unit-tested.)*
- [x] A systemd user timer runs `save` on the configured interval; `install.sh`
      installs + enables it and the CLI symlinks; `uninstall.sh` reverses it.
      *(Timer active; the service ran `save` (exit 0) producing a fresh snapshot.
      `uninstall.sh` implemented + code-reviewed; not executed to keep the install.)*

## Risks & Assumptions

- **pane_id stability across reboot** — if herdr preserves `pane_id` in
  `session.json`, restore matches directly. If ids are reassigned on restore, the
  `(session, workspace_label, cwd)` fallback matcher is used. This is the load-
  bearing assumption and can only be fully confirmed after a real reboot; the
  fallback makes restore robust either way. Mitigation: log unmatched entries.
- **Idle-shell detection** — relies on `foreground_processes` being just the shell
  (pid == `shell_pid`). A pane left at a shell prompt is "idle"; a pane mid-command
  is skipped to avoid clobbering input.
- **Command re-run safety** — only whitelisted programs are relaunched; the default
  list excludes anything stateful/destructive. `pane run` types into the shell, so
  a non-idle pane could receive stray input — guarded by the idle check.
- **Argument fidelity** — `argv` is captured verbatim; programs that embedded an
  absolute path or a transient flag will re-run with the same. Acceptable.
- **Reversibility** — pure userspace; rollback = `uninstall.sh` (removes symlinks,
  disables/removes the timer). Snapshots are data files under `~/.config`.
- **Races with periodic save** — atomic write (tmp + rename); restore reads a
  consistent file.

## Alternatives Considered

- **Full layout rebuild from snapshot** (recreate workspaces/tabs/panes/splits via
  `workspace create` + `pane split`, then launch). Rejected for v1: herdr already
  restores layout reliably; rebuilding would duplicate panes and must capture/replay
  the split tree. Kept as a possible later mode for "restore on a fresh machine".
- **`agent start` (new pane per program)** instead of `pane run` into existing
  panes. Rejected: would create extra panes alongside herdr's restored ones.
- **Hooking herdr's own restart** for auto-restore. Deferred to a follow-up; v1 is
  manual to keep timing/double-launch behavior predictable.

## Open Questions

- Snapshot history depth (just last, or keep N for "restore an earlier layout")?
  Default: keep last + a small rotation.
- Should `restore` optionally target a single session/workspace? (v1: all; a
  `--session`/`--workspace` filter is a cheap add.)

## Executive Summary

Adds `herdr-resurrect`, a tmux-resurrect-style
save/restore for the programs running in herdr panes. `save` (manual + a ~5-min
systemd timer) snapshots each pane's `argv`/`cwd`; `restore` relaunches whitelisted
programs into the panes herdr already brought back after a reboot, via
`herdr pane run`. KDE/Wayland-agnostic (pure herdr socket API); complements herdr's
`resume_agents_on_restore` (which covers AI-agent panes).
