#!/usr/bin/env bash
# vscode-gather: Move all VS Code windows to the primary monitor and maximize them.
# Linux: KWin scripting via D-Bus (KDE Plasma 6 / Wayland)
# macOS: AppleScript via osascript

set -euo pipefail

VERSION="2.0"
SCRIPT_NAME="vscode-gather"
PLATFORM="$(uname -s)"
DEBUG=false
DRY_RUN=false
TARGET_CLASS="code"
TARGET_PROCESS="Code"
TARGET_OUTPUT=""

usage() {
    cat <<EOF
vscode-gather v${VERSION} — gather VS Code windows to one monitor

Usage: $(basename "$0") [OPTIONS]

Options:
  -o, --output NAME   Target output name. Default: primary monitor.
                       Linux: e.g. DP-3, HDMI-1
                       macOS: display name from --list-outputs (e.g. "Color LCD")
  -c, --class CLASS   Window class to match (default: code)
                       Linux: KWin resourceClass
                       macOS: also sets process name (default: Code)
  -l, --list-outputs  List available displays and exit
  -n, --dry-run       Print the generated script without running it
  -d, --debug         Enable debug output
  -h, --help          Show this help
  -v, --version       Show version
EOF
}

log() { echo "[gather] $*"; }
debug() { $DEBUG && echo "[gather:debug] $*" || true; }

# ---------------------------------------------------------------------------
# Display detection
# ---------------------------------------------------------------------------

detect_primary_output_linux() {
    local output_name=""
    while IFS= read -r line; do
        line=$(echo "$line" | sed 's/\x1b\[[0-9;]*m//g')
        if [[ "$line" =~ ^Output:\ +[0-9]+\ +([A-Za-z0-9_-]+) ]]; then
            output_name="${BASH_REMATCH[1]}"
        elif [[ "$line" =~ priority\ +1$ ]] && [[ -n "$output_name" ]]; then
            echo "$output_name"
            return 0
        elif [[ "$line" =~ priority\ +[0-9]+ ]]; then
            output_name=""
        fi
    done < <(kscreen-doctor --outputs 2>/dev/null)
    return 1
}

detect_primary_output_macos() {
    osascript -l JavaScript -e '
ObjC.import("AppKit");
var main = $.NSScreen.mainScreen;
if (main) {
    ObjC.unwrap(main.localizedName);
} else {
    null;
}
' 2>/dev/null || return 1
}

detect_primary_output() {
    case "$PLATFORM" in
        Linux)  detect_primary_output_linux ;;
        Darwin) detect_primary_output_macos ;;
        *)      log "ERROR: Unsupported platform: $PLATFORM"; return 1 ;;
    esac
}

list_outputs() {
    case "$PLATFORM" in
        Linux)
            log "Available outputs (via kscreen-doctor):"
            kscreen-doctor --outputs 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' \
                | grep -E "^Output:|priority" | sed 's/^/  /'
            ;;
        Darwin)
            log "Available displays (via NSScreen):"
            osascript -l JavaScript -e '
ObjC.import("AppKit");
var screens = $.NSScreen.screens;
var mainName = ObjC.unwrap($.NSScreen.mainScreen.localizedName);
for (var i = 0; i < screens.count; i++) {
    var s = screens.objectAtIndex(i);
    var name = ObjC.unwrap(s.localizedName);
    var f = s.frame;
    var tag = (name === mainName) ? " (PRIMARY)" : "";
    "  " + (i + 1) + ". " + name + tag + " — " + f.size.width + "x" + f.size.height;
}
' 2>/dev/null
            ;;
    esac
}

# ---------------------------------------------------------------------------
# Linux (KDE Plasma 6 / Wayland) — KWin scripting via D-Bus
# ---------------------------------------------------------------------------

generate_kwin_script() {
    local target_output="$1"
    local target_class="$2"

    cat <<JSEOF
(function() {
    var targetOutput = null;
    var screens = workspace.screens;
    for (var i = 0; i < screens.length; i++) {
        if (screens[i].name === "${target_output}") {
            targetOutput = screens[i];
            break;
        }
    }

    if (!targetOutput) {
        console.log("${SCRIPT_NAME}: ERROR - output '${target_output}' not found");
        return;
    }

    var moved = 0;
    var windows = workspace.windowList();
    for (var i = 0; i < windows.length; i++) {
        var w = windows[i];
        if (w.resourceClass !== "${target_class}") continue;
        if (w.skipTaskbar || w.specialWindow) continue;

        var wasOnTarget = (w.output && w.output.name === "${target_output}");

        workspace.sendClientToScreen(w, targetOutput);
        w.setMaximize(true, true);

        moved++;
        var status = wasOnTarget ? "maximized (already on target)" : "moved + maximized";
        console.log("${SCRIPT_NAME}: " + status + ": " + w.caption);
    }

    console.log("${SCRIPT_NAME}: processed " + moved + " window(s) to " + targetOutput.name);
})();
JSEOF
}

run_kwin_script() {
    local script_content="$1"
    local tmpfile
    tmpfile=$(mktemp "/tmp/${SCRIPT_NAME}-XXXXXX.js")
    echo "$script_content" > "$tmpfile"

    debug "Script file: $tmpfile"

    local script_id
    script_id=$(qdbus6 org.kde.KWin /Scripting org.kde.kwin.Scripting.loadScript "$tmpfile" "$SCRIPT_NAME")
    debug "Loaded script ID: $script_id"

    if [[ "$script_id" -lt 0 ]]; then
        log "ERROR: Failed to load KWin script (ID: $script_id)"
        rm -f "$tmpfile"
        return 1
    fi

    qdbus6 org.kde.KWin "/Scripting/Script${script_id}" org.kde.kwin.Script.run
    debug "Script executed"

    sleep 0.3

    if $DEBUG; then
        journalctl --user -u plasma-kwin_wayland --since "3 seconds ago" --no-pager 2>/dev/null \
            | grep "$SCRIPT_NAME" || true
    fi

    qdbus6 org.kde.KWin /Scripting org.kde.kwin.Scripting.unloadScript "$SCRIPT_NAME" >/dev/null 2>&1 || true

    rm -f "$tmpfile"
}

gather_linux() {
    local target_output="$1"
    local target_class="$2"

    local script
    script=$(generate_kwin_script "$target_output" "$target_class")

    if $DRY_RUN; then
        echo "$script"
        exit 0
    fi

    run_kwin_script "$script"
}

# ---------------------------------------------------------------------------
# macOS — AppleScript via osascript
# ---------------------------------------------------------------------------

get_display_bounds() {
    local target_name="$1"
    osascript -l JavaScript -e "
ObjC.import('AppKit');
var screens = $.NSScreen.screens;
var target = null;
for (var i = 0; i < screens.count; i++) {
    var s = screens.objectAtIndex(i);
    var name = ObjC.unwrap(s.localizedName);
    if (name === '${target_name}') { target = s; break; }
}
if (!target) target = $.NSScreen.mainScreen;
var v = target.visibleFrame;
var full = target.frame;
// NSScreen coordinates are flipped (origin at bottom-left).
// Convert to top-left origin for AppleScript.
var menuBarHeight = full.size.height - v.size.height - v.origin.y + full.origin.y;
var topLeftX = v.origin.x;
var topLeftY = full.origin.y + menuBarHeight;
JSON.stringify({x: topLeftX, y: topLeftY, w: v.size.width, h: v.size.height});
" 2>/dev/null
}

generate_applescript() {
    local target_process="$1"
    local bounds_json="$2"

    local dx dy dw dh
    dx=$(echo "$bounds_json" | python3 -c "import json,sys; print(int(json.load(sys.stdin)['x']))")
    dy=$(echo "$bounds_json" | python3 -c "import json,sys; print(int(json.load(sys.stdin)['y']))")
    dw=$(echo "$bounds_json" | python3 -c "import json,sys; print(int(json.load(sys.stdin)['w']))")
    dh=$(echo "$bounds_json" | python3 -c "import json,sys; print(int(json.load(sys.stdin)['h']))")

    cat <<ASEOF
tell application "System Events"
    set targetProc to first process whose name is "${target_process}"
    set windowCount to count of windows of targetProc
    if windowCount = 0 then
        return "0"
    end if
    set moved to 0
    repeat with w in (windows of targetProc)
        set position of w to {${dx}, ${dy}}
        set size of w to {${dw}, ${dh}}
        set moved to moved + 1
    end repeat
    return moved as text
end tell
ASEOF
}

gather_macos() {
    local target_output="$1"
    local target_process="$2"

    debug "Target process: $target_process"
    debug "Target display: $target_output"

    # Display bounds come from NSScreen (no Accessibility needed), so a dry-run
    # can print the script without the Accessibility grant.
    local bounds_json
    bounds_json=$(get_display_bounds "$target_output")
    debug "Display bounds: $bounds_json"

    local script
    script=$(generate_applescript "$target_process" "$bounds_json")

    if $DRY_RUN; then
        echo "$script"
        exit 0
    fi

    # Actual window manipulation requires Accessibility access.
    if ! osascript -e 'tell application "System Events" to get name of first process whose frontmost is true' >/dev/null 2>&1; then
        log "ERROR: Accessibility access denied."
        log "Grant access in System Settings → Privacy & Security → Accessibility"
        log "Add your terminal app ($(basename "$(ps -p $PPID -o comm= 2>/dev/null || echo Terminal)"))"
        exit 1
    fi

    local moved
    moved=$(osascript -e "$script" 2>&1) || {
        log "ERROR: AppleScript execution failed"
        debug "$moved"
        exit 1
    }

    log "Processed $moved window(s)"

    if $DEBUG; then
        debug "Post-gather window state:"
        osascript -e "
tell application \"System Events\"
    set targetProc to first process whose name is \"${target_process}\"
    set results to \"\"
    repeat with w in (windows of targetProc)
        set {x, y} to position of w
        set {pw, ph} to size of w
        set results to results & \"  \" & (name of w) & \": (\" & x & \",\" & y & \") \" & pw & \"x\" & ph & linefeed
    end repeat
    return results
end tell
" 2>/dev/null || true
    fi
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

LIST_OUTPUTS=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        -o|--output)  TARGET_OUTPUT="$2"; shift 2 ;;
        -c|--class)   TARGET_CLASS="$2"; shift 2 ;;
        -l|--list-outputs) LIST_OUTPUTS=true; shift ;;
        -n|--dry-run) DRY_RUN=true; shift ;;
        -d|--debug)   DEBUG=true; shift ;;
        -h|--help)    usage; exit 0 ;;
        -v|--version) echo "vscode-gather v${VERSION}"; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
    esac
done

if $LIST_OUTPUTS; then
    list_outputs
    exit 0
fi

# Map --class to macOS process name
if [[ "$PLATFORM" == "Darwin" ]] && [[ "$TARGET_CLASS" == "code" ]]; then
    TARGET_PROCESS="Code"
elif [[ "$PLATFORM" == "Darwin" ]]; then
    TARGET_PROCESS="$TARGET_CLASS"
fi

# --- Resolve target output ---
if [[ -z "$TARGET_OUTPUT" ]]; then
    log "Detecting primary monitor..."
    TARGET_OUTPUT=$(detect_primary_output) || {
        log "ERROR: Could not detect primary monitor. Use -o/--output to specify."
        exit 1
    }
fi
log "Target output: $TARGET_OUTPUT"

# --- Gather ---
case "$PLATFORM" in
    Linux)  gather_linux "$TARGET_OUTPUT" "$TARGET_CLASS" ;;
    Darwin) gather_macos "$TARGET_OUTPUT" "$TARGET_PROCESS" ;;
    *)      log "ERROR: Unsupported platform: $PLATFORM"; exit 1 ;;
esac

log "Done."
