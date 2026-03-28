"""Snapshot capture from HLS stream for Birdcam."""

import glob
import os
import subprocess
import time
from datetime import datetime

from config import load as load_config
from logging_setup import get_logger

logger = get_logger("snapshot")


def _get_latest_segment():
    """Find the latest complete HLS segment by parsing the playlist."""
    config = load_config()
    hls_path = config["hls"]["path"]
    playlist_path = os.path.join(hls_path, "stream.m3u8")

    if not os.path.exists(playlist_path):
        return None

    segments = []
    with open(playlist_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                segments.append(os.path.join(hls_path, line))

    # Use second-to-last segment (latest fully written)
    if len(segments) >= 2:
        return segments[-2]
    elif segments:
        return segments[-1]
    return None


def take_snapshot():
    """Capture a JPEG snapshot from the current stream.

    Returns the filename on success, or raises an exception on failure.
    """
    config = load_config()
    snap_path = config["snapshots"]["path"]
    os.makedirs(snap_path, exist_ok=True)

    segment = _get_latest_segment()
    if not segment:
        logger.error("No HLS segment available — is the camera running?")
        raise RuntimeError("No HLS segment available — is the camera running?")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}.jpg"
    output_path = os.path.join(snap_path, filename)

    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", segment,
            "-frames:v", "1",
            "-q:v", "2",
            "-y",
            output_path,
        ],
        capture_output=True, text=True, timeout=10,
    )

    if result.returncode != 0:
        logger.error("ffmpeg snapshot failed: %s", result.stderr.strip())
        raise RuntimeError(f"ffmpeg snapshot failed: {result.stderr}")

    if not os.path.exists(output_path):
        logger.error("Snapshot file was not created")
        raise RuntimeError("Snapshot file was not created")

    logger.info("Snapshot captured: %s", filename)
    return filename


def list_snapshots():
    """Return list of snapshot filenames, newest first."""
    config = load_config()
    snap_path = config["snapshots"]["path"]
    if not os.path.isdir(snap_path):
        return []

    files = []
    for f in os.listdir(snap_path):
        if f.endswith(".jpg"):
            full = os.path.join(snap_path, f)
            files.append({
                "filename": f,
                "size_kb": round(os.path.getsize(full) / 1024),
                "timestamp": f.replace(".jpg", ""),
            })

    files.sort(key=lambda x: x["filename"], reverse=True)
    return files
