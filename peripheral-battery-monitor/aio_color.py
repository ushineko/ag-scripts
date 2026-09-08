"""AIO RGB control.

Builds the request sequences that set a solid colour, an RGB effect, or a
brightness level on an OpenLinkHub-managed device, and applies them
synchronously for CLI use. The Qt section reuses the same builders and executes
them over QNetworkAccessManager.

This is the one part of the AIO feature that writes. Speed control stays absent
on purpose: Commander ST firmware 2.x silently discards fan and pump duty writes
from both OpenLinkHub and liquidctl, so a speed control would report success and
change nothing. RGB writes do land. See
~/git/sysadmin/runbooks/aio-coolant-overtemp-and-commander-st-fan-control.md.

Four traps, all of which fail silently rather than returning an error:

1. Colour lives in the device's per-channel `RGBOverride`, not in the `static`
   profile. Editing the profile applies cleanly and changes no LED. The order
   that works is: set the override, then select `static`.
2. Selecting an animated effect requires the override *disabled* first, or it
   masks the animation.
3. `Brightness: 0` blacks every LED out, after which colour commands succeed and
   nothing lights up.
4. Profile names map to effect implementations in Go and cannot be invented. An
   unknown name returns "Unable to change device RGB profile".

Requests are returned as ordered *stages*. Every request within a stage is
independent, and a stage may only be dispatched once the previous one has
completed. That is what encodes trap 1 and trap 2.
"""

from __future__ import annotations

import json
import logging
import sys
import urllib.error
import urllib.request

from aio_reader import DEFAULT_BASE_URL, DEFAULT_TIMEOUT, decode_payload

_log = logging.getLogger(__name__)

PATH_SET_OVERRIDE = "color/setOverride"
PATH_COLOR = "color"
PATH_BRIGHTNESS = "brightness"
PATH_PROFILES = "color/"

# The `static` profile is what renders an override as a solid colour.
PROFILE_STATIC = "static"
# Both are reachable from the colour menu, so they are filtered out of the
# effect list to avoid offering the same thing twice.
NON_EFFECT_PROFILES = frozenset({PROFILE_STATIC, "off"})

# Brightness levels the daemon accepts. 0 means "use the RGB profile's own
# brightness", which in practice renders black — see trap 3.
BRIGHTNESS_MIN = 0
BRIGHTNESS_MAX = 3
BRIGHTNESS_REPAIR = 3

# Effect animation speed for the override payload. 4 matches aio-color.sh.
OVERRIDE_SPEED = 4

# Names and values identical to aio-color.sh, so both tools mean the same thing
# by "teal".
NAMED_COLORS: dict[str, tuple[int, int, int]] = {
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "cyan": (0, 255, 255),
    "magenta": (255, 0, 255),
    "white": (255, 255, 255),
    "orange": (255, 85, 0),
    "purple": (128, 0, 255),
    "pink": (255, 0, 128),
    "lime": (128, 255, 0),
    "teal": (0, 255, 128),
    "off": (0, 0, 0),
}


def parse_color(value: str) -> tuple[int, int, int] | None:
    """Resolve a colour name or `#rrggbb` string. None if neither."""
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if not text:
        return None
    if text in NAMED_COLORS:
        return NAMED_COLORS[text]
    hex_part = text[1:] if text.startswith("#") else text
    if len(hex_part) != 6:
        return None
    try:
        return (
            int(hex_part[0:2], 16),
            int(hex_part[2:4], 16),
            int(hex_part[4:6], 16),
        )
    except ValueError:
        return None


def _color_payload(rgb: tuple[int, int, int]) -> dict:
    return {"red": rgb[0], "green": rgb[1], "blue": rgb[2]}


def brightness_request(device_id: str, level: int) -> tuple[str, dict]:
    """One brightness request. Raises on a level the daemon would reject."""
    if not isinstance(level, int) or isinstance(level, bool):
        raise ValueError(f"brightness must be an int, got {level!r}")
    if not BRIGHTNESS_MIN <= level <= BRIGHTNESS_MAX:
        raise ValueError(f"brightness must be {BRIGHTNESS_MIN}-{BRIGHTNESS_MAX}, got {level}")
    return (PATH_BRIGHTNESS, {"deviceId": device_id, "brightness": level})


def _brightness_repair_stage(device_id: str, brightness: int | None) -> list[list]:
    """A leading stage that lifts brightness off 0, or nothing.

    Only level 0 is touched. There every LED is already dark, so a colour
    request cannot be satisfied without it (trap 3). Levels 1-3 are the user's
    deliberate choice and are left alone.
    """
    if brightness != 0:
        return []
    _log.info("aio_rgb_brightness_repair from=0 to=%s", BRIGHTNESS_REPAIR)
    return [[brightness_request(device_id, BRIGHTNESS_REPAIR)]]


def _override_stage(device_id: str, channels: list[int], rgb: tuple[int, int, int],
                    enabled: bool) -> list:
    color = _color_payload(rgb)
    return [
        (
            PATH_SET_OVERRIDE,
            {
                "deviceId": device_id,
                "channelId": channel,
                "subDeviceId": 0,
                "enabled": enabled,
                "startColor": color,
                "endColor": color,
                "speed": OVERRIDE_SPEED,
            },
        )
        for channel in channels
    ]


def _profile_stage(device_id: str, channels: list[int], profile: str) -> list:
    return [
        (PATH_COLOR, {"deviceId": device_id, "channelId": channel, "profile": profile})
        for channel in channels
    ]


def solid_requests(device_id: str, channels: list[int], rgb: tuple[int, int, int],
                   *, brightness: int | None = None) -> list[list]:
    """Stages that set every channel to one solid colour.

    Override first, then `static`. Reversing these is the documented silent
    failure: the profile applies, and no LED changes.
    """
    return [
        *_brightness_repair_stage(device_id, brightness),
        _override_stage(device_id, channels, rgb, enabled=True),
        _profile_stage(device_id, channels, PROFILE_STATIC),
    ]


def effect_requests(device_id: str, channels: list[int], profile: str,
                    *, brightness: int | None = None) -> list[list]:
    """Stages that select an animated effect on every channel.

    The override is disabled first or it masks the animation (trap 2).
    """
    return [
        *_brightness_repair_stage(device_id, brightness),
        _override_stage(device_id, channels, (0, 0, 0), enabled=False),
        _profile_stage(device_id, channels, profile),
    ]


def effects_for_device(profiles_json: dict | None, device_id: str | None) -> list[str]:
    """Effect names this device actually implements, from `GET /api/color/`.

    Per-device, unlike the global `database/rgb.json` the shell script reads:
    that file lists profiles this cooler does not implement, and selecting one
    is trap 4.
    """
    if not isinstance(profiles_json, dict) or not device_id:
        return []
    entry = (profiles_json.get("data") or {}).get(device_id)
    if not isinstance(entry, dict):
        return []
    profiles = entry.get("profiles")
    if not isinstance(profiles, dict):
        return []
    return sorted(name for name in profiles if name not in NON_EFFECT_PROFILES)


def _post(base_url: str, path: str, payload: dict, timeout: float) -> bool:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/{path}",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            body = decode_payload(resp.read())
    except (urllib.error.URLError, OSError) as e:
        _log.warning("aio_rgb_post_failed path=%s err=%s", path, e)
        return False
    if not isinstance(body, dict) or body.get("status") != 1:
        _log.warning("aio_rgb_post_rejected path=%s body=%s", path, body)
        return False
    return True


def apply_stages(stages: list[list], base_url: str = DEFAULT_BASE_URL,
                 timeout: float = DEFAULT_TIMEOUT) -> tuple[int, int]:
    """Apply stages in order, synchronously. Returns (ok, failed).

    Used by the CLI and tests. The Qt section runs the same stages over
    QNetworkAccessManager instead, so it never blocks the GUI thread.
    """
    ok = failed = 0
    for stage in stages:
        for path, payload in stage:
            if _post(base_url, path, payload, timeout):
                ok += 1
            else:
                failed += 1
    return ok, failed


def _read_target(base_url: str, timeout: float) -> tuple[str | None, list[int], int | None]:
    import aio_reader

    snapshot = aio_reader.read_aio(base_url, timeout)
    return snapshot["device_id"], snapshot["rgb_channels"], snapshot["brightness"]


def main(argv: list[str]) -> int:
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.DEBUG if "--debug" in argv else logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )
    args = [a for a in argv if a != "--debug"]
    base = DEFAULT_BASE_URL
    device_id, channels, brightness = _read_target(base, DEFAULT_TIMEOUT)

    if "--list" in args or not args:
        print("Colours:", " ".join(sorted(NAMED_COLORS)))
        profiles = decode_payload(_get(f"{base.rstrip('/')}/{PATH_PROFILES}", DEFAULT_TIMEOUT))
        print("Effects:", " ".join(effects_for_device(profiles, device_id)) or "(unknown)")
        print(f"Device: {device_id} channels={channels} brightness={brightness}")
        return 0

    if not device_id or not channels:
        print("no OpenLinkHub device with RGB channels", file=sys.stderr)
        return 1

    if args[0] == "--brightness":
        if len(args) < 2:
            print("--brightness needs a level 0-3", file=sys.stderr)
            return 2
        ok, failed = apply_stages([[brightness_request(device_id, int(args[1]))]], base)
    else:
        rgb = parse_color(args[0])
        if rgb is not None:
            stages = solid_requests(device_id, channels, rgb, brightness=brightness)
        else:
            stages = effect_requests(device_id, channels, args[0], brightness=brightness)
        ok, failed = apply_stages(stages, base)

    print(f"{ok} ok, {failed} failed")
    return 0 if failed == 0 else 1


def _get(url: str, timeout: float) -> bytes | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.read()
    except (urllib.error.URLError, OSError) as e:
        _log.debug("aio_rgb_get_failed url=%s err=%s", url, e)
        return None


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
