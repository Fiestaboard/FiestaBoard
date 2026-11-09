"""What happened the last times each page was sent (H9b; Figma 04d 1.7 "Sent").

One entry per outcome, newest first, at most :data:`MAX_SENDS_PER_PAGE` per page:

* ``sent`` — a frame of the page landed on a board;
* ``failed`` — the write failed or raised. ``error`` is the board's H12
  failure code (``auth``, ``unreachable``, ``timeout``, …) when H12 recorded
  it during this send (``last_error_at`` at or after the send started), so
  the Sent row can say why without free text (which can carry hosts). An
  older code is never copied: it would name a cause from another day;
* ``paused`` / ``silenced`` / ``held`` — Show now refused by pause or
  Silence (``held``: queued to show when Silence ends).

**Repeats merge.** A failure the engine retries every pass, or Show now
pressed again during Silence, repeats the newest entry: same outcome, via,
board and code. It is merged into that entry (``count`` + ``last_at``)
instead of pushing older entries out of the window, so an unplugged board
cannot wipe a page's history. ``sent`` entries are never merged: each is a
frame that landed at its own time.

Not recorded: unchanged-content skips, throttled and superseded writes (the
next tick retries; nothing happened), UI-only targets, previews, trigger and
silence pages, native playlists. ``via`` is ``auto`` (the hub showed it on its
own: schedule, collection, Change Page) or ``show_now`` (``POST
/pages/{id}/send``).

This is per **page**; H12's health is per **display**. A failed send copies
the display's ``last_error`` code rather than inventing a second taxonomy.

**Persistence, light** (the H12 pattern): in memory, written to
``<data>/page_sends.json`` at once when the last write is older than
:data:`SENDS_FLUSH_INTERVAL_SECONDS`, otherwise by one timer at the end of
the interval, always on shutdown (:func:`flush_send_history`), and at once
when a page is forgotten. A clock page that changes every minute costs one
write per three minutes, never one per frame; a crash loses at most the last
interval. A merged repeat only updates memory: it is written with the next
new entry, a page delete or shutdown, so a board that stays down costs no
SD-card writes. Writes are atomic and serialised. The file is validated on load:
entries with an outcome, client or instant this build does not know are
dropped, and an unknown failure code reads as null (as H12 does), so a
rollback never fails a read.
"""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Literal, get_args

from src.atomic_io import write_json_atomic
from src.outputs.health import ErrorCode, board_health

from .history import iso

logger = logging.getLogger(__name__)

MAX_SENDS_PER_PAGE = 20
SENDS_FLUSH_INTERVAL_SECONDS = 180.0
SCHEMA_VERSION = 1
_FILENAME = "page_sends.json"
#: 9999-12-31T23:59:59Z, the last instant ``datetime`` can show.
_LATEST_EPOCH = 253_402_300_799.0

SendOutcomeName = Literal["sent", "failed", "paused", "silenced", "held"]
SendVia = Literal["auto", "show_now"]
_OUTCOMES = frozenset(get_args(SendOutcomeName))
_VIAS = frozenset(get_args(SendVia))
_CODES = frozenset(get_args(ErrorCode))


def _instant(value) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    if not math.isfinite(value) or not 0 < value <= _LATEST_EPOCH:
        return None
    return float(value)


def _clean(entry) -> dict | None:
    """*entry* as this build reads it, or None when it is not one."""
    if not isinstance(entry, dict):
        return None
    at = _instant(entry.get("at"))
    if at is None:
        return None
    if entry.get("outcome") not in _OUTCOMES or entry.get("via") not in _VIAS:
        return None
    error = entry.get("error")
    board_id, board_name = entry.get("board_id"), entry.get("board_name")
    cleaned = {
        "at": at,
        "outcome": entry["outcome"],
        "via": entry["via"],
        "board_id": board_id if isinstance(board_id, str) else None,
        "board_name": board_name if isinstance(board_name, str) else None,
        "error": error if error in _CODES else None,  # a newer build's code reads as unknown
    }
    count, last_at = entry.get("count"), _instant(entry.get("last_at"))
    if isinstance(count, int) and not isinstance(count, bool) and count > 1 and last_at is not None and last_at >= at:
        cleaned["count"] = count
        cleaned["last_at"] = last_at
    return cleaned


def _repeats(newest: dict | None, entry: dict) -> bool:
    """*entry* is the same event as *newest* again (never a ``sent``: each landing is its own)."""
    return (
        newest is not None
        and entry["outcome"] != "sent"
        and all(newest[k] == entry[k] for k in ("outcome", "via", "board_id", "error"))
    )


class SendHistory:
    """Every page's recent send outcomes, kept in memory and written lightly."""

    def __init__(
        self,
        path: Path,
        clock: Callable[[], float] = time.time,
        timer: Callable[..., threading.Timer] = threading.Timer,
    ) -> None:
        self.path = Path(path)
        self.clock = clock
        self._timer_factory = timer
        self._lock = threading.Lock()
        #: Held across snapshot and write, so writes land in the order they were taken.
        self._write_lock = threading.Lock()
        self._pages: dict[str, list[dict]] = {}  # oldest first
        self._dirty = False
        #: Merged repeats not yet on disk: written with the next write, never on their own.
        self._repeats_pending = False
        #: Pages deleted in this process: a send in flight when its page went is not recorded.
        self._forgotten: set[str] = set()
        self._written_at: float | None = None
        self._timer: threading.Timer | None = None
        self._closed = False
        self._load()

    def _load(self) -> None:
        try:
            loaded = json.loads(self.path.read_text())
        except FileNotFoundError:
            return
        except (OSError, ValueError):
            logger.warning("Could not read %s; send history starts empty", self.path, exc_info=True)
            return
        pages = loaded.get("pages") if isinstance(loaded, dict) else None
        if not isinstance(pages, dict):
            logger.warning("%s has no pages object; send history starts empty", self.path)
            return
        for page_id, entries in pages.items():
            if not isinstance(entries, list):
                continue
            cleaned = [e for e in map(_clean, entries) if e is not None]
            if cleaned:
                self._pages[page_id] = cleaned[-MAX_SENDS_PER_PAGE:]

    # ── reads and writes ───────────────────────────────────────────────

    def sends(self, page_id: str) -> list[dict]:
        """The page's outcomes, newest first, as the wire shape."""
        with self._lock:
            entries = list(self._pages.get(page_id, ()))
        return [
            {**e, "at": iso(e["at"]), "count": e.get("count", 1), "last_at": iso(e.get("last_at"))}
            for e in reversed(entries)
        ]

    def record(
        self,
        page_id: str,
        *,
        outcome: str,
        via: str,
        board_id: str | None,
        board_name: str | None,
        error: str | None = None,
    ) -> None:
        entry = _clean(
            {
                "at": self.clock(),
                "outcome": outcome,
                "via": via,
                "board_id": board_id,
                "board_name": board_name,
                "error": error,
            }
        )
        if entry is None:
            logger.debug("Not recording an unknown send outcome %r for page %s", outcome, page_id)
            return
        with self._lock:
            if page_id in self._forgotten:
                return
            entries = self._pages.setdefault(page_id, [])
            newest = entries[-1] if entries else None
            if _repeats(newest, entry):
                newest["count"] = newest.get("count", 1) + 1
                newest["last_at"] = entry["at"]
                newest["board_name"] = entry["board_name"]
                self._repeats_pending = True
                return
            entries.append(entry)
            del entries[:-MAX_SENDS_PER_PAGE]
            self._dirty = True
            elapsed = None if self._written_at is None else self.clock() - self._written_at
            due = elapsed is None or elapsed >= SENDS_FLUSH_INTERVAL_SECONDS
            if not due:
                # Clamped: a clock stepped back makes elapsed negative, which
                # must not arm a timer for longer than one interval.
                self._arm_timer(min(SENDS_FLUSH_INTERVAL_SECONDS, SENDS_FLUSH_INTERVAL_SECONDS - elapsed))
        if due:
            self.flush()

    def forget(self, page_id: str) -> None:
        """A deleted page's history goes at once (deletes are rare).

        A send still in flight for it is not recorded afterwards, so a deleted
        page's history never comes back (and is never written with no page to prune it).
        """
        with self._lock:
            self._forgotten.add(page_id)
            if self._pages.pop(page_id, None) is None:
                return
            self._dirty = True
        self.flush()

    def flush(self) -> None:
        with self._lock:
            self._disarm_timer()
            if not self._dirty and not self._repeats_pending:
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
                snapshot = {
                    "schema_version": SCHEMA_VERSION,
                    "pages": {k: [dict(e) for e in v] for k, v in self._pages.items()},
                }
                self._dirty = False
                self._repeats_pending = False
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                write_json_atomic(self.path, snapshot, indent=None)
            except OSError:
                # Advisory: a failed write never fails a send. It stays pending.
                logger.warning("Could not write %s", self.path, exc_info=True)
                with self._lock:
                    self._dirty = True


_store: SendHistory | None = None
_store_lock = threading.Lock()


def send_history() -> SendHistory:
    global _store
    with _store_lock:
        if _store is None:
            from src.paths import get_data_dir

            _store = SendHistory(get_data_dir() / _FILENAME)
        return _store


def reset_send_history() -> None:
    """Forget the store (tests; a fresh process reads the file again)."""
    global _store
    with _store_lock:
        if _store is not None:
            _store.close()
        _store = None


def flush_send_history() -> None:
    with _store_lock:
        store = _store
    if store is not None:
        store.flush()


def board_error_code(service, board_id: str | None, since: float | None) -> str | None:
    """The board's H12 ``last_error`` code when H12 recorded it at or after *since*, else None.

    H12 keeps ``last_error`` across contacts and restarts, so without the
    instant a failure H12 did not classify (a render that raised before any
    HTTP, a projection error) would take a cause from days ago. ``last_error_at``
    has whole seconds, so *since* is compared rounded down.
    """
    if not board_id or since is None:
        return None
    try:
        health = board_health(service, board_id)
        if health.last_error is None or health.last_error_at is None:
            return None
        at = datetime.fromisoformat(health.last_error_at).timestamp()
    except Exception:
        return None
    return health.last_error if at >= math.floor(since) else None


def record_send(
    page_id: str,
    *,
    outcome: str,
    via: str,
    board_id: str | None,
    board_name: str | None,
    service=None,
    started_at: float | None = None,
) -> None:
    """Record one outcome; never raises (history is advisory).

    *started_at* is when this send began (``time.time()``, before render): a
    ``failed`` copies the board's H12 code only when it is that fresh.
    """
    try:
        error = board_error_code(service, board_id, started_at) if outcome == "failed" else None
        send_history().record(page_id, outcome=outcome, via=via, board_id=board_id, board_name=board_name, error=error)
    except Exception:
        logger.warning("Could not record a send of page %s", page_id, exc_info=True)
