# Architecture

## Overview

```
┌──────────────────────────────────────────────────────────────────┐
│  Raspberry Pi                                                    │
│                                                                  │
│  Camera 3 NoIR                                                   │
│       │                                                          │
│       ▼                                                          │
│  rpicam-vid (H.264 hardware encoder)                             │
│       │ pipe                                                     │
│       ▼                                                          │
│  ffmpeg (HLS segmenter, -c:v copy)                               │
│       │                                                          │
│       ▼                                                          │
│  /dev/shm/birdcam/  ← tmpfs (no SD card wear)                   │
│    ├── stream.m3u8                                               │
│    ├── seg_001.ts ... seg_005.ts                                 │
│    ├── gpio_status.json   ← written by GPIO service              │
│    └── gpio_commands      ← written by web, read by GPIO service │
│                                                                  │
│  nginx (:80) ────────────────────────────────┐                   │
│    ├── /hls/*        → serves from tmpfs     │                   │
│    ├── /snapshots/*  → serves from disk      │                   │
│    └── /*            → proxy to Flask :8080  │                   │
│                                              │                   │
│  gunicorn + Flask (:8080) ◄──────────────────┘                   │
│    ├── Web UI (HTML/CSS/JS + hls.js + Chart.js)                  │
│    ├── REST API (config, snapshots, GPIO, sensor data)           │
│    └── Snapshot capture (ffmpeg frame extract)                   │
│                                                                  │
│  GPIO service (standalone daemon) ◄── gpiod (libgpiod)          │
│    ├── Output pins: IR light, normal light, fan                  │
│    ├── Input pins: PIR motion sensor (edge detection)            │
│    ├── DHT22 sensor: temperature + humidity                      │
│    ├── Fan auto-control (CPU temp hysteresis)                    │
│    ├── Light schedule (complementary IR/normal)                  │
│    ├── SQLite database (sensor data + motion events)             │
│    └── Optional MQTT publishing                                  │
│                                                                  │
│  SQLite (/var/lib/birdcam/sensor_data.db)                        │
│    ├── sensor_data table (temp, humidity, cpu, status flags)     │
│    └── motion_events table (timestamp, duration)                 │
│                                                                  │
│  systemd                                                         │
│    ├── birdcam-stream.service   (camera pipeline)                │
│    ├── birdcam-web.service      (Flask/gunicorn)                 │
│    ├── birdcam-gpio.service     (GPIO/sensor daemon)             │
│    ├── birdcam-cleanup.timer    (hourly retention)               │
│    └── auto-restart on failure                                   │
└──────────────────────────────────────────────────────────────────┘
         │
         ▼
   LAN browsers (Safari, Chrome)
   play HLS via hls.js / native
```

## Component Details

### Streaming Pipeline (`birdcam-stream.service`)
- `rpicam-vid` captures H.264 using the Pi's hardware encoder (near-zero CPU)
- Output is piped to `ffmpeg` which remuxes into HLS segments (`-c:v copy`, no re-encoding)
- Segments are 2 seconds each, playlist holds 5 segments (10-second window)
- Written to tmpfs (`/dev/shm/birdcam/`) to avoid SD card wear
- Old segments are automatically deleted by ffmpeg
- Service uses `KillMode=control-group` and kills zombie rpicam-vid processes on restart
- Supports 0° and 180° rotation (configured in YAML)

### Web Application (`birdcam-web.service`)
- Flask app served by gunicorn (2 workers, 30-second timeout)
- Bound to localhost:8080 (nginx handles external traffic)
- Serves four pages: Live stream, Sensor Graphs, Health dashboard, Settings
- REST API for configuration, snapshots, GPIO control, sensor data, logs
- Snapshot capture: reads latest complete HLS segment, extracts a JPEG frame via ffmpeg
- Communicates with GPIO service via file-based IPC (see below)

### GPIO and Sensor Service (`birdcam-gpio.service`)
- Standalone Python daemon, decoupled from the web application
- Uses `gpiod` (libgpiod) for GPIO pin control — works on Pi 4, Pi 5, and Zero 2 W
- Controls three output pins: IR light, normal light, fan
- Monitors one input pin: PIR motion sensor (edge detection with pull-down bias, 50ms debounce)
- Reads DHT22 temperature/humidity sensor via `adafruit-circuitpython-dht`
- Fan auto-control: turns on above configurable threshold, off below a lower threshold (hysteresis prevents rapid toggling)
- Light schedule: complementary mode where one time pair switches between IR (night) and normal light (day). Manual overrides via web UI revert at the next scheduled transition
- Motion detection: events logged to SQLite with configurable cooldown between events
- Records sensor data to SQLite at configurable intervals (default 60 seconds)
- Optional MQTT publishing of sensor status to external dashboards
- Hourly cleanup of sensor data older than retention period

### IPC Between Web and GPIO Service
- **Status**: GPIO service writes `/dev/shm/birdcam/gpio_status.json` containing current pin states, sensor readings, and timestamps. Web app reads this file on API requests. Written immediately after command processing and after each sensor poll cycle.
- **Commands**: Web app appends JSON commands to `/dev/shm/birdcam/gpio_commands`. GPIO service reads and deletes this file each loop iteration. Commands include light/IR/fan toggle requests.
- Both files live on tmpfs for speed and to avoid SD card writes.

### Database (SQLite)
- Location: `/var/lib/birdcam/sensor_data.db`
- WAL mode enabled for concurrent read (web) / write (GPIO service)
- Tables:
  - `sensor_data`: timestamp, temperature, humidity, cpu_temp, cpu_load, light/ir_light/fan status flags
  - `motion_events`: timestamp, optional duration
- Indexed on timestamp for efficient time-range queries
- Automatic retention cleanup (configurable, default 30 days)

### Reverse Proxy (nginx)
- Serves HLS segments directly from tmpfs (bypass Python for performance)
- Serves snapshot files directly from disk
- Proxies API/UI requests to Flask
- Rate limits the snapshot endpoint (10 requests/minute per IP, burst of 3)
- Security headers: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`
- CORS headers on HLS responses for cross-origin playback

### Cleanup (`birdcam-cleanup.timer`)
- Runs hourly via systemd timer
- Deletes snapshots older than retention period (default 180 days)
- Deletes oldest snapshots when free disk space drops below threshold
- Deletes log files older than retention period (default 7 days)

### Logging
- Centralized via `logging_setup.py` — each module gets a named logger via `get_logger(source)`
- Structured format: `YYYY-MM-DD HH:MM:SS [LEVEL] [source] message`
- All output goes to stderr, captured by systemd and redirected to log files
- `SOURCE_FILE_MAP` in `logging_setup.py` is the registry mapping sources to log files
- Log sources: `stream`, `web`, `cleanup`, `gpio` get their own log files; `snapshot`, `health`, `config` share `web.log`
- Log viewer in Health page supports filtering by source, level, time period, and verbose mode
- Mtime-based caching prevents redundant file reads

### Configuration
- Single YAML file at `/etc/birdcam/birdcam.yml`
- Read by shell scripts (via Python one-liner) and the Flask app
- Settings page writes changes back to this file
- Validation in `config.py` enforces allowed values, ranges, and constraints
- Stream config changes require a service restart; GPIO/MQTT changes require GPIO service restart
- UI changes take effect on page reload

## Web UI Pages

| Page | URL | Description |
|------|-----|-------------|
| Live | `/` | Video player, snapshot button, light/IR/fan toggles, sensor readings |
| Graphs | `/graphs` | Time-series charts for temperature, humidity, and motion events |
| Health | `/health` | System metrics, service status, log viewer |
| Settings | `/settings` | All configuration options, service restart buttons |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | System health report |
| `/api/snapshot` | POST | Capture snapshot (rate-limited) |
| `/api/snapshots` | GET | List snapshots |
| `/api/config` | GET/PUT | Read/write configuration |
| `/api/logs` | GET | Filterable log entries |
| `/api/restart-stream` | POST | Restart camera pipeline |
| `/api/restart-gpio` | POST | Restart GPIO service |
| `/api/gpio/status` | GET | Current switch states and sensor readings |
| `/api/gpio/light` | POST | Toggle normal light |
| `/api/gpio/ir-light` | POST | Toggle IR light |
| `/api/gpio/fan` | POST | Toggle fan |
| `/api/sensor-data` | GET | Time-series sensor data (query: `?minutes=N`) |
| `/api/motion-events` | GET | Motion event history (query: `?minutes=N`) |

## Design Decisions

**Why rpicam-vid + ffmpeg instead of alternatives:**
- rpicam-vid is the official Raspberry Pi camera tool, guaranteed compatibility with Camera 3
- Hardware H.264 encoding means near-zero CPU
- ffmpeg's HLS muxer is battle-tested and standards-compliant
- Simpler than GStreamer, fewer moving parts than MediaMTX

**Why nginx:**
- HLS viewers request a new .ts segment every 2 seconds
- Serving these through Python/gunicorn wastes CPU on the Pi
- nginx serves them with sendfile() at near-zero cost
- Also provides rate limiting and security headers for free

**Why Flask:**
- Python is pre-installed on Pi OS, minimal dependency footprint
- Simple enough for 3 concurrent API users
- All heavy lifting (video serving) is handled by nginx

**Why tmpfs for HLS:**
- SD cards have limited write cycles
- HLS generates continuous small writes (segments every 2s)
- /dev/shm is RAM-backed, fast and doesn't wear the SD card

**Why a separate GPIO service:**
- Decouples sensor polling from web request handling
- GPIO requires continuous polling (edge detection, scheduled actions) that doesn't fit a request-response model
- Can restart independently without affecting the web UI or stream
- File-based IPC is simple, reliable, and avoids shared-memory complexity

**Why gpiod (libgpiod) instead of RPi.GPIO:**
- Modern Linux GPIO interface, works on Pi 4 and Pi 5
- RPi.GPIO is deprecated and doesn't support Pi 5's RP1 chip
- Provides proper edge detection with debounce at the kernel level

**Why SQLite for sensor data:**
- Zero-config, no separate database server
- WAL mode allows concurrent reads (web) and writes (GPIO service)
- Lightweight enough for a Pi Zero 2 W
- Easy to back up (single file)

**Why file-based IPC instead of sockets/queues:**
- Both services can restart independently without connection management
- Status file is always readable (no "service unavailable" states)
- Command file is append-only, simple, and atomic enough for single-writer use
- tmpfs makes it fast and avoids SD card writes

## Future Extension Points

- **Audio**: Add a USB microphone, change `rpicam-vid` output to include audio track, adjust ffmpeg to mux both streams.
- **Recording**: Add a second ffmpeg output writing continuous MP4 files to disk alongside HLS.
- **Additional sensors**: New sensor types can be added to the GPIO service poll loop and exposed via new API endpoints.
