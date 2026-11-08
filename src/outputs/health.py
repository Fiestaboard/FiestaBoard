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
  ``unexpected_status``, ``blocked``), plus ``invalid_request`` when the
  request could not even be built (a bad address or header in the board's
  settings), so a plugin that swallows its exception still shows the real
  cause. :class:`~src.outputs.plugin_driver.OutputPluginDriver` adds what HTTP
  cannot see: ``write_failed`` (the output said so, and no HTTP failure
  explains it), ``raised``, ``timeout`` (the write ran past its budget),
  ``bad_response`` and ``read_failed`` (reads).
- **The circuit breaker** is ``breaker_open``, a flag read live from the
  breaker, *beside* ``last_error``. A refused write never reaches the device,
  so it is not a contact attempt and never replaces the cause: a board whose
  token is wrong keeps reading ``auth`` while the hub holds its writes back.
- **Updates** (``last_update_at``) are frames that landed. A pull output
  (FiestaPanel) records updates only; the hub never contacts it, and its
  viewers' liveness is H13b's ``last_shown_at``.

**Vestaboard Cloud:** for a Cloud API board, contact means the *cloud API*
answered, not that the board itself is online (the cloud API does not say),
and ``latency_ms`` is the cloud round trip.

**Persistence, light.** ``last_connected_at``, ``last_update_at``,
``last_error_at`` and ``last_error`` survive a restart in
``<data>/board_health.json``. A change marks the board dirty; the file is
written at most every :data:`HEALTH_FLUSH_INTERVAL_SECONDS`: at once when the
interval has passed, otherwise by a timer at the end of it, so an idle board's
last change is not left waiting for the next one. It is also written on
shutdown (:func:`flush_board_health`), and never per frame. A crash loses at
most the last interval's changes. Writes are atomic (``*.tmp`` and a rename)
and serialised, so an older snapshot can never land after a newer one.

The file is validated on load: an entry keeps only finite, in-range numeric
instants and codes this build knows. A rollback can leave a newer build's
codes behind; they read as unknown (null) rather than failing a status read.
A removed board's entry is dropped (:func:`forget_board_health`).

``reachable`` and ``latency_ms`` are unknown again after a restart, until this
process has its own contact or failure. ``reachable`` then follows this
process's *last event* (a contact or a failure), never a comparison of wall
times: a FiestaPi has no real-time clock and can boot reading earlier than an
error persisted before the reboot, until NTP syncs.
"""

from __future__ import annotations

import contextlib
import json
import logging
import math
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, get_args

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
    # The request could not be built: a bad address, header or body.
    "invalid_request",
    # What only the driver sees.
    "write_failed",
    "raised",
    "bad_response",
    "read_failed",
]
_KNOWN_CODES = frozenset(get_args(ErrorCode))
_INSTANTS = ("last_connected_at", "last_update_at", "last_error_at")
#: 9999-12-31T23:59:59Z, the last instant ``datetime`` can show.
_LATEST_EPOCH = 253_402_300_799.0


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
            "server_error, unexpected_status, blocked (host not allowed), invalid_request (the request could not "
            "be built: a bad address or header in the board's settings). From the hub: write_failed, raised, "
            "bad_response, read_failed. Kept while breaker_open holds writes back."
        ),
    )
    reachable: bool | None = Field(
        default=None,
        description=(
            "True when this hub process's last event for the board was a contact, false when it was a failure, "
            "null until it has had either (and always for a FiestaPanel, which the hub never contacts)."
        ),
    )
    breaker_open: bool = Field(
        default=False,
        description=(
            "True while the hub holds writes back after repeated failures (it retries every few minutes). "
            "last_error still says what the failures were."
        ),
    )


def _valid_instant(value) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and 0 < value <= _LATEST_EPOCH
    )


def _clean(entry) -> dict | None:
    """*entry* as this build can read it, or ``None`` when it is not an entry at all."""
    if not isinstance(entry, dict):
        return None
    cleaned: dict = {key: float(entry[key]) if _valid_instant(entry.get(key)) else None for key in _INSTANTS}
    code = entry.get("last_error")
    cleaned["last_error"] = code if isinstance(code, str) and code in _KNOWN_CODES else None
    return cleaned


def _instant(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, UTC).replace(microsecond=0).isoformat()


class HealthStore:
    """The persisted part of every board's health, in one small JSON file."""

    def __init__(
        self,
        path: Path,
        clock: Callable[[], float] = time.time,
        timer: Callable[..., threading.Timer] = threading.Timer,
    ) -> None:
        self.path = path
        self.clock = clock
        self._timer_factory = timer
        self._lock = threading.Lock()
        #: Held across snapshot and write, so writes land in the order they were taken.
        self._write_lock = threading.Lock()
        self._data: dict[str, dict] = {}
        self._dirty = False
        self._written_at: float | None = None
        self._timer: threading.Timer | None = None
        self._closed = False
        try:
            loaded = json.loads(path.read_text())
        except FileNotFoundError:
            loaded = {}
        except (OSError, ValueError):
            logger.warning("Could not read %s; board health starts empty", path, exc_info=True)
            loaded = {}
        if not isinstance(loaded, dict):
            logger.warning("%s is not an object; board health starts empty", path)
            loaded = {}
        for board_id, entry in loaded.items():
            cleaned = _clean(entry)
            if cleaned is not None:
                self._data[board_id] = cleaned

    def get(self, board_id: str) -> dict:
        with self._lock:
            return dict(self._data.get(board_id) or {})

    def update(self, board_id: str, values: dict) -> None:
        """Remember *values* for *board_id*; write now if the interval has passed, else at its end."""
        with self._lock:
            self._data[board_id] = values
            self._dirty = True
            elapsed = None if self._written_at is None else self.clock() - self._written_at
            due = elapsed is None or elapsed >= HEALTH_FLUSH_INTERVAL_SECONDS
            if not due:
                self._arm_timer(HEALTH_FLUSH_INTERVAL_SECONDS - elapsed)
        if due:
            self.flush()

    def forget(self, board_id: str) -> None:
        """Drop a removed board's entry, and write that now (removals are rare)."""
        with self._lock:
            if self._data.pop(board_id, None) is None:
                return
            self._dirty = True
        self.flush()

    def flush(self) -> None:
        with self._lock:
            self._disarm_timer()
            if not self._dirty:
                return
            self._written_at = self.clock()
        self._write()

    def close(self) -> None:
        """Stop the pending timer, if any (tests; a store being replaced)."""
        with self._lock:
            self._closed = True
            self._disarm_timer()

    # The timer helpers run under self._lock.
    def _arm_timer(self, delay: float) -> None:
        if self._timer is not None or self._closed:
            return
        timer = self._timer_factory(max(0.0, delay), self._on_timer)
        timer.daemon = True
        self._timer = timer
        timer.start()

    def _disarm_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _on_timer(self) -> None:
        with self._lock:
            self._timer = None
            if self._closed:
                return
        self.flush()

    def _write(self) -> None:
        with self._write_lock:
            with self._lock:
                snapshot = json.dumps(self._data, sort_keys=True)
                self._dirty = False
            tmp = self.path.with_suffix(".tmp")
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp.write_text(snapshot)
                tmp.replace(self.path)
            except OSError:
                # Health is advisory: a failed write must never fail a send.
                # It stays pending, so the next flush (or shutdown) tries again.
                logger.warning("Could not write %s", self.path, exc_info=True)
                with self._lock:
                    self._dirty = True
                with contextlib.suppress(OSError):
                    tmp.unlink(missing_ok=True)


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
        if _store is not None:
            _store.close()
        _store = None


def flush_board_health() -> None:
    """Write any pending board health now (the app's shutdown)."""
    if _store is not None:
        _store.flush()


def forget_board_health(board_id: str) -> None:
    """Drop a removed board's persisted health."""
    health_store().forget(board_id)


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
        #: This process's last event, ``"contact"`` or ``"error"`` (``reachable`` needs one).
        self._last_event: str | None = None
        #: Whether the device's circuit breaker is open now; the driver binds it.
        self.breaker: Callable[[], bool] | None = None
        #: Failures recorded so far, so the driver can tell whether HTTP explained one.
        self.error_count = 0

    def record_contact(self, seconds: float) -> None:
        """The device answered; *seconds* is how long the request took."""
        with self._lock:
            self._connected_at = self.clock()
            self._latency_ms = max(0, round(seconds * 1000))
            self._last_event = "contact"
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
            self._last_event = "error"
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

    def _breaker_open(self) -> bool:
        probe = self.breaker
        if probe is None:
            return False
        try:
            return bool(probe())
        except Exception:
            logger.debug("Could not read the breaker for %s", self.board_id, exc_info=True)
            return False

    def as_dict(self) -> dict:
        breaker_open = self._breaker_open()
        with self._lock:
            reachable = None if self._last_event is None else self._last_event == "contact"
            return {
                "last_connected_at": _instant(self._connected_at),
                "last_update_at": _instant(self._updated_at),
                "latency_ms": self._latency_ms,
                "last_error_at": _instant(self._error_at),
                "last_error": self._error,
                "reachable": reachable,
                "breaker_open": breaker_open,
            }

    def summary(self) -> HealthSummary:
        return HealthSummary(**self.as_dict())


def board_health(service, board_id: str) -> HealthSummary:
    """*board_id*'s health from the live service, or an all-null summary when it has no runtime."""
    try:  # a health read must never break a status poll
        runtime = service.runtime_for(board_id) if service is not None else None
        health = getattr(getattr(runtime, "output", None), "health", None)
        if isinstance(health, BoardHealth):
            return health.summary()
    except Exception:
        logger.warning("Could not report the health of board %s", board_id, exc_info=True)
    return HealthSummary()
