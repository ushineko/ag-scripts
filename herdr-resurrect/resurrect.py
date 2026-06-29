"""save() and restore() — the heart of herdr-resurrect.

save: snapshot every whitelisted, running foreground program across all sessions.
restore: relaunch each saved program into its matching idle pane (herdr has
already restored the layout), via `herdr pane run`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import config
import herdr_api
import snapshot
import whitelist
from snapshot import PaneSnap


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


def save() -> list[PaneSnap]:
    cfg = config.load()
    wl = whitelist.effective_whitelist(cfg)
    snaps: list[PaneSnap] = []
    for p in _annotated_live_panes():
        if whitelist.is_agent_pane(p.get("agent_status", "")):
            continue  # herdr's resume_agents_on_restore handles agent panes
        fg = p["_fg"]
        if fg is None:
            continue  # idle shell
        name, argv = fg
        if name not in wl:
            continue
        snaps.append(PaneSnap(
            session=p["_session"],
            workspace_id=p.get("workspace_id", ""),
            workspace_label=p.get("_workspace_label", ""),
            tab_id=p.get("tab_id", ""),
            pane_id=p["pane_id"],
            cwd=p.get("foreground_cwd") or p.get("cwd", ""),
            name=name,
            argv=argv,
        ))
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
