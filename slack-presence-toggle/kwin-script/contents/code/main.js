// KWin script: reports whether Slack is "reachable" to the tray app.
//
// "Reachable" = at least one window with resourceClass === SLACK_CLASS is
// on the current virtual desktop, not minimized, and not fully covered by
// any single higher-stacked window. Side-by-side or partially-overlapping
// arrangements still count as reachable. Fully covered, on another desktop,
// minimized, or absent count as not reachable.
//
// This is what users mean by "Slack is on top" on a multi-monitor setup,
// where KWin's single global "active window" doesn't capture per-screen
// topmost-ness. A non-Slack window taking focus on monitor B does not flip
// us to not-reachable as long as Slack is still visible on monitor A.
//
// Sends WindowActivated(rc, caption) over D-Bus on every transition:
//   - reachable becomes true:  rc = SLACK_CLASS,        caption = "[reachable:<reason>]"
//   - reachable becomes false: rc = "__not-reachable__", caption = "[<reason>]"
// The python tray app already treats rc !== SLACK_CLASS as "non-Slack
// focus", so no python-side changes are needed.
//
// SLACK_CLASS is hardcoded; if your Slack distribution (Flatpak, Snap,
// dev build) uses a different resourceClass, edit it here AND in the
// tray app's slack_resource_class config.
//
// Verified on Plasma 6 / Wayland.

var SLACK_CLASS = "Slack";
var BUS_NAME = "io.github.ushineko.SlackPresenceToggle";
var OBJ_PATH = "/FocusMonitor";
var IFACE    = "io.github.ushineko.SlackPresenceToggle.FocusMonitor";

var lastReachable = null;  // null until first evaluation

function send(rc, caption) {
    callDBus(BUS_NAME, OBJ_PATH, IFACE, "WindowActivated", rc, caption);
}

function isOnCurrentDesktop(w) {
    if (w.onAllDesktops) return true;
    var desks = w.desktops;
    if (!desks || desks.length === 0) return false;
    var current = workspace.currentDesktop;
    for (var i = 0; i < desks.length; i++) {
        if (desks[i] === current) return true;
    }
    return false;
}

function rectFullyContains(outer, inner) {
    if (!outer || !inner) return false;
    return outer.x <= inner.x &&
           outer.y <= inner.y &&
           outer.x + outer.width >= inner.x + inner.width &&
           outer.y + outer.height >= inner.y + inner.height;
}

function isVisibleNormalWindow(w) {
    if (!w) return false;
    if (w.minimized) return false;
    if (!isOnCurrentDesktop(w)) return false;
    var fg = w.frameGeometry;
    if (!fg || fg.width <= 0 || fg.height <= 0) return false;
    return true;
}

function isSlackReachable() {
    var stack = workspace.stackingOrder;
    if (!stack) return false;

    // Collect Slack candidates with their stack index.
    var slackEntries = [];
    for (var i = 0; i < stack.length; i++) {
        var w = stack[i];
        if (!w || !w.resourceClass) continue;
        if (w.resourceClass.toString() !== SLACK_CLASS) continue;
        if (!isVisibleNormalWindow(w)) continue;
        slackEntries.push({ w: w, idx: i, geom: w.frameGeometry });
    }
    if (slackEntries.length === 0) return false;

    // For each Slack window, check if any single higher-stacked visible
    // window fully contains its frame geometry. If at least one Slack
    // window is not fully covered, Slack is reachable. Multi-rectangle
    // tiled coverage (two non-overlapping windows that collectively cover
    // Slack) is rare and intentionally not handled — would require a
    // region-difference test we can keep out of the hot path.
    for (var k = 0; k < slackEntries.length; k++) {
        var s = slackEntries[k];
        var fullyCovered = false;
        for (var j = s.idx + 1; j < stack.length; j++) {
            var above = stack[j];
            if (!above) continue;
            if (above === s.w) continue;
            if (!isVisibleNormalWindow(above)) continue;
            if (rectFullyContains(above.frameGeometry, s.geom)) {
                fullyCovered = true;
                break;
            }
        }
        if (!fullyCovered) return true;
    }
    return false;
}

function evaluate(reason) {
    var reachable = isSlackReachable();
    if (reachable === lastReachable) return;
    lastReachable = reachable;
    if (reachable) {
        send(SLACK_CLASS, "[reachable:" + reason + "]");
    } else {
        send("__not-reachable__", "[" + reason + "]");
    }
}

console.log("slack-focus-monitor: script loaded (visibility-based)");

// Initial emit so the tray app can sync to the current state on startup
// and after every script reload.
evaluate("startup");

// Workspace-level signals: any of these can flip reachability without a
// per-window signal firing first (e.g., desktop switch reveals a window
// that covers Slack on the new desktop).
workspace.windowActivated.connect(function() { evaluate("activated"); });
workspace.currentDesktopChanged.connect(function() { evaluate("desktopChanged"); });

function trackWindow(w) {
    if (!w) return;
    // Wrap each connect in try/catch in case some KWin builds drop a
    // signal we expect; we'd rather lose one trigger than refuse to load.
    try { if (w.minimizedChanged) w.minimizedChanged.connect(function() { evaluate("minimized"); }); } catch (e) {}
    try { if (w.frameGeometryChanged) w.frameGeometryChanged.connect(function() { evaluate("geom"); }); } catch (e) {}
    try { if (w.outputChanged) w.outputChanged.connect(function() { evaluate("output"); }); } catch (e) {}
    try { if (w.desktopsChanged) w.desktopsChanged.connect(function() { evaluate("desktops"); }); } catch (e) {}
}

// Track existing windows, then track any new ones as they appear.
var existing = workspace.windowList ? workspace.windowList() : [];
for (var i = 0; i < existing.length; i++) {
    trackWindow(existing[i]);
}
workspace.windowAdded.connect(function(w) {
    trackWindow(w);
    evaluate("added");
});
workspace.windowRemoved.connect(function() {
    evaluate("removed");
});
