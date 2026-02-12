#!/usr/bin/env python3
"""Install/uninstall KWin rule for Foghorn Leghorn always-on-top behavior.

KDE Plasma on Wayland does not reliably honor Qt's WindowStaysOnTopHint.
This script writes a KWin rule to ~/.config/kwinrulesrc that forces
the keep-above property at the compositor level.
"""

import configparser
import subprocess
import sys
from pathlib import Path

WMCLASS = "foghorn-leghorn"
RULE_DESCRIPTION = "Foghorn Leghorn Always On Top"


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


def install_rule():
    config_path = Path.home() / ".config" / "kwinrulesrc"
    config = _read_config(config_path)
    rules = _rules_list(config)

    # Check for existing rule
    target_section = None
    for section in rules:
        if section in config and config[section].get("wmclass") == WMCLASS:
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
    rule["above"] = "true"
    rule["aboverule"] = "2"  # Force

    with open(config_path, "w") as f:
        config.write(f, space_around_delimiters=False)
    print(f"Wrote rule to {config_path}")
    _kwin_reconfigure()


def uninstall_rule():
    config_path = Path.home() / ".config" / "kwinrulesrc"
    if not config_path.exists():
        print("No kwinrulesrc found.")
        return

    config = _read_config(config_path)
    rules = _rules_list(config)

    new_rules = []
    removed = 0
    for section in rules:
        if section in config and config[section].get("wmclass") == WMCLASS:
            print(f"Removing rule in section [{section}]...")
            config.remove_section(section)
            removed += 1
        else:
            new_rules.append(section)

    if removed == 0:
        print("No rules found to remove.")
        return

    config["General"]["rules"] = ",".join(new_rules)
    config["General"]["count"] = str(len(new_rules))

    with open(config_path, "w") as f:
        config.write(f, space_around_delimiters=False)
    print(f"Removed {removed} rule(s).")
    _kwin_reconfigure()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--uninstall":
        uninstall_rule()
    else:
        install_rule()
