"""One reader for "what is on the board" (issue #1912).

Three surfaces answer the same question — the grid of flap codes a board is
actually showing — from the same caches:

* ``GET /board/current-message`` (``src/board_api/routes.py``), which may
  also read the board live;
* ``GET /panel/{panel_id}/frame`` (``src/panels/routes.py``), the
  unauthenticated TV viewer, which must never read a physical board live;
* the MCP ``get_board_content`` tool (``src/mcp_server.py``), which reports
  which cache answered.

Each used to carry its own copy of the selection ("the poll cache, else what
the client last sent, else ..."), and the copies had drifted: only one could
live-read, only one reported a source, only one respected the virtual
board's shape guard. This module is the single implementation. The routes
and the tool decide *presentation* (field names, error transport, which
timestamp their contract publishes); the *selection* lives here, and nothing
outside this module reads ``_polled_characters`` / ``_last_characters``.

Selection order
---------------
Given the board's runtime (its client plus the per-board poll cache):

1. ``force_live`` — read the board now, prime the poll cache, ``"live"``.
   A read that answers nothing raises :class:`BoardReadError`; the caller's
   contract decides what that means (a 503, say).
2. The poll cache, when populated — ``"polled"``, stamped with the poll
   time.
3. ``allow_live`` and no poll cache — as (1).
4. A **virtual** board reads from its own memory: that memory *is* the
   board, the read is not I/O, and it refuses a frame whose shape no longer
   matches the board (a re-fit left it behind). ``"live"`` — or ``"empty"``
   when it refuses, deliberately *not* falling through to the last-sent
   cache, which would serve the stale-shape frame the guard exists to hide.
5. What the client last sent — ``"last_sent"``.
6. ``"empty"``.

``board_id`` ``None`` means the primary board. The primary is always served
from the primary caches (``service.vb_client`` and the primary poll cache)
even when asked for by its own id, because legacy installs key the primary
runtime under a sentinel rather than its settings id (#1874 review).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Literal

logger = logging.getLogger(__name__)

Source = Literal["polled", "last_sent", "live", "empty"]


class BoardReadError(RuntimeError):
    """A live read was asked for and the board answered nothing."""

    def __init__(self, board_id: str | None):
        super().__init__(f"Failed to read current board message (board_id={board_id})")
        self.board_id = board_id


@dataclass(frozen=True)
class BoardState:
    """What one board shows, and where that answer came from.

    ``timestamp`` is when the grid was observed: the poll time for
    ``"polled"``, the moment of the read for ``"live"``, the send time for
    ``"last_sent"`` (only virtual clients track one), ``None`` for
    ``"empty"``. ``last_sent_at`` is published separately because the panel
    viewer reports it whatever the source. ``expected_characters`` is what
    the client last sent — the other half of drift detection.
    """

    board_id: str | None
    characters: list[list[int]] | None
    source: Source
    timestamp: float | None
    last_sent_at: float | None
    expected_characters: list[list[int]] | None
    client: Any | None

    @property
    def rows(self) -> int:
        return len(self.characters) if self.characters is not None else 0

    @property
    def cols(self) -> int:
        return len(self.characters[0]) if self.characters else 0


#: Default for ``read_board_state(service=...)``: resolve the display service
#: at call time. Distinct from ``None`` so a caller that already resolved it
#: (and got nothing) can say so instead of triggering a second resolution.
_RESOLVE_SERVICE: Any = object()


def _primary_board_id() -> str | None:
    """The settings-declared primary board id, or None when unknowable."""
    from . import display_runtime

    try:
        return display_runtime.get_settings_service().get_primary_board_id()
    except Exception as exc:  # settings unreadable → treat every id as secondary
        logger.debug("Could not resolve the primary board id: %s", exc)
        return None


def _empty(board_id: str | None) -> BoardState:
    return BoardState(
        board_id=board_id,
        characters=None,
        source="empty",
        timestamp=None,
        last_sent_at=None,
        expected_characters=None,
        client=None,
    )


def read_board_state(
    board_id: str | None = None,
    *,
    allow_live: bool = False,
    force_live: bool = False,
    service: Any = _RESOLVE_SERVICE,
) -> BoardState:
    """Select what *board_id* is showing from the display service's caches.

    Args:
        board_id: Board to read; ``None`` (or the primary's own id) means
            the primary board. An id with no runtime answers ``"empty"`` —
            whether the board *exists* is the caller's verdict to make
            (``_require_board`` → 404, ``ToolError``, ...).
        allow_live: Permit a live ``read_current_message()`` on the board's
            client when the poll cache is empty. Network I/O on a physical
            board; leave it off on any surface a viewer polls unattended.
        force_live: Read the board now even if the poll cache is populated.
            Implies ``allow_live``.
        service: The ``DisplayService`` to read from. Defaults to resolving
            it at call time; pass what you already resolved (even ``None``)
            so one request never resolves it twice.

    Raises:
        BoardReadError: a live read was attempted and returned nothing.
    """
    if service is _RESOLVE_SERVICE:
        from . import display_runtime

        service = display_runtime.get_service()
    if service is None:
        return _empty(board_id)

    if board_id is None or board_id == _primary_board_id():
        client = service.vb_client
        polled = service._polled_characters
        polled_at = service._polled_at

        def prime(characters: list[list[int]], at: float) -> None:
            service._polled_characters = characters
            service._polled_at = at

    else:
        rt = service.get_runtime(board_id)
        if rt is None:
            return _empty(board_id)
        client = rt.client
        polled = rt.polled_characters
        polled_at = rt.polled_at

        def prime(characters: list[list[int]], at: float) -> None:
            rt.polled_characters = characters
            rt.polled_at = at

    expected = getattr(client, "_last_characters", None) if client is not None else None
    last_sent_at = getattr(client, "_last_sent_at", None) if client is not None else None

    def state(characters: list[list[int]] | None, source: Source, timestamp: float | None) -> BoardState:
        return BoardState(
            board_id=board_id,
            characters=characters,
            source=source,
            timestamp=timestamp,
            last_sent_at=last_sent_at,
            expected_characters=expected,
            client=client,
        )

    if client is not None and (force_live or (allow_live and polled is None)):
        characters = client.read_current_message()
        if characters is None:
            raise BoardReadError(board_id)
        now = time.time()
        prime(characters, now)
        return state(characters, "live", now)

    if polled is not None:
        return state(polled, "polled", polled_at)

    if client is not None and getattr(client, "is_virtual", False):
        characters = client.read_current_message()
        if characters is None:
            return state(None, "empty", None)
        return state(characters, "live", time.time())

    if expected is not None:
        return state(expected, "last_sent", last_sent_at)

    return state(None, "empty", None)
