#!/usr/bin/env bash
# Tests for display-mirror-toggle.sh
# Run: ./tests/test_display_mirror_toggle.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="${SCRIPT_DIR}/display-mirror-toggle.sh"

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

echo "Running display-mirror-toggle tests..."
echo

# Test 1: Script exists and is executable
echo "Test: Script exists and is executable"
if [[ -x "$SCRIPT" ]]; then
    pass "Script is executable"
else
    fail "Script not executable"
fi

# Test 2: --help shows usage
echo "Test: --help flag"
output=$("$SCRIPT" --help)
if echo "$output" | grep -q "Usage:"; then
    pass "--help shows usage"
else
    fail "--help does not show usage"
fi

# Test 3: --help mentions --source
echo "Test: --help mentions --source"
output=$("$SCRIPT" --help)
if echo "$output" | grep -q -- "--source"; then
    pass "--help includes --source"
else
    fail "--help missing --source"
fi

# Test 4: --help mentions --replica
echo "Test: --help mentions --replica"
output=$("$SCRIPT" --help)
if echo "$output" | grep -q -- "--replica"; then
    pass "--help includes --replica"
else
    fail "--help missing --replica"
fi

# Test 5: --help mentions --enable, --disable, --status
echo "Test: --help mentions mode flags"
output=$("$SCRIPT" --help)
if echo "$output" | grep -q -- "--enable" && \
   echo "$output" | grep -q -- "--disable" && \
   echo "$output" | grep -q -- "--status"; then
    pass "--help includes all mode flags"
else
    fail "--help missing one or more mode flags"
fi

# Test 6: --version prints version
echo "Test: --version flag"
output=$("$SCRIPT" --version)
if echo "$output" | grep -qE "display-mirror-toggle v[0-9]+\."; then
    pass "--version shows version"
else
    fail "--version unexpected output: $output"
fi

# Test 7: Invalid option exits non-zero
echo "Test: Invalid option handling"
if ! "$SCRIPT" --not-a-real-flag &>/dev/null; then
    pass "Invalid option returns error"
else
    fail "Invalid option should return error"
fi

# Test 8: --source without value exits non-zero
echo "Test: --source requires value"
if ! "$SCRIPT" --source 2>/dev/null; then
    pass "--source without value returns error"
else
    fail "--source without value should return error"
fi

# Test 9: --source consuming another flag exits non-zero
echo "Test: --source rejects flag-like value"
if ! "$SCRIPT" --source --replica DP-3 2>/dev/null; then
    pass "--source rejects flag-like value"
else
    fail "--source should reject flag-like value"
fi

# Test 10: --replica without value exits non-zero
echo "Test: --replica requires value"
if ! "$SCRIPT" --replica 2>/dev/null; then
    pass "--replica without value returns error"
else
    fail "--replica without value should return error"
fi

# Test 11: Conflicting modes exit non-zero
echo "Test: --enable and --disable are mutually exclusive"
if ! "$SCRIPT" --enable --disable 2>/dev/null; then
    pass "Conflicting modes return error"
else
    fail "Conflicting modes should return error"
fi

# Test 12: --status and --enable are mutually exclusive
echo "Test: --status and --enable are mutually exclusive"
if ! "$SCRIPT" --status --enable 2>/dev/null; then
    pass "--status + --enable returns error"
else
    fail "--status + --enable should return error"
fi

# Test 13: Missing kscreen-doctor exits with code 2
echo "Test: Missing kscreen-doctor exits with code 2"
# Resolve bash by absolute path before stripping PATH, otherwise the outer
# shell can't even invoke the child bash. Use --status so the script takes
# the read-only path.
BASH_BIN="$(command -v bash)"
set +e
PATH="/nonexistent" "$BASH_BIN" "$SCRIPT" --status &>/dev/null
rc=$?
set -e
if [[ $rc -eq 2 ]]; then
    pass "Exit code 2 when kscreen-doctor absent"
else
    fail "Expected exit 2, got $rc"
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
