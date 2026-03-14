# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Raspberry Pi birdhouse camera system — LAN-only, browser-based live HLS stream with web UI. Runs on Raspberry Pi OS Lite (Bookworm) with a Pi Camera 3 NoIR.

- **Repository**: https://github.com/ruiterer/Vogelhuis
- **Branch**: `main`

## Stack

- **Streaming**: rpicam-vid (hardware H.264) → ffmpeg (HLS segmenter, `-c:v copy`) → tmpfs
- **Web**: Flask + gunicorn on localhost:8080, behind nginx on port 80
- **Frontend**: Vanilla HTML/CSS/JS + hls.js (vendored)
- **Config**: Single YAML file at `/etc/birdcam/birdcam.yml`
- **Services**: systemd units for stream, web, cleanup timer
- **Target hardware**: Pi 4B primary, Pi Zero 2 W and Pi 5 compatible

## Key Paths (on Pi)

- App code: `/opt/birdcam/src/`
- Config: `/etc/birdcam/birdcam.yml`
- HLS segments: `/dev/shm/birdcam/` (tmpfs)
- Snapshots: `/var/lib/birdcam/snapshots/`
- Logs: `/var/log/birdcam/`
- Python venv: `/opt/birdcam/venv/`

## Development Notes

- No Docker — everything runs directly on the host
- No internet dependency at runtime
- No timestamp overlay in video — clock is shown on the web page via JS
- Snapshots are extracted from HLS segments (no rpicam-still interruption)
- The `birdcam` system user runs all services, with sudoers for stream restart
- GPIO integration is planned for future (sensors, IR control) — keep architecture modular

## Testing on Pi

```bash
sudo bash install.sh          # fresh install
sudo bash tests/smoke_test.sh # automated smoke tests
sudo bash update.sh           # deploy changes
```

## Constraints

- Keep CPU usage low (target <15% at 720p/25fps)
- Minimize SD card writes (HLS on tmpfs, limited logging)
- Support 3 concurrent browser viewers
- All config changes must survive reboots (persisted to YAML)
- Valid resolutions: `480p`, `720p`, `1080p`; valid framerates: `5`, `15`, `25`, `30`
- Config validation lives in `src/config.py` — update `validate()` when adding new settings
- nginx serves `/hls/` and `/snapshots/` directly; only API/UI routes go through Flask
- Shell scripts read YAML config via Python one-liners (no separate config format)
