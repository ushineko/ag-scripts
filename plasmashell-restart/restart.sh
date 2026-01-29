#!/bin/bash

# Plasmashell restart utility for KDE Plasma 6
# Supports light refresh (D-Bus) or full restart (systemd)

VERSION="1.1.0"

show_help() {
    echo "Usage: $(basename "$0") [OPTION]"
    echo ""
    echo "Restart or refresh the KDE Plasma shell."
    echo ""
    echo "Options:"
    echo "  -r, --refresh    Light refresh via D-Bus (no process restart)"
    echo "  -f, --full       Full restart via systemd (default)"
    echo "  -h, --help       Show this help message"
    echo "  -v, --version    Show version"
    echo ""
    echo "The light refresh is useful for minor visual glitches."
    echo "Full restart is needed when widgets/panels are unresponsive."
}

refresh_shell() {
    echo "Refreshing Plasma Shell via D-Bus..."
    if dbus-send --session --dest=org.kde.plasmashell --type=method_call \
        /PlasmaShell org.kde.PlasmaShell.refreshCurrentShell 2>/dev/null; then
        echo "Plasma Shell refreshed."
    else
        echo "D-Bus refresh failed. Try --full restart instead."
        return 1
    fi
}

full_restart() {
    echo "Restarting Plasma Shell..."

    # Prefer systemd if the service exists (Plasma 6 / modern setups)
    if systemctl --user cat plasma-plasmashell.service &>/dev/null; then
        echo "Using systemd to restart plasmashell..."
        systemctl --user restart plasma-plasmashell.service

        # Wait and verify
        sleep 2
        if systemctl --user is-active --quiet plasma-plasmashell.service; then
            echo "Plasma Shell restarted successfully."
        else
            echo "Warning: Service may not have started correctly."
            systemctl --user status plasma-plasmashell.service --no-pager
            return 1
        fi
    else
        # Fallback for older systems or non-systemd setups
        echo "Systemd service not found, using legacy method..."

        # Detect which quit app is available (Plasma 6 vs Plasma 5)
        if command -v kquitapp6 &>/dev/null; then
            QUIT_CMD="kquitapp6"
        elif command -v kquitapp5 &>/dev/null; then
            QUIT_CMD="kquitapp5"
        else
            QUIT_CMD=""
        fi

        # Kill plasma
        if [ -n "$QUIT_CMD" ]; then
            $QUIT_CMD plasmashell 2>/dev/null || killall plasmashell 2>/dev/null
        else
            killall plasmashell 2>/dev/null
        fi

        # Wait for it to die
        sleep 2

        # Start it back up with --no-respawn to match systemd behavior
        kstart plasmashell --no-respawn >/dev/null 2>&1 &

        sleep 1
        if pgrep -x plasmashell >/dev/null; then
            echo "Plasma Shell restarted."
        else
            echo "Warning: plasmashell may not have started."
            return 1
        fi
    fi
}

# Parse arguments
MODE="full"
while [[ $# -gt 0 ]]; do
    case "$1" in
        -r|--refresh)
            MODE="refresh"
            shift
            ;;
        -f|--full)
            MODE="full"
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        -v|--version)
            echo "plasmashell-restart version $VERSION"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Execute
case "$MODE" in
    refresh)
        refresh_shell
        ;;
    full)
        full_restart
        ;;
esac
