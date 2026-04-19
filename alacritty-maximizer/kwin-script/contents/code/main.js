/*
 * Alacritty Maximizer KWin Script
 *
 * Places windows whose resourceClass matches "alacritty-pos-<X>_<Y>" on the
 * screen whose geometry contains the point (X, Y), then maximizes them.
 * Re-evaluates on screen configuration changes so windows return to their
 * home monitor after disconnect/reconnect events (e.g. OLED pixel refresh)
 * or once deferred-to monitors come online after fresh login.
 */

const CLASS_PREFIX = "alacritty-pos-";

const debugMode = readConfig("debugMode", false);

function debug() {
    if (!debugMode) return;
    const args = ["alacritty-maximizer:"];
    for (let i = 0; i < arguments.length; i++) {
        args.push(arguments[i]);
    }
    console.debug.apply(console, args);
}

function parseTargetPos(resourceClass) {
    if (!resourceClass) return null;
    const str = String(resourceClass).toLowerCase();
    if (str.indexOf(CLASS_PREFIX) !== 0) return null;
    const coords = str.substring(CLASS_PREFIX.length);
    const parts = coords.split("_");
    if (parts.length !== 2) return null;
    const x = parseInt(parts[0], 10);
    const y = parseInt(parts[1], 10);
    if (isNaN(x) || isNaN(y)) return null;
    return { x: x, y: y };
}

function findScreenAtPoint(tx, ty) {
    const screens = workspace.screens;
    if (!screens) return -1;
    for (let i = 0; i < screens.length; i++) {
        const g = screens[i].geometry;
        if (tx >= g.x && tx < g.x + g.width && ty >= g.y && ty < g.y + g.height) {
            return i;
        }
    }
    return -1;
}

function placeWindow(window) {
    if (!window) return;
    const target = parseTargetPos(window.resourceClass);
    if (!target) return;

    if (!(window.moveable && window.moveableAcrossScreens && window.resizeable)) {
        debug("window not repositionable:", window.caption, "class:", window.resourceClass);
        return;
    }

    const screenIdx = findScreenAtPoint(target.x, target.y);
    if (screenIdx < 0) {
        debug("target screen not online yet for", window.caption, "target:", target.x + "," + target.y);
        return;
    }

    if (window.screen !== screenIdx) {
        debug("moving", window.caption, "from screen", window.screen, "to", screenIdx);
        workspace.sendClientToScreen(window, screenIdx);
    } else {
        debug("already on target screen", screenIdx, "for", window.caption);
    }

    if (typeof window.setMaximize === "function") {
        window.setMaximize(true, true);
    } else {
        const area = workspace.clientArea(KWin.MaximizeArea, window);
        window.frameGeometry.x = area.x;
        window.frameGeometry.y = area.y;
        window.frameGeometry.width = area.width;
        window.frameGeometry.height = area.height;
    }
}

function reevaluateAll() {
    debug("re-evaluating all windows");
    let list = null;
    if (typeof workspace.windowList === "function") {
        list = workspace.windowList();
    } else if (typeof workspace.clientList === "function") {
        list = workspace.clientList();
    } else if (workspace.stackingOrder) {
        list = workspace.stackingOrder;
    }
    if (!list) {
        debug("no window enumeration API available; skipping re-evaluation");
        return;
    }
    for (let i = 0; i < list.length; i++) {
        placeWindow(list[i]);
    }
}

debug("initializing (debugMode=" + debugMode + ")");

workspace.windowAdded.connect(placeWindow);

if (workspace.screensChanged && typeof workspace.screensChanged.connect === "function") {
    workspace.screensChanged.connect(reevaluateAll);
} else if (workspace.virtualScreenGeometryChanged && typeof workspace.virtualScreenGeometryChanged.connect === "function") {
    debug("screensChanged not available; falling back to virtualScreenGeometryChanged");
    workspace.virtualScreenGeometryChanged.connect(reevaluateAll);
} else {
    debug("no screen-change signal available; hotplug re-evaluation disabled");
}
