"""AIO (liquid cooler) data layer.

Reads liquid-cooler thermals from the OpenLinkHub daemon's localhost HTTP API
and returns a JSON-serializable snapshot. OpenLinkHub is the only source; a
device the daemon cannot open or does not support is simply absent from the
snapshot.

The module exposes three entry points:

- `build_snapshot(cpu_json, devices_json)`: pure, no I/O. Both arguments are
  already-decoded API responses (either may be None). The Qt section calls this
  after fetching asynchronously, so all parsing lives in exactly one place.
- `read_aio()`: synchronous convenience wrapper (urllib fetch + build_snapshot),
  used by the CLI and by tests. The UI does not use it — see aio_section.py.
- CLI mode: `aio_reader.py --json` prints the snapshot to stdout. Logs go to
  stderr.

Three quirks of the OpenLinkHub API drive most of the code here:

1. `status` means different things per endpoint. `/api/cpuTemp` returns
   `status:1` on success; `/api/devices/` returns `status:0` on success. We gate
   the devices response on having channels, never on `status`.
2. `/api/devices/` includes pseudo-devices — a `"cluster"` entry with no
   channels. Devices without channels are skipped.
3. Temperatures arrive as pre-formatted strings with a unit ("98.0 °C"), and the
   daemon has a Celsius/Fahrenheit toggle, so "208.4 °F" is reachable.

Read-only by design. Fan and pump duty writes are silently ignored by Commander
ST firmware 2.x (both OpenLinkHub and liquidctl report success and change
nothing), so this module issues GETs only. See
~/git/sysadmin/runbooks/aio-coolant-overtemp-and-commander-st-fan-control.md.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_BASE_URL = os.environ.get("OPENLINKHUB_API", "http://127.0.0.1:27003/api")
DEFAULT_TIMEOUT = 2.0

CPU_TEMP_PATH = "cpuTemp"
DEVICES_PATH = "devices/"

# OpenLinkHub's channel `description` values we care about. Matching on these
# rather than on channel index keeps the reader device-agnostic (channel 0 being
# the AIO is a convention of this cooler, not of the API).
DESC_AIO = "AIO"
DESC_FAN = "Fan"

_log = logging.getLogger(__name__)


def endpoint_urls(base_url: str = DEFAULT_BASE_URL) -> dict[str, str]:
    """The two URLs a snapshot needs, keyed by their `build_snapshot` argument.

    Shared by `read_aio` and by the Qt section's async fetch so the endpoint
    layout is described once.
    """
    base = base_url.rstrip("/")
    return {"cpu": f"{base}/{CPU_TEMP_PATH}", "devices": f"{base}/{DEVICES_PATH}"}


def decode_payload(raw: bytes | str | None) -> dict | None:
    """Decode an API response body. Anything unusable yields None."""
    if not raw:
        return None
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)
    except (UnicodeDecodeError, ValueError) as e:
        _log.debug("openlinkhub_decode_failed err=%s", e)
        return None


def _parse_temperature(value) -> float | None:
    """Parse an OpenLinkHub temperature into Celsius.

    Accepts the daemon's formatted strings ("98.0 °C", "208.4 °F"), a bare
    number, or a numeric string. Returns None for anything unparseable, which
    callers treat as "not reported".
    """
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None

    fahrenheit = "F" in text.upper()
    # Keep digits, sign and decimal point; drop the degree sign and unit letter.
    number = "".join(c for c in text if c.isdigit() or c in "-.")
    try:
        celsius = float(number)
    except ValueError:
        return None
    if fahrenheit:
        celsius = (celsius - 32.0) * 5.0 / 9.0
    return round(celsius, 1)


def _channel_sort_key(key) -> tuple[int, str]:
    """Sort "10" after "9". Non-numeric keys sort last, by name."""
    try:
        return (int(key), "")
    except (TypeError, ValueError):
        return (2**31, str(key))


def _iter_channels(devices_json: dict | None):
    """Yield (device_name, channel_dict) for every channel of every real device.

    Skips pseudo-devices such as the "cluster" entry, which carry no channels.
    """
    if not isinstance(devices_json, dict):
        return
    devices = devices_json.get("devices")
    if not isinstance(devices, dict):
        return
    for device in devices.values():
        if not isinstance(device, dict):
            continue
        detail = device.get("GetDevice")
        if not isinstance(detail, dict):
            continue
        channels = detail.get("devices")
        if not isinstance(channels, dict) or not channels:
            continue
        product = detail.get("product") or device.get("Product") or "?"
        # Channel keys are stringified ints; sort numerically so fan order is
        # stable and matches the daemon's own display order.
        for key in sorted(channels, key=_channel_sort_key):
            channel = channels[key]
            if isinstance(channel, dict):
                yield product, channel


def _rpm(channel: dict) -> int | None:
    value = channel.get("rpm")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _extract_cpu_temp(cpu_json: dict | None) -> float | None:
    """Pull the CPU package temperature out of an /api/cpuTemp response.

    This endpoint does use `status` as a success flag (unlike /api/devices/).
    """
    if not isinstance(cpu_json, dict):
        return None
    if cpu_json.get("status") != 1:
        return None
    return _parse_temperature(cpu_json.get("data"))


def _extract_cooler(devices_json: dict | None) -> tuple[float | None, int | None, str | None]:
    """Return (coolant_temp_c, pump_rpm, label) for the first cooler found.

    Prefers a channel whose description is "AIO". Falls back to any channel that
    advertises temperatures and actually reports one, so a non-Corsair cooler
    with a different description still shows up. A temperature of exactly 0 is
    OpenLinkHub's null value for fan channels, not a real reading.
    """
    fallback: tuple[float | None, int | None, str | None] | None = None

    for product, channel in _iter_channels(devices_json):
        temp = _parse_temperature(channel.get("temperature"))
        if temp is not None and temp == 0:
            temp = None
        label = channel.get("name") or product

        if channel.get("description") == DESC_AIO:
            return temp, _rpm(channel), label

        if fallback is None and channel.get("HasTemps") and temp is not None:
            fallback = (temp, _rpm(channel), label)

    if fallback is not None:
        return fallback
    return None, None, None


def _extract_fans(devices_json: dict | None) -> list[dict]:
    """Return [{"name", "rpm"}] for every fan channel across all devices.

    A fan reporting 0 rpm is kept — zero-RPM mode is a real state — but callers
    exclude it from the average.
    """
    fans: list[dict] = []
    for _product, channel in _iter_channels(devices_json):
        if channel.get("description") != DESC_FAN:
            continue
        if not channel.get("HasSpeed"):
            continue
        rpm = _rpm(channel)
        if rpm is None:
            continue
        fans.append({"name": channel.get("name") or "Fan", "rpm": rpm})
    return fans


def average_fan_rpm(fans: list[dict]) -> int | None:
    """Mean rpm across fans that are actually spinning, or None."""
    spinning = [f["rpm"] for f in fans if isinstance(f.get("rpm"), int) and f["rpm"] > 0]
    if not spinning:
        return None
    return int(round(sum(spinning) / len(spinning)))


def build_snapshot(cpu_json: dict | None, devices_json: dict | None) -> dict:
    """Build the snapshot dict from two decoded API responses. Pure; no I/O.

    `available` is True when at least one metric is displayable. A daemon that
    answers but manages only unsupported hardware (no cooler, no fans, no CPU
    temp) is reported as unavailable, so the section stays hidden rather than
    rendering an empty frame.
    """
    cpu_temp = _extract_cpu_temp(cpu_json)
    coolant_temp, pump_rpm, coolant_label = _extract_cooler(devices_json)
    fans = _extract_fans(devices_json)

    available = cpu_temp is not None or coolant_temp is not None or bool(fans)
    if available:
        error = None
    elif cpu_json is None and devices_json is None:
        error = "openlinkhub unreachable"
    else:
        error = "no supported device"

    return {
        "available": available,
        "error": error,
        "timestamp": time.time(),
        "cpu_temp_c": cpu_temp,
        "coolant_temp_c": coolant_temp,
        "coolant_label": coolant_label,
        "pump_rpm": pump_rpm,
        "fans": fans,
    }


def _fetch_json(url: str, timeout: float) -> dict | None:
    """GET a JSON document. Any failure yields None — callers degrade."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return decode_payload(resp.read())
    except (urllib.error.URLError, OSError) as e:
        _log.debug("openlinkhub_fetch_failed url=%s err=%s", url, e)
        return None


def read_aio(base_url: str = DEFAULT_BASE_URL, timeout: float = DEFAULT_TIMEOUT) -> dict:
    """Synchronous snapshot. Used by the CLI and tests, not by the Qt section."""
    urls = endpoint_urls(base_url)
    return build_snapshot(
        _fetch_json(urls["cpu"], timeout),
        _fetch_json(urls["devices"], timeout),
    )


def main(argv: list[str]) -> int:
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.DEBUG if "--debug" in argv else logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )
    snapshot = read_aio()
    print(json.dumps(snapshot, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
