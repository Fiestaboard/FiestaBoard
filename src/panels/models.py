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
    # Small sequential number for TV-typable URLs (/p/1). Assigned by
    # storage at creation; 0 means "not yet assigned".
    short_code: int = Field(default=0, ge=0)
    name: str = Field(min_length=1, max_length=100)
    board_id: str
    screen_diagonal_inches: float = Field(default=55.0, ge=3.0, le=200.0)
    # Screen aspect ratio (width:height). 16:9 covers almost every TV;
    # ultrawides (21:9), 4:3 signage and portrait installs (9:16) change
    # how many Note blocks the auto-fit grid can hold.
    screen_aspect_w: float = Field(default=16.0, ge=1.0, le=100.0)
    screen_aspect_h: float = Field(default=9.0, ge=1.0, le=100.0)
    calibration_scale: float = Field(default=1.0, ge=0.85, le=1.15)
    # Mechanical flip animation on the viewer. Off by default: on a large
    # auto-fit grid the spin reads slow and busy — characters just update
    # in place. The toggle stays for people who want the theater.
    animations_enabled: bool = False
    # Exactly one panel may hold the local-display role at a time: it is the
    # one served by the reserved /p/display viewer URL (FiestaPi HDMI kiosk).
    # The service enforces the single-holder invariant on update.
    is_display: bool = False
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
    screen_diagonal_inches: float = Field(default=55.0, ge=3.0, le=200.0)
    screen_aspect_w: float = Field(default=16.0, ge=1.0, le=100.0)
    screen_aspect_h: float = Field(default=9.0, ge=1.0, le=100.0)


class PanelUpdate(BaseModel):
    """Request model for updating a panel; all fields optional."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    screen_diagonal_inches: float | None = Field(default=None, ge=3.0, le=200.0)
    screen_aspect_w: float | None = Field(default=None, ge=1.0, le=100.0)
    screen_aspect_h: float | None = Field(default=None, ge=1.0, le=100.0)
    calibration_scale: float | None = Field(default=None, ge=0.85, le=1.15)
    animations_enabled: bool | None = None
    is_display: bool | None = None
    backdrop: BackdropStyle | None = None
    auto_dim: AutoDim | None = None


# ---------------------------------------------------------------------------
# API response models (Phase 2 slice 8)
#
# Every panel payload the API serves is a Panel plus the geometry of the
# virtual board behind it, which the TV viewer scales itself from. The board
# fields are optional-with-null rather than absent so a panel whose board was
# deleted out from under it (``board_missing: true``) has the same shape as a
# healthy one — the client branches on the value, never on the key.
# ---------------------------------------------------------------------------


class PanelBoardFields(BaseModel):
    """Board-derived fields attached to every panel payload."""

    device_type: str | None = None
    board_missing: bool = False
    rows: int | None = None
    cols: int | None = None


class PanelResponse(Panel, PanelBoardFields):
    """A panel plus its board's shape — the app's view of one panel."""


class PanelListResponse(BaseModel):
    """``GET /panels``."""

    panels: list[PanelResponse]
    total: int


class IncompatiblePanelReference(BaseModel):
    """A page that no longer fits a panel's board after a screen-size re-fit.

    Warn-only, exactly like ``PUT /pages/{id}`` after a size retarget (#1250):
    the reference is left in place and the caller decides what to do.
    """

    page_id: str
    page_name: str
    surface: str
    schedule_id: str | None = None


class PanelUpdateResponse(PanelResponse):
    """``PATCH /panels/{panel_id}``.

    ``incompatible_references`` is null unless the screen size changed and the
    board was re-fit — it was previously an intermittently-present key, which
    forced the client to distinguish "absent" from "empty".
    """

    incompatible_references: list[IncompatiblePanelReference] | None = None


class PanelDeleteResponse(BaseModel):
    """``DELETE /panels/{panel_id}`` — the id that is now gone."""

    id: str


class PanelPublicResponse(PanelResponse):
    """``GET /panel/{panel_id}`` — the unauthenticated viewer's config.

    Adds the two presentation facts a TV needs and the app does not: which
    colour of board it is imitating, and which glyph flap code 62 paints on
    this hardware.
    """

    board_color: str | None = None
    code62_glyph: str | None = None


class PanelFrameResponse(BaseModel):
    """``GET /panel/{panel_id}/frame`` — what the panel's board shows now.

    ``characters`` is null until something has been sent to the board; the
    geometry is still reported so the viewer can lay itself out and render a
    blank grid rather than collapsing.
    """

    characters: list[list[int]] | None = None
    message: str | None = None
    rows: int
    cols: int
    updated_at: str | None = None
