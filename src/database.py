"""SQLite database for Birdcam sensor data and motion events."""

import os
import sqlite3
import threading
from datetime import datetime, timedelta

from logging_setup import get_logger

logger = get_logger("gpio")

DEFAULT_DB_PATH = "/var/lib/birdcam/sensor_data.db"
_DB_PATH = os.environ.get("BIRDCAM_DB_PATH", DEFAULT_DB_PATH)

_local = threading.local()


def _get_db_path():
    return _DB_PATH


def set_db_path(path):
    """Override database path (for testing)."""
    global _DB_PATH
    _DB_PATH = path


def _get_connection():
    """Return a thread-local database connection."""
    if not hasattr(_local, "conn") or _local.conn is None:
        path = _get_db_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _local.conn = sqlite3.connect(path, timeout=10)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA busy_timeout=5000")
    return _local.conn


def init_db():
    """Create tables if they don't exist."""
    conn = _get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sensor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')),
            temperature REAL,
            humidity REAL,
            cpu_temp REAL,
            cpu_load REAL,
            light_status INTEGER DEFAULT 0,
            ir_light_status INTEGER DEFAULT 0,
            fan_status INTEGER DEFAULT 0,
            motion_status INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS motion_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')),
            duration_seconds REAL
        );

        CREATE INDEX IF NOT EXISTS idx_sensor_data_timestamp ON sensor_data(timestamp);
        CREATE INDEX IF NOT EXISTS idx_motion_events_timestamp ON motion_events(timestamp);
    """)
    conn.commit()
    logger.info("Database initialized")


def record_sensor_data(temperature=None, humidity=None, cpu_temp=None,
                       cpu_load=None, light_status=0, ir_light_status=0,
                       fan_status=0, motion_status=0):
    """Insert a sensor reading."""
    conn = _get_connection()
    conn.execute(
        """INSERT INTO sensor_data
           (timestamp, temperature, humidity, cpu_temp, cpu_load,
            light_status, ir_light_status, fan_status, motion_status)
           VALUES (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime'),
                   ?, ?, ?, ?, ?, ?, ?, ?)""",
        (temperature, humidity, cpu_temp, cpu_load,
         light_status, ir_light_status, fan_status, motion_status),
    )
    conn.commit()


def record_motion_event(duration_seconds=None):
    """Insert a motion event."""
    conn = _get_connection()
    conn.execute(
        """INSERT INTO motion_events (timestamp, duration_seconds)
           VALUES (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime'), ?)""",
        (duration_seconds,),
    )
    conn.commit()


def get_sensor_data(minutes=60):
    """Return sensor records for the last N minutes."""
    conn = _get_connection()
    cutoff = (datetime.now() - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S")
    rows = conn.execute(
        """SELECT timestamp, temperature, humidity, cpu_temp, cpu_load,
                  light_status, ir_light_status, fan_status, motion_status
           FROM sensor_data
           WHERE timestamp >= ?
           ORDER BY timestamp ASC""",
        (cutoff,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_motion_events(minutes=60):
    """Return motion events for the last N minutes."""
    conn = _get_connection()
    cutoff = (datetime.now() - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S")
    rows = conn.execute(
        """SELECT timestamp, duration_seconds
           FROM motion_events
           WHERE timestamp >= ?
           ORDER BY timestamp ASC""",
        (cutoff,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_latest_reading():
    """Return the most recent sensor record, or None."""
    conn = _get_connection()
    row = conn.execute(
        """SELECT timestamp, temperature, humidity, cpu_temp, cpu_load,
                  light_status, ir_light_status, fan_status, motion_status
           FROM sensor_data
           ORDER BY id DESC LIMIT 1"""
    ).fetchone()
    return dict(row) if row else None


def cleanup_old_data(retention_days=30):
    """Delete records older than retention_days."""
    conn = _get_connection()
    cutoff = (datetime.now() - timedelta(days=retention_days)).strftime("%Y-%m-%dT%H:%M:%S")
    r1 = conn.execute("DELETE FROM sensor_data WHERE timestamp < ?", (cutoff,))
    r2 = conn.execute("DELETE FROM motion_events WHERE timestamp < ?", (cutoff,))
    conn.commit()
    total = r1.rowcount + r2.rowcount
    if total > 0:
        logger.info("Cleaned up %d old records (retention: %d days)", total, retention_days)
    return total


def close():
    """Close the thread-local connection."""
    if hasattr(_local, "conn") and _local.conn:
        _local.conn.close()
        _local.conn = None
