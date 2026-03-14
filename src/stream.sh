#!/bin/bash
# Birdcam streaming pipeline: rpicam-vid → ffmpeg → HLS
# Runs as a systemd service. Reads config from /etc/birdcam/birdcam.yml.

set -euo pipefail

CONFIG="/etc/birdcam/birdcam.yml"

# Read a config value using Python + PyYAML
get_config() {
    python3 -c "
import yaml
with open('$CONFIG') as f:
    c = yaml.safe_load(f)
print($1)
"
}

# Resolution mapping
get_dimensions() {
    case "$1" in
        480p)  echo "854 480" ;;
        720p)  echo "1280 720" ;;
        1080p) echo "1920 1080" ;;
        *)     echo "1280 720" ;;
    esac
}

# Load configuration
RESOLUTION=$(get_config "c['stream']['resolution']")
FRAMERATE=$(get_config "c['stream']['framerate']")
HLS_PATH=$(get_config "c['hls']['path']")
SEGMENT_DURATION=$(get_config "c['hls']['segment_duration']")
PLAYLIST_SIZE=$(get_config "c['hls']['playlist_size']")

read -r WIDTH HEIGHT <<< "$(get_dimensions "$RESOLUTION")"

echo "Birdcam stream starting: ${WIDTH}x${HEIGHT} @ ${FRAMERATE}fps"
echo "HLS output: ${HLS_PATH}/stream.m3u8"

# Ensure HLS output directory exists (tmpfs)
mkdir -p "$HLS_PATH"

# Clean stale segments from previous run
rm -f "${HLS_PATH}"/*.ts "${HLS_PATH}"/*.m3u8

# Trap signals for clean shutdown
cleanup() {
    echo "Stopping stream..."
    kill -- -$$ 2>/dev/null || true
    rm -f "${HLS_PATH}"/*.ts "${HLS_PATH}"/*.m3u8
    echo "Stream stopped."
}
trap cleanup EXIT INT TERM

# Start the pipeline
# rpicam-vid: capture H.264 from camera using hardware encoder
# ffmpeg: remux into HLS segments (no re-encoding, copy only)
rpicam-vid \
    --camera 0 \
    --codec h264 \
    --width "$WIDTH" \
    --height "$HEIGHT" \
    --framerate "$FRAMERATE" \
    --bitrate 0 \
    --profile main \
    --level 4.2 \
    --inline \
    --nopreview \
    --timeout 0 \
    --output - \
  | ffmpeg \
    -hide_banner \
    -loglevel warning \
    -fflags +genpts \
    -i pipe:0 \
    -c:v copy \
    -f hls \
    -hls_time "$SEGMENT_DURATION" \
    -hls_list_size "$PLAYLIST_SIZE" \
    -hls_flags delete_segments+temp_file \
    -hls_segment_filename "${HLS_PATH}/seg_%03d.ts" \
    "${HLS_PATH}/stream.m3u8"
