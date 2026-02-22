#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "ERROR: This script is for macOS only."
    echo ""
    echo "On Linux, use the systemd installer instead:"
    echo "  sudo bash systemd/install.sh"
    exit 1
fi

INSTALL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
LOGS_DIR="$INSTALL_DIR/logs"

echo "Installing Mortgage Monitor launchd agents..."
echo "  Install dir : $INSTALL_DIR"
echo "  LaunchAgents: $LAUNCH_AGENTS_DIR"
echo ""

mkdir -p "$LAUNCH_AGENTS_DIR"
mkdir -p "$LOGS_DIR"

for PLIST in com.mortgage-monitor.run.plist com.mortgage-monitor.web.plist; do
    SRC="$INSTALL_DIR/launchd/$PLIST"
    DEST="$LAUNCH_AGENTS_DIR/$PLIST"

    sed "s|__INSTALL_DIR__|$INSTALL_DIR|g" "$SRC" > "$DEST"
    echo "  Written: $DEST"

    # Unload first in case it was previously loaded
    launchctl unload "$DEST" 2>/dev/null || true
    launchctl load "$DEST"
    echo "  Loaded:  $PLIST"
done

echo ""
echo "Done. The web UI will start automatically at login."
echo ""
echo "Useful commands:"
echo "  launchctl list | grep mortgage     # check agents are loaded"
echo "  tail -f $LOGS_DIR/web.log         # web UI logs"
echo "  tail -f $LOGS_DIR/run.log         # weekly check logs"
echo ""
echo "To trigger the weekly check manually right now:"
echo "  launchctl start com.mortgage-monitor.run"
echo ""
echo "To uninstall:"
echo "  launchctl unload ~/Library/LaunchAgents/com.mortgage-monitor.run.plist"
echo "  launchctl unload ~/Library/LaunchAgents/com.mortgage-monitor.web.plist"
