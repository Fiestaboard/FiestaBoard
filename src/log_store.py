"""The application log store: the in-memory ring, the JSON file handlers,
and the reader ``GET /logs`` serves.

Extracted from ``src/api_server.py`` (Phase 2 Task 8). It lived there only
because the log handlers are installed at app import; nothing about reading a
log page needs the route table, and the debug router could not read one
without dragging the whole 10k-line module back in.

``src/api_server.py`` re-exports every name below under the identity it had
before the move, so ``api_server.LOG_DIR = tmp`` and
``patch("src.api_server._read_logs_from_files")`` still resolve — with one
exception: ``LOG_DIR`` is a *rebindable* module global, so a test that sets
``api_server.LOG_DIR`` is setting a name this module never reads. Set
``src.log_store.LOG_DIR`` instead.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import threading
from collections import deque
from pathlib import Path
from typing import Any

from .paths import get_data_dir

logger = logging.getLogger(__name__)


# Log file configuration.
#
# ``LOG_DIR`` is a *test seam* in the same shape as ``SYSTEM_UPDATE_STATE_FILE``
# further down: production leaves it ``None`` and ``_log_dir()`` resolves
# ``<data>/logs`` lazily through ``src.paths.get_data_dir()`` (honoring
# ``FIESTABOARD_DATA_DIR``, #1762). It was previously the hard-coded container
# path ``/app/data/logs``, which bypassed the seam entirely and made the test
# suite write ``data/logs/app.log`` into the checkout on every run (#1881).
#
# Resolve at call time, never at import time: import-time resolution is what
# created this class of bug (#1894).
LOG_DIR: Path | None = None
LOG_MAX_BYTES = 5 * 1024 * 1024  # 5MB per file
LOG_BACKUP_COUNT = 5  # Keep 5 backup files (25MB total max)


def _log_dir() -> Path:
    """Resolve the log directory, honoring the ``LOG_DIR`` test seam."""
    return LOG_DIR if LOG_DIR is not None else get_data_dir() / "logs"


def _log_file() -> Path:
    """Resolve the current log file (``<data>/logs/app.log``)."""
    return _log_dir() / "app.log"


# In-memory log buffer (last 500 log entries for quick access)
_log_buffer: deque = deque(maxlen=500)
_log_lock = threading.Lock()


def _create_log_entry(record: logging.LogRecord, formatted_message: str) -> dict[str, Any]:
    """Create a structured log entry from a log record with UTC timestamp."""
    from .time_service import get_time_service

    time_service = get_time_service()

    return {
        "timestamp": time_service.create_utc_timestamp(),
        "level": record.levelname,
        "logger": record.name,
        "message": formatted_message,
    }


class LogBufferHandler(logging.Handler):
    """Custom logging handler that stores logs in memory for API access."""

    def emit(self, record):
        try:
            log_entry = _create_log_entry(record, self.format(record))
            with _log_lock:
                _log_buffer.append(log_entry)
        except Exception:
            self.handleError(record)


class JSONFileHandler(logging.handlers.RotatingFileHandler):
    """Rotating file handler that writes logs as JSON lines."""

    def emit(self, record):
        try:
            log_entry = _create_log_entry(record, self.format(record))
            # Write as JSON line
            msg = json.dumps(log_entry) + "\n"
            stream = self.stream
            stream.write(msg)
            self.flush()
            # Handle rotation
            if self.shouldRollover(record):
                self.doRollover()
        except Exception:
            self.handleError(record)

    def shouldRollover(self, record):
        """Check if we should rollover based on file size."""
        if self.stream is None:
            self.stream = self._open()
        if self.maxBytes > 0:
            self.stream.seek(0, 2)  # Seek to end
            if self.stream.tell() >= self.maxBytes:
                return True
        return False


def _setup_file_logging():
    """Set up file-based logging with rotation."""
    try:
        # Create logs directory if it doesn't exist
        log_file = _log_file()
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # Create JSON file handler with rotation
        file_handler = JSONFileHandler(
            str(log_file), maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8"
        )
        file_handler.setFormatter(logging.Formatter("%(message)s"))
        file_handler.setLevel(logging.INFO)

        # Add to root logger
        logging.getLogger().addHandler(file_handler)
        logger.info(f"File logging initialized: {log_file}")
    except Exception as e:
        logger.warning(f"Failed to set up file logging: {e}")


def _read_logs_from_files(
    limit: int = 100, offset: int = 0, level: str | None = None, search: str | None = None
) -> tuple[list[dict[str, Any]], int, bool]:
    """
    Read logs from log files with filtering and pagination.

    Returns: (logs, total_matching, has_more)
    """
    all_logs = []

    # Read from current log file and backups
    current_log = _log_file()
    log_files = [current_log]
    for i in range(1, LOG_BACKUP_COUNT + 1):
        backup_file = Path(f"{current_log}.{i}")
        if backup_file.exists():
            log_files.append(backup_file)

    # Read all log entries from files (newest first)
    for log_file in log_files:
        if not log_file.exists():
            continue
        try:
            with open(log_file, encoding="utf-8") as f:
                lines = f.readlines()
                for line in reversed(lines):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        all_logs.append(entry)
                    except json.JSONDecodeError:
                        continue
        except Exception:
            continue

    # Also include in-memory buffer (most recent)
    with _log_lock:
        memory_logs = list(_log_buffer)

    # Merge: memory logs are most recent, then file logs
    # Deduplicate by timestamp + message
    seen = set()
    merged_logs = []

    for log in reversed(memory_logs):
        key = (log.get("timestamp"), log.get("message"))
        if key not in seen:
            seen.add(key)
            merged_logs.append(log)

    for log in all_logs:
        key = (log.get("timestamp"), log.get("message"))
        if key not in seen:
            seen.add(key)
            merged_logs.append(log)

    # Apply filters
    filtered_logs = merged_logs

    if level:
        level_upper = level.upper()
        filtered_logs = [log for log in filtered_logs if log.get("level") == level_upper]

    if search:
        search_lower = search.lower()
        filtered_logs = [
            log
            for log in filtered_logs
            if search_lower in log.get("message", "").lower() or search_lower in log.get("logger", "").lower()
        ]

    total_matching = len(filtered_logs)

    # Apply pagination
    start = offset
    end = offset + limit
    paginated = filtered_logs[start:end]
    has_more = end < total_matching

    return paginated, total_matching, has_more
