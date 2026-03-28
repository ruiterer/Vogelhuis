"""Birdcam — Flask web application."""

import json
import os
import subprocess
import time

from flask import Flask, render_template, jsonify, request, send_from_directory, abort

import config as cfg
from database import get_sensor_data, get_motion_events, get_latest_reading
from health import get_full_health
from snapshot import take_snapshot, list_snapshots
from logs import get_logs, get_sources
from logging_setup import get_logger

app = Flask(__name__)

# Simple rate limiting for snapshot endpoint
_last_snapshot_time = 0
SNAPSHOT_MIN_INTERVAL = 3  # seconds between snapshots

# GPIO command file (shared with gpio_service via /dev/shm)
GPIO_COMMAND_FILE = "/dev/shm/birdcam/gpio_commands"
GPIO_STATUS_FILE = "/dev/shm/birdcam/gpio_status.json"

logger = get_logger("web")


# --- Pages ---

@app.route("/")
def index():
    conf = cfg.load()
    return render_template("index.html", config=conf)


@app.route("/settings")
def settings():
    conf = cfg.load()
    return render_template("settings.html", config=conf,
                           resolutions=cfg.VALID_RESOLUTIONS,
                           framerates=cfg.VALID_FRAMERATES)


@app.route("/health")
def health_page():
    conf = cfg.load()
    return render_template("health.html", config=conf, sources=get_sources())


@app.route("/graphs")
def graphs_page():
    conf = cfg.load()
    return render_template("graphs.html", config=conf)


# --- API ---

@app.route("/api/health")
def api_health():
    return jsonify(get_full_health())


@app.route("/api/snapshot", methods=["POST"])
def api_snapshot():
    global _last_snapshot_time
    now = time.time()
    if now - _last_snapshot_time < SNAPSHOT_MIN_INTERVAL:
        return jsonify({"error": "Please wait a few seconds between snapshots"}), 429

    try:
        filename = take_snapshot()
        _last_snapshot_time = time.time()
        return jsonify({"filename": filename, "url": f"/snapshots/{filename}"})
    except RuntimeError as e:
        logger.error("Snapshot failed: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/snapshots")
def api_snapshots():
    return jsonify(list_snapshots())


@app.route("/snapshots/<filename>")
def download_snapshot(filename):
    conf = cfg.load()
    snap_path = conf["snapshots"]["path"]
    # Sanitize: only allow filenames matching expected pattern
    if not filename.endswith(".jpg") or "/" in filename:
        abort(404)
    return send_from_directory(snap_path, filename, as_attachment=True)


@app.route("/api/config", methods=["GET"])
def api_config_get():
    return jsonify(cfg.load())


@app.route("/api/config", methods=["PUT"])
def api_config_put():
    new_config = request.get_json()
    if not new_config:
        return jsonify({"error": "Invalid JSON"}), 400

    current = cfg.load()

    # Apply allowed changes
    if "stream" in new_config:
        s = new_config["stream"]
        if "resolution" in s:
            current["stream"]["resolution"] = s["resolution"]
        if "framerate" in s:
            current["stream"]["framerate"] = int(s["framerate"])
        if "rotation" in s:
            current["stream"]["rotation"] = int(s["rotation"])

    if "ui" in new_config:
        if "title" in new_config["ui"]:
            current["ui"]["title"] = str(new_config["ui"]["title"])[:100]

    if "snapshots" in new_config:
        sn = new_config["snapshots"]
        if "retention_days" in sn:
            current["snapshots"]["retention_days"] = int(sn["retention_days"])
        if "min_free_disk_percent" in sn:
            current["snapshots"]["min_free_disk_percent"] = int(sn["min_free_disk_percent"])
        if "path" in sn:
            current["snapshots"]["path"] = str(sn["path"])

    if "system" in new_config:
        if "timezone" in new_config["system"]:
            current["system"]["timezone"] = str(new_config["system"]["timezone"])[:50]

    # GPIO config
    if "gpio" in new_config:
        g = new_config["gpio"]
        gpio = current["gpio"]
        if "enabled" in g:
            gpio["enabled"] = bool(g["enabled"])
        if "sensor_poll_interval" in g:
            gpio["sensor_poll_interval"] = int(g["sensor_poll_interval"])
        if "pins" in g:
            for pin_name in ("ir_light", "light", "fan", "dht22", "motion"):
                if pin_name in g["pins"]:
                    gpio["pins"][pin_name] = int(g["pins"][pin_name])
        if "fan" in g:
            if "on_temp" in g["fan"]:
                gpio["fan"]["on_temp"] = int(g["fan"]["on_temp"])
            if "off_temp" in g["fan"]:
                gpio["fan"]["off_temp"] = int(g["fan"]["off_temp"])
        if "light_schedule" in g:
            for key in ("night_start", "day_start"):
                if key in g["light_schedule"]:
                    gpio["light_schedule"][key] = str(g["light_schedule"][key])[:5]
        if "motion" in g:
            if "cooldown" in g["motion"]:
                gpio["motion"]["cooldown"] = int(g["motion"]["cooldown"])
        if "data_retention_days" in g:
            gpio["data_retention_days"] = int(g["data_retention_days"])

    # MQTT config
    if "mqtt" in new_config:
        m = new_config["mqtt"]
        mqtt = current["mqtt"]
        if "enabled" in m:
            mqtt["enabled"] = bool(m["enabled"])
        if "broker" in m:
            mqtt["broker"] = str(m["broker"])[:200]
        if "port" in m:
            mqtt["port"] = int(m["port"])
        if "topic" in m:
            mqtt["topic"] = str(m["topic"])[:200]
        if "location" in m:
            mqtt["location"] = str(m["location"])[:100]
        if "object_name" in m:
            mqtt["object_name"] = str(m["object_name"])[:100]
        if "publish_interval" in m:
            mqtt["publish_interval"] = int(m["publish_interval"])

    errors = cfg.validate(current)
    if errors:
        return jsonify({"error": errors}), 400

    cfg.save(current)
    logger.info("Configuration updated")

    gpio_restart = _gpio_config_changed(new_config)
    return jsonify({
        "status": "saved",
        "restart_required": _stream_config_changed(new_config),
        "gpio_restart_required": gpio_restart,
    })


@app.route("/api/logs")
def api_logs():
    source = request.args.get("source")
    level = request.args.get("level")
    minutes = request.args.get("minutes", type=int)
    verbose = request.args.get("verbose", "").lower() in ("1", "true", "yes")
    entries = get_logs(source=source, level=level, minutes=minutes, verbose=verbose)
    return jsonify(entries)


@app.route("/api/restart-stream", methods=["POST"])
def api_restart_stream():
    try:
        result = subprocess.run(
            ["sudo", "systemctl", "restart", "birdcam-stream"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            logger.info("Stream service restarted")
            return jsonify({"status": "restarting"})
        else:
            return jsonify({"error": result.stderr}), 500
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Restart command timed out"}), 500


# --- GPIO API ---

@app.route("/api/gpio/status")
def api_gpio_status():
    """Return current GPIO/sensor state from the status file."""
    try:
        with open(GPIO_STATUS_FILE, "r") as f:
            status = json.load(f)
        return jsonify(status)
    except (FileNotFoundError, json.JSONDecodeError):
        return jsonify({
            "light": False, "ir_light": False, "fan": False, "fan_auto": True,
            "motion": False, "temperature": None, "humidity": None,
            "cpu_temp": None, "cpu_load": None, "timestamp": None,
            "service_running": False,
        })


@app.route("/api/gpio/light", methods=["POST"])
def api_gpio_light():
    return _send_gpio_command("light")


@app.route("/api/gpio/ir-light", methods=["POST"])
def api_gpio_ir_light():
    return _send_gpio_command("ir_light")


@app.route("/api/gpio/fan", methods=["POST"])
def api_gpio_fan():
    return _send_gpio_command("fan")


@app.route("/api/restart-gpio", methods=["POST"])
def api_restart_gpio():
    try:
        result = subprocess.run(
            ["sudo", "systemctl", "restart", "birdcam-gpio"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            logger.info("GPIO service restarted")
            return jsonify({"status": "restarting"})
        else:
            return jsonify({"error": result.stderr}), 500
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Restart command timed out"}), 500


def _send_gpio_command(target):
    """Send a command to the GPIO service via the command file."""
    data = request.get_json()
    if data is None or "state" not in data:
        return jsonify({"error": "Missing 'state' in request body"}), 400

    state = bool(data["state"])
    cmd = json.dumps({"target": target, "state": state}) + "\n"

    try:
        os.makedirs(os.path.dirname(GPIO_COMMAND_FILE), exist_ok=True)
        with open(GPIO_COMMAND_FILE, "a") as f:
            f.write(cmd)
        logger.info("GPIO command: %s = %s", target, state)
        return jsonify({"status": "ok", "target": target, "state": state})
    except (PermissionError, OSError) as e:
        logger.error("Failed to send GPIO command: %s", e)
        return jsonify({"error": "GPIO service not available"}), 503


# --- Sensor data API ---

@app.route("/api/sensor-data")
def api_sensor_data():
    """Return sensor time-series data for graphs."""
    minutes = request.args.get("minutes", 1440, type=int)
    minutes = max(1, min(minutes, 43200))  # 1 min to 30 days
    data = get_sensor_data(minutes)
    return jsonify(data)


@app.route("/api/motion-events")
def api_motion_events():
    """Return motion events for the requested period."""
    minutes = request.args.get("minutes", 1440, type=int)
    minutes = max(1, min(minutes, 43200))
    events = get_motion_events(minutes)
    return jsonify(events)


def _stream_config_changed(new_config):
    """Check if stream-related config was changed (requires service restart)."""
    if "stream" not in new_config:
        return False
    s = new_config["stream"]
    return "resolution" in s or "framerate" in s or "rotation" in s


def _gpio_config_changed(new_config):
    """Check if GPIO-related config was changed (requires service restart)."""
    return "gpio" in new_config or "mqtt" in new_config


# --- Error handlers ---

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=True)
