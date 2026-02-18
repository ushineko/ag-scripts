"""Unit tests for DHCP device identification heuristics."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))


from device_identifier import (  # noqa: E402
    DeviceIdentifier,
    format_mac_type,
    icon_name_for_device_type,
    infer_device_type,
    is_private_mac,
)


def test_is_private_mac():
    assert is_private_mac("6e:be:93:2e:94:9a") is True
    assert is_private_mac("4c:e1:73:42:34:c9") is False


def test_hostname_inference_takes_priority():
    assert infer_device_type("my-iphone", "Unknown vendor", private_mac=False) == "phone"
    assert infer_device_type("NPI89D0", "Unknown vendor", private_mac=False) == "printer"


def test_vendor_inference_when_hostname_unknown():
    assert infer_device_type("unknown", "Canon Inc.", private_mac=False) == "printer"
    assert infer_device_type("unknown", "Intel Corporate", private_mac=False) == "computer"


def test_private_mac_fallback_type():
    assert infer_device_type("device", "Private MAC", private_mac=True) == "private"


def test_icon_mapping_defaults_to_network_wired():
    assert icon_name_for_device_type("phone") == "phone"
    assert icon_name_for_device_type("nonexistent-type") == "network-wired"


def test_identifier_marks_private_mac_without_lookup():
    identifier = DeviceIdentifier(vendor_lookup=lambda _: "Apple, Inc.")
    vendor, device_type, icon_name = identifier.identify("6e:be:93:2e:94:9a", "mystery")

    assert vendor == "Private MAC"
    assert device_type == "private"
    assert icon_name == "network-wireless"


def test_format_mac_type():
    assert format_mac_type("6e:be:93:2e:94:9a") == "Locally administered (private)"
    assert format_mac_type("4c:e1:73:42:34:c9") == "Globally unique"

