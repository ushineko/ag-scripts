#!/bin/bash
# Simple tests for bluetooth-reset.sh
# Run: ./tests/test_bluetooth_reset.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="${SCRIPT_DIR}/bluetooth-reset.sh"

PASSED=0
FAILED=0

pass() {
    echo "  PASS: $1"
    ((++PASSED)) || true
}

fail() {
    echo "  FAIL: $1"
    ((++FAILED)) || true
}

echo "Running bluetooth-reset tests..."
echo

# Test 1: Script exists and is executable
echo "Test: Script exists and is executable"
if [[ -x "$SCRIPT" ]]; then
    pass "Script is executable"
else
    fail "Script not executable"
fi

# Test 2: Help flag works
echo "Test: --help flag"
output=$("$SCRIPT" --help)
if echo "$output" | grep -q "Usage:"; then
    pass "--help shows usage"
else
    fail "--help doesn't show usage"
fi

# Test 3: Version flag works
echo "Test: --version flag"
output=$("$SCRIPT" --version)
if echo "$output" | grep -q "bluetooth-reset v"; then
    pass "--version shows version"
else
    fail "--version doesn't show version"
fi

# Test 4: Invalid option returns error
echo "Test: Invalid option handling"
if ! "$SCRIPT" --invalid-option &>/dev/null; then
    pass "Invalid option returns error"
else
    fail "Invalid option should return error"
fi

# Test 5: --reconnect without pattern shows error
echo "Test: --reconnect requires pattern"
if ! "$SCRIPT" --reconnect 2>/dev/null; then
    pass "--reconnect without pattern returns error"
else
    fail "--reconnect without pattern should return error"
fi

# Test 6: --scan-timeout without value shows error
echo "Test: --scan-timeout requires number"
if ! "$SCRIPT" --scan-timeout 2>/dev/null; then
    pass "--scan-timeout without value returns error"
else
    fail "--scan-timeout without value should return error"
fi

# Test 7: --scan-timeout with non-number shows error
echo "Test: --scan-timeout rejects non-number"
if ! "$SCRIPT" --scan-timeout abc 2>/dev/null; then
    pass "--scan-timeout rejects non-number"
else
    fail "--scan-timeout should reject non-number"
fi

# Test 8: Help text includes reconnect option
echo "Test: Help text includes reconnect"
output=$("$SCRIPT" --help)
if echo "$output" | grep -q "\-r, --reconnect"; then
    pass "Help text includes --reconnect"
else
    fail "Help text missing --reconnect"
fi

# Test 9: Status flag works (if bluetooth available)
echo "Test: --status flag"
if systemctl list-unit-files bluetooth.service &>/dev/null; then
    output=$("$SCRIPT" --status)
    if echo "$output" | grep -q "Service:"; then
        pass "--status shows service info"
    else
        fail "--status doesn't show service info"
    fi
else
    echo "  SKIP: bluetooth.service not available"
fi

# Test 10: Quiet status works
echo "Test: --status --quiet flag"
if systemctl list-unit-files bluetooth.service &>/dev/null; then
    output=$("$SCRIPT" --status --quiet)
    if [[ "$output" == "active" || "$output" == "inactive" ]]; then
        pass "--status --quiet shows only status"
    else
        fail "--status --quiet unexpected output: $output"
    fi
else
    echo "  SKIP: bluetooth.service not available"
fi

# Summary
echo
echo "========================================="
echo "Results: ${PASSED} passed, ${FAILED} failed"
echo "========================================="

if [[ $FAILED -gt 0 ]]; then
    exit 1
fi
exit 0
