#!/bin/bash
# Birdcam — Update/redeploy script
# Run as root: sudo bash update.sh

set -euo pipefail

APP_DIR="/opt/birdcam"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

info() { echo -e "\033[1;34m[INFO]\033[0m $*"; }
ok()   { echo -e "\033[1;32m[OK]\033[0m $*"; }
err()  { echo -e "\033[1;31m[ERROR]\033[0m $*" >&2; }

if [ "$(id -u)" -ne 0 ]; then
    err "This script must be run as root (sudo bash update.sh)"
    exit 1
fi

info "Stopping services..."
systemctl stop birdcam-stream || true
systemctl stop birdcam-web || true

info "Updating application files..."
cp -r "${REPO_DIR}/src" "$APP_DIR/"
chmod +x "${APP_DIR}/src/stream.sh" "${APP_DIR}/src/cleanup.sh"
chown -R birdcam:birdcam "$APP_DIR"

info "Updating Python dependencies..."
"${APP_DIR}/venv/bin/pip" install --quiet -r "${REPO_DIR}/requirements.txt"

info "Updating systemd units..."
cp "${REPO_DIR}"/systemd/*.service /etc/systemd/system/
cp "${REPO_DIR}"/systemd/*.timer /etc/systemd/system/
systemctl daemon-reload

info "Updating nginx config..."
cp "${REPO_DIR}/nginx/birdcam.conf" /etc/nginx/sites-available/birdcam
nginx -t

info "Restarting services..."
systemctl start birdcam-stream
systemctl start birdcam-web
systemctl restart nginx

ok "Update complete!"
echo ""
echo "Note: Your config at /etc/birdcam/birdcam.yml was preserved."
echo "If new config options were added, review birdcam.yml.default for new settings."
