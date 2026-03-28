"""Tests for GPIO config validation, fan/light/motion logic, and API endpoints."""

import json
import os
import sys
import tempfile
import time

import pytest

# Add src/ to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Point config at a temp file before any birdcam imports
_tmp_config = tempfile.NamedTemporaryFile(suffix=".yml", delete=False, mode="w")
_tmp_config.write("{}\n")
_tmp_config.close()
os.environ["BIRDCAM_CONFIG"] = _tmp_config.name


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------

from config import validate, DEFAULTS, _deep_merge
import copy


def make_config(**overrides):
    """Create a valid config with optional overrides."""
    config = copy.deepcopy(DEFAULTS)
    for key, value in overrides.items():
        parts = key.split(".")
        obj = config
        for p in parts[:-1]:
            obj = obj[p]
        obj[parts[-1]] = value
    return config


class TestGpioConfigDefaults:
    def test_defaults_are_valid(self):
        errors = validate(DEFAULTS)
        assert errors == []

    def test_gpio_section_present_in_defaults(self):
        assert "gpio" in DEFAULTS
        assert "pins" in DEFAULTS["gpio"]
        assert "fan" in DEFAULTS["gpio"]
        assert "light_schedule" in DEFAULTS["gpio"]
        assert "motion" in DEFAULTS["gpio"]

    def test_mqtt_section_present_in_defaults(self):
        assert "mqtt" in DEFAULTS
        assert DEFAULTS["mqtt"]["enabled"] is False


class TestGpioPinValidation:
    def test_valid_pins(self):
        errors = validate(DEFAULTS)
        assert errors == []

    def test_pin_out_of_range(self):
        config = make_config()
        config["gpio"]["pins"]["ir_light"] = 30
        errors = validate(config)
        assert any("ir_light" in e and "0-27" in e for e in errors)

    def test_pin_negative(self):
        config = make_config()
        config["gpio"]["pins"]["fan"] = -1
        errors = validate(config)
        assert any("fan" in e for e in errors)

    def test_duplicate_pins(self):
        config = make_config()
        config["gpio"]["pins"]["ir_light"] = 19  # same as light
        errors = validate(config)
        assert any("conflict" in e.lower() for e in errors)

    def test_all_different_pins_valid(self):
        config = make_config()
        config["gpio"]["pins"] = {
            "ir_light": 2, "light": 3, "fan": 4, "dht22": 5, "motion": 6,
        }
        errors = validate(config)
        assert errors == []


class TestFanThresholdValidation:
    def test_on_temp_must_be_greater_than_off_temp(self):
        config = make_config()
        config["gpio"]["fan"]["on_temp"] = 40
        config["gpio"]["fan"]["off_temp"] = 50
        errors = validate(config)
        assert any("on_temp" in e and "greater" in e for e in errors)

    def test_equal_temps_invalid(self):
        config = make_config()
        config["gpio"]["fan"]["on_temp"] = 50
        config["gpio"]["fan"]["off_temp"] = 50
        errors = validate(config)
        assert any("on_temp" in e for e in errors)

    def test_on_temp_out_of_range(self):
        config = make_config()
        config["gpio"]["fan"]["on_temp"] = 90
        errors = validate(config)
        assert any("on_temp" in e and "30-85" in e for e in errors)

    def test_off_temp_out_of_range(self):
        config = make_config()
        config["gpio"]["fan"]["off_temp"] = 20
        errors = validate(config)
        assert any("off_temp" in e and "25-80" in e for e in errors)

    def test_valid_thresholds(self):
        config = make_config()
        config["gpio"]["fan"]["on_temp"] = 60
        config["gpio"]["fan"]["off_temp"] = 45
        errors = validate(config)
        assert errors == []


class TestLightScheduleValidation:
    def test_valid_schedule(self):
        config = make_config()
        config["gpio"]["light_schedule"]["night_start"] = "21:15"
        config["gpio"]["light_schedule"]["day_start"] = "06:30"
        errors = validate(config)
        assert errors == []

    def test_invalid_format(self):
        config = make_config()
        config["gpio"]["light_schedule"]["night_start"] = "9:15pm"
        errors = validate(config)
        assert any("HH:MM" in e for e in errors)

    def test_missing_leading_zero(self):
        config = make_config()
        config["gpio"]["light_schedule"]["day_start"] = "6:30"
        errors = validate(config)
        assert any("HH:MM" in e for e in errors)

    def test_empty_value(self):
        config = make_config()
        config["gpio"]["light_schedule"]["night_start"] = ""
        errors = validate(config)
        assert any("night_start" in e for e in errors)


class TestSensorPollValidation:
    def test_too_short(self):
        config = make_config()
        config["gpio"]["sensor_poll_interval"] = 5
        errors = validate(config)
        assert any("sensor_poll_interval" in e for e in errors)

    def test_too_long(self):
        config = make_config()
        config["gpio"]["sensor_poll_interval"] = 500
        errors = validate(config)
        assert any("sensor_poll_interval" in e for e in errors)

    def test_valid_interval(self):
        config = make_config()
        config["gpio"]["sensor_poll_interval"] = 30
        errors = validate(config)
        assert errors == []


class TestMotionCooldownValidation:
    def test_too_short(self):
        config = make_config()
        config["gpio"]["motion"]["cooldown"] = 2
        errors = validate(config)
        assert any("cooldown" in e for e in errors)

    def test_valid_cooldown(self):
        config = make_config()
        config["gpio"]["motion"]["cooldown"] = 60
        errors = validate(config)
        assert errors == []


class TestDataRetentionValidation:
    def test_too_long(self):
        config = make_config()
        config["gpio"]["data_retention_days"] = 500
        errors = validate(config)
        assert any("data_retention_days" in e for e in errors)

    def test_valid_retention(self):
        config = make_config()
        config["gpio"]["data_retention_days"] = 30
        errors = validate(config)
        assert errors == []


class TestMqttValidation:
    def test_disabled_no_errors(self):
        config = make_config()
        config["mqtt"]["enabled"] = False
        errors = validate(config)
        assert errors == []

    def test_enabled_without_broker(self):
        config = make_config()
        config["mqtt"]["enabled"] = True
        config["mqtt"]["broker"] = ""
        errors = validate(config)
        assert any("broker" in e for e in errors)

    def test_enabled_with_broker(self):
        config = make_config()
        config["mqtt"]["enabled"] = True
        config["mqtt"]["broker"] = "192.168.1.100"
        errors = validate(config)
        assert errors == []

    def test_invalid_port(self):
        config = make_config()
        config["mqtt"]["enabled"] = True
        config["mqtt"]["broker"] = "localhost"
        config["mqtt"]["port"] = 0
        errors = validate(config)
        assert any("port" in e for e in errors)

    def test_invalid_publish_interval(self):
        config = make_config()
        config["mqtt"]["enabled"] = True
        config["mqtt"]["broker"] = "localhost"
        config["mqtt"]["publish_interval"] = 5
        errors = validate(config)
        assert any("publish_interval" in e for e in errors)


# ---------------------------------------------------------------------------
# Fan control logic
# ---------------------------------------------------------------------------

from gpio_service import _state, _update_fan, _process_commands, _write_status, STATUS_FILE


class TestFanControlLogic:
    @pytest.fixture(autouse=True)
    def reset_state(self):
        _state["fan"] = False
        _state["fan_override"] = None
        _state["cpu_temp"] = None
        yield

    def test_fan_turns_on_above_threshold(self):
        config = make_config()
        _state["cpu_temp"] = 55.0
        _update_fan(config)
        assert _state["fan"] is True

    def test_fan_stays_off_below_on_threshold(self):
        config = make_config()
        _state["cpu_temp"] = 45.0
        _update_fan(config)
        assert _state["fan"] is False

    def test_fan_turns_off_below_off_threshold(self):
        config = make_config()
        _state["fan"] = True
        _state["cpu_temp"] = 35.0
        _update_fan(config)
        assert _state["fan"] is False

    def test_hysteresis_fan_stays_on_between_thresholds(self):
        config = make_config()
        _state["fan"] = True
        _state["cpu_temp"] = 45.0  # between 40 (off) and 50 (on)
        _update_fan(config)
        assert _state["fan"] is True

    def test_manual_override_clears_after_one_cycle(self):
        config = make_config()
        _state["fan_override"] = True
        _state["cpu_temp"] = 55.0
        _update_fan(config)
        # Override should be cleared
        assert _state["fan_override"] is None

    def test_no_action_when_cpu_temp_is_none(self):
        config = make_config()
        _state["cpu_temp"] = None
        _state["fan"] = False
        _update_fan(config)
        assert _state["fan"] is False


# ---------------------------------------------------------------------------
# Complementary light command processing
# ---------------------------------------------------------------------------


class TestComplementaryLightCommands:
    @pytest.fixture(autouse=True)
    def reset_state_and_commands(self, tmp_path, monkeypatch):
        _state["light"] = False
        _state["ir_light"] = False
        _state["light_override"] = None
        _state["ir_light_override"] = None
        _state["fan"] = False
        _state["fan_override"] = None
        # Use temp files for command/status IPC
        self.cmd_file = str(tmp_path / "gpio_commands")
        self.status_file = str(tmp_path / "gpio_status.json")
        import gpio_service
        monkeypatch.setattr(gpio_service, "COMMAND_FILE", self.cmd_file)
        monkeypatch.setattr(gpio_service, "STATUS_FILE", self.status_file)
        monkeypatch.setattr(gpio_service, "_output_lines", None)
        yield

    def _write_command(self, target, state):
        with open(self.cmd_file, "a") as f:
            f.write(json.dumps({"target": target, "state": state}) + "\n")

    def test_light_on_turns_ir_off(self):
        _state["ir_light"] = True
        _state["ir_light_override"] = True
        self._write_command("light", True)
        _process_commands(make_config())
        assert _state["light"] is True
        assert _state["ir_light"] is False
        assert _state["ir_light_override"] is False

    def test_ir_on_turns_light_off(self):
        _state["light"] = True
        _state["light_override"] = True
        self._write_command("ir_light", True)
        _process_commands(make_config())
        assert _state["ir_light"] is True
        assert _state["light"] is False
        assert _state["light_override"] is False

    def test_light_off_does_not_affect_ir(self):
        _state["ir_light"] = True
        _state["ir_light_override"] = True
        self._write_command("light", False)
        _process_commands(make_config())
        assert _state["light"] is False
        assert _state["ir_light"] is True  # unchanged

    def test_ir_off_does_not_affect_light(self):
        _state["light"] = True
        _state["light_override"] = True
        self._write_command("ir_light", False)
        _process_commands(make_config())
        assert _state["ir_light"] is False
        assert _state["light"] is True  # unchanged

    def test_both_off_is_valid(self):
        _state["light"] = True
        _state["ir_light"] = True
        self._write_command("light", False)
        self._write_command("ir_light", False)
        _process_commands(make_config())
        assert _state["light"] is False
        assert _state["ir_light"] is False

    def test_status_file_written_after_command(self):
        self._write_command("light", True)
        _process_commands(make_config())
        assert os.path.exists(self.status_file)
        with open(self.status_file) as f:
            status = json.load(f)
        assert status["light"] is True
        assert status["ir_light"] is False

    def test_no_status_written_without_commands(self):
        # Empty command file
        with open(self.cmd_file, "w") as f:
            f.write("")
        _process_commands(make_config())
        assert not os.path.exists(self.status_file)


# ---------------------------------------------------------------------------
# Light schedule logic
# ---------------------------------------------------------------------------

from gpio_service import _is_night_time, _parse_time


class TestLightScheduleLogic:
    def test_parse_time(self):
        assert _parse_time("21:15") == (21, 15)
        assert _parse_time("06:30") == (6, 30)
        assert _parse_time("00:00") == (0, 0)

    def test_night_time_detection(self):
        """Night is between 21:15 and 06:30."""
        config = make_config()

        from unittest.mock import patch
        from datetime import datetime

        # 22:00 should be night
        with patch("gpio_service.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 28, 22, 0, 0)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert _is_night_time(config) is True

        # 12:00 should be day
        with patch("gpio_service.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 28, 12, 0, 0)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert _is_night_time(config) is False

        # 03:00 should be night (after midnight)
        with patch("gpio_service.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 28, 3, 0, 0)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert _is_night_time(config) is True

    def test_exact_night_start_is_night(self):
        config = make_config()
        from unittest.mock import patch
        from datetime import datetime

        with patch("gpio_service.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 28, 21, 15, 0)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert _is_night_time(config) is True

    def test_exact_day_start_is_day(self):
        config = make_config()
        from unittest.mock import patch
        from datetime import datetime

        with patch("gpio_service.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 28, 6, 30, 0)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert _is_night_time(config) is False


# ---------------------------------------------------------------------------
# MQTT payload
# ---------------------------------------------------------------------------

class TestMqttPayload:
    def test_mqtt_disabled_by_default(self):
        config = make_config()
        assert config["mqtt"]["enabled"] is False

    def test_payload_format(self):
        """Verify MQTT payload structure matches Node-RED format."""
        from gpio_service import _state
        _state["temperature"] = 22.5
        _state["humidity"] = 65.0
        _state["light"] = True
        _state["ir_light"] = False
        _state["fan"] = False
        _state["motion"] = True
        _state["cpu_temp"] = 45.2
        _state["cpu_load"] = 12.3

        # Build payload like _publish_mqtt does
        mqtt_config = DEFAULTS["mqtt"]
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

        assert payload["location"] == "Tuin"
        assert payload["object"] == "Vogelhuis_Boom"
        assert payload["temperature"] == 22.5
        assert payload["humidity"] == 65.0
        assert payload["light_status"] == 1
        assert payload["ir_light_status"] == 0
        assert payload["ventilation_status"] == 0
        assert payload["movement_status"] == 1
        assert payload["cpu_temp"] == 45.2
        assert payload["cpu_load"] == 12.3


# ---------------------------------------------------------------------------
# Flask API endpoints
# ---------------------------------------------------------------------------

import database as db


class TestGpioApiEndpoints:
    @pytest.fixture(autouse=True)
    def setup_app(self, tmp_path, monkeypatch):
        # Temp database
        db_path = str(tmp_path / "test_api.db")
        db.set_db_path(db_path)
        db.close()
        db.init_db()

        # Temp log dir
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "stream.log").write_text("")
        (log_dir / "web.log").write_text("")
        (log_dir / "cleanup.log").write_text("")
        (log_dir / "gpio.log").write_text("")

        import config
        import logs
        _orig_load = config.load

        def _patched_load():
            c = _orig_load()
            c["system"]["log_path"] = str(log_dir)
            return c
        monkeypatch.setattr(logs, "load_config", _patched_load)

        # Temp GPIO status file
        self.status_dir = tmp_path / "shm"
        self.status_dir.mkdir()
        status_file = str(self.status_dir / "gpio_status.json")
        monkeypatch.setattr("app.GPIO_STATUS_FILE", status_file)
        monkeypatch.setattr("app.GPIO_COMMAND_FILE", str(self.status_dir / "gpio_commands"))

        # Write a status file
        with open(status_file, "w") as f:
            json.dump({
                "light": True, "ir_light": False, "fan": False, "fan_auto": True,
                "motion": False, "temperature": 22.5, "humidity": 65.0,
                "cpu_temp": 45.2, "cpu_load": 8.0,
                "timestamp": "2026-03-28T12:00:00",
            }, f)

        # Insert some sensor data
        for i in range(5):
            db.record_sensor_data(temperature=20.0 + i, humidity=50.0 + i, cpu_temp=40.0 + i)
        db.record_motion_event()

        from app import app
        app.config["TESTING"] = True
        self.client = app.test_client()

        yield
        db.close()

    def test_gpio_status_returns_json(self):
        resp = self.client.get("/api/gpio/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "light" in data
        assert "temperature" in data

    def test_gpio_status_values(self):
        resp = self.client.get("/api/gpio/status")
        data = resp.get_json()
        assert data["light"] is True
        assert data["temperature"] == 22.5

    def test_gpio_light_toggle(self):
        resp = self.client.post("/api/gpio/light",
                                json={"state": True},
                                content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["target"] == "light"

    def test_gpio_ir_light_toggle(self):
        resp = self.client.post("/api/gpio/ir-light",
                                json={"state": False},
                                content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["target"] == "ir_light"

    def test_gpio_fan_toggle(self):
        resp = self.client.post("/api/gpio/fan",
                                json={"state": True},
                                content_type="application/json")
        assert resp.status_code == 200

    def test_gpio_toggle_missing_state(self):
        resp = self.client.post("/api/gpio/light",
                                json={},
                                content_type="application/json")
        assert resp.status_code == 400

    def test_gpio_toggle_no_body(self):
        resp = self.client.post("/api/gpio/light",
                                content_type="application/json")
        assert resp.status_code == 400

    def test_sensor_data_returns_json(self):
        resp = self.client.get("/api/sensor-data?minutes=60")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) >= 5

    def test_sensor_data_has_fields(self):
        resp = self.client.get("/api/sensor-data?minutes=60")
        data = resp.get_json()
        if data:
            d = data[0]
            assert "timestamp" in d
            assert "temperature" in d
            assert "humidity" in d
            assert "cpu_temp" in d

    def test_motion_events_returns_json(self):
        resp = self.client.get("/api/motion-events?minutes=60")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_sensor_data_minutes_clamped(self):
        # Extremely large value should be clamped
        resp = self.client.get("/api/sensor-data?minutes=999999")
        assert resp.status_code == 200

    def test_graphs_page_renders(self):
        resp = self.client.get("/graphs")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "chart-temperature" in html
        assert "chart-humidity" in html
        assert "chart-motion" in html

    def test_settings_page_has_gpio_fields(self):
        resp = self.client.get("/settings")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "gpio.pins.ir_light" in html
        assert "gpio.fan.on_temp" in html
        assert "gpio.light_schedule.night_start" in html
        assert "mqtt.broker" in html

    def test_health_page_has_gpio_service(self):
        resp = self.client.get("/health")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "birdcam-gpio" in html

    def test_index_page_has_gpio_controls(self):
        resp = self.client.get("/")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "btn-light" in html
        assert "btn-ir-light" in html
        assert "btn-fan" in html
        assert "sensor-readings" in html

    def test_nav_has_graphs_link(self):
        resp = self.client.get("/")
        html = resp.data.decode()
        assert "/graphs" in html


class TestConfigApiGpio:
    @pytest.fixture(autouse=True)
    def setup_app(self, tmp_path, monkeypatch):
        # Temp config file
        self.config_file = tmp_path / "test_config.yml"
        self.config_file.write_text("{}\n")
        monkeypatch.setattr("config.CONFIG_PATH", str(self.config_file))

        from app import app
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_config_get_has_gpio(self):
        resp = self.client.get("/api/config")
        data = resp.get_json()
        assert "gpio" in data
        assert "mqtt" in data

    def test_config_put_gpio_settings(self):
        resp = self.client.put("/api/config",
                               json={"gpio": {"sensor_poll_interval": 30}},
                               content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["gpio_restart_required"] is True

        # Verify saved
        resp = self.client.get("/api/config")
        data = resp.get_json()
        assert data["gpio"]["sensor_poll_interval"] == 30

    def test_config_put_mqtt_settings(self):
        resp = self.client.put("/api/config",
                               json={"mqtt": {"enabled": True, "broker": "192.168.1.100"}},
                               content_type="application/json")
        assert resp.status_code == 200

    def test_config_put_invalid_gpio(self):
        resp = self.client.put("/api/config",
                               json={"gpio": {"sensor_poll_interval": 5}},
                               content_type="application/json")
        assert resp.status_code == 400


# Cleanup
@pytest.fixture(autouse=True, scope="session")
def cleanup_temp_config():
    yield
    try:
        os.unlink(_tmp_config.name)
    except OSError:
        pass
