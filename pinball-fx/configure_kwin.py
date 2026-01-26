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

def get_portrait_screen_info():
    try:
        from PyQt6.QtWidgets import QApplication
        if not QApplication.instance():
            app = QApplication(sys.argv)
        else:
            app = QApplication.instance()
        
        screens = app.screens()
        for i, screen in enumerate(screens):
            geo = screen.geometry()
            # Check for portrait (Height > Width)
            if geo.height() > geo.width():
                print(f"Found Portrait Monitor: Screen {i} ({geo.width()}x{geo.height()} at {geo.x()},{geo.y()})")
                return i, geo.x(), geo.y()
    except ImportError:
        print("PyQt6 not found. Cannot auto-detect screen index.")
    
    return None, None, None

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

def install_rule():
    screen_idx, x, y = get_portrait_screen_info()
    if screen_idx is None:
        print("No portrait monitor found or PyQt6 missing. Skipping auto-rule creation.")
        print("Please manually configure KWin rule for screen targeting.")
        return

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
            if config[section].get('wmclass') == WM_CLASS and config[section].get('Description') == RULE_DESCRIPTION:
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
    
    # Position Rule (More reliable than Screen rule)
    rule['position'] = f"{x},{y}"
    rule['positionrule'] = '4' # Apply Initially
    
    # Size Rule (Maximize) - handled by fullscreen, but good backup?
    # rule['maximizevert'] = 'true'
    # rule['maximizevertrule'] = '4'
    # rule['maximizehoriz'] = 'true'
    # rule['maximizehorizrule'] = '4'

    # Fullscreen Rule
    rule['fullscreen'] = 'true'
    rule['fullscreenrule'] = '4' # Apply Initially (changed from Force '2' to allow user to exit if needed, or maybe '2' is better?)
    # Let's stick to '4' (Apply Initially) for fullscreen too if we trust position.
    
    # Remove old screen rule if it exists as we replace it with position
    if 'screen' in rule: del rule['screen']
    if 'screenrule' in rule: del rule['screenrule']

    try:
        with open(config_path, 'w') as f:
            config.write(f, space_around_delimiters=False)
        print("Successfully wrote KWin rule.")
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

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--uninstall":
        uninstall_rule()
    else:
        install_rule()
