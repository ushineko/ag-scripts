#!/bin/bash
set -u

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if script is run as root (we generally want to run as user and sudo when needed)
# but if run as root, $USER might be root, which isn't what we usually want for the user add part.
# We'll assume the user runs this as their normal user.

if [ "$EUID" -eq 0 ]; then
   log_warn "Running as root. This script is designed to be run as a standard user with sudo privileges."
   # If running as root via sudo, SUDO_USER will be set.
   if [ -n "${SUDO_USER-}" ]; then
       REAL_USER="$SUDO_USER"
   else
       REAL_USER=$(whoami)
   fi
else
   REAL_USER=$(whoami)
fi

log_info "Setting up Docker for user: $REAL_USER"

# 1. Install Docker if not present
if ! command -v docker &> /dev/null; then
    log_info "Docker not found. Installing..."
    if ! sudo pacman -S --noconfirm --needed docker docker-buildx; then
        log_error "Failed to install docker. Please check your pacman configuration."
        exit 1
    fi
    log_info "Docker installed successfully."
else
    log_info "Docker is already installed."
fi

# 2. Enable and Start Docker Service
log_info "Ensuring Docker service is active..."
if ! systemctl is-active --quiet docker; then
    log_info "Starting Docker service..."
    sudo systemctl enable --now docker
else
    log_info "Docker service is already running."
fi

# 3. User Group Configuration
if groups "$REAL_USER" | grep &>/dev/null '\bdocker\b'; then
    log_info "User $REAL_USER is already in the 'docker' group."
    GROUP_ALREADY_ACTIVE=true
else
    log_info "Adding $REAL_USER to 'docker' group..."
    sudo usermod -aG docker "$REAL_USER"
    log_info "User added to docker group."
    GROUP_ALREADY_ACTIVE=false
fi

# 4. Verification
verify_docker() {
    log_info "Verifying Docker access..."
    
    # Check daemon access
    if docker ps &>/dev/null; then
        log_info "Successfully connected to Docker daemon."
    else
        log_error "Cannot connect to Docker daemon. You might need to re-login for group changes to take full effect."
        # Attempt to show why
        docker ps
        return 1
    fi

    # Run test container
    log_info "Running test container..."
    if docker run --rm hello-world &>/dev/null; then
        log_info "Test container ran successfully! (hello-world)"
    elif docker run --rm alpine echo "Test" &>/dev/null; then
         log_info "Test container ran successfully! (alpine)"
    else
        log_error "Failed to run test container."
        return 1
    fi
    
    log_info "Docker setup complete and verified!"
}

# If group was just added, we need to run verification in a new group context
if [ "$GROUP_ALREADY_ACTIVE" = false ]; then
    log_warn "Group membership updated. Using 'sg' to verify without logout..."
    # Export the function so bash -c can use it? No, sg takes a command.
    # We'll just run the commands directly via sg
    
    sg docker -c "if docker ps >/dev/null; then echo 'Daemon Check: OK'; else echo 'Daemon Check: FAIL'; exit 1; fi"
    if [ $? -eq 0 ]; then
        log_info "Daemon check passed via sg."
        sg docker -c "docker run --rm hello-world >/dev/null && echo 'Container Check: OK'"
    else
         log_error "Verification failed even with sg. A full logout/login is recommended."
    fi
else
    verify_docker
fi

if [ "$GROUP_ALREADY_ACTIVE" = false ]; then
    echo ""
    log_warn "IMPORTANT: Group changes have been applied."
    log_warn "To run Docker commands in your CURRENT shell, run:"
    echo -e "    ${GREEN}newgrp docker${NC}"
    log_warn "Or log out and log back in to apply changes system-wide."
    echo ""
fi
