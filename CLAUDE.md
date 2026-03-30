# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Raspberry Pi birdhouse camera system — LAN-only, browser-based live HLS stream with web UI. Runs on Raspberry Pi OS Lite (Bookworm) with a Pi Camera 3 NoIR.

- **Repository**: https://github.com/ruiterer/Vogelhuis
- **Branch**: `main`

## Stack

- **Streaming**: rpicam-vid (hardware H.264) → ffmpeg (HLS segmenter, `-c:v copy`) → tmpfs
- **Web**: Flask + gunicorn (2 workers) on localhost:8080, behind nginx on port 80
- **Frontend**: Vanilla HTML/CSS/JS + hls.js (vendored, v1.5.13) + Chart.js (vendored, v4.4.7)
- **Config**: Single YAML file at `/etc/birdcam/birdcam.yml`
- **Logging**: Centralized via `logging_setup.py` — structured format (`YYYY-MM-DD HH:MM:SS [LEVEL] [source]`), stderr → systemd → log files, mtime-cached reader
- **GPIO**: `gpiod` (libgpiod) for pin control, `adafruit-circuitpython-dht` for DHT22 sensor
- **Database**: SQLite with WAL mode at `/var/lib/birdcam/sensor_data.db`
- **MQTT**: Optional `paho-mqtt` publishing for external dashboards
- **Services**: systemd units for stream, web, gpio, cleanup timer
- **Target hardware**: Pi 4B primary, Pi Zero 2 W and Pi 5 compatible

## Key Paths (on Pi)

- App code: `/opt/birdcam/src/`
- Config: `/etc/birdcam/birdcam.yml`
- HLS segments: `/dev/shm/birdcam/` (tmpfs)
- GPIO status/commands: `/dev/shm/birdcam/gpio_status.json`, `gpio_commands`
- Sensor database: `/var/lib/birdcam/sensor_data.db`
- Snapshots: `/var/lib/birdcam/snapshots/`
- Logs: `/var/log/birdcam/`
- Python venv: `/opt/birdcam/venv/`

## Source Modules

| Module | Purpose |
|--------|---------|
| `app.py` | Flask web app, API endpoints (including GPIO control and sensor data), config persistence |
| `config.py` | Config loading, defaults, validation (stream, GPIO, MQTT), resolution mapping |
| `database.py` | SQLite schema, sensor data recording, motion events, retention cleanup |
| `gpio_service.py` | Standalone daemon: GPIO init, fan/light control, DHT22/motion sensors, MQTT, data recording |
| `health.py` | System metrics, service status (stream, web, gpio, nginx), camera health checks |
| `logging_setup.py` | Centralized logger factory (`get_logger(source)`) and `SOURCE_FILE_MAP` registry |
| `logs.py` | Log file parsing with mtime caching, filtering, verbose/unstructured support |
| `snapshot.py` | Snapshot capture from HLS segments via ffmpeg |
| `stream.sh` | rpicam-vid → ffmpeg HLS pipeline |
| `cleanup.sh` | Hourly snapshot/log retention (age-based + disk space threshold) |

## Web UI & API

**Pages**: Live stream (`/`), Settings (`/settings`), Sensor Graphs (`/graphs`), Health dashboard (`/health`)

**API endpoints**:
- `/api/health` — system health report
- `/api/snapshot` (POST) — capture snapshot (rate-limited)
- `/api/snapshots` — list snapshots
- `/api/config` (GET/PUT) — configuration (stream, GPIO, MQTT)
- `/api/logs` (GET) — filterable by source/level/minutes/verbose
- `/api/restart-stream` (POST) — restart camera pipeline
- `/api/restart-gpio` (POST) — restart GPIO service
- `/api/gpio/status` — current switch states, sensor readings, motion
- `/api/gpio/light` (POST) — toggle normal light
- `/api/gpio/ir-light` (POST) — toggle IR light
- `/api/gpio/fan` (POST) — toggle fan
- `/api/sensor-data?minutes=N` — time-series sensor data for graphs
- `/api/motion-events?minutes=N` — motion event history

## GPIO & Sensor Architecture

- **Separate systemd service** (`birdcam-gpio.service`) — decoupled from web
- **IPC**: GPIO service writes status to `/dev/shm/birdcam/gpio_status.json` (web reads). Web writes commands to `gpio_commands` (GPIO service reads).
- **Light schedule**: Complementary — one time pair configures both IR and normal light. Manual override reverts at next scheduled transition.
- **Fan control**: CPU temperature hysteresis (configurable on/off thresholds). Manual override holds for one check cycle.
- **Motion detection**: PIR sensor via gpiod edge detection with software cooldown. Events logged to SQLite.
- **DHT22**: Temperature/humidity sensor, polled at configurable interval (default 60s), retry on failure.
- **MQTT**: Optional, publishes JSON status matching legacy Node-RED format. Configurable broker, topic, location, interval.
- **Data retention**: SQLite cleanup (configurable, default 30 days), runs hourly.

## Config Sections

```yaml
stream:    # resolution, framerate, rotation
ui:        # title
snapshots: # path, retention_days, min_free_disk_percent
system:    # timezone, log_retention_days, log_path
hls:       # segment_duration, playlist_size, path
gpio:      # enabled, sensor_poll_interval, pins, fan thresholds, light_schedule, motion cooldown, data_retention_days
mqtt:      # enabled, broker, port, topic, location, object_name, publish_interval
```

## Development Notes

- No Docker — everything runs directly on the host
- No internet dependency at runtime (all JS vendored)
- Vanilla HTML/CSS/JS only — no build step, no frameworks
- Snapshots are extracted from HLS segments (no rpicam-still interruption)
- The `birdcam` system user runs all services (in `video` and `gpio` groups), with sudoers for service restarts
- All service logging goes to stderr, captured by systemd — no direct FileHandler
- Logging uses centralized `logging_setup.get_logger(source)` — each module gets a distinct source name
- `SOURCE_FILE_MAP` in `logging_setup.py` is the single source of truth for log sources; adding a new source = one line there
- Log sources: `stream`, `web`, `cleanup`, `gpio` (own log files), `snapshot`, `health`, `config` (share `web.log`)
- Stream service uses `KillMode=control-group` + `ExecStartPre` pkill to ensure clean camera release on restart
- rpicam-vid creates kernel threads that can zombie — always kill before restarting, never run rpicam-hello while stream is active
- GPIO service uses `gpiod` (works on Pi 4 and Pi 5, modern libgpiod API)
- SQLite uses WAL mode for concurrent read (web) / write (gpio service)

## Testing

```bash
# On dev machine (requires pytest, flask, pyyaml, psutil, paho-mqtt):
python -m pytest tests/ -v  # 128 unit/integration tests

# Individual test files:
python -m pytest tests/test_logging.py -v   # logging system tests
python -m pytest tests/test_database.py -v  # SQLite database tests
python -m pytest tests/test_gpio.py -v      # GPIO config, logic, API tests

# On Pi:
sudo bash install.sh          # fresh install
sudo bash tests/smoke_test.sh # automated smoke tests
sudo bash update.sh           # deploy changes
```

## Constraints

- Keep CPU usage low (target <15% at 720p/25fps)
- Minimize SD card writes (HLS on tmpfs, SQLite with WAL mode, structured logging)
- Support 3 concurrent browser viewers
- All config changes must survive reboots (persisted to YAML)
- Valid resolutions: `480p`, `720p`, `1080p`; valid framerates: `5`, `15`, `25`, `30`; valid rotations: `0`, `180`; valid camera_models: `auto`, `ov5647_noir`, `imx219_noir`, `imx477_noir`, `imx708_noir`, `imx708_wide_noir`
- GPIO pins: BCM 0-27, no duplicates allowed
- Fan thresholds: on_temp must be > off_temp (hysteresis)
- Light schedule: HH:MM format, complementary (IR and normal light are opposites)
- Config validation lives in `src/config.py` — update `validate()` when adding new settings
- nginx serves `/hls/` and `/snapshots/` directly; only API/UI routes go through Flask
- Shell scripts read YAML config via Python one-liners (no separate config format)
