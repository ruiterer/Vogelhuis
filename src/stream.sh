#!/bin/bash
# Birdcam streaming pipeline: rpicam-vid → ffmpeg → HLS
# Runs as a systemd service. Reads config from /etc/birdcam/birdcam.yml.

set -euo pipefail

CONFIG="/etc/birdcam/birdcam.yml"

# Structured logging to stderr (captured by systemd to log file)
log_info()  { echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO] [stream] $*" >&2; }
log_warn()  { echo "$(date '+%Y-%m-%d %H:%M:%S') [WARN] [stream] $*" >&2; }
log_error() { echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] [stream] $*" >&2; }

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
ROTATION=$(get_config "c.get('stream', {}).get('rotation', 0)")
CAMERA_MODEL=$(get_config "c.get('stream', {}).get('camera_model', 'auto')")
HLS_PATH=$(get_config "c['hls']['path']")
SEGMENT_DURATION=$(get_config "c['hls']['segment_duration']")
PLAYLIST_SIZE=$(get_config "c['hls']['playlist_size']")

read -r WIDTH HEIGHT <<< "$(get_dimensions "$RESOLUTION")"

# Resolve tuning file for camera model
TUNING_ARGS=()
if [ "$CAMERA_MODEL" != "auto" ]; then
    # Map model name to tuning filename
    case "$CAMERA_MODEL" in
        ov5647_noir)       TUNING_FILE="ov5647_noir.json" ;;
        imx219_noir)       TUNING_FILE="imx219_noir.json" ;;
        imx477_noir)       TUNING_FILE="imx477_noir.json" ;;
        imx708_noir)       TUNING_FILE="imx708_noir.json" ;;
        imx708_wide_noir)  TUNING_FILE="imx708_wide_noir.json" ;;
        *)                 TUNING_FILE="" ;;
    esac
    if [ -n "$TUNING_FILE" ]; then
        # Detect ISP: Pi 5 uses PiSP, older Pis use vc4 (bcm2835)
        if grep -q "Pi 5" /proc/device-tree/model 2>/dev/null; then
            ISP_DIR="pisp"
        else
            ISP_DIR="vc4"
        fi
        TUNING_PATH="/usr/share/libcamera/ipa/rpi/${ISP_DIR}/${TUNING_FILE}"
        if [ -f "$TUNING_PATH" ]; then
            TUNING_ARGS=(--tuning-file "$TUNING_PATH")
        else
            log_warn "Tuning file ${TUNING_PATH} not found, using auto detection"
        fi
    fi
fi

log_info "Stream starting: ${WIDTH}x${HEIGHT} @ ${FRAMERATE}fps, rotation=${ROTATION}, camera=${CAMERA_MODEL}"
log_info "HLS output: ${HLS_PATH}/stream.m3u8"

# Ensure HLS output directory exists (tmpfs)
mkdir -p "$HLS_PATH"

# Clean stale segments from previous run
rm -f "${HLS_PATH}"/*.ts "${HLS_PATH}"/*.m3u8

# Trap signals for clean shutdown
cleanup() {
    log_info "Stream stopping"
    # Kill all processes in our process group
    kill -- -$$ 2>/dev/null || true
    rm -f "${HLS_PATH}"/*.ts "${HLS_PATH}"/*.m3u8
    log_info "Stream stopped"
}
trap cleanup EXIT INT TERM

# Start the pipeline
# rpicam-vid: capture H.264 from camera using hardware encoder
# ffmpeg: remux into HLS segments (no re-encoding, copy only)
# stderr from both tools goes directly to the log (captured by systemd)
# Pi 5 uses libav backend and needs explicit format for stdout
LIBAV_FMT_ARGS=()
if grep -q "Pi 5" /proc/device-tree/model 2>/dev/null; then
    LIBAV_FMT_ARGS=(--libav-format h264)
fi

rpicam-vid \
    --camera 0 \
    --codec h264 \
    --width "$WIDTH" \
    --height "$HEIGHT" \
    --framerate "$FRAMERATE" \
    --rotation "$ROTATION" \
    "${TUNING_ARGS[@]}" \
    "${LIBAV_FMT_ARGS[@]}" \
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
