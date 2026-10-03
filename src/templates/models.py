"""Pydantic models for the ``/templates`` API (Phase 2 slice 8).

These endpoints are the page editor's backend: the variable catalog drives
autocomplete, the validator drives the inline error markers, and the two
render endpoints drive the preview pane and live-edit sends.

``template`` is ``str | list[str]`` everywhere because the editor sends a list
of lines and the older callers (and the MCP tools) send one string; both are
supported and the distinction is meaningful — a list is padded to the device's
row count, a bare string is not.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from src.devices import (
    MAX_GRID_COLS,
    MAX_GRID_ROWS,
    MAX_NOTES_PER_AXIS,
    MIN_GRID_COLS,
    MIN_GRID_ROWS,
    DeviceType,
)


class TemplateVariablesResponse(BaseModel):
    """``GET /templates/variables`` — everything the editor autocompletes on."""

    variables: dict[str, list[str]] = Field(description="Source name -> available field names")
    max_lengths: dict[str, int] = Field(description="Variable -> longest rendered width, for layout hints")
    variable_metadata: dict[str, Any] = Field(default_factory=dict)
    variable_groups: dict[str, Any] = Field(default_factory=dict)
    colors: dict[str, int] = Field(description="Colour name -> flap code (63-70)")
    symbols: list[str]
    filters: list[str]
    formatting: dict[str, Any]
    syntax_examples: dict[str, str]


class FormulaFunctionEntry(BaseModel):
    """One built-in formula function, as the function picker lists it."""

    category: str
    signature: str
    summary: str


class FormulaFunctionsResponse(BaseModel):
    """``GET /templates/formula-functions``."""

    functions: dict[str, FormulaFunctionEntry]


class TemplateValidateRequest(BaseModel):
    """``POST /templates/validate`` request body."""

    template: str | list[str]


class TemplateValidationError(BaseModel):
    """One syntax problem, positioned for the editor's gutter marker."""

    line: int
    column: int
    message: str


class TemplateValidationResponse(BaseModel):
    """``POST /templates/validate``.

    ``valid: false`` at 200 is the *verdict* this endpoint exists to report,
    not a failed request — the caller asked "is this template well formed?"
    and got an answer. The conventions ratchet's ``no_200_on_failure`` rule
    only flags a literal ``{"valid": False}`` constant, which this never
    returns; the field is computed from the error list.
    """

    valid: bool
    errors: list[TemplateValidationError]


class TemplateRenderRequest(BaseModel):
    """``POST /templates/render`` request body.

    ``device_type`` is the ``DeviceType`` Literal, not a bare string: the
    renderer falls back to flagship geometry for anything it does not know,
    so a typo used to render at the wrong size and answer 200.

    ``notes_wide``/``notes_tall`` size a ``note_array``, whose grid is not
    fixed: ``15·notes_wide`` columns by ``3·notes_tall`` rows. Without them
    the preview rendered every array as a single 3x15 Note, so a
    ``{{filled:-}}`` line stopped one note short of the board the same page
    filled correctly when sent (issue #2032). Bounds match
    :class:`src.pages.models.Page` so a page and its preview accept exactly
    the same geometry; both are ignored for ``flagship`` and ``note``.

    ``grid_rows``/``grid_cols`` size a ``panel`` (a FiestaPanel's explicit
    per-character grid) and are required for one: a panel has no implied
    size, so rendering without them would silently answer flagship geometry.
    """

    template: str | list[str]
    device_type: DeviceType | None = None
    notes_wide: int = Field(default=1, ge=1, le=MAX_NOTES_PER_AXIS)
    notes_tall: int = Field(default=1, ge=1, le=MAX_NOTES_PER_AXIS)
    grid_rows: int | None = Field(default=None, ge=MIN_GRID_ROWS, le=MAX_GRID_ROWS)
    grid_cols: int | None = Field(default=None, ge=MIN_GRID_COLS, le=MAX_GRID_COLS)
    line_metadata: list[dict[str, Any]] | None = None

    @model_validator(mode="after")
    def _panel_needs_a_grid(self) -> TemplateRenderRequest:
        if self.device_type == "panel" and (self.grid_rows is None or self.grid_cols is None):
            raise ValueError("A panel render needs grid_rows and grid_cols")
        return self


class TemplateRenderResponse(BaseModel):
    """``POST /templates/render``."""

    rendered: str
    lines: list[str]
    line_count: int


class TemplateRenderLiveRequest(TemplateRenderRequest):
    """``POST /templates/render/live`` request body."""

    board_id: str | None = None


class TemplateRenderLiveResponse(TemplateRenderResponse):
    """``POST /templates/render/live``.

    ``paused`` was already always present on this response; it stays a
    required field so the client can tell "nothing was sent because the board
    is paused" apart from "nothing was sent because there is no board".
    """

    sent_to_board: bool
    paused: bool = False
    board_id: str | None = None
