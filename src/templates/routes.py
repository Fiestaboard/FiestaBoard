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

from src.api_errors import errors
from src.board_client import board_client_from_board_dict
from src.board_guards import _board_is_paused, _require_board
from src.board_send_executor import run_board_preview
from src.devices import resolve_dimensions
from src.plugins.registry import get_plugin_registry
from src.settings.service import get_settings_service
from src.text_to_board import text_to_board_array

from .engine import get_template_engine
from .expressions import function_signatures
from .models import (
    FormulaFunctionsResponse,
    TemplateRenderLiveRequest,
    TemplateRenderLiveResponse,
    TemplateRenderRequest,
    TemplateRenderResponse,
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
@router.get("/templates/variables", response_model=TemplateVariablesResponse)
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
            "filters": ["pad:N", "truncate:N", "wrap"],
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

    Returns validation errors if any.
    """
    template = request.template

    # Handle both string and list input
    if isinstance(template, list):
        template = "\n".join(template)

    template_engine = get_template_engine()
    problems = template_engine.validate_template(template)

    return TemplateValidationResponse(
        valid=len(problems) == 0,
        errors=[{"line": e.line, "column": e.column, "message": e.message} for e in problems],
    )


# No 4xx of its own: the function table is a module-level constant, so this
# route cannot fail on anything the caller controls. See the declared_errors
# exception in tests/conventions_manifest.json.
@router.get("/templates/formula-functions", response_model=FormulaFunctionsResponse)
async def get_formula_functions():
    """
    Return metadata for every built-in formula function.

    Response shape:
      { "functions": { NAME: { "category": str, "signature": str, "summary": str } } }

    Intended for editor tooling (autocomplete, function picker).
    """
    return FormulaFunctionsResponse.model_validate({"functions": function_signatures()})


@router.post("/templates/render", response_model=TemplateRenderResponse, responses=errors(400, 422))
async def render_template(request: TemplateRenderRequest):
    """
    Render a template with current data.

    Body should include:
    - template: Template string or list of lines to render

    Useful for previewing template output before saving as a page.
    """
    template = request.template
    device_type = request.device_type

    # Determine line count from device type
    from src.devices import DEFAULT_DEVICE_TYPE, DEVICE_DIMENSIONS

    dims = DEVICE_DIMENSIONS.get(device_type or DEFAULT_DEVICE_TYPE, DEVICE_DIMENSIONS[DEFAULT_DEVICE_TYPE])
    num_rows = dims.rows

    # Early return for empty templates to avoid unnecessary processing
    blank = TemplateRenderResponse(rendered="\n".join([""] * num_rows), lines=[""] * num_rows, line_count=num_rows)
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
                template_engine.render_lines, template, line_metadata=line_metadata, device_type=device_type
            )
        else:
            logger.info(f"Rendering template string: {template}")
            rendered = await asyncio.to_thread(template_engine.render, template)

        lines = rendered.split("\n")
        return TemplateRenderResponse(rendered=rendered, lines=lines, line_count=len(lines))
    except Exception as e:
        logger.error(f"Template rendering error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Template rendering failed: {str(e)}") from e


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
    device_type = request.device_type

    # Determine line count from device type
    from src.devices import DEFAULT_DEVICE_TYPE, DEVICE_DIMENSIONS

    dims = DEVICE_DIMENSIONS.get(device_type or DEFAULT_DEVICE_TYPE, DEVICE_DIMENSIONS[DEFAULT_DEVICE_TYPE])
    num_rows = dims.rows

    # Render the template
    try:
        if isinstance(template, list):
            if not template or all(not line.strip() for line in template):
                return TemplateRenderLiveResponse(
                    rendered="\n".join([""] * num_rows),
                    lines=[""] * num_rows,
                    line_count=num_rows,
                    sent_to_board=False,
                    board_id=board_id,
                )
            rendered = await asyncio.to_thread(
                template_engine.render_lines, template, line_metadata=line_metadata, device_type=device_type
            )
        else:
            if not template.strip():
                return TemplateRenderLiveResponse(
                    rendered="\n".join([""] * num_rows),
                    lines=[""] * num_rows,
                    line_count=num_rows,
                    sent_to_board=False,
                    board_id=board_id,
                )
            rendered = await asyncio.to_thread(template_engine.render, template)
    except Exception as e:
        logger.error(f"Template rendering error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Template rendering failed: {str(e)}") from e

    # Find the target board
    board_settings = settings_service.get_board_settings()
    boards = board_settings.boards if board_settings else []

    target_board = None
    if board_id:
        target_board = _require_board(board_id)
    elif boards:
        target_board = boards[0]

    sent_to_board = False
    paused = False
    if target_board:
        # Block when the target board is paused (issue #970). Render is still
        # returned to the caller so the live editor preview keeps updating.
        if _board_is_paused(board_id=target_board.get("id")):
            logger.info("Board %s is paused - skipping live template send", target_board.get("id"))
            paused = True
        else:
            client = board_client_from_board_dict(target_board)
            if client:
                device_type = target_board.get("device_type", "flagship")
                dims = resolve_dimensions(
                    device_type,
                    target_board.get("notes_wide", 1),
                    target_board.get("notes_tall", 1),
                )
                board_array = text_to_board_array(rendered, rows=dims.rows, cols=dims.cols)

                transition_settings = settings_service.get_transition_settings()
                # Live editor sends are rapid-fire; a "plugin:<id>" system
                # default would run a multi-second frame animation per edit
                # (and this ad-hoc client has no transition runner attached).
                # Fall back to an instant send for plugin strategies.
                from src.board_client import TRANSITION_PLUGIN_PREFIX

                live_strategy = transition_settings.strategy
                if isinstance(live_strategy, str) and live_strategy.startswith(TRANSITION_PLUGIN_PREFIX):
                    live_strategy = None
                try:
                    # Live-editor previews get their own bounded pool (#1878):
                    # rapid-fire keystroke sends must not occupy the workers
                    # /refresh, /force-refresh and POST /pages/{id}/send need.
                    success, was_sent = await run_board_preview(
                        client.send_characters,
                        board_array,
                        strategy=live_strategy,
                        step_interval_ms=transition_settings.step_interval_ms,
                        step_size=transition_settings.step_size,
                        force=True,
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
