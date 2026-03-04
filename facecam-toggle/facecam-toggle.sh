#!/bin/bash
# Toggle the Elgato Facecam virtual camera service on/off.
# Designed for KDE Plasma taskbar (system tray widget or custom shortcut).

SERVICE="facecam-virtual.service"
ICON_ON="camera-on"
ICON_OFF="camera-off"

is_active() {
    systemctl --user is-active --quiet "$SERVICE"
}

notify() {
    local summary="$1" body="$2" icon="$3"
    notify-send -a "Facecam Toggle" -i "$icon" "$summary" "$body"
}

case "${1:-toggle}" in
    on|start)
        systemctl --user start "$SERVICE"
        notify "Camera On" "Virtual camera active" "$ICON_ON"
        ;;
    off|stop)
        systemctl --user stop "$SERVICE"
        notify "Camera Off" "Virtual camera stopped" "$ICON_OFF"
        ;;
    toggle)
        if is_active; then
            systemctl --user stop "$SERVICE"
            notify "Camera Off" "Virtual camera stopped" "$ICON_OFF"
        else
            systemctl --user start "$SERVICE"
            notify "Camera On" "Virtual camera active" "$ICON_ON"
        fi
        ;;
    status)
        if is_active; then
            echo "active"
        else
            echo "inactive"
        fi
        ;;
    *)
        echo "Usage: $(basename "$0") [on|off|toggle|status]"
        exit 1
        ;;
esac
