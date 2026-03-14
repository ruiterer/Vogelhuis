"""Configuration management for Birdcam."""

import copy
import os
import yaml

CONFIG_PATH = os.environ.get("BIRDCAM_CONFIG", "/etc/birdcam/birdcam.yml")

DEFAULTS = {
    "stream": {
        "resolution": "720p",
        "framerate": 25,
    },
    "ui": {
        "title": "Birdcam",
    },
    "snapshots": {
        "path": "/var/lib/birdcam/snapshots",
        "retention_days": 180,
        "min_free_disk_percent": 10,
    },
    "system": {
        "timezone": "Europe/Amsterdam",
        "log_retention_days": 7,
        "log_path": "/var/log/birdcam",
    },
    "hls": {
        "segment_duration": 2,
        "playlist_size": 5,
        "path": "/dev/shm/birdcam",
    },
}

RESOLUTION_MAP = {
    "480p": (854, 480),
    "720p": (1280, 720),
    "1080p": (1920, 1080),
}

VALID_FRAMERATES = [5, 15, 25, 30]
VALID_RESOLUTIONS = list(RESOLUTION_MAP.keys())


def _deep_merge(base, override):
    """Merge override dict into base dict recursively."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load():
    """Load configuration from disk, merged with defaults."""
    try:
        with open(CONFIG_PATH, "r") as f:
            user_config = yaml.safe_load(f) or {}
    except FileNotFoundError:
        user_config = {}
    return _deep_merge(DEFAULTS, user_config)


def save(config):
    """Save configuration to disk."""
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def get_resolution_dimensions(resolution_str):
    """Return (width, height) tuple for a resolution string like '720p'."""
    return RESOLUTION_MAP.get(resolution_str, RESOLUTION_MAP["720p"])


def validate(config):
    """Validate configuration values. Returns list of error strings."""
    errors = []
    res = config.get("stream", {}).get("resolution", "720p")
    if res not in VALID_RESOLUTIONS:
        errors.append(f"Invalid resolution: {res}. Must be one of {VALID_RESOLUTIONS}")

    fps = config.get("stream", {}).get("framerate", 25)
    if fps not in VALID_FRAMERATES:
        errors.append(f"Invalid framerate: {fps}. Must be one of {VALID_FRAMERATES}")

    threshold = config.get("snapshots", {}).get("min_free_disk_percent", 10)
    if not (1 <= threshold <= 50):
        errors.append(f"min_free_disk_percent must be between 1 and 50, got {threshold}")

    retention = config.get("snapshots", {}).get("retention_days", 180)
    if not (1 <= retention <= 3650):
        errors.append(f"retention_days must be between 1 and 3650, got {retention}")

    return errors
