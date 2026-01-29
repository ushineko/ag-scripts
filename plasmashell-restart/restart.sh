#!/bin/bash

# Detect which quit app is available (Plasma 6 vs Plasma 5)
if command -v kquitapp6 &> /dev/null; then
    QUIT_CMD="kquitapp6"
elif command -v kquitapp5 &> /dev/null; then
    QUIT_CMD="kquitapp5"
else
    echo "Neither kquitapp6 nor kquitapp5 found. Attempting killall..."
    QUIT_CMD="false"
fi

echo "Restarting Plasma Shell..."

# Kill plasma
if [ "$QUIT_CMD" != "false" ]; then
    $QUIT_CMD plasmashell || killall plasmashell
else
    killall plasmashell
fi

# Wait for it to die
sleep 2

# Start it back up
kstart plasmashell > /dev/null 2>&1 &

echo "Plasma Shell restarted."
