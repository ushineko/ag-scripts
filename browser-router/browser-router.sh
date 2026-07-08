#!/bin/bash
# browser-router.sh - Routes URLs to different browsers based on domain patterns
#
# Created: 2026-02-02
# Purpose: Chromium/Vivaldi lack PipeWire camera support on Wayland, so routes
#          webcam-dependent sites (Teams, etc.) to Firefox while keeping Vivaldi
#          as the default browser for everything else.
#
# Usage: browser-router.sh <url>
#
# Configuration: Edit the domain patterns in the if statement below to customize
#                which URLs go to Firefox vs Vivaldi. See also the "primary
#                window" config block below for the Vivaldi multi-window fix.

set -euo pipefail

url="${1:-}"

if [[ -z "$url" ]]; then
    echo "Usage: browser-router.sh <url>" >&2
    exit 1
fi

# --- Primary Vivaldi window (Wayland multi-window workaround) ----------------
#
# On Wayland, forwarding a URL to an already-running Vivaldi ("vivaldi-stable
# <url>") hands the URL over Chromium's singleton socket to the existing
# browser, which tries to open a tab in its internally-tracked last-active
# window. If that window can't be activated by the client (Wayland forbids
# clients from stealing focus, and the xdg-activation token is not relayed
# across the singleton socket), Vivaldi drops the open entirely -- the target
# window just "flashes" and no tab appears. This is a Vivaldi/Chromium-on-
# Wayland bug, not something the router can fix by forwarding differently.
#
# Workaround: before forwarding, ask KWin (the compositor -- it is NOT bound by
# the client focus-stealing restriction) to activate and raise a Vivaldi window
# on the configured primary monitor. Vivaldi then sees that window become
# focused, forwards the URL into it, and it is already on top -- which is what
# you want anyway (read the page immediately).
#
# PRIMARY_OUTPUT is a comma-separated list of KWin output connector name(s)
# (e.g. "HDMI-A-1" or "HDMI-A-1,DP-3"). Find yours with: kscreen-doctor -o
# Set it empty to disable this behavior and fall back to a plain hand-off.
#
# Precedence: built-in default < ~/.config/browser-router/config < env var
#             BROWSER_ROUTER_PRIMARY_OUTPUT.
PRIMARY_OUTPUT="HDMI-A-1"
CONFIG_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/browser-router/config"
if [[ -f "$CONFIG_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$CONFIG_FILE" 2>/dev/null || true
fi
# Use ${VAR-default} (not :-) so an explicit empty env var disables the feature.
PRIMARY_OUTPUT="${BROWSER_ROUTER_PRIMARY_OUTPUT-$PRIMARY_OUTPUT}"

# Activate + raise a Vivaldi window on one of the PRIMARY_OUTPUT connectors via
# KWin scripting. Best-effort: any failure (not KDE, tools missing, no matching
# window) is swallowed so routing always proceeds. Never aborts the caller.
activate_primary_vivaldi() {
    local outputs="$1"
    [[ -z "$outputs" ]] && return 0

    local qdbus=""
    if command -v qdbus6 >/dev/null 2>&1; then
        qdbus=qdbus6
    elif command -v qdbus >/dev/null 2>&1; then
        qdbus=qdbus
    else
        return 0
    fi

    # Build a JS array literal of the target connector names. Output names are
    # simple (letters/digits/dash), but strip anything else defensively.
    local js_targets="" name
    local IFS=,
    for name in $outputs; do
        name="${name//[^A-Za-z0-9_-]/}"
        [[ -z "$name" ]] && continue
        js_targets+="\"$name\","
    done
    unset IFS
    [[ -z "$js_targets" ]] && return 0

    local script
    script=$(mktemp --tmpdir browser-router-activate-XXXXXX.js) || return 0
    cat > "$script" <<EOF
(function () {
    var targets = [${js_targets}];
    var ws = workspace.windowList();
    for (var i = 0; i < ws.length; i++) {
        var w = ws[i];
        if (w.resourceClass !== "vivaldi-stable") continue;
        if (w.skipTaskbar || w.specialWindow) continue;
        if (!w.output) continue;
        for (var j = 0; j < targets.length; j++) {
            if (w.output.name === targets[j]) {
                workspace.activeWindow = w;
                return;
            }
        }
    }
})();
EOF

    local name_id="browser-router-activate"
    "$qdbus" org.kde.KWin /Scripting org.kde.kwin.Scripting.unloadScript "$name_id" >/dev/null 2>&1 || true
    local id
    id=$("$qdbus" org.kde.KWin /Scripting org.kde.kwin.Scripting.loadScript "$script" "$name_id" 2>/dev/null) || id=""
    if [[ "$id" =~ ^-?[0-9]+$ ]] && (( id >= 0 )); then
        "$qdbus" org.kde.KWin "/Scripting/Script${id}" org.kde.kwin.Script.run >/dev/null 2>&1 || true
        # Give KWin time to activate the window and Vivaldi time to register the
        # focus change before we forward the URL over the singleton socket.
        sleep 0.4
        "$qdbus" org.kde.KWin /Scripting org.kde.kwin.Scripting.unloadScript "$name_id" >/dev/null 2>&1 || true
    fi
    rm -f "$script"
}

# --- Routing -----------------------------------------------------------------

# Route Teams links to teams-for-linux (camera, screen sharing, recording all work there)
if [[ "$url" == *"teams.microsoft.com"* ]] || \
   [[ "$url" == *"teams.live.com"* ]]; then
    exec teams-for-linux "$url"
# Route other Microsoft 365 / Office apps and Slack to Firefox
elif [[ "$url" == *"outlook.office.com"* ]] || \
   [[ "$url" == *"outlook.office365.com"* ]] || \
   [[ "$url" == *"outlook.live.com"* ]] || \
   [[ "$url" == *".sharepoint.com"* ]] || \
   [[ "$url" == *"onedrive.live.com"* ]] || \
   [[ "$url" == *"office.com"* ]] || \
   [[ "$url" == *"app.slack.com"* ]]; then
    exec firefox "$url"
else
    # Surface the primary-monitor Vivaldi window first so the forwarded URL
    # lands in a visible, focused window (see block above). Best-effort.
    activate_primary_vivaldi "$PRIMARY_OUTPUT" || true
    exec vivaldi-stable "$url"
fi
