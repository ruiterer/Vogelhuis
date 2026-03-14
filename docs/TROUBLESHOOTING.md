# Troubleshooting

## Stream not working / "Offline" shown

**Check if the stream service is running:**
```bash
sudo systemctl status birdcam-stream
```

**Check stream logs:**
```bash
cat /var/log/birdcam/stream.log
```

**Common causes:**
- Camera ribbon cable not seated properly → reseat it, reboot
- Camera not detected → run `rpicam-hello --list-cameras` to verify
- libcamera issue → reboot the Pi
- ffmpeg error → check logs for specific error message

**Fix:**
```bash
sudo systemctl restart birdcam-stream
```

If it keeps failing (5 restarts in 5 minutes hits the rate limit):
```bash
sudo systemctl reset-failed birdcam-stream
sudo systemctl start birdcam-stream
```

## Web UI not loading

**Check nginx:**
```bash
sudo systemctl status nginx
sudo nginx -t
```

**Check web service:**
```bash
sudo systemctl status birdcam-web
cat /var/log/birdcam/web.log
```

**Check if port 80 is in use by something else:**
```bash
sudo ss -tlnp | grep :80
```

## Stream plays but keeps buffering

- Reduce resolution (try 480p)
- Reduce framerate (try 15fps)
- Check CPU load on the health page — if above 80%, reduce settings
- Check network: run `ping <pi-ip>` from a viewer device, look for packet loss

## Snapshots not working

**"No HLS segment available":**
The camera stream must be running to take snapshots. Check stream status.

**Permission error:**
```bash
ls -la /var/lib/birdcam/snapshots/
# Should be owned by birdcam:birdcam
sudo chown -R birdcam:birdcam /var/lib/birdcam/snapshots
```

**ffmpeg error:**
```bash
# Test manually
ffmpeg -i /dev/shm/birdcam/seg_001.ts -frames:v 1 -q:v 2 /tmp/test.jpg
```

## Camera not detected

```bash
# List cameras
rpicam-hello --list-cameras

# Check if camera interface is enabled
sudo raspi-config nonint get_camera
# 0 = enabled, 1 = disabled

# Enable camera if disabled
sudo raspi-config nonint do_camera 0
sudo reboot
```

**Check ribbon cable:** The cable should be inserted with the blue side facing the Ethernet port on Pi 4B.

## Services won't start after reboot

```bash
# Check what failed
sudo systemctl --failed

# View boot logs
sudo journalctl -b --no-pager | grep birdcam

# Re-enable services
sudo systemctl enable birdcam-stream birdcam-web birdcam-cleanup.timer
sudo systemctl start birdcam-stream birdcam-web
```

## High CPU usage

- Check health page for CPU percentage
- If above 50%, reduce resolution or framerate
- The streaming pipeline with `-c:v copy` should use ~5% CPU
- High CPU usually means ffmpeg is re-encoding (should not happen with this config)

## Disk space running out

The cleanup script runs hourly. To trigger it manually:
```bash
sudo systemctl start birdcam-cleanup
```

Check current disk usage:
```bash
df -h /
```

## Logs filling up

Logs are rotated by the cleanup script (max 7 days by default). To clear manually:
```bash
sudo truncate -s 0 /var/log/birdcam/*.log
```

## Hostname (.local) not resolving

Ensure avahi-daemon is running:
```bash
sudo systemctl status avahi-daemon
sudo systemctl enable --now avahi-daemon
```

The Pi should be reachable at `<hostname>.local`. Check hostname:
```bash
hostname
```

## Resetting to defaults

```bash
sudo cp /path/to/repo/birdcam.yml.default /etc/birdcam/birdcam.yml
sudo systemctl restart birdcam-stream birdcam-web
```
