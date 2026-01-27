#!/usr/bin/env python3
import configparser
import sys
import subprocess
import os
from pathlib import Path

# Constants
APP_NAME = "Pinball FX"
WM_CLASS = "PinballFX" # Substring match
RULE_DESCRIPTION = "Pinball FX Portrait Mode"

def get_connected_screens():
    """Returns a list of tuples: (screen_index, width, height, x, y, is_portrait)"""
    screens_info = []
    try:
        from PyQt6.QtWidgets import QApplication
        if not QApplication.instance():
            app = QApplication(sys.argv)
        else:
            app = QApplication.instance()
        
        screens = app.screens()
        for i, screen in enumerate(screens):
            geo = screen.geometry()
            is_portrait = geo.height() > geo.width()
            screens_info.append((i, geo.width(), geo.height(), geo.x(), geo.y(), is_portrait))
    except ImportError:
        print("PyQt6 not found. Cannot detect screens via Python.")
        # Fallback could be implemented here (e.g. xrandr parsing), but PyQt6 is expected.
    return screens_info

def select_screen_menu(screens_info):
    """Shows a kdialog menu to select a screen."""
    if not screens_info:
        return None

    menu_args = ["kdialog", "--title", "Pinball FX Screen Switcher", "--menu", "Select Monitor for Pinball FX:"]
    
    for s in screens_info:
        idx, w, h, x, y, portrait = s
        orientation = "Portrait" if portrait else "Landscape"
        description = f"Screen {idx}: {w}x{h} ({orientation})"
        # Key is just the index as string
        menu_args.extend([str(idx), description])

    # Add Uninstall option
    menu_args.extend(["UNINSTALL", "Disable/Uninstall Rule"])

    try:
        result = subprocess.run(menu_args, capture_output=True, text=True, check=True)
        selection = result.stdout.strip()
        return selection
    except subprocess.CalledProcessError:
        return None # User cancelled

def run_kwin_reconfigure():
    commands = [
        "qdbus6 org.kde.KWin /KWin reconfigure",
        "qdbus org.kde.KWin /KWin reconfigure",
        "dbus-send --session --dest=org.kde.KWin /KWin org.kde.KWin.reconfigure"
    ]
    for cmd in commands:
        try:
            subprocess.run(cmd, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("KWin reconfigured successfully.")
            return
        except subprocess.CalledProcessError:
            continue
    print("Warning: Could not reload KWin configuration automatically.")

def install_rule(screen_index, screens_info):
    # Find screen info
    target_screen = next((s for s in screens_info if str(s[0]) == screen_index), None)
    if not target_screen:
        print("Invalid screen selection.")
        return

    idx, w, h, x, y, portrait = target_screen

    config_path = Path.home() / ".config" / "kwinrulesrc"
    config = configparser.ConfigParser(strict=False)
    config.optionxform = str
    
    if config_path.exists():
        try:
            config.read(config_path)
        except Exception as e:
            print(f"Error reading kwinrulesrc: {e}")
            return

    if 'General' not in config:
        config['General'] = {'count': '0'}

    rules_str = config['General'].get('rules', '')
    rules_list = [r for r in rules_str.split(',') if r]
    
    # Check if rule exists
    target_section = None
    for section in rules_list:
        if section in config:
            # Only check Description as wmclass might be a regex now
            if config[section].get('Description') == RULE_DESCRIPTION:
                target_section = section
                break
    
    if not target_section:
        # Generate new ID
        current_ids = [int(r) for r in rules_list if r.isdigit()]
        next_id = max(current_ids + [0]) + 1
        target_section = str(next_id)
        rules_list.append(target_section)
        print(f"Creating new rule in section [{target_section}]...")
    else:
        print(f"Updating existing rule in section [{target_section}]...")

    # Update General sections
    config['General']['rules'] = ','.join(rules_list)
    config['General']['count'] = str(len(rules_list))

    if target_section not in config:
        config[target_section] = {}

    rule = config[target_section]
    rule['Description'] = RULE_DESCRIPTION
    
    # Regex Match for broader compatibility (Handling Mangohud or other prefix/suffixes)
    rule['wmclass'] = r"^.*pinballfx-win64-shipping\.exe.*$"
    rule['wmclassmatch'] = '3' # Regex match
    
    # Remove Title match to avoid race conditions if title changes during startup
    if 'title' in rule: del rule['title']
    if 'titlematch' in rule: del rule['titlematch']
    

    # Position Rule
    rule['position'] = f"{x},{y}"
    rule['positionrule'] = '2' # Force (Apply Now & Lock)
    
    # Size Rule
    rule['size'] = f"{w},{h}"
    rule['sizerule'] = '2' # Force

    # Fullscreen Rule
    rule['fullscreen'] = 'true'
    rule['fullscreenrule'] = '2' # Force
    
    # Nborder Rule (Ensure no decorations)
    rule['noborder'] = 'true'
    rule['noborderrule'] = '2' # Force
    
    # Remove old screen rule if it exists as we replace it with position
    if 'screen' in rule: del rule['screen']
    if 'screenrule' in rule: del rule['screenrule']

    try:
        with open(config_path, 'w') as f:
            config.write(f, space_around_delimiters=False)
        print(f"Successfully wrote KWin rule for Screen {idx} at {x},{y}.")
        run_kwin_reconfigure()
    except Exception as e:
        print(f"Failed to write config: {e}")

def uninstall_rule():
    config_path = Path.home() / ".config" / "kwinrulesrc"
    if not config_path.exists(): return

    config = configparser.ConfigParser(strict=False)
    config.optionxform = str
    try:
        config.read(config_path)
    except: return

    if 'General' not in config: return

    rules_str = config['General'].get('rules', '')
    rules_list = [r for r in rules_str.split(',') if r]
    
    new_rules = []
    removed = False
    
    for section in rules_list:
        if section in config and config[section].get('Description') == RULE_DESCRIPTION:
            config.remove_section(section)
            removed = True
        else:
            new_rules.append(section)
            
    if removed:
        config['General']['rules'] = ','.join(new_rules)
        config['General']['count'] = str(len(new_rules))
        with open(config_path, 'w') as f:
            config.write(f, space_around_delimiters=False)
        print("Removed KWin rule.")
        run_kwin_reconfigure()
    else:
        print("No existing rule found to remove.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Configure KWin rules for Pinball FX.")
    parser.add_argument("--uninstall", action="store_true", help="Uninstall the KWin rule.")
    parser.add_argument("--screen", type=str, help="Manually select screen index (0, 1, etc.)")
    args = parser.parse_args()

    if args.uninstall:
        uninstall_rule()
    else:
        screens = get_connected_screens()
        if not screens:
            print("Could not detect screens.")
            sys.exit(1)

        selection = None
        if args.screen:
            selection = args.screen
            # Verify selection logic
            if not any(str(s[0]) == selection for s in screens):
                print(f"Error: Screen {selection} not found.")
                sys.exit(1)
        else:
            selection = select_screen_menu(screens)
        
        if selection == "UNINSTALL":
            uninstall_rule()
        elif selection is not None:
             install_rule(selection, screens)
        else:
            print("Cancelled.")
