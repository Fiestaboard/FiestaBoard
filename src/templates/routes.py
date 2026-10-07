"""FastAPI router for the template variables / validation / render endpoints.

Handlers were moved here verbatim from ``src/api_server.py`` (Phase 2 slice 8,
Task 8) and the conventions pass was applied in the same commit.

Collaborators resolve from their canonical homes at **module import time**, so
this module never loads ``src.api_server``
(``tests/test_small_domains_decoupled.py`` asserts that in a fresh
interpreter). Tests that need to stub a collaborator patch it where this
module binds it — ``src.templates.routes.<name>`` — not
``src.api_server.<name>``.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from src.api_deprecation import superseded_by_v1
from src.api_errors import errors
from src.board_guards import _board_is_paused, _find_board, _require_board
from src.board_send_executor import run_board_preview
from src.devices import geometry_of, resolve_dimensions
from src.display_runtime import live_driver
from src.led.charsets import has_extended_markup, validate_message
from src.outputs.board_profile import board_character_set
from src.outputs.cells import extended_markup_kw, project_for_output
from src.plugins.registry import get_plugin_registry
from src.settings.service import get_settings_service
from src.text_to_board import text_to_board_array

from .engine import get_template_engine
from .expressions import function_signatures
from .filters import TEMPLATE_FILTERS
from .models import (
    FormulaFunctionsResponse,
    TemplateRenderCheckedResponse,
    TemplateRenderLiveRequest,
    TemplateRenderLiveResponse,
    TemplateRenderRequest,
    TemplateValidateRequest,
    TemplateValidationResponse,
    TemplateVariablesResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["templates"])


# No 4xx of its own: it reads the in-process template engine and plugin
# registry, both of which always exist — an install with no plugins answers
# empty catalogs. See the declared_errors exception in
# tests/conventions_manifest.json.
@router.get(
    "/templates/variables",
    response_model=TemplateVariablesResponse,
    dependencies=[superseded_by_v1("GET /templates/variables")],
)
async def get_template_variables():
    """
    Get available template variables by source.

    Returns a dictionary mapping source names to available field names.
    Use these in templates as {{source.field}}, e.g., {{weather.temperature}}.
    Also includes rich metadata (descriptions, types, previews) and variable
    groups when declared by the plugin.
    """
    template_engine = get_template_engine()
    registry = get_plugin_registry()

    # ``get_all_variables_with_metadata`` builds a FETCH-ALL template context,
    # and ``get_available_variables`` can trigger an auto-discovery fetch, so
    # this route can block for the full context-build budget. It is an
    # ``async def``, which means that block would be the whole event loop.
    variables, max_lengths, metadata, groups = await asyncio.to_thread(
        lambda: (
            template_engine.get_available_variables(),
            template_engine.get_variable_max_lengths(),
            registry.get_all_variables_with_metadata(),
            registry.get_all_variable_groups(),
        )
    )

    return TemplateVariablesResponse.model_validate(
        {
            "variables": variables,
            "max_lengths": max_lengths,
            "variable_metadata": metadata,
            "variable_groups": groups,
            "colors": {
                "red": 63,
                "orange": 64,
                "yellow": 65,
                "green": 66,
                "blue": 67,
                "violet": 68,
                "white": 69,
                "black": 70,
            },
            "symbols": ["sun", "star", "cloud", "rain", "snow", "storm", "fog", "partly", "heart", "check", "x"],
            # From the one roster the engine, the MCP instructions and the chat
            # prompt all read, so the editor cannot advertise a different set
            # (this list used to omit the real ``zeropad:N``).
            "filters": [spelling for spelling, _summary in TEMPLATE_FILTERS],
            "formatting": {
                "fill_space": {
                    "syntax": "{{fill_space}}",
                    "description": "Expands to fill remaining space on the line. Use multiple for multi-column layouts.",
                },
                "fill_space_repeat": {
                    "syntax": "{{fill_space_repeat:pattern}}",
                    "description": "Fills remaining space with repeating colors or characters. Examples: {{fill_space_repeat:red}} or {{fill_space_repeat:-}}",
                },
            },
            "syntax_examples": {
                "variable": "{{weather.temperature}}",
                "variable_with_filter": "{{weather.temperature|pad:3}}",
                "color_inline": "{{red}} Warning {{red}}",
                "color_code": "{63}",
                "symbol": "{sun}",
                "wrap": "{{star_trek.quote|wrap}}",
                "fill_space": "Left{{fill_space}}Right",
                "fill_space_three_columns": "A{{fill_space}}B{{fill_space}}C",
            },
        }
    )


@router.post("/templates/validate", response_model=TemplateValidationResponse, responses=errors(422))
async def validate_template(request: TemplateValidateRequest):
    """
    Validate template syntax.

    Body should include:
    - template: Template string or list of lines to validate
    - board_id: Optional board to validate for; a board whose character set
      is rich measures line length in the tiles it draws (extended markup)

    Returns validation errors if any.
    """
    template = request.template

    # Handle both string and list input
    if isinstance(template, list):
        template = "\n".join(template)

    template_engine = get_template_engine()
    problems = template_engine.validate_template(template, **_CharsetCheck(request.board_id).render_kw)

    return TemplateValidationResponse(
        valid=len(problems) == 0,
        errors=[{"line": e.line, "column": e.column, "message": e.message} for e in problems],
    )


# No 4xx of its own: the function table is a module-level constant, so this
# route cannot fail on anything the caller controls. See the declared_errors
# exception in tests/conventions_manifest.json.
@router.get(
    "/templates/formula-functions",
    response_model=FormulaFunctionsResponse,
    dependencies=[superseded_by_v1("GET /templates/formula-functions")],
)
async def get_formula_functions():
    """
    Return metadata for every built-in formula function.

    Response shape:
      { "functions": { NAME: { "category": str, "signature": str, "summary": str } } }

    Intended for editor tooling (autocomplete, function picker).
    """
    return FormulaFunctionsResponse.model_validate({"functions": function_signatures()})


@router.post(
    "/templates/render",
    response_model=TemplateRenderCheckedResponse,
    # `charset` / `charset_issues` are set only for a board-targeted render,
    # so every other response is exactly what it always was.
    response_model_exclude_unset=True,
    responses=errors(400, 422),
)
async def render_template(request: TemplateRenderRequest):
    """
    Render a template with current data.

    Body should include:
    - template: Template string or list of lines to render

    Optional ``board_id``: render for that board — with extended markup when
    its output's character set is rich — and report ``charset`` and
    ``charset_issues``, every cell of the result that set draws differently
    (FiestaUI ``validateMessage`` parity), for the editor's warnings.

    Useful for previewing template output before saving as a page.
    """
    template = request.template
    check = _CharsetCheck(request.board_id)
    device_type, notes_wide, notes_tall, grid_rows, grid_cols = _render_geometry(request, check.board)

    # Row count must come from the same geometry ``render_lines`` renders at.
    # A ``DEVICE_DIMENSIONS`` lookup cannot: it has no ``note_array`` key, so
    # an array fell through to flagship's 6 rows on the blank path below while
    # the body rendered 3 rows of one note (issue #2032). ``board_context_for``
    # resolves every device type, arrays included, and falls back to the
    # default for an unknown one exactly as ``render_lines`` does.
    from src.devices import DEFAULT_DEVICE_TYPE, board_context_for

    dims = board_context_for(device_type or DEFAULT_DEVICE_TYPE, notes_wide, notes_tall, grid_rows, grid_cols)
    num_rows = dims.rows

    # Early return for empty templates to avoid unnecessary processing
    blank = TemplateRenderCheckedResponse(
        rendered="\n".join([""] * num_rows), lines=[""] * num_rows, line_count=num_rows, **check.result(None)
    )
    if isinstance(template, list):
        if not template or all(not line.strip() for line in template):
            return blank
    elif isinstance(template, str) and not template.strip():
        return blank

    template_engine = get_template_engine()
    line_metadata = request.line_metadata

    try:
        # Rendering fetches plugin data, so it belongs on a worker thread, not
        # on the event loop. The engine's own fetch is demand-driven, so a
        # template naming four variables fetches four plugins, not every one.
        if isinstance(template, list):
            logger.info(f"Rendering template lines: {template}")
            rendered = await asyncio.to_thread(
                template_engine.render_lines,
                template,
                line_metadata=line_metadata,
                device_type=device_type,
                notes_wide=notes_wide,
                notes_tall=notes_tall,
                grid_rows=grid_rows,
                grid_cols=grid_cols,
                **check.render_kw,
            )
        else:
            logger.info(f"Rendering template string: {template}")
            rendered = await asyncio.to_thread(template_engine.render, template, **check.render_kw)

        lines = rendered.split("\n")
        return TemplateRenderCheckedResponse(
            rendered=rendered, lines=lines, line_count=len(lines), **check.result(rendered)
        )
    except Exception as e:
        logger.error(f"Template rendering error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Template rendering failed: {str(e)}") from e


def _render_geometry(request, board: dict | None) -> tuple:
    """``(device_type, notes_wide, notes_tall, grid_rows, grid_cols)`` to render at.

    The request's own geometry when it names a device type; otherwise the
    target board's grid — a render for a 10x16 panel is 10x16, not the
    Flagship default (the engine already sends the board's grid).
    """
    if request.device_type is None and board is not None:
        return tuple(geometry_of(board))
    return (request.device_type, request.notes_wide, request.notes_tall, request.grid_rows, request.grid_cols)


class _CharsetCheck:
    """A render targeted at a board: how to render, and what to report.

    Every render speaks extended markup (plan D19; split-flap boards too
    since the Task 12 flip, :func:`src.outputs.cells.charset_extended_markup`).
    No board named: no extra fields. A board named: its resolved character
    set (plan D17) decides the issues reported; an unknown board, or one
    whose set is unknown (a FiestaPanel), reports ``charset: null`` and
    checks nothing.
    """

    def __init__(self, board_id: str | None) -> None:
        self.targeted = board_id is not None
        board = _find_board(board_id) if board_id is not None else None
        #: The board named, when it exists.
        self.board = board
        self.charset = board_character_set(board) if board is not None else None
        self.render_kw: dict = {"extended_markup": True} if has_extended_markup(self.charset) else {}

    def result(self, rendered: str | None) -> dict:
        if not self.targeted:
            return {}
        if self.charset is None:
            return {"charset": None, "charset_issues": None}
        issues = validate_message(rendered or "", self.charset).issues
        return {"charset": self.charset["id"], "charset_issues": [i.to_dict() for i in issues]}


@router.post("/templates/render/live", response_model=TemplateRenderLiveResponse, responses=errors(400, 404, 422))
async def render_template_live(request: TemplateRenderLiveRequest):
    """
    Render a template and send it to a board (live edit mode).

    Body should include:
    - template: Template string or list of lines to render
    - board_id: Optional board ID to target (defaults to first configured board)

    Returns the rendered result plus whether it was sent to the board.
    """
    template = request.template
    board_id = request.board_id

    template_engine = get_template_engine()
    settings_service = get_settings_service()
    line_metadata = request.line_metadata

    # The target board, resolved before rendering: a board whose output draws
    # a rich character set renders with its extended markup (plan D19), and
    # a request that names no geometry renders at the board's grid.
    # (An unknown board_id is a 404 only once there is something to send: a
    # blank template answers blank rows and touches no board.)
    board_settings = settings_service.get_board_settings()
    boards = board_settings.boards if board_settings else []
    target_board = None
    if board_id:
        target_board = _find_board(board_id)
    elif boards:
        target_board = boards[0]
    device_type, notes_wide, notes_tall, grid_rows, grid_cols = _render_geometry(request, target_board)

    # Same note-array-aware resolution as ``render_template`` above (#2032):
    # ``DEVICE_DIMENSIONS`` has no ``note_array`` key, so the blank path used
    # to answer flagship rows for an array.
    from src.devices import DEFAULT_DEVICE_TYPE, board_context_for

    dims = board_context_for(device_type or DEFAULT_DEVICE_TYPE, notes_wide, notes_tall, grid_rows, grid_cols)
    num_rows = dims.rows

    # A blank template answers blank rows and touches no board.
    if isinstance(template, list):
        blank = not template or all(not line.strip() for line in template)
    else:
        blank = not template.strip()
    if blank:
        return TemplateRenderLiveResponse(
            rendered="\n".join([""] * num_rows),
            lines=[""] * num_rows,
            line_count=num_rows,
            sent_to_board=False,
            board_id=board_id,
        )

    if board_id and target_board is None:
        _require_board(board_id)
    client = live_driver(target_board.get("id")) if target_board else None
    render_kw = extended_markup_kw(client)

    # Render the template
    try:
        if isinstance(template, list):
            rendered = await asyncio.to_thread(
                template_engine.render_lines,
                template,
                line_metadata=line_metadata,
                device_type=device_type,
                notes_wide=notes_wide,
                notes_tall=notes_tall,
                grid_rows=grid_rows,
                grid_cols=grid_cols,
                **render_kw,
            )
        else:
            rendered = await asyncio.to_thread(template_engine.render, template, **render_kw)
    except Exception as e:
        logger.error(f"Template rendering error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Template rendering failed: {str(e)}") from e

    sent_to_board = False
    paused = False
    if target_board:
        # Block when the target board is paused (issue #970). Render is still
        # returned to the caller so the live editor preview keeps updating.
        if _board_is_paused(board_id=target_board.get("id")):
            logger.info("Board %s is paused - skipping live template send", target_board.get("id"))
            paused = True
        else:
            # The board's LIVE driver: a live edit is a write of the board's
            # runtime — it preempts a running transition, shares the engine's
            # send lock and floor, and lands in the frame cache, so the engine
            # knows the board now shows the edit.
            if client:
                geometry = geometry_of(target_board)
                device_type = geometry.device_type
                dims = resolve_dimensions(*geometry)
                board_array, rich = project_for_output(client, rendered, dims.rows, dims.cols, flap=text_to_board_array)

                transition_settings = settings_service.get_transition_settings(target_board.get("id"))
                # Live editor sends are rapid-fire; a "plugin:<id>" system
                # default would run a multi-second frame animation per edit.
                # Fall back to an instant send for plugin strategies.
                from src.outputs.transitions import TRANSITION_PLUGIN_PREFIX

                live_strategy = transition_settings.strategy
                if isinstance(live_strategy, str) and live_strategy.startswith(TRANSITION_PLUGIN_PREFIX):
                    live_strategy = None
                try:
                    # Live-editor previews get their own bounded pool (#1878):
                    # rapid-fire keystroke sends must not occupy the workers
                    # /refresh, /force-refresh and POST /pages/{id}/send need.
                    success, was_sent = await run_board_preview(
                        client.render,
                        board_array,
                        strategy=live_strategy,
                        step_interval_ms=transition_settings.step_interval_ms,
                        step_size=transition_settings.step_size,
                        force=True,
                        **rich,
                    )
                    sent_to_board = was_sent
                except Exception as e:
                    logger.error(f"Live send to board failed: {e}", exc_info=True)

    lines = rendered.split("\n")
    return TemplateRenderLiveResponse(
        rendered=rendered,
        lines=lines,
        line_count=len(lines),
        sent_to_board=sent_to_board,
        paused=paused,
        board_id=target_board.get("id") if target_board else None,
    )
