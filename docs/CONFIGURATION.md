# Configuration Guide

All settings are in `/etc/birdcam/birdcam.yml`. Changes can be made via the web UI (Settings page) or by editing the file directly.

## Settings Reference

### Stream

| Setting | Options | Default | Notes |
|---------|---------|---------|-------|
| `resolution` | `480p`, `720p`, `1080p` | `720p` | Higher = more bandwidth, more CPU on Pi Zero 2 W |
| `framerate` | `5`, `15`, `25`, `30` | `25` | Lower = less bandwidth, better for Pi Zero 2 W |

Changing stream settings requires restarting the camera service (use the button on the Settings page or `sudo systemctl restart birdcam-stream`).

**Resolution dimensions:**
- 480p: 854x480
- 720p: 1280x720
- 1080p: 1920x1080

**Recommendations by hardware:**

| Pi Model | Recommended | Maximum |
|----------|-------------|---------|
| Pi 4B | 1080p @ 30fps | 1080p @ 30fps |
| Pi 5 | 1080p @ 30fps | 1080p @ 30fps |
| Pi Zero 2 W | 480p @ 15fps | 720p @ 25fps |

### Interface

| Setting | Default | Notes |
|---------|---------|-------|
| `title` | `Birdcam` | Shown in the navigation bar and browser tab |

### Snapshots

| Setting | Default | Notes |
|---------|---------|-------|
| `path` | `/var/lib/birdcam/snapshots` | Directory where JPEG snapshots are saved |
| `retention_days` | `180` | Snapshots older than this are deleted |
| `min_free_disk_percent` | `10` | If free disk drops below this, oldest snapshots are deleted |

### System

| Setting | Default | Notes |
|---------|---------|-------|
| `timezone` | `Europe/Amsterdam` | Used by the OS; set via `timedatectl` during install |
| `log_retention_days` | `7` | Log files older than this are deleted |
| `log_path` | `/var/log/birdcam` | Directory for service logs |

### HLS Tuning

| Setting | Default | Notes |
|---------|---------|-------|
| `segment_duration` | `2` | Seconds per HLS segment. Lower = less latency, more overhead |
| `playlist_size` | `5` | Number of segments in the playlist |
| `path` | `/dev/shm/birdcam` | tmpfs directory for HLS segments |

**Latency:** With default settings (2s segments, playlist size 5), expect 4-6 seconds of latency. Reducing `segment_duration` to 1 and `playlist_size` to 3 can reduce latency to 2-4 seconds but may cause buffering on slow networks.

## Applying Changes

- **UI settings** (title): take effect on page reload, no restart needed
- **Stream settings** (resolution, framerate): require a camera service restart
- **Snapshot/system settings**: take effect immediately (cleanup runs hourly)
- **HLS tuning**: requires camera service restart

## Editing Config Manually

```bash
sudo nano /etc/birdcam/birdcam.yml
sudo systemctl restart birdcam-stream  # if stream settings changed
```
