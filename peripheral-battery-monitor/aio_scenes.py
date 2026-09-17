"""Lighting/LCD scenes bound to numpad shortcuts (spec 025).

A scene is a preset pairing one lighting colour with one LCD mode, applied
together by `Ctrl+Alt+Numpad N`. This module is the pure half: defaults,
validation and normalisation. Applying a scene lives in `aio_section`, because
every device call has to go through `LiquidctlQueue` — a shortcut that drove
liquidctl directly would race the 5 s status poll instead of queueing behind it.

Scene shape::

    {"color": "red",     "lcd": "dashboard"}
    {"color": "#ff8800", "lcd": "liquid"}
    {"color": "off",     "lcd": null}          # LCD untouched
    {"color": null,      "lcd": "/path/x.gif"} # lighting untouched

`color` is a NAMED_COLORS name, `#rrggbb`, `off`, or null.
`lcd` is `dashboard`, `liquid`, a path to an image or GIF, or null.

Brightness is deliberately not part of a scene. A shortcut that unexpectedly
dimmed the screen would be a surprise, and brightness is a standing preference
rather than part of a look.
"""

from __future__ import annotations

import logging
import os

import aio_color

_log = logging.getLogger(__name__)

SLOT_MIN = 1
SLOT_MAX = 9

LCD_DASHBOARD = "dashboard"
LCD_LIQUID = "liquid"
_LCD_KEYWORDS = (LCD_DASHBOARD, LCD_LIQUID)

SETTINGS_KEY = "aio_scenes"

# Seeded defaults. Six solid colours on the live dashboard cover the common
# case; 7 hands the LCD back to the firmware readout, 8 is an example of a scene
# driving an animated GIF, and 9 is "everything off" as an easy way out.
DEFAULT_SCENES: dict[str, dict] = {
    "1": {"color": "red", "lcd": LCD_DASHBOARD},
    "2": {"color": "green", "lcd": LCD_DASHBOARD},
    "3": {"color": "blue", "lcd": LCD_DASHBOARD},
    "4": {"color": "purple", "lcd": LCD_DASHBOARD},
    "5": {"color": "cyan", "lcd": LCD_DASHBOARD},
    "6": {"color": "orange", "lcd": LCD_DASHBOARD},
    "7": {"color": "white", "lcd": LCD_LIQUID},
    "8": {"color": "magenta",
          "lcd": os.path.expanduser("~/Pictures/CappelixImages/bluemarble.gif")},
    "9": {"color": "off", "lcd": LCD_LIQUID},
}


def valid_slot(slot) -> bool:
    """True for an integer (or integer-ish string) in the bindable range.

    Floats are rejected rather than truncated: `int(1.5)` is 1, so accepting it
    would silently fire the wrong scene.
    """
    if isinstance(slot, bool):
        return False
    if isinstance(slot, float) and not slot.is_integer():
        return False
    try:
        n = int(slot)
    except (TypeError, ValueError):
        return False
    return SLOT_MIN <= n <= SLOT_MAX


def describe_problem(scene) -> str | None:
    """Why this scene is unusable, or None when it is fine.

    Returns a reason rather than raising so a bad entry in a hand-edited
    settings file logs something actionable and is skipped, instead of taking
    down the shortcut or the app.
    """
    if not isinstance(scene, dict):
        return f"not an object: {type(scene).__name__}"

    unknown = set(scene) - {"color", "lcd"}
    if unknown:
        return f"unknown key(s): {', '.join(sorted(unknown))}"

    colour = scene.get("color")
    if colour is not None:
        if not isinstance(colour, str):
            return f"color must be a string or null, got {type(colour).__name__}"
        if aio_color.parse_color(colour) is None:
            return f"unparseable color: {colour!r}"

    lcd = scene.get("lcd")
    if lcd is not None:
        if not isinstance(lcd, str):
            return f"lcd must be a string or null, got {type(lcd).__name__}"
        if lcd not in _LCD_KEYWORDS and not lcd.startswith(("/", "~")):
            return (f"lcd must be one of {_LCD_KEYWORDS}, or an absolute path; "
                    f"got {lcd!r}")

    if colour is None and lcd is None:
        return "scene changes nothing (both color and lcd are null)"
    return None


def normalise(scene: dict) -> dict:
    """A validated scene with its path expanded. Assumes it already passed."""
    lcd = scene.get("lcd")
    if isinstance(lcd, str) and lcd.startswith("~"):
        lcd = os.path.expanduser(lcd)
    return {"color": scene.get("color"), "lcd": lcd}


def load(settings: dict) -> dict[str, dict]:
    """Scenes from settings, falling back per-slot to the defaults.

    Per-slot rather than all-or-nothing: one malformed hand-edited entry should
    cost that slot, not the other eight.
    """
    stored = settings.get(SETTINGS_KEY)
    if not isinstance(stored, dict):
        stored = {}

    scenes: dict[str, dict] = {}
    for slot in range(SLOT_MIN, SLOT_MAX + 1):
        key = str(slot)
        scene = stored.get(key, DEFAULT_SCENES.get(key))
        problem = describe_problem(scene)
        if problem is not None:
            _log.warning("scene_invalid slot=%s problem=%s", key, problem)
            fallback = DEFAULT_SCENES.get(key)
            if describe_problem(fallback) is not None:
                continue
            scene = fallback
        scenes[key] = normalise(scene)
    return scenes


def seed(settings: dict) -> bool:
    """Write the defaults into settings if absent. True when it changed.

    Never overwrites an existing set: the whole point of storing scenes in the
    settings file is that the user can retune them.
    """
    if isinstance(settings.get(SETTINGS_KEY), dict) and settings[SETTINGS_KEY]:
        return False
    settings[SETTINGS_KEY] = {k: dict(v) for k, v in DEFAULT_SCENES.items()}
    return True


def summarise(scene: dict) -> str:
    """One-line description, for logs and menu labels."""
    colour = scene.get("color") or "—"
    lcd = scene.get("lcd") or "—"
    if isinstance(lcd, str) and lcd not in _LCD_KEYWORDS:
        lcd = os.path.basename(lcd)
    return f"{colour} / {lcd}"
