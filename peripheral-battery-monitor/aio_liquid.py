"""Kraken LCD control (specs 021, 022, 023).

Builds `liquidctl` command lines for the NZXT Kraken Elite V2's LCD and
validates their arguments. Pure argv construction: nothing here runs a process,
opens a device, or touches Qt. `aio_section.py` executes what this returns,
through a queue that serialises every liquidctl invocation.

**Colour is deliberately not here.** Specs 021 and 022 built an RGB path on
liquidctl before establishing that liquidctl exposes *no* colour channels for
this cooler — every `set <channel> color` returns "operation not supported by
the device". OpenRGB drives the Kraken's lighting (and the radiator fans, whose
RGB daisy-chains into it) along with every other lit device; see `rgb_openrgb`.
Spec 023 removed the liquidctl colour code rather than leave a second backend
that cannot work on this hardware.

Two device facts shape what remains:

1. **One hidraw node, many callers.** The status poll runs `liquidctl status`
   every 5 s against the same device these writes address, and the OpenRGB
   server holds a handle too. Two concurrent liquidctl processes on one node is
   a corruption risk, so every call built here is serialised by the caller —
   `LiquidctlQueue` does that; this module cannot.
2. **`set_screen` is marked Unstable upstream** and the LCD's bucket-switching
   fails intermittently under repeated writes (liquidctl#774). Keeping argv
   construction in one place makes an upstream change a single-file fix.

The LCD is 640x640. liquidctl resizes whatever image it is given, but rendering
at native size avoids a resample.
"""

from __future__ import annotations

import logging
import os

_log = logging.getLogger(__name__)

LIQUIDCTL_BIN = os.environ.get("LIQUIDCTL_BIN", "liquidctl")
LIQUIDCTL_MATCH = os.environ.get("LIQUIDCTL_MATCH", "kraken")

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


def _base_argv() -> list[str]:
    return [LIQUIDCTL_BIN, "--match", LIQUIDCTL_MATCH]


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

    The safe fallback: the firmware draws it, so it needs no host traffic and
    cannot hit the bucket-switch failure that repeated image pushes can.
    """
    return _base_argv() + ["set", LCD_CHANNEL, "screen", LCD_MODE_LIQUID]


def lcd_static_argv(path: str) -> list[str] | None:
    """Display a still image. liquidctl resizes it to 640x640 itself."""
    if not path or not isinstance(path, str):
        return None
    return _base_argv() + ["set", LCD_CHANNEL, "screen", LCD_MODE_STATIC, path]


def lcd_gif_argv(path: str) -> list[str] | None:
    """Play an animated GIF."""
    if not path or not isinstance(path, str):
        return None
    return _base_argv() + ["set", LCD_CHANNEL, "screen", LCD_MODE_GIF, path]
