"""Lightweight Loki logging handler for FiestaBoard.

Pushes structured JSON log entries to a local Loki instance via its
HTTP push API (/loki/api/v1/push).  Entries are batched in memory and
flushed periodically by a background daemon thread to avoid blocking
the main application on every log call.

Only activated when LOCAL_MONITORING is enabled and Loki is running
alongside Prometheus and Grafana inside the container.
"""

import json
import logging
import threading
import urllib.error
import urllib.request
from collections import deque

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Component labels — extracted from the Python logger name so that Grafana
# users can filter logs by component (e.g. {component="mqtt"}).
# ---------------------------------------------------------------------------
_COMPONENT_PREFIXES = {
    "src.mqtt": "mqtt",
    "src.api_server": "api",
    "src.main": "core",
    "src.displays": "display",
    "src.pages": "pages",
    "src.schedules": "schedules",
    "src.carousels": "carousels",
    "src.settings": "settings",
    "src.config": "config",
    "src.templates": "templates",
    "plugins.": "plugin",
}


def _component_from_logger(name: str) -> str:
    """Derive a short component label from a dotted logger name."""
    for prefix, label in _COMPONENT_PREFIXES.items():
        if name.startswith(prefix):
            return label
    return "app"


class LokiHandler(logging.Handler):
    """Batching logging handler that pushes entries to Loki's HTTP API.

    Parameters
    ----------
    url : str
        Full push URL, e.g. ``http://127.0.0.1:3101/loki/api/v1/push``.
    batch_size : int
        Maximum entries to buffer before forcing a flush (default 50).
    flush_interval : float
        Seconds between periodic flushes (default 5).
    """

    def __init__(
        self,
        url: str = "http://127.0.0.1:3101/loki/api/v1/push",
        batch_size: int = 50,
        flush_interval: float = 5.0,
        level: int = logging.DEBUG,
    ):
        super().__init__(level)
        self._url = url
        self._batch_size = batch_size
        self._flush_interval = flush_interval

        self._buffer: deque = deque()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._loki_available: bool | None = None  # unknown until first push
        self._consecutive_failures = 0

        # Daemon thread flushes the buffer periodically
        self._thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------
    # logging.Handler interface
    # ------------------------------------------------------------------
    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = self._build_entry(record)
            batch = None
            with self._lock:
                self._buffer.append(entry)
                if len(self._buffer) >= self._batch_size:
                    batch = list(self._buffer)
                    self._buffer.clear()

            if batch:
                self._push(batch)
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        self._stop_event.set()
        self._flush()  # best-effort final flush
        super().close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _build_entry(self, record: logging.LogRecord) -> dict:
        """Create a Loki-compatible stream entry from a log record."""
        ts_ns = str(int(record.created * 1e9))
        message = self.format(record) if self.formatter else record.getMessage()
        component = _component_from_logger(record.name)

        return {
            "labels": {
                "job": "fiestaboard",
                "level": record.levelname,
                "component": component,
                "logger": record.name,
            },
            "timestamp_ns": ts_ns,
            "message": message,
        }

    # ------------------------------------------------------------------
    def _flush_loop(self) -> None:
        """Background loop: flush buffer every *flush_interval* seconds."""
        while not self._stop_event.is_set():
            self._stop_event.wait(self._flush_interval)
            self._flush()

    def _flush(self) -> None:
        with self._lock:
            if not self._buffer:
                return
            batch = list(self._buffer)
            self._buffer.clear()
        self._push(batch)

    # ------------------------------------------------------------------
    def _push(self, entries: list) -> None:
        """Push a batch of entries to Loki."""
        # Group entries by label-set (Loki requires unique label combos per stream)
        streams: dict[str, dict] = {}
        for e in entries:
            key = json.dumps(e["labels"], sort_keys=True)
            if key not in streams:
                streams[key] = {
                    "stream": e["labels"],
                    "values": [],
                }
            streams[key]["values"].append([e["timestamp_ns"], e["message"]])

        payload = json.dumps({"streams": list(streams.values())}).encode("utf-8")

        req = urllib.request.Request(
            self._url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            if not self._loki_available:
                self._loki_available = True
                self._consecutive_failures = 0
        except (urllib.error.URLError, OSError):
            self._consecutive_failures += 1
            # Silently drop — Loki may not be running yet.  Avoid log-storm
            # by not logging here (we're inside the logging subsystem).
            if self._loki_available is None and self._consecutive_failures >= 3:
                self._loki_available = False
