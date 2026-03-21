"""Centralized logging setup for Birdcam.

Provides a single get_logger(source) factory and a source registry that maps
source names to log files.  Adding a new source (e.g. a future sensor service)
is a one-line addition to SOURCE_FILE_MAP.
"""

import logging

# Source registry: maps source name → log filename.
# Log files live under the configured system.log_path (default /var/log/birdcam/).
# Multiple sources may share a file (e.g. Flask sub-modules all write to web.log).
SOURCE_FILE_MAP = {
    "stream": "stream.log",
    "web": "web.log",
    "cleanup": "cleanup.log",
    "snapshot": "web.log",
    "health": "web.log",
    "config": "web.log",
}

_configured = set()


class _LevelRenamer(logging.Filter):
    """Rename WARNING → WARN and CRITICAL → ERROR for consistent output."""

    _MAP = {"WARNING": "WARN", "CRITICAL": "ERROR"}

    def filter(self, record):
        record.levelname = self._MAP.get(record.levelname, record.levelname)
        return True


def get_logger(source):
    """Return a logger that writes structured lines to stderr.

    Format: YYYY-MM-DD HH:MM:SS [LEVEL] [source] message
    Systemd captures stderr and appends it to the appropriate log file.
    """
    name = f"birdcam.{source}"
    logger = logging.getLogger(name)

    if name not in _configured:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()  # stderr
        handler.setFormatter(logging.Formatter(
            f"%(asctime)s [%(levelname)s] [{source}] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        handler.addFilter(_LevelRenamer())
        logger.addHandler(handler)
        logger.propagate = False
        _configured.add(name)

    return logger
