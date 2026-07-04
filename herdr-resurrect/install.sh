#!/usr/bin/env bash
# Install herdr-resurrect: symlink the CLI and install systemd user timers that
# (1) snapshot running pane programs every N minutes and (2) auto-restore them
# shortly after login. Manual restore is still available:
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

    cat > "$UNIT_DIR/$APP-autorestore.service" <<EOF
[Unit]
Description=Auto-restore herdr pane programs after a boot/restart (herdr-resurrect)
[Service]
Type=oneshot
ExecStart=$BIN_DIR/$APP autorestore
EOF

    cat > "$UNIT_DIR/$APP-autorestore.timer" <<EOF
[Unit]
Description=Trigger herdr-resurrect auto-restore shortly after login
[Timer]
OnStartupSec=30s
Persistent=false
[Install]
WantedBy=timers.target
EOF

    systemctl --user daemon-reload
    for unit in "$APP-save.timer" "$APP-autorestore.timer"; do
        systemctl --user enable --now "$unit" >/dev/null 2>&1 || \
            systemctl --user enable --now "$unit"
    done
    echo "installed + enabled $APP-save.timer (every ${interval}m)"
    echo "installed + enabled $APP-autorestore.timer (30s after login)"
fi

echo
echo "$APP installed."
echo "  Snapshot now:   $APP save"
echo "  After a reboot: auto-restores ~30s after login; manual: $APP restore"
echo "                  (preview with --dry-run)"
echo "  Status:         $APP status | $APP list"
echo "  Config:         ~/.config/$APP/config.json (whitelist, interval)"
