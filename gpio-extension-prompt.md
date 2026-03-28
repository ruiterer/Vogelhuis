# Vogelhuis GPIO & Sensor Extension — Implementation Prompt

## Context

This is the Vogelhuis project — a Raspberry Pi birdhouse camera system with a Flask web UI, HLS live stream, and systemd services. See `CLAUDE.md` for the full architecture.

The project is being extended to replace a Node-RED setup with native GPIO control, environmental sensors, motion detection, MQTT publishing, and historical graphs. All new functionality must follow the existing architecture patterns: YAML config, centralized logging, systemd services, vendored frontend libraries, no cloud/Docker/internet dependencies.

Reference files from the original Node-RED implementation are in `/Users/erik/Downloads/`:
- `detect-movement.py` — PIR motion detection script (GPIO 7, BCM mode, 100ms poll)
- `initialization_raspberry_pins.json` — GPIO pin init (13, 19, 22 as outputs)
- `fan_control.json` — CPU temp fan control (ON >50°C, OFF <40°C, 60s poll)
- `get_temperature_humidity.json` — DHT22 sensor read (pin 7/pintype 4, 60s interval)
- `get_status_from_switches.json` — GPIO pin state polling + MQTT message assembly
- `switch_control.json` — UI switches for IR/light/fan + light schedules
- `run_motion_detection.json` — Node-RED exec node launching the motion script

---

## 1. New Source Module: `src/gpio_service.py`

Create a new daemon that runs as a separate systemd service (`birdcam-gpio.service`), decoupled from the web service. This is the main loop that:

### 1.1 GPIO Initialization
- On startup, configure output pins (IR light, normal light, fan) and input pin (motion sensor) using **`gpiod`** (libgpiod Python bindings — modern, works on Pi 4 and Pi 5, preferred on Bookworm).
- All pin numbers are read from `birdcam.yml` config (see section 7).
- On shutdown, release GPIO resources cleanly.

### 1.2 Light Control (Complementary Schedule)
- Two lights operate on a complementary schedule defined by a single time pair:
  - **Night start** (default `21:15`): IR light ON, normal light OFF
  - **Day start** (default `06:30`): IR light OFF, normal light ON
- Both times are configurable via the settings page and persisted to `birdcam.yml`.
- Manual toggle override (via API) is allowed. The override holds until the next scheduled transition, at which point the schedule reasserts.
- Track override state in memory (not persisted — reboot restores schedule).

### 1.3 Fan Control (CPU Temperature)
- Read CPU temperature every `sensor_poll_interval` seconds (default 60) via `vcgencmd measure_temp` or `/sys/class/thermal/thermal_zone0/temp`.
- Fan turns ON when CPU temp exceeds `fan_on_temp` (default 50°C).
- Fan turns OFF when CPU temp drops below `fan_off_temp` (default 40°C).
- Both thresholds are configurable via settings page.
- Manual fan toggle via API: override holds until the next check cycle, then auto-control resumes.

### 1.4 DHT22 Sensor Reading
- Read temperature and humidity from a DHT22 sensor every `sensor_poll_interval` seconds.
- Use the most reliable Python library for DHT22 on Bookworm with `gpiod` (evaluate `adafruit-circuitpython-dht` with `libgpiod`).
- DHT22 GPIO pin is configurable (default GPIO 4).
- Handle read failures gracefully (DHT22 is notoriously flaky — retry once, log warning, skip cycle on failure).

### 1.5 Motion Detection
- Monitor PIR sensor GPIO pin (default GPIO 7) for rising/falling edges using `gpiod` event monitoring.
- Implement a **software cooldown** (configurable, default 30 seconds) — don't log a new motion event within the cooldown period of the last one.
- Log each motion event (start timestamp) to the SQLite database.
- Update a shared state (e.g., in the database or a status file) so the web UI can show current motion status.

### 1.6 Data Recording
- Every `sensor_poll_interval` seconds, write a record to the SQLite database containing:
  - Timestamp
  - Birdhouse temperature (°C)
  - Birdhouse humidity (%)
  - CPU temperature (°C)
  - CPU load (%)
  - Light status (on/off)
  - IR light status (on/off)
  - Fan status (on/off)
  - Motion status (active/inactive)

### 1.7 MQTT Publishing (Optional)
- MQTT can be enabled/disabled in config (`mqtt.enabled`, default `false`).
- When enabled, publish a JSON message every `mqtt.publish_interval` seconds (default 60) to the configured MQTT broker.
- Configurable settings: `mqtt.broker` (host), `mqtt.port` (default 1883), `mqtt.topic` (default `birdcam/status`), `mqtt.location` (default `Tuin`), `mqtt.object_name` (default `Vogelhuis_Boom`).
- Payload format (matches existing Node-RED format):
  ```json
  {
    "location": "Tuin",
    "object": "Vogelhuis_Boom",
    "temperature": 22.5,
    "humidity": 65.0,
    "light_status": 1,
    "ir_light_status": 0,
    "ventilation_status": 0,
    "movement_status": 0,
    "cpu_temp": 45.2,
    "cpu_load": 12.3
  }
  ```
- Use `paho-mqtt` library. Handle broker disconnection gracefully (retry with backoff, don't crash the service).

### 1.8 Logging
- Register a new `gpio` source in `logging_setup.py`'s `SOURCE_FILE_MAP`.
- Use `get_logger('gpio')` for all logging.
- Log to its own log file (`/var/log/birdcam/gpio.log`).

---

## 2. SQLite Database: `src/database.py`

Create a database module for sensor data storage.

### 2.1 Schema
```sql
CREATE TABLE sensor_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    temperature REAL,        -- birdhouse temp (°C)
    humidity REAL,           -- birdhouse humidity (%)
    cpu_temp REAL,           -- CPU temperature (°C)
    cpu_load REAL,           -- CPU load (%)
    light_status INTEGER,    -- 0=off, 1=on
    ir_light_status INTEGER, -- 0=off, 1=on
    fan_status INTEGER,      -- 0=off, 1=on
    motion_status INTEGER    -- 0=no motion, 1=motion
);

CREATE TABLE motion_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    duration_seconds REAL    -- how long motion lasted (NULL if still active)
);
```

### 2.2 Database Location
- Store at `/var/lib/birdcam/sensor_data.db`.
- Create with WAL mode enabled for concurrent read/write (web reads while gpio service writes).

### 2.3 Data Retention
- Configurable retention period (default 30 days).
- Cleanup runs on the existing cleanup timer pattern (hourly via systemd timer or within the gpio service loop).
- Delete records older than the retention period.

### 2.4 Query Helpers
- `get_sensor_data(minutes)` — return sensor records for the last N minutes (for graph API).
- `get_motion_events(minutes)` — return motion events for the last N minutes.
- `get_latest_reading()` — return the most recent sensor record (for dashboard display).
- `record_sensor_data(...)` — insert a new sensor reading.
- `record_motion_event(...)` — insert a new motion event.

---

## 3. New API Endpoints in `src/app.py`

### 3.1 GPIO Control
- `POST /api/gpio/light` — toggle normal light (body: `{"state": true/false}`)
- `POST /api/gpio/ir-light` — toggle IR light (body: `{"state": true/false}`)
- `POST /api/gpio/fan` — toggle fan (body: `{"state": true/false}`)
- `GET /api/gpio/status` — return current state of all switches, sensor readings, and motion status

### 3.2 Sensor Data (for graphs)
- `GET /api/sensor-data?minutes=60` — return sensor time-series data for the requested period
- `GET /api/motion-events?minutes=60` — return motion events for the requested period

### 3.3 Communication Between Web and GPIO Service
- The web service reads from the SQLite database for sensor data and status.
- For GPIO control commands (toggle light/fan), use a lightweight IPC mechanism:
  - Option A: Write command to a small SQLite `commands` table that the gpio service polls.
  - Option B: Unix domain socket or named pipe.
  - Option C: A simple file-based command queue in `/dev/shm/birdcam/`.
  - Choose the simplest reliable approach that fits the existing architecture.

---

## 4. Web UI — Main Stream Page (`/`) Modifications

### 4.1 Control Switches
- Add toggle switches for **IR Light**, **Normal Light**, and **Fan** next to the existing snapshot and fullscreen buttons.
- Each switch shows current state (on/off) and can be toggled.
- Fan switch should indicate when it's in auto mode vs manual override.
- Use simple toggle button styling consistent with the existing UI (vanilla HTML/CSS/JS, no frameworks).

### 4.2 Live Sensor Readings
- Below the button row but above the snapshot links, display:
  - Birdhouse temperature (°C)
  - Birdhouse humidity (%)
  - CPU temperature (°C)
  - Motion indicator (active/inactive)
- Poll `/api/gpio/status` every 5-10 seconds for live updates.
- Show "--" or similar placeholder when sensor data is unavailable.

---

## 5. Web UI — New Graphs Page (`/graphs`)

### 5.1 Page Layout
- New page accessible from the navigation (add nav link alongside existing pages).
- Time range selector buttons: **1h**, **6h**, **12h**, **24h**, **7d**, **30d**.
- Default view: last 24 hours.

### 5.2 Charts (use Chart.js, vendored)
- **Temperature chart**: Birdhouse temperature and CPU temperature on the same chart (dual y-axis or shared, whichever reads better). Line chart with time x-axis.
- **Humidity chart**: Birdhouse humidity. Line chart.
- **Motion activity chart**: Bar chart or timeline showing motion events over time.
- All charts are responsive and work on mobile browsers.
- Charts auto-refresh every 60 seconds (or match the sensor poll interval).

### 5.3 Chart.js
- Vendor Chart.js (like hls.js is vendored) — download the minified bundle into `static/js/`.
- Include the `chartjs-adapter-date-fns` (or similar lightweight date adapter) for time-axis support.

---

## 6. Systemd Service: `birdcam-gpio.service`

```ini
[Unit]
Description=Birdcam GPIO & Sensor Service
After=network.target
Wants=birdcam-stream.service

[Service]
Type=simple
User=birdcam
Group=birdcam
ExecStart=/opt/birdcam/venv/bin/python /opt/birdcam/src/gpio_service.py
Restart=on-failure
RestartSec=5
StandardError=journal

[Install]
WantedBy=multi-user.target
```

- The `birdcam` user needs permission to access GPIO via `gpiod` (add to `gpio` group if needed).
- Register this service in the health check system so it appears on the health dashboard.

---

## 7. Configuration Additions to `birdcam.yml`

Add a new `gpio` section to the config schema in `src/config.py`:

```yaml
gpio:
  enabled: true
  sensor_poll_interval: 60      # seconds
  pins:
    ir_light: 13                # BCM GPIO number
    light: 19                   # BCM GPIO number
    fan: 22                     # BCM GPIO number
    dht22: 4                    # BCM GPIO number
    motion: 7                   # BCM GPIO number
  fan:
    on_temp: 50                 # °C — turn fan on above this
    off_temp: 40                # °C — turn fan off below this
  light_schedule:
    night_start: "21:15"        # IR on, light off
    day_start: "06:30"          # IR off, light on
  motion:
    cooldown: 30                # seconds between logged events
  data_retention_days: 30       # delete sensor data older than this

mqtt:
  enabled: false
  broker: ""                    # hostname or IP
  port: 1883
  topic: "birdcam/status"
  location: "Tuin"
  object_name: "Vogelhuis_Boom"
  publish_interval: 60          # seconds
```

- Add defaults and validation in `config.py` (validate pin numbers, temp thresholds, time formats, intervals).
- All GPIO settings must be editable from the `/settings` page and persist to YAML.

---

## 8. Settings Page Updates (`/settings`)

Add new sections to the settings page:

### 8.1 GPIO Settings
- Pin assignments (IR light, light, fan, DHT22, motion) — number inputs
- Fan temperature thresholds (on/off) — number inputs with °C labels
- Light schedule (night start, day start) — time inputs
- Motion cooldown — number input in seconds
- Sensor poll interval — number input in seconds

### 8.2 MQTT Settings
- Enable/disable toggle
- Broker hostname/IP — text input
- Port — number input
- Topic — text input
- Location — text input
- Object name — text input
- Publish interval — number input in seconds

### 8.3 Data Settings
- Data retention period — number input in days

All settings use the existing config API pattern (`GET/PUT /api/config`).

---

## 9. Installation & Dependencies

### 9.1 System Packages
Add to `install.sh`:
```bash
sudo apt-get install -y python3-libgpiod libgpiod-dev
```

### 9.2 Python Packages
Add to requirements or venv setup:
- `gpiod` (libgpiod Python bindings)
- `adafruit-circuitpython-dht` (or whichever DHT22 library is most reliable)
- `paho-mqtt` (for optional MQTT support)

### 9.3 Permissions
- Ensure the `birdcam` user is in the `gpio` group (for `gpiod` access).
- SQLite database directory (`/var/lib/birdcam/`) already exists — ensure write permission.

### 9.4 Update Script
Update `update.sh` to:
- Install new Python dependencies
- Deploy `birdcam-gpio.service`
- Enable and start the new service
- Run database migrations if needed

---

## 10. Health Dashboard Updates

- Add `birdcam-gpio.service` to the list of monitored services in `health.py`.
- Show the GPIO service status on the health page alongside stream and web services.
- Add `gpio` as a log source so GPIO logs appear in the health page log viewer.

---

## 11. Testing

### 11.1 Unit Tests (`tests/test_gpio.py`)
Write comprehensive tests covering:

**Config & Validation:**
- GPIO config defaults are applied correctly
- Pin number validation (valid BCM range, no duplicates)
- Fan threshold validation (on_temp > off_temp)
- Light schedule time format validation
- MQTT config validation (broker required when enabled)
- Sensor poll interval bounds (minimum 10s, maximum 300s)
- Motion cooldown bounds
- Data retention bounds

**Database (`tests/test_database.py`):**
- Schema creation on first run
- `record_sensor_data()` inserts correctly
- `record_motion_event()` inserts correctly
- `get_sensor_data(minutes)` returns correct time range
- `get_motion_events(minutes)` returns correct time range
- `get_latest_reading()` returns most recent record
- Data retention cleanup deletes old records, keeps recent ones
- WAL mode is enabled
- Concurrent read/write doesn't block
- Empty database returns sensible defaults

**Fan Control Logic:**
- Fan turns ON when CPU > on_temp
- Fan stays OFF when CPU between off_temp and on_temp
- Fan turns OFF when CPU < off_temp
- Hysteresis: fan stays ON when CPU drops to between thresholds
- Manual override holds for one cycle then auto resumes

**Light Schedule Logic:**
- Correct light states during "day" period
- Correct light states during "night" period
- Schedule transition at boundary times
- Manual override is tracked
- Manual override reverts at next scheduled time
- Edge case: current time equals schedule time exactly
- Schedule change via config updates correctly

**Motion Detection Logic:**
- Motion event logged on rising edge
- Cooldown period prevents duplicate logging
- Motion event after cooldown is logged
- Duration tracking (start → end)

**MQTT:**
- Message payload format matches expected schema
- MQTT disabled by default (no connection attempt)
- MQTT enabled constructs correct payload
- Graceful handling when broker unreachable

**API Endpoints:**
- `POST /api/gpio/light` toggles state
- `POST /api/gpio/ir-light` toggles state
- `POST /api/gpio/fan` toggles state
- `GET /api/gpio/status` returns all states
- `GET /api/sensor-data?minutes=60` returns data
- `GET /api/motion-events?minutes=60` returns data
- Invalid parameters return appropriate errors
- GPIO control when service not running returns graceful error

### 11.2 Integration Tests (`tests/test_gpio_integration.py`)
- Config round-trip: save GPIO settings via API, read back, verify
- Settings page loads with GPIO/MQTT sections
- Graphs page loads and contains chart elements
- Main page includes toggle switches and sensor readout area
- API returns valid JSON for all new endpoints

### 11.3 Smoke Tests (extend `tests/smoke_test.sh`)
Add checks for:
- `birdcam-gpio.service` is active
- SQLite database file exists and is readable
- `/api/gpio/status` returns 200
- `/api/sensor-data?minutes=1` returns 200
- `/graphs` page returns 200
- GPIO log file exists
- Settings page contains GPIO config fields

---

## Implementation Order

1. `src/database.py` — SQLite schema, queries, retention
2. `src/config.py` — add GPIO/MQTT config section, defaults, validation
3. `src/gpio_service.py` — main daemon (GPIO init, sensor loop, fan/light/motion logic, MQTT)
4. `src/logging_setup.py` — register `gpio` source
5. `src/app.py` — new API endpoints
6. `src/health.py` — register GPIO service monitoring
7. Templates/static — update main page (switches, readings), settings page (GPIO/MQTT sections), new graphs page
8. `static/js/` — vendor Chart.js, implement graph rendering
9. Systemd unit file, install/update scripts, permissions
10. Tests — unit, integration, smoke test extensions
11. Update `CLAUDE.md` with new architecture documentation

---

## Constraints Reminder

- No internet dependency at runtime (all JS vendored)
- Vanilla HTML/CSS/JS only (no React, no build step)
- Keep CPU usage low — sensor polling and DB writes are lightweight
- Minimize SD card writes — SQLite with WAL mode, reasonable poll intervals
- All config survives reboot (YAML + systemd)
- Must work on Pi 4B, Pi Zero 2 W, and Pi 5
- Follow existing code patterns (centralized logging, config validation, systemd integration)
