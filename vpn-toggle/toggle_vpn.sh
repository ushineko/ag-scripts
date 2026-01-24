#!/usr/bin/env bash



# 1. Resolve VPN Name
if [ -z "$1" ]; then
    # Default provided? Or default to the original logical one?
    # Let's default to the Vegas one if nothing passed, for backward compat with existing hotkey
    VPN_INPUT="us_las_vegas" 
else
    VPN_INPUT="$1"
fi

# Find exact connection name via partial match
# -t terse, -f NAME fields
VPN_NAME=$(nmcli -t -f NAME connection show | grep -i "$VPN_INPUT" | head -n 1)

if [ -z "$VPN_NAME" ]; then
    if command -v kdialog >/dev/null; then
        kdialog --error "Could not find any VPN connection matching '$VPN_INPUT'"
    else
        echo "Error: VPN '$VPN_INPUT' not found."
    fi
    exit 1
fi

# 2. Check State
IS_ACTIVE=0
STATUS_TEXT="Disconnected"
if nmcli connection show --active | grep -Fq "$VPN_NAME"; then
    IS_ACTIVE=1
    STATUS_TEXT="Connected"
fi

# 3. Build Dialog Options
OPTIONS=()
if [ "$IS_ACTIVE" -eq 1 ]; then
    OPTIONS+=("disable" "Disable VPN")
    OPTIONS+=("bounce" "Bounce (Restart)")
else
    OPTIONS+=("enable" "Enable VPN")
fi
OPTIONS+=("config" "Open Configuration")

# 4. Show Menu
if command -v kdialog >/dev/null; then
    ACTION=$(kdialog --icon "network-vpn" \
                     --title "VPN Control: $VPN_NAME" \
                     --menu "Current Status: $STATUS_TEXT" \
                     "${OPTIONS[@]}")
elif command -v zenity >/dev/null; then
    # Fallback to zenity if kdialog fits
    ACTION=$(zenity --list --title="VPN Control: $VPN_NAME" \
                    --text="Current Status: $STATUS_TEXT" \
                    --column="Action" --column="Description" \
                    "${OPTIONS[@]}" --print-column=1)
else
    echo "No dialog tool found."
    exit 1
fi

# User cancelled?
if [ -z "$ACTION" ]; then
    exit 0
fi

# 5. Execute
case "$ACTION" in
    enable)
        notify-send "VPN" "Connecting to $VPN_NAME..." --icon=network-vpn-symbolic
        nmcli con up "$VPN_NAME"
        if [ $? -eq 0 ]; then
             notify-send "VPN" "Connected: $VPN_NAME" --icon=network-vpn-symbolic
        else
             notify-send "VPN" "Failed to connect: $VPN_NAME" --icon=dialog-error-symbolic
        fi
        ;;
    disable)
        notify-send "VPN" "Disconnecting $VPN_NAME..." --icon=network-vpn-disconnected-symbolic
        nmcli con down "$VPN_NAME"
        ;;
    bounce)
        notify-send "VPN" "Bouncing $VPN_NAME..." --icon=network-vpn-acquiring-symbolic
        nmcli con down "$VPN_NAME"
        sleep 2
        nmcli con up "$VPN_NAME"
        if [ $? -eq 0 ]; then
             notify-send "VPN" "Reconnected: $VPN_NAME" --icon=network-vpn-symbolic
        fi
        ;;
    config)
        # Try to launch KDE settings
        if command -v plasma-open-settings >/dev/null; then
            plasma-open-settings kcm_networkmanagement
        elif command -v kcmshell6 >/dev/null; then
            kcmshell6 kcm_networkmanagement
        elif command -v kcmshell5 >/dev/null; then
            kcmshell5 kcm_networkmanagement
        else
            nm-connection-editor 2>/dev/null || notify-send "Error" "No configuration tool found."
        fi
        ;;
esac
