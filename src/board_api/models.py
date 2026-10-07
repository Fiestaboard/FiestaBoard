"""Wire models for the out-of-band board surface (Phase 2, Task 8)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.api_deprecation import FLAT_BOARD_FIELDS_NOTE
from src.canvas.schemas import CanvasLayerModel


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


class WelcomeMessageRequest(BaseModel):
    """Optional body of ``POST /send-welcome-message``.

    ``board_id`` names the board to greet: the setup wizard names the board it
    just created (a TV, an output plugin's device), which need not be the
    primary — a seeded placeholder Vestaboard may still be first. Omitted →
    the primary board, exactly as before.
    """

    board_id: str | None = None


class SendResponse(BaseModel):
    """The outcome of an out-of-band write.

    ``sent`` is False when the content was identical to what the board
    already shows — the write was correctly skipped, not refused. Every other
    non-delivery (paused board, silence window, send floor, board failure) is
    a status code, not a flag.
    """

    message: str
    sent: bool


class BoardCurrentMessageResponse(BaseModel):
    """``GET /board/current-message`` — what is physically on the board."""

    #: The 2-D grid on the board. Null for a secondary board that has never
    #: been written to (issue #1247).
    characters: list[list[int]] | None = None
    #: The same frame as rich cells (FiestaUI ``BoardToken[][]`` JSON, as
    #: ``GET /panel/{id}/frame`` serves them), for a board whose output took
    #: them (an LED output: colour, case and icons ``characters`` cannot
    #: hold). Additive and present ONLY then; every other board's response is
    #: exactly what it was.
    cells: list[list[dict[str, Any]]] | None = None
    #: The page's pixel canvases on that frame (FiestaUI ``LedBitmapLayer``
    #: JSON: ``{x, y, width, height, rgba}``, rgba base64), drawn over
    #: ``cells``. Present ONLY for a pixel-matrix board (``[]`` when the frame
    #: has none).
    layers: list[CanvasLayerModel] | None = None
    #: ``characters`` rendered as the string form ``BoardDisplay`` takes.
    message: str | None = None
    rows: int
    cols: int
    #: What FiestaBoard last sent, which may differ from what is on the board
    #: if something else wrote to it. Null until the first send.
    expected_characters: list[list[int]] | None = None
    #: ISO timestamp of the poll this was served from; null on a live read.
    cached_at: str | None = None
    #: Deprecated (removed in v11): the flat connection mode, projected for
    #: compatibility (src/api_deprecation.py FLAT_BOARD_FIELDS).
    api_mode: str = Field(json_schema_extra={"deprecated": True}, description=FLAT_BOARD_FIELDS_NOTE)
    #: Echo of the requested board id; null means the primary board.
    board_id: str | None = None
