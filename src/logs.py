"""Log reading and parsing for Birdcam."""

import os
import re
from datetime import datetime, timedelta

from config import load as load_config
from logging_setup import SOURCE_FILE_MAP

# Matches our structured format: 2026-03-20 14:30:00 [LEVEL] [source] message
STRUCTURED_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[(\w+)\] \[(\w+)\] (.*)$"
)

# mtime-based cache: {filepath: {"mtime": float, "entries": list}}
_cache = {}


def get_sources():
    """Return sorted list of all known source names for UI filter population."""
    return sorted(SOURCE_FILE_MAP.keys())


def _get_log_files():
    """Return {filename: [sources]} mapping derived from the source registry."""
    files = {}
    for source, filename in SOURCE_FILE_MAP.items():
        files.setdefault(filename, []).append(source)
    return files


def _parse_line(line, source_hint):
    """Parse a log line into a structured dict."""
    line = line.rstrip()
    if not line:
        return None

    m = STRUCTURED_RE.match(line)
    if m:
        return {
            "timestamp": m.group(1),
            "level": m.group(2).upper(),
            "source": m.group(3),
            "message": m.group(4),
            "unstructured": False,
        }

    # Unstructured line — detect level from content
    level = "INFO"
    lower = line.lower()
    if "warn" in lower:
        level = "WARN"
    if "error" in lower or "fatal" in lower or "fail" in lower:
        level = "ERROR"

    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "level": level,
        "source": source_hint,
        "message": line,
        "unstructured": True,
    }


def _read_log_file(filepath, source_hint, max_lines=2000):
    """Read and parse a single log file, with mtime-based caching."""
    if not os.path.isfile(filepath):
        return []

    try:
        mtime = os.path.getmtime(filepath)
    except OSError:
        return []

    cached = _cache.get(filepath)
    if cached and cached["mtime"] == mtime:
        return cached["entries"]

    entries = []
    try:
        with open(filepath, "r", errors="replace") as f:
            lines = f.readlines()
            for line in lines[-max_lines:]:
                entry = _parse_line(line, source_hint)
                if entry:
                    entries.append(entry)
    except (PermissionError, OSError):
        entries.append({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "level": "ERROR",
            "source": source_hint,
            "message": f"Could not read {filepath}",
            "unstructured": False,
        })

    _cache[filepath] = {"mtime": mtime, "entries": entries}
    return entries


def get_logs(source=None, level=None, minutes=None, verbose=False, max_lines=500):
    """Fetch log entries with optional filtering.

    Args:
        source: source name (e.g. "stream", "web", "snapshot"), or None for all
        level: "INFO", "WARN", "ERROR", or None for all
        minutes: Only entries from the last N minutes, or None for all
        verbose: If False (default), hide unstructured lines
        max_lines: Maximum entries to return
    """
    config = load_config()
    log_path = config["system"]["log_path"]
    log_files = _get_log_files()

    # Determine which files to read
    if source and source in SOURCE_FILE_MAP:
        # Read the file this source lives in
        filename = SOURCE_FILE_MAP[source]
        files_to_read = {filename: log_files[filename]}
    else:
        files_to_read = log_files

    # Read all requested log files
    all_entries = []
    for filename, sources in files_to_read.items():
        filepath = os.path.join(log_path, filename)
        # Use first source in list as hint for unstructured lines
        all_entries.extend(_read_log_file(filepath, sources[0]))

    # Filter by source (for sub-module sources sharing a file)
    if source and source in SOURCE_FILE_MAP:
        all_entries = [e for e in all_entries if e["source"] == source]

    # Filter out unstructured lines unless verbose
    if not verbose:
        all_entries = [e for e in all_entries if not e["unstructured"]]

    # Filter by level
    if level:
        level_upper = level.upper()
        if level_upper == "WARN":
            all_entries = [e for e in all_entries if e["level"] in ("WARN", "ERROR")]
        elif level_upper == "ERROR":
            all_entries = [e for e in all_entries if e["level"] == "ERROR"]

    # Filter by time period
    if minutes and minutes > 0:
        cutoff = datetime.now() - timedelta(minutes=minutes)
        cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
        all_entries = [e for e in all_entries if e["timestamp"] >= cutoff_str]

    # Sort chronologically (oldest first)
    all_entries.sort(key=lambda e: e["timestamp"])

    return all_entries[-max_lines:]
