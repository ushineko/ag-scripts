"""Snapshot data model + persistence + live-pane matching."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass

from config import HISTORY_DIR, SNAPSHOT_PATH, ensure_dir


@dataclass
class PaneSnap:
    session: str
    workspace_id: str
    workspace_label: str
    tab_id: str
    pane_id: str
    cwd: str
    name: str           # program name, e.g. "btop"
    argv: list[str]     # full argv, e.g. ["btop", "-u", "500"]

    @property
    def cmdline(self) -> str:
        # Quote args containing whitespace so `pane run` re-runs them intact.
        parts = []
        for a in self.argv:
            parts.append(f'"{a}"' if (" " in a or "\t" in a) else a)
        return " ".join(parts) if parts else self.name


def write_snapshot(snaps: list[PaneSnap], *, timestamp: float | None = None,
                   history: int = 3) -> None:
    ensure_dir()
    payload = {
        "version": 1,
        "saved_at": timestamp if timestamp is not None else time.time(),
        "panes": [asdict(s) for s in snaps],
    }
    tmp = SNAPSHOT_PATH + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(payload, fh, indent=2)
    os.replace(tmp, SNAPSHOT_PATH)
    _rotate_history(payload, history)


def _rotate_history(payload: dict, keep: int) -> None:
    if keep <= 0:
        return
    os.makedirs(HISTORY_DIR, exist_ok=True)
    stamp = int(payload["saved_at"])
    path = os.path.join(HISTORY_DIR, f"snapshot-{stamp}.json")
    try:
        with open(path, "w") as fh:
            json.dump(payload, fh, indent=2)
    except OSError:
        return
    files = sorted(
        (f for f in os.listdir(HISTORY_DIR) if f.startswith("snapshot-")),
        reverse=True,
    )
    for stale in files[keep:]:
        try:
            os.unlink(os.path.join(HISTORY_DIR, stale))
        except OSError:
            pass


def read_snapshot() -> dict | None:
    try:
        with open(SNAPSHOT_PATH) as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def load_snaps() -> tuple[list[PaneSnap], float | None]:
    data = read_snapshot()
    if not data:
        return [], None
    snaps = [PaneSnap(**p) for p in data.get("panes", [])]
    return snaps, data.get("saved_at")


def match_live_pane(snap: PaneSnap, live_panes: list[dict]) -> dict | None:
    """Find the current pane corresponding to a saved one.

    Primary: same session + pane_id (stable if herdr preserves ids across
    restart). Fallback: same session + workspace label-or-id + cwd.
    """
    same_session = [p for p in live_panes if p["_session"] == snap.session]
    for p in same_session:
        if p.get("pane_id") == snap.pane_id:
            return p
    for p in same_session:
        if p.get("cwd") == snap.cwd and (
            p.get("_workspace_label") == snap.workspace_label
            or p.get("workspace_id") == snap.workspace_id
        ):
            return p
    return None
