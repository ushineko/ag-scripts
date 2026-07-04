"""save() and restore() — the heart of herdr-resurrect.

save: snapshot every whitelisted, running foreground program across all sessions.
restore: relaunch each saved program into its matching idle pane (herdr has
already restored the layout), via `herdr pane run`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace

import config
import herdr_api
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


def _uptime_sec() -> float:
    """Seconds since system boot, or +inf if it can't be determined (so the
    boot-grace guard simply never triggers rather than misfiring)."""
    try:
        return time.clock_gettime(time.CLOCK_BOOTTIME)
    except (AttributeError, OSError):
        return float("inf")


def _annotated_live_panes() -> list[dict]:
    """All live panes across running sessions, each annotated with its session,
    workspace label, and current foreground program (`_fg` = (name, argv)|None)."""
    panes: list[dict] = []
    for sess in herdr_api.list_sessions():
        if not sess.running:
            continue
        try:
            labels = herdr_api.list_workspace_labels(sess.name)
            raw = herdr_api.list_panes(sess.name)
        except herdr_api.HerdrError:
            continue
        for p in raw:
            p["_session"] = sess.name
            p["_workspace_label"] = labels.get(p.get("workspace_id", ""),
                                               p.get("workspace_id", ""))
            try:
                pinfo = herdr_api.pane_process_info(sess.name, p["pane_id"])
            except herdr_api.HerdrError:
                pinfo = {}
            p["_fg"] = whitelist.foreground_program(pinfo)
            panes.append(p)
    return panes


def _merge_preserving(new_snaps: list[PaneSnap], prev_snaps: list[PaneSnap],
                      live: list[dict], *, uptime_sec: float,
                      boot_grace_sec: float = BOOT_GRACE_SEC,
                      restart_drop_ratio: float = RESTART_DROP_RATIO,
                      ) -> list[PaneSnap]:
    """Carry forward the last-known program for panes that are currently idle but
    were running before a restart, so a full-server restart doesn't clobber the
    restore source with bare shells.

    A previously-captured entry that is absent now is preserved only when its
    pane still exists in the layout AND is idle (its program vanished, the pane
    didn't), AND the drop looks like a restart rather than a deliberate close:
    either we're within the post-boot grace window, or a large fraction of
    captured panes went idle at once (the signature of a server restart). During
    steady state a one-off pane close falls through and is dropped normally, so
    intentionally-closed panels don't linger and get auto-relaunched."""
    new_by_pane = {(s.session, s.pane_id) for s in new_snaps}
    recoverable: list[tuple[PaneSnap, dict]] = []
    for s in prev_snaps:
        if (s.session, s.pane_id) in new_by_pane:
            continue  # still captured this cycle (running); nothing to preserve
        pane = snapshot.match_live_pane(s, live)
        if pane is not None and pane.get("_fg") is None:
            recoverable.append((s, pane))
    if not recoverable:
        return new_snaps
    mass_drop = (len(prev_snaps) > 0
                 and len(recoverable) / len(prev_snaps) >= restart_drop_ratio)
    if not (mass_drop or uptime_sec < boot_grace_sec):
        return new_snaps
    # Preserve, refreshing layout coordinates from the live pane in case herdr
    # reassigned ids across the restart (the program/argv is what matters).
    preserved = [
        replace(s,
                pane_id=pane.get("pane_id", s.pane_id),
                tab_id=pane.get("tab_id", s.tab_id),
                workspace_id=pane.get("workspace_id", s.workspace_id),
                workspace_label=pane.get("_workspace_label", s.workspace_label))
        for s, pane in recoverable
    ]
    return new_snaps + preserved


def save() -> list[PaneSnap]:
    cfg = config.load()
    wl = whitelist.effective_whitelist(cfg)
    patterns = whitelist.cmdline_patterns(cfg)
    live = _annotated_live_panes()
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
    prev_snaps, _ = snapshot.load_snaps()
    snaps = _merge_preserving(new_snaps, prev_snaps, live,
                              uptime_sec=_uptime_sec())
    snapshot.write_snapshot(snaps, history=int(cfg.get("history", 3)))
    return snaps


@dataclass
class RestoreResult:
    restored: list[tuple[PaneSnap, str]] = field(default_factory=list)
    already: list[PaneSnap] = field(default_factory=list)
    busy: list[PaneSnap] = field(default_factory=list)
    unmatched: list[PaneSnap] = field(default_factory=list)
    dry_run: bool = False


def restore(*, dry_run: bool = False) -> RestoreResult:
    snaps, _saved_at = snapshot.load_snaps()
    result = RestoreResult(dry_run=dry_run)
    if not snaps:
        return result
    live = _annotated_live_panes()
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
    return result
