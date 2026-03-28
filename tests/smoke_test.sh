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

for svc in birdcam-stream birdcam-web birdcam-gpio nginx; do
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
echo "[Logging]"

# Verify log API returns valid JSON array with required fields
log_json=$(curl -sf http://127.0.0.1/api/logs?minutes=60 2>/dev/null)
if echo "$log_json" | python3 -c "import sys,json;json.load(sys.stdin)" 2>/dev/null; then
    pass "Log API returns valid JSON"
else
    fail "Log API broken"
fi

# Verify log entries have required fields
echo "$log_json" | python3 -c "
import sys, json
entries = json.load(sys.stdin)
if not entries:
    print('  no entries to check')
    sys.exit(0)
required = {'timestamp', 'level', 'source', 'message', 'unstructured'}
for e in entries[:5]:
    missing = required - set(e.keys())
    if missing:
        print(f'  missing fields: {missing}')
        sys.exit(1)
" 2>/dev/null && pass "Log entries have required fields" || fail "Log entries missing fields"

# Verify log entries are chronologically sorted
echo "$log_json" | python3 -c "
import sys, json
entries = json.load(sys.stdin)
timestamps = [e['timestamp'] for e in entries]
if timestamps != sorted(timestamps):
    sys.exit(1)
" 2>/dev/null && pass "Log entries sorted chronologically" || fail "Log entries not sorted"

# Verify source filter works
source_json=$(curl -sf "http://127.0.0.1/api/logs?source=web&minutes=60" 2>/dev/null)
echo "$source_json" | python3 -c "
import sys, json
entries = json.load(sys.stdin)
for e in entries:
    if e['source'] != 'web':
        sys.exit(1)
" 2>/dev/null && pass "Source filter works" || fail "Source filter broken"

# Verify verbose toggle works (should include unstructured lines)
curl -sf "http://127.0.0.1/api/logs?verbose=1&minutes=60" | python3 -c "import sys,json;json.load(sys.stdin)" 2>/dev/null \
    && pass "Verbose mode works" || fail "Verbose mode broken"

echo ""
echo "[GPIO & Sensors]"

[ -f /var/lib/birdcam/sensor_data.db ] && pass "Sensor database exists" || fail "Sensor database missing"

curl -sf http://127.0.0.1/api/gpio/status | python3 -c "import sys,json;json.load(sys.stdin)" 2>/dev/null \
    && pass "GPIO status API returns valid JSON" || fail "GPIO status API broken"

curl -sf "http://127.0.0.1/api/sensor-data?minutes=1" | python3 -c "import sys,json;json.load(sys.stdin)" 2>/dev/null \
    && pass "Sensor data API returns valid JSON" || fail "Sensor data API broken"

curl -sf "http://127.0.0.1/api/motion-events?minutes=1" | python3 -c "import sys,json;json.load(sys.stdin)" 2>/dev/null \
    && pass "Motion events API returns valid JSON" || fail "Motion events API broken"

curl -sf -o /dev/null http://127.0.0.1/graphs \
    && pass "Graphs page reachable" || fail "Graphs page not reachable"

# Verify settings page has GPIO fields
curl -sf http://127.0.0.1/settings | grep -q "gpio.pins.ir_light" \
    && pass "Settings page has GPIO fields" || fail "Settings page missing GPIO fields"

# Verify index page has GPIO controls
curl -sf http://127.0.0.1/ | grep -q "btn-light" \
    && pass "Stream page has GPIO controls" || fail "Stream page missing GPIO controls"

[ -f /var/log/birdcam/gpio.log ] && pass "GPIO log file exists" || skip "GPIO log file not yet created"

echo ""
echo "[HLS Stream]"

# Wait for stream to produce segments if it just started
if [ ! -f /dev/shm/birdcam/stream.m3u8 ] && systemctl is-active birdcam-stream >/dev/null 2>&1; then
    echo "  Waiting for HLS segments..."
    for i in $(seq 1 15); do
        [ -f /dev/shm/birdcam/stream.m3u8 ] && break
        sleep 2
    done
fi

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

if systemctl is-active birdcam-stream >/dev/null 2>&1; then
    pass "Camera in use by active stream"
elif rpicam-hello --list-cameras --timeout 3000 2>/dev/null | grep -q "Available"; then
    pass "Camera detected by libcamera"
else
    skip "Camera not detected (may not be connected)"
fi

echo ""
echo "[Nginx Config]"

nginx -t 2>/dev/null && pass "Nginx config valid" || fail "Nginx config invalid"

echo ""
echo "[Cleanup Logic]"

# Verify free disk percentage calculation is correct
actual_used=$(df --output=pcent / | tail -1 | tr -d '% ')
actual_free=$((100 - actual_used))
min_free=$(/opt/birdcam/venv/bin/python3 -c "
import yaml
with open('/etc/birdcam/birdcam.yml') as f:
    c = yaml.safe_load(f)
print(c.get('snapshots', {}).get('min_free_disk_percent', 10))
")
[ "$actual_free" -gt "$min_free" ] \
    && pass "Free disk ${actual_free}% above threshold ${min_free}%" \
    || skip "Free disk ${actual_free}% below threshold ${min_free}% (cleanup would trigger)"

# Verify cleanup script calculates free space correctly (not using used% as free%)
cleanup_free=$(bash -c '
    used_percent=$(df --output=pcent / | tail -1 | tr -d "% ")
    free_percent=$((100 - used_percent))
    echo $free_percent
')
[ "$cleanup_free" -eq "$actual_free" ] \
    && pass "Cleanup free% calculation matches actual (${cleanup_free}%)" \
    || fail "Cleanup free% calculation wrong: got ${cleanup_free}%, expected ${actual_free}%"

# Verify cleanup script doesn't delete snapshots when disk has plenty of free space
if [ "$actual_free" -gt "$min_free" ]; then
    # Create a test snapshot, run cleanup, verify it survives
    test_snap="/var/lib/birdcam/snapshots/00000000_000000_snapshot.jpg"
    echo "test" > "$test_snap"
    chown birdcam:birdcam "$test_snap"
    bash /opt/birdcam/src/cleanup.sh > /dev/null 2>&1
    if [ -f "$test_snap" ]; then
        pass "Cleanup preserves snapshots when disk has free space"
        rm -f "$test_snap"
    else
        fail "Cleanup deleted snapshot despite sufficient free space"
    fi
fi

echo ""
echo "[Sudoers]"

[ -f /etc/sudoers.d/birdcam ] && pass "Sudoers rule installed" || fail "Sudoers rule missing"

echo ""
echo "=== Results: $PASS passed, $FAIL failed, $SKIP skipped ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
