# Birdcam User Manual

Welcome to your birdhouse camera system! This manual explains how to use and enjoy your birdcam.

## Table of Contents

1. [Getting Started](#getting-started)
2. [Watching the Live Stream](#watching-the-live-stream)
3. [Taking Snapshots](#taking-snapshots)
4. [Controlling Lights and Fan](#controlling-lights-and-fan)
5. [Sensor Readings](#sensor-readings)
6. [Sensor Graphs](#sensor-graphs)
7. [System Health](#system-health)
8. [Settings](#settings)
9. [Hardware Setup](#hardware-setup)
10. [Advanced Section](#advanced-section)

---

## Getting Started

Your birdcam is a small computer (Raspberry Pi) inside or near the birdhouse, with a camera, lights, sensors, and a fan. It streams live video to your home network and lets you monitor conditions inside the birdhouse from any phone, tablet, or computer.

### How to access

1. Make sure your phone/tablet/computer is connected to the same home Wi-Fi network as the birdcam
2. Open a web browser (Safari, Chrome, Firefox, or Edge)
3. Type the birdcam address in the address bar: `http://<pi-ip-address>/`
4. The live stream page will load

The address is a number like `http://192.168.1.56/` — it was shown at the end of installation. If you don't know the address, check your router's device list for a device called "Vogelhuis" or similar.

You may also be able to reach it using `http://vogelhuis.local/` (the hostname followed by `.local`).

### Navigation

The top of every page has a navigation bar with four tabs:

| Tab | What it shows |
|-----|---------------|
| **Live** | Live video stream, snapshot button, light/fan controls, current sensor readings |
| **Graphs** | Temperature, humidity, and motion charts over time |
| **Health** | System information, service status, and logs |
| **Settings** | All configuration options |

---

## Watching the Live Stream

The **Live** page is the main page. It shows:

- A live video feed from the camera inside the birdhouse
- A status indicator in the top-right corner of the video:
  - **Live** (green) — the camera is streaming
  - **Offline** (red) — the camera is not available; it will reconnect automatically when it comes back

The video has a delay of about 4-6 seconds compared to real time. This is normal for this type of streaming.

### Fullscreen

Click the **Fullscreen** button below the video to fill your screen with the camera view. Press Escape or the back button to exit fullscreen.

---

## Taking Snapshots

Below the live video, click the **Snapshot** button to capture a photo from the current stream.

- A green notification will confirm the snapshot was saved
- The photo appears as a thumbnail in the **Recent Snapshots** section below
- Click any thumbnail to download the full-resolution JPEG image
- You can take one snapshot every 3 seconds
- Up to 12 recent snapshots are shown on the page

Snapshots are stored on the Pi and automatically cleaned up after 180 days (configurable in Settings).

---

## Controlling Lights and Fan

Three toggle buttons are shown below the video:

| Button | What it controls |
|--------|-----------------|
| **Light** | The normal (visible) LED light inside the birdhouse |
| **IR Light** | The infrared LED light (invisible to birds, used for night vision) |
| **Fan** | The ventilation fan |

- A button turns **green** when the device is on
- Click a button to toggle it on or off
- **Light and IR Light are complementary**: turning on the light automatically turns off the IR light, and vice versa. This prevents both being on at the same time.

### Automatic behaviour

**Lights** follow a daily schedule:
- At night (default: after 21:15), the IR light turns on and the normal light turns off. This lets the camera see in the dark without disturbing the birds.
- During the day (default: after 06:30), the normal light turns on and the IR light turns off.
- If you manually toggle a light, your choice stays active until the next scheduled switch.

**Fan** runs automatically based on CPU temperature:
- Turns on when the temperature reaches the on-threshold (default: 50°C)
- Turns off when it cools below the off-threshold (default: 40°C)
- If you manually toggle the fan, your choice stays active for one check cycle (about 60 seconds), then automatic control resumes.

---

## Sensor Readings

Below the light and fan controls on the Live page, you can see current readings:

| Reading | What it means |
|---------|---------------|
| **Temp** | Air temperature inside the birdhouse (from the DHT22 sensor) |
| **Humidity** | Relative humidity inside the birdhouse |
| **CPU** | Temperature of the Raspberry Pi processor |
| **Motion** | Shows "Active" (in orange) when movement is detected by the PIR sensor |

Readings showing "--" mean the sensor is not connected or not responding. The readings update every 5 seconds.

---

## Sensor Graphs

The **Graphs** page shows historical data in three charts:

### Temperature
Shows two lines on the same chart:
- **Birdhouse**: air temperature from the DHT22 sensor (if connected)
- **CPU**: processor temperature of the Raspberry Pi

### Humidity
Shows the relative humidity inside the birdhouse over time.

### Motion Activity
Shows a bar for each time the PIR motion sensor was triggered. Useful for seeing when birds visit the house.

### Selecting a time range

At the top of the page, buttons let you choose how far back to look:

| Button | Period shown |
|--------|-------------|
| 1h | Last hour |
| 6h | Last 6 hours |
| 12h | Last 12 hours |
| 24h | Last 24 hours (default) |
| 7d | Last 7 days |
| 30d | Last 30 days |

All three charts always show the same time range. The graphs update automatically every minute.

---

## System Health

The **Health** page shows technical information about the system:

### Status cards
- **CPU**: processor usage percentage (normal: 5-15%)
- **Memory**: RAM usage (normal: under 200 MB)
- **Temperature**: CPU temperature (normal: 40-65°C; above 80°C is concerning)
- **Disk**: SD card usage and free space
- **Uptime**: how long the system has been running since last reboot
- **Camera**: whether the camera is online

### Services
Shows whether each system component is running:
- **birdcam-stream**: the camera and video pipeline
- **birdcam-web**: the web interface you are using
- **birdcam-gpio**: the sensor and light/fan control service
- **nginx**: the web server

Green "active" means running normally. Red "inactive" means the service has stopped.

### Log viewer
At the bottom of the Health page, a log viewer shows system messages. This is mainly useful for troubleshooting. You can filter by source (which service), severity level, and time period.

---

## Settings

The **Settings** page lets you change how the system works. After changing settings, click **Save** at the top.

### Stream settings
- **Resolution**: video quality (480p, 720p, or 1080p). Square format, cropped from the center of the sensor. Higher is sharper but uses more resources.
- **Framerate**: how many frames per second (5, 15, 25, or 30). 25 is smooth; 15 is fine for a birdhouse.
- **Rotate 180°**: flip the image if the camera is mounted upside down.

After changing stream settings, click the **Restart Camera Stream** button to apply them. The video will briefly go offline while it restarts.

### Interface settings
- **Page title**: the name shown in the navigation bar and browser tab.

### Snapshot settings
- **Retention days**: how long to keep snapshots before automatically deleting them.

### GPIO settings
- **Enabled**: turn the sensor/light/fan system on or off entirely.
- **Pin assignments**: which GPIO pins the sensors and devices are connected to. Only change these if your wiring differs from the default.
- **Fan thresholds**: the temperatures at which the fan turns on and off.
- **Light schedule**: when to switch between normal and IR light.
- **Motion cooldown**: minimum time between recorded motion events (prevents flooding).
- **Data retention**: how many days of sensor history to keep.

After changing GPIO settings, click the **Restart GPIO Service** button.

### MQTT settings
For advanced users who want to send sensor data to external systems like Home Assistant or Node-RED. Leave disabled if you don't use these tools.

---

## Hardware Setup

This section describes the physical components and how they are connected.

### Components

| Component | Model | Purpose |
|-----------|-------|---------|
| Computer | Raspberry Pi 4B | Runs the software, captures and streams video |
| Camera | Raspberry Pi Camera 3 NoIR | Night-vision camera (no IR filter, sensitive to IR light) |
| Temperature/humidity sensor | DHT22 (AM2302) | Measures conditions inside the birdhouse |
| Motion sensor | HC-SR501 PIR | Detects movement (birds entering/leaving) |
| IR LEDs | IR illumination board/strip | Provides invisible light for night-vision recording |
| Normal LEDs | White LED board/strip | Provides visible light during the day |
| Fan | 5V DC fan | Ventilation to keep the Pi cool in an enclosed space |
| Power supply | 5V 3A USB-C | Powers the Raspberry Pi |
| SD card | 32GB+ (high-endurance recommended) | Stores the operating system and data |

### Camera connection

The camera connects to the Pi via a flat ribbon cable:

1. Locate the camera connector on the Pi (between the Ethernet port and the HDMI ports on Pi 4B)
2. Gently lift the black plastic clip on the connector
3. Insert the ribbon cable with the blue side facing the Ethernet port
4. Press the clip back down to lock the cable
5. Mount the camera facing into the birdhouse

If the camera is mounted upside down, enable the 180° rotation in Settings.

### GPIO wiring

All sensors and devices connect to the Pi's 40-pin GPIO header. The default pin assignments use BCM (Broadcom) numbering:

```
                    Raspberry Pi GPIO Header
                    (pin 1 is top-left)

                3V3  [1]  [2]  5V
        DHT22 data → [3]  [4]  5V ← PIR VCC, IR/Light/Fan power
                     [5]  [6]  GND ← shared ground
     Motion (BCM 4)  [7]  [8]
                GND  [9]  [10]
                     [11] [12]
                     [13] [14] GND
                     [15] [16]
                3V3  [17] [18]
                     [19] [20] GND
                     [21] [22]
                     [23] [24]
                GND  [25] [26]
  IR Light (BCM 13) → [33] [34] GND
   Light (BCM 19) →   [35] [36]
                       [37] [38]
                  GND  [39] [40]
     Fan (BCM 22) →    [15] ← physical pin
```

**Default BCM pin assignments:**

| Device | BCM Pin | Physical Pin | Direction |
|--------|---------|-------------|-----------|
| DHT22 (data) | 4 | 7 | Input |
| Motion (PIR) | 7 | 26 | Input |
| IR Light | 13 | 33 | Output |
| Normal Light | 19 | 35 | Output |
| Fan | 22 | 15 | Output |

### Wiring each component

**DHT22 temperature/humidity sensor:**
- VCC → 3.3V (pin 1)
- Data → BCM 4 (pin 7)
- GND → Ground (pin 6 or any GND pin)
- Place a 10K ohm pull-up resistor between VCC and Data

**PIR motion sensor (HC-SR501):**
- VCC → 5V (pin 2 or 4)
- OUT → BCM 7 (pin 26)
- GND → Ground
- Adjust the two potentiometers on the sensor: one controls sensitivity, the other controls the hold time

**IR light, normal light, and fan:**
These are output devices and typically cannot be driven directly from a GPIO pin (max ~16mA). Use a transistor or MOSFET as a switch:
- GPIO pin → transistor/MOSFET gate (through a 1K resistor for BJT)
- Device power → 5V supply (pin 2 or 4, or external supply for high-current devices)
- Device ground → transistor/MOSFET drain → ground

For low-power LED strips or small fans that draw under 16mA, you can connect directly to the GPIO pin, but this is uncommon. A MOSFET (e.g., IRLZ44N) or a transistor (e.g., 2N2222) is recommended.

### Mounting

- Mount the Pi and camera inside or near the birdhouse in a weatherproof enclosure
- Position the camera to face the nesting area
- Mount the PIR sensor where it can detect birds entering
- Place the DHT22 sensor where it measures the air inside the birdhouse, away from direct sunlight and heat from the Pi
- Ensure the fan can draw air across the Pi for cooling
- Route the power cable to a nearby outdoor outlet

---

## Advanced Section

This section is for users comfortable with the Linux command line and SSH.

### SSH access

Connect to the Pi:
```bash
ssh admin@<pi-ip-address>
```

### Service management

All birdcam services are managed by systemd:

```bash
# Check status of all services
sudo systemctl status birdcam-stream birdcam-web birdcam-gpio nginx

# Restart a specific service
sudo systemctl restart birdcam-stream
sudo systemctl restart birdcam-web
sudo systemctl restart birdcam-gpio

# View live logs
sudo journalctl -u birdcam-stream -f
sudo journalctl -u birdcam-gpio -f

# View log files directly
cat /var/log/birdcam/stream.log
cat /var/log/birdcam/web.log
cat /var/log/birdcam/gpio.log
```

### Configuration file

The configuration file is at `/etc/birdcam/birdcam.yml`. You can edit it directly:

```bash
sudo nano /etc/birdcam/birdcam.yml
```

After editing, restart the relevant service:
```bash
sudo systemctl restart birdcam-stream   # for stream changes
sudo systemctl restart birdcam-gpio     # for GPIO/MQTT changes
```

See [Configuration Guide](CONFIGURATION.md) for all available settings.

### File locations

| What | Path |
|------|------|
| Application code | `/opt/birdcam/src/` |
| Configuration | `/etc/birdcam/birdcam.yml` |
| Snapshots | `/var/lib/birdcam/snapshots/` |
| Sensor database | `/var/lib/birdcam/sensor_data.db` |
| HLS segments (tmpfs) | `/dev/shm/birdcam/` |
| GPIO status (tmpfs) | `/dev/shm/birdcam/gpio_status.json` |
| Log files | `/var/log/birdcam/` |
| Python virtual environment | `/opt/birdcam/venv/` |
| Systemd units | `/etc/systemd/system/birdcam-*.service` |

### Database

Sensor data is stored in SQLite at `/var/lib/birdcam/sensor_data.db`. You can query it directly:

```bash
sudo -u birdcam sqlite3 /var/lib/birdcam/sensor_data.db

-- Recent sensor readings
SELECT * FROM sensor_data ORDER BY timestamp DESC LIMIT 10;

-- Recent motion events
SELECT * FROM motion_events ORDER BY timestamp DESC LIMIT 10;

-- Average temperature over the last 24 hours
SELECT AVG(temperature) FROM sensor_data
WHERE timestamp > datetime('now', '-1 day');
```

### MQTT integration

When MQTT is enabled, the GPIO service publishes a JSON payload to the configured topic at regular intervals. This is compatible with Home Assistant, Node-RED, and other MQTT-based dashboards.

Example Home Assistant `configuration.yaml`:
```yaml
mqtt:
  sensor:
    - name: "Birdhouse Temperature"
      state_topic: "birdcam/status"
      value_template: "{{ value_json.temperature }}"
      unit_of_measurement: "°C"
    - name: "Birdhouse Humidity"
      state_topic: "birdcam/status"
      value_template: "{{ value_json.humidity }}"
      unit_of_measurement: "%"
    - name: "Birdhouse Motion"
      state_topic: "birdcam/status"
      value_template: "{{ value_json.movement_status }}"
```

### API

The birdcam provides a REST API for programmatic access. All endpoints return JSON.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | System health and service status |
| `/api/snapshot` | POST | Capture a snapshot |
| `/api/snapshots` | GET | List all snapshots |
| `/api/config` | GET | Read current configuration |
| `/api/config` | PUT | Update configuration |
| `/api/gpio/status` | GET | Current sensor readings and switch states |
| `/api/gpio/light` | POST | Toggle light (`{"state": true}`) |
| `/api/gpio/ir-light` | POST | Toggle IR light (`{"state": true}`) |
| `/api/gpio/fan` | POST | Toggle fan (`{"state": true}`) |
| `/api/sensor-data?minutes=N` | GET | Sensor time-series data |
| `/api/motion-events?minutes=N` | GET | Motion event history |
| `/api/logs` | GET | Log entries (query: `source`, `level`, `minutes`, `verbose`) |
| `/api/restart-stream` | POST | Restart camera pipeline |
| `/api/restart-gpio` | POST | Restart GPIO service |

Example:
```bash
# Get current sensor readings
curl http://<pi-ip>/api/gpio/status

# Take a snapshot
curl -X POST http://<pi-ip>/api/snapshot

# Get last hour of temperature data
curl http://<pi-ip>/api/sensor-data?minutes=60
```

### Updating

```bash
cd /path/to/Vogelhuis
git pull
sudo bash update.sh
```

The update script stops all services, copies new files, installs dependencies, and restarts everything. Your configuration is preserved.

### Backup and restore

```bash
# Backup
mkdir -p ~/birdcam-backup
cp /etc/birdcam/birdcam.yml ~/birdcam-backup/
cp /var/lib/birdcam/sensor_data.db ~/birdcam-backup/
cp -r /var/lib/birdcam/snapshots ~/birdcam-backup/

# Restore
sudo cp ~/birdcam-backup/birdcam.yml /etc/birdcam/
sudo cp ~/birdcam-backup/sensor_data.db /var/lib/birdcam/
sudo cp ~/birdcam-backup/snapshots/* /var/lib/birdcam/snapshots/
sudo chown -R birdcam:birdcam /var/lib/birdcam
sudo systemctl restart birdcam-stream birdcam-web birdcam-gpio
```

### Uninstalling

```bash
sudo bash uninstall.sh
```

This removes services, nginx config, the application directory, and the system user. Snapshots and sensor data in `/var/lib/birdcam/` are preserved by default.
