#!/usr/bin/env bash
# vscode-gather: Move all VS Code windows to the primary monitor and maximize them.
# Uses KWin scripting via D-Bus — works on KDE Plasma 6 / Wayland.

set -euo pipefail

VERSION="1.0"
SCRIPT_NAME="vscode-gather"
DEBUG=false
DRY_RUN=false
TARGET_CLASS="code"
TARGET_OUTPUT=""

usage() {
    cat <<EOF
vscode-gather v${VERSION} — gather VS Code windows to one monitor

Usage: $(basename "$0") [OPTIONS]

Options:
  -o, --output NAME   Target output name (e.g. DP-3). Default: primary monitor.
  -c, --class CLASS   Window class to match (default: code)
  -n, --dry-run       Print the KWin script without running it
  -d, --debug         Enable debug output
  -h, --help          Show this help
  -v, --version       Show version
EOF
}

log() { echo "[gather] $*"; }
debug() { $DEBUG && echo "[gather:debug] $*" || true; }

detect_primary_output() {
    # kscreen-doctor lists outputs with "priority N" — priority 1 is primary.
    # Parse: "Output: N <name> <uuid>" followed by "priority N"
    local output_name=""
    while IFS= read -r line; do
        # Strip ANSI escape codes
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

        // Move to target output (w.output is read-only in KDE 6)
        workspace.sendClientToScreen(w, targetOutput);

        // Maximize (setMaximize(horizontal, vertical))
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

    # Brief pause to let the script complete
    sleep 0.3

    # Read results from journal
    if $DEBUG; then
        journalctl --user -u plasma-kwin_wayland --since "3 seconds ago" --no-pager 2>/dev/null \
            | grep "$SCRIPT_NAME" || true
    fi

    # Unload
    qdbus6 org.kde.KWin /Scripting org.kde.kwin.Scripting.unloadScript "$SCRIPT_NAME" >/dev/null 2>&1 || true

    rm -f "$tmpfile"
}

# --- Parse args ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        -o|--output)  TARGET_OUTPUT="$2"; shift 2 ;;
        -c|--class)   TARGET_CLASS="$2"; shift 2 ;;
        -n|--dry-run) DRY_RUN=true; shift ;;
        -d|--debug)   DEBUG=true; shift ;;
        -h|--help)    usage; exit 0 ;;
        -v|--version) echo "vscode-gather v${VERSION}"; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
    esac
done

# --- Resolve target output ---
if [[ -z "$TARGET_OUTPUT" ]]; then
    log "Detecting primary monitor..."
    TARGET_OUTPUT=$(detect_primary_output) || {
        log "ERROR: Could not detect primary monitor. Use -o/--output to specify."
        exit 1
    }
fi
log "Target output: $TARGET_OUTPUT"

# --- Generate and run ---
script=$(generate_kwin_script "$TARGET_OUTPUT" "$TARGET_CLASS")

if $DRY_RUN; then
    echo "$script"
    exit 0
fi

run_kwin_script "$script"
log "Done."
