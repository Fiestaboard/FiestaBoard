"""Wire models for the service surface (Phase 2, Task 8)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ApiInfoResponse(BaseModel):
    """``GET /`` — what this server is, for a human poking at the root."""

    name: str
    version: str
    status: str


class HealthResponse(BaseModel):
    """``GET|HEAD /health`` — the liveness probe nginx, Docker and the boot
    gate all use."""

    status: str
    service_running: bool
    version: str


class BoardStatus(BaseModel):
    """Per-board runtime state (issue #1244)."""

    configured: bool
    paused: bool
    active_page_id: str | None = None
    #: Why this board failed to get a client at startup, if it did (#1749).
    error: str | None = None


class StatusResponse(BaseModel):
    """``GET /status`` — the display loop's state plus a per-board breakdown."""

    running: bool
    initialized: bool
    config_summary: dict[str, Any]
    boards: dict[str, BoardStatus] = {}


class ServiceStateResponse(BaseModel):
    """``POST /start`` / ``POST /stop`` — the loop's state after the call.

    ``running`` is the state the caller asked about; ``changed`` says whether
    this request is what put it there, which is what the old
    ``"already_running"`` / ``"not_running"`` status words encoded.
    """

    running: bool
    changed: bool
    message: str


class RefreshRequest(BaseModel):
    """Optional body of ``POST /refresh``.

    ``board_id`` may also arrive as a query parameter; the query wins when
    both are present, which is what the pre-conversion handler did.
    """

    board_id: str | None = None


class RefreshResponse(BaseModel):
    """``POST /refresh`` — what the refresh pass did."""

    message: str
    #: The board that was refreshed; null means "every board, primary first".
    board_id: str | None = None
    #: Whether anything was actually written to a board (unchanged content
    #: and a UI-only output target both leave this False).
    sent: bool


class SilenceStatusResponse(BaseModel):
    """``GET /silence-status`` — the resolved silence window for one board."""

    enabled: bool
    active: bool
    start_time_utc: str
    end_time_utc: str
    current_time_utc: str
    next_change_utc: str
    #: Wall-clock seconds until the next active/inactive transition; null when
    #: silence is disabled and there is no transition to count down to.
    seconds_until_next_change: int | None = None
    mode: str | None = None
    page_id: str | None = None
    indicator_text: str | None = None
    indicator_position: str | None = None
    #: The board this window describes. Null only when no board is configured.
    board_id: str | None = None
