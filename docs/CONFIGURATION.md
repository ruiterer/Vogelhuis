# Configuration Guide

All settings are in `/etc/birdcam/birdcam.yml`. Changes can be made via the web UI (Settings page) or by editing the file directly.

## Settings Reference

### Stream

| Setting | Options | Default | Notes |
|---------|---------|---------|-------|
| `resolution` | `480p`, `720p`, `1080p` | `720p` | Higher = more bandwidth, more CPU on Pi Zero 2 W |
| `framerate` | `5`, `15`, `25`, `30` | `25` | Lower = less bandwidth, better for Pi Zero 2 W |
| `rotation` | `0`, `180` | `0` | Rotate the image if the camera is mounted upside down |
| `camera_model` | `auto`, `ov5647_noir`, `imx219_noir`, `imx477_noir`, `imx708_noir`, `imx708_wide_noir` | `auto` | Select your NoIR camera to fix pink tint under IR |

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

Snapshot filenames use the format `YYYYMMDD_HHMMSS.jpg`.

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

### GPIO

| Setting | Default | Notes |
|---------|---------|-------|
| `enabled` | `true` | Enable or disable the entire GPIO/sensor subsystem |
| `sensor_poll_interval` | `60` | Seconds between sensor readings (10-300) |

**Pin assignments** (BCM numbering, 0-27, no duplicates allowed):

| Pin | Default | Function |
|-----|---------|----------|
| `pins.ir_light` | `13` | IR LED illumination (output) |
| `pins.light` | `19` | Normal LED light (output) |
| `pins.fan` | `22` | Ventilation fan (output) |
| `pins.dht22` | `4` | DHT22 temperature/humidity sensor (data pin) |
| `pins.motion` | `7` | PIR motion sensor (input) |

**Fan auto-control:**

| Setting | Default | Notes |
|---------|---------|-------|
| `fan.on_temp` | `50` | Fan turns on when CPU reaches this temperature (°C) |
| `fan.off_temp` | `40` | Fan turns off when CPU drops below this temperature (°C) |

`on_temp` must be greater than `off_temp` (hysteresis prevents rapid on/off toggling). Valid range: 30-85°C.

**Light schedule** (complementary mode):

| Setting | Default | Notes |
|---------|---------|-------|
| `light_schedule.night_start` | `21:15` | IR light turns on, normal light turns off |
| `light_schedule.day_start` | `06:30` | Normal light turns on, IR light turns off |

Times are in `HH:MM` format (24-hour). The schedule runs automatically. Manual toggles via the web UI override the schedule until the next transition.

**Motion detection:**

| Setting | Default | Notes |
|---------|---------|-------|
| `motion.cooldown` | `30` | Minimum seconds between logged motion events (1-3600) |

**Data retention:**

| Setting | Default | Notes |
|---------|---------|-------|
| `data_retention_days` | `30` | Sensor data and motion events older than this are deleted (1-365) |

### MQTT

Optional MQTT publishing for integration with external dashboards (e.g., Node-RED, Home Assistant).

| Setting | Default | Notes |
|---------|---------|-------|
| `enabled` | `false` | Enable MQTT publishing |
| `broker` | `""` | MQTT broker hostname or IP address (required when enabled) |
| `port` | `1883` | MQTT broker port (1-65535) |
| `topic` | `birdcam/status` | Topic to publish to |
| `location` | `Tuin` | Location field in the MQTT payload |
| `object_name` | `Vogelhuis_Boom` | Object name field in the MQTT payload |
| `publish_interval` | `60` | Seconds between MQTT publishes (10-3600) |

**MQTT payload format** (JSON):
```json
{
  "location": "Tuin",
  "object": "Vogelhuis_Boom",
  "temperature": 22.5,
  "humidity": 65.0,
  "light_status": true,
  "ir_light_status": false,
  "ventilation_status": false,
  "movement_status": false,
  "cpu_temp": 48.3,
  "cpu_load": 12.5
}
```

## Applying Changes

- **UI settings** (title): take effect on page reload, no restart needed
- **Stream settings** (resolution, framerate, rotation): require a camera service restart
- **GPIO/MQTT settings**: require a GPIO service restart
- **Snapshot/system settings**: take effect immediately (cleanup runs hourly)
- **HLS tuning**: requires camera service restart

Service restarts can be triggered from the Settings page or via command line.

## Editing Config Manually

```bash
sudo nano /etc/birdcam/birdcam.yml
sudo systemctl restart birdcam-stream  # if stream settings changed
sudo systemctl restart birdcam-gpio    # if GPIO/MQTT settings changed
```

## Full Default Configuration

See `birdcam.yml.default` in the repository for a complete annotated example.
