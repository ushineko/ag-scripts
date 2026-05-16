#!/usr/bin/env bash
# display-mirror-toggle.sh - Toggle a KDE Plasma 6 / Wayland display mirror on/off
# Version: 1.0.0

set -euo pipefail

VERSION="1.0.0"
SCRIPT_NAME="${0##*/}"

# Defaults match the FUERAN-dummy / Philips-OLED setup on njv-cachyos.
# See ~/git/sysadmin/docs/sunshine-moonlight-setup.md for background.
DEFAULT_SOURCE="HDMI-A-1"
DEFAULT_REPLICA="DP-3"

if [[ -t 1 ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    BLUE='\033[0;34m'
    NC='\033[0m'
else
    RED='' GREEN='' YELLOW='' BLUE='' NC=''
fi

usage() {
    cat <<EOF
Display Mirror Toggle v${VERSION}

Toggle a KDE Plasma 6 / Wayland display mirror relationship between two outputs.
Disables/enables the source output in the same atomic kscreen-doctor call.

Usage: ${SCRIPT_NAME} [OPTIONS]

Options:
    -h, --help                Show this help message
    -v, --version             Show version
    -s, --source CONNECTOR    Source output (default: ${DEFAULT_SOURCE})
    -r, --replica CONNECTOR   Replica output that mirrors the source
                              (default: ${DEFAULT_REPLICA})
        --status              Show current mirror state, do not change anything
        --enable              Force enable: source enabled + replica mirrors source
        --disable             Force disable: clear mirror + disable source
    -q, --quiet               Minimal output

With no mode flag, the default behavior is to toggle.

Exit codes:
    0  Success
    1  Runtime error (e.g., kscreen-doctor failed)
    2  Dependency missing (kscreen-doctor not on PATH)

Examples:
    ${SCRIPT_NAME}                           # Toggle the default mirror
    ${SCRIPT_NAME} --status                  # Show current state
    ${SCRIPT_NAME} --disable                 # Force off
    ${SCRIPT_NAME} --enable                  # Force on
    ${SCRIPT_NAME} -s HDMI-A-2 -r DP-1      # Custom source/replica pair

Notes:
    The kscreen-doctor verb is 'mirror', not 'replicate' or 'replication',
    despite the read-side display showing "replication source". Disabling
    the source without clearing the mirror first fails with a negative-
    geometry error; this script always pairs the verbs atomically.
EOF
}

log_info() { [[ "$QUIET" == "true" ]] || echo -e "${BLUE}$1${NC}"; }
log_success() { [[ "$QUIET" == "true" ]] || echo -e "${GREEN}$1${NC}"; }
log_warn() { [[ "$QUIET" == "true" ]] || echo -e "${YELLOW}$1${NC}"; }
log_error() { echo -e "${RED}$1${NC}" >&2; }

# Strip ANSI escape sequences. kscreen-doctor -o emits color codes even when
# piped, which breaks naive grep/awk on tokens like "enabled".
strip_ansi() {
    sed 's/\x1b\[[0-9;]*m//g'
}

check_requirements() {
    if ! command -v kscreen-doctor &>/dev/null; then
        log_error "Error: kscreen-doctor not found on PATH."
        log_error "Install KDE Plasma's libkscreen tools (package: libkscreen on Arch)."
        exit 2
    fi
}

# Parse `kscreen-doctor -o` and return the connector's enabled state and
# replication source value. Output two lines:
#   <enabled|disabled>
#   <replication-source-index-or-0>
#
# If the connector is not present in the output, prints "absent" + "0".
query_output() {
    local connector="$1"
    kscreen-doctor -o 2>/dev/null | strip_ansi | awk -v c="$connector" '
        /^Output:/ {
            split($0, parts, " ")
            current = parts[3]
            in_block = (current == c)
            if (in_block) { found = 1; enabled = ""; repl = "0" }
            next
        }
        in_block {
            if ($0 ~ /^[[:space:]]*enabled[[:space:]]*$/) enabled = "enabled"
            else if ($0 ~ /^[[:space:]]*disabled[[:space:]]*$/) enabled = "disabled"
            else if (match($0, /replication source:[[:space:]]*[0-9]+/)) {
                repl = substr($0, RSTART + length("replication source:"))
                gsub(/[[:space:]]/, "", repl)
            }
        }
        END {
            if (!found) { print "absent"; print "0" }
            else {
                print (enabled == "" ? "disabled" : enabled)
                print repl
            }
        }
    '
}

# Returns 0 if mirror is currently active (source enabled AND replica has a
# non-zero replication source), 1 otherwise.
is_mirror_active() {
    local source_state replica_repl
    source_state="$(query_output "$SOURCE" | sed -n '1p')"
    replica_repl="$(query_output "$REPLICA" | sed -n '2p')"

    [[ "$source_state" == "enabled" && "$replica_repl" != "0" ]]
}

show_status() {
    local source_state replica_state replica_repl
    source_state="$(query_output "$SOURCE" | sed -n '1p')"
    {
        read -r replica_state
        read -r replica_repl
    } < <(query_output "$REPLICA")

    if [[ "$QUIET" == "true" ]]; then
        if is_mirror_active; then echo "active"; else echo "inactive"; fi
        return 0
    fi

    echo "Display Mirror Toggle v${VERSION}"
    echo "Source:  ${SOURCE} (${source_state})"
    if [[ "$replica_state" == "absent" ]]; then
        echo "Replica: ${REPLICA} (absent)"
    elif [[ "$replica_repl" != "0" ]]; then
        echo "Replica: ${REPLICA} (mirroring output ${replica_repl})"
    else
        echo "Replica: ${REPLICA} (${replica_state}, no mirror)"
    fi

    if is_mirror_active; then
        echo "State:   mirror active"
    else
        echo "State:   mirror off"
    fi
}

do_enable() {
    if is_mirror_active; then
        log_info "Mirror already active. Nothing to do."
        return 0
    fi

    log_info "Enabling ${SOURCE} and setting ${REPLICA} to mirror it..."
    if kscreen-doctor "output.${SOURCE}.enable" "output.${REPLICA}.mirror.${SOURCE}"; then
        log_success "Done. Mirror active."
        return 0
    else
        log_error "kscreen-doctor failed while enabling the mirror."
        return 1
    fi
}

do_disable() {
    if ! is_mirror_active; then
        log_info "Mirror already off. Nothing to do."
        return 0
    fi

    log_info "Clearing mirror and disabling ${SOURCE}..."
    if kscreen-doctor "output.${REPLICA}.mirror.none" "output.${SOURCE}.disable"; then
        log_success "Done. Mirror off."
        return 0
    else
        log_error "kscreen-doctor failed while disabling the mirror."
        return 1
    fi
}

main() {
    local mode="toggle"
    local enable_set=false
    local disable_set=false
    local status_set=false
    SOURCE="$DEFAULT_SOURCE"
    REPLICA="$DEFAULT_REPLICA"
    QUIET="false"

    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                usage
                exit 0
                ;;
            -v|--version)
                echo "${SCRIPT_NAME%.sh} v${VERSION}"
                exit 0
                ;;
            -s|--source)
                if [[ $# -lt 2 || "$2" =~ ^- ]]; then
                    log_error "Error: ${1} requires a connector name."
                    exit 1
                fi
                SOURCE="$2"
                shift 2
                ;;
            -r|--replica)
                if [[ $# -lt 2 || "$2" =~ ^- ]]; then
                    log_error "Error: ${1} requires a connector name."
                    exit 1
                fi
                REPLICA="$2"
                shift 2
                ;;
            --status)
                status_set=true
                mode="status"
                shift
                ;;
            --enable)
                enable_set=true
                mode="enable"
                shift
                ;;
            --disable)
                disable_set=true
                mode="disable"
                shift
                ;;
            -q|--quiet)
                QUIET="true"
                shift
                ;;
            *)
                log_error "Unknown option: $1"
                usage >&2
                exit 1
                ;;
        esac
    done

    # Reject conflicting mode flags
    local mode_count=0
    $enable_set && ((++mode_count)) || true
    $disable_set && ((++mode_count)) || true
    $status_set && ((++mode_count)) || true
    if [[ $mode_count -gt 1 ]]; then
        log_error "Error: --enable, --disable, and --status are mutually exclusive."
        exit 1
    fi

    check_requirements

    case $mode in
        status)
            show_status
            exit 0
            ;;
        enable)
            do_enable
            exit $?
            ;;
        disable)
            do_disable
            exit $?
            ;;
        toggle)
            if is_mirror_active; then
                do_disable
                exit $?
            else
                do_enable
                exit $?
            fi
            ;;
    esac
}

main "$@"
