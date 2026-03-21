# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Raspberry Pi birdhouse camera system — LAN-only, browser-based live HLS stream with web UI. Runs on Raspberry Pi OS Lite (Bookworm) with a Pi Camera 3 NoIR.

- **Repository**: https://github.com/ruiterer/Vogelhuis
- **Branch**: `main`

## Stack

- **Streaming**: rpicam-vid (hardware H.264) → ffmpeg (HLS segmenter, `-c:v copy`) → tmpfs
- **Web**: Flask + gunicorn (2 workers) on localhost:8080, behind nginx on port 80
- **Frontend**: Vanilla HTML/CSS/JS + hls.js (vendored, v1.5.13)
- **Config**: Single YAML file at `/etc/birdcam/birdcam.yml`
- **Logging**: Centralized via `logging_setup.py` — structured format (`YYYY-MM-DD HH:MM:SS [LEVEL] [source]`), stderr → systemd → log files, mtime-cached reader
- **Services**: systemd units for stream, web, cleanup timer
- **Target hardware**: Pi 4B primary, Pi Zero 2 W and Pi 5 compatible

## Key Paths (on Pi)

- App code: `/opt/birdcam/src/`
- Config: `/etc/birdcam/birdcam.yml`
- HLS segments: `/dev/shm/birdcam/` (tmpfs)
- Snapshots: `/var/lib/birdcam/snapshots/`
- Logs: `/var/log/birdcam/`
- Python venv: `/opt/birdcam/venv/`

## Source Modules

| Module | Purpose |
|--------|---------|
| `app.py` | Flask web app, API endpoints, config persistence |
| `config.py` | Config loading, defaults, validation, resolution mapping |
| `health.py` | System metrics, service status, camera health checks |
| `logging_setup.py` | Centralized logger factory (`get_logger(source)`) and `SOURCE_FILE_MAP` registry |
| `logs.py` | Log file parsing with mtime caching, filtering, verbose/unstructured support |
| `snapshot.py` | Snapshot capture from HLS segments via ffmpeg |
| `stream.sh` | rpicam-vid → ffmpeg HLS pipeline |
| `cleanup.sh` | Hourly snapshot/log retention (age-based + disk space threshold) |

## Web UI & API

**Pages**: Live stream (`/`), Settings (`/settings`), Health dashboard (`/health` — includes log viewer with source/level/time filters, auto-refresh, download)

**API endpoints**: `/api/health`, `/api/snapshot` (POST, rate-limited), `/api/snapshots`, `/api/config` (GET/PUT), `/api/logs` (GET, filterable by source/level/minutes/verbose), `/api/restart-stream` (POST)

## Development Notes

- No Docker — everything runs directly on the host
- No internet dependency at runtime
- No timestamp overlay in video — clock is shown on the web page via JS
- Snapshots are extracted from HLS segments (no rpicam-still interruption)
- The `birdcam` system user runs all services, with sudoers for stream restart
- All service logging goes to stderr, captured by systemd journal — no direct FileHandler (avoids permission issues)
- Logging uses centralized `logging_setup.get_logger(source)` — each module gets a distinct source name
- `SOURCE_FILE_MAP` in `logging_setup.py` is the single source of truth for log sources; adding a new source (e.g. sensor) = one line there
- Log sources: `stream`, `web`, `cleanup` (own log files), `snapshot`, `health`, `config` (share `web.log`)
- Unstructured lines (ffmpeg, rpicam-vid output) are hidden by default; shown via "Verbose" toggle with parse-time timestamps
- Log reader uses mtime-based caching to avoid re-reading unchanged files on each 5s poll
- Stream service has no WatchdogSec (bash pipelines can't send sd_notify pings)
- Stream service uses `KillMode=control-group` + `ExecStartPre` pkill to ensure clean camera release on restart
- rpicam-vid creates kernel threads that can zombie — always kill before restarting, never run rpicam-hello while stream is active
- GPIO integration is planned for future (sensors, IR control) — keep architecture modular

## Testing

```bash
# On dev machine (requires pytest, flask, pyyaml, psutil):
python -m pytest tests/test_logging.py -v  # 44 unit/integration tests

# On Pi:
sudo bash install.sh          # fresh install
sudo bash tests/smoke_test.sh # automated smoke tests (includes logging checks)
sudo bash update.sh           # deploy changes
```

## Constraints

- Keep CPU usage low (target <15% at 720p/25fps)
- Minimize SD card writes (HLS on tmpfs, structured logging with configurable retention)
- Support 3 concurrent browser viewers
- All config changes must survive reboots (persisted to YAML)
- Valid resolutions: `480p`, `720p`, `1080p`; valid framerates: `5`, `15`, `25`, `30`; valid rotations: `0`, `180`
- Config validation lives in `src/config.py` — update `validate()` when adding new settings
- nginx serves `/hls/` and `/snapshots/` directly; only API/UI routes go through Flask
- Shell scripts read YAML config via Python one-liners (no separate config format)
