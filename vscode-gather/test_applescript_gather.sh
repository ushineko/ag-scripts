#!/usr/bin/env bash
# Test script for validating AppleScript-based window gathering on macOS.
# Run from Terminal.app (or iTerm2) after granting Accessibility access:
#   System Settings → Privacy & Security → Accessibility → add your terminal app
#
# Usage:
#   ./test_applescript_gather.sh              # enumerate VS Code windows (read-only)
#   ./test_applescript_gather.sh --move       # actually move + resize windows
#   ./test_applescript_gather.sh --dry-run    # print the AppleScript without running

set -euo pipefail

MODE="${1:-}"

echo "=== Test 1: Accessibility permission check ==="
if osascript -e 'tell application "System Events" to get name of first process whose frontmost is true' >/dev/null 2>&1; then
    echo "PASS: Accessibility access granted"
else
    echo "FAIL: Accessibility access denied (error -25211)"
    echo "  → Grant access in System Settings → Privacy & Security → Accessibility"
    echo "  → Add: $(ps -p $PPID -o comm= 2>/dev/null || echo 'your terminal app')"
    exit 1
fi

echo ""
echo "=== Test 2: VS Code process detection ==="
VS_CODE_NAME=$(osascript -e '
tell application "System Events"
    set codeProcs to every process whose name is "Code"
    if (count of codeProcs) > 0 then
        return name of first item of codeProcs
    else
        return "NOT_FOUND"
    end if
end tell
' 2>&1)
if [[ "$VS_CODE_NAME" == "NOT_FOUND" ]]; then
    echo "FAIL: No process named 'Code' found. Is VS Code running?"
    exit 1
fi
echo "PASS: Found process: $VS_CODE_NAME"

echo ""
echo "=== Test 3: Window enumeration ==="
WINDOW_INFO=$(osascript -e '
tell application "System Events"
    set codeProc to first process whose name is "Code"
    set windowCount to count of windows of codeProc
    set results to "Window count: " & windowCount & linefeed
    repeat with w in (windows of codeProc)
        set results to results & "  - " & (name of w) & linefeed
        set {x, y} to position of w
        set {pw, ph} to size of w
        set results to results & "    position: (" & x & ", " & y & "), size: " & pw & "x" & ph & linefeed
    end repeat
    return results
end tell
' 2>&1)
echo "$WINDOW_INFO"

echo ""
echo "=== Test 4: Display detection ==="
DISPLAY_INFO=$(system_profiler SPDisplaysDataType -json 2>/dev/null)
echo "$DISPLAY_INFO" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for gpu in data.get('SPDisplaysDataType', []):
    for disp in gpu.get('spdisplays_ndrvs', []):
        name = disp.get('_name', 'unknown')
        main = disp.get('spdisplays_main', 'spdisplays_no')
        res = disp.get('_spdisplays_resolution', 'unknown')
        is_main = '(PRIMARY)' if main == 'spdisplays_yes' else ''
        print(f'  Display: {name} {is_main}')
        print(f'    Resolution: {res}')
"

if [[ "$MODE" == "--dry-run" ]]; then
    echo ""
    echo "=== Dry-run: AppleScript that would gather windows ==="
    cat <<'APPLESCRIPT'
tell application "System Events"
    set codeProc to first process whose name is "Code"
    -- Get screen bounds (approximation: use desktop bounds)
    tell application "Finder"
        set {deskLeft, deskTop, deskRight, deskBottom} to bounds of window of desktop
    end tell
    set screenW to deskRight - deskLeft
    set screenH to deskBottom - deskTop

    repeat with w in (windows of codeProc)
        set position of w to {deskLeft, deskTop}
        set size of w to {screenW, screenH}
    end repeat
end tell
APPLESCRIPT
    exit 0
fi

if [[ "$MODE" == "--move" ]]; then
    echo ""
    echo "=== Test 5: Gather + maximize windows ==="
    RESULT=$(osascript -e '
    tell application "System Events"
        set codeProc to first process whose name is "Code"
        set windowCount to count of windows of codeProc
        if windowCount = 0 then
            return "No windows to move"
        end if
    end tell

    -- Get usable desktop area (excludes menu bar and dock)
    tell application "Finder"
        set {deskLeft, deskTop, deskRight, deskBottom} to bounds of window of desktop
    end tell
    set screenW to deskRight - deskLeft
    set screenH to deskBottom - deskTop

    tell application "System Events"
        set codeProc to first process whose name is "Code"
        set moved to 0
        repeat with w in (windows of codeProc)
            set position of w to {deskLeft, deskTop}
            set size of w to {screenW, screenH}
            set moved to moved + 1
        end repeat
        return "Moved and maximized " & moved & " window(s) to (" & deskLeft & "," & deskTop & ") " & screenW & "x" & screenH
    end tell
    ' 2>&1)
    echo "$RESULT"

    echo ""
    echo "=== Verify: Window positions after gather ==="
    osascript -e '
    tell application "System Events"
        set codeProc to first process whose name is "Code"
        set results to ""
        repeat with w in (windows of codeProc)
            set {x, y} to position of w
            set {pw, ph} to size of w
            set results to results & "  - " & (name of w) & linefeed
            set results to results & "    position: (" & x & ", " & y & "), size: " & pw & "x" & ph & linefeed
        end repeat
        return results
    end tell
    '
else
    echo ""
    echo "Read-only mode. Use --move to test window gathering, --dry-run to see the script."
fi
