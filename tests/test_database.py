"""Tests for the Birdcam sensor database."""

import os
import sqlite3
import sys
import tempfile
import threading
import time

import pytest

# Add src/ to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Point config at a temp file before any birdcam imports
_tmp_config = tempfile.NamedTemporaryFile(suffix=".yml", delete=False, mode="w")
_tmp_config.write("{}\n")
_tmp_config.close()
os.environ["BIRDCAM_CONFIG"] = _tmp_config.name

import database as db


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    """Use a temporary database for each test."""
    db_path = str(tmp_path / "test_sensor.db")
    db.set_db_path(db_path)
    db.close()  # Clear any existing thread-local connection
    db.init_db()
    yield db_path
    db.close()


class TestSchemaCreation:
    def test_tables_created(self, temp_db):
        conn = sqlite3.connect(temp_db)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {t[0] for t in tables}
        assert "sensor_data" in table_names
        assert "motion_events" in table_names
        conn.close()

    def test_indexes_created(self, temp_db):
        conn = sqlite3.connect(temp_db)
        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
        index_names = {i[0] for i in indexes}
        assert "idx_sensor_data_timestamp" in index_names
        assert "idx_motion_events_timestamp" in index_names
        conn.close()

    def test_wal_mode_enabled(self, temp_db):
        conn = sqlite3.connect(temp_db)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"
        conn.close()

    def test_idempotent_init(self, temp_db):
        # Calling init_db again should not fail
        db.init_db()
        db.init_db()


class TestRecordSensorData:
    def test_insert_basic(self):
        db.record_sensor_data(temperature=22.5, humidity=65.0, cpu_temp=45.2, cpu_load=12.3)
        latest = db.get_latest_reading()
        assert latest is not None
        assert latest["temperature"] == 22.5
        assert latest["humidity"] == 65.0
        assert latest["cpu_temp"] == 45.2
        assert latest["cpu_load"] == 12.3

    def test_insert_with_status_flags(self):
        db.record_sensor_data(
            temperature=20.0, humidity=50.0,
            light_status=1, ir_light_status=0, fan_status=1, motion_status=0,
        )
        latest = db.get_latest_reading()
        assert latest["light_status"] == 1
        assert latest["ir_light_status"] == 0
        assert latest["fan_status"] == 1
        assert latest["motion_status"] == 0

    def test_insert_with_none_values(self):
        db.record_sensor_data(temperature=None, humidity=None)
        latest = db.get_latest_reading()
        assert latest["temperature"] is None
        assert latest["humidity"] is None

    def test_timestamp_auto_populated(self):
        db.record_sensor_data(temperature=20.0)
        latest = db.get_latest_reading()
        assert latest["timestamp"] is not None
        assert "T" in latest["timestamp"]


class TestRecordMotionEvent:
    def test_insert_motion_event(self):
        db.record_motion_event()
        events = db.get_motion_events(minutes=5)
        assert len(events) >= 1

    def test_insert_with_duration(self):
        db.record_motion_event(duration_seconds=5.2)
        events = db.get_motion_events(minutes=5)
        assert any(e["duration_seconds"] == 5.2 for e in events)

    def test_insert_without_duration(self):
        db.record_motion_event()
        events = db.get_motion_events(minutes=5)
        assert any(e["duration_seconds"] is None for e in events)


class TestGetSensorData:
    def test_returns_correct_time_range(self):
        # Insert some data
        for i in range(5):
            db.record_sensor_data(temperature=20.0 + i)

        data = db.get_sensor_data(minutes=5)
        assert len(data) == 5

    def test_ordered_by_timestamp(self):
        db.record_sensor_data(temperature=20.0)
        db.record_sensor_data(temperature=21.0)
        data = db.get_sensor_data(minutes=5)
        timestamps = [d["timestamp"] for d in data]
        assert timestamps == sorted(timestamps)

    def test_returns_all_fields(self):
        db.record_sensor_data(
            temperature=22.0, humidity=55.0, cpu_temp=42.0, cpu_load=8.0,
            light_status=1, ir_light_status=0, fan_status=0, motion_status=1,
        )
        data = db.get_sensor_data(minutes=5)
        assert len(data) >= 1
        d = data[-1]
        assert "timestamp" in d
        assert "temperature" in d
        assert "humidity" in d
        assert "cpu_temp" in d
        assert "cpu_load" in d
        assert "light_status" in d
        assert "ir_light_status" in d
        assert "fan_status" in d
        assert "motion_status" in d

    def test_empty_database_returns_empty_list(self):
        data = db.get_sensor_data(minutes=60)
        assert data == []


class TestGetMotionEvents:
    def test_returns_events_in_range(self):
        db.record_motion_event()
        db.record_motion_event(duration_seconds=3.0)
        events = db.get_motion_events(minutes=5)
        assert len(events) == 2

    def test_ordered_by_timestamp(self):
        db.record_motion_event()
        db.record_motion_event()
        events = db.get_motion_events(minutes=5)
        timestamps = [e["timestamp"] for e in events]
        assert timestamps == sorted(timestamps)

    def test_empty_returns_empty(self):
        events = db.get_motion_events(minutes=60)
        assert events == []


class TestGetLatestReading:
    def test_returns_most_recent(self):
        db.record_sensor_data(temperature=20.0)
        db.record_sensor_data(temperature=25.0)
        latest = db.get_latest_reading()
        assert latest["temperature"] == 25.0

    def test_returns_none_when_empty(self):
        result = db.get_latest_reading()
        assert result is None


class TestCleanupOldData:
    def test_deletes_nothing_when_all_recent(self):
        db.record_sensor_data(temperature=20.0)
        db.record_motion_event()
        deleted = db.cleanup_old_data(retention_days=30)
        assert deleted == 0

    def test_sensor_data_preserved_when_recent(self):
        db.record_sensor_data(temperature=20.0)
        db.cleanup_old_data(retention_days=30)
        assert db.get_latest_reading() is not None


class TestConcurrentAccess:
    def test_concurrent_read_write(self, temp_db):
        """Verify WAL mode allows concurrent reads during writes."""
        errors = []

        def writer():
            try:
                for i in range(10):
                    db.record_sensor_data(temperature=20.0 + i)
                    time.sleep(0.01)
            except Exception as e:
                errors.append(f"writer: {e}")

        def reader():
            try:
                for _ in range(10):
                    db.get_sensor_data(minutes=5)
                    time.sleep(0.01)
            except Exception as e:
                errors.append(f"reader: {e}")

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=reader)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert errors == [], f"Concurrent access errors: {errors}"


# Cleanup
@pytest.fixture(autouse=True, scope="session")
def cleanup_temp_config():
    yield
    try:
        os.unlink(_tmp_config.name)
    except OSError:
        pass
