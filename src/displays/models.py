"""Pydantic models for the ``/displays`` API (Phase 2 slice 8).

A "display" is one plugin's formatted output. These endpoints predate the
plugin marketplace and are the oldest surface in the app; ``/displays/{id}/raw``
is already deprecated in favour of ``/plugins/{id}/data``.

The request model matters more than usual here: ``POST /displays/raw/batch``
used to take a bare ``dict`` and hand-roll its own ``isinstance(x, list)``
check. ``enabled_only`` is a ``StrictBool`` rather than a ``bool`` because
Pydantic's lax mode coerces ``"yes"``, ``1`` and ``"on"`` to ``True`` — which
would silently *widen* the contract the hand-rolled check had.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, StrictBool


class DisplayEntry(BaseModel):
    """One installed display source, as the picker lists it."""

    type: str = Field(description="Plugin id, e.g. 'weather'")
    available: bool = Field(description="Whether the plugin is enabled and configured")
    description: str = ""
    source: str = Field(default="plugin", description="Always 'plugin'; kept for older clients")


class DisplayListResponse(BaseModel):
    """``GET /displays``."""

    displays: list[DisplayEntry]
    total: int
    available_count: int


class DisplayResponse(BaseModel):
    """``GET /displays/{display_type}`` — formatted output ready for a board."""

    display_type: str
    message: str
    lines: list[str]
    line_count: int
    available: bool


class DisplayRawResponse(BaseModel):
    """``GET /displays/{display_type}/raw`` — pre-formatting plugin data."""

    display_type: str
    data: dict[str, Any] | None = None
    available: bool
    error: str | None = None


class DisplayRawBatchRequest(BaseModel):
    """``POST /displays/raw/batch`` request body.

    ``display_types`` defaults to the empty list rather than being required so
    the endpoint keeps answering its own 400 ("display_types parameter
    required") for both the omitted and the empty case, exactly as it did
    before the conversion.
    """

    display_types: list[str] = Field(default_factory=list)
    enabled_only: StrictBool = True


class DisplayRawBatchEntry(BaseModel):
    """One source's slot in the batch response."""

    data: dict[str, Any] = Field(default_factory=dict)
    available: bool
    error: str | None = None


class DisplayRawBatchResponse(BaseModel):
    """``POST /displays/raw/batch``.

    ``total`` counts what was *asked for*; ``displays`` holds what came back,
    which is smaller when ``enabled_only`` filtered a source out.
    """

    displays: dict[str, DisplayRawBatchEntry]
    total: int
    successful: int


class DisplaySendResponse(BaseModel):
    """``POST /displays/{display_type}/send``."""

    status: str = "success"
    display_type: str
    message: str
    sent_to_board: bool
    paused: bool = Field(description="True when the send was skipped because the board is paused")
    target: str
