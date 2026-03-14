#!/bin/bash
# Birdcam — Uninstall script
# Run as root: sudo bash uninstall.sh

set -euo pipefail

info() { echo -e "\033[1;34m[INFO]\033[0m $*"; }
ok()   { echo -e "\033[1;32m[OK]\033[0m $*"; }

if [ "$(id -u)" -ne 0 ]; then
    echo "This script must be run as root (sudo bash uninstall.sh)"
    exit 1
fi

echo "This will remove Birdcam services, files, and the birdcam user."
echo "Snapshots in /var/lib/birdcam/snapshots will be PRESERVED."
echo ""
read -p "Continue? (y/N) " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo "Aborted."
    exit 0
fi

info "Stopping services..."
systemctl stop birdcam-stream 2>/dev/null || true
systemctl stop birdcam-web 2>/dev/null || true
systemctl stop birdcam-cleanup.timer 2>/dev/null || true

info "Disabling services..."
systemctl disable birdcam-stream 2>/dev/null || true
systemctl disable birdcam-web 2>/dev/null || true
systemctl disable birdcam-cleanup.timer 2>/dev/null || true

info "Removing systemd units..."
rm -f /etc/systemd/system/birdcam-stream.service
rm -f /etc/systemd/system/birdcam-web.service
rm -f /etc/systemd/system/birdcam-cleanup.service
rm -f /etc/systemd/system/birdcam-cleanup.timer
systemctl daemon-reload

info "Removing nginx config..."
rm -f /etc/nginx/sites-enabled/birdcam
rm -f /etc/nginx/sites-available/birdcam
systemctl restart nginx 2>/dev/null || true

info "Removing application files..."
rm -rf /opt/birdcam

info "Removing config..."
rm -rf /etc/birdcam

info "Removing logs..."
rm -rf /var/log/birdcam

info "Removing HLS tmpfs directory..."
rm -rf /dev/shm/birdcam

info "Removing sudoers rule..."
rm -f /etc/sudoers.d/birdcam

ok "Birdcam uninstalled."
echo ""
echo "Snapshots preserved at: /var/lib/birdcam/snapshots"
echo "To also remove snapshots: sudo rm -rf /var/lib/birdcam"
echo "To remove the birdcam user: sudo userdel birdcam"
