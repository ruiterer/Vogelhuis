#!/bin/bash
# Birdcam — Automated smoke tests
# Run as root on the Raspberry Pi: sudo bash tests/smoke_test.sh

set -uo pipefail

PASS=0
FAIL=0
SKIP=0

pass() { echo -e "  \033[32mPASS\033[0m $*"; PASS=$((PASS + 1)); }
fail() { echo -e "  \033[31mFAIL\033[0m $*"; FAIL=$((FAIL + 1)); }
skip() { echo -e "  \033[33mSKIP\033[0m $*"; SKIP=$((SKIP + 1)); }

echo "=== Birdcam Smoke Tests ==="
echo ""

# --- File and directory checks ---
echo "[Files & Directories]"

[ -f /etc/birdcam/birdcam.yml ] && pass "Config file exists" || fail "Config file missing"
[ -d /opt/birdcam/src ] && pass "App directory exists" || fail "App directory missing"
[ -d /var/lib/birdcam/snapshots ] && pass "Snapshot directory exists" || fail "Snapshot directory missing"
[ -d /var/log/birdcam ] && pass "Log directory exists" || fail "Log directory missing"
[ -x /opt/birdcam/src/stream.sh ] && pass "stream.sh is executable" || fail "stream.sh not executable"
[ -x /opt/birdcam/src/cleanup.sh ] && pass "cleanup.sh is executable" || fail "cleanup.sh not executable"
[ -f /opt/birdcam/src/static/js/hls.min.js ] && pass "hls.js present" || fail "hls.js missing"
[ -f /opt/birdcam/venv/bin/python ] && pass "Python venv exists" || fail "Python venv missing"

echo ""
echo "[Python Dependencies]"

/opt/birdcam/venv/bin/python -c "import flask" 2>/dev/null && pass "Flask importable" || fail "Flask not importable"
/opt/birdcam/venv/bin/python -c "import yaml" 2>/dev/null && pass "PyYAML importable" || fail "PyYAML not importable"
/opt/birdcam/venv/bin/python -c "import psutil" 2>/dev/null && pass "psutil importable" || fail "psutil not importable"
/opt/birdcam/venv/bin/python -c "import gunicorn" 2>/dev/null && pass "gunicorn importable" || fail "gunicorn not importable"

echo ""
echo "[System Services]"

for svc in birdcam-stream birdcam-web nginx; do
    status=$(systemctl is-active "$svc" 2>/dev/null)
    if [ "$status" = "active" ]; then
        pass "$svc is active"
    else
        fail "$svc is $status"
    fi
done

status=$(systemctl is-active birdcam-cleanup.timer 2>/dev/null)
[ "$status" = "active" ] && pass "cleanup timer is active" || fail "cleanup timer is $status"

echo ""
echo "[Network]"

curl -sf -o /dev/null http://127.0.0.1/ && pass "Web UI reachable on port 80" || fail "Web UI not reachable"
curl -sf -o /dev/null http://127.0.0.1/health && pass "Health page reachable" || fail "Health page not reachable"
curl -sf -o /dev/null http://127.0.0.1/settings && pass "Settings page reachable" || fail "Settings page not reachable"
curl -sf http://127.0.0.1/api/health | python3 -c "import sys,json;json.load(sys.stdin)" 2>/dev/null \
    && pass "Health API returns valid JSON" || fail "Health API broken"

echo ""
echo "[HLS Stream]"

if [ -f /dev/shm/birdcam/stream.m3u8 ]; then
    pass "HLS playlist exists"
    segment_count=$(ls /dev/shm/birdcam/seg_*.ts 2>/dev/null | wc -l)
    [ "$segment_count" -gt 0 ] && pass "HLS segments present ($segment_count)" || fail "No HLS segments"
    curl -sf -o /dev/null http://127.0.0.1/hls/stream.m3u8 \
        && pass "HLS playlist served via nginx" || fail "HLS playlist not served"
else
    fail "HLS playlist missing (camera may not be connected)"
fi

echo ""
echo "[Camera]"

if rpicam-hello --list-cameras 2>/dev/null | grep -q "Available"; then
    pass "Camera detected by libcamera"
else
    skip "Camera not detected (may not be connected)"
fi

echo ""
echo "[Nginx Config]"

nginx -t 2>/dev/null && pass "Nginx config valid" || fail "Nginx config invalid"

echo ""
echo "[Sudoers]"

[ -f /etc/sudoers.d/birdcam ] && pass "Sudoers rule installed" || fail "Sudoers rule missing"

echo ""
echo "=== Results: $PASS passed, $FAIL failed, $SKIP skipped ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
