#!/bin/bash
# Birdcam — Full installation script for Raspberry Pi OS Lite
# Run as root: sudo bash install.sh

set -euo pipefail

APP_DIR="/opt/birdcam"
CONFIG_DIR="/etc/birdcam"
CONFIG_FILE="${CONFIG_DIR}/birdcam.yml"
LOG_DIR="/var/log/birdcam"
SNAP_DIR="/var/lib/birdcam/snapshots"
HLS_DIR="/dev/shm/birdcam"
VENV_DIR="${APP_DIR}/venv"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
HLS_JS_VERSION="1.5.13"
CHARTJS_VERSION="4.4.7"

# --- Helpers ---

info() { echo -e "\033[1;34m[INFO]\033[0m $*"; }
ok()   { echo -e "\033[1;32m[OK]\033[0m $*"; }
err()  { echo -e "\033[1;31m[ERROR]\033[0m $*" >&2; }

check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        err "This script must be run as root (sudo bash install.sh)"
        exit 1
    fi
}

check_pi() {
    if [ ! -f /proc/device-tree/model ]; then
        err "This does not appear to be a Raspberry Pi"
        exit 1
    fi
    info "Detected: $(cat /proc/device-tree/model)"
}

# --- Installation steps ---

install_system_packages() {
    info "Updating package index..."
    apt-get update -qq

    info "Installing system packages..."
    apt-get install -y -qq \
        curl \
        ffmpeg \
        nginx \
        python3-venv \
        python3-pip \
        python3-libgpiod \
        libgpiod-dev \
        rpicam-apps \
        > /dev/null

    ok "System packages installed"
}

create_user() {
    if id "birdcam" &>/dev/null; then
        info "User 'birdcam' already exists"
    else
        useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin birdcam
        ok "Created system user 'birdcam'"
    fi

    # Add birdcam user to video group (camera access) and gpio group
    usermod -aG video,gpio birdcam
}

setup_directories() {
    mkdir -p "$APP_DIR" "$CONFIG_DIR" "$LOG_DIR" "$SNAP_DIR" "$HLS_DIR"
    chown birdcam:birdcam "$LOG_DIR" "$SNAP_DIR" "$HLS_DIR"
    # Database lives under /var/lib/birdcam — ensure birdcam can write there
    chown birdcam:birdcam /var/lib/birdcam
    ok "Directories created"
}

install_python_env() {
    info "Setting up Python virtual environment..."
    python3 -m venv --system-site-packages "$VENV_DIR"
    "${VENV_DIR}/bin/pip" install --quiet --upgrade pip
    "${VENV_DIR}/bin/pip" install --quiet -r "${REPO_DIR}/requirements.txt"
    # GPIO and sensor libraries (Pi-only, may fail on other platforms)
    "${VENV_DIR}/bin/pip" install --quiet gpiod RPi.GPIO adafruit-circuitpython-dht 2>/dev/null || \
        info "GPIO/DHT libraries install skipped (install manually on Pi if needed)"
    ok "Python environment ready"
}

install_app_files() {
    info "Installing application files..."
    cp -r "${REPO_DIR}/src" "$APP_DIR/"
    chmod +x "${APP_DIR}/src/stream.sh" "${APP_DIR}/src/cleanup.sh"
    chown -R birdcam:birdcam "$APP_DIR"
    ok "Application files installed"
}

install_hlsjs() {
    local js_dir="${APP_DIR}/src/static/js"
    if [ -f "${js_dir}/hls.min.js" ] && [ -s "${js_dir}/hls.min.js" ]; then
        info "hls.js already present"
    else
        info "Downloading hls.js v${HLS_JS_VERSION}..."
        curl -sL "https://cdn.jsdelivr.net/npm/hls.js@${HLS_JS_VERSION}/dist/hls.min.js" \
            -o "${js_dir}/hls.min.js"
        chown birdcam:birdcam "${js_dir}/hls.min.js"
        ok "hls.js installed"
    fi
}

install_chartjs() {
    local js_dir="${APP_DIR}/src/static/js"
    if [ -f "${js_dir}/chart.min.js" ] && [ -s "${js_dir}/chart.min.js" ]; then
        info "Chart.js already present"
    else
        info "Downloading Chart.js v${CHARTJS_VERSION}..."
        curl -sL "https://cdn.jsdelivr.net/npm/chart.js@${CHARTJS_VERSION}/dist/chart.umd.min.js" \
            -o "${js_dir}/chart.min.js"
        chown birdcam:birdcam "${js_dir}/chart.min.js"
        ok "Chart.js installed"
    fi
}

install_config() {
    if [ -f "$CONFIG_FILE" ]; then
        info "Config already exists at ${CONFIG_FILE}, preserving it"
    else
        cp "${REPO_DIR}/birdcam.yml.default" "$CONFIG_FILE"
        chown birdcam:birdcam "$CONFIG_FILE"
        ok "Default config installed at ${CONFIG_FILE}"
    fi
}

install_systemd_units() {
    info "Installing systemd units..."
    cp "${REPO_DIR}"/systemd/*.service /etc/systemd/system/
    cp "${REPO_DIR}"/systemd/*.timer /etc/systemd/system/
    systemctl daemon-reload

    systemctl enable birdcam-stream.service
    systemctl enable birdcam-web.service
    systemctl enable birdcam-gpio.service
    systemctl enable birdcam-cleanup.timer

    ok "Systemd units installed and enabled"
}

install_nginx() {
    info "Configuring nginx..."
    cp "${REPO_DIR}/nginx/birdcam.conf" /etc/nginx/sites-available/birdcam

    # Disable default site if present
    rm -f /etc/nginx/sites-enabled/default

    # Enable birdcam site
    ln -sf /etc/nginx/sites-available/birdcam /etc/nginx/sites-enabled/birdcam

    # Test config
    nginx -t
    ok "Nginx configured"
}

setup_sudoers() {
    local sudoers_file="/etc/sudoers.d/birdcam"
    cat > "$sudoers_file" <<'EOF'
# Allow birdcam user to restart its own stream service
birdcam ALL=(ALL) NOPASSWD: /bin/systemctl restart birdcam-stream
birdcam ALL=(ALL) NOPASSWD: /bin/systemctl restart birdcam-gpio
birdcam ALL=(ALL) NOPASSWD: /bin/systemctl status birdcam-stream
birdcam ALL=(ALL) NOPASSWD: /bin/systemctl status birdcam-web
birdcam ALL=(ALL) NOPASSWD: /bin/systemctl status birdcam-gpio
birdcam ALL=(ALL) NOPASSWD: /bin/systemctl status nginx
EOF
    chmod 440 "$sudoers_file"
    ok "Sudoers rules installed"
}

set_timezone() {
    local tz
    tz=$(python3 -c "
import yaml
with open('${CONFIG_FILE}') as f:
    c = yaml.safe_load(f)
print(c.get('system', {}).get('timezone', 'Europe/Amsterdam'))
" 2>/dev/null || echo "Europe/Amsterdam")
    timedatectl set-timezone "$tz"
    ok "Timezone set to ${tz}"
}

start_services() {
    info "Starting services..."
    systemctl start birdcam-stream
    systemctl start birdcam-web
    systemctl start birdcam-gpio
    systemctl start birdcam-cleanup.timer
    systemctl restart nginx
    ok "All services started"
}

print_summary() {
    local ip
    ip=$(hostname -I | awk '{print $1}')
    echo ""
    echo "============================================"
    echo "  Birdcam installation complete!"
    echo "============================================"
    echo ""
    echo "  Live stream:  http://${ip}/"
    echo "  Settings:     http://${ip}/settings"
    echo "  Graphs:       http://${ip}/graphs"
    echo "  Health:       http://${ip}/health"
    echo ""
    echo "  Config file:  ${CONFIG_FILE}"
    echo "  Snapshots:    ${SNAP_DIR}"
    echo "  Logs:         ${LOG_DIR}"
    echo ""
    echo "  Service commands:"
    echo "    sudo systemctl status birdcam-stream"
    echo "    sudo systemctl restart birdcam-stream"
    echo "    sudo journalctl -u birdcam-stream -f"
    echo ""
    echo "  Also accessible via: http://$(hostname).local/"
    echo "============================================"
}

# --- Main ---

main() {
    info "Starting Birdcam installation..."
    check_root
    check_pi
    install_system_packages
    create_user
    setup_directories
    install_python_env
    install_app_files
    install_hlsjs
    install_chartjs
    install_config
    install_systemd_units
    install_nginx
    setup_sudoers
    set_timezone
    start_services
    print_summary
}

main "$@"
