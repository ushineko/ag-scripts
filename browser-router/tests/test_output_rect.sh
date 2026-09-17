#!/usr/bin/env bash
# Tests for output_rect(): the scale/rotation arithmetic that maps a kscreen
# output to the logical rectangle KWin's getWindowInfo reports windows in.
# Pure jq + fixture JSON, no D-Bus and no compositor needed.

set -uo pipefail
cd "$(dirname "$0")" || exit 1

FIXTURE="fixtures/kscreen-njv-cachyos.json"
fails=0

# Stub kscreen-doctor with the fixture, then source only the function under test
# out of the router (sourcing the whole script would route a URL).
kscreen-doctor() { cat "$FIXTURE"; }
export -f kscreen-doctor 2>/dev/null || true
eval "$(sed -n '/^output_rect() {/,/^}/p' ../browser-router.sh)"

check() {
    local desc="$1" want="$2" got="$3"
    if [[ "$got" == "$want" ]]; then
        echo "ok   - $desc"
    else
        echo "FAIL - $desc: want '$want', got '$got'"
        fails=$((fails + 1))
    fi
}

# DP-3: landscape, pos 0,1120, mode 3840x2160 at scale 1.5 -> logical 2560x1440.
check "explicit landscape output" "0 1120 2560 1440" "$(output_rect DP-3)"

# DP-2: portrait. kscreen reports `size` already rotated (2160x3840), so the
# scale divide alone must yield 1440x2560 -- no extra transpose.
check "explicit portrait output" "2560 0 1440 2560" "$(output_rect DP-2)"

# auto resolves the lowest `priority`, which is Plasma's primary (DP-3 here).
check "auto picks priority 1" "0 1120 2560 1440" "$(output_rect auto)"
check "no argument defaults to auto" "0 1120 2560 1440" "$(output_rect)"

# A connector that is not present must FAIL, so the caller falls back to auto
# rather than activating a window on the wrong monitor. This is the regression:
# the old code hardcoded HDMI-A-1 and silently did nothing once it disappeared.
if output_rect HDMI-A-1 >/dev/null 2>&1; then
    echo "FAIL - absent connector must not resolve"
    fails=$((fails + 1))
else
    echo "ok   - absent connector fails so the caller can fall back"
fi

# A connected-but-disabled output is not a valid target either.
if output_rect DP-1 >/dev/null 2>&1; then
    echo "FAIL - disabled output must not resolve"
    fails=$((fails + 1))
else
    echo "ok   - disabled output fails"
fi

if (( fails )); then
    echo "$fails test(s) failed"
    exit 1
fi
echo "all tests passed"
