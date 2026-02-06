#!/bin/bash
# test_installation.sh - Test install.sh and uninstall.sh functionality
#
# Run with: ./tests/test_installation.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TESTS_PASSED=0
TESTS_FAILED=0

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

pass() {
    echo -e "${GREEN}PASS${NC}: $1"
    ((TESTS_PASSED++)) || true
}

fail() {
    echo -e "${RED}FAIL${NC}: $1"
    ((TESTS_FAILED++)) || true
}

# Test: install.sh exists and is executable
test_install_exists() {
    if [[ -x "$SCRIPT_DIR/install.sh" ]]; then
        pass "install.sh exists and is executable"
    else
        fail "install.sh not found or not executable"
    fi
}

# Test: uninstall.sh exists and is executable
test_uninstall_exists() {
    if [[ -x "$SCRIPT_DIR/uninstall.sh" ]]; then
        pass "uninstall.sh exists and is executable"
    else
        fail "uninstall.sh not found or not executable"
    fi
}

# Test: loader script exists and is executable
test_loader_exists() {
    if [[ -x "$SCRIPT_DIR/ssh-agent-load.sh" ]]; then
        pass "ssh-agent-load.sh exists and is executable"
    else
        fail "ssh-agent-load.sh not found or not executable"
    fi
}

# Test: systemd service template exists
test_service_exists() {
    if [[ -f "$SCRIPT_DIR/ssh-add.service" ]]; then
        pass "ssh-add.service exists"
    else
        fail "ssh-add.service not found"
    fi
}

# Test: install.sh --help works
test_install_help() {
    if "$SCRIPT_DIR/install.sh" --help &>/dev/null; then
        pass "install.sh --help exits cleanly"
    else
        fail "install.sh --help failed"
    fi
}

# Test: uninstall.sh --help works
test_uninstall_help() {
    if "$SCRIPT_DIR/uninstall.sh" --help &>/dev/null; then
        pass "uninstall.sh --help exits cleanly"
    else
        fail "uninstall.sh --help failed"
    fi
}

# Test: install.sh --dry-run works (if ksshaskpass installed)
test_install_dryrun() {
    if command -v ksshaskpass &>/dev/null; then
        if "$SCRIPT_DIR/install.sh" --dry-run &>/dev/null; then
            pass "install.sh --dry-run completes successfully"
        else
            fail "install.sh --dry-run failed"
        fi
    else
        echo "SKIP: install.sh --dry-run (ksshaskpass not installed)"
    fi
}

# Test: uninstall.sh --dry-run works
test_uninstall_dryrun() {
    if "$SCRIPT_DIR/uninstall.sh" --dry-run &>/dev/null; then
        pass "uninstall.sh --dry-run completes successfully"
    else
        fail "uninstall.sh --dry-run failed"
    fi
}

# Test: loader script handles missing config gracefully
test_loader_no_config() {
    # Temporarily move config if it exists
    local config="$HOME/.config/ssh-agent-setup/keys.conf"
    local backup=""
    if [[ -f "$config" ]]; then
        backup=$(mktemp)
        mv "$config" "$backup"
    fi

    if "$SCRIPT_DIR/ssh-agent-load.sh" 2>/dev/null; then
        pass "ssh-agent-load.sh handles missing config gracefully"
    else
        fail "ssh-agent-load.sh fails with missing config"
    fi

    # Restore config
    if [[ -n "$backup" ]]; then
        mv "$backup" "$config"
    fi
}

# Test: systemd service file has correct format
test_service_format() {
    if grep -q '\[Unit\]' "$SCRIPT_DIR/ssh-add.service" && \
       grep -q '\[Service\]' "$SCRIPT_DIR/ssh-add.service" && \
       grep -q '\[Install\]' "$SCRIPT_DIR/ssh-add.service"; then
        pass "ssh-add.service has correct systemd format"
    else
        fail "ssh-add.service missing required sections"
    fi
}

# Test: service references ksshaskpass
test_service_askpass() {
    if grep -q 'SSH_ASKPASS=ksshaskpass' "$SCRIPT_DIR/ssh-add.service"; then
        pass "ssh-add.service sets SSH_ASKPASS correctly"
    else
        fail "ssh-add.service missing SSH_ASKPASS"
    fi
}

# Run all tests
main() {
    echo "SSH Agent Setup - Installation Tests"
    echo "====================================="
    echo ""

    test_install_exists
    test_uninstall_exists
    test_loader_exists
    test_service_exists
    test_install_help
    test_uninstall_help
    test_install_dryrun
    test_uninstall_dryrun
    test_loader_no_config
    test_service_format
    test_service_askpass

    echo ""
    echo "====================================="
    echo "Results: $TESTS_PASSED passed, $TESTS_FAILED failed"

    if [[ $TESTS_FAILED -gt 0 ]]; then
        exit 1
    fi
}

main
