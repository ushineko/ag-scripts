"""Kraken RGB and LCD control (spec 021).

Builds `liquidctl` command lines for the NZXT Kraken Elite V2 and validates
their arguments. Pure argv construction: nothing here runs a process, opens a
device, or touches Qt. `aio_section.py` executes what this module returns,
through a queue that serialises every liquidctl invocation — see the note on
contention below.

This replaces `aio_color.py` for the current cooler. That module still describes
an OpenLinkHub RGB device correctly and is retained untouched; the menu picks a
backend by which of the two reports a usable target.

Two device facts drive the shape of this module:

1. **One hidraw node, many callers.** The spec 020 status poll runs
   `liquidctl status` every 5 seconds against the same device these writes
   address. Two concurrent liquidctl processes on one hidraw node is a
   corruption risk, so every call built here is expected to be serialised by the
   caller. This module cannot enforce that; `LiquidctlQueue` does.
2. **`set_screen` is marked Unstable upstream** and the LCD's own
   bucket-switching is known to fail intermittently under repeated writes
   (liquidctl#774). Keeping all argv construction in one place means a liquidctl
   interface change is a single-file fix.

The LCD is 640x640. liquidctl resizes whatever image it is given, but rendering
at native size avoids a resample.
"""

from __future__ import annotations

import logging
import os

import aio_color

_log = logging.getLogger(__name__)

# Reuse spec 019's colour vocabulary verbatim so the menu reads identically.
NAMED_COLORS = aio_color.NAMED_COLORS

LIQUIDCTL_BIN = os.environ.get("LIQUIDCTL_BIN", "liquidctl")
LIQUIDCTL_MATCH = os.environ.get("LIQUIDCTL_MATCH", "kraken")

# Colour channel names the Kraken driver family defines. Whether a *particular*
# device implements any of them is a separate question, answered by
# `color_channels()` below — do not assume this tuple is available.
COLOR_CHANNELS = ("sync", "ring", "logo", "external")
DEFAULT_COLOR_CHANNEL = "sync"

# Caches for the capability probes; None means "not yet probed".
_color_channels_cache: list[str] | None = None
_color_devices_cache: list[dict] | None = None


def is_animated(path: str) -> bool:
    """True when `path` holds more than one frame.

    Decided by reading the file, not by its extension: a single-frame `.gif` is
    better served by the cheaper `static` path, and an animated file that someone
    named `.png` should still animate. Any failure to read reports False, so an
    unreadable file falls back to `static` and fails there with liquidctl's own
    error rather than raising here.

    Pillow is liquidctl's dependency, already installed wherever liquidctl can
    show an image at all, so importing it costs this project nothing.
    """
    if not path or not isinstance(path, str):
        return False
    try:
        from PIL import Image

        with Image.open(path) as image:
            return getattr(image, "n_frames", 1) > 1
    except Exception as e:
        _log.debug("animated_probe_failed path=%s err=%s", path, e)
        return False


def color_devices(refresh: bool = False) -> list[dict]:
    """Every liquidctl device reporting colour channels.

    Spec 021 only inspected Kraken instances and hardcoded `--match kraken`, so
    an NZXT RGB controller could never have been found even once attached. This
    scans every driver and returns each device's own match token, so colour
    capability appears by itself when colour hardware does.

    Each entry: {"match", "description", "channels"}. The match token is derived
    from the description and is what `--match` needs to select that device.
    """
    global _color_devices_cache
    if _color_devices_cache is not None and not refresh:
        return [dict(d) for d in _color_devices_cache]

    devices: list[dict] = []
    try:
        from liquidctl.driver import find_liquidctl_devices

        for device in find_liquidctl_devices():
            channels = [c for c in (getattr(device, "_color_channels", None) or {})]
            if not channels:
                continue
            description = getattr(device, "description", "") or "device"
            devices.append({
                "match": None,          # assigned below, once all are known
                "address": getattr(device, "address", None),
                "description": description,
                "channels": channels,
            })
        _assign_match_tokens(devices)
    except Exception as e:
        _log.debug("color_device_probe_failed err=%s", e)
        devices = []

    _color_devices_cache = devices
    return [dict(d) for d in devices]


def _assign_match_tokens(devices: list[dict]):
    """Give each device a `--match` token that selects it and nothing else.

    liquidctl matches a case-insensitive substring of the description, so a
    token must be checked for uniqueness against *every* device, not just
    chosen for being distinctive-looking. "rgb" reads like a good token for an
    RGB controller right up until you notice the cooler is called
    "NZXT Kraken 2024 Elite RGB" — that token would address both, and the write
    would land on whichever liquidctl enumerated first.

    Tries single words first, then the full description, which liquidctl always
    matches exactly one of.
    """
    descriptions = [d["description"].lower() for d in devices]

    def unique(token: str, index: int) -> bool:
        return sum(1 for d in descriptions if token in d) == 1 and \
            token in descriptions[index]

    for i, device in enumerate(devices):
        # Only real words: punctuation like "&" can be technically unique while
        # being useless in a log line and fragile against a renamed product.
        words = [w for w in
                 (x.strip("()").lower() for x in device["description"].split())
                 if len(w) >= 3 and any(c.isalnum() for c in w)]
        chosen = next((w for w in words if unique(w, i)), None)
        if chosen is None:
            # No single word distinguishes it; a two-word run usually does.
            for a, b in zip(words, words[1:]):
                pair = f"{a} {b}"
                if unique(pair, i):
                    chosen = pair
                    break
        device["match"] = chosen or device["description"].lower()
        # Substring matching cannot always disambiguate: "NZXT HUE 2" is a
        # substring of "NZXT HUE 2 Ambient", so no token selects the shorter
        # one. Flag those so the caller addresses them exactly instead.
        device["ambiguous"] = chosen is None and not unique(
            device["description"].lower(), i)


def color_channels(refresh: bool = False) -> list[str]:
    """Colour channels *this* device actually implements. Often empty.

    Measured, not assumed. `_COLOR_CHANNELS_KRAKENX` is a class-level table
    shared across the Kraken family; the driver assigns each instance its own
    `_color_channels`, and on the NZXT Kraken 2024 Elite (`1e71:3012`) that
    instance map is **empty**. Every `set <channel> color` against this unit
    returns "operation not supported by the device", on all four channel names.

    So the menu must gate on this rather than on the family table, or it offers
    controls that cannot work. The probe enumerates HID devices but never calls
    `connect()`, so it costs ~0.09 s and does not contend for the hidraw node.
    """
    global _color_channels_cache
    if _color_channels_cache is not None and not refresh:
        return list(_color_channels_cache)

    channels: list[str] = []
    try:
        from liquidctl.driver import find_liquidctl_devices
        from liquidctl.driver.kraken3 import KrakenX3

        for device in find_liquidctl_devices():
            if isinstance(device, KrakenX3):  # KrakenZ3 subclasses this
                channels = [c for c in (getattr(device, "_color_channels", None) or {})]
                break
    except Exception as e:
        _log.debug("kraken_color_probe_failed err=%s", e)
        channels = []

    _color_channels_cache = channels
    return list(channels)


def color_supported() -> bool:
    """True when this device implements at least one colour channel."""
    return bool(color_channels())


LCD_CHANNEL = "lcd"
LCD_RESOLUTION = (640, 640)
LCD_MODE_LIQUID = "liquid"
LCD_MODE_STATIC = "static"
LCD_MODE_GIF = "gif"
LCD_MODE_BRIGHTNESS = "brightness"
LCD_MODE_ORIENTATION = "orientation"

BRIGHTNESS_MIN = 0
BRIGHTNESS_MAX = 100
ORIENTATIONS = (0, 90, 180, 270)

# Mode used for a plain solid colour.
MODE_FIXED = "fixed"
MODE_OFF = "off"

# Effects not worth listing in a menu: `fixed` is the Colour submenu's job and
# `off` has its own entry, while `super-*` modes take up to 40 colours and have
# no sensible one-click form.
_MENU_EXCLUDED_MODES = frozenset({MODE_FIXED, MODE_OFF, "super-fixed", "super-breathing"})


def _color_modes() -> dict[str, tuple]:
    """The driver's own mode table, or {} when liquidctl is not importable.

    Imported lazily and defensively: the app must start on a machine without
    liquidctl, and this is the only place that needs the library rather than the
    binary. Reading the driver's table rather than hardcoding a list keeps the
    menu correct across liquidctl releases.
    """
    try:
        from liquidctl.driver.kraken3 import _COLOR_MODES
    except Exception as e:  # ImportError, or an upstream rename
        _log.debug("kraken_color_modes_unavailable err=%s", e)
        return {}
    return dict(_COLOR_MODES)


def effect_modes() -> dict[str, list[str]]:
    """Menu-ready effects, split by whether they take a colour.

    Returns {"plain": [...], "colored": [...]}. `plain` modes ignore colours
    entirely (rainbow and spectrum variants); `colored` modes need at least one,
    and the menu pairs them with a chosen colour.
    """
    plain: list[str] = []
    colored: list[str] = []
    for name, spec in _color_modes().items():
        if name in _MENU_EXCLUDED_MODES:
            continue
        try:
            mincolors = spec[3]
        except (TypeError, IndexError):
            continue
        (plain if mincolors == 0 else colored).append(name)
    return {"plain": sorted(plain), "colored": sorted(colored)}


def is_known_mode(mode: str) -> bool:
    """True when the driver advertises this colour mode.

    Falls back to accepting `fixed`/`off` when the table is unavailable, so a
    machine with the binary but not the library can still set a solid colour.
    """
    modes = _color_modes()
    if not modes:
        return mode in (MODE_FIXED, MODE_OFF)
    return mode in modes


def _base_argv(match: str | None = None, address: str | None = None) -> list[str]:
    """Base command, optionally targeting a device other than the cooler.

    `--address` selects exactly one device and is used when no substring can
    distinguish this device from another; `--match` is preferred otherwise
    because it survives a replug, which an address does not.
    """
    if address:
        return [LIQUIDCTL_BIN, "--address", address]
    return [LIQUIDCTL_BIN, "--match", match or LIQUIDCTL_MATCH]


def device_selector(device: dict) -> dict:
    """Keyword arguments selecting `device`, from a `color_devices()` entry."""
    if device.get("ambiguous") and device.get("address"):
        return {"address": device["address"]}
    return {"match": device.get("match")}


def _hex(rgb: tuple[int, int, int]) -> str:
    return "%02x%02x%02x" % rgb


def color_argv(
    channel: str,
    mode: str,
    colors: list[tuple[int, int, int]] | None = None,
    match: str | None = None,
    address: str | None = None,
) -> list[str] | None:
    """`liquidctl set <channel> color <mode> [hex...]`, or None if invalid.

    Returning None rather than raising keeps menu callbacks total: a bad
    selection logs and does nothing instead of propagating into the Qt event
    loop.
    """
    # Validate against the channels this device actually reports when we know
    # them. COLOR_CHANNELS is only the Kraken family's naming — an NZXT RGB
    # controller uses led1/led2/sync, and rejecting those would make
    # multi-device support impossible.
    known = [c for d in color_devices() for c in d["channels"]]
    allowed = known or list(COLOR_CHANNELS)
    if channel not in allowed:
        _log.warning("color_bad_channel channel=%s allowed=%s", channel, allowed)
        return None
    if not is_known_mode(mode):
        _log.warning("kraken_bad_mode mode=%s", mode)
        return None

    argv = _base_argv(match, address) + ["set", channel, "color", mode]
    for rgb in colors or []:
        if not _valid_rgb(rgb):
            _log.warning("kraken_bad_color color=%r", rgb)
            return None
        argv.append(_hex(rgb))
    return argv


def _valid_rgb(rgb) -> bool:
    return (
        isinstance(rgb, (tuple, list))
        and len(rgb) == 3
        and all(isinstance(c, int) and not isinstance(c, bool) and 0 <= c <= 255 for c in rgb)
    )


def solid_color_argv(channel: str, value: str, match: str | None = None,
                     address: str | None = None) -> list[str] | None:
    """A named colour or `#rrggbb` as a solid fill. `off` blanks the channel."""
    rgb = aio_color.parse_color(value)
    if rgb is None:
        _log.warning("kraken_unparseable_color value=%r", value)
        return None
    if rgb == (0, 0, 0):
        return color_argv(channel, MODE_OFF, match=match, address=address)
    return color_argv(channel, MODE_FIXED, [rgb], match=match, address=address)


def lcd_brightness_argv(level: int) -> list[str] | None:
    if not isinstance(level, int) or isinstance(level, bool):
        return None
    if not BRIGHTNESS_MIN <= level <= BRIGHTNESS_MAX:
        _log.warning("kraken_bad_brightness level=%r", level)
        return None
    return _base_argv() + ["set", LCD_CHANNEL, "screen", LCD_MODE_BRIGHTNESS, str(level)]


def lcd_orientation_argv(degrees: int) -> list[str] | None:
    if degrees not in ORIENTATIONS:
        _log.warning("kraken_bad_orientation degrees=%r", degrees)
        return None
    return _base_argv() + ["set", LCD_CHANNEL, "screen", LCD_MODE_ORIENTATION, str(degrees)]


def lcd_liquid_argv() -> list[str]:
    """Firmware-rendered coolant temperature.

    This is the safe fallback: the firmware draws it, so it needs no host
    traffic and cannot hit the bucket-switch failure that repeated image pushes
    can.
    """
    return _base_argv() + ["set", LCD_CHANNEL, "screen", LCD_MODE_LIQUID]


def lcd_static_argv(path: str) -> list[str] | None:
    """Display an image file. liquidctl resizes it to 640x640 itself."""
    if not path or not isinstance(path, str):
        return None
    return _base_argv() + ["set", LCD_CHANNEL, "screen", LCD_MODE_STATIC, path]


def lcd_gif_argv(path: str) -> list[str] | None:
    if not path or not isinstance(path, str):
        return None
    return _base_argv() + ["set", LCD_CHANNEL, "screen", LCD_MODE_GIF, path]
