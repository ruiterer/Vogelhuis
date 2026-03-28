"""Configuration management for Birdcam."""

import copy
import os
import re

import yaml

from logging_setup import get_logger

logger = get_logger("config")

CONFIG_PATH = os.environ.get("BIRDCAM_CONFIG", "/etc/birdcam/birdcam.yml")

DEFAULTS = {
    "stream": {
        "resolution": "720p",
        "framerate": 25,
        "rotation": 0,
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
    "gpio": {
        "enabled": True,
        "sensor_poll_interval": 60,
        "pins": {
            "ir_light": 13,
            "light": 19,
            "fan": 22,
            "dht22": 4,
            "motion": 7,
        },
        "fan": {
            "on_temp": 50,
            "off_temp": 40,
        },
        "light_schedule": {
            "night_start": "21:15",
            "day_start": "06:30",
        },
        "motion": {
            "cooldown": 30,
        },
        "data_retention_days": 30,
    },
    "mqtt": {
        "enabled": False,
        "broker": "",
        "port": 1883,
        "topic": "birdcam/status",
        "location": "Tuin",
        "object_name": "Vogelhuis_Boom",
        "publish_interval": 60,
    },
}

RESOLUTION_MAP = {
    "480p": (854, 480),
    "720p": (1280, 720),
    "1080p": (1920, 1080),
}

VALID_FRAMERATES = [5, 15, 25, 30]
VALID_ROTATIONS = [0, 180]
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
    logger.info("Configuration saved")


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

    rotation = config.get("stream", {}).get("rotation", 0)
    if rotation not in VALID_ROTATIONS:
        errors.append(f"Invalid rotation: {rotation}. Must be one of {VALID_ROTATIONS}")

    threshold = config.get("snapshots", {}).get("min_free_disk_percent", 10)
    if not (1 <= threshold <= 50):
        errors.append(f"min_free_disk_percent must be between 1 and 50, got {threshold}")

    retention = config.get("snapshots", {}).get("retention_days", 180)
    if not (1 <= retention <= 3650):
        errors.append(f"retention_days must be between 1 and 3650, got {retention}")

    # GPIO validation
    gpio = config.get("gpio", {})
    if gpio.get("enabled", True):
        pins = gpio.get("pins", {})
        valid_bcm = range(0, 28)
        pin_values = {}
        for name in ("ir_light", "light", "fan", "dht22", "motion"):
            pin = pins.get(name)
            if pin is not None:
                if int(pin) not in valid_bcm:
                    errors.append(f"GPIO pin {name} ({pin}) must be 0-27")
                if int(pin) in pin_values.values():
                    dup_name = [k for k, v in pin_values.items() if v == int(pin)][0]
                    errors.append(f"GPIO pin conflict: {name} and {dup_name} both use pin {pin}")
                pin_values[name] = int(pin)

        poll = gpio.get("sensor_poll_interval", 60)
        if not (10 <= int(poll) <= 300):
            errors.append(f"sensor_poll_interval must be 10-300, got {poll}")

        fan = gpio.get("fan", {})
        on_temp = fan.get("on_temp", 50)
        off_temp = fan.get("off_temp", 40)
        if int(on_temp) <= int(off_temp):
            errors.append(f"fan on_temp ({on_temp}) must be greater than off_temp ({off_temp})")
        if not (30 <= int(on_temp) <= 85):
            errors.append(f"fan on_temp must be 30-85, got {on_temp}")
        if not (25 <= int(off_temp) <= 80):
            errors.append(f"fan off_temp must be 25-80, got {off_temp}")

        schedule = gpio.get("light_schedule", {})
        time_re = re.compile(r"^\d{2}:\d{2}$")
        for key in ("night_start", "day_start"):
            val = schedule.get(key, "")
            if not time_re.match(str(val)):
                errors.append(f"light_schedule.{key} must be HH:MM format, got '{val}'")

        cooldown = gpio.get("motion", {}).get("cooldown", 30)
        if not (5 <= int(cooldown) <= 600):
            errors.append(f"motion cooldown must be 5-600, got {cooldown}")

        data_ret = gpio.get("data_retention_days", 30)
        if not (1 <= int(data_ret) <= 365):
            errors.append(f"data_retention_days must be 1-365, got {data_ret}")

    # MQTT validation
    mqtt = config.get("mqtt", {})
    if mqtt.get("enabled", False):
        if not mqtt.get("broker", "").strip():
            errors.append("MQTT broker address is required when MQTT is enabled")
        port = mqtt.get("port", 1883)
        if not (1 <= int(port) <= 65535):
            errors.append(f"MQTT port must be 1-65535, got {port}")
        interval = mqtt.get("publish_interval", 60)
        if not (10 <= int(interval) <= 3600):
            errors.append(f"MQTT publish_interval must be 10-3600, got {interval}")

    if errors:
        logger.warning("Validation failed: %s", "; ".join(errors))
    return errors
