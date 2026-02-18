"""Lease parsing and interface detection utilities."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import ipaddress
from pathlib import Path
import time
from typing import Iterable, Sequence

from device_identifier import DeviceIdentifier, format_mac_type


DEFAULT_LEASE_FILE = "/var/lib/misc/dnsmasq.leases"


@dataclass(frozen=True)
class DhcpLease:
    expiry: int
    mac: str
    ip: str
    hostname: str
    client_id: str | None
    vendor: str
    device_type: str
    icon_name: str
    is_expired: bool
    time_remaining: int
    is_static: bool
    mac_type: str
    raw_hostname: str
    reverse_dns: str | None = None


@dataclass(frozen=True)
class RouteEntry:
    interface: str
    destination: int
    mask: int
    metric: int


def _route_hex_to_int(value_hex: str) -> int:
    return int.from_bytes(bytes.fromhex(value_hex), byteorder="little", signed=False)


def _normalize_mac(mac: str) -> str:
    return mac.lower()


def _validate_ipv4(ip: str) -> str:
    parsed = ipaddress.ip_address(ip)
    if parsed.version != 4:
        raise ValueError("IPv6 addresses are not supported by this widget")
    return ip


def parse_lease_line(
    line: str,
    identifier: DeviceIdentifier,
    now: int | None = None,
) -> DhcpLease:
    parts = line.strip().split()
    if len(parts) < 5:
        raise ValueError(f"Invalid lease line: {line!r}")

    current_ts = int(time.time()) if now is None else now

    expiry = int(parts[0])
    mac = _normalize_mac(parts[1])
    ip = _validate_ipv4(parts[2])
    raw_hostname = parts[3]
    hostname = "Unknown" if raw_hostname == "*" else raw_hostname
    raw_client_id = parts[4]
    client_id = None if raw_client_id == "*" else raw_client_id

    is_static = expiry == 0
    is_expired = False if is_static else current_ts > expiry
    if is_static or is_expired:
        time_remaining = 0
    else:
        time_remaining = max(0, expiry - current_ts)

    vendor, device_type, icon_name = identifier.identify(mac, hostname)
    return DhcpLease(
        expiry=expiry,
        mac=mac,
        ip=ip,
        hostname=hostname,
        client_id=client_id,
        vendor=vendor,
        device_type=device_type,
        icon_name=icon_name,
        is_expired=is_expired,
        time_remaining=time_remaining,
        is_static=is_static,
        mac_type=format_mac_type(mac),
        raw_hostname=raw_hostname,
        reverse_dns=None,
    )


def sort_leases(leases: Iterable[DhcpLease]) -> list[DhcpLease]:
    """Sort static first, active next (newest first), expired last."""

    def sort_key(lease: DhcpLease) -> tuple[int, int, str, str]:
        if lease.is_static:
            return (0, 0, lease.hostname.lower(), lease.ip)
        if lease.is_expired:
            return (2, -lease.expiry, lease.hostname.lower(), lease.ip)
        return (1, -lease.expiry, lease.hostname.lower(), lease.ip)

    return sorted(leases, key=sort_key)


def load_leases(
    lease_file: str | Path = DEFAULT_LEASE_FILE,
    identifier: DeviceIdentifier | None = None,
    include_expired: bool = True,
    now: int | None = None,
) -> list[DhcpLease]:
    parser = identifier or DeviceIdentifier()
    path = Path(lease_file)
    if not path.exists():
        return []

    leases: list[DhcpLease] = []
    current_ts = int(time.time()) if now is None else now

    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            lease = parse_lease_line(line, parser, now=current_ts)
        except (ValueError, OSError):
            continue
        if lease.is_expired and not include_expired:
            continue
        leases.append(lease)

    return sort_leases(leases)


def _load_routes(route_path: str | Path = "/proc/net/route") -> list[RouteEntry]:
    path = Path(route_path)
    if not path.exists():
        return []

    entries: list[RouteEntry] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 8:
            continue

        interface = parts[0]
        destination = _route_hex_to_int(parts[1])
        flags = int(parts[3], 16)
        metric = int(parts[6], 10)
        mask = _route_hex_to_int(parts[7])

        if not (flags & 0x1):  # Route is up
            continue

        entries.append(
            RouteEntry(
                interface=interface,
                destination=destination,
                mask=mask,
                metric=metric,
            )
        )

    return entries


def detect_default_interface(routes: Sequence[RouteEntry] | None = None) -> str:
    candidates = list(routes) if routes is not None else _load_routes()
    defaults = [route for route in candidates if route.destination == 0 and route.mask == 0]
    if not defaults:
        return "unknown"
    defaults.sort(key=lambda route: (route.metric, route.interface))
    return defaults[0].interface


def detect_interface_for_ip(
    ip: str,
    routes: Sequence[RouteEntry] | None = None,
) -> str | None:
    candidates = list(routes) if routes is not None else _load_routes()
    if not candidates:
        return None

    ip_int = int(ipaddress.ip_address(ip))
    matched: list[tuple[int, int, str]] = []
    for route in candidates:
        if ip_int & route.mask == route.destination:
            prefix_len = route.mask.bit_count()
            matched.append((prefix_len, -route.metric, route.interface))

    if not matched:
        return None

    matched.sort(reverse=True)
    return matched[0][2]


def detect_interface_for_leases(
    leases: Sequence[DhcpLease],
    routes: Sequence[RouteEntry] | None = None,
) -> str:
    candidates = list(routes) if routes is not None else _load_routes()
    if not leases:
        return detect_default_interface(candidates)

    counter: Counter[str] = Counter()
    for lease in leases:
        interface = detect_interface_for_ip(lease.ip, candidates)
        if interface:
            counter[interface] += 1

    if counter:
        return counter.most_common(1)[0][0]
    return detect_default_interface(candidates)


def _format_duration(seconds: int, include_seconds: bool = False) -> str:
    total = max(0, seconds)
    hours, rem = divmod(total, 3600)
    minutes, sec = divmod(rem, 60)
    if include_seconds:
        return f"{hours}h {minutes}m {sec}s"
    return f"{hours}h {minutes}m"


def format_time_remaining(lease: DhcpLease, include_seconds: bool = False) -> str:
    if lease.is_static:
        return "STATIC"
    if lease.is_expired:
        return "EXPIRED"
    return f"expires in {_format_duration(lease.time_remaining, include_seconds=include_seconds)}"
