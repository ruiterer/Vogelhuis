"""Log reading and parsing for Birdcam."""

import os
import re
from datetime import datetime, timedelta

from config import load as load_config

# Matches our structured format: 2026-03-20 14:30:00 [LEVEL] [source] message
STRUCTURED_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[(\w+)\] \[(\w+)\] (.*)$"
)

LOG_FILES = {
    "stream": "stream.log",
    "web": "web.log",
    "cleanup": "cleanup.log",
}


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
        }

    # Unstructured line — detect level from content
    level = "INFO"
    lower = line.lower()
    if "warn" in lower:
        level = "WARN"
    if "error" in lower or "fatal" in lower or "fail" in lower:
        level = "ERROR"

    return {
        "timestamp": "",
        "level": level,
        "source": source_hint,
        "message": line,
    }


def _read_log_file(filepath, source_hint, max_lines=2000):
    """Read and parse a single log file, returning newest lines first."""
    if not os.path.isfile(filepath):
        return []

    entries = []
    try:
        with open(filepath, "r", errors="replace") as f:
            # Read all lines and take the last max_lines
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
        })

    return entries


def get_logs(source=None, level=None, minutes=None, max_lines=500):
    """Fetch log entries with optional filtering.

    Args:
        source: "stream", "web", "cleanup", or None for all
        level: "INFO", "WARN", "ERROR", or None for all
        minutes: Only entries from the last N minutes, or None for all
        max_lines: Maximum entries to return
    """
    config = load_config()
    log_path = config["system"]["log_path"]

    # Determine which files to read
    if source and source in LOG_FILES:
        files = {source: LOG_FILES[source]}
    else:
        files = LOG_FILES

    # Read all requested log files
    all_entries = []
    for src, filename in files.items():
        filepath = os.path.join(log_path, filename)
        all_entries.extend(_read_log_file(filepath, src))

    # Filter by level
    if level:
        level_upper = level.upper()
        if level_upper == "WARN":
            # WARN includes WARN and ERROR
            all_entries = [e for e in all_entries if e["level"] in ("WARN", "ERROR")]
        elif level_upper == "ERROR":
            all_entries = [e for e in all_entries if e["level"] == "ERROR"]
        # INFO = show all (no filter)

    # Filter by time period
    if minutes and minutes > 0:
        cutoff = datetime.now() - timedelta(minutes=minutes)
        cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
        all_entries = [
            e for e in all_entries
            if e["timestamp"] >= cutoff_str or e["timestamp"] == ""
        ]

    # Sort by timestamp descending (newest first), empty timestamps last
    all_entries.sort(
        key=lambda e: e["timestamp"] if e["timestamp"] else "0",
        reverse=True,
    )

    return all_entries[:max_lines]
