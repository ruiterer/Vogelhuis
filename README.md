# Birdcam

A Raspberry Pi birdhouse camera system with live HLS streaming and a browser-based UI.

## Features

- Live H.264 video stream via HLS (Safari, Chrome, any modern browser)
- Configurable resolution (480p / 720p / 1080p) and framerate (5-30 fps)
- Manual snapshot capture with JPEG download
- System health monitoring (CPU, memory, temperature, disk)
- Automatic snapshot retention and disk space management
- Self-healing services with automatic restart on failure
- Runs entirely on LAN — no cloud or internet dependency

## Hardware

- Raspberry Pi 4B (also compatible with Pi Zero 2 W, Pi 5)
- Raspberry Pi Camera 3 NoIR
- IR illumination inside the birdhouse

## Quick Start

### 1. Prepare the Pi

Install Raspberry Pi OS Lite (Bookworm) on an SD card using [Raspberry Pi Imager](https://www.raspberrypi.com/software/). Enable SSH and configure Wi-Fi during imaging.

### 2. Install Birdcam

SSH into the Pi, then:

```bash
git clone https://github.com/ruiterer/Vogelhuis.git
cd Vogelhuis
sudo bash install.sh
```

### 3. Open in Browser

Navigate to `http://<pi-ip-address>/` on any device on your LAN.

## Documentation

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

Snapshots are preserved by default during uninstall.

## Project Structure

```
├── install.sh              # Fresh installation
├── update.sh               # Update/redeploy
├── uninstall.sh            # Clean removal
├── birdcam.yml.default     # Default configuration
├── requirements.txt        # Python dependencies
├── src/                    # Application code
│   ├── app.py              # Flask web application
│   ├── config.py           # Configuration management
│   ├── health.py           # System health monitoring
│   ├── snapshot.py         # Snapshot capture
│   ├── stream.sh           # Camera → HLS pipeline
│   ├── cleanup.sh          # Retention cleanup
│   ├── static/             # CSS, JS (hls.js)
│   └── templates/          # HTML pages
├── systemd/                # Service unit files
├── nginx/                  # Reverse proxy config
├── tests/                  # Smoke tests and validation
└── docs/                   # Documentation
```

## License

Private project.
