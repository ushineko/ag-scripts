"""AIO (liquid cooler) data layer.

Reads liquid-cooler thermals from two sources and returns a JSON-serializable
snapshot:

1. `liquidctl --json status` (preferred). The cooler on this machine is an NZXT
   Kraken Elite V2 (`1e71:3012`), which the kernel's `nzxt-kraken3` driver does
   not match — it covers 2007/2014/3008/300C/300E — so no hwmon node exists and
   `sensors` reports nothing. liquidctl is the only source of pump rpm and
   coolant temperature.
2. The OpenLinkHub daemon's localhost HTTP API (fallback for the cooler, and
   still the only source of the CPU package temperature).

Both are optional. A source that is absent, unreadable or manages no cooler
contributes nothing rather than producing a wrong reading — see the note on
`_extract_cooler` about PSU probes.

The module exposes three entry points:

- `build_snapshot(cpu_json, devices_json, liquid_json)`: pure, no I/O. All
  arguments are already-decoded responses (any may be None). The Qt section
  calls this after fetching asynchronously, so all parsing lives in exactly one
  place.
- `read_aio()`: synchronous convenience wrapper (urllib fetch + liquidctl
  subprocess + build_snapshot), used by the CLI and by tests. The UI does not
  use it — see aio_section.py, which drives liquidctl through QProcess so the
  GUI thread never blocks.
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
import shutil
import subprocess
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

# Descriptions that denote an actual cooler channel. The fallback cooler search
# is restricted to these because the HX1000i PSU advertises `description:
# "Probe"` channels named "VRM Temperature" and "PSU Temperature" that carry a
# plausible-looking temperature. Accepting any channel with a temperature — as
# this module previously did — rendered a PSU VRM sensor as coolant next to a
# pump reading of 0, which is indistinguishable from a stopped pump. See
# spec 020.
COOLER_DESCRIPTIONS = frozenset({DESC_AIO, "Pump", "Water Block", "Liquid"})

# liquidctl source. `--match` narrows to the cooler so an HX1000i or Aura
# controller on the same bus is not opened; opening those costs time and can
# contend for a hidraw node.
LIQUIDCTL_BIN = os.environ.get("LIQUIDCTL_BIN", "liquidctl")
LIQUIDCTL_MATCH = os.environ.get("LIQUIDCTL_MATCH", "kraken")
LIQUIDCTL_TIMEOUT = 5.0

# liquidctl status keys, lowercased for matching. The driver labels these
# "Liquid temperature", "Pump speed", "Fan speed" for a Kraken; other coolers
# use slightly different wording, so match on substrings.
_LIQUID_TEMP_KEYS = ("liquid temperature", "coolant temperature", "temperature")
_LIQUID_PUMP_KEYS = ("pump speed",)
_LIQUID_FAN_KEYS = ("fan speed",)

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


def liquidctl_argv(match: str = LIQUIDCTL_MATCH) -> list[str]:
    """The command the liquidctl source runs.

    Shared by `read_aio` and by the Qt section's QProcess call so the invocation
    is described once.
    """
    return [LIQUIDCTL_BIN, "--json", "--match", match, "status"]


def liquidctl_available() -> bool:
    """True when the liquidctl binary is on PATH. Cheap; no device access."""
    return shutil.which(LIQUIDCTL_BIN) is not None


def _liquid_value(entry: dict) -> float | None:
    """Pull a numeric `value` out of one liquidctl status entry."""
    value = entry.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def parse_liquidctl(raw: bytes | str | dict | list | None) -> dict | None:
    """Turn `liquidctl --json status` output into a cooler dict.

    Returns {"coolant_temp_c", "pump_rpm", "fans", "label"} for the first device
    that reports at least one of coolant temperature or pump speed, or None when
    the payload is missing, unparseable, or describes no cooler.

    liquidctl emits a list of devices, each with a `status` list of
    {key, value, unit} records, so nothing here assumes a fixed ordering.
    """
    if isinstance(raw, (bytes, str)):
        raw = decode_payload(raw)
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return None

    for device in raw:
        if not isinstance(device, dict):
            continue
        status = device.get("status")
        if not isinstance(status, list):
            continue

        coolant = pump = None
        fans: list[dict] = []
        for entry in status:
            if not isinstance(entry, dict):
                continue
            key = str(entry.get("key") or "").strip().lower()
            if not key:
                continue
            value = _liquid_value(entry)
            if value is None:
                continue

            if coolant is None and any(k in key for k in _LIQUID_TEMP_KEYS):
                # A Kraken reports °C; liquidctl does not convert units, so an
                # F-reporting driver would need handling here if one appears.
                coolant = round(value, 1)
            elif pump is None and any(k in key for k in _LIQUID_PUMP_KEYS):
                pump = int(value)
            elif any(k in key for k in _LIQUID_FAN_KEYS):
                fans.append({"name": entry.get("key") or "Fan", "rpm": int(value)})

        if coolant is None and pump is None:
            continue
        return {
            "coolant_temp_c": coolant,
            "pump_rpm": pump,
            "fans": fans,
            "label": device.get("description") or "Liquid cooler",
        }

    return None


def _channel_sort_key(key) -> tuple[int, str]:
    """Sort "10" after "9". Non-numeric keys sort last, by name."""
    try:
        return (int(key), "")
    except (TypeError, ValueError):
        return (2**31, str(key))


def _iter_devices(devices_json: dict | None):
    """Yield each device's `GetDevice` detail dict."""
    if not isinstance(devices_json, dict):
        return
    devices = devices_json.get("devices")
    if not isinstance(devices, dict):
        return
    for device in devices.values():
        if not isinstance(device, dict):
            continue
        detail = device.get("GetDevice")
        if isinstance(detail, dict):
            yield detail


def _iter_channels(devices_json: dict | None):
    """Yield (device_name, channel_dict) for every channel of every real device.

    Skips pseudo-devices such as the "cluster" entry, which carry no channels.
    """
    for detail in _iter_devices(devices_json):
        channels = detail.get("devices")
        if not isinstance(channels, dict) or not channels:
            continue
        product = detail.get("product") or "?"
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

    Prefers a channel whose description is "AIO". Falls back to any channel
    whose description names a cooler role (see COOLER_DESCRIPTIONS), so a cooler
    that labels its channel "Pump" or "Water Block" still shows up.

    The fallback is deliberately restricted to those descriptions rather than
    "anything with a temperature". The HX1000i PSU reports `description:
    "Probe"` channels carrying its VRM and internal temperatures, and accepting
    those surfaced a PSU sensor as coolant with `pump_rpm: 0` beside it — a
    reading that looks exactly like a stopped pump on a healthy machine, and
    conversely would mask a genuinely stopped pump. See spec 020.

    A temperature of exactly 0 is OpenLinkHub's null value for fan channels, not
    a real reading.
    """
    fallback: tuple[float | None, int | None, str | None] | None = None

    for product, channel in _iter_channels(devices_json):
        description = channel.get("description")
        if description not in COOLER_DESCRIPTIONS:
            continue

        temp = _parse_temperature(channel.get("temperature"))
        if temp is not None and temp == 0:
            temp = None
        label = channel.get("name") or product

        if description == DESC_AIO:
            return temp, _rpm(channel), label
        if fallback is None:
            fallback = (temp, _rpm(channel), label)

    if fallback is not None:
        return fallback
    return None, None, None


def _extract_rgb_target(devices_json: dict | None) -> tuple[str | None, list[int], int | None]:
    """Return (device_id, rgb_channels, brightness) for the RGB write target.

    Prefers the device owning the AIO channel, matching how aio-color.sh picks
    its default device. Falls back to the first device that has RGB channels, so
    a non-cooler RGB device is still addressable.

    Channels come from the `rgbDevices` map rather than by probing channels
    0..15 with `getOverride`, which is what the shell script has to do. The map
    is already in the response this snapshot is built from.
    """
    fallback: tuple[str | None, list[int], int | None] | None = None

    for detail in _iter_devices(devices_json):
        rgb = detail.get("rgbDevices")
        if not isinstance(rgb, dict) or not rgb:
            continue
        channels = []
        for key in sorted(rgb, key=_channel_sort_key):
            try:
                channels.append(int(key))
            except (TypeError, ValueError):
                continue
        if not channels:
            continue

        serial = detail.get("serial")
        profile = detail.get("DeviceProfile")
        brightness = None
        if isinstance(profile, dict):
            value = profile.get("Brightness")
            if isinstance(value, int) and not isinstance(value, bool):
                brightness = value

        target = (serial, channels, brightness)
        own_channels = detail.get("devices")
        if isinstance(own_channels, dict) and any(
            isinstance(c, dict) and c.get("description") == DESC_AIO
            for c in own_channels.values()
        ):
            return target
        if fallback is None:
            fallback = target

    return fallback if fallback is not None else (None, [], None)


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


# Alert thresholds. These are judgement calls, not vendor specification. Idle
# readings on this machine are coolant 36.3 C and pump 1725 rpm at 35% duty; the
# Corsair failure that motivated spec 020 took the CPU to 100 C.
COOLANT_WARN_C = 50.0
COOLANT_CRITICAL_C = 60.0
PUMP_WARN_RPM = 500

ALERT_OK = "ok"
ALERT_WARNING = "warning"
ALERT_CRITICAL = "critical"


def evaluate_alert(snapshot: dict) -> tuple[str, str | None]:
    """Classify a snapshot's cooling health. Pure; returns (state, reason).

    Only positive evidence raises an alert. A snapshot with no pump reading is
    `ok`, not `critical` — absence of evidence is not a stopped pump, and a
    liquidctl that failed to run must not look like a cooling failure. The
    caller distinguishes "no data" from "healthy" via `available`.
    """
    if not isinstance(snapshot, dict):
        return ALERT_OK, None

    pump = snapshot.get("pump_rpm")
    coolant = snapshot.get("coolant_temp_c")

    pump_reported = isinstance(pump, int) and not isinstance(pump, bool)
    coolant_reported = isinstance(coolant, (int, float)) and not isinstance(coolant, bool)

    if coolant_reported and coolant >= COOLANT_CRITICAL_C:
        return ALERT_CRITICAL, f"Coolant {coolant:.1f} C"
    if pump_reported and pump == 0:
        return ALERT_CRITICAL, "Pump stopped (0 rpm)"
    if pump_reported and pump < PUMP_WARN_RPM:
        return ALERT_WARNING, f"Pump {pump} rpm"
    if coolant_reported and coolant >= COOLANT_WARN_C:
        return ALERT_WARNING, f"Coolant {coolant:.1f} C"
    return ALERT_OK, None


def build_snapshot(
    cpu_json: dict | None,
    devices_json: dict | None,
    liquid_json: bytes | str | dict | list | None = None,
) -> dict:
    """Build the snapshot dict from the decoded source responses. Pure; no I/O.

    `liquid_json` is `liquidctl --json status` output and takes precedence over
    OpenLinkHub for coolant temperature, pump speed and cooler fans. OpenLinkHub
    remains the only source of the CPU package temperature and of the RGB write
    target, and is still consulted for the cooler when liquidctl yields nothing.

    `available` is True when at least one metric is displayable. Sources that
    answer but manage no cooler (no coolant, no pump, no fans, no CPU temp) are
    reported as unavailable, so the section stays hidden rather than rendering an
    empty frame.
    """
    cpu_temp = _extract_cpu_temp(cpu_json)
    coolant_temp, pump_rpm, coolant_label = _extract_cooler(devices_json)
    fans = _extract_fans(devices_json)
    device_id, rgb_channels, brightness = _extract_rgb_target(devices_json)

    liquid = parse_liquidctl(liquid_json)
    source = "openlinkhub" if (coolant_temp is not None or pump_rpm is not None) else None
    if liquid is not None:
        coolant_temp = liquid["coolant_temp_c"]
        pump_rpm = liquid["pump_rpm"]
        coolant_label = liquid["label"]
        # Cooler fans come from the same device as the pump; prefer them, but
        # keep OpenLinkHub's list if liquidctl reported none (a cooler whose
        # fans are on a separate controller).
        if liquid["fans"]:
            fans = liquid["fans"]
        source = "liquidctl"

    available = cpu_temp is not None or coolant_temp is not None or bool(fans)
    if available:
        error = None
    elif cpu_json is None and devices_json is None and liquid_json is None:
        error = "no cooling source reachable"
    else:
        error = "no supported device"

    snapshot = {
        "available": available,
        "error": error,
        "timestamp": time.time(),
        "cpu_temp_c": cpu_temp,
        "coolant_temp_c": coolant_temp,
        "coolant_label": coolant_label,
        "pump_rpm": pump_rpm,
        "fans": fans,
        # Which source supplied the cooler reading, or None when neither did.
        # Surfaced so the UI and logs can tell "no cooler" from "no daemon".
        "cooler_source": source,
        # RGB write target (spec 019). Present whenever the daemon reports RGB
        # channels, independent of whether any temperature was readable.
        "device_id": device_id,
        "rgb_channels": rgb_channels,
        "brightness": brightness,
    }
    snapshot["alert_state"], snapshot["alert_reason"] = evaluate_alert(snapshot)
    return snapshot


def _fetch_json(url: str, timeout: float) -> dict | None:
    """GET a JSON document. Any failure yields None — callers degrade."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return decode_payload(resp.read())
    except (urllib.error.URLError, OSError) as e:
        _log.debug("openlinkhub_fetch_failed url=%s err=%s", url, e)
        return None


def _run_liquidctl(timeout: float = LIQUIDCTL_TIMEOUT) -> str | None:
    """Run liquidctl and return its stdout. Any failure yields None.

    Blocking, so this is for the CLI and tests only. The Qt section drives the
    same command through QProcess — see aio_section.py. The timeout matters:
    liquidctl opens a hidraw node, and contention on this machine (logid,
    solaar and battery_reader sharing one node) has produced multi-second
    stalls in the past.
    """
    if not liquidctl_available():
        _log.debug("liquidctl_missing bin=%s", LIQUIDCTL_BIN)
        return None
    try:
        proc = subprocess.run(
            liquidctl_argv(),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as e:
        _log.debug("liquidctl_failed err=%s", e)
        return None
    if proc.returncode != 0:
        _log.debug("liquidctl_nonzero rc=%s err=%s", proc.returncode, proc.stderr.strip()[:200])
        return None
    return proc.stdout


def read_aio(base_url: str = DEFAULT_BASE_URL, timeout: float = DEFAULT_TIMEOUT) -> dict:
    """Synchronous snapshot. Used by the CLI and tests, not by the Qt section."""
    urls = endpoint_urls(base_url)
    return build_snapshot(
        _fetch_json(urls["cpu"], timeout),
        _fetch_json(urls["devices"], timeout),
        _run_liquidctl(),
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
