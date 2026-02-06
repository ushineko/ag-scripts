#!/bin/bash
# uninstall.sh - Remove SSH agent auto-load configuration
#
# Removes:
#   ~/.local/bin/ssh-agent-load.sh
#   ~/.config/systemd/user/ssh-add.service
#   ~/.config/environment.d/ssh-askpass.conf
#   ~/.config/ssh-agent-setup/ (directory)

set -euo pipefail

DRY_RUN=false
KEEP_CONFIG=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run|-n)
            DRY_RUN=true
            shift
            ;;
        --keep-config)
            KEEP_CONFIG=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--dry-run|-n] [--keep-config]"
            echo ""
            echo "Removes SSH agent auto-load configuration."
            echo ""
            echo "Options:"
            echo "  --dry-run, -n   Show what would be done without making changes"
            echo "  --keep-config   Keep the keys.conf file (preserve key list)"
            echo "  --help, -h      Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

# Remove file if exists
remove_file() {
    local path="$1"
    if [[ -f "$path" ]]; then
        if $DRY_RUN; then
            info "[DRY-RUN] Would remove: $path"
        else
            rm -f "$path"
            info "Removed: $path"
        fi
    else
        info "Already removed: $path"
    fi
}

# Remove directory if exists and empty (or force)
remove_dir() {
    local path="$1"
    local force="${2:-false}"
    if [[ -d "$path" ]]; then
        if $DRY_RUN; then
            info "[DRY-RUN] Would remove directory: $path"
        else
            if $force; then
                rm -rf "$path"
            else
                rmdir "$path" 2>/dev/null || warn "Directory not empty, keeping: $path"
                return
            fi
            info "Removed directory: $path"
        fi
    fi
}

main() {
    echo "SSH Agent Auto-Load Uninstall"
    echo "=============================="
    echo ""

    if $DRY_RUN; then
        warn "DRY-RUN mode - no changes will be made"
        echo ""
    fi

    # Define paths
    LOCAL_BIN="$HOME/.local/bin"
    SYSTEMD_USER="$HOME/.config/systemd/user"
    ENVIRONMENT_D="$HOME/.config/environment.d"
    CONFIG_DIR="$HOME/.config/ssh-agent-setup"

    # Disable service first
    if systemctl --user is-enabled ssh-add.service &>/dev/null; then
        if $DRY_RUN; then
            info "[DRY-RUN] Would disable ssh-add.service"
        else
            info "Disabling systemd service..."
            systemctl --user disable ssh-add.service 2>/dev/null || true
        fi
    fi

    # Stop service if running
    if systemctl --user is-active ssh-add.service &>/dev/null; then
        if $DRY_RUN; then
            info "[DRY-RUN] Would stop ssh-add.service"
        else
            systemctl --user stop ssh-add.service 2>/dev/null || true
        fi
    fi
    echo ""

    # Remove files
    info "Removing installed files..."
    remove_file "$LOCAL_BIN/ssh-agent-load.sh"
    remove_file "$SYSTEMD_USER/ssh-add.service"
    remove_file "$ENVIRONMENT_D/ssh-askpass.conf"
    echo ""

    # Handle config directory
    if $KEEP_CONFIG; then
        info "Keeping config directory: $CONFIG_DIR (--keep-config specified)"
    else
        info "Removing config directory..."
        remove_dir "$CONFIG_DIR" true
    fi
    echo ""

    # Reload systemd
    if ! $DRY_RUN; then
        info "Reloading systemd user daemon..."
        systemctl --user daemon-reload
    fi

    echo "=============================="
    if $DRY_RUN; then
        info "DRY-RUN complete. Run without --dry-run to apply changes."
    else
        info "Uninstall complete!"
        echo ""
        echo "Note: KWallet may still have stored passphrases."
        echo "To remove them, open KWalletManager and delete entries under 'ksshaskpass'."
    fi
}

main
