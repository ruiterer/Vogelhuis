#!/bin/bash
# Birdcam cleanup: snapshot retention and log rotation.
# Runs hourly via systemd timer.

set -euo pipefail

CONFIG="/etc/birdcam/birdcam.yml"
LOG_TAG="birdcam-cleanup"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [$LOG_TAG] $*"
}

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
        log "Deleted $deleted snapshots older than $RETENTION_DAYS days"
    fi
fi

# --- Snapshot cleanup by disk space ---
if [ -d "$SNAP_PATH" ]; then
    free_percent=$(df --output=pcent / | tail -1 | tr -d '% ')
    used_percent=$((100 - free_percent))

    if [ "$free_percent" -lt "$MIN_FREE_PERCENT" ]; then
        log "Free disk space ${free_percent}% below threshold ${MIN_FREE_PERCENT}%, cleaning snapshots"
        # Delete oldest snapshots until threshold is met or no snapshots remain
        while [ "$free_percent" -lt "$MIN_FREE_PERCENT" ]; do
            oldest=$(ls -t "$SNAP_PATH"/*_snapshot.jpg 2>/dev/null | tail -1)
            if [ -z "$oldest" ]; then
                log "No more snapshots to delete, free space still at ${free_percent}%"
                break
            fi
            rm -f "$oldest"
            log "Deleted $oldest"
            free_percent=$(df --output=pcent / | tail -1 | tr -d '% ')
        done
        log "Free disk space now at ${free_percent}%"
    fi
fi

# --- Log retention ---
if [ -d "$LOG_PATH" ]; then
    deleted=$(find "$LOG_PATH" -name "*.log" -mtime +"$LOG_RETENTION_DAYS" -delete -print | wc -l)
    if [ "$deleted" -gt 0 ]; then
        log "Deleted $deleted log files older than $LOG_RETENTION_DAYS days"
    fi
fi

log "Cleanup complete"
