#!/bin/bash
# Install the Pinball FX gamescope wrapper (v3.0.0).
#
# This installer does not install a .desktop entry. In v3 the menu entry comes
# from Heroic itself; we just provide a wrapper script that Heroic invokes.
#
# Removes any v1.x / v2.x desktop entries and KWin rules left over from prior
# versions of this tool.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WRAPPER="$SCRIPT_DIR/pinball_fx_wrapper.sh"
DETECT="$SCRIPT_DIR/detect_portrait_screen.py"
KWIN_INSTALLER="$SCRIPT_DIR/install_kwin_rule.py"

APPS_DIR="$HOME/.local/share/applications"
LEGACY_DESKTOPS=(
    "$APPS_DIR/PinballFX.desktop"
    "$APPS_DIR/PinballFixer.desktop"
)

chmod +x "$WRAPPER" "$DETECT" "$KWIN_INSTALLER"

for legacy in "${LEGACY_DESKTOPS[@]}"; do
    if [ -f "$legacy" ]; then
        echo "Removing legacy desktop entry: $legacy"
        rm -f "$legacy"
    fi
done

echo "Removing any pre-existing Pinball FX KWin rule..."
"$KWIN_INSTALLER" --uninstall || true

cat <<EOF

Installation complete. Next: configure Heroic to use the wrapper.

In the Heroic GUI, open Pinball FX → Settings:

  1. Wine version → "Wine Default" (or any system wine). NOT Proton — Proton's
     winebus.sys can't disambiguate when Steam Input's virtual gamepad is also
     present, breaking controller input. See README's v3.1.0 changelog.
  2. Wrapper Command (under "Advanced" / "Other") → enter exactly:

         $WRAPPER

  3. Save and launch from Heroic's library or the Heroic-managed
     "Pinball FX" desktop entry.

Optional env overrides (set in Heroic's "Environment Variables" section):
  PINBALL_FX_WIDTH=2160               override gamescope render width
  PINBALL_FX_HEIGHT=3840              override gamescope render height

The KWin rule pinning gamescope's window to the portrait monitor is
installed automatically on first real launch (so it captures live monitor
geometry).

Caveats discovered during v2.x/v3.x debugging — see README.md for full notes:
  - In-game settings: keep "Windowed Fullscreen". Switching to Exclusive
    Fullscreen inside gamescope blanks the display.
  - For native 4K rendering, disable KDE fractional scaling on the portrait
    monitor (or use the WIDTH / HEIGHT env overrides above).
  - HDR is not supported in v3.1.0 (dropped in favor of working controller).
EOF
