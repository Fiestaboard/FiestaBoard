"""``/v1/variables``, ``/v1/render``, ``/v1/functions``, ``/v1/health``, ``/v1/status``.

Everything a caller needs to *write* a template and to check the instance is
alive. ``GET /v1/variables`` is the merge the design names: the internal API
answers "what names can I use in a template" at two endpoints —
``GET /templates/variables`` for the engine's own vocabulary and
``GET /plugins/variables/all`` for what plugins contribute — and a caller has
to know to ask both.
"""

from __future__ import annotations

from fastapi import Query

from src.api_errors import errors
from src.plugins import routes as plugins_routes
from src.service_api import routes as service_routes
from src.service_api.models import HealthResponse, StatusResponse
from src.templates import routes as templates_routes
from src.templates.models import FormulaFunctionsResponse, TemplateRenderRequest, TemplateRenderResponse

from .boards import resolve_board
from .models import RenderRequest, VariableCatalog
from .router import router


@router.get(
    "/variables",
    response_model=VariableCatalog,
    responses=errors(503),
    summary="List every name a template can use",
    description=(
        "The whole template vocabulary in one answer: the built-in variables, everything the installed plugins "
        "contribute, the colour and symbol names, and the filters you can apply. `max_lengths` gives the longest "
        "value each variable can render to, which is what you size a row against."
    ),
)
async def list_variables() -> VariableCatalog:
    template_view = await templates_routes.get_template_variables()
    plugin_view = await plugins_routes.get_all_plugin_variables()

    variables = {**template_view.variables}
    for namespace, names in (plugin_view.variables or {}).items():
        if isinstance(names, list):
            variables.setdefault(namespace, names)

    max_lengths = {**template_view.max_lengths}
    for name, length in (plugin_view.max_lengths or {}).items():
        if isinstance(length, int):
            max_lengths.setdefault(name, length)

    return VariableCatalog(
        variables=variables,
        max_lengths=max_lengths,
        variable_metadata=template_view.variable_metadata,
        variable_groups=template_view.variable_groups,
        colors=template_view.colors,
        symbols=template_view.symbols,
        filters=template_view.filters,
        formatting=template_view.formatting,
        syntax_examples=template_view.syntax_examples,
        plugin_system_enabled=bool(plugin_view.plugin_system_enabled),
    )


@router.get(
    "/functions",
    response_model=FormulaFunctionsResponse,
    responses=errors(503),
    summary="List the functions a template expression can call",
    description=(
        "Every function usable inside `{{ }}` — conditionals, arithmetic, text and date helpers — with its "
        "signature and a one-line summary. This is the reference for writing a collection's `variable` rules as "
        "well as for page templates."
    ),
)
async def list_functions() -> FormulaFunctionsResponse:
    return await templates_routes.get_formula_functions()


@router.post(
    "/render",
    response_model=TemplateRenderResponse,
    responses=errors(400, 404),
    summary="Render a template without saving or sending it",
    description=(
        "Runs a template against the current data and gives you back the text, so you can see what a page would "
        "look like before you save it. Pass `board` — a board id or `primary` — to lay it out for that board's "
        "size; without it the template is rendered at the default flagship geometry. Nothing is written to any "
        "board."
    ),
)
async def render_template(
    request: RenderRequest,
    board: str | None = Query(
        default=None,
        description="Board id, or 'primary', whose geometry the template should be laid out for.",
    ),
) -> TemplateRenderResponse:
    device_type = None
    if board is not None:
        device_type = resolve_board(board)[1].get("device_type") or "flagship"
    return await templates_routes.render_template(
        TemplateRenderRequest(
            template=request.template,
            device_type=device_type,
            line_metadata=request.line_metadata,
        )
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    responses=errors(503),
    summary="Check that the instance is up",
    description=(
        "Answers 200 whenever the process is serving. `service_running` reports whether the display loop — the "
        "thing that actually drives the boards — is running, which is separate from the API being reachable."
    ),
)
async def health() -> HealthResponse:
    return await service_routes.health()


@router.get(
    "/status",
    response_model=StatusResponse,
    responses=errors(503),
    summary="Read the display loop's state, board by board",
    description=(
        "What the instance is doing: whether the display loop is running, a summary of the resolved configuration, "
        "and per board whether it has a working connection, whether it is paused, which page it is showing, and "
        "why it failed to start if it did."
    ),
)
async def status() -> StatusResponse:
    return await service_routes.get_status()
