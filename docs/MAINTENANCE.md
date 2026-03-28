# Maintenance Guide

## Routine Operations

### Check system status
```bash
sudo systemctl status birdcam-stream birdcam-web birdcam-gpio nginx
```
Or visit `http://<pi-ip>/health` in a browser.

### Restart the camera stream
Via web UI: Settings page, click "Restart Camera Stream"

Via command line:
```bash
sudo systemctl restart birdcam-stream
```

### Restart the GPIO service
Via web UI: Settings page, click "Restart GPIO Service"

Via command line:
```bash
sudo systemctl restart birdcam-gpio
```

### View logs
Via web UI: Health page has a built-in log viewer with source/level filtering.

Via command line:
```bash
# Stream log
cat /var/log/birdcam/stream.log

# Web app log
cat /var/log/birdcam/web.log

# GPIO/sensor log
cat /var/log/birdcam/gpio.log

# Cleanup log
cat /var/log/birdcam/cleanup.log

# Follow a log in real time
tail -f /var/log/birdcam/gpio.log
```

### Run cleanup manually
```bash
sudo systemctl start birdcam-cleanup
```

## Updating Birdcam

### From git repository
On the Pi:
```bash
cd /path/to/Vogelhuis
git pull
sudo bash update.sh
```

The update script preserves your configuration at `/etc/birdcam/birdcam.yml`. If new configuration options were added, review `birdcam.yml.default` for the new settings.

### From a local copy
Copy the updated files to the Pi and run:
```bash
sudo bash update.sh
```

## Backup

### What to back up
- `/etc/birdcam/birdcam.yml` — your configuration
- `/var/lib/birdcam/snapshots/` — your saved snapshots
- `/var/lib/birdcam/sensor_data.db` — sensor readings and motion event history

### Backup command
```bash
mkdir -p ~/birdcam-backup
cp /etc/birdcam/birdcam.yml ~/birdcam-backup/
cp /var/lib/birdcam/sensor_data.db ~/birdcam-backup/
cp -r /var/lib/birdcam/snapshots ~/birdcam-backup/
```

### Restore
```bash
sudo cp ~/birdcam-backup/birdcam.yml /etc/birdcam/
sudo cp ~/birdcam-backup/sensor_data.db /var/lib/birdcam/
sudo cp ~/birdcam-backup/snapshots/* /var/lib/birdcam/snapshots/
sudo chown -R birdcam:birdcam /var/lib/birdcam
sudo systemctl restart birdcam-stream birdcam-web birdcam-gpio
```

## SD Card Health

The system is designed to minimize SD card writes:
- HLS segments are written to RAM (tmpfs)
- GPIO status and command files are on tmpfs
- Logs are limited and rotated weekly
- Snapshots are the only regular user-triggered disk writes
- SQLite sensor data uses WAL mode (batched writes) at configurable intervals

For extra longevity, consider using a high-endurance SD card (e.g., Samsung PRO Endurance, SanDisk MAX Endurance).

## Monitoring

### Health page
The Health page (`/health`) auto-refreshes every 5 seconds and shows:
- CPU usage (normal: 5-15% with default settings)
- Memory usage (normal: 100-200 MB used)
- CPU temperature (normal: 40-65°C; concerning above 80°C)
- Disk usage
- System uptime
- Camera status
- Service status for all four services (stream, web, GPIO, nginx)
- Log viewer with filtering by source, level, and time period

### Sensor graphs
The Graphs page (`/graphs`) shows time-series data:
- Temperature: birdhouse (DHT22) and CPU temperature on the same chart
- Humidity: from the DHT22 sensor
- Motion Activity: bar chart of PIR motion events

All graphs use a consistent time axis matching the selected period (1h, 6h, 12h, 24h, 7d, 30d). Data refreshes every 60 seconds.

### Live page sensors
The Live page shows current sensor readings below the stream controls:
- Temperature, humidity, CPU temperature, and motion status
- Light, IR light, and fan toggle buttons with real-time state
- Readings update every 5 seconds

### Temperature management
If the Pi is in an enclosed birdhouse:
- Temperature above 70°C: consider better ventilation or enabling the fan
- Temperature above 80°C: reduce resolution/framerate
- The Pi throttles at 85°C (performance drops automatically)
- The automatic fan control (default: on at 50°C, off at 40°C) helps manage temperature

## Data Retention

| Data | Default retention | Configured in |
|------|-------------------|---------------|
| Snapshots | 180 days | `snapshots.retention_days` |
| Sensor data | 30 days | `gpio.data_retention_days` |
| Motion events | 30 days | `gpio.data_retention_days` |
| Log files | 7 days | `system.log_retention_days` |

Snapshot cleanup runs hourly via systemd timer. Sensor data cleanup runs hourly within the GPIO service.

## Known Limitations

- **SD card life**: While minimized, long-term snapshot storage and logging do write to SD card
- **Pi Zero 2 W**: Limited to 480p @ 15fps for reliable operation
- **HLS latency**: 4-6 seconds is inherent to the protocol; not reducible without changing to a different streaming method
- **Single camera**: The system supports one camera; multiple cameras would need separate instances
- **No recording**: The system streams live only; continuous recording would require additional storage and pipeline changes
- **DHT22 reliability**: The sensor occasionally returns read errors; the system retries automatically
- **Light schedule**: Only one transition pair (day/night); more complex schedules would require code changes
