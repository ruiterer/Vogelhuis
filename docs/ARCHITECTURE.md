# Architecture

## Overview

```
┌──────────────────────────────────────────────────────────┐
│  Raspberry Pi                                            │
│                                                          │
│  Camera 3 NoIR                                           │
│       │                                                  │
│       ▼                                                  │
│  rpicam-vid (H.264 hardware encoder)                     │
│       │ pipe                                             │
│       ▼                                                  │
│  ffmpeg (HLS segmenter, -c:v copy)                       │
│       │                                                  │
│       ▼                                                  │
│  /dev/shm/birdcam/  ← tmpfs (no SD card wear)           │
│    ├── stream.m3u8                                       │
│    ├── seg_001.ts                                        │
│    └── seg_002.ts                                        │
│                                                          │
│  nginx (:80) ─────────────────────────────┐              │
│    ├── /hls/*     → serves from tmpfs     │              │
│    ├── /snapshots → serves from disk      │              │
│    └── /*         → proxy to Flask :8080  │              │
│                                           │              │
│  gunicorn + Flask (:8080) ◄───────────────┘              │
│    ├── Web UI (HTML/CSS/JS)                              │
│    ├── REST API                                          │
│    └── Snapshot capture (ffmpeg frame extract)            │
│                                                          │
│  systemd                                                 │
│    ├── birdcam-stream.service                            │
│    ├── birdcam-web.service                               │
│    ├── birdcam-cleanup.timer (hourly)                    │
│    └── auto-restart on failure                           │
└──────────────────────────────────────────────────────────┘
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

### Web Application (`birdcam-web.service`)
- Flask app served by gunicorn (2 workers)
- Serves the UI pages and REST API
- Bound to localhost:8080 (nginx handles external traffic)
- Snapshot capture: reads latest complete segment from HLS, extracts a JPEG frame

### Reverse Proxy (nginx)
- Serves HLS segments directly from tmpfs (bypass Python for performance)
- Serves snapshot files directly from disk
- Proxies API/UI requests to Flask
- Rate limits the snapshot endpoint (10 requests/minute per IP)
- Security headers applied globally

### Cleanup (`birdcam-cleanup.timer`)
- Runs hourly
- Deletes snapshots older than retention period
- Deletes oldest snapshots when disk space is low
- Deletes log files older than retention period

### Configuration
- Single YAML file at `/etc/birdcam/birdcam.yml`
- Read by both shell scripts (via Python one-liner) and the Flask app
- Settings page writes changes back to this file
- Stream config changes require a service restart (triggered via UI button)

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

## Future Extension Points

- **GPIO sensors**: Add a `modules/` directory with Python files per sensor type. Each module provides a `read()` function and registers API routes via Flask blueprints. UI widgets are added as partials in the templates.
- **Audio**: Add a USB microphone, change `rpicam-vid` output to include audio track, adjust ffmpeg to mux both streams.
- **Recording**: Add a second ffmpeg output writing continuous MP4 files to disk alongside HLS.
