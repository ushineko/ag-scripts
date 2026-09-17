#!/bin/bash
# browser-router.sh - Routes URLs to different browsers based on domain patterns
#
# Created: 2026-02-02
# Purpose: Chromium/Vivaldi lack PipeWire camera support on Wayland, so routes
#          webcam-dependent sites (Teams, etc.) to Firefox while keeping Vivaldi
#          as the default browser for everything else.
#
# Usage: browser-router.sh <url>
#        BROWSER_ROUTER_DEBUG=1 browser-router.sh <url>   # trace to stderr
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

# This runs as the system's http/https handler, so every failure is invisible by
# default -- which is how a dead window-activation path went unnoticed for weeks.
# BROWSER_ROUTER_DEBUG=1 narrates every decision to stderr.
dbg() { [[ -n "${BROWSER_ROUTER_DEBUG:-}" ]] && echo "browser-router: $*" >&2; return 0; }

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
# on the primary monitor. Vivaldi then sees that window become focused, forwards
# the URL into it, and it is already on top -- which is what you want anyway.
#
# PRIMARY_OUTPUT accepts:
#   auto    - resolve Plasma's primary (lowest `priority`) output at run time.
#             The default, and the only value that survives a cable move.
#   NAME[,NAME...]
#           - explicit KWin connector name(s), e.g. "DP-3" or "DP-3,HDMI-A-1".
#             Any name not currently enabled is ignored; if none of them match,
#             falls back to auto rather than silently doing nothing.
#   (empty) - disable this behaviour entirely, plain hand-off.
#
# Precedence: built-in default < ~/.config/browser-router/config < env var
#             BROWSER_ROUTER_PRIMARY_OUTPUT.
#
# NOTE ON THE DEFAULT: this used to be the hardcoded connector "HDMI-A-1".
# Moving the Philips to another port renamed it to DP-3, the name matched
# nothing, and the workaround became a silent no-op. Connector names are a
# property of which port a cable is in, not of the desk -- never hardcode one.
PRIMARY_OUTPUT="auto"
CONFIG_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/browser-router/config"
if [[ -f "$CONFIG_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$CONFIG_FILE" 2>/dev/null || true
fi
# Use ${VAR-default} (not :-) so an explicit empty env var disables the feature.
PRIMARY_OUTPUT="${BROWSER_ROUTER_PRIMARY_OUTPUT-$PRIMARY_OUTPUT}"

# Logical (scaled, rotation-applied) rectangle of one output, as "x y w h".
# kscreen's `pos` is already logical but `size` is not, hence the scale divide;
# window geometry from KWin's getWindowInfo is logical, so the two must agree.
# With name="auto" (or unset) picks the enabled output with the lowest priority,
# which is what Plasma calls the primary.
output_rect() {
    local name="${1:-auto}" json
    json=$(kscreen-doctor -j 2>/dev/null) || return 1
    if [[ "$name" == "auto" ]]; then
        jq -er '[.outputs[] | select(.enabled)] | sort_by(.priority) | .[0]
                | "\(.pos.x) \(.pos.y) \((.size.width / .scale) | round) \((.size.height / .scale) | round)"' \
           <<<"$json" 2>/dev/null
    else
        jq -er --arg n "$name" '.outputs[] | select(.enabled and .name == $n)
                | "\(.pos.x) \(.pos.y) \((.size.width / .scale) | round) \((.size.height / .scale) | round)"' \
           <<<"$json" 2>/dev/null
    fi
}

# Activate + raise a Vivaldi window on the primary output. Best-effort: any
# failure (not KDE, tools missing, no matching window) is swallowed so routing
# always proceeds. Never aborts the caller.
#
# Deliberately does NOT use KWin's Scripting interface. `loadScript` returns an
# id that collides with an already-exposed /Scripting/ScriptN object, creating
# nothing, after which `run()` on that path is a silent no-op against somebody
# else's script -- verified on this box, where every load returns id 3 while
# /Scripting/Script3 already exists. WindowsRunner + getWindowInfo are plain,
# stable D-Bus with no object-lifetime games, and cost ~8ms each.
activate_primary_vivaldi() {
    local outputs="$1"
    [[ -z "$outputs" ]] && { dbg "primary-window activation disabled"; return 0; }

    command -v gdbus     >/dev/null 2>&1 || { dbg "no gdbus";     return 0; }
    command -v qdbus6    >/dev/null 2>&1 || { dbg "no qdbus6";    return 0; }
    command -v jq        >/dev/null 2>&1 || { dbg "no jq";        return 0; }
    command -v kscreen-doctor >/dev/null 2>&1 || { dbg "no kscreen-doctor"; return 0; }

    # Resolve the target rectangle. An explicit name that is not currently
    # enabled falls through to auto -- a moved cable should degrade to "the
    # primary monitor", never to "do nothing".
    local rect="" name
    local IFS=,
    for name in $outputs; do
        name="${name//[^A-Za-z0-9_-]/}"
        [[ -z "$name" ]] && continue
        if rect=$(output_rect "$name"); then
            dbg "target output $name rect=$rect"
            break
        fi
        dbg "configured output $name is not enabled; ignoring"
        rect=""
    done
    unset IFS
    if [[ -z "$rect" ]]; then
        rect=$(output_rect auto) || { dbg "cannot resolve any output"; return 0; }
        dbg "falling back to primary output, rect=$rect"
    fi
    local ox oy ow oh
    read -r ox oy ow oh <<<"$rect"

    # Window uuids KWin's WindowsRunner matches for "vivaldi". The reply also
    # carries raw icon bytes, so pull ids by pattern rather than parsing it.
    local match ids
    match=$(gdbus call --session --dest org.kde.KWin --object-path /WindowsRunner \
            --method org.kde.krunner1.Match "vivaldi" 2>/dev/null) || {
        dbg "WindowsRunner Match failed"; return 0; }
    ids=$(grep -oE "'0_\{[0-9a-f-]+\}'" <<<"$match" | tr -d "'" | sort -u) || true
    [[ -z "$ids" ]] && { dbg "no vivaldi windows found"; return 0; }

    local id uuid info cls wx wy ww wh cx cy target="" fallback=""
    while read -r id; do
        [[ -z "$id" ]] && continue
        uuid="${id#0_}"
        info=$(qdbus6 org.kde.KWin /KWin getWindowInfo "$uuid" 2>/dev/null) || continue
        cls=$(sed -n 's/^resourceClass: //p'  <<<"$info")
        wx=$(sed -n 's/^x: //p'      <<<"$info")
        wy=$(sed -n 's/^y: //p'      <<<"$info")
        ww=$(sed -n 's/^width: //p'  <<<"$info")
        wh=$(sed -n 's/^height: //p' <<<"$info")
        [[ "$cls" == "vivaldi-stable" ]] || continue
        [[ -z "$wx$wy$ww$wh" ]] && continue
        # Any vivaldi window beats none, if the primary output holds none.
        [[ -z "$fallback" ]] && fallback="$id"
        cx=$(( wx + ww / 2 ))
        cy=$(( wy + wh / 2 ))
        if (( cx >= ox && cx < ox + ow && cy >= oy && cy < oy + oh )); then
            target="$id"
            dbg "window $uuid at ${wx},${wy} ${ww}x${wh} is on the target output"
            break
        fi
        dbg "window $uuid at ${wx},${wy} ${ww}x${wh} is off-target"
    done <<<"$ids"

    if [[ -z "$target" ]]; then
        target="$fallback"
        [[ -n "$target" ]] && dbg "no vivaldi window on the target output; using $target"
    fi
    [[ -z "$target" ]] && { dbg "nothing to activate"; return 0; }

    gdbus call --session --dest org.kde.KWin --object-path /WindowsRunner \
        --method org.kde.krunner1.Run "$target" "" >/dev/null 2>&1 || {
        dbg "activation call failed"; return 0; }
    dbg "activated $target"
    # Give KWin time to activate the window and Vivaldi time to register the
    # focus change before we forward the URL over the singleton socket.
    sleep 0.4
}

# --- Routing -----------------------------------------------------------------

# Route Teams links to teams-for-linux (camera, screen sharing, recording all work there)
if [[ "$url" == *"teams.microsoft.com"* ]] || \
   [[ "$url" == *"teams.live.com"* ]]; then
    dbg "routing to teams-for-linux: $url"
    exec teams-for-linux "$url"
# Route other Microsoft 365 / Office apps and Slack to Firefox
elif [[ "$url" == *"outlook.office.com"* ]] || \
   [[ "$url" == *"outlook.office365.com"* ]] || \
   [[ "$url" == *"outlook.live.com"* ]] || \
   [[ "$url" == *".sharepoint.com"* ]] || \
   [[ "$url" == *"onedrive.live.com"* ]] || \
   [[ "$url" == *"office.com"* ]] || \
   [[ "$url" == *"app.slack.com"* ]]; then
    dbg "routing to firefox: $url"
    exec firefox "$url"
else
    # Surface the primary-monitor Vivaldi window first so the forwarded URL
    # lands in a visible, focused window (see block above). Best-effort.
    dbg "routing to vivaldi: $url"
    activate_primary_vivaldi "$PRIMARY_OUTPUT" || true
    exec vivaldi-stable "$url"
fi
