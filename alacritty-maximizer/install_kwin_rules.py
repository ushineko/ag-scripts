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

def install_rules():
    # We need PyQt6 to get accurate screen coordinates (matching what we see in main.py)
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QPoint
        # Create headless app just to query screens
        if not QApplication.instance():
            app = QApplication(sys.argv)
        else:
            app = QApplication.instance()
        screens = app.screens()
    except ImportError:
        print("Error: PyQt6 not found. Please install it.")
        return False

    config_path = Path.home() / ".config" / "kwinrulesrc"
    
    config = configparser.ConfigParser(strict=False)
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
    
    # We create a rule for each detected screen
    for i, screen in enumerate(screens):
        rule_name = f"alacritty-monitor-{i}"
        
        # Get geometry
        geo = screen.geometry()
        # For KWin, position should be "x,y"
        position_str = f"{geo.x()},{geo.y()}"
        description = f"Alacritty Maximize on Monitor {i} ({position_str})"
        
        found = False
        target_section = None

        # Search for existing rule in rules_list
        for section in rules_list:
            if section in config:
                if config[section].get('wmclass') == rule_name:
                    target_section = section
                    found = True
                    break
        
        if not found:
            current_ids = []
            for r in rules_list:
                if r.isdigit():
                    current_ids.append(int(r))
            
            next_id = max(current_ids + [0]) + 1
            target_section = str(next_id)
            rules_list.append(target_section)
            print(f"Creating rule '{rule_name}' in section [{target_section}]...")
        else:
            print(f"Updating existing rule '{rule_name}' in section [{target_section}]...")

        config['General']['rules'] = ','.join(rules_list)
        config['General']['count'] = str(len(rules_list))

        if target_section not in config:
            config[target_section] = {}
            
        rule = config[target_section]
        rule['Description'] = description
        rule['wmclass'] = rule_name
        rule['wmclassmatch'] = '1' # Exact match
        
        # SCREEN RULE - REMOVED (Unreliable)
        # rule['screen'] = str(i)
        # rule['screenrule'] = '2'
        
        # POSITION RULE - NEW (Reliable)
        rule['position'] = position_str
        rule['positionrule'] = '2' # Force
        
        # Maximize Rules
        rule['maximizevert'] = 'true'
        rule['maximizevertrule'] = '2' # Force
        rule['maximizehoriz'] = 'true'
        rule['maximizehorizrule'] = '2' # Force
        
        rule['activity'] = 'All Desktops'
        rule['activityrule'] = '2' # Force
        
        # Ensure minimal decoration if desired, though Maximize usually handles it
        # rule['noborder'] = 'true'
        # rule['noborderrule'] = '2'


    try:
        with open(config_path, 'w') as f:
            config.write(f, space_around_delimiters=False)
        print(f"Successfully wrote to {config_path}")
        run_kwin_reconfigure()
        return True
    except Exception as e:
        print(f"Failed to write config: {e}")
        return False

def uninstall_rules():
    config_path = Path.home() / ".config" / "kwinrulesrc"
    if not config_path.exists():
        print("Config file not found.")
        return

    config = configparser.ConfigParser(strict=False)
    config.optionxform = str
    
    try:
        config.read(config_path)
    except Exception as e:
        print(f"Error reading kwinrulesrc: {e}")
        return

    if 'General' not in config:
        return

    rules_str = config['General'].get('rules', '')
    rules_list = [r for r in rules_str.split(',') if r]
    
    new_rules_list = []
    removed_count = 0
    
    for section in rules_list:
        keep = True
        if section in config:
            # Check if this rule belongs to us
            if config[section].get('wmclass', '').startswith('alacritty-monitor-'):
                print(f"Removing rule in section [{section}]...")
                config.remove_section(section)
                keep = False
                removed_count += 1
        
        if keep:
            new_rules_list.append(section)
            
    if removed_count > 0:
        config['General']['rules'] = ','.join(new_rules_list)
        config['General']['count'] = str(len(new_rules_list))
        
        try:
            with open(config_path, 'w') as f:
                config.write(f, space_around_delimiters=False)
            print(f"Successfully removed {removed_count} rules.")
            run_kwin_reconfigure()
        except Exception as e:
            print(f"Failed to write config: {e}")
    else:
        print("No rules found to remove.")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--uninstall":
        uninstall_rules()
    else:
        install_rules()
