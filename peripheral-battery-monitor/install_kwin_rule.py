
import configparser
import os
import sys
from pathlib import Path
import subprocess

def run_kwin_reconfigure():
    # Try different dbus commands to reload kwin
    commands = [
        "qdbus6 org.kde.KWin /KWin reconfigure",
        "qdbus org.kde.KWin /KWin reconfigure",
        "dbus-send --session --dest=org.kde.KWin /KWin org.kde.KWin.reconfigure"
    ]
    for cmd in commands:
        try:
            print(f"Running: {cmd}")
            subprocess.run(cmd, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("KWin reconfigured successfully.")
            return
        except subprocess.CalledProcessError:
            continue
    print("Warning: Could not reload KWin configuration automatically. You may need to log out or run 'kwin_wayland --replace' (risky).")

def install_rule():
    config_path = Path.home() / ".config" / "kwinrulesrc"
    
    # KWin config is technically INI-like but configparser is sometimes strict.
    # We use strict=False to allow duplicate keys if any (though KWin shouldn't have them).
    config = configparser.ConfigParser(strict=False)
    # KWin keys are case sensitive
    config.optionxform = str
    
    if config_path.exists():
        try:
            config.read(config_path)
        except Exception as e:
            print(f"Error reading kwinrulesrc: {e}")
            return False

    if 'General' not in config:
        config['General'] = {'count': '0'}

    rules_str = config['General'].get('rules', '')
    rules_list = [r for r in rules_str.split(',') if r]
    
    try:
        count = int(config['General'].get('count', len(rules_list)))
    except ValueError:
        count = len(rules_list)

    found = False
    target_section = None

    # Search for existing rule in rules_list
    for section in rules_list:
        if section in config:
            # Check if this rule is ours
            if config[section].get('wmclass') == 'peripheral-battery-monitor':
                target_section = section
                found = True
                break
    
    if not found:
        # Assign next highest available integer
        current_ids = [int(r) for r in rules_list if r.isdigit()]
        next_id = max(current_ids + [0]) + 1
        target_section = str(next_id)
        
        rules_list.append(target_section)
        config['General']['rules'] = ','.join(rules_list)
        config['General']['count'] = str(len(rules_list))
        print(f"Creating new rule in section [{target_section}]...")
    else:
        print(f"Updating existing rule in section [{target_section}]...")

    # Define rule properties
    if target_section not in config:
        config[target_section] = {}
        
    rule = config[target_section]
    rule['Description'] = 'Peripheral Battery Monitor Always On Top'
    rule['wmclass'] = 'peripheral-battery-monitor'
    rule['wmclassmatch'] = '1' # Exact match
    
    # Important properties
    rule['above'] = 'true'
    rule['aboverule'] = '2' # Force
    

    # Optional: Force it to not have a titlebar if the user really wanted that visually,
    # but for now sticking to "above" only as requested.

    rule['noborder'] = 'true' 
    rule['noborderrule'] = '2'

    # Attempt to enable "Remember" for Position (4), Size (4), and Screen (4)
    # This tells KWin to save and restore these properties for this window class.
    rule['positionrule'] = '4'
    rule['sizerule'] = '4'
    rule['screenrule'] = '4'
    
    # Translucency (95% default) - "Apply Initially" (4) allows app to override
    rule['opacityactive'] = '95'
    rule['opacityactiverule'] = '4'
    rule['opacityinactive'] = '95'
    rule['opacityinactiverule'] = '4'

    try:
        with open(config_path, 'w') as f:
            config.write(f, space_around_delimiters=False)
        print(f"Successfully wrote to {config_path}")
        run_kwin_reconfigure()
        return True
    except Exception as e:
        print(f"Failed to write config: {e}")
        return False

if __name__ == "__main__":
    install_rule()
