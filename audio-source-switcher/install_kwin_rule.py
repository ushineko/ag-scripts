#!/usr/bin/env python3
"""Install/uninstall KWin rules for the volume OSD.

KDE Plasma on Wayland gives clients no control over absolute window position or
stacking, and its default placement is not centered. This script writes one KWin
rule per screen that forces the OSD to a centered position, keeps it above other
windows, and removes its border / taskbar / switcher / pager presence.

The OSD is matched by its per-screen window title (all app windows share one
Wayland app_id, so the title is the only reliable per-window discriminator).

Usage:
    install_kwin_rule.py              # install/update rules for current screens
    install_kwin_rule.py --uninstall  # remove all OSD rules
"""

import configparser
import subprocess
import sys
from pathlib import Path

# Make the audio_source_switcher package importable when run from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from audio_source_switcher.gui.osd import (  # noqa: E402
    OSD_WIDTH,
    OSD_HEIGHT,
    OSD_TITLE_BASE,
    osd_title_for_screen,
)

DESCRIPTION_PREFIX = "Audio Source Switcher Volume OSD"
CONFIG_PATH = Path.home() / ".config" / "kwinrulesrc"

# KWin rule policy: 2 = Force.
FORCE = "2"
# KWin string-match policy: 1 = Exact.
MATCH_EXACT = "1"


def _kwin_reconfigure():
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


def _read_config() -> configparser.ConfigParser:
    config = configparser.ConfigParser(strict=False)
    config.optionxform = str  # KWin keys are case-sensitive
    if CONFIG_PATH.exists():
        config.read(CONFIG_PATH)
    if "General" not in config:
        config["General"] = {"count": "0"}
    return config


def _rules_list(config: configparser.ConfigParser) -> list[str]:
    return [r for r in config["General"].get("rules", "").split(",") if r]


def _write_config(config: configparser.ConfigParser):
    with open(CONFIG_PATH, "w") as f:
        config.write(f, space_around_delimiters=False)
    print(f"Wrote {CONFIG_PATH}")


def _apply_osd_rule_keys(rule, title: str, x: int, y: int):
    rule["Description"] = f"{DESCRIPTION_PREFIX} @ {x},{y}"
    rule["title"] = title
    rule["titlematch"] = MATCH_EXACT
    rule["position"] = f"{x},{y}"
    rule["positionrule"] = FORCE
    rule["above"] = "true"
    rule["aboverule"] = FORCE
    rule["noborder"] = "true"
    rule["noborderrule"] = FORCE
    rule["skiptaskbar"] = "true"
    rule["skiptaskbarrule"] = FORCE
    rule["skipswitcher"] = "true"
    rule["skipswitcherrule"] = FORCE
    rule["skippager"] = "true"
    rule["skippagerrule"] = FORCE


def _screen_osd_targets() -> list[tuple[str, int, int]]:
    """For each screen, return (title, centered_top_left_x, centered_top_left_y)."""
    app = QApplication.instance() or QApplication(sys.argv)
    targets = []
    for screen in app.screens():
        geo = screen.geometry()
        title = osd_title_for_screen(geo.x(), geo.y())
        x = geo.x() + (geo.width() - OSD_WIDTH) // 2
        y = geo.y() + (geo.height() - OSD_HEIGHT) // 2
        targets.append((title, x, y))
    return targets


def install_rules():
    config = _read_config()
    rules = _rules_list(config)

    for title, x, y in _screen_osd_targets():
        # Find an existing OSD rule for this title.
        target_section = None
        for section in rules:
            if section in config and config[section].get("title") == title \
                    and config[section].get("Description", "").startswith(DESCRIPTION_PREFIX):
                target_section = section
                print(f"Updating OSD rule for '{title}' in section [{section}]...")
                break

        if target_section is None:
            current_ids = [int(r) for r in rules if r.isdigit()]
            next_id = max(current_ids + [0]) + 1
            target_section = str(next_id)
            rules.append(target_section)
            print(f"Creating OSD rule for '{title}' in section [{target_section}]...")

        if target_section not in config:
            config[target_section] = {}
        _apply_osd_rule_keys(config[target_section], title, x, y)

    config["General"]["rules"] = ",".join(rules)
    config["General"]["count"] = str(len(rules))
    _write_config(config)
    _kwin_reconfigure()


def uninstall_rules():
    if not CONFIG_PATH.exists():
        print("No kwinrulesrc found.")
        return

    config = _read_config()
    rules = _rules_list(config)

    kept, removed = [], 0
    for section in rules:
        desc = config[section].get("Description", "") if section in config else ""
        title = config[section].get("title", "") if section in config else ""
        if desc.startswith(DESCRIPTION_PREFIX) or title.startswith(OSD_TITLE_BASE):
            print(f"Removing OSD rule in section [{section}]...")
            config.remove_section(section)
            removed += 1
        else:
            kept.append(section)

    if removed == 0:
        print("No OSD rules found to remove.")
        return

    config["General"]["rules"] = ",".join(kept)
    config["General"]["count"] = str(len(kept))
    _write_config(config)
    print(f"Removed {removed} OSD rule(s).")
    _kwin_reconfigure()


if __name__ == "__main__":
    if "--uninstall" in sys.argv:
        uninstall_rules()
    else:
        install_rules()
