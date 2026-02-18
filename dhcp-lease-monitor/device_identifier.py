"""Device identification helpers for DHCP lease entries."""

from __future__ import annotations

from typing import Callable

try:
    from mac_vendor_lookup import MacLookup  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    MacLookup = None


UNKNOWN_VENDOR = "Unknown vendor"
PRIVATE_VENDOR = "Private MAC"


def is_private_mac(mac: str) -> bool:
    """Return True for locally administered (randomized/private) MAC addresses."""
    try:
        first_octet = int(mac.split(":", 1)[0], 16)
    except (ValueError, IndexError):
        return False
    return bool(first_octet & 0x02)


def format_mac_type(mac: str) -> str:
    if is_private_mac(mac):
        return "Locally administered (private)"
    return "Globally unique"


def _contains_any(value: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in value for pattern in patterns)


def infer_device_type(hostname: str, vendor: str, private_mac: bool) -> str:
    """Infer device type from hostname + vendor using spec-defined priority."""
    host = hostname.lower()
    vendor_lc = vendor.lower()

    if "iphone" in host:
        return "phone"
    if "ipad" in host:
        return "tablet"
    if _contains_any(host, ("macbook", "mbp", "-laptop")):
        return "laptop"
    if "air" in host and "apple" in vendor_lc:
        return "laptop"
    if host.startswith("npi"):
        return "printer"
    if _contains_any(host, ("printer", "laserjet", "officejet")):
        return "printer"
    if _contains_any(host, ("tv", "roku", "firestick", "chromecast", "appletv")):
        return "tv"
    if _contains_any(host, ("echo", "alexa", "google-home", "homepod")):
        return "speaker"
    if _contains_any(vendor_lc, ("hp inc", "hewlett", "canon", "epson", "brother")):
        return "printer"
    if "apple" in vendor_lc:
        return "apple"
    if _contains_any(vendor_lc, ("samsung", "oneplus", "xiaomi", "huawei")):
        return "phone"
    if _contains_any(vendor_lc, ("intel", "realtek", "qualcomm")):
        return "computer"
    if private_mac:
        return "private"
    return "unknown"


def icon_name_for_device_type(device_type: str) -> str:
    return {
        "phone": "phone",
        "tablet": "tablet",
        "laptop": "laptop",
        "printer": "printer",
        "tv": "video-display",
        "speaker": "audio-speakers",
        "apple": "computer-apple",
        "computer": "computer",
        "private": "network-wireless",
        "unknown": "network-wired",
    }.get(device_type, "network-wired")


def display_device_type(device_type: str) -> str:
    return {
        "phone": "Phone",
        "tablet": "Tablet",
        "laptop": "Laptop",
        "printer": "Printer",
        "tv": "TV / Media",
        "speaker": "Smart Speaker",
        "apple": "Apple Device",
        "computer": "Computer",
        "private": "Private MAC Device",
        "unknown": "Unknown",
    }.get(device_type, "Unknown")


class DeviceIdentifier:
    """Vendor + device type resolver with cached OUI lookups."""

    def __init__(self, vendor_lookup: object | None = None) -> None:
        self._cache: dict[str, str] = {}
        self._lookup_fn: Callable[[str], str] | None = None

        if callable(vendor_lookup):
            self._lookup_fn = vendor_lookup  # type: ignore[assignment]
        elif vendor_lookup is not None and hasattr(vendor_lookup, "lookup"):
            self._lookup_fn = vendor_lookup.lookup  # type: ignore[assignment]
        elif MacLookup is not None:
            try:
                lookup = MacLookup()
                self._lookup_fn = lookup.lookup
            except Exception:
                self._lookup_fn = None

    def resolve_vendor(self, mac: str) -> str:
        if is_private_mac(mac):
            return PRIVATE_VENDOR

        prefix = ":".join(mac.lower().split(":")[:3])
        if prefix in self._cache:
            return self._cache[prefix]

        vendor = UNKNOWN_VENDOR
        if self._lookup_fn is not None:
            try:
                value = self._lookup_fn(mac)
                if isinstance(value, str) and value.strip():
                    vendor = value.strip()
            except Exception:
                vendor = UNKNOWN_VENDOR

        self._cache[prefix] = vendor
        return vendor

    def identify(self, mac: str, hostname: str) -> tuple[str, str, str]:
        private_mac = is_private_mac(mac)
        vendor = self.resolve_vendor(mac)
        device_type = infer_device_type(hostname, vendor, private_mac)
        icon_name = icon_name_for_device_type(device_type)
        return vendor, device_type, icon_name

