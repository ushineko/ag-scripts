#!/bin/bash
# Toggle the aiqlabs OpenVPN3 connection on/off.
# Designed for KDE Plasma taskbar shortcut.

CONFIG_NAME="aiqlabs"
ICON_ON="network-vpn"
ICON_OFF="network-vpn-disconnected"
ICON_WAIT="network-vpn-acquiring"
APP_NAME="AIQLabs VPN"

# Timeout for waiting on web auth (seconds)
AUTH_TIMEOUT=60

# TODO: openvpn3 opens a browser to a useless "auth successful" page via xdg-open.
# PATH override works from terminal but not from .desktop entries. Needs investigation.

is_connected() {
    openvpn3 sessions-list 2>/dev/null | grep -q "Config name: $CONFIG_NAME"
}

get_session_status() {
    openvpn3 sessions-list 2>/dev/null | grep "Status:" | sed 's/.*Status: //'
}

notify() {
    local summary="$1" body="$2" icon="$3"
    notify-send -a "$APP_NAME" -i "$icon" "$summary" "$body"
}

do_connect() {
    notify "VPN Connecting" "Starting $CONFIG_NAME..." "$ICON_WAIT"

    local output
    output=$(openvpn3 session-start --config "$CONFIG_NAME" 2>&1)
    local rc=$?

    if [ $rc -ne 0 ]; then
        notify "VPN Failed" "Could not start session: $output" "$ICON_OFF"
        return 1
    fi

    # Wait for connection to establish (web auth may take time)
    local elapsed=0
    while [ $elapsed -lt $AUTH_TIMEOUT ]; do
        local status
        status=$(get_session_status)
        if echo "$status" | grep -qi "Client connected"; then
            notify "VPN Connected" "$CONFIG_NAME is active" "$ICON_ON"
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done

    notify "VPN Timeout" "Web auth not completed within ${AUTH_TIMEOUT}s" "$ICON_OFF"
    # Clean up the pending session
    openvpn3 session-manage --config "$CONFIG_NAME" --disconnect 2>/dev/null
    return 1
}

do_disconnect() {
    openvpn3 session-manage --config "$CONFIG_NAME" --disconnect >/dev/null 2>&1
    notify "VPN Disconnected" "$CONFIG_NAME stopped" "$ICON_OFF"
}

case "${1:-toggle}" in
    on|start)
        if is_connected; then
            notify "VPN Already Connected" "$CONFIG_NAME is active" "$ICON_ON"
        else
            do_connect
        fi
        ;;
    off|stop)
        if is_connected; then
            do_disconnect
        else
            notify "VPN Not Connected" "$CONFIG_NAME is not active" "$ICON_OFF"
        fi
        ;;
    toggle)
        if is_connected; then
            do_disconnect
        else
            do_connect
        fi
        ;;
    status)
        if is_connected; then
            echo "connected"
            get_session_status
        else
            echo "disconnected"
        fi
        ;;
    *)
        echo "Usage: $(basename "$0") [on|off|toggle|status]"
        exit 1
        ;;
esac
