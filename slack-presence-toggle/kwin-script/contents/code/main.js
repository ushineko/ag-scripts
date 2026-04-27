// KWin script: forwards each window-activation event over D-Bus to the
// slack-presence-toggle tray app.
//
// Verified on Plasma 6 / Wayland: workspace.windowActivated is the correct
// signal. console.log() output appears in `journalctl --user` if you need
// to debug whether the script is firing.

var BUS_NAME = "io.github.ushineko.SlackPresenceToggle";
var OBJ_PATH = "/FocusMonitor";
var IFACE    = "io.github.ushineko.SlackPresenceToggle.FocusMonitor";

function send(rc, caption) {
    callDBus(BUS_NAME, OBJ_PATH, IFACE, "WindowActivated", rc, caption);
}

console.log("slack-focus-monitor: script loaded");

// Emit the current active window once at load so the listener can sync
// state on first run (and after every script reload). Without this, the
// listener doesn't learn the focus until the next focus change, which
// breaks the "Slack focused at launch -> alt-tab away -> grace timer"
// path.
var initial = workspace.activeWindow;
if (initial) {
    var initialRc = initial.resourceClass ? initial.resourceClass.toString() : "";
    var initialCaption = initial.caption ? initial.caption.toString() : "";
    send(initialRc, initialCaption);
}

workspace.windowActivated.connect(function(window) {
    if (!window) {
        send("", "");
        return;
    }
    var rc = window.resourceClass ? window.resourceClass.toString() : "";
    var caption = window.caption ? window.caption.toString() : "";
    send(rc, caption);
});
