"""Unit tests for DHCP lease parsing, sorting, and interface detection."""

from __future__ import annotations

import ipaddress
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))


from device_identifier import DeviceIdentifier  # noqa: E402
from lease_reader import (  # noqa: E402
    RouteEntry,
    detect_default_interface,
    detect_interface_for_ip,
    detect_interface_for_leases,
    load_leases,
    parse_lease_line,
)


def test_parse_lease_line_normalizes_fields():
    identifier = DeviceIdentifier(vendor_lookup=lambda _: "Apple, Inc.")
    line = "1771454360 AC:AE:19:42:56:A8 192.168.86.68 * *"
    lease = parse_lease_line(line, identifier=identifier, now=1771450000)

    assert lease.mac == "ac:ae:19:42:56:a8"
    assert lease.hostname == "Unknown"
    assert lease.client_id is None
    assert lease.vendor == "Apple, Inc."
    assert lease.is_expired is False
    assert lease.time_remaining == 4360
    assert lease.reverse_dns is None


def test_sorting_static_top_active_middle_expired_bottom(tmp_path: Path):
    now = 1000
    content = "\n".join(
        [
            "0 02:00:00:00:00:01 192.168.86.2 printer *",
            "1800 4c:e1:73:42:34:c9 192.168.86.20 macbook-pro 01:4c:e1:73:42:34:c9",
            "2400 dc:a6:32:12:34:56 192.168.86.30 desktop *",
            "900 00:11:22:33:44:55 192.168.86.99 old-device *",
        ]
    )
    lease_file = tmp_path / "dnsmasq.leases"
    lease_file.write_text(content)

    leases = load_leases(
        lease_file=lease_file,
        identifier=DeviceIdentifier(vendor_lookup=lambda _: "Unknown vendor"),
        include_expired=True,
        now=now,
    )

    assert leases[0].is_static is True
    assert leases[1].expiry == 2400
    assert leases[2].expiry == 1800
    assert leases[3].is_expired is True


def test_include_expired_false_hides_expired(tmp_path: Path):
    now = 1000
    content = "\n".join(
        [
            "1200 aa:bb:cc:dd:ee:01 192.168.86.10 active-one *",
            "900 aa:bb:cc:dd:ee:02 192.168.86.11 expired-one *",
        ]
    )
    lease_file = tmp_path / "dnsmasq.leases"
    lease_file.write_text(content)

    leases = load_leases(
        lease_file=lease_file,
        identifier=DeviceIdentifier(vendor_lookup=lambda _: "Unknown vendor"),
        include_expired=False,
        now=now,
    )

    assert len(leases) == 1
    assert leases[0].hostname == "active-one"


def test_invalid_lines_are_ignored(tmp_path: Path):
    lease_file = tmp_path / "dnsmasq.leases"
    lease_file.write_text(
        "\n".join(
            [
                "this is not valid",
                "1700 aa:bb:cc:dd:ee:ff not-an-ip host *",
                "1800 aa:bb:cc:dd:ee:11 192.168.86.22 valid-host *",
            ]
        )
    )

    leases = load_leases(
        lease_file=lease_file,
        identifier=DeviceIdentifier(vendor_lookup=lambda _: "Unknown vendor"),
        now=1000,
    )

    assert len(leases) == 1
    assert leases[0].ip == "192.168.86.22"


def test_interface_detection_prefers_longest_prefix_and_metric():
    subnet_86 = ipaddress.ip_network("192.168.86.0/24")
    subnet_168 = ipaddress.ip_network("192.168.0.0/16")
    routes = [
        RouteEntry(
            interface="eno2",
            destination=int(subnet_86.network_address),
            mask=int(subnet_86.netmask),
            metric=100,
        ),
        RouteEntry(
            interface="eth0",
            destination=int(subnet_168.network_address),
            mask=int(subnet_168.netmask),
            metric=50,
        ),
        RouteEntry(interface="wlan0", destination=0, mask=0, metric=10),
    ]

    assert detect_interface_for_ip("192.168.86.45", routes) == "eno2"
    assert detect_interface_for_ip("192.168.50.8", routes) == "eth0"
    assert detect_default_interface(routes) == "wlan0"


def test_interface_detection_for_leases_falls_back_to_default():
    routes = [RouteEntry(interface="wlan0", destination=0, mask=0, metric=100)]
    assert detect_interface_for_leases([], routes) == "wlan0"
