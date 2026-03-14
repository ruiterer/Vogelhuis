# Maintenance Guide

## Routine Operations

### Check system status
```bash
sudo systemctl status birdcam-stream birdcam-web nginx
```
Or visit `http://<pi-ip>/health` in a browser.

### Restart the camera stream
Via web UI: Settings → "Restart Camera Stream"

Via command line:
```bash
sudo systemctl restart birdcam-stream
```

### View logs
```bash
# Stream log
cat /var/log/birdcam/stream.log

# Web app log
cat /var/log/birdcam/web.log

# Cleanup log
cat /var/log/birdcam/cleanup.log

# Follow stream log in real time
tail -f /var/log/birdcam/stream.log
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

### From a local copy
Copy the updated files to the Pi and run:
```bash
sudo bash update.sh
```

## Backup

### What to back up
- `/etc/birdcam/birdcam.yml` — your configuration
- `/var/lib/birdcam/snapshots/` — your saved snapshots

### Backup command
```bash
mkdir -p ~/birdcam-backup
cp /etc/birdcam/birdcam.yml ~/birdcam-backup/
cp -r /var/lib/birdcam/snapshots ~/birdcam-backup/
```

### Restore
```bash
sudo cp ~/birdcam-backup/birdcam.yml /etc/birdcam/
sudo cp ~/birdcam-backup/snapshots/* /var/lib/birdcam/snapshots/
sudo chown -R birdcam:birdcam /var/lib/birdcam/snapshots
sudo systemctl restart birdcam-stream birdcam-web
```

## SD Card Health

The system is designed to minimize SD card writes:
- HLS segments are written to RAM (tmpfs)
- Logs are limited and rotated weekly
- Snapshots are the only regular disk writes (user-triggered)

For extra longevity, consider using a high-endurance SD card (e.g., Samsung PRO Endurance, SanDisk MAX Endurance).

## Monitoring

The health page auto-refreshes every 5 seconds and shows:
- CPU usage (normal: 5-15% with default settings)
- Memory usage (normal: 100-200 MB used)
- CPU temperature (normal: 40-65°C; concerning above 80°C)
- Disk usage
- Uptime
- Camera and service status

### Temperature management
If the Pi is in an enclosed birdhouse:
- Temperature above 70°C: consider better ventilation
- Temperature above 80°C: reduce resolution/framerate
- The Pi throttles at 85°C (performance drops automatically)

## Known Limitations

- **SD card life**: While minimized, long-term snapshot storage and logging do write to SD card
- **Pi Zero 2 W**: Limited to 480p @ 15fps for reliable operation
- **HLS latency**: 4-6 seconds is inherent to the protocol; not reducible without changing to a different streaming method
- **Single camera**: The system supports one camera; multiple cameras would need separate instances
- **No recording**: The system streams live only; continuous recording would require additional storage and pipeline changes
