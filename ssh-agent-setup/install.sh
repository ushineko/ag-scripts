#!/bin/bash
# install.sh - Set up automatic SSH key loading on Plasma desktop login
#
# Creates:
#   ~/.local/bin/ssh-agent-load.sh       - loader script
#   ~/.config/systemd/user/ssh-add.service - systemd user service
#   ~/.config/environment.d/ssh-askpass.conf - SSH_ASKPASS environment
#   ~/.config/ssh-agent-setup/keys.conf  - configurable key list

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRY_RUN=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run|-n)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--dry-run|-n]"
            echo ""
            echo "Sets up automatic SSH key loading on Plasma desktop login"
            echo "using KWallet for secure passphrase storage."
            echo ""
            echo "Options:"
            echo "  --dry-run, -n  Show what would be done without making changes"
            echo "  --help, -h     Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check prerequisites
check_prerequisites() {
    local missing=()

    if ! command -v ksshaskpass &>/dev/null; then
        missing+=("ksshaskpass")
    fi

    if ! command -v ssh-add &>/dev/null; then
        missing+=("openssh (ssh-add)")
    fi

    if ! systemctl --user list-unit-files &>/dev/null; then
        missing+=("systemd user session")
    fi

    if [[ ${#missing[@]} -gt 0 ]]; then
        error "Missing prerequisites:"
        for pkg in "${missing[@]}"; do
            echo "  - $pkg"
        done
        echo ""
        echo "Install ksshaskpass with: sudo pacman -S ksshaskpass"
        return 1
    fi

    return 0
}

# Create directory if it doesn't exist
ensure_dir() {
    local dir="$1"
    if [[ ! -d "$dir" ]]; then
        if $DRY_RUN; then
            info "[DRY-RUN] Would create directory: $dir"
        else
            mkdir -p "$dir"
            info "Created directory: $dir"
        fi
    fi
}

# Copy file with message
install_file() {
    local src="$1"
    local dest="$2"
    local mode="${3:-644}"

    if $DRY_RUN; then
        info "[DRY-RUN] Would install: $dest"
    else
        cp "$src" "$dest"
        chmod "$mode" "$dest"
        info "Installed: $dest"
    fi
}

main() {
    echo "SSH Agent Auto-Load Setup"
    echo "========================="
    echo ""

    if $DRY_RUN; then
        warn "DRY-RUN mode - no changes will be made"
        echo ""
    fi

    # Check prerequisites
    info "Checking prerequisites..."
    if ! check_prerequisites; then
        exit 1
    fi
    info "All prerequisites satisfied"
    echo ""

    # Define paths
    LOCAL_BIN="$HOME/.local/bin"
    SYSTEMD_USER="$HOME/.config/systemd/user"
    ENVIRONMENT_D="$HOME/.config/environment.d"
    CONFIG_DIR="$HOME/.config/ssh-agent-setup"

    # Create directories
    info "Creating directories..."
    ensure_dir "$LOCAL_BIN"
    ensure_dir "$SYSTEMD_USER"
    ensure_dir "$ENVIRONMENT_D"
    ensure_dir "$CONFIG_DIR"
    echo ""

    # Install loader script
    info "Installing loader script..."
    install_file "$SCRIPT_DIR/ssh-agent-load.sh" "$LOCAL_BIN/ssh-agent-load.sh" "755"

    # Install systemd service
    info "Installing systemd user service..."
    install_file "$SCRIPT_DIR/ssh-add.service" "$SYSTEMD_USER/ssh-add.service"

    # Install environment config
    info "Installing SSH_ASKPASS environment..."
    install_file "$SCRIPT_DIR/ssh-askpass.conf" "$ENVIRONMENT_D/ssh-askpass.conf"

    # Install keys config (only if not exists to preserve user edits)
    if [[ ! -f "$CONFIG_DIR/keys.conf" ]]; then
        info "Installing default keys config..."
        install_file "$SCRIPT_DIR/keys.conf.template" "$CONFIG_DIR/keys.conf"
    else
        if $DRY_RUN; then
            info "[DRY-RUN] Would keep existing: $CONFIG_DIR/keys.conf"
        else
            info "Keeping existing keys config: $CONFIG_DIR/keys.conf"
        fi
    fi
    echo ""

    # Enable service
    if $DRY_RUN; then
        info "[DRY-RUN] Would reload systemd user daemon"
        info "[DRY-RUN] Would enable ssh-add.service"
    else
        info "Enabling systemd service..."
        systemctl --user daemon-reload
        systemctl --user enable ssh-add.service
    fi
    echo ""

    # Show summary
    echo "========================="
    if $DRY_RUN; then
        info "DRY-RUN complete. Run without --dry-run to apply changes."
    else
        info "Installation complete!"
        echo ""
        echo "Next steps:"
        echo "  1. Edit your key list: $CONFIG_DIR/keys.conf"
        echo "  2. Log out and log back in"
        echo "  3. On first login, KWallet will prompt for each key's passphrase"
        echo "  4. Subsequent logins will load keys automatically"
        echo ""
        echo "To test immediately (without relogging):"
        echo "  systemctl --user start ssh-add.service"
        echo "  ssh-add -l"
    fi
}

main
