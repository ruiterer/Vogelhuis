# Birdcam

A Raspberry Pi birdhouse camera system with live HLS streaming, GPIO sensor monitoring, and a browser-based UI.

## Features

- Live H.264 video stream via HLS (Safari, Chrome, any modern browser)
- Configurable resolution (480p / 720p / 1080p, square format) and framerate (5-30 fps)
- Manual snapshot capture with thumbnail preview and JPEG download
- GPIO control: IR light, normal light, and fan with web UI toggles
- Complementary light schedule (automatic IR/normal light switching)
- Temperature and humidity monitoring (DHT22 sensor)
- Motion detection (PIR sensor) with event history
- Sensor graphs with configurable time ranges (1h to 30d)
- CPU temperature-based fan auto-control with hysteresis
- System health monitoring (CPU, memory, temperature, disk, service status)
- Log viewer with source/level filtering and download
- Optional MQTT publishing for external dashboards
- Automatic snapshot retention and disk space management
- Sensor data stored in SQLite with configurable retention
- Self-healing services with automatic restart on failure
- Runs entirely on LAN — no cloud or internet dependency

## Hardware

- Raspberry Pi 4B (also compatible with Pi Zero 2 W, Pi 5)
- Raspberry Pi Camera 3 NoIR
- DHT22 temperature/humidity sensor
- PIR motion sensor
- IR LED illumination
- Normal LED light
- 5V fan for ventilation
- See [Manual](docs/MANUAL.md) for wiring details

## Quick Start

### 1. Prepare the Pi

Install Raspberry Pi OS Lite (Bookworm) on an SD card using [Raspberry Pi Imager](https://www.raspberrypi.com/software/). During imaging:

- Enable SSH
- Configure Wi-Fi (if not using Ethernet)
- Set hostname (e.g., `birdcam`)

### 2. Install Prerequisites

SSH into the Pi, then install `git` and `curl` (not included in Pi OS Lite by default):

```bash
sudo apt update && sudo apt install -y git curl
```

### 3. Install Birdcam

```bash
git clone https://github.com/ruiterer/Vogelhuis.git
cd Vogelhuis
sudo bash install.sh
```

The install script handles all remaining dependencies (ffmpeg, nginx, Python venv, rpicam-apps, hls.js, Chart.js, GPIO libraries).

### 4. Open in Browser

Navigate to `http://<pi-ip-address>/` on any device on your LAN.

## Documentation

- [Manual](docs/MANUAL.md) — how to use the system (start here)
- [Architecture](docs/ARCHITECTURE.md) — system design and component overview
- [Configuration](docs/CONFIGURATION.md) — all settings explained
- [Troubleshooting](docs/TROUBLESHOOTING.md) — common issues and fixes
- [Maintenance](docs/MAINTENANCE.md) — day-to-day operations, updates, backups

## Updating

```bash
cd Vogelhuis
git pull
sudo bash update.sh
```

## Uninstalling

```bash
sudo bash uninstall.sh
```

Snapshots and sensor data are preserved by default during uninstall.

## Project Structure

```
├── install.sh              # Fresh installation
├── update.sh               # Update/redeploy
├── uninstall.sh            # Clean removal
├── birdcam.yml.default     # Default configuration
├── requirements.txt        # Python dependencies
├── src/                    # Application code
│   ├── app.py              # Flask web application and API
│   ├── config.py           # Configuration management
│   ├── database.py         # SQLite sensor data storage
│   ├── gpio_service.py     # GPIO/sensor daemon
│   ├── health.py           # System health monitoring
│   ├── logging_setup.py    # Centralized logging
│   ├── logs.py             # Log file parsing
│   ├── snapshot.py         # Snapshot capture
│   ├── stream.sh           # Camera → HLS pipeline
│   ├── cleanup.sh          # Retention cleanup
│   ├── static/             # CSS, JS (hls.js, Chart.js)
│   └── templates/          # HTML pages
├── systemd/                # Service unit files
├── nginx/                  # Reverse proxy config
├── tests/                  # Unit tests and smoke tests
└── docs/                   # Documentation
```

## License

Private project.
