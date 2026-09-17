"""OpenRGB lighting control (spec 023).

Builds `openrgb` command lines and parses its output. Pure: nothing here runs a
process or touches Qt — `aio_section` executes what this returns through the
same serialised queue the cooler uses.

Why OpenRGB rather than liquidctl
---------------------------------
liquidctl reports **zero colour channels** for the NZXT Kraken 2024 Elite, which
specs 021 and 022 took to mean the hardware had no controllable lighting. It
does: OpenRGB drives the Kraken (and with it the radiator fans, whose RGB
daisy-chains into it), the GPU, the motherboard and the peripherals. The gap was
in the backend, not the hardware.

Three measured facts shape this module
--------------------------------------
1. **Always use `--client`.** The plain CLI re-detects every device on each
   invocation at ~9.1 s; against the running server the same call is ~0.03 s.
   Beware: the CLI *silently falls back* to local detection when the server is
   down, so a "working" command can still take nine seconds — `server_alive()`
   exists to tell the difference rather than inferring it from success.
2. **Modes are per device and do not overlap.** The RTX 4090 accepts
   `direct/breathing/flashing/off` and rejects `static`; the Kraken accepts
   `static`. Sending one broadcast mode is how the GPU got switched off during
   investigation — it errored on the mode and went dark anyway. So a mode is
   validated against that device's own list before being sent.
3. **Indices are not stable.** A server that has rescanned lists every device
   twice, so an index is only meaningful within one listing. Devices are
   addressed by name and resolved to an index per operation; nothing persists an
   index.
"""

from __future__ import annotations

import logging
import os
import re
import socket

_log = logging.getLogger(__name__)

OPENRGB_BIN = os.environ.get("OPENRGB_BIN", "openrgb")
OPENRGB_HOST = os.environ.get("OPENRGB_HOST", "127.0.0.1")
OPENRGB_PORT = int(os.environ.get("OPENRGB_PORT", "6742"))

# Devices a lighting profile drives by default: the case interior, plus the MM700
# mousepad, which the user asked to join the scenes (spec 030). Matched as
# case-insensitive substrings of the device name.
#
# The mouse and keyboard stay out. Their lighting is usually per-application and
# a scene stamping over it would be unwelcome; the mousepad is ambient in the
# same way the case is.
#
# NOTE on the MM700: OpenLinkHub also manages it. Two controllers writing one
# device can fight, and OpenLinkHub can reassert its own colour. If the mousepad
# ignores scenes or reverts, exclude it there (the `exclude` list in
# ~/.config/OpenLinkHub or /var/lib/openlinkhub/config.json) so OpenRGB owns it.
DEFAULT_SCOPE = ("kraken", "geforce", "maximus", "mm700")

# Intent -> the modes that can express it, best first. Resolution picks the
# first one a given device actually supports.
SOLID_MODES = ("static", "direct")
OFF_MODES = ("off", "direct")

_DEVICE_LINE = re.compile(r"^(\d+):\s+(.+?)\s*$")


def server_alive(timeout: float = 0.5) -> bool:
    """True when the OpenRGB server accepts a connection.

    Checked explicitly because the CLI hides the difference: with the server
    down, `--client` quietly falls back to a ~9 s local detection and still
    succeeds, so command success cannot distinguish the two.
    """
    try:
        with socket.create_connection((OPENRGB_HOST, OPENRGB_PORT), timeout):
            return True
    except OSError:
        return False


def _client_argv() -> list[str]:
    return [OPENRGB_BIN, "--client", f"{OPENRGB_HOST}:{OPENRGB_PORT}"]


def list_argv() -> list[str]:
    """Command listing the server's devices."""
    return _client_argv() + ["--list-devices"]


def parse_devices(output: bytes | str | None) -> list[dict]:
    """Parse `--list-devices` output into [{"index", "name"}].

    A rescanned server repeats every device, so only the first index per name is
    kept: later duplicates address the same hardware and would double every
    command.
    """
    if isinstance(output, bytes):
        output = output.decode("utf-8", "replace")
    if not output:
        return []

    devices: list[dict] = []
    seen: set[str] = set()
    for line in output.splitlines():
        match = _DEVICE_LINE.match(line.strip())
        if not match:
            continue
        index, name = int(match.group(1)), match.group(2).strip()
        # Skip liquidctl/OpenRGB log noise that happens to look like "N: text".
        if not name or name.startswith("["):
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        devices.append({"index": index, "name": name})
    return devices


def in_scope(name: str, scope: tuple[str, ...] = DEFAULT_SCOPE) -> bool:
    """True when a device name matches any scope substring."""
    lowered = (name or "").lower()
    return any(token.lower() in lowered for token in scope)


def scoped_devices(devices: list[dict],
                   scope: tuple[str, ...] = DEFAULT_SCOPE) -> list[dict]:
    return [d for d in devices if in_scope(d.get("name", ""), scope)]


def resolve_mode(supported: list[str], intent: str) -> str | None:
    """Pick a mode expressing `intent` from those a device supports.

    Returns None when the device cannot express it, so the caller skips that
    device rather than sending a mode it will reject. The GPU rejecting `static`
    and going dark is the reason this is not optional.
    """
    wanted = SOLID_MODES if intent == "solid" else OFF_MODES if intent == "off" else (intent,)
    # Return the device's own spelling ("Direct", not "direct"): OpenRGB is
    # lenient about case today, but echoing what the device reported is what
    # lets a caller compare the result against `active_mode` to confirm the
    # write actually landed.
    by_lower = {m.lower(): m for m in (supported or [])}
    for mode in wanted:
        if mode.lower() in by_lower:
            return by_lower[mode.lower()]
    return None


def detail_argv() -> list[str]:
    """Command listing devices with their modes, zones and active mode."""
    return _client_argv() + ["--list-detailed"]


_MODES_LINE = re.compile(r"^\s*Modes:\s*(.+)$")
_MODE_TOKEN = re.compile(r"\[([^\]]+)\]|'([^']+)'|(\S+)")


def parse_modes(line: str) -> tuple[list[str], str | None]:
    """Parse a `Modes:` line into (all modes, active mode).

    OpenRGB marks the active mode with brackets and quotes any mode whose name
    contains spaces, e.g.::

        Modes: Off [Direct] 'Rainbow Wave' Magic 'Color Cycle' Breathing

    The active mode matters: reading it back is how a write is confirmed to have
    landed, which a zero exit code does not establish — the GPU returned success
    while staying off.
    """
    modes: list[str] = []
    active: str | None = None
    for bracketed, quoted, bare in _MODE_TOKEN.findall(line or ""):
        name = bracketed or quoted or bare
        if not name:
            continue
        # A bracketed token may itself be quoted: [<'Rainbow Wave'>].
        name = name.strip().strip("'")
        modes.append(name)
        if bracketed:
            active = name
    return modes, active


def parse_detailed(output: bytes | str | None) -> list[dict]:
    """Parse `--list-detailed` into per-device dicts.

    Each: {"index", "name", "type", "modes", "active_mode", "zones"}. Duplicate
    names from a rescanned server are collapsed to their first occurrence.
    """
    if isinstance(output, bytes):
        output = output.decode("utf-8", "replace")
    if not output:
        return []

    devices: list[dict] = []
    seen: set[str] = set()
    current: dict | None = None

    for raw in output.splitlines():
        line = raw.rstrip()
        header = _DEVICE_LINE.match(line.strip()) if not line.startswith(" ") else None
        if header and not line.strip().startswith("["):
            name = header.group(2).strip()
            key = name.lower()
            current = None
            if name and key not in seen:
                seen.add(key)
                current = {"index": int(header.group(1)), "name": name,
                           "type": "", "modes": [], "active_mode": None,
                           "zones": []}
                devices.append(current)
            continue
        if current is None:
            continue
        stripped = line.strip()
        if stripped.startswith("Type:"):
            current["type"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("Modes:"):
            match = _MODES_LINE.match(line)
            if match:
                current["modes"], current["active_mode"] = parse_modes(match.group(1))
        elif stripped.startswith("Zones:"):
            current["zones"] = [z for _, z, b in
                                _MODE_TOKEN.findall(stripped.split(":", 1)[1])
                                for z in ([z] if z else [b]) if z]
    return devices


def set_color_argv(device: str | int, mode: str,
                   rgb: tuple[int, int, int] | None = None) -> list[str] | None:
    """Command setting one device's mode, optionally with a colour.

    `device` may be a name or an index. Names are preferred and are what this
    project uses: OpenRGB matches a name substring of 3+ characters, and indices
    shift whenever the server rescans (a rescanned server lists every device
    twice), so a stored index can address the wrong hardware.
    """
    if isinstance(device, bool) or device is None:
        _log.warning("openrgb_bad_device device=%r", device)
        return None
    if isinstance(device, int):
        if device < 0:
            _log.warning("openrgb_bad_index index=%r", device)
            return None
        selector = str(device)
    else:
        selector = str(device).strip()
        if len(selector) < 3:
            # Below OpenRGB's search threshold; it would match nothing or
            # everything rather than failing cleanly.
            _log.warning("openrgb_device_name_too_short name=%r", selector)
            return None

    if not mode or not isinstance(mode, str):
        _log.warning("openrgb_bad_mode mode=%r", mode)
        return None

    argv = _client_argv() + ["--device", selector, "--mode", mode]
    if rgb is not None:
        if not _valid_rgb(rgb):
            _log.warning("openrgb_bad_color rgb=%r", rgb)
            return None
        argv += ["--color", "%02X%02X%02X" % rgb]
    return argv


def _valid_rgb(rgb) -> bool:
    return (
        isinstance(rgb, (tuple, list))
        and len(rgb) == 3
        and all(isinstance(c, int) and not isinstance(c, bool) and 0 <= c <= 255
                for c in rgb)
    )
