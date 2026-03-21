#!/bin/bash
# Birdcam cleanup: snapshot retention and log rotation.
# Runs hourly via systemd timer.

set -euo pipefail

CONFIG="/etc/birdcam/birdcam.yml"

log_info()  { echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO] [cleanup] $*"; }
log_warn()  { echo "$(date '+%Y-%m-%d %H:%M:%S') [WARN] [cleanup] $*"; }
log_error() { echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] [cleanup] $*"; }

get_config() {
    python3 -c "
import yaml
with open('$CONFIG') as f:
    c = yaml.safe_load(f)
print($1)
"
}

SNAP_PATH=$(get_config "c['snapshots']['path']")
RETENTION_DAYS=$(get_config "c['snapshots']['retention_days']")
MIN_FREE_PERCENT=$(get_config "c['snapshots']['min_free_disk_percent']")
LOG_PATH=$(get_config "c['system']['log_path']")
LOG_RETENTION_DAYS=$(get_config "c['system']['log_retention_days']")

# --- Snapshot retention by age ---
if [ -d "$SNAP_PATH" ]; then
    deleted=$(find "$SNAP_PATH" -name "*_snapshot.jpg" -mtime +"$RETENTION_DAYS" -delete -print | wc -l)
    if [ "$deleted" -gt 0 ]; then
        log_info "Deleted $deleted snapshots older than $RETENTION_DAYS days"
    fi
fi

# --- Snapshot cleanup by disk space ---
if [ -d "$SNAP_PATH" ]; then
    used_percent=$(df --output=pcent / | tail -1 | tr -d '% ')
    free_percent=$((100 - used_percent))

    if [ "$free_percent" -lt "$MIN_FREE_PERCENT" ]; then
        log_warn "Free disk space ${free_percent}% below threshold ${MIN_FREE_PERCENT}%, cleaning snapshots"
        # Delete oldest snapshots until threshold is met or no snapshots remain
        while [ "$free_percent" -lt "$MIN_FREE_PERCENT" ]; do
            oldest=$(ls -t "$SNAP_PATH"/*_snapshot.jpg 2>/dev/null | tail -1)
            if [ -z "$oldest" ]; then
                log_warn "No more snapshots to delete, free space still at ${free_percent}%"
                break
            fi
            rm -f "$oldest"
            log_info "Deleted $oldest"
            used_percent=$(df --output=pcent / | tail -1 | tr -d '% ')
            free_percent=$((100 - used_percent))
        done
        log_info "Free disk space now at ${free_percent}%"
    fi
fi

# --- Log retention ---
if [ -d "$LOG_PATH" ]; then
    deleted=$(find "$LOG_PATH" -name "*.log" -mtime +"$LOG_RETENTION_DAYS" -delete -print | wc -l)
    if [ "$deleted" -gt 0 ]; then
        log_info "Deleted $deleted log files older than $LOG_RETENTION_DAYS days"
    fi
fi

log_info "Cleanup complete"
