#!/bin/bash
# capture_window_screenshot.sh - Capture a screenshot of a specific window
# Uses kdotool (KDE) for window management and spectacle for screenshots
# Wayland-compatible
#
# Usage:
#   ./capture_window_screenshot.sh <app_identifier> <output_path> [--launch "<command>"]
#
# Examples:
#   ./capture_window_screenshot.sh "peripheral-battery-monitor" assets/screenshot.png
#   ./capture_window_screenshot.sh "Battery Monitor" screenshot.png --launch "python3 app.py"

set -euo pipefail

VERSION="1.0.0"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

usage() {
    cat << EOF
Usage: $(basename "$0") <app_identifier> <output_path> [options]

Capture a screenshot of a specific window for README documentation.

Arguments:
  app_identifier    Window class name or title to search for (case-insensitive)
  output_path       Where to save the screenshot (PNG)

Options:
  --launch <cmd>    Command to launch the app if not running
  --delay <secs>    Delay before screenshot (default: 1)
  --help            Show this help message
  --version         Show version

Examples:
  $(basename "$0") "peripheral-battery-monitor" assets/screenshot.png
  $(basename "$0") "Battery Monitor" shot.png --launch "python3 app.py" --delay 2
EOF
    exit 0
}

error() {
    echo -e "${RED}Error: $1${NC}" >&2
    exit 1
}

info() {
    echo -e "${GREEN}$1${NC}"
}

warn() {
    echo -e "${YELLOW}$1${NC}"
}

# Check dependencies
check_deps() {
    local missing=()

    if ! command -v kdotool &> /dev/null; then
        missing+=("kdotool")
    fi

    if ! command -v spectacle &> /dev/null; then
        missing+=("spectacle")
    fi

    if [ ${#missing[@]} -gt 0 ]; then
        error "Missing dependencies: ${missing[*]}\nInstall with: sudo pacman -S ${missing[*]}"
    fi
}

# Find window by class name or title
find_window() {
    local identifier="$1"
    local window_id=""

    # Try searching by class name first (more reliable)
    window_id=$(kdotool search --class "$identifier" 2>/dev/null | head -1)

    if [ -z "$window_id" ]; then
        # Fall back to searching by name/title
        window_id=$(kdotool search --name "$identifier" 2>/dev/null | head -1)
    fi

    echo "$window_id"
}

# Main
main() {
    local app_identifier=""
    local output_path=""
    local launch_cmd=""
    local delay=1

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --help)
                usage
                ;;
            --version)
                echo "capture_window_screenshot.sh v$VERSION"
                exit 0
                ;;
            --launch)
                launch_cmd="$2"
                shift 2
                ;;
            --delay)
                delay="$2"
                shift 2
                ;;
            -*)
                error "Unknown option: $1"
                ;;
            *)
                if [ -z "$app_identifier" ]; then
                    app_identifier="$1"
                elif [ -z "$output_path" ]; then
                    output_path="$1"
                else
                    error "Too many arguments"
                fi
                shift
                ;;
        esac
    done

    # Validate required arguments
    if [ -z "$app_identifier" ] || [ -z "$output_path" ]; then
        error "Missing required arguments. Use --help for usage."
    fi

    check_deps

    info "Looking for window: $app_identifier"

    # Find the window
    local window_id
    window_id=$(find_window "$app_identifier")

    # If not found and launch command provided, try launching
    if [ -z "$window_id" ] && [ -n "$launch_cmd" ]; then
        warn "Window not found. Launching: $launch_cmd"
        eval "$launch_cmd" &

        # Wait for window to appear (up to 10 seconds)
        local attempts=0
        while [ -z "$window_id" ] && [ $attempts -lt 20 ]; do
            sleep 0.5
            window_id=$(find_window "$app_identifier")
            ((attempts++))
        done
    fi

    if [ -z "$window_id" ]; then
        error "Could not find window matching: $app_identifier"
    fi

    info "Found window ID: $window_id"

    # Get window info for logging
    local window_name
    window_name=$(kdotool getwindowname "$window_id" 2>/dev/null || echo "Unknown")
    info "Window title: $window_name"

    # Bring window to front
    info "Activating window..."
    kdotool windowactivate "$window_id"
    kdotool windowraise "$window_id"

    # Wait for window to settle
    info "Waiting ${delay}s for window to settle..."
    sleep "$delay"

    # Ensure output directory exists
    local output_dir
    output_dir=$(dirname "$output_path")
    if [ -n "$output_dir" ] && [ "$output_dir" != "." ]; then
        mkdir -p "$output_dir"
    fi

    # Capture screenshot of the window
    info "Capturing screenshot..."

    # spectacle options:
    # -a = active window
    # -b = include window decorations
    # -n = no notification
    # -o = output file
    spectacle -a -b -n -o "$output_path"

    if [ -f "$output_path" ]; then
        info "Screenshot saved to: $output_path"
        # Show file size
        local size
        size=$(du -h "$output_path" | cut -f1)
        info "File size: $size"
    else
        error "Failed to save screenshot"
    fi
}

main "$@"
