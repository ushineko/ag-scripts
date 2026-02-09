#!/bin/bash
# bluetooth-reset.sh - Reset Linux Bluetooth stack when it becomes unresponsive
# Version: 2.0.0

set -euo pipefail

VERSION="2.0.0"
DEFAULT_SCAN_TIMEOUT=30
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
    -h, --help                  Show this help message
    -v, --version               Show version
    -s, --status                Show current bluetooth status (no restart)
    -c, --check                 Check if bluetooth appears stuck (scan test)
    -H, --hard                  Hard reset: rfkill toggle + service restart
    -r, --reconnect PATTERN     Hard reset + scan + pair + connect device by name
    -t, --scan-timeout SECONDS  Scan timeout for --reconnect (default: ${DEFAULT_SCAN_TIMEOUT})
    -y, --yes                   Skip confirmation prompt
    -q, --quiet                 Minimal output

Examples:
    ${SCRIPT_NAME}                              # Restart bluetooth service
    ${SCRIPT_NAME} --status                     # Show status only
    ${SCRIPT_NAME} --check                      # Test if scanning works
    ${SCRIPT_NAME} --hard                       # Aggressive reset
    ${SCRIPT_NAME} -r "Keychron K4 HE"          # Reconnect keyboard
    ${SCRIPT_NAME} -r Keychron                   # Partial name match
    ${SCRIPT_NAME} -r Keychron -t 60             # Longer scan timeout
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

remove_stale_pairings() {
    local pattern="$1"
    local quiet=${2:-false}
    local removed=0

    while IFS= read -r line; do
        local mac name
        mac=$(echo "$line" | awk '{print $2}')
        name=$(echo "$line" | cut -d' ' -f3-)
        if [[ -n "$mac" && "$name" == *"$pattern"* ]]; then
            [[ "$quiet" != "true" ]] && log_info "  Removing stale pairing: $name ($mac)"
            bluetoothctl remove "$mac" &>/dev/null || true
            ((++removed)) || true
        fi
    done < <(bluetoothctl devices Paired 2>/dev/null)

    if [[ $removed -gt 0 && "$quiet" != "true" ]]; then
        log_info "  Removed $removed stale pairing(s)."
    fi
}

scan_for_device() {
    local pattern="$1"
    local scan_timeout="$2"
    local quiet=${3:-false}

    [[ "$quiet" != "true" ]] && log_info "Scanning for '$pattern' (${scan_timeout}s timeout)..."

    # Start scanning in background
    bluetoothctl scan on &>/dev/null &
    local scan_pid=$!

    local elapsed=0
    local found_mac=""
    while [[ $elapsed -lt $scan_timeout ]]; do
        sleep 2
        elapsed=$((elapsed + 2))

        # Check all known devices for a name match
        while IFS= read -r line; do
            local mac name
            mac=$(echo "$line" | awk '{print $2}')
            name=$(echo "$line" | cut -d' ' -f3-)
            if [[ "$name" == *"$pattern"* ]]; then
                found_mac="$mac"
                break 2
            fi
        done < <(bluetoothctl devices 2>/dev/null)

        [[ "$quiet" != "true" ]] && printf "\r  %ds / %ds..." "$elapsed" "$scan_timeout"
    done

    # Stop scanning
    kill "$scan_pid" 2>/dev/null || true
    bluetoothctl scan off &>/dev/null || true
    [[ "$quiet" != "true" ]] && echo

    if [[ -z "$found_mac" ]]; then
        log_error "Device matching '$pattern' not found within ${scan_timeout}s."
        log_error "Ensure the device is in pairing mode and try again."
        return 1
    fi

    local found_name
    found_name=$(bluetoothctl devices 2>/dev/null | grep "$found_mac" | cut -d' ' -f3-)
    [[ "$quiet" != "true" ]] && log_success "  Found: $found_name ($found_mac)"
    echo "$found_mac"
}

pair_and_connect() {
    local mac="$1"
    local quiet=${2:-false}

    [[ "$quiet" != "true" ]] && log_info "Pairing with $mac..."
    if ! bluetoothctl pair "$mac" 2>&1 | tail -1 | grep -qi "successful\|already"; then
        log_error "Pairing failed for $mac."
        return 1
    fi
    [[ "$quiet" != "true" ]] && log_success "  Paired."

    [[ "$quiet" != "true" ]] && log_info "Trusting $mac..."
    bluetoothctl trust "$mac" &>/dev/null || true
    [[ "$quiet" != "true" ]] && log_success "  Trusted."

    [[ "$quiet" != "true" ]] && log_info "Connecting to $mac..."
    if ! bluetoothctl connect "$mac" 2>&1 | tail -1 | grep -qi "successful\|already"; then
        log_error "Connection failed for $mac."
        return 1
    fi
    [[ "$quiet" != "true" ]] && log_success "  Connected."
    return 0
}

do_reconnect() {
    local device_pattern="$1"
    local scan_timeout="$2"
    local quiet=${3:-false}

    [[ "$quiet" != "true" ]] && echo "Bluetooth Reconnect - '$device_pattern'"
    [[ "$quiet" != "true" ]] && echo

    # Step 1: Hard reset
    [[ "$quiet" != "true" ]] && log_info "Step 1/4: Hard reset bluetooth adapter..."
    if ! do_restart true "$quiet"; then
        log_error "Hard reset failed."
        return 1
    fi

    # Step 2: Remove stale pairings
    [[ "$quiet" != "true" ]] && log_info "Step 2/4: Cleaning stale pairings..."
    remove_stale_pairings "$device_pattern" "$quiet"

    # Step 3: Scan for device
    [[ "$quiet" != "true" ]] && log_info "Step 3/4: Scanning for device..."
    local mac
    # scan_for_device prints the MAC as its last line of stdout
    mac=$(scan_for_device "$device_pattern" "$scan_timeout" "$quiet" | tail -1) || return 1

    if [[ -z "$mac" || ! "$mac" =~ ^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$ ]]; then
        log_error "Could not determine device MAC address."
        return 1
    fi

    # Step 4: Pair and connect
    [[ "$quiet" != "true" ]] && log_info "Step 4/4: Pairing and connecting..."
    if ! pair_and_connect "$mac" "$quiet"; then
        return 1
    fi

    [[ "$quiet" != "true" ]] && echo
    local device_name
    device_name=$(bluetoothctl info "$mac" 2>/dev/null | grep "Name:" | cut -d' ' -f2- | xargs)
    [[ "$quiet" != "true" ]] && log_success "Reconnected: ${device_name:-$mac}"
    return 0
}

main() {
    local mode="restart"
    local hard=false
    local skip_confirm=false
    local quiet=false
    local reconnect_pattern=""
    local scan_timeout="$DEFAULT_SCAN_TIMEOUT"

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
            -r|--reconnect)
                mode="reconnect"
                if [[ $# -lt 2 || "$2" =~ ^- ]]; then
                    log_error "Error: --reconnect requires a device name pattern."
                    log_error "Example: ${SCRIPT_NAME} --reconnect Keychron"
                    exit 1
                fi
                reconnect_pattern="$2"
                shift 2
                ;;
            -t|--scan-timeout)
                if [[ $# -lt 2 || ! "$2" =~ ^[0-9]+$ ]]; then
                    log_error "Error: --scan-timeout requires a number (seconds)."
                    exit 1
                fi
                scan_timeout="$2"
                shift 2
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
        reconnect)
            if do_reconnect "$reconnect_pattern" "$scan_timeout" "$quiet"; then
                exit 0
            else
                exit 1
            fi
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
