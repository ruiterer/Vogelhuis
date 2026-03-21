"""Birdcam — Flask web application."""

import os
import subprocess
import time

from flask import Flask, render_template, jsonify, request, send_from_directory, abort

import config as cfg
from health import get_full_health
from snapshot import take_snapshot, list_snapshots
from logs import get_logs, get_sources
from logging_setup import get_logger

app = Flask(__name__)

# Simple rate limiting for snapshot endpoint
_last_snapshot_time = 0
SNAPSHOT_MIN_INTERVAL = 3  # seconds between snapshots

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
    if not filename.endswith("_snapshot.jpg") or "/" in filename:
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

    errors = cfg.validate(current)
    if errors:
        return jsonify({"error": errors}), 400

    cfg.save(current)
    logger.info("Configuration updated")
    return jsonify({"status": "saved", "restart_required": _stream_config_changed(new_config)})


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


def _stream_config_changed(new_config):
    """Check if stream-related config was changed (requires service restart)."""
    if "stream" not in new_config:
        return False
    s = new_config["stream"]
    return "resolution" in s or "framerate" in s or "rotation" in s


# --- Error handlers ---

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=True)
