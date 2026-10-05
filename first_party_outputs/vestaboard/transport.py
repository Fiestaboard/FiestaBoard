"""The Vestaboard wire: endpoints, headers, timeouts, payloads and read shapes.

Moved whole from FiestaBoard core's ``src/board_client.py`` when the
Vestaboard became an output plugin (Phase 4). Every request goes through the
instance's ``self.http`` (FiestaBoard's device client: the
``FIESTABOARD_OUTPUTS_ALLOW_HOSTS`` fence, the run's cancel token); the
requests themselves — URL, headers, body, ``(connect, read)`` timeouts — are
byte-for-byte what the in-core client sent (``tests/golden/wire``).

APIs:

- **Local API** — ``POST/GET http://{host}:7000/local-api/message`` with
  ``X-Vestaboard-Local-Api-Key``; the only one that animates a transition.
- **RW Cloud API** — ``POST/GET https://rw.vestaboard.com/`` with
  ``X-Vestaboard-Read-Write-Key``; one message per 15 seconds.
- **Note-array Cloud API** — ``POST/GET https://cloud.vestaboard.com/`` with
  ``X-Vestaboard-Token``; one message per 15 seconds.
"""

from __future__ import annotations

import email.utils
import json
import logging
import math
import os
import re
from datetime import UTC, datetime
from typing import Any

import requests

logger = logging.getLogger(__name__)

#: The Vestaboard Local API's port.
LOCAL_API_PORT = 7000

#: Read/Write Cloud API base URL. ``VESTABOARD_RW_API_URL`` points cloud
#: boards somewhere else (a dev or test mock); the real cloud by default.
CLOUD_API_URL = os.environ.get("VESTABOARD_RW_API_URL") or "https://rw.vestaboard.com/"

#: Note-array Cloud API base URL. ``VESTABOARD_CLOUD_API_URL`` points
#: note-array boards at a mock (docker-compose.dev.yml sets it).
CLOUD_NOTE_ARRAY_API_URL = os.environ.get("VESTABOARD_CLOUD_API_URL") or "https://cloud.vestaboard.com/"

#: The device-native transition strategies the Local API animates, in the
#: order the API documents them.
#:
#: - ``column`` — Wave (left-to-right); ``reverse-column`` — Drift
#:   (right-to-left); ``edges-to-center`` — Curtain (outside-in);
#: - ``row``, ``diagonal``, ``random`` — API only.
VALID_STRATEGIES = ["column", "reverse-column", "edges-to-center", "row", "diagonal", "random"]

#: The send floors (seconds): one message per 15 seconds on both cloud APIs
#: (docs/setup/cloud-api.md); the Local API has no documented limit.
NOTE_ARRAY_MIN_SEND_INTERVAL: float = 15.0
CLOUD_MIN_SEND_INTERVAL: float = 15.0

#: Connection-level send retry: once, after a short backoff, only for errors
#: where the board never ACCEPTED the connection (:func:`is_retryable_send_error`).
SEND_MAX_ATTEMPTS: int = 2
SEND_RETRY_BACKOFF_SECONDS: float = 0.5

#: ``(connect, read)`` timeouts. LAN connects fail fast (an unreachable board
#: otherwise burns the whole timeout per attempt); the cloud gets a little
#: longer for DNS + TLS.
LOCAL_REQUEST_TIMEOUT: tuple[float, float] = (3.0, 10.0)
CLOUD_REQUEST_TIMEOUT: tuple[float, float] = (5.0, 10.0)

#: How many Notes a note array may be on each axis.
MAX_NOTES_PER_AXIS = 8
#: One Note's grid.
NOTE_ROWS, NOTE_COLS = 3, 15
#: A Flagship's and a Note's grid.
FLAGSHIP = (6, 22)
NOTE = (3, 15)

# Colour markers like {63}, {red}, {/}, {/red}.
COLOR_MARKER_PATTERN = re.compile(
    r"\{(?:"
    + r"/?"  # Optional closing slash
    + r"(?:"
    + r"6[3-9]|70|"  # Numeric codes 63-70
    + r"red|orange|yellow|green|blue|violet|purple|white|black"  # Named colors
    + r")?"  # Color name/code is optional for {/}
    + r")\}",
    re.IGNORECASE,
)


def strip_color_markers(text: str) -> str:
    """*text* without colour markers ({63}, {red}, {/}, {/red}): the text API
    would show them literally."""
    return COLOR_MARKER_PATTERN.sub("", text)


def is_retryable_send_error(exc: BaseException) -> bool:
    """True when the board never accepted the connection, so a retry is worth it.

    A refused or reset connection, or a DNS failure, means the board is not
    listening: the retry is cheap (the failure is immediate) and often wins —
    a board mid-reboot, a transient LAN blip. ``ConnectTimeout`` subclasses
    ``ConnectionError`` as well as ``Timeout`` and lands on this side for the
    same reason: no connection was established.

    A ``ReadTimeout`` is the opposite case. The board took the request and then
    went quiet, so it is wedged, and the second attempt pays the identical read
    timeout against the identical wedged board (#1754 measured a send to a
    wedged board going from 10.01s to 20.53s for nothing).
    """
    return isinstance(exc, requests.exceptions.ConnectionError)


def retry_after_seconds(response: Any, fallback: int | None) -> int | None:
    """Whole seconds a ``Retry-After`` header asks for, else *fallback*.

    Accepts both forms RFC 9110 allows: delta-seconds and an HTTP-date.
    """
    value = (getattr(response, "headers", None) or {}).get("Retry-After")
    if value:
        value = value.strip()
        if value.isdigit():
            return max(1, int(value))
        try:
            when = email.utils.parsedate_to_datetime(value)
        except (TypeError, ValueError):
            when = None
        if when is not None:
            if when.tzinfo is None:
                when = when.replace(tzinfo=UTC)
            return max(1, math.ceil((when - datetime.now(UTC)).total_seconds()))
    return fallback


def is_valid_note_array_grid(rows: int, cols: int) -> bool:
    """A note array's size: whole Notes on each axis, at most 8 each way."""
    if rows <= 0 or cols <= 0:
        return False
    if rows % NOTE_ROWS != 0 or cols % NOTE_COLS != 0:
        return False
    return (rows // NOTE_ROWS) <= MAX_NOTES_PER_AXIS and (cols // NOTE_COLS) <= MAX_NOTES_PER_AXIS


def is_valid_character_grid(rows: Any) -> bool:
    """True if *rows* is a rectangular int grid of a Vestaboard's size
    (Flagship, Note, or a note array)."""
    if not isinstance(rows, list) or not rows:
        return False
    first = rows[0]
    if not isinstance(first, list):
        return False
    ncols = len(first)
    nrows = len(rows)
    if (nrows, ncols) not in (FLAGSHIP, NOTE) and not is_valid_note_array_grid(nrows, ncols):
        return False
    for row in rows:
        if not isinstance(row, list) or len(row) != ncols:
            return False
        if not all(isinstance(c, int) for c in row):
            return False
    return True


def parse_read_message_payload(data: Any) -> list[list[int]] | None:
    """The character grid in a Local or Cloud read (``GET``) body.

    The Cloud API answers ``{"currentMessage": {"layout": "<json string>",
    "id": ...}}``; the Local API a raw grid or ``{"message": ...}``.
    """
    if isinstance(data, list):
        return data if is_valid_character_grid(data) else None
    if not isinstance(data, dict):
        return None
    if "message" in data:
        m = data.get("message")
        return m if isinstance(m, list) and is_valid_character_grid(m) else None
    cm = data.get("currentMessage")
    if isinstance(cm, dict) and "layout" in cm:
        layout = cm.get("layout")
        if layout is None or layout == "":
            return None
        if isinstance(layout, str):
            try:
                layout = json.loads(layout)
            except (json.JSONDecodeError, TypeError):
                return None
        if isinstance(layout, list) and is_valid_character_grid(layout):
            return layout
    return None


def is_successful_board_read_response(data: Any) -> bool:
    """True if a read body is a working read (a grid, or the explicit empty state)."""
    if parse_read_message_payload(data) is not None:
        return True
    return bool(isinstance(data, dict) and "currentMessage" in data and data.get("currentMessage") is None)
