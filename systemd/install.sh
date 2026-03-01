#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "ERROR: This script requires Linux with systemd."
    echo ""
    echo "On macOS, use the launchd installer instead:"
    echo "  bash launchd/install.sh"
    exit 1
fi

if ! command -v systemctl &>/dev/null; then
    echo "ERROR: systemctl not found. This script requires a Linux system with systemd."
    exit 1
fi

INSTALL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CURRENT_USER="$(whoami)"
SYSTEMD_DIR="/etc/systemd/system"

echo "Installing Mortgage Monitor systemd units..."
echo "  Install dir : $INSTALL_DIR"
echo "  Running as  : $CURRENT_USER"
echo ""

echo "Stopping existing services..."
systemctl stop mortgage-monitor-web.service 2>/dev/null || true
systemctl stop mortgage-monitor.timer 2>/dev/null || true
systemctl stop mortgage-monitor.service 2>/dev/null || true
echo ""

for UNIT in mortgage-monitor.service mortgage-monitor.timer mortgage-monitor-web.service; do
    SRC="$INSTALL_DIR/systemd/$UNIT"
    DEST="$SYSTEMD_DIR/$UNIT"
    sed \
        -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" \
        -e "s|__USER__|$CURRENT_USER|g" \
        "$SRC" > "$DEST"
    echo "  Written: $DEST"
done

systemctl daemon-reload
echo ""
echo "Enabling and starting services..."
systemctl enable --now mortgage-monitor.timer
systemctl enable --now mortgage-monitor-web.service
echo ""
echo "Done. Check status with:"
echo "  systemctl status mortgage-monitor.timer"
echo "  systemctl status mortgage-monitor-web.service"
echo "  journalctl -u mortgage-monitor -f"
