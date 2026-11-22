"""save() and restore() — the heart of herdr-resurrect.

save: snapshot every whitelisted, running foreground program across all sessions.
restore: relaunch each saved program into its matching idle pane (herdr has
already restored the layout), via `herdr pane run`.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from dataclasses import dataclass, field, replace
from typing import Callable

import config
import herdr_api
import pane_busy
import restart
import snapshot
import whitelist
from snapshot import PaneSnap

# After a full-server restart (reboot or `herdr server` restart) herdr restores
# the pane layout as bare shells; the programs that were running are gone until a
# restore relaunches them. A plain save() in that window would capture the empty
# state and clobber the snapshot that restore() depends on. These two guards
# decide when a now-idle pane's last-known program should be carried forward
# instead of dropped.
BOOT_GRACE_SEC = 1800          # within 30 min of boot, bare == "not yet restored"
RESTART_DROP_RATIO = 0.5       # >=50% of captured panes idling at once == restart
# After a restart-triggered restore, how long save() waits before re-scanning
# so the relaunched programs show up as pane foregrounds and get captured.
RESTART_SETTLE_SEC = 2.0


def _uptime_sec() -> float:
    """Seconds since system boot, or +inf if it can't be determined (so the
    boot-grace guard simply never triggers rather than misfiring)."""
    try:
        return time.clock_gettime(time.CLOCK_BOOTTIME)  # Linux
    except (AttributeError, OSError):
        pass
    if sys.platform == "darwin":
        boot = _darwin_boot_time()
        return time.time() - boot if boot is not None else float("inf")
    try:
        import ctypes  # Windows: kernel tick count (ms since boot)
        return ctypes.windll.kernel32.GetTickCount64() / 1000.0
    except (AttributeError, OSError):
        return float("inf")


def _darwin_boot_time() -> float | None:
    """Epoch seconds of the last boot from `sysctl kern.boottime`, which prints
    `{ sec = 1795147917, usec = 719635 } ...`. macOS has no CLOCK_BOOTTIME."""
    try:
        out = subprocess.run(["/usr/sbin/sysctl", "-n", "kern.boottime"],
                             capture_output=True, text=True, timeout=5,
                             check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"sec\s*=\s*(\d+)", out)
    return float(m.group(1)) if m else None


def _annotated_live_panes() -> tuple[list[dict], set[str]]:
    """All live panes across running sessions, each annotated with its session,
    workspace label, and current foreground program (`_fg` = (name, argv)|None).

    Also returns the set of sessions actually scanned. A session herdr has not
    started (its server is spawned lazily, when a terminal attaches it) or whose
    pane query failed contributes no panes, and the caller must not read that
    silence as "its panes were closed" -- see _merge_preserving."""
    panes: list[dict] = []
    scanned: set[str] = set()
    for sess in herdr_api.list_sessions():
        if not sess.running:
            continue
        try:
            labels = herdr_api.list_workspace_labels(sess.name)
            raw = herdr_api.list_panes(sess.name)
        except herdr_api.HerdrError:
            continue
        scanned.add(sess.name)
        for p in raw:
            p["_session"] = sess.name
            p["_workspace_label"] = labels.get(p.get("workspace_id", ""),
                                               p.get("workspace_id", ""))
            try:
                pinfo = herdr_api.pane_process_info(sess.name, p["pane_id"])
            except herdr_api.HerdrError:
                pinfo = {}
            p["_fg"] = whitelist.foreground_program(pinfo)
            p["_shell_pid"] = pinfo.get("shell_pid")
            panes.append(p)
    return panes, scanned


def _merge_preserving(new_snaps: list[PaneSnap], prev_snaps: list[PaneSnap],
                      live: list[dict], *, uptime_sec: float,
                      scanned_sessions: set[str] | None = None,
                      server_age_sec: dict[str, float] | None = None,
                      boot_grace_sec: float = BOOT_GRACE_SEC,
                      restart_drop_ratio: float = RESTART_DROP_RATIO,
                      ) -> list[PaneSnap]:
    """Carry forward the last-known program for panes that stopped running before
    a restart, so a full-server restart doesn't clobber the restore source with
    bare shells.

    A previously-captured entry that is absent now is preserved when the drop
    looks like a restart rather than a deliberate close: either we're within the
    post-boot grace window, or a large fraction of captured panes went away at
    once (the signature of a server restart). During steady state a one-off pane
    close falls through and is dropped normally, so intentionally-closed panels
    don't linger and get auto-relaunched.

    Crucially, the restart signal and the preservation are computed from *all*
    absent panes, not only those already re-materialized in the live layout.
    Right after a reboot herdr may fire the periodic save (OnBootSec=2min) before
    it has rebuilt the pane layout, so `live` can be empty even though every
    program needs carrying forward. Requiring the pane to already exist would
    drop everything and overwrite the snapshot restore() depends on — exactly the
    clobber this guard exists to prevent. An entry whose pane never comes back is
    harmless: restore() finds no idle pane to match and simply skips it, and once
    uptime clears the grace window a genuinely-removed pane is dropped on the next
    steady-state save.

    `scanned_sessions` names the sessions this cycle actually queried. Entries
    belonging to any other session are carried forward unconditionally, and are
    excluded from the restart ratio on both sides. herdr starts a named session's
    server only when a terminal attaches it, so an unattached session reports no
    panes all day; reading that silence as "closed" is what used to delete a whole
    session's programs from the snapshot once the boot grace expired, leaving both
    autorestore and `prefix+ctrl+r` with nothing to restore. Absence of evidence
    is not evidence of closure. Passing None keeps the old all-sessions-scanned
    behaviour.

    `server_age_sec` maps a session to seconds since its herdr server started.
    The grace window is measured from that, per session, because a server
    restart days after boot leaves the same bare shells a reboot does. A session
    missing from the map falls back to `uptime_sec`."""
    new_by_pane = {(s.session, s.pane_id) for s in new_snaps}
    absent = [s for s in prev_snaps
              if (s.session, s.pane_id) not in new_by_pane]
    if not absent:
        return new_snaps
    if scanned_sessions is None:
        unscanned, absent_scanned, considered_prev = [], absent, prev_snaps
    else:
        unscanned = [s for s in absent if s.session not in scanned_sessions]
        absent_scanned = [s for s in absent if s.session in scanned_sessions]
        considered_prev = [s for s in prev_snaps
                           if s.session in scanned_sessions]
    # An unscanned session told us nothing, so keep its entries verbatim: there
    # is no live pane to re-match them against either.
    preserved: list[PaneSnap] = list(unscanned)
    mass_drop = (len(considered_prev) > 0
                 and len(absent_scanned) / len(considered_prev) >= restart_drop_ratio)
    ages = server_age_sec or {}
    for s in absent_scanned:
        if not (mass_drop or ages.get(s.session, uptime_sec) < boot_grace_sec):
            continue
        pane = snapshot.match_live_pane(s, live)
        if pane is not None and pane.get("_fg") is not None:
            continue  # pane already runs a different program; don't shadow it
        if pane is not None:
            # Pane is back but idle: refresh layout coordinates in case herdr
            # reassigned ids across the restart (the program/argv is what matters).
            s = replace(s,
                        pane_id=pane.get("pane_id", s.pane_id),
                        tab_id=pane.get("tab_id", s.tab_id),
                        workspace_id=pane.get("workspace_id", s.workspace_id),
                        workspace_label=pane.get("_workspace_label", s.workspace_label))
        preserved.append(s)
    return new_snaps + preserved


def _quiet(_msg: str) -> None:
    pass


def _capture(live: list[dict], cfg: dict) -> list[PaneSnap]:
    """Snapshot entries for every whitelisted foreground program in `live`."""
    wl = whitelist.effective_whitelist(cfg)
    patterns = whitelist.cmdline_patterns(cfg)
    new_snaps: list[PaneSnap] = []
    for p in live:
        if whitelist.is_agent_pane(p.get("agent_status", "")):
            continue  # herdr's resume_agents_on_restore handles agent panes
        fg = p["_fg"]
        if fg is None:
            continue  # idle shell
        name, argv = fg
        if not whitelist.is_capturable(name, " ".join(argv), wl, patterns):
            continue
        new_snaps.append(PaneSnap(
            session=p["_session"],
            workspace_id=p.get("workspace_id", ""),
            workspace_label=p.get("_workspace_label", ""),
            tab_id=p.get("tab_id", ""),
            pane_id=p["pane_id"],
            cwd=p.get("foreground_cwd") or p.get("cwd", ""),
            name=name,
            argv=argv,
        ))
    return new_snaps


def _running_server_identities() -> dict[str, float]:
    """session -> start time of its running herdr server (see restart.py)."""
    identities: dict[str, float] = {}
    for sess in herdr_api.list_sessions():
        if not sess.running:
            continue
        ident = restart.server_identity(sess.socket_path)
        if ident is not None:
            identities[sess.name] = ident
    return identities


def _restore_restarted_session(name: str, snaps: list[PaneSnap],
                               live: list[dict], log: Callable[[str], None],
                               ) -> tuple[bool, bool]:
    """Handle one session whose server restarted. Returns (restored_any,
    settled); an unsettled session keeps its old record so the next save
    looks at it again."""
    session_snaps = [s for s in snaps if s.session == name]
    session_live = [p for p in live if p["_session"] == name]
    verdict = restart.restart_verdict(session_snaps, session_live,
                                      RESTART_DROP_RATIO)
    if verdict == restart.LAYOUT_PENDING:
        log(f"[restart] session {name!r}: new server, layout not rebuilt yet; "
            "will retry next save")
        return False, False
    if verdict == restart.NOT_CORROBORATED:
        log(f"[restart] session {name!r}: new server, programs still running "
            "or none saved; not restoring")
        return False, True
    log(f"[restart] session {name!r}: server restarted; restoring")
    r = restore(sessions={name})
    if r.lock_busy:
        log(f"[restart] session {name!r}: another restore is running; skipped")
    for snap, pid in r.restored:
        log(f"[restart] {name:8} {pid:8} {snap.cmdline}")
    for label, pid, cmd in r.labels_restored:
        log(f"[restart] {name:8} {pid:8} {label} -> {cmd}")
    return bool(r.restored or r.labels_restored), True


def _restore_restarted(identities: dict[str, float], snaps: list[PaneSnap],
                       live: list[dict], log: Callable[[str], None]) -> bool:
    """Restore every session whose herdr server started since the last save,
    and record the servers seen. Returns whether anything was relaunched."""
    recorded = restart.load_state()
    updated = dict(recorded)
    restored_any = False
    for name, ident in sorted(identities.items()):
        settled = True
        if restart.classify(recorded.get(name), ident) == restart.RESTARTED:
            restored, settled = _restore_restarted_session(name, snaps, live, log)
            restored_any = restored_any or restored
        if settled:
            updated[name] = ident
    if updated != recorded:
        restart.save_state(updated)
    return restored_any


def save(*, log: Callable[[str], None] = _quiet) -> list[PaneSnap]:
    """Snapshot running programs. First, restore any session whose herdr
    server restarted since the last save (spec 003): the periodic save is the
    one thing guaranteed to run after a restart that no hook announces."""
    cfg = config.load()
    live, scanned = _annotated_live_panes()
    identities = _running_server_identities()
    prev_snaps, _ = snapshot.load_snaps()
    if _restore_restarted(identities, prev_snaps, live, log):
        time.sleep(RESTART_SETTLE_SEC)
        live, scanned = _annotated_live_panes()
    now = time.time()
    snaps = _merge_preserving(
        _capture(live, cfg), prev_snaps, live,
        uptime_sec=_uptime_sec(), scanned_sessions=scanned,
        server_age_sec={n: now - t for n, t in identities.items()})
    snapshot.write_snapshot(snaps, history=int(cfg.get("history", 3)))
    return snaps


def match_label_command(label: str, label_commands: dict[str, str]) -> str | None:
    """Command configured for a pane label, or None. Matches the full label
    (`panel:yazi`) first, then the bare suffix after the last ':' (`yazi`), so
    config keys can be written either way."""
    if not label:
        return None
    if label in label_commands:
        return label_commands[label]
    return label_commands.get(label.rsplit(":", 1)[-1])


def _command_program(cmd: str) -> str:
    """Normalized image name of a command's leading executable token, e.g.
    'C:\\miniforge3\\python.exe -m src.main' -> 'python', 'yazi' -> 'yazi'."""
    parts = cmd.split()
    return whitelist.normalize_name(parts[0] if parts else cmd).lower()


def _label_pane_busy(pane: dict, cmd: str) -> bool:
    """Whether the pane already runs `cmd`'s program (so restore would duplicate
    it). Prefers the OS process table, which is authoritative even where herdr's
    Windows process-info can't see the program; matching the specific program
    name ignores transient prompt renderers (oh-my-posh/starship/git) that
    briefly appear as children of an idle shell. Falls back to herdr's foreground
    view where the OS check is unavailable (e.g. macOS)."""
    target = _command_program(cmd)
    names = pane_busy.shell_child_names(pane.get("_shell_pid"))
    if names is not None:
        return target in names
    fg = pane.get("_fg")
    if fg is None:
        return False
    return whitelist.normalize_name(fg[0]).lower() == target


@dataclass
class RestoreResult:
    restored: list[tuple[PaneSnap, str]] = field(default_factory=list)
    already: list[PaneSnap] = field(default_factory=list)
    busy: list[PaneSnap] = field(default_factory=list)
    unmatched: list[PaneSnap] = field(default_factory=list)
    # Label-driven restore (label, pane_id, command).
    labels_restored: list[tuple[str, str, str]] = field(default_factory=list)
    labels_already: list[tuple[str, str]] = field(default_factory=list)
    labels_failed: list[tuple[str, str]] = field(default_factory=list)
    dry_run: bool = False
    # Another restore held the lock throughout; this one did nothing.
    lock_busy: bool = False


def _restore_from_snapshot(snaps: list[PaneSnap], live: list[dict],
                           result: RestoreResult, *, dry_run: bool) -> None:
    for snap in snaps:
        pane = snapshot.match_live_pane(snap, live)
        if pane is None:
            result.unmatched.append(snap)
            continue
        fg = pane.get("_fg")
        if fg is not None:
            name, _ = fg
            (result.already if name == snap.name else result.busy).append(snap)
            continue
        # Idle pane -> relaunch.
        if not dry_run:
            try:
                herdr_api.pane_run(snap.session, pane["pane_id"], snap.cmdline)
            except herdr_api.HerdrError:
                result.busy.append(snap)
                continue
        result.restored.append((snap, pane["pane_id"]))


def _restore_from_labels(label_commands: dict[str, str], live: list[dict],
                         result: RestoreResult, *, dry_run: bool) -> None:
    for pane in live:
        if whitelist.is_agent_pane(pane.get("agent_status", "")):
            continue  # herdr's resume_agents_on_restore owns agent panes
        cmd = match_label_command(pane.get("label", ""), label_commands)
        if cmd is None:
            continue
        label = pane.get("label", "")
        if _label_pane_busy(pane, cmd):
            result.labels_already.append((label, cmd))
            continue
        if not dry_run:
            try:
                herdr_api.pane_run(pane["_session"], pane["pane_id"], cmd)
            except herdr_api.HerdrError:
                result.labels_failed.append((label, cmd))
                continue
        result.labels_restored.append((label, pane["pane_id"], cmd))


def restore(*, dry_run: bool = False,
            sessions: set[str] | None = None) -> RestoreResult:
    """Relaunch saved (and label-configured) programs into their idle panes.

    `sessions` limits the pass to the named herdr sessions; None means all of
    them. Scoping matters for autorestore, which restores each session once, as
    that session's server comes up -- they do not come up together.

    Runs under restart.restore_lock: the login autorestore, the keybind and a
    restart-triggered save can overlap, and two of them typing the same command
    into one idle pane would launch the program twice. A dry run needs no lock."""
    cfg = config.load()
    label_commands = cfg.get("label_commands", {}) or {}
    snaps, _saved_at = snapshot.load_snaps()
    result = RestoreResult(dry_run=dry_run)
    if sessions is not None:
        snaps = [s for s in snaps if s.session in sessions]
    if not snaps and not label_commands:
        return result
    if dry_run:
        _restore_pass(snaps, label_commands, sessions, result, dry_run=True)
        return result
    with restart.restore_lock() as held:
        if not held:
            result.lock_busy = True
            return result
        _restore_pass(snaps, label_commands, sessions, result, dry_run=False)
    return result


def _restore_pass(snaps: list[PaneSnap], label_commands: dict[str, str],
                  sessions: set[str] | None, result: RestoreResult, *,
                  dry_run: bool) -> None:
    live, _scanned = _annotated_live_panes()
    if sessions is not None:
        live = [p for p in live if p["_session"] in sessions]
    _restore_from_snapshot(snaps, live, result, dry_run=dry_run)
    if label_commands:
        _restore_from_labels(label_commands, live, result, dry_run=dry_run)
