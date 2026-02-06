#!/bin/bash
# bluetooth-reset.sh - Reset Linux Bluetooth stack when it becomes unresponsive
# Version: 1.0.0

set -euo pipefail

VERSION="1.0.0"
SCRIPT_NAME="$(basename "$0")"

# Colors (disabled if not a terminal)
if [[ -t 1 ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    BLUE='\033[0;34m'
    NC='\033[0m' # No Color
else
    RED='' GREEN='' YELLOW='' BLUE='' NC=''
fi

usage() {
    cat <<EOF
Bluetooth Reset Utility v${VERSION}

Reset the Linux Bluetooth stack when it becomes unresponsive.
BlueZ can get stuck after extended uptime or frequent device connect/disconnect cycles.

Usage: ${SCRIPT_NAME} [OPTIONS]

Options:
    -h, --help      Show this help message
    -v, --version   Show version
    -s, --status    Show current bluetooth status (no restart)
    -c, --check     Check if bluetooth appears stuck (scan test)
    -H, --hard      Hard reset: rfkill toggle + service restart
    -y, --yes       Skip confirmation prompt
    -q, --quiet     Minimal output

Examples:
    ${SCRIPT_NAME}              # Restart bluetooth service
    ${SCRIPT_NAME} --status     # Show status only
    ${SCRIPT_NAME} --check      # Test if scanning works
    ${SCRIPT_NAME} --hard       # Aggressive reset
EOF
}

log_info() { echo -e "${BLUE}$1${NC}"; }
log_success() { echo -e "${GREEN}$1${NC}"; }
log_warn() { echo -e "${YELLOW}$1${NC}"; }
log_error() { echo -e "${RED}$1${NC}" >&2; }

check_requirements() {
    if ! command -v systemctl &>/dev/null; then
        log_error "Error: systemctl not found. This script requires systemd."
        exit 2
    fi

    if ! systemctl list-unit-files bluetooth.service &>/dev/null; then
        log_error "Error: bluetooth.service not found."
        exit 2
    fi

    if ! command -v bluetoothctl &>/dev/null; then
        log_error "Error: bluetoothctl not found. Install bluez package."
        exit 2
    fi
}

get_service_status() {
    if systemctl is-active bluetooth.service &>/dev/null; then
        echo "active"
    else
        echo "inactive"
    fi
}

get_connected_devices() {
    local devices=()
    while IFS= read -r line; do
        local mac name
        mac=$(echo "$line" | awk '{print $2}')
        name=$(echo "$line" | cut -d' ' -f3-)
        if [[ -n "$mac" ]]; then
            # Check if device is actually connected
            if bluetoothctl info "$mac" 2>/dev/null | grep -q "Connected: yes"; then
                devices+=("$name")
            fi
        fi
    done < <(bluetoothctl devices 2>/dev/null)

    if [[ ${#devices[@]} -gt 0 ]]; then
        printf '%s\n' "${devices[@]}"
    fi
}

show_status() {
    local quiet=${1:-false}

    local status
    status=$(get_service_status)

    if [[ "$quiet" != "true" ]]; then
        echo "Bluetooth Status:"
        echo "  Service: $status"

        local connected
        connected=$(get_connected_devices)
        if [[ -n "$connected" ]]; then
            echo "  Connected devices:"
            while IFS= read -r device; do
                echo "    - $device"
            done <<< "$connected"
        else
            echo "  Connected devices: (none)"
        fi
    else
        echo "$status"
    fi
}

check_bluetooth() {
    log_info "Testing bluetooth scanning capability..."

    # Try to scan for 5 seconds
    local scan_result
    if scan_result=$(timeout 5 bluetoothctl --timeout 5 scan on 2>&1); then
        if echo "$scan_result" | grep -q "Discovery started"; then
            log_success "Bluetooth scanning is working."
            bluetoothctl scan off &>/dev/null || true
            return 0
        fi
    fi

    # Check for common error patterns
    if echo "$scan_result" | grep -qi "busy\|failed\|error"; then
        log_warn "Bluetooth appears stuck. Restart recommended."
        log_warn "Run: ${SCRIPT_NAME} --hard"
        return 1
    fi

    log_warn "Bluetooth scan test inconclusive."
    return 1
}

do_restart() {
    local hard=${1:-false}
    local quiet=${2:-false}

    [[ "$quiet" != "true" ]] && log_info "Restarting bluetooth service..."

    if [[ "$hard" == "true" ]]; then
        [[ "$quiet" != "true" ]] && log_info "Performing hard reset (rfkill toggle)..."
        sudo rfkill block bluetooth 2>/dev/null || true
        sleep 1
        sudo rfkill unblock bluetooth 2>/dev/null || true
        sleep 1
    fi

    if ! sudo systemctl restart bluetooth; then
        log_error "Failed to restart bluetooth service."
        return 1
    fi

    # Wait for service to stabilize
    sleep 2

    [[ "$quiet" != "true" ]] && log_success "Bluetooth service restarted."
    return 0
}

main() {
    local mode="restart"
    local hard=false
    local skip_confirm=false
    local quiet=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                usage
                exit 0
                ;;
            -v|--version)
                echo "bluetooth-reset v${VERSION}"
                exit 0
                ;;
            -s|--status)
                mode="status"
                shift
                ;;
            -c|--check)
                mode="check"
                shift
                ;;
            -H|--hard)
                hard=true
                shift
                ;;
            -y|--yes)
                skip_confirm=true
                shift
                ;;
            -q|--quiet)
                quiet=true
                shift
                ;;
            *)
                log_error "Unknown option: $1"
                usage
                exit 1
                ;;
        esac
    done

    check_requirements

    case $mode in
        status)
            show_status "$quiet"
            exit 0
            ;;
        check)
            check_bluetooth
            exit $?
            ;;
        restart)
            if [[ "$quiet" != "true" ]]; then
                echo "Bluetooth Reset Utility v${VERSION}"
                echo
                show_status false
                echo
            fi

            # Warn about connected devices
            local connected
            connected=$(get_connected_devices)
            if [[ -n "$connected" ]]; then
                local count
                count=$(echo "$connected" | wc -l)
                log_warn "WARNING: ${count} device(s) will be disconnected."
                echo

                if [[ "$skip_confirm" != "true" && -t 0 ]]; then
                    read -rp "Continue? [y/N] " confirm
                    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
                        echo "Aborted."
                        exit 0
                    fi
                fi
            fi

            if do_restart "$hard" "$quiet"; then
                if [[ "$quiet" != "true" ]]; then
                    echo
                    echo "New Status:"
                    show_status false | tail -n +2
                fi
                exit 0
            else
                exit 1
            fi
            ;;
    esac
}

main "$@"
