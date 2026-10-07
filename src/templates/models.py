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

from pydantic import BaseModel, Field, field_validator, model_validator

from src.canvas.models import Canvas, validate_page_canvases
from src.canvas.schemas import CanvasIssueModel, CanvasLayerModel

from src.devices import (
    ABSOLUTE_MIN_GRID_COLS,
    ABSOLUTE_MIN_GRID_ROWS,
    MAX_GRID_COLS,
    MAX_GRID_ROWS,
    MAX_NOTES_PER_AXIS,
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
    """``POST /templates/validate`` request body.

    ``board_id`` validates for that board: line length is measured in the
    tiles it draws, so extended markup (spans, blocks, icons) counts by its
    cells when the board's character set is rich (plan D19). An unknown board
    validates as split-flap, exactly as with no ``board_id``.
    """

    template: str | list[str]
    board_id: str | None = None


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

    ``board_id`` renders for that board: with extended markup when its
    output's character set is rich (plan D19), and — on ``/templates/render``
    — checked against that set (see :class:`TemplateRenderResponse`). It
    does not choose the geometry; the fields above do. An unknown board is a
    read's safe default: rendered as split-flap, nothing checked.
    """

    template: str | list[str]
    board_id: str | None = None
    device_type: DeviceType | None = None
    notes_wide: int = Field(default=1, ge=1, le=MAX_NOTES_PER_AXIS)
    notes_tall: int = Field(default=1, ge=1, le=MAX_NOTES_PER_AXIS)
    grid_rows: int | None = Field(default=None, ge=ABSOLUTE_MIN_GRID_ROWS, le=MAX_GRID_ROWS)
    grid_cols: int | None = Field(default=None, ge=ABSOLUTE_MIN_GRID_COLS, le=MAX_GRID_COLS)
    line_metadata: list[dict[str, Any]] | None = None
    #: The page's pixel canvases (``POST /templates/render`` only; the live
    #: render ignores them). Their cells are blanked (or text flows around a
    #: ``flow`` canvas) on every board; for a pixel-matrix ``board_id`` the
    #: response also carries their ``layers`` and ``canvas_issues``.
    canvases: list[Canvas] | None = None

    @field_validator("canvases")
    @classmethod
    def _canvases_valid(cls, value: list[Canvas] | None) -> list[Canvas] | None:
        return None if value is None else validate_page_canvases(value)

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


class CharsetIssue(BaseModel):
    """One cell the target board's character set cannot draw as written
    (FiestaUI ``CharsetValidationIssue``; tokens in its ``BoardToken`` JSON).

    ``reason`` is ``char``, ``case``, ``tile``, ``icon``, ``colorSpan`` or
    ``blockSpan``; ``fallback`` is what the board draws there instead.
    """

    row: int
    col: int
    token: dict[str, Any]
    reason: str
    fallback: dict[str, Any]


class TemplateRenderCheckedResponse(TemplateRenderResponse):
    """``POST /templates/render``, as the editor's warnings read it.

    ``charset`` / ``charset_issues`` are present only when the request named
    a ``board_id`` (the response is otherwise exactly what it always was):
    the board's character set id and every cell of the rendered message
    that set draws differently (``validateMessage`` parity, plan D17). Both
    are null when the board is unknown or its set is (a FiestaPanel):
    nothing was checked.
    """

    charset: str | None = None
    charset_issues: list[CharsetIssue] | None = None
    #: The request's canvases rasterised for its ``board_id`` when that board
    #: is a pixel matrix. Present ONLY then; draw them over the cells.
    layers: list[CanvasLayerModel] | None = None
    #: Problems drawing those canvases. Present exactly when ``layers`` is.
    canvas_issues: list[CanvasIssueModel] | None = None


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
