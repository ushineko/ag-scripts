#!/bin/bash
# Gamescope wrapper for Heroic-launched Pinball FX (v3.1.5).
#
# Heroic invokes this with the wine command + game exe + Epic auth args.
# We detect the portrait monitor, install/refresh the gamescope KWin rule,
# spawn gamescope wrapping the args Heroic gave us, and run a watchdog that
# tears down the gamescope process tree once the game .exe exits (otherwise
# wine daemons keep gamescopereaper alive for ages, leaving Heroic stuck on
# "playing").
#
# Configure in Heroic per-game settings → "Wrapper Command":
#     /path/to/pinball_fx_wrapper.sh
#
# Env override:
#   PINBALL_FX_WIDTH / _HEIGHT  override the resolution the GAME sees as its
#                               display (gamescope -w/-h, the nested width).
#                               Defaults to detected logical screen size.
#                               Example: PINBALL_FX_WIDTH=2160 _HEIGHT=3840 to
#                               make UE see a native 4K display and offer 4K
#                               in the in-game resolution menu.
#
# v3.1.0 dropped HDR support — Proton-GE was the only path that carried HDR
# through gamescope's WSI layer, but Proton-GE's winebus.sys can't disambiguate
# gamepad devices when Steam Input's virtual XInput pad is also present.
# System wine handles the duplicate gracefully but doesn't carry HDR. Picked
# controller, dropped HDR.
#
# v3.1.1 fixed:
#   - -W/-H vs -w/-h were inverted. Now PINBALL_FX_WIDTH controls the nested
#     width (-w), what the game sees as its display.
#   - Added EXIT trap to sweep orphan gamescopereaper.
#
# v3.1.2 fixed: the v3.1.1 EXIT trap never fired in the common case because
#   gamescopereaper is a subreaper waiting for ALL descendants to exit, and
#   wine's winedevice.exe daemons take their sweet time. Wrapper's `wait` blocked
#   indefinitely, trap never ran, Heroic stayed on "playing". v3.1.2 adds a
#   background watchdog that takes gamescope down once the actual game .exe
#   exits, regardless of lingering wine daemons.
#
# v3.1.3 fixed: even after gamescope is gone, Heroic kept reporting "playing"
#   because it polls for any process owning the game's WINEPREFIX, and the wine
#   system daemons (winedevice.exe etc.) linger after the game closes. Cleanup
#   trap now runs `wineserver -k` for the inherited WINEPREFIX.
#
# v3.1.4 fixed two more issues found by real launches:
#   - Reaper pkill pattern was matching PinballFX-Win64-Shipping.exe but the
#     gamescopereaper cmdline references the LAUNCHER exe (PinballFX.exe), not
#     the running shipping process. Reaper was never killed.
#   - wineserver -k is a no-op when no wineserver is running (which is exactly
#     the post-game-exit state); the orphan winedevice.exe daemons survived.
#     Cleanup now also pkills any wine daemon (winedevice / wineserver /
#     services.exe / plugplay.exe / explorer.exe) whose /proc/PID/environ
#     names our WINEPREFIX, scoped so other wine apps using a different prefix
#     are untouched.
#
# v3.1.5 fixed the KWin rule hijacking unrelated gamescope windows. The rule
#   matched only on wmclass=gamescope, so any concurrent gamescope session
#   (Battle.net launcher, debug `gamescope -- alacritty`, etc.) would also be
#   force-pinned to the portrait monitor at portrait geometry. Two changes:
#   - Rule now also matches on title substring "PinballFX". Gamescope
#     propagates the focused inner window's title to its outer xdg-toplevel,
#     and KWin re-evaluates match conditions dynamically when caption changes
#     (verified empirically on Plasma 6), so other gamescope windows are
#     released the moment their title fails to match.
#   - Rule install is now transient: cleanup uninstalls it on wrapper exit.
#     Belt-and-suspenders against any future caption-set quirk, and avoids
#     leaving placement state in kwinrulesrc between sessions.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Pattern for the running game .exe (used by the watchdog to detect game exit).
GAME_PATTERN='PinballFX-Win64-Shipping\.exe'
# Pattern for the launcher .exe (which appears in the gamescopereaper cmdline,
# since gamescope was invoked with `wine .../PinballFX.exe`).
LAUNCHER_PATTERN='PinballFX\.exe'

if ! command -v gamescope >/dev/null 2>&1; then
    echo "pinball-fx-wrapper: error: gamescope not on PATH" >&2
    exit 1
fi

# Logical geometry of the portrait monitor (W H X Y).
read -r LW LH X Y < <("$SCRIPT_DIR/detect_portrait_screen.py")

# KWin rule pinning gamescope's outer window to the portrait monitor.
# Idempotent — refreshes geometry on each launch in case monitor layout changes.
"$SCRIPT_DIR/install_kwin_rule.py" --x "$X" --y "$Y" --width "$LW" --height "$LH" >/dev/null || \
    echo "pinball-fx-wrapper: warning: KWin rule install failed (continuing)" >&2

# Resolution the game sees inside gamescope (gamescope -w/-h, the nested size).
NW="${PINBALL_FX_WIDTH:-$LW}"
NH="${PINBALL_FX_HEIGHT:-$LH}"

# gamescope's output buffer is always the logical screen size — KWin places this
# surface on the portrait monitor via the rule above. If the nested resolution
# is bigger, gamescope downscales the game's render to fit the output buffer.
GAMESCOPE_ARGS=(-W "$LW" -H "$LH" -w "$NW" -h "$NH" -f)

echo "pinball-fx-wrapper: nested ${NW}x${NH}, output ${LW}x${LH} at ${X},${Y}"
echo "pinball-fx-wrapper: cmd: gamescope ${GAMESCOPE_ARGS[*]} -- $*"

# Run gamescope in the background so we can supervise it.
gamescope "${GAMESCOPE_ARGS[@]}" -- "$@" &
GS_PID=$!

# Watchdog: wait for the game .exe to appear, then for it to disappear, then
# tear down gamescope. Without this, gamescopereaper waits for wine daemons
# (winedevice.exe etc.) which can linger for minutes, leaving Heroic stuck on
# "playing".
(
    # Allow up to 120s for the game to start (UE shader compile on cold prefix
    # can take a while).
    for _ in $(seq 1 120); do
        pgrep -f "$GAME_PATTERN" >/dev/null && break
        sleep 1
    done
    # Wait for the game .exe to exit.
    while pgrep -f "$GAME_PATTERN" >/dev/null; do
        sleep 2
    done
    # Game gone. Brief grace for clean shutdown, then take gamescope down.
    sleep 2
    if kill -0 "$GS_PID" 2>/dev/null; then
        echo "pinball-fx-wrapper: game exited, terminating gamescope tree" >&2
        kill -TERM "$GS_PID" 2>/dev/null || true
        sleep 3
        kill -KILL "$GS_PID" 2>/dev/null || true
        pkill -KILL -f "gamescopereaper.*${LAUNCHER_PATTERN}" 2>/dev/null || true
    fi
) &
WATCHDOG_PID=$!

# shellcheck disable=SC2329  # invoked via `trap`, not directly
cleanup() {
    kill "$WATCHDOG_PID" 2>/dev/null || true
    pkill -KILL -f "gamescopereaper.*${LAUNCHER_PATTERN}" 2>/dev/null || true
    # Free the WINEPREFIX so Heroic's "any process owning the prefix" poll
    # clears. Two-pronged because wineserver -k is a no-op when no wineserver
    # is running (which is exactly the post-game-exit state):
    #   1. Try wineserver -k (clean wine-managed teardown if wineserver alive)
    #   2. Then SIGKILL any wine system daemon (winedevice.exe, services.exe,
    #      plugplay.exe, explorer.exe, wineserver) whose /proc/PID/environ
    #      shows WINEPREFIX matching ours. Scoped so other wine apps using
    #      a different prefix are untouched.
    if [ -n "${WINEPREFIX:-}" ]; then
        if command -v wineserver >/dev/null 2>&1; then
            WINEPREFIX="$WINEPREFIX" wineserver -k 2>/dev/null || true
        fi
        local pid
        for pid in $(pgrep -f 'winedevice|services\.exe|plugplay\.exe|explorer\.exe|wineserver' 2>/dev/null); do
            if grep -qz "WINEPREFIX=${WINEPREFIX}" "/proc/${pid}/environ" 2>/dev/null; then
                kill -KILL "$pid" 2>/dev/null || true
            fi
        done
    fi
    # Tear down the transient KWin rule. Belt-and-suspenders alongside the
    # title-substring match: even if a future gamescope version changes its
    # caption-set behavior, the rule won't outlive this wrapper invocation.
    "$SCRIPT_DIR/install_kwin_rule.py" --uninstall >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

# Wait for gamescope (or watchdog kill) to finish, then propagate exit code.
set +e
wait "$GS_PID"
GS_EXIT=$?
set -e
exit "$GS_EXIT"
