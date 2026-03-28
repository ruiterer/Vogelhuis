#!/usr/bin/env python3
"""Birdcam GPIO & Sensor Service.

Runs as a standalone daemon (birdcam-gpio.service) managing:
- Light control (complementary schedule + manual override)
- Fan control (CPU temperature with hysteresis + manual override)
- DHT22 temperature/humidity sensor
- PIR motion detection
- Sensor data recording to SQLite
- Optional MQTT publishing
"""

import json
import os
import signal
import sys
import time
from datetime import datetime, timedelta

# Add src/ to path when running as a script
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import load as load_config
from database import init_db, record_sensor_data, record_motion_event, cleanup_old_data, close as close_db
from logging_setup import get_logger

logger = get_logger("gpio")

# --- Global state ---

_running = True
_state = {
    "light": False,
    "ir_light": False,
    "fan": False,
    "motion": False,
    "temperature": None,
    "humidity": None,
    "cpu_temp": None,
    "cpu_load": None,
    "light_override": None,     # None = schedule, True/False = manual
    "ir_light_override": None,
    "fan_override": None,       # None = auto, True/False = manual
}

# Track motion timing
_last_motion_event = 0
_motion_start_time = None

# Track cleanup timing
_last_cleanup = 0
CLEANUP_INTERVAL = 3600  # 1 hour

# GPIO chip and line objects (gpiod)
_chip = None
_output_lines = {}
_motion_line = None

# MQTT client
_mqtt_client = None
_last_mqtt_publish = 0

# DHT sensor
_dht_device = None


def get_state():
    """Return a copy of current state (for IPC)."""
    return dict(_state)


# --- Signal handling ---

def _signal_handler(signum, frame):
    global _running
    logger.info("Received signal %d, shutting down", signum)
    _running = False


# --- GPIO (gpiod) ---

def _init_gpio(config):
    """Initialize GPIO pins using gpiod."""
    global _chip, _output_lines, _motion_line

    try:
        import gpiod
    except ImportError:
        logger.error("gpiod not available — GPIO disabled")
        return False

    pins = config["gpio"]["pins"]

    try:
        _chip = gpiod.Chip("/dev/gpiochip0")
    except (FileNotFoundError, PermissionError) as e:
        # Try gpiochip4 for Pi 5
        try:
            _chip = gpiod.Chip("/dev/gpiochip4")
        except Exception:
            logger.error("Cannot open GPIO chip: %s", e)
            return False

    # Configure output pins
    output_pins = {
        "ir_light": pins["ir_light"],
        "light": pins["light"],
        "fan": pins["fan"],
    }

    try:
        config_output = gpiod.LineSettings(
            direction=gpiod.line.Direction.OUTPUT,
            output_value=gpiod.line.Value.INACTIVE,
        )
        config_input = gpiod.LineSettings(
            direction=gpiod.line.Direction.INPUT,
            edge_detection=gpiod.line.Edge.BOTH,
            debounce_period=timedelta(milliseconds=50),
        )

        req_lines = {}
        for name, pin in output_pins.items():
            req_lines[int(pin)] = config_output

        # Request output lines
        _output_lines = _chip.request_lines(
            consumer="birdcam-gpio",
            config=req_lines,
        )

        # Request motion input line
        _motion_line = _chip.request_lines(
            consumer="birdcam-motion",
            config={int(pins["motion"]): config_input},
        )

        logger.info("GPIO initialized: outputs=%s, motion=GPIO%d",
                     {k: v for k, v in output_pins.items()}, pins["motion"])
        return True

    except Exception as e:
        logger.error("GPIO initialization failed: %s", e)
        return False


def _set_output(pin, state):
    """Set a GPIO output pin high (True) or low (False)."""
    if _output_lines is None:
        return
    try:
        import gpiod
        value = gpiod.line.Value.ACTIVE if state else gpiod.line.Value.INACTIVE
        _output_lines.set_value(int(pin), value)
    except Exception as e:
        logger.error("Failed to set GPIO %d: %s", pin, e)


def _cleanup_gpio():
    """Release GPIO resources."""
    global _output_lines, _motion_line, _chip
    try:
        if _output_lines:
            _output_lines.release()
            _output_lines = None
        if _motion_line:
            _motion_line.release()
            _motion_line = None
        if _chip:
            _chip.close()
            _chip = None
    except Exception as e:
        logger.warning("GPIO cleanup error: %s", e)


# --- DHT22 sensor ---

def _init_dht(config):
    """Initialize DHT22 sensor."""
    global _dht_device
    pin = config["gpio"]["pins"]["dht22"]
    try:
        import adafruit_dht
        import board
        # Map BCM pin number to board pin
        pin_map = {
            4: board.D4, 5: board.D5, 6: board.D6, 7: board.D7,
            8: board.D8, 9: board.D9, 10: board.D10, 11: board.D11,
            12: board.D12, 13: board.D13, 14: board.D14, 15: board.D15,
            16: board.D16, 17: board.D17, 18: board.D18, 19: board.D19,
            20: board.D20, 21: board.D21, 22: board.D22, 23: board.D23,
            24: board.D24, 25: board.D25, 26: board.D26, 27: board.D27,
        }
        board_pin = pin_map.get(int(pin))
        if board_pin is None:
            logger.error("No board mapping for GPIO %d", pin)
            return False
        _dht_device = adafruit_dht.DHT22(board_pin, use_pulseio=False)
        logger.info("DHT22 initialized on GPIO %d", pin)
        return True
    except ImportError:
        logger.error("adafruit_dht not available — DHT22 disabled")
        return False
    except Exception as e:
        logger.error("DHT22 initialization failed: %s", e)
        return False


def _read_dht():
    """Read temperature and humidity from DHT22. Returns (temp, humidity) or (None, None)."""
    if _dht_device is None:
        return None, None
    try:
        temp = _dht_device.temperature
        hum = _dht_device.humidity
        if temp is not None and hum is not None:
            return round(temp, 1), round(hum, 1)
    except RuntimeError as e:
        # DHT22 is notoriously flaky — retry once
        try:
            time.sleep(2)
            temp = _dht_device.temperature
            hum = _dht_device.humidity
            if temp is not None and hum is not None:
                return round(temp, 1), round(hum, 1)
        except Exception:
            pass
        logger.debug("DHT22 read failed: %s", e)
    except Exception as e:
        logger.warning("DHT22 error: %s", e)
    return None, None


def _cleanup_dht():
    """Release DHT22 resources."""
    global _dht_device
    if _dht_device:
        try:
            _dht_device.exit()
        except Exception:
            pass
        _dht_device = None


# --- CPU metrics ---

def _read_cpu_temp():
    """Read CPU temperature in Celsius."""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return round(int(f.read().strip()) / 1000, 1)
    except (FileNotFoundError, ValueError):
        return None


def _read_cpu_load():
    """Read CPU load percentage."""
    try:
        import psutil
        return psutil.cpu_percent(interval=0)
    except ImportError:
        # Fallback: read /proc/stat
        try:
            with open("/proc/loadavg") as f:
                return round(float(f.read().split()[0]) * 100, 1)
        except Exception:
            return None


# --- Fan control ---

def _update_fan(config):
    """Auto-control fan based on CPU temperature with hysteresis."""
    cpu_temp = _state["cpu_temp"]
    if cpu_temp is None:
        return

    fan_config = config["gpio"]["fan"]
    on_temp = fan_config["on_temp"]
    off_temp = fan_config["off_temp"]
    fan_pin = config["gpio"]["pins"]["fan"]

    # If manual override is active, clear it (one-cycle hold)
    if _state["fan_override"] is not None:
        _state["fan_override"] = None
        return

    if cpu_temp > on_temp and not _state["fan"]:
        _state["fan"] = True
        _set_output(fan_pin, True)
        logger.info("Fan ON (CPU %.1f°C > %d°C)", cpu_temp, on_temp)
    elif cpu_temp < off_temp and _state["fan"]:
        _state["fan"] = False
        _set_output(fan_pin, False)
        logger.info("Fan OFF (CPU %.1f°C < %d°C)", cpu_temp, off_temp)


# --- Light schedule ---

def _parse_time(time_str):
    """Parse HH:MM string to (hour, minute) tuple."""
    parts = time_str.split(":")
    return int(parts[0]), int(parts[1])


def _is_night_time(config):
    """Determine if current time is in the 'night' period."""
    schedule = config["gpio"]["light_schedule"]
    night_h, night_m = _parse_time(schedule["night_start"])
    day_h, day_m = _parse_time(schedule["day_start"])

    now = datetime.now()
    night_time = now.replace(hour=night_h, minute=night_m, second=0, microsecond=0)
    day_time = now.replace(hour=day_h, minute=day_m, second=0, microsecond=0)

    current_minutes = now.hour * 60 + now.minute
    night_minutes = night_h * 60 + night_m
    day_minutes = day_h * 60 + day_m

    if night_minutes > day_minutes:
        # Normal case: night_start (21:15) > day_start (06:30)
        # Night is from night_start to midnight + midnight to day_start
        return current_minutes >= night_minutes or current_minutes < day_minutes
    else:
        # Inverted: night_start < day_start
        return night_minutes <= current_minutes < day_minutes


def _check_schedule_transition(config):
    """Check if we're at a schedule transition point and clear overrides."""
    schedule = config["gpio"]["light_schedule"]
    now = datetime.now()
    current_hm = f"{now.hour:02d}:{now.minute:02d}"

    if current_hm == schedule["night_start"] or current_hm == schedule["day_start"]:
        if _state["light_override"] is not None or _state["ir_light_override"] is not None:
            logger.info("Schedule transition — clearing manual overrides")
            _state["light_override"] = None
            _state["ir_light_override"] = None


def _update_lights(config):
    """Update lights based on schedule, respecting manual overrides."""
    pins = config["gpio"]["pins"]

    _check_schedule_transition(config)

    night = _is_night_time(config)

    # IR light: on at night, off during day (unless overridden)
    if _state["ir_light_override"] is not None:
        desired_ir = _state["ir_light_override"]
    else:
        desired_ir = night

    if desired_ir != _state["ir_light"]:
        _state["ir_light"] = desired_ir
        _set_output(pins["ir_light"], desired_ir)
        logger.info("IR light %s (%s)", "ON" if desired_ir else "OFF",
                     "override" if _state["ir_light_override"] is not None else "schedule")

    # Normal light: on during day, off at night (unless overridden)
    if _state["light_override"] is not None:
        desired_light = _state["light_override"]
    else:
        desired_light = not night

    if desired_light != _state["light"]:
        _state["light"] = desired_light
        _set_output(pins["light"], desired_light)
        logger.info("Light %s (%s)", "ON" if desired_light else "OFF",
                     "override" if _state["light_override"] is not None else "schedule")


# --- Motion detection ---

def _check_motion(config):
    """Check PIR sensor for motion events."""
    global _last_motion_event, _motion_start_time

    if _motion_line is None:
        return

    motion_pin = config["gpio"]["pins"]["motion"]
    cooldown = config["gpio"]["motion"]["cooldown"]

    try:
        import gpiod
        # Read current value
        value = _motion_line.get_value(int(motion_pin))
        motion_detected = (value == gpiod.line.Value.ACTIVE)

        if motion_detected and not _state["motion"]:
            # Rising edge — motion started
            _state["motion"] = True
            _motion_start_time = time.time()
            now = time.time()
            if now - _last_motion_event >= cooldown:
                record_motion_event()
                _last_motion_event = now
                logger.info("Motion detected")

        elif not motion_detected and _state["motion"]:
            # Falling edge — motion ended
            _state["motion"] = False
            if _motion_start_time:
                duration = time.time() - _motion_start_time
                _motion_start_time = None
                logger.debug("Motion ended (%.1fs)", duration)

    except Exception as e:
        logger.debug("Motion check error: %s", e)


# --- MQTT ---

def _init_mqtt(config):
    """Initialize MQTT client if enabled."""
    global _mqtt_client
    mqtt_config = config.get("mqtt", {})
    if not mqtt_config.get("enabled", False):
        return

    broker = mqtt_config.get("broker", "").strip()
    if not broker:
        logger.warning("MQTT enabled but no broker configured")
        return

    try:
        import paho.mqtt.client as mqtt
        _mqtt_client = mqtt.Client(client_id="birdcam-gpio")
        _mqtt_client.on_connect = lambda c, u, f, rc: logger.info("MQTT connected to %s", broker)
        _mqtt_client.on_disconnect = lambda c, u, rc: logger.warning("MQTT disconnected (rc=%d)", rc)
        _mqtt_client.connect_async(broker, int(mqtt_config.get("port", 1883)))
        _mqtt_client.loop_start()
        logger.info("MQTT client initialized (broker=%s:%d)", broker, mqtt_config.get("port", 1883))
    except ImportError:
        logger.error("paho-mqtt not available — MQTT disabled")
    except Exception as e:
        logger.error("MQTT init failed: %s", e)


def _publish_mqtt(config):
    """Publish sensor status via MQTT."""
    global _last_mqtt_publish

    if _mqtt_client is None:
        return

    mqtt_config = config.get("mqtt", {})
    if not mqtt_config.get("enabled", False):
        return

    now = time.time()
    interval = mqtt_config.get("publish_interval", 60)
    if now - _last_mqtt_publish < interval:
        return

    topic = mqtt_config.get("topic", "birdcam/status")
    payload = {
        "location": mqtt_config.get("location", "Tuin"),
        "object": mqtt_config.get("object_name", "Vogelhuis_Boom"),
        "temperature": _state["temperature"] or 0,
        "humidity": _state["humidity"] or 0,
        "light_status": 1 if _state["light"] else 0,
        "ir_light_status": 1 if _state["ir_light"] else 0,
        "ventilation_status": 1 if _state["fan"] else 0,
        "movement_status": 1 if _state["motion"] else 0,
        "cpu_temp": _state["cpu_temp"] or 0,
        "cpu_load": _state["cpu_load"] or 0,
    }

    try:
        _mqtt_client.publish(topic, json.dumps(payload), qos=0)
        _last_mqtt_publish = now
    except Exception as e:
        logger.warning("MQTT publish failed: %s", e)


def _cleanup_mqtt():
    """Disconnect MQTT client."""
    global _mqtt_client
    if _mqtt_client:
        try:
            _mqtt_client.loop_stop()
            _mqtt_client.disconnect()
        except Exception:
            pass
        _mqtt_client = None


# --- Command processing (IPC via file) ---

COMMAND_FILE = "/dev/shm/birdcam/gpio_commands"


def _process_commands(config):
    """Read and process pending GPIO control commands."""
    if not os.path.exists(COMMAND_FILE):
        return

    try:
        with open(COMMAND_FILE, "r") as f:
            commands = f.readlines()
        # Clear the file immediately
        with open(COMMAND_FILE, "w") as f:
            f.write("")
    except (PermissionError, OSError):
        return

    pins = config["gpio"]["pins"]

    for line in commands:
        line = line.strip()
        if not line:
            continue
        try:
            cmd = json.loads(line)
            target = cmd.get("target")
            state = cmd.get("state")

            if target == "light":
                _state["light_override"] = state
                _state["light"] = state
                _set_output(pins["light"], state)
                logger.info("Light manually set %s", "ON" if state else "OFF")

            elif target == "ir_light":
                _state["ir_light_override"] = state
                _state["ir_light"] = state
                _set_output(pins["ir_light"], state)
                logger.info("IR light manually set %s", "ON" if state else "OFF")

            elif target == "fan":
                _state["fan_override"] = state
                _state["fan"] = state
                _set_output(pins["fan"], state)
                logger.info("Fan manually set %s", "ON" if state else "OFF")

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Invalid command: %s (%s)", line, e)


# --- Status file (for web service to read) ---

STATUS_FILE = "/dev/shm/birdcam/gpio_status.json"


def _write_status():
    """Write current state to a status file for the web service."""
    try:
        status = {
            "light": _state["light"],
            "ir_light": _state["ir_light"],
            "fan": _state["fan"],
            "fan_auto": _state["fan_override"] is None,
            "motion": _state["motion"],
            "temperature": _state["temperature"],
            "humidity": _state["humidity"],
            "cpu_temp": _state["cpu_temp"],
            "cpu_load": _state["cpu_load"],
            "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        }
        tmp = STATUS_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(status, f)
        os.replace(tmp, STATUS_FILE)
    except (PermissionError, OSError) as e:
        logger.debug("Status file write failed: %s", e)


# --- Main loop ---

def main():
    global _running, _last_cleanup

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    logger.info("GPIO service starting")

    config = load_config()

    if not config["gpio"].get("enabled", True):
        logger.info("GPIO disabled in config — exiting")
        return

    # Initialize database
    init_db()

    # Initialize hardware
    gpio_ok = _init_gpio(config)
    dht_ok = _init_dht(config)
    _init_mqtt(config)

    if not gpio_ok:
        logger.warning("GPIO init failed — running in degraded mode (sensors only)")

    poll_interval = config["gpio"]["sensor_poll_interval"]
    last_sensor_read = 0

    # Set initial light state from schedule
    _update_lights(config)

    logger.info("GPIO service ready (poll interval: %ds)", poll_interval)

    try:
        while _running:
            now = time.time()

            # Reload config periodically (every 5 cycles)
            if int(now) % (poll_interval * 5) < poll_interval:
                config = load_config()

            # Process any pending commands from web UI
            _process_commands(config)

            # Check motion (fast loop — every 0.5s)
            _check_motion(config)

            # Sensor read cycle
            if now - last_sensor_read >= poll_interval:
                # Read sensors
                temp, hum = _read_dht()
                _state["temperature"] = temp
                _state["humidity"] = hum
                _state["cpu_temp"] = _read_cpu_temp()
                _state["cpu_load"] = _read_cpu_load()

                # Fan auto-control
                _update_fan(config)

                # Light schedule
                _update_lights(config)

                # Record to database
                record_sensor_data(
                    temperature=_state["temperature"],
                    humidity=_state["humidity"],
                    cpu_temp=_state["cpu_temp"],
                    cpu_load=_state["cpu_load"],
                    light_status=1 if _state["light"] else 0,
                    ir_light_status=1 if _state["ir_light"] else 0,
                    fan_status=1 if _state["fan"] else 0,
                    motion_status=1 if _state["motion"] else 0,
                )

                # MQTT
                _publish_mqtt(config)

                # Write status for web service
                _write_status()

                last_sensor_read = now

            # Data retention cleanup (hourly)
            if now - _last_cleanup >= CLEANUP_INTERVAL:
                retention = config["gpio"].get("data_retention_days", 30)
                cleanup_old_data(retention)
                _last_cleanup = now

            # Sleep briefly — motion needs fast response
            time.sleep(0.5)

    except Exception as e:
        logger.error("Fatal error in main loop: %s", e)
    finally:
        logger.info("GPIO service shutting down")
        _cleanup_dht()
        _cleanup_mqtt()
        _cleanup_gpio()
        close_db()
        # Remove status file
        try:
            os.unlink(STATUS_FILE)
        except OSError:
            pass


if __name__ == "__main__":
    main()
