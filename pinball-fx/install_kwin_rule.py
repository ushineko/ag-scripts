#!/usr/bin/env python3
"""Install/uninstall the KWin rule pinning gamescope's outer window.

Gamescope on KDE Wayland runs nested — its outer window is one stable client
that KWin places like any other. This rule force-positions it on the chosen
monitor's geometry, force-fullscreen, no border, so the launcher's
gamescope window always lands where Pinball FX expects.

The rule matches on `wmclass=gamescope` AND `title` substring `PinballFX`.
The title narrowing is critical: gamescope's outer xdg-toplevel propagates
the focused inner window's title to its own caption, so when UE-Pinball
sets its window title to "PinballFX", that's what KWin sees on the outer
gamescope surface. Without the title match, ANY gamescope window on the
host (Battle.net launcher, Steam game, `gamescope -- alacritty` for
debugging) would be force-pinned to the portrait monitor, since they all
share `wmclass=gamescope`. KWin re-evaluates rule matches dynamically when
caption changes — verified empirically against Plasma 6 — so concurrent
gamescope windows with other titles are released the moment their caption
fails to match.

Also removes the legacy `Pinball FX Portrait Mode` rule from v1.x of this
tool, so upgrades don't leave dead config behind.
"""

from __future__ import annotations

import argparse
import configparser
import subprocess
import sys
from pathlib import Path

WMCLASS = "gamescope"
TITLE = "PinballFX"
RULE_DESCRIPTION = "Pinball FX Gamescope Placement"
LEGACY_RULE_DESCRIPTION = "Pinball FX Portrait Mode"

KWINRULESRC = Path.home() / ".config" / "kwinrulesrc"


def _kwin_reconfigure() -> None:
    """Trigger KWin to reload its rule configuration via D-Bus."""
    commands = [
        ["qdbus6", "org.kde.KWin", "/KWin", "reconfigure"],
        ["qdbus", "org.kde.KWin", "/KWin", "reconfigure"],
        ["dbus-send", "--session", "--dest=org.kde.KWin",
         "/KWin", "org.kde.KWin.reconfigure"],
    ]
    for cmd in commands:
        try:
            subprocess.run(cmd, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("KWin reconfigured.")
            return
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    print("Warning: could not reload KWin configuration automatically.")


def _read_config(config_path: Path) -> configparser.ConfigParser:
    config = configparser.ConfigParser(strict=False)
    config.optionxform = str  # KWin keys are case-sensitive
    if config_path.exists():
        config.read(config_path)
    if "General" not in config:
        config["General"] = {"count": "0"}
    return config


def _rules_list(config: configparser.ConfigParser) -> list[str]:
    return [r for r in config["General"].get("rules", "").split(",") if r]


def _drop_legacy_rules(config: configparser.ConfigParser) -> int:
    """Remove the v1.x 'Pinball FX Portrait Mode' rule if present. Returns count removed."""
    rules = _rules_list(config)
    keep: list[str] = []
    removed = 0
    for section in rules:
        if section in config and config[section].get("Description") == LEGACY_RULE_DESCRIPTION:
            config.remove_section(section)
            removed += 1
        else:
            keep.append(section)
    if removed:
        config["General"]["rules"] = ",".join(keep)
        config["General"]["count"] = str(len(keep))
    return removed


def install_rule(
    x: int, y: int, width: int, height: int,
    config_path: Path = KWINRULESRC,
    reconfigure: bool = True,
) -> None:
    config = _read_config(config_path)

    legacy_removed = _drop_legacy_rules(config)
    if legacy_removed:
        print(f"Removed {legacy_removed} legacy v1.x rule(s).")

    rules = _rules_list(config)

    target_section: str | None = None
    for section in rules:
        if section in config and config[section].get("Description") == RULE_DESCRIPTION:
            target_section = section
            print(f"Updating existing rule in section [{section}]...")
            break

    if target_section is None:
        current_ids = [int(r) for r in rules if r.isdigit()]
        next_id = max(current_ids + [0]) + 1
        target_section = str(next_id)
        rules.append(target_section)
        config["General"]["rules"] = ",".join(rules)
        config["General"]["count"] = str(len(rules))
        print(f"Creating new rule in section [{target_section}]...")

    if target_section not in config:
        config[target_section] = {}

    rule = config[target_section]
    rule["Description"] = RULE_DESCRIPTION
    rule["wmclass"] = WMCLASS
    rule["wmclassmatch"] = "1"  # Exact match
    rule["title"] = TITLE
    rule["titlematch"] = "2"  # Substring match — caption is dynamic
    rule["position"] = f"{x},{y}"
    rule["positionrule"] = "2"  # Force
    rule["size"] = f"{width},{height}"
    rule["sizerule"] = "2"  # Force
    rule["fullscreen"] = "true"
    rule["fullscreenrule"] = "2"  # Force
    rule["noborder"] = "true"
    rule["noborderrule"] = "2"  # Force

    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        config.write(f, space_around_delimiters=False)
    print(f"Wrote rule to {config_path}")
    if reconfigure:
        _kwin_reconfigure()


def uninstall_rule(
    config_path: Path = KWINRULESRC,
    reconfigure: bool = True,
) -> int:
    """Remove this tool's rule (and any legacy v1.x rule). Returns count removed."""
    if not config_path.exists():
        print("No kwinrulesrc found.")
        return 0

    config = _read_config(config_path)
    rules = _rules_list(config)

    keep: list[str] = []
    removed = 0
    for section in rules:
        if section in config and config[section].get("Description") in {RULE_DESCRIPTION, LEGACY_RULE_DESCRIPTION}:
            print(f"Removing rule in section [{section}]...")
            config.remove_section(section)
            removed += 1
        else:
            keep.append(section)

    if removed == 0:
        print("No matching rules found.")
        return 0

    config["General"]["rules"] = ",".join(keep)
    config["General"]["count"] = str(len(keep))

    with open(config_path, "w") as f:
        config.write(f, space_around_delimiters=False)
    print(f"Removed {removed} rule(s).")
    if reconfigure:
        _kwin_reconfigure()
    return removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install/uninstall the Pinball FX gamescope KWin rule.")
    parser.add_argument("--uninstall", action="store_true", help="Remove the rule instead of installing.")
    parser.add_argument("--x", type=int, help="Window X position.")
    parser.add_argument("--y", type=int, help="Window Y position.")
    parser.add_argument("--width", type=int, help="Window width.")
    parser.add_argument("--height", type=int, help="Window height.")
    args = parser.parse_args(argv)

    if args.uninstall:
        uninstall_rule()
        return 0

    if None in (args.x, args.y, args.width, args.height):
        print("error: --x, --y, --width, --height are required when installing", file=sys.stderr)
        return 2

    install_rule(args.x, args.y, args.width, args.height)
    return 0


if __name__ == "__main__":
    sys.exit(main())
