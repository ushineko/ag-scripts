#!/usr/bin/env python3
"""Install/uninstall KWin rules for DHCP Lease Monitor."""

from __future__ import annotations

import configparser
from pathlib import Path
import subprocess
import sys


APP_WMCLASS = "dhcp-lease-monitor"
RULE_DESCRIPTION = "DHCP Lease Monitor Always On Top"
KWIN_RULES_PATH = Path.home() / ".config" / "kwinrulesrc"


def run_kwin_reconfigure() -> None:
    commands = [
        ["qdbus6", "org.kde.KWin", "/KWin", "reconfigure"],
        ["qdbus", "org.kde.KWin", "/KWin", "reconfigure"],
        ["dbus-send", "--session", "--dest=org.kde.KWin", "/KWin", "org.kde.KWin.reconfigure"],
    ]
    for cmd in commands:
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("KWin reconfigured.")
            return
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    print("Warning: could not automatically reload KWin config.")


def load_config() -> configparser.ConfigParser:
    config = configparser.ConfigParser(strict=False)
    config.optionxform = str
    if KWIN_RULES_PATH.exists():
        config.read(KWIN_RULES_PATH)
    if "General" not in config:
        config["General"] = {"count": "0", "rules": ""}
    return config


def write_config(config: configparser.ConfigParser) -> None:
    KWIN_RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(KWIN_RULES_PATH, "w", encoding="utf-8") as handle:
        config.write(handle, space_around_delimiters=False)


def install_rule() -> int:
    config = load_config()
    rules_list = [item for item in config["General"].get("rules", "").split(",") if item]

    target_section = None
    for section in rules_list:
        if section in config and config[section].get("wmclass") == APP_WMCLASS:
            target_section = section
            break

    if target_section is None:
        numeric_ids = [int(item) for item in rules_list if item.isdigit()]
        target_section = str(max(numeric_ids + [0]) + 1)
        rules_list.append(target_section)
        print(f"Creating KWin rule section [{target_section}]")
    else:
        print(f"Updating existing KWin rule section [{target_section}]")

    config["General"]["rules"] = ",".join(rules_list)
    config["General"]["count"] = str(len(rules_list))

    if target_section not in config:
        config[target_section] = {}
    rule = config[target_section]
    rule["Description"] = RULE_DESCRIPTION
    rule["wmclass"] = APP_WMCLASS
    rule["wmclassmatch"] = "1"
    rule["above"] = "true"
    rule["aboverule"] = "2"
    rule["noborder"] = "true"
    rule["noborderrule"] = "2"
    rule["positionrule"] = "4"
    rule["sizerule"] = "4"
    rule["screenrule"] = "4"

    write_config(config)
    run_kwin_reconfigure()
    print(f"Installed KWin rule in {KWIN_RULES_PATH}")
    return 0


def uninstall_rule() -> int:
    if not KWIN_RULES_PATH.exists():
        print("No KWin rules file found; nothing to remove.")
        return 0

    config = load_config()
    rules_list = [item for item in config["General"].get("rules", "").split(",") if item]
    kept_rules: list[str] = []
    removed = 0

    for section in rules_list:
        if section in config and config[section].get("wmclass") == APP_WMCLASS:
            config.remove_section(section)
            removed += 1
            continue
        kept_rules.append(section)

    config["General"]["rules"] = ",".join(kept_rules)
    config["General"]["count"] = str(len(kept_rules))
    write_config(config)

    if removed:
        run_kwin_reconfigure()
        print(f"Removed {removed} KWin rule(s) for {APP_WMCLASS}.")
    else:
        print("No matching KWin rules found.")
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--uninstall":
        return uninstall_rule()
    return install_rule()


if __name__ == "__main__":
    raise SystemExit(main())

