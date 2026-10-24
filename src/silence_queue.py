"""Sends held during a board's silence window, one per board (issue #1944).

When a board's silence schedule has ``show_queued_on_exit`` turned on, a
write that silence refuses — a Compose message, ``POST /v1/boards/{b}/message``,
``/send-message``, the MCP ``send_message`` tool, a Home Assistant MQTT send,
a page or display send — is held here as a typed *intent* and painted by the
display engine the moment the window ends.

Rules:

* **One per board, newest wins.** A second hold replaces the first.
* **An intent, not a frame.** A held page or display is re-rendered at
  delivery, so "Weather" shows the 7:00 weather, not the 2:00 one.
* **Persisted.** Every hold and discard rewrites
  ``<data dir>/silence_held.json`` atomically, so a restart during the night
  does not lose the morning message. The file is loaded lazily on first use.
* **24 hours at most.** An entry older than :data:`HELD_TTL_SECONDS` is
  dropped on load and on peek — a message held two nights ago is not news.
* **Peek, then discard on success.** The engine peeks, sends, and discards
  only once the send reports success, so a board that is offline at 7:00 gets
  the message on a later tick instead of losing it.

Keys are resolved board ids. The caller resolves "the primary board" before
it holds, so ``''`` never appears as a key.
"""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from src.atomic_io import write_json_atomic

logger = logging.getLogger(__name__)

HeldKind = Literal["text", "lines", "grid", "page", "display"]
_KINDS: tuple[str, ...] = ("text", "lines", "grid", "page", "display")

#: A held send older than this is stale and never delivered.
HELD_TTL_SECONDS = 24 * 3600

#: Longest preview the UI shows for a held message.
_PREVIEW_CHARS = 28

_FILE_NAME = "silence_held.json"

_lock = threading.Lock()
_held: dict[str, HeldSend] | None = None
_loaded_path: Path | None = None
_delivery_locks: dict[tuple[Path, str], threading.Lock] = {}


class QueueUnavailableError(OSError):
    """Existing queue data could not be read safely; leave it intact for repair."""


@dataclass(frozen=True)
class HeldSend:
    """One write silence refused and is holding until the window ends."""

    kind: HeldKind
    payload: Any
    board_id: str
    queued_at: float

    def __post_init__(self) -> None:
        if not isinstance(self.board_id, str) or not self.board_id:
            raise ValueError("A held send needs a resolved board id")
        if self.kind not in _KINDS:
            raise ValueError(f"Unknown held send kind: {self.kind!r}")
        if not isinstance(self.queued_at, (int, float)) or not math.isfinite(self.queued_at):
            raise ValueError("A held send needs a finite timestamp")
        # The status API formats this as an ISO instant. A finite but
        # out-of-range persisted value must not make that read fail.
        datetime.fromtimestamp(self.queued_at, tz=UTC)
        if self.kind in ("text", "page", "display") and not isinstance(self.payload, str):
            raise ValueError("A text, page or display intent needs a string payload")
        if self.kind == "lines" and (
            not isinstance(self.payload, list) or not all(isinstance(line, str) for line in self.payload)
        ):
            raise ValueError("A lines intent needs a list of strings")
        if self.kind == "grid":
            if not isinstance(self.payload, dict) or not isinstance(self.payload.get("characters"), list):
                raise ValueError("A grid intent needs a characters grid")
            if not all(
                isinstance(row, list) and all(type(cell) is int for cell in row) for row in self.payload["characters"]
            ):
                raise ValueError("A grid intent needs integer rows")

    @classmethod
    def text(cls, text: str, *, board_id: str) -> HeldSend:
        """Free text, word-wrapped to the board when it is delivered."""
        return cls("text", str(text), board_id, time.time())

    @classmethod
    def lines(cls, lines: list[str], *, board_id: str) -> HeldSend:
        """One string per row, laid out as given."""
        return cls("lines", [str(line) for line in lines], board_id, time.time())

    @classmethod
    def grid(cls, characters: list[list[int]], *, board_id: str, cells: Any = None) -> HeldSend:
        """A raw flap grid (``characters``/``fill``), with its rich cells if any."""
        return cls("grid", {"characters": characters, "cells": cells}, board_id, time.time())

    @classmethod
    def page(cls, page_id: str, *, board_id: str) -> HeldSend:
        """A saved page, rendered fresh when silence ends."""
        return cls("page", str(page_id), board_id, time.time())

    @classmethod
    def display(cls, display_type: str, *, board_id: str) -> HeldSend:
        """A plugin display, fetched fresh when silence ends."""
        return cls("display", str(display_type), board_id, time.time())

    def is_stale(self, now: float | None = None) -> bool:
        return ((now if now is not None else time.time()) - self.queued_at) > HELD_TTL_SECONDS


def _path() -> Path:
    from src.paths import get_data_dir

    return get_data_dir() / _FILE_NAME


def _from_dict(raw: Any) -> HeldSend | None:
    if not isinstance(raw, dict):
        return None
    try:
        return HeldSend(
            kind=raw["kind"],
            payload=raw["payload"],
            board_id=raw["board_id"],
            queued_at=float(raw["queued_at"]),
        )
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        return None


def _load_locked() -> dict[str, HeldSend]:
    """The store, loaded from disk on first use (caller holds ``_lock``)."""
    global _held, _loaded_path
    path = _path()
    if _held is not None and _loaded_path == path:
        return _held
    loaded: dict[str, HeldSend] = {}
    dropped = False
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError:
        raw = {}
    except (OSError, ValueError, UnicodeError) as exc:
        raise QueueUnavailableError(f"Cannot read held-send store: {path}") from exc
    if not isinstance(raw, dict):
        raise QueueUnavailableError("Held-send store must contain an object")
    now = time.time()
    for board_id, entry in raw.items():
        send = _from_dict(entry)
        if send is None or send.board_id != board_id:
            # Never rewrite partially damaged data and silently lose another
            # board's recoverable intent. Retry loading after external repair.
            raise QueueUnavailableError(f"Invalid held-send record for board {board_id}")
        if send.is_stale(now):
            dropped = True
            continue
        loaded[board_id] = send
    _held = loaded
    _loaded_path = path
    if dropped:
        try:
            _save_locked(loaded)
        except OSError as exc:
            logger.warning("Could not persist expired held-send cleanup: %s", exc)
    return _held


def _save_locked(held: dict[str, HeldSend]) -> None:
    """Atomically rewrite the store file (caller holds ``_lock``)."""
    path = _path()
    data = {board_id: asdict(send) for board_id, send in held.items()}
    write_json_atomic(path, data, private=True)


def _publish_locked(candidate: dict[str, HeldSend]) -> None:
    """Publish memory only after the candidate map is durably saved."""
    global _held
    _save_locked(candidate)
    _held = candidate


def hold(send: HeldSend) -> None:
    """Hold *send* for its board, replacing whatever was held there."""
    with _lock:
        held = _load_locked()
        _publish_locked({**held, send.board_id: send})


def peek(board_id: str | None) -> HeldSend | None:
    """The send held for *board_id*, or ``None``. Does not consume it."""
    if not board_id:
        return None
    with _lock:
        held = _load_locked()
        send = held.get(board_id)
        if send is not None and send.is_stale():
            try:
                _publish_locked({bid: item for bid, item in held.items() if bid != board_id})
            except OSError as exc:
                # Stale content is never eligible, even if disk cleanup fails.
                logger.warning("Could not persist expired held-send cleanup: %s", exc)
            return None
        return send


def discard(board_id: str | None, *, expected: HeldSend | None = None) -> bool:
    """Forget this board's intent, optionally only if it is still *expected*.

    Delivery snapshots the intent before writing. Comparing under the store
    lock prevents an older completion from removing a newer queued message.
    """
    if not board_id:
        return False
    with _lock:
        held = _load_locked()
        if board_id not in held:
            return False
        if expected is not None and held[board_id] != expected:
            return False
        _publish_locked({bid: item for bid, item in held.items() if bid != board_id})
        return True


def deliver(expected: HeldSend | None, send, *args, require_current: bool = False, check=None, **kwargs):
    """Serialize consuming writes per board without blocking new holds/discard."""
    if expected is None:
        return _deliver_observed(expected, send, *args, require_current=require_current, check=check, **kwargs)
    with _lock:
        delivery_lock = _delivery_locks.setdefault((_path(), expected.board_id), threading.Lock())
    with delivery_lock:
        return _deliver_observed(expected, send, *args, require_current=require_current, check=check, **kwargs)


def _deliver_observed(expected, send, *args, require_current=False, check=None, **kwargs):
    """Retry until actual success, conditionally clearing only this intent.

    An exception/interruption or failed cleanup leaves the original durable
    intent retryable. An ambiguous physical outcome can therefore send twice.
    """
    from src.send_outcome import SendOutcome

    if (require_current and expected is not None and peek(expected.board_id) != expected) or (check and not check()):
        return False, False
    result = send(*args, **kwargs)
    if expected is None:
        return result
    outcome = SendOutcome.of(result)
    if outcome.success and outcome.was_sent and not outcome.throttled:
        try:
            discard(expected.board_id, expected=expected)
        except OSError as exc:
            # Hardware already succeeded. Report it truthfully; the durable
            # queue can repeat this send on a later tick or after restart.
            logger.error("Could not clear delivered held send for board %s; it may retry: %s", expected.board_id, exc)
    return result


def _page_name(page_id: str) -> str:
    try:
        from src.pages.service import get_page_service

        page = get_page_service().get_page(page_id)
        name = getattr(page, "name", None) if page is not None else None
        return name if isinstance(name, str) and name else page_id
    except Exception:  # pragma: no cover - defensive: a preview never fails
        return page_id


def _truncate(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= _PREVIEW_CHARS:
        return text
    cut = text[:_PREVIEW_CHARS]
    if text[_PREVIEW_CHARS] != " " and " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip() + "…"


def preview_text(send: HeldSend) -> str:
    """A short, human preview of *send* for the UI (at most 40 characters)."""
    if send.kind == "text":
        return _truncate(str(send.payload))
    if send.kind == "lines":
        return _truncate(" ".join(line for line in send.payload if str(line).strip()))
    if send.kind == "page":
        return _truncate(f"Page: {_page_name(str(send.payload))}")
    if send.kind == "display":
        return _truncate(f"Display: {send.payload}")
    return "Board pattern"
