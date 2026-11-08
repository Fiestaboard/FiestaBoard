"""Per-display health (H12): when the hub last reached the board, and how it went.

Kept on the board's :class:`~src.outputs.runtime.OutputRuntime`, which a driver
rebuild (a board re-save) hands on.

- **Contact** (``last_connected_at``, ``latency_ms``) is recorded by
  :class:`~src.outputs.http.OutputHttp`, where every device request goes, and
  only when the device answered: a 2xx/3xx, or a 429 the device sends. Core's
  dedupe and send-floor short-circuits never reach the device, and a plugin
  that reports "unchanged" without a request proves nothing.
- **Failures** are classified there too, with :data:`~src.outputs.hooks.FailureClass`
  (``auth``, ``unreachable``, ``timeout``, ``server_error``,
  ``unexpected_status``, ``blocked``), so a plugin that swallows its exception
  still shows the real cause. :class:`~src.outputs.plugin_driver.OutputPluginDriver`
  adds what HTTP cannot see: ``write_failed`` (the output said so, and no HTTP
  failure explains it), ``raised``, ``timeout`` (the write ran past its
  budget), ``breaker_open``, ``bad_response`` and ``read_failed`` (reads).
- **Updates** (``last_update_at``) are frames that landed. A pull output
  (FiestaPanel) records updates only; the hub never contacts it, and its
  viewers' liveness is H13b's ``last_shown_at``.

**Vestaboard Cloud:** for a Cloud API board, contact means the *cloud API*
answered, not that the board itself is online (the cloud API does not say),
and ``latency_ms`` is the cloud round trip.

**Persistence, light.** ``last_connected_at``, ``last_update_at``,
``last_error_at`` and ``last_error`` survive a restart in
``<data>/board_health.json``. A change marks the board dirty; the file is
written at most every :data:`HEALTH_FLUSH_INTERVAL_SECONDS` and on shutdown
(:func:`flush_board_health`), never per frame. ``reachable`` and ``latency_ms``
are unknown again after a restart, until this process has its own contact or
failure.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

#: The most often the health file is written, in seconds (and on shutdown).
HEALTH_FLUSH_INTERVAL_SECONDS = 180.0
_FILENAME = "board_health.json"
_PERSISTED = ("last_connected_at", "last_update_at", "last_error_at", "last_error")

ErrorCode = Literal[
    # FailureClass, classified by OutputHttp from the device's answer.
    "auth",
    "unreachable",
    "timeout",
    "server_error",
    "unexpected_status",
    "blocked",
    # What only the driver sees.
    "write_failed",
    "raised",
    "breaker_open",
    "bad_response",
    "read_failed",
]


class HealthSummary(BaseModel):
    """A display's health, as ``GET /status`` and ``GET /v1/boards/{board}`` report it."""

    last_connected_at: str | None = Field(
        default=None,
        description=(
            "When the device last answered the hub (UTC, whole seconds). For a Vestaboard Cloud API board this is "
            "the cloud API answering, not the board itself."
        ),
    )
    last_update_at: str | None = Field(default=None, description="When a frame last landed (UTC, whole seconds).")
    latency_ms: int | None = Field(
        default=None, description="How long the request behind last_connected_at took; null after a restart."
    )
    last_error_at: str | None = Field(default=None, description="When the last failed contact happened.")
    last_error: ErrorCode | None = Field(
        default=None,
        description=(
            "Why it failed. From the device's answer: auth (credential refused), unreachable, timeout, "
            "server_error, unexpected_status, blocked (host not allowed). From the hub: write_failed, raised, "
            "breaker_open (writes paused after repeated failures), bad_response, read_failed."
        ),
    )
    reachable: bool | None = Field(
        default=None,
        description=(
            "True when the last contact is newer than the last error, false when not, null until this hub process "
            "has had either (and always for a FiestaPanel, which the hub never contacts)."
        ),
    )


def _instant(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, UTC).replace(microsecond=0).isoformat()


class HealthStore:
    """The persisted part of every board's health, in one small JSON file."""

    def __init__(self, path: Path, clock: Callable[[], float] = time.time) -> None:
        self.path = path
        self.clock = clock
        self._lock = threading.Lock()
        self._data: dict[str, dict] = {}
        self._dirty = False
        self._written_at: float | None = None
        try:
            loaded = json.loads(path.read_text())
            if isinstance(loaded, dict):
                self._data = {k: v for k, v in loaded.items() if isinstance(v, dict)}
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            logger.warning("Could not read %s; board health starts empty", path, exc_info=True)

    def get(self, board_id: str) -> dict:
        with self._lock:
            return dict(self._data.get(board_id) or {})

    def update(self, board_id: str, values: dict) -> None:
        """Remember *values* for *board_id*; write now only if the interval has passed."""
        with self._lock:
            self._data[board_id] = values
            self._dirty = True
            due = self._written_at is None or self.clock() - self._written_at >= HEALTH_FLUSH_INTERVAL_SECONDS
        if due:
            self.flush()

    def flush(self) -> None:
        with self._lock:
            if not self._dirty:
                return
            self._written_at = self.clock()
        self._write()

    def _write(self) -> None:
        with self._lock:
            snapshot = json.dumps(self._data, sort_keys=True)
            self._dirty = False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(snapshot)
            tmp.replace(self.path)
        except OSError:
            # Health is advisory: a failed write must never fail a send.
            logger.warning("Could not write %s", self.path, exc_info=True)


_store: HealthStore | None = None
_store_lock = threading.Lock()


def health_store() -> HealthStore:
    global _store
    with _store_lock:
        if _store is None:
            from src.paths import get_data_dir

            _store = HealthStore(get_data_dir() / _FILENAME)
        return _store


def reset_health_store() -> None:
    """Forget the store (tests; a fresh process reads the file again)."""
    global _store
    with _store_lock:
        _store = None


def flush_board_health() -> None:
    """Write any pending board health now (the app's shutdown)."""
    if _store is not None:
        _store.flush()


class BoardHealth:
    """Thread-safe health record for one board. ``clock`` is wall time (seconds since the epoch).

    *board_id* ``None`` is a draft driver's private runtime: it is never persisted.
    """

    def __init__(self, board_id: str | None = None, clock: Callable[[], float] = time.time) -> None:
        self.board_id = board_id
        self.clock = clock
        self._lock = threading.Lock()
        stored = health_store().get(board_id) if board_id else {}
        self._connected_at: float | None = stored.get("last_connected_at")
        self._updated_at: float | None = stored.get("last_update_at")
        self._error_at: float | None = stored.get("last_error_at")
        self._error: str | None = stored.get("last_error")
        self._latency_ms: int | None = None
        #: Whether this process has seen a contact or failure (``reachable`` needs one).
        self._live = False
        #: Failures recorded so far, so the driver can tell whether HTTP explained one.
        self.error_count = 0

    def record_contact(self, seconds: float) -> None:
        """The device answered; *seconds* is how long the request took."""
        with self._lock:
            self._connected_at = self.clock()
            self._latency_ms = max(0, round(seconds * 1000))
            self._live = True
        self._persist()

    def record_update(self) -> None:
        """A frame landed."""
        with self._lock:
            self._updated_at = self.clock()
        self._persist()

    def record_error(self, code: ErrorCode) -> None:
        """A contact failed, for *code*."""
        with self._lock:
            self._error_at = self.clock()
            self._error = code
            self._live = True
            self.error_count += 1
        self._persist()

    def _persist(self) -> None:
        if not self.board_id:
            return
        with self._lock:
            values = {
                "last_connected_at": self._connected_at,
                "last_update_at": self._updated_at,
                "last_error_at": self._error_at,
                "last_error": self._error,
            }
        health_store().update(self.board_id, values)

    def as_dict(self) -> dict:
        with self._lock:
            connected, error = self._connected_at, self._error_at
            if not self._live:
                reachable = None
            else:
                reachable = error is None or (connected is not None and connected >= error)
            return {
                "last_connected_at": _instant(connected),
                "last_update_at": _instant(self._updated_at),
                "latency_ms": self._latency_ms,
                "last_error_at": _instant(error),
                "last_error": self._error,
                "reachable": reachable,
            }

    def summary(self) -> HealthSummary:
        return HealthSummary(**self.as_dict())


def board_health(service, board_id: str) -> HealthSummary:
    """*board_id*'s health from the live service, or an all-null summary when it has no runtime."""
    try:
        runtime = service.runtime_for(board_id) if service is not None else None
        health = getattr(getattr(runtime, "output", None), "health", None)
    except Exception:  # a health read must never break a status poll
        health = None
    return health.summary() if isinstance(health, BoardHealth) else HealthSummary()
