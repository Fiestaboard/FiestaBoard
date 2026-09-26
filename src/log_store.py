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
import os
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


# Reverse-read chunk size. One 64 KB read holds ~250 JSON log lines, so a
# default 50-row page is usually satisfied by a single read() near the end of
# ``app.log``.
_REVERSE_CHUNK_BYTES = 64 * 1024

# How many recently-seen ``(timestamp, message)`` keys the deduplicator
# remembers. The old reader kept one per entry in the whole corpus — 177k
# tuples for a full 33.5 MB log set, and the single largest term in the
# 191.6 MB an unfiltered ``GET /logs?limit=100`` used to allocate.
#
# A window is sufficient because duplicates cannot be far apart in the
# newest-first stream: rotation writes every line to exactly one file, so the
# only pairs that ever collide are an entry in the 500-slot in-memory ring and
# its copy among the newest lines of ``app.log``. Those are at most ~1000
# positions apart; 4096 is an 8x margin over that, and costs well under a
# megabyte.
_DEDUPE_WINDOW = 4096


def _iter_lines_reversed(path: Path, chunk_size: int = _REVERSE_CHUNK_BYTES):
    """Yield a file's lines newest-last-first, reading backwards in chunks.

    The equivalent of ``reversed(f.readlines())`` without the ``readlines()``:
    the caller can stop after a handful of lines and the rest of the file is
    never read. Lines come back as ``bytes``; decoding is the caller's job so
    that one undecodable line does not sink the file.
    """
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        remaining = f.tell()
        # Bytes belonging to a line that started before the current chunk.
        partial = b""
        while remaining > 0:
            read_size = min(chunk_size, remaining)
            remaining -= read_size
            f.seek(remaining)
            parts = (f.read(read_size) + partial).split(b"\n")
            # parts[0] is only a line's tail unless we just read byte 0.
            partial = parts.pop(0)
            yield from reversed(parts)
        if partial:
            yield partial


def _iter_entries_newest_first():
    """Yield log entries newest first, opening as little as possible.

    Order matches what the eager reader produced: the in-memory ring
    (newest first), then ``app.log``, then ``app.log.1`` .. ``app.log.N``,
    each read back to front. Files are opened lazily, so a consumer that
    stops after one page never touches the backups.
    """
    with _log_lock:
        memory_logs = list(_log_buffer)
    yield from reversed(memory_logs)

    current_log = _log_file()
    candidates = [current_log] + [Path(f"{current_log}.{i}") for i in range(1, LOG_BACKUP_COUNT + 1)]

    for log_file in candidates:
        if not log_file.exists():
            continue
        try:
            for raw in _iter_lines_reversed(log_file):
                line = raw.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except (UnicodeDecodeError, ValueError):
                    # Not JSON, or not even UTF-8. Skip the line. The old
                    # reader let a decode error escape ``readlines()`` and
                    # dropped the whole file; reverse reading has already
                    # emitted the newer entries by then, so per-line is both
                    # the only available granularity and the better one.
                    continue
        except Exception:
            # A file that cannot be read never breaks the endpoint, as before.
            continue


def _read_logs_from_files(
    limit: int = 100, offset: int = 0, level: str | None = None, search: str | None = None
) -> tuple[list[dict[str, Any]], int, bool]:
    """
    Read logs from log files with filtering and pagination.

    Returns: (logs, total_matching, has_more)

    Cost is O(offset + limit), not O(bytes on disk): the stream is consumed
    newest first and abandoned one entry past the requested page.
    Consequently ``total_matching`` is a **lower bound** whenever the scan
    stopped early — the reader cannot count a corpus it deliberately did not
    read. It is exact whenever the stream was exhausted, which covers every
    small deployment and every filter that matches less than a full page.
    ``has_more`` is exact in all cases and is the authoritative "is there
    another page" signal.
    """
    need = offset + limit
    level_upper = level.upper() if level else None
    search_lower = search.lower() if search else None

    # Bounded dedupe window: a set for lookups, a deque to evict the oldest
    # key once it can no longer collide with anything still to come.
    seen: set[tuple[Any, Any]] = set()
    seen_order: deque[tuple[Any, Any]] = deque()

    page: list[dict[str, Any]] = []
    matched = 0

    for entry in _iter_entries_newest_first():
        # Deduplicate before filtering, as before: two entries can share a
        # ``(timestamp, message)`` while differing in level, and the first one
        # seen is the one that counts.
        key = (entry.get("timestamp"), entry.get("message"))
        if key in seen:
            continue
        seen.add(key)
        seen_order.append(key)
        if len(seen_order) > _DEDUPE_WINDOW:
            seen.discard(seen_order.popleft())

        if level_upper is not None and entry.get("level") != level_upper:
            continue
        if search_lower is not None and not (
            search_lower in entry.get("message", "").lower() or search_lower in entry.get("logger", "").lower()
        ):
            continue

        matched += 1
        if matched > offset and len(page) < limit:
            page.append(entry)
        if matched > need:
            # One past the page: enough to answer ``has_more`` exactly.
            break

    return page, matched, matched > need
