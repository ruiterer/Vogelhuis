"""System health monitoring for Birdcam."""

import os
import time
import subprocess
import psutil

from config import load as load_config


def get_cpu_percent():
    """Return CPU usage percentage (1-second sample)."""
    return psutil.cpu_percent(interval=1)


def get_memory():
    """Return memory usage dict."""
    mem = psutil.virtual_memory()
    return {
        "total_mb": round(mem.total / 1024 / 1024),
        "used_mb": round(mem.used / 1024 / 1024),
        "percent": mem.percent,
    }


def get_cpu_temperature():
    """Return CPU temperature in Celsius, or None if unavailable."""
    thermal_path = "/sys/class/thermal/thermal_zone0/temp"
    try:
        with open(thermal_path) as f:
            return round(int(f.read().strip()) / 1000, 1)
    except (FileNotFoundError, ValueError):
        return None


def get_disk_usage():
    """Return disk usage for the root filesystem."""
    usage = psutil.disk_usage("/")
    return {
        "total_gb": round(usage.total / 1024 / 1024 / 1024, 1),
        "used_gb": round(usage.used / 1024 / 1024 / 1024, 1),
        "free_gb": round(usage.free / 1024 / 1024 / 1024, 1),
        "percent": usage.percent,
    }


def get_uptime():
    """Return system uptime as a human-readable string."""
    try:
        with open("/proc/uptime") as f:
            seconds = float(f.read().split()[0])
    except (FileNotFoundError, ValueError):
        return "unknown"
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def get_service_status(service_name):
    """Check if a systemd service is active."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service_name],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "unknown"


def get_camera_status():
    """Check camera health by verifying HLS segments are fresh."""
    config = load_config()
    hls_path = config["hls"]["path"]
    playlist = os.path.join(hls_path, "stream.m3u8")

    if not os.path.exists(playlist):
        return {"status": "offline", "detail": "No HLS playlist found"}

    age = time.time() - os.path.getmtime(playlist)
    if age > 10:
        return {"status": "stale", "detail": f"Playlist not updated for {int(age)}s"}

    return {"status": "online", "detail": "Stream active"}


def get_full_health():
    """Return complete health report."""
    return {
        "cpu_percent": get_cpu_percent(),
        "memory": get_memory(),
        "cpu_temperature": get_cpu_temperature(),
        "disk": get_disk_usage(),
        "uptime": get_uptime(),
        "camera": get_camera_status(),
        "services": {
            "birdcam-stream": get_service_status("birdcam-stream"),
            "birdcam-web": get_service_status("birdcam-web"),
            "nginx": get_service_status("nginx"),
        },
    }
