"""Wire models for the out-of-band board surface (Phase 2, Task 8)."""

from __future__ import annotations

from pydantic import BaseModel, StrictBool


class MessageRequest(BaseModel):
    """Body of ``POST /send-message``.

    ``board_id`` closes the gap that made board 2 unreachable over HTTP: the
    MCP executor (``src.ops.executors.send_message``) has taken one since
    issue #1765, and this endpoint — the one the published docs recommend —
    had no spelling for it. Omitted → the primary board, which is exactly
    what every existing caller gets today.
    """

    text: str
    board_id: str | None = None
    override_silence: StrictBool = False


class SendResponse(BaseModel):
    """The outcome of an out-of-band write.

    ``sent`` is False for unchanged content or a held message. Accepted
    silence holds return 202 with ``held`` and ``silenced`` true; refusals,
    pause, send-floor throttles and board failures keep their error status.
    """

    message: str
    sent: bool
    silenced: bool = False
    held: bool = False
    ends_at_utc: str | None = None


class BoardCurrentMessageResponse(BaseModel):
    """``GET /board/current-message`` — what is physically on the board."""

    #: The 2-D grid on the board. Null for a secondary board that has never
    #: been written to (issue #1247).
    characters: list[list[int]] | None = None
    #: ``characters`` rendered as the string form ``BoardDisplay`` takes.
    message: str | None = None
    rows: int
    cols: int
    #: What FiestaBoard last sent, which may differ from what is on the board
    #: if something else wrote to it. Null until the first send.
    expected_characters: list[list[int]] | None = None
    #: ISO timestamp of the poll this was served from; null on a live read.
    cached_at: str | None = None
    api_mode: str
    #: Echo of the requested board id; null means the primary board.
    board_id: str | None = None
