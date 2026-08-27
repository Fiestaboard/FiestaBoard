"""Pydantic models for FiestaPanel panels.

A panel pairs a virtual board (which the platform drives like any other
board) with the display configuration a TV needs to render it at true
physical scale: screen size, calibration nudge, backdrop, and auto-dim.
"""

import re
import secrets
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Panel ids go in unauthenticated URLs; long random slugs keep them
# unguessable-by-accident (they are NOT treated as secrets).
_PANEL_ID_BYTES = 9  # token_urlsafe(9) -> 12 chars

_TIME_RE = re.compile(r"([01]\d|2[0-3]):[0-5]\d")

BackdropStyle = Literal["wall", "dark", "none"]


def _generate_panel_id() -> str:
    return secrets.token_urlsafe(_PANEL_ID_BYTES)


class AutoDim(BaseModel):
    """Night-time dimming window, evaluated against the TV's local clock."""

    enabled: bool = False
    start: str = "22:00"
    end: str = "07:00"

    @field_validator("start", "end")
    @classmethod
    def _validate_hh_mm(cls, v: str) -> str:
        if not _TIME_RE.fullmatch(v):
            raise ValueError(f"Invalid time {v!r}; expected HH:MM (24h)")
        return v


class Panel(BaseModel):
    """A FiestaPanel: display config for one virtual board."""

    id: str = Field(default_factory=_generate_panel_id)
    name: str = Field(min_length=1, max_length=100)
    board_id: str
    screen_diagonal_inches: float = Field(default=55.0, ge=10.0, le=200.0)
    calibration_scale: float = Field(default=1.0, ge=0.85, le=1.15)
    backdrop: BackdropStyle = "wall"
    auto_dim: AutoDim = Field(default_factory=AutoDim)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PanelCreate(BaseModel):
    """Request model for creating a panel (its virtual board is co-created).

    No shape is chosen: the board's grid is auto-fit from the screen size
    (see src/panels/autofit.py).
    """

    name: str = Field(min_length=1, max_length=100)
    screen_diagonal_inches: float = Field(default=55.0, ge=10.0, le=200.0)


class PanelUpdate(BaseModel):
    """Request model for updating a panel; all fields optional."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    screen_diagonal_inches: float | None = Field(default=None, ge=10.0, le=200.0)
    calibration_scale: float | None = Field(default=None, ge=0.85, le=1.15)
    backdrop: BackdropStyle | None = None
    auto_dim: AutoDim | None = None
