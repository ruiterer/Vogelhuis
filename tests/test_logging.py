"""Tests for the Birdcam logging system."""

import json
import os
import sys
import tempfile
import time

import pytest

# Add src/ to path so imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Point config at a temp file before any birdcam imports
_tmp_config = tempfile.NamedTemporaryFile(suffix=".yml", delete=False, mode="w")
_tmp_config.write("{}\n")
_tmp_config.close()
os.environ["BIRDCAM_CONFIG"] = _tmp_config.name

from logging_setup import SOURCE_FILE_MAP, get_logger
from logs import (
    STRUCTURED_RE,
    _parse_line,
    _read_log_file,
    _cache,
    get_logs,
    get_sources,
)


# ---------------------------------------------------------------------------
# logging_setup
# ---------------------------------------------------------------------------

class TestSourceRegistry:
    """SOURCE_FILE_MAP is the single source of truth for log sources."""

    def test_known_sources_present(self):
        expected = {"stream", "web", "cleanup", "snapshot", "health", "config"}
        assert expected == set(SOURCE_FILE_MAP.keys())

    def test_all_values_are_log_filenames(self):
        for source, filename in SOURCE_FILE_MAP.items():
            assert filename.endswith(".log"), f"{source} → {filename}"

    def test_sub_modules_share_web_log(self):
        for sub in ("snapshot", "health", "config"):
            assert SOURCE_FILE_MAP[sub] == "web.log"


class TestGetLogger:
    def test_returns_logger_with_source_name(self):
        log = get_logger("testmod")
        assert log.name == "birdcam.testmod"

    def test_logger_writes_structured_format(self, capsys):
        log = get_logger("fmttest")
        log.info("hello world")
        line = capsys.readouterr().err.strip()
        assert STRUCTURED_RE.match(line), f"Line does not match format: {line!r}"
        m = STRUCTURED_RE.match(line)
        assert m.group(2) == "INFO"
        assert m.group(3) == "fmttest"
        assert m.group(4) == "hello world"

    def test_warning_renamed_to_warn(self, capsys):
        log = get_logger("warntest")
        log.warning("something off")
        line = capsys.readouterr().err.strip()
        assert "[WARN]" in line
        assert "[WARNING]" not in line

    def test_critical_renamed_to_error(self, capsys):
        log = get_logger("crittest")
        log.critical("bad stuff")
        line = capsys.readouterr().err.strip()
        assert "[ERROR]" in line

    def test_idempotent_no_duplicate_handlers(self, capsys):
        get_logger("dupetest")
        get_logger("dupetest")
        log = get_logger("dupetest")
        log.info("once")
        lines = capsys.readouterr().err.strip().split("\n")
        assert len(lines) == 1


# ---------------------------------------------------------------------------
# logs._parse_line
# ---------------------------------------------------------------------------

class TestParseLine:
    def test_structured_line(self):
        line = "2026-03-20 14:30:00 [INFO] [web] Server started"
        result = _parse_line(line, "web")
        assert result["timestamp"] == "2026-03-20 14:30:00"
        assert result["level"] == "INFO"
        assert result["source"] == "web"
        assert result["message"] == "Server started"
        assert result["unstructured"] is False

    def test_structured_warn(self):
        line = "2026-03-20 14:30:00 [WARN] [stream] Camera stale"
        result = _parse_line(line, "stream")
        assert result["level"] == "WARN"
        assert result["unstructured"] is False

    def test_unstructured_line_gets_timestamp(self):
        line = "Some random ffmpeg output"
        result = _parse_line(line, "stream")
        assert result["unstructured"] is True
        assert result["timestamp"] != ""
        # Should be a valid timestamp
        assert STRUCTURED_RE.match(
            f'{result["timestamp"]} [INFO] [x] test'
        )

    def test_unstructured_error_detection(self):
        line = "ffmpeg: error while loading shared libraries"
        result = _parse_line(line, "stream")
        assert result["level"] == "ERROR"
        assert result["unstructured"] is True

    def test_unstructured_warn_detection(self):
        line = "deprecated pixel format used, make sure you set the warning"
        result = _parse_line(line, "stream")
        assert result["level"] == "WARN"

    def test_empty_line_returns_none(self):
        assert _parse_line("", "web") is None
        assert _parse_line("   \n", "web") is None


# ---------------------------------------------------------------------------
# logs._read_log_file  (with caching)
# ---------------------------------------------------------------------------

class TestReadLogFile:
    def test_nonexistent_file_returns_empty(self, tmp_path):
        result = _read_log_file(str(tmp_path / "nope.log"), "test")
        assert result == []

    def test_reads_structured_lines(self, tmp_path):
        log = tmp_path / "test.log"
        log.write_text(
            "2026-03-20 14:00:00 [INFO] [web] line one\n"
            "2026-03-20 14:00:01 [WARN] [web] line two\n"
        )
        entries = _read_log_file(str(log), "web")
        assert len(entries) == 2
        assert entries[0]["level"] == "INFO"
        assert entries[1]["level"] == "WARN"

    def test_caching_returns_same_result(self, tmp_path):
        log = tmp_path / "cached.log"
        log.write_text("2026-03-20 14:00:00 [INFO] [web] cached\n")
        path = str(log)

        entries1 = _read_log_file(path, "web")
        entries2 = _read_log_file(path, "web")
        assert entries1 is entries2  # same object from cache

    def test_cache_invalidated_on_mtime_change(self, tmp_path):
        log = tmp_path / "changing.log"
        log.write_text("2026-03-20 14:00:00 [INFO] [web] v1\n")
        path = str(log)

        entries1 = _read_log_file(path, "web")
        assert len(entries1) == 1

        # Ensure mtime changes (filesystem granularity)
        time.sleep(0.05)
        log.write_text(
            "2026-03-20 14:00:00 [INFO] [web] v1\n"
            "2026-03-20 14:00:01 [INFO] [web] v2\n"
        )
        # Force different mtime
        os.utime(path, (time.time() + 1, time.time() + 1))

        entries2 = _read_log_file(path, "web")
        assert len(entries2) == 2

    def test_max_lines_limits_output(self, tmp_path):
        log = tmp_path / "big.log"
        lines = [f"2026-03-20 14:00:{i:02d} [INFO] [web] line {i}\n" for i in range(50)]
        log.write_text("".join(lines))
        entries = _read_log_file(str(log), "web", max_lines=10)
        assert len(entries) == 10
        # Should be the LAST 10 lines
        assert entries[-1]["message"] == "line 49"


# ---------------------------------------------------------------------------
# logs.get_sources
# ---------------------------------------------------------------------------

class TestGetSources:
    def test_returns_sorted_list(self):
        sources = get_sources()
        assert sources == sorted(sources)
        assert "stream" in sources
        assert "web" in sources
        assert "snapshot" in sources

    def test_contains_all_registry_keys(self):
        assert set(get_sources()) == set(SOURCE_FILE_MAP.keys())


# ---------------------------------------------------------------------------
# logs.get_logs  (integration-level)
# ---------------------------------------------------------------------------

class TestGetLogs:
    @pytest.fixture(autouse=True)
    def setup_log_dir(self, tmp_path, monkeypatch):
        """Create temp log files and point config at them."""
        self.log_dir = tmp_path

        # Write structured log entries
        (tmp_path / "stream.log").write_text(
            "2026-03-20 14:00:00 [INFO] [stream] Stream starting\n"
            "2026-03-20 14:00:01 [WARN] [stream] Camera slow\n"
            "Some rpicam-vid unstructured output\n"
        )
        (tmp_path / "web.log").write_text(
            "2026-03-20 14:00:00 [INFO] [web] Server started\n"
            "2026-03-20 14:00:02 [INFO] [snapshot] Snapshot captured: test.jpg\n"
            "2026-03-20 14:00:03 [ERROR] [health] HLS playlist stale\n"
            "2026-03-20 14:00:04 [INFO] [config] Configuration saved\n"
        )
        (tmp_path / "cleanup.log").write_text(
            "2026-03-20 14:00:05 [INFO] [cleanup] Cleanup complete\n"
        )

        # Patch the bound reference in logs module (not config module)
        import config
        import logs
        _orig_load = config.load
        def _patched_load():
            c = _orig_load()
            c["system"]["log_path"] = str(tmp_path)
            return c
        monkeypatch.setattr(logs, "load_config", _patched_load)

        # Clear cache between tests
        _cache.clear()

    def test_all_sources_returned_by_default(self):
        entries = get_logs()
        sources = {e["source"] for e in entries}
        assert "stream" in sources
        assert "web" in sources
        assert "cleanup" in sources

    def test_filter_by_source_stream(self):
        entries = get_logs(source="stream")
        assert all(e["source"] == "stream" for e in entries)

    def test_filter_by_source_snapshot(self):
        entries = get_logs(source="snapshot")
        assert len(entries) == 1
        assert entries[0]["source"] == "snapshot"
        assert "Snapshot captured" in entries[0]["message"]

    def test_filter_by_source_health(self):
        entries = get_logs(source="health")
        assert len(entries) == 1
        assert entries[0]["level"] == "ERROR"

    def test_filter_by_source_config(self):
        entries = get_logs(source="config")
        assert len(entries) == 1
        assert "Configuration saved" in entries[0]["message"]

    def test_filter_by_level_warn(self):
        entries = get_logs(level="WARN")
        assert all(e["level"] in ("WARN", "ERROR") for e in entries)

    def test_filter_by_level_error(self):
        entries = get_logs(level="ERROR")
        assert all(e["level"] == "ERROR" for e in entries)

    def test_verbose_false_hides_unstructured(self):
        entries = get_logs(verbose=False)
        assert not any(e["unstructured"] for e in entries)

    def test_verbose_true_shows_unstructured(self):
        entries = get_logs(verbose=True)
        unstructured = [e for e in entries if e["unstructured"]]
        assert len(unstructured) > 0
        # Unstructured lines should have a timestamp
        for e in unstructured:
            assert e["timestamp"] != ""

    def test_chronological_sort(self):
        entries = get_logs()
        timestamps = [e["timestamp"] for e in entries]
        assert timestamps == sorted(timestamps)

    def test_time_filter(self):
        # All our test entries are from 2026 — minutes filter against "now"
        # should return nothing (entries are in the past)
        entries = get_logs(minutes=1)
        assert len(entries) == 0

    def test_max_lines(self):
        entries = get_logs(max_lines=2)
        assert len(entries) <= 2

    def test_unknown_source_returns_all(self):
        entries = get_logs(source="nonexistent")
        # Unknown source not in registry → returns all
        assert len(entries) > 0


# ---------------------------------------------------------------------------
# Integration: modules get distinct loggers
# ---------------------------------------------------------------------------

class TestModuleLoggers:
    def test_each_module_has_own_logger(self):
        from logging_setup import get_logger
        web = get_logger("web")
        snap = get_logger("snapshot")
        health = get_logger("health")
        assert web.name != snap.name != health.name

    def test_config_module_has_logger(self):
        import config
        assert hasattr(config, "logger")
        assert config.logger.name == "birdcam.config"

    def test_snapshot_module_has_logger(self):
        import snapshot
        assert hasattr(snapshot, "logger")
        assert snapshot.logger.name == "birdcam.snapshot"

    def test_health_module_has_logger(self):
        import health
        assert hasattr(health, "logger")
        assert health.logger.name == "birdcam.health"


# ---------------------------------------------------------------------------
# Integration: Flask API
# ---------------------------------------------------------------------------

class TestFlaskLogAPI:
    @pytest.fixture(autouse=True)
    def setup_app(self, tmp_path, monkeypatch):
        self.log_dir = tmp_path

        (tmp_path / "stream.log").write_text(
            "2026-03-20 14:00:00 [INFO] [stream] Stream started\n"
        )
        (tmp_path / "web.log").write_text(
            "2026-03-20 14:00:01 [INFO] [web] Ready\n"
            "2026-03-20 14:00:02 [INFO] [snapshot] Snap taken\n"
        )
        (tmp_path / "cleanup.log").write_text("")

        import config
        import logs
        _orig_load = config.load
        def _patched_load():
            c = _orig_load()
            c["system"]["log_path"] = str(tmp_path)
            return c
        monkeypatch.setattr(logs, "load_config", _patched_load)
        _cache.clear()

        from app import app
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_api_logs_returns_json(self):
        resp = self.client.get("/api/logs")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_api_logs_source_filter(self):
        resp = self.client.get("/api/logs?source=snapshot")
        data = resp.get_json()
        assert all(e["source"] == "snapshot" for e in data)

    def test_api_logs_verbose_param(self):
        resp = self.client.get("/api/logs?verbose=1")
        data = resp.get_json()
        assert isinstance(data, list)

    def test_api_logs_entries_have_required_fields(self):
        resp = self.client.get("/api/logs")
        data = resp.get_json()
        for entry in data:
            assert "timestamp" in entry
            assert "level" in entry
            assert "source" in entry
            assert "message" in entry
            assert "unstructured" in entry

    def test_api_logs_chronological_order(self):
        resp = self.client.get("/api/logs")
        data = resp.get_json()
        timestamps = [e["timestamp"] for e in data]
        assert timestamps == sorted(timestamps)

    def test_health_page_renders(self):
        resp = self.client.get("/health")
        assert resp.status_code == 200
        html = resp.data.decode()
        # Should contain dynamically populated source options
        assert "snapshot" in html.lower()
        assert "health" in html.lower()


# ---------------------------------------------------------------------------
# Cleanup temp config
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True, scope="session")
def cleanup_temp_config():
    yield
    try:
        os.unlink(_tmp_config.name)
    except OSError:
        pass
