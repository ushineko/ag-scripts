// KWin script: forwards window-activation events to the focus_listener.py
// service over D-Bus.
//
// Verified on Plasma 6 / Wayland: workspace.windowActivated is the correct
// signal. console.log() output appears in `journalctl --user`.

var BUS_NAME = "io.github.ushineko.SlackFocusMonitor";
var OBJ_PATH = "/SlackFocusMonitor";
var IFACE    = "io.github.ushineko.SlackFocusMonitor";

function send(rc, caption) {
    callDBus(BUS_NAME, OBJ_PATH, IFACE, "WindowActivated", rc, caption);
}

send("__SCRIPT_LOADED__", "");
console.log("slack-focus-monitor: script loaded");

workspace.windowActivated.connect(function(window) {
    if (!window) {
        send("", "");
        return;
    }
    var rc = window.resourceClass ? window.resourceClass.toString() : "";
    var caption = window.caption ? window.caption.toString() : "";
    send(rc, caption);
});
