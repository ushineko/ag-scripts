#!/usr/bin/env bash
# Install herdr-resurrect: symlink the CLI and install a systemd user timer that
# snapshots running pane programs every N minutes. Restore is manual:
#   herdr-resurrect restore   (after a reboot, once herdr has restored the layout)
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP="herdr-resurrect"
BIN_DIR="$HOME/.local/bin"

# --- deps -------------------------------------------------------------------
missing=()
command -v python3 >/dev/null 2>&1 || missing+=("python3")
command -v herdr   >/dev/null 2>&1 || missing+=("herdr")
if (( ${#missing[@]} )); then
    echo "$APP: missing dependencies: ${missing[*]}"; exit 1
fi

mkdir -p "$BIN_DIR"
chmod +x "$SRC_DIR/cli.py"
ln -sf "$SRC_DIR/cli.py" "$BIN_DIR/$APP"
echo "symlinked $BIN_DIR/$APP"

# --- periodic save (Linux: systemd user timer; macOS: launchd not yet) -------
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "note: periodic auto-save via launchd is not yet implemented on macOS."
    echo "      The CLI works; add a launchd agent or cron for periodic 'save'."
else
    interval="$(S="$SRC_DIR" python3 -c 'import sys,os; sys.path.insert(0,os.environ["S"]); import config; print(int(config.load().get("save_interval_min",5)))' 2>/dev/null || echo 5)"
    [ -n "$interval" ] || interval=5
    UNIT_DIR="$HOME/.config/systemd/user"
    mkdir -p "$UNIT_DIR"

    cat > "$UNIT_DIR/$APP-save.service" <<EOF
[Unit]
Description=Snapshot running herdr pane programs (herdr-resurrect)
[Service]
Type=oneshot
ExecStart=$BIN_DIR/$APP save
EOF

    cat > "$UNIT_DIR/$APP-save.timer" <<EOF
[Unit]
Description=Periodic herdr-resurrect snapshot (every ${interval}m)
[Timer]
OnBootSec=2min
OnUnitActiveSec=${interval}min
Persistent=true
[Install]
WantedBy=timers.target
EOF

    systemctl --user daemon-reload
    systemctl --user enable --now "$APP-save.timer" >/dev/null 2>&1 || \
        systemctl --user enable --now "$APP-save.timer"
    echo "installed + enabled $APP-save.timer (every ${interval}m)"
fi

echo
echo "$APP installed."
echo "  Snapshot now:   $APP save"
echo "  After a reboot: $APP restore   (preview with --dry-run)"
echo "  Status:         $APP status | $APP list"
echo "  Config:         ~/.config/$APP/config.json (whitelist, interval)"
