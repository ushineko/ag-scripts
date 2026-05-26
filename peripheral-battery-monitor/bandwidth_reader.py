"""Bandwidth data layer.

Reads /proc/net/dev for a configured set of interfaces and returns a JSON-
serializable dict. Optionally enriches tailscale* interfaces with metadata
obtained from `tailscale status --json` (rate-limited, best-effort).

The module exposes two entry points:

- `read_interfaces(names, *, include_tailscale_meta=False)`: importable API
  used by the in-process bandwidth UI poller. Cheap; suitable for ~2s cadence.
- CLI mode: `bandwidth_reader.py --json [iface ...]` prints the same dict to
  stdout. Logs go to stderr.

The output shape is intentionally plain dicts (no dataclasses) so the data
layer contract is exactly JSON.
"""

import json
import logging
import os
import subprocess
import sys
import time

PROC_NET_DEV = "/proc/net/dev"

_TS_META_TTL_SECS = 60.0
_TS_META_CACHE: dict | None = None
_TS_META_CACHE_TS: float = 0.0


def _parse_proc_net_dev(text: str) -> dict[str, dict]:
    """Parse the contents of /proc/net/dev into {iface: {rx_bytes, tx_bytes}}.

    Format (two header lines, then one interface per line):
        Inter-|   Receive ...                       |  Transmit ...
         face |bytes    packets errs drop ... |bytes    packets errs drop ...
            lo: 12345 67 0 0 0 0 0 0 12345 67 0 0 0 0 0 0
    """
    out: dict[str, dict] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        name_part, _, stats_part = line.partition(":")
        name = name_part.strip()
        fields = stats_part.split()
        if len(fields) < 16:
            continue
        try:
            rx_bytes = int(fields[0])
            tx_bytes = int(fields[8])
        except ValueError:
            continue
        out[name] = {"rx_bytes": rx_bytes, "tx_bytes": tx_bytes}
    return out


def _read_proc_net_dev() -> dict[str, dict]:
    try:
        with open(PROC_NET_DEV, "r") as f:
            return _parse_proc_net_dev(f.read())
    except OSError as e:
        logging.getLogger(__name__).warning("proc_net_dev_read_failed: %s", e)
        return {}


def _fetch_tailscale_status(timeout: float = 2.0) -> dict | None:
    """Run `tailscale status --json` and return the parsed dict, or None.

    Failures (missing binary, non-zero exit, parse error, timeout) all yield
    None; callers should treat that as 'metadata unknown' and continue.
    """
    try:
        proc = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logging.getLogger(__name__).debug("tailscale_status_unavailable: %s", e)
        return None
    if proc.returncode != 0:
        logging.getLogger(__name__).debug(
            "tailscale_status_nonzero: rc=%s stderr=%s", proc.returncode, proc.stderr[:200]
        )
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        logging.getLogger(__name__).warning("tailscale_status_parse_failed: %s", e)
        return None


def _summarize_tailscale(status: dict | None) -> dict:
    """Reduce a `tailscale status --json` dict to the metadata fields we display.

    Returns a dict with keys: type, backend_state, exit_node, exit_node_online.
    When `status` is None (call failed), all dynamic fields are None / "unknown".
    """
    if not status:
        return {
            "type": "tailscale",
            "backend_state": "unknown",
            "exit_node": None,
            "exit_node_online": None,
        }

    backend_state = status.get("BackendState", "unknown")
    exit_node = None
    exit_node_online = None

    exit_status = status.get("ExitNodeStatus")
    if exit_status:
        exit_id = exit_status.get("ID")
        exit_node_online = exit_status.get("Online")
        peers = status.get("Peer") or {}
        for _peer_key, peer in peers.items():
            if peer.get("ID") == exit_id:
                exit_node = peer.get("HostName") or peer.get("DNSName") or exit_id
                break
        if exit_node is None:
            exit_node = exit_id

    return {
        "type": "tailscale",
        "backend_state": backend_state,
        "exit_node": exit_node,
        "exit_node_online": exit_node_online,
    }


def _cached_tailscale_summary(now: float, ttl: float = _TS_META_TTL_SECS) -> dict:
    """Return a cached tailscale summary, refreshing at most once per `ttl` seconds."""
    global _TS_META_CACHE, _TS_META_CACHE_TS
    if _TS_META_CACHE is not None and (now - _TS_META_CACHE_TS) < ttl:
        return _TS_META_CACHE
    summary = _summarize_tailscale(_fetch_tailscale_status())
    _TS_META_CACHE = summary
    _TS_META_CACHE_TS = now
    return summary


def read_interfaces(
    names: list[str],
    *,
    include_tailscale_meta: bool = False,
) -> dict:
    """Read counters for the given interfaces from /proc/net/dev.

    Returns a JSON-serializable dict:
        {
          "timestamp": <monotonic seconds, float>,
          "interfaces": [
            {
              "name": "tailscale0",
              "exists": true,
              "rx_bytes": 1234,
              "tx_bytes": 5678,
              "metadata": { "type": "tailscale", "backend_state": "Running",
                            "exit_node": "us-east", "exit_node_online": true }
            },
            ...
          ]
        }

    When `include_tailscale_meta` is True, any interface name beginning with
    "tailscale" gets a `metadata` field; metadata is cached internally so
    `tailscale status --json` runs at most once per minute regardless of
    polling frequency. All other interfaces have `metadata: null`.
    """
    snapshot = _read_proc_net_dev()
    now = time.monotonic()
    ts_summary: dict | None = None

    entries: list[dict] = []
    for name in names:
        entry: dict = {
            "name": name,
            "exists": name in snapshot,
            "rx_bytes": snapshot.get(name, {}).get("rx_bytes", 0),
            "tx_bytes": snapshot.get(name, {}).get("tx_bytes", 0),
            "metadata": None,
        }
        if include_tailscale_meta and name.startswith("tailscale"):
            if ts_summary is None:
                ts_summary = _cached_tailscale_summary(now)
            entry["metadata"] = ts_summary
        entries.append(entry)

    return {"timestamp": now, "interfaces": entries}


def _main_cli(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)

    args = [a for a in argv[1:] if a != "--json"]
    include_ts = "--tailscale-meta" in args
    args = [a for a in args if a != "--tailscale-meta"]

    if not args:
        print(
            "usage: bandwidth_reader.py --json [--tailscale-meta] <iface> [<iface> ...]",
            file=sys.stderr,
        )
        return 2

    result = read_interfaces(args, include_tailscale_meta=include_ts)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main_cli(sys.argv))
