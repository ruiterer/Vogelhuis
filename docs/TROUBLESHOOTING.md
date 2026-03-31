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
- Camera ribbon cable not seated properly — reseat it, reboot
- Camera not detected — run `rpicam-hello --list-cameras` to verify
- Previous rpicam-vid process still running — `sudo pkill rpicam-vid`, then restart
- libcamera issue — reboot the Pi

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

## Pi 5: "Tuning data file target returned bcm2835, expected pisp"

The Pi 5 uses a different image signal processor (PiSP) than older Pis (vc4/bcm2835). If you see this error, the stream script is loading a tuning file from the wrong directory.

**Cause:** The `camera_model` setting is pointing to a vc4 tuning file instead of the pisp one.

**Fix:** Update to the latest version which auto-detects the ISP:
```bash
cd ~/Vogelhuis
git pull
sudo bash update.sh
```

Verify the correct tuning file is loaded by checking the stream log:
```bash
grep "Using tuning file" /var/log/birdcam/stream.log
# Pi 5 should show: /usr/share/libcamera/ipa/rpi/pisp/...
# Pi 4 should show: /usr/share/libcamera/ipa/rpi/vc4/...
```

## Pi 5: "libav: cannot allocate output context"

On Pi 5, `rpicam-vid` uses the libav backend internally and cannot pipe raw H.264 to stdout. The stream script handles this automatically by using `--libav-format mpegts` on Pi 5.

**Fix:** Update to the latest version:
```bash
cd ~/Vogelhuis
git pull
sudo bash update.sh
```

## Temperature/humidity showing "--"

The DHT22 sensor is either not connected or not responding.

**Check wiring:**
- Data pin connected to the correct GPIO pin (default: BCM 4)
- VCC connected to 3.3V (not 5V)
- GND connected to ground
- 10K pull-up resistor between data and VCC

**Check GPIO service:**
```bash
sudo systemctl status birdcam-gpio
cat /var/log/birdcam/gpio.log
```

**Test sensor manually:**
```bash
sudo /opt/birdcam/venv/bin/python -c "
import board, adafruit_dht
d = adafruit_dht.DHT22(board.D4)
print(d.temperature, d.humidity)
d.exit()
"
```

DHT22 sensors can be unreliable — occasional read failures are normal. The system retries automatically.

## Lights not toggling / reverting

**Symptom:** You toggle a light via the web UI, but it reverts after a few seconds.

**Check that the GPIO service is running:**
```bash
sudo systemctl status birdcam-gpio
```

If the GPIO service is stopped, the status file becomes stale and the web UI reads old state. Restart the service:
```bash
sudo systemctl restart birdcam-gpio
```

**Lights switching at unexpected times:**
The light schedule automatically switches between IR and normal light at the configured times. Manual toggles override the schedule but revert at the next transition. Check the schedule in Settings or in `/etc/birdcam/birdcam.yml` under `gpio.light_schedule`.

## Fan running constantly or not at all

**Fan auto-control** uses CPU temperature with hysteresis:
- Turns on when CPU reaches `fan.on_temp` (default: 50°C)
- Turns off when CPU drops below `fan.off_temp` (default: 40°C)

Check CPU temperature on the Health page or:
```bash
cat /sys/class/thermal/thermal_zone0/temp
# Divide by 1000 for °C
```

If the fan doesn't respond to manual toggle, check wiring and GPIO pin assignment.

## Motion sensor always active or never triggers

**Always showing active (no sensor connected):**
This is expected if no PIR sensor is wired. The GPIO input pin uses a pull-down bias, so it should read inactive when nothing is connected. If it still reads active, check for electrical noise on the pin or try a different GPIO pin.

**Never triggers (sensor connected):**
- Check PIR sensor power (typically 5V VCC, not 3.3V)
- Check PIR output is connected to the correct GPIO pin (default: BCM 7)
- Adjust PIR sensitivity and delay potentiometers on the sensor board
- Check motion cooldown setting — events closer together than the cooldown are ignored

## Sensor graphs empty or not loading

**Check that Chart.js and the date adapter are installed:**
```bash
ls -la /opt/birdcam/src/static/js/chart.min.js
ls -la /opt/birdcam/src/static/js/chartjs-adapter-date-fns.bundle.min.js
```

If missing, run the update script:
```bash
cd /path/to/Vogelhuis
sudo bash update.sh
```

**No data in graphs:**
The GPIO service must be running and the DHT22 sensor connected for temperature/humidity data. CPU temperature is always recorded if the GPIO service is running. Check the selected time range — if data only exists for the last hour, a 30-day view will look empty.

## MQTT not publishing

**Check that MQTT is enabled** in the config with a valid broker address.

**Check GPIO service logs for MQTT errors:**
```bash
grep -i mqtt /var/log/birdcam/gpio.log
```

**Test broker connectivity:**
```bash
/opt/birdcam/venv/bin/python -c "
import paho.mqtt.client as mqtt
c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
c.connect('YOUR_BROKER_IP', 1883, 60)
print('Connected')
c.disconnect()
"
```

## Services won't start after reboot

```bash
# Check what failed
sudo systemctl --failed

# View boot logs
sudo journalctl -b --no-pager | grep birdcam

# Re-enable services
sudo systemctl enable birdcam-stream birdcam-web birdcam-gpio birdcam-cleanup.timer
sudo systemctl start birdcam-stream birdcam-web birdcam-gpio
```

## High CPU usage

- Check health page for CPU percentage
- If above 50%, reduce resolution or framerate
- On Pi 4, the streaming pipeline uses hardware H.264 encoding (~5% CPU)
- On Pi 5, the pipeline currently uses software x264 encoding via the libav backend, which uses more CPU but is manageable on the Pi 5's quad-core processor
- Unexpectedly high CPU usually means ffmpeg is re-encoding (should not happen with `-c:v copy`)

## Disk space running out

The cleanup script runs hourly. To trigger it manually:
```bash
sudo systemctl start birdcam-cleanup
```

Check current disk usage:
```bash
df -h /
```

Snapshots and sensor data are the main disk consumers. Reduce retention days in settings if needed.

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
sudo systemctl restart birdcam-stream birdcam-web birdcam-gpio
```
