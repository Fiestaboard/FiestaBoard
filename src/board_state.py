"""One reader for "what is on the board" (issue #1912).

Four surfaces answer the same question — the grid of flap codes a board is
showing — from the same caches:

* ``GET /board/current-message`` (``src/board_api/routes.py``), which may
  also read the board live;
* ``GET /panel/{panel_id}/frame`` (``src/panels/routes.py``), the
  unauthenticated TV viewer, which must never read a physical board live;
* the MCP ``get_board_content`` tool (``src/mcp_server.py``), which reports
  which cache answered;
* ``GET /v1/boards/{board}`` (``src/v1/routes_boards.py``).

Each used to carry its own copy of the selection, and the copies had
drifted. This module is the single implementation. The routes and the tool
decide *presentation* (field names, error transport, which timestamp their
contract publishes); the *selection* lives here, and nothing outside this
module reads ``_polled_characters`` / ``_last_characters``.

Two intents
-----------
The surfaces do not all ask the same question, and the difference is real:

``want="board"``
    What the board *shows*. The background poll cache answers first — it is
    the only evidence of the physical flaps — then the fallbacks below.

``want="sent"``
    What FiestaBoard last *displayed or sent*, immediately. The panel viewer
    asks this: a write that never refreshes the poll cache (MQTT, a direct
    send, a transition restore) must reach the TV now, not after the next
    30 s / 3 min poll. The poll cache is never consulted.

Selection order
---------------
1. ``want="board"`` only: the poll cache, when populated — ``"polled"``,
   stamped with the poll time.
2. A **virtual** board reads from its own memory: that memory *is* the
   board, the read is a mutex and a copy, and it refuses a frame whose
   shape no longer matches the board (a re-fit left it behind). ``"live"``
   — or ``"empty"`` when it refuses, deliberately *not* falling through to
   the last-sent cache, which would serve the stale-shape frame the guard
   exists to hide. A refusal is never an error.
3. What the client last sent — ``"last_sent"``.
4. ``"empty"``.

:func:`read_board_state` does no I/O. :func:`read_board_state_live` is the
``want="board"`` read plus a network read of a physical board where the poll
cache cannot answer (or on ``force``), run off the event loop only then.

``board_id`` ``None`` means the primary board; ids resolve through
``DisplayService.runtime_for`` — the id's own runtime first, the primary
runtime for the settings primary's id only when nothing is keyed under it
(legacy installs key it under a sentinel, #1874 review).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, replace
from typing import Any, Literal

logger = logging.getLogger(__name__)

Source = Literal["polled", "last_sent", "live", "empty"]
Want = Literal["board", "sent"]


class BoardReadError(RuntimeError):
    """A live read of a physical board was attempted and it answered nothing."""

    def __init__(self, board_id: str | None):
        super().__init__(f"Failed to read current board message (board_id={board_id})")
        self.board_id = board_id


@dataclass(frozen=True)
class BoardState:
    """What one board shows, and where that answer came from.

    ``polled_at`` is set only when the poll cache answered (``source ==
    "polled"``). ``last_sent_at`` is when the client last stored a frame
    (only virtual clients track one) and is published whatever answered,
    because the panel viewer reports it regardless. ``expected_characters``
    is what the client last sent — the other half of drift detection.
    """

    board_id: str | None
    characters: list[list[int]] | None
    source: Source
    polled_at: float | None
    last_sent_at: float | None
    expected_characters: list[list[int]] | None
    api_mode: Literal["local", "cloud"]

    @property
    def rows(self) -> int:
        return len(self.characters) if self.characters is not None else 0

    @property
    def cols(self) -> int:
        return len(self.characters[0]) if self.characters else 0


def _empty(board_id: str | None) -> BoardState:
    return BoardState(
        board_id=board_id,
        characters=None,
        source="empty",
        polled_at=None,
        last_sent_at=None,
        expected_characters=None,
        api_mode="local",
    )


def _is_virtual(client: Any) -> bool:
    # ``VirtualBoardClient`` sets ``is_virtual = True``; a hardware client
    # has no such attribute. Tested with ``is True`` (main.py's convention)
    # so a Mock or proxy client's auto-attribute never earns a memory read.
    return getattr(client, "is_virtual", False) is True


def _polled_pair(rt: Any) -> tuple[list[list[int]] | None, float | None]:
    """The poll cache as one ``(characters, polled_at)`` pair.

    The poll thread writes the two fields in two statements. Reading
    ``polled_at`` on both sides of ``polled_characters`` and retrying when it
    moved keeps a poll landing mid-read from pairing new flaps with an old
    timestamp.
    """
    at = rt.polled_at
    for _ in range(3):
        characters = rt.polled_characters
        again = rt.polled_at
        if again == at:
            return characters, at
        at = again
    return rt.polled_characters, at


def _prime(rt: Any, characters: list[list[int]], at: float) -> None:
    rt.polled_characters = characters
    rt.polled_at = at


def _select(rt: Any, board_id: str | None, *, want: Want, skip_poll_cache: bool = False) -> BoardState:
    """The selection order above, over one resolved runtime. No I/O."""
    client = rt.client
    base = BoardState(
        board_id=board_id,
        characters=None,
        source="empty",
        polled_at=None,
        last_sent_at=getattr(client, "_last_sent_at", None) if client is not None else None,
        expected_characters=getattr(client, "_last_characters", None) if client is not None else None,
        api_mode="cloud" if getattr(client, "use_cloud", False) else "local",
    )

    if want == "board" and not skip_poll_cache:
        polled, polled_at = _polled_pair(rt)
        if polled is not None:
            return replace(base, characters=polled, source="polled", polled_at=polled_at)

    if _is_virtual(client):
        displayed = client.read_current_message()
        if displayed is None:
            return base
        return replace(base, characters=displayed, source="live")

    if base.expected_characters is not None:
        return replace(base, characters=base.expected_characters, source="last_sent")

    return base


def read_board_state(board_id: str | None, *, want: Want, service: Any) -> BoardState:
    """Select what *board_id* is showing from the display service's caches.

    Args:
        board_id: Board to read; ``None`` means the primary board. An id with
            no runtime answers ``"empty"`` — whether the board *exists* is
            the caller's verdict to make (``_require_board`` → 404,
            ``ToolError``, ...).
        want: ``"board"`` (what the flaps show; poll cache first) or
            ``"sent"`` (what FiestaBoard last displayed/sent; never the poll
            cache). See the module docstring.
        service: The ``DisplayService`` the caller already resolved — its
            ``None`` answers ``"empty"``. Passed explicitly because every
            surface resolves it through its own seam.

    Never performs I/O: a virtual board's memory read is a mutex and a
    copy, and a physical board is only ever served from its caches.
    """
    if service is None:
        return _empty(board_id)
    rt = service.runtime_for(board_id)
    if rt is None:
        return _empty(board_id)
    return _select(rt, board_id, want=want)


async def read_board_state_live(board_id: str | None, *, force: bool = False, service: Any) -> BoardState:
    """``want="board"``, plus a live read of a physical board where the poll
    cache cannot answer.

    The network read runs on a worker thread, and only when it happens: a
    populated poll cache (unless ``force``) and a virtual board's memory are
    served inline. A live read that succeeds primes the poll cache, so the
    next request is fast; a virtual board's memory read primes it too, as
    the poll thread would.

    Raises:
        BoardReadError: the physical board was read and answered nothing. A
            virtual board's refusal (nothing displayed, or a stale-shape
            frame) is ``"empty"``, never an error.
    """
    if service is None:
        return _empty(board_id)
    rt = service.runtime_for(board_id)
    if rt is None:
        return _empty(board_id)

    state = _select(rt, board_id, want="board", skip_poll_cache=force)
    client = rt.client
    if state.source == "polled" or client is None:
        return state
    if _is_virtual(client):
        if state.characters is not None:
            _prime(rt, state.characters, time.time())
        return state

    characters = await asyncio.to_thread(client.read_current_message)
    if characters is None:
        raise BoardReadError(board_id)
    _prime(rt, characters, time.time())
    return replace(state, characters=characters, source="live", polled_at=None)
