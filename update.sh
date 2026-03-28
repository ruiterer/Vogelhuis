#!/bin/bash
# Birdcam — Update/redeploy script
# Run as root: sudo bash update.sh

set -euo pipefail

APP_DIR="/opt/birdcam"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
CHARTJS_VERSION="4.4.7"
CHARTJS_DATE_ADAPTER_VERSION="3.0.0"

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
systemctl stop birdcam-gpio || true

info "Updating application files..."
cp -r "${REPO_DIR}/src" "$APP_DIR/"
chmod +x "${APP_DIR}/src/stream.sh" "${APP_DIR}/src/cleanup.sh"
chown -R birdcam:birdcam "$APP_DIR"

info "Updating Python dependencies..."
"${APP_DIR}/venv/bin/pip" install --quiet -r "${REPO_DIR}/requirements.txt"
# GPIO and sensor libraries (Pi-only)
"${APP_DIR}/venv/bin/pip" install --quiet gpiod RPi.GPIO adafruit-circuitpython-dht 2>/dev/null || \
    info "GPIO/DHT libraries install skipped"

info "Installing Chart.js if missing..."
js_dir="${APP_DIR}/src/static/js"
if [ ! -f "${js_dir}/chart.min.js" ] || [ ! -s "${js_dir}/chart.min.js" ]; then
    curl -sL "https://cdn.jsdelivr.net/npm/chart.js@${CHARTJS_VERSION}/dist/chart.umd.min.js" \
        -o "${js_dir}/chart.min.js"
    chown birdcam:birdcam "${js_dir}/chart.min.js"
    ok "Chart.js installed"
fi

info "Installing Chart.js date adapter if missing..."
if [ ! -f "${js_dir}/chartjs-adapter-date-fns.bundle.min.js" ] || [ ! -s "${js_dir}/chartjs-adapter-date-fns.bundle.min.js" ]; then
    curl -sL "https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@${CHARTJS_DATE_ADAPTER_VERSION}/dist/chartjs-adapter-date-fns.bundle.min.js" \
        -o "${js_dir}/chartjs-adapter-date-fns.bundle.min.js"
    chown birdcam:birdcam "${js_dir}/chartjs-adapter-date-fns.bundle.min.js"
    ok "Chart.js date adapter installed"
fi

info "Updating systemd units..."
cp "${REPO_DIR}"/systemd/*.service /etc/systemd/system/
cp "${REPO_DIR}"/systemd/*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable birdcam-gpio.service 2>/dev/null || true

info "Updating nginx config..."
cp "${REPO_DIR}/nginx/birdcam.conf" /etc/nginx/sites-available/birdcam
nginx -t

info "Updating sudoers..."
cat > /etc/sudoers.d/birdcam <<'EOF'
# Allow birdcam user to restart its own services
birdcam ALL=(ALL) NOPASSWD: /bin/systemctl restart birdcam-stream
birdcam ALL=(ALL) NOPASSWD: /bin/systemctl restart birdcam-gpio
birdcam ALL=(ALL) NOPASSWD: /bin/systemctl status birdcam-stream
birdcam ALL=(ALL) NOPASSWD: /bin/systemctl status birdcam-web
birdcam ALL=(ALL) NOPASSWD: /bin/systemctl status birdcam-gpio
birdcam ALL=(ALL) NOPASSWD: /bin/systemctl status nginx
EOF
chmod 440 /etc/sudoers.d/birdcam

info "Ensuring birdcam user is in gpio group..."
usermod -aG gpio birdcam 2>/dev/null || true

info "Fixing log file permissions..."
chown -R birdcam:birdcam /var/log/birdcam

info "Restarting services..."
systemctl start birdcam-stream
systemctl start birdcam-web
systemctl start birdcam-gpio
systemctl restart nginx

ok "Update complete!"
echo ""
echo "Note: Your config at /etc/birdcam/birdcam.yml was preserved."
echo "If new config options were added, review birdcam.yml.default for new settings."
echo "New: GPIO/sensor service, sensor graphs at /graphs, MQTT support."
