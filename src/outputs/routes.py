"""The outputs router: boards for output plugins, board settings actions,
and the installed-outputs listing.

HTTP only: the service (:mod:`src.outputs.service`) does the work and raises
domain errors, mapped to status codes by ``_STATUS_BY_ERROR``.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Response

from src.api_errors import errors
from src.display_runtime import reinitialize_board_clients

from .actions import list_outputs, run_draft_action, run_saved_action
from .errors import (
    BoardNotFoundError,
    BuiltinOutputError,
    GeometryError,
    InvalidActionInputError,
    InvalidOutputConfigError,
    OutputInstallRefusedError,
    OutputNotInstallableError,
    OutputNotInstalledError,
    OutputPluginsDisabledError,
    OutputSourceUnreachableError,
    UndeclaredDeviceModelError,
)
from .hooks import OutputActionError, UnknownOutputAction
from .install import install_output, list_available_outputs
from .models import (
    ActionResult,
    AvailableOutput,
    DraftActionRequest,
    OutputBoardCreate,
    OutputBoardResponse,
    OutputSummary,
    SavedBoardActionRequest,
)
from .service import create_output_board, describe_board

router = APIRouter(tags=["outputs"])

_STATUS_BY_ERROR: dict[type[Exception], int] = {
    OutputNotInstalledError: 404,
    OutputPluginsDisabledError: 409,
    BuiltinOutputError: 400,
    UndeclaredDeviceModelError: 400,
    GeometryError: 400,
    InvalidOutputConfigError: 400,
    BoardNotFoundError: 404,
    UnknownOutputAction: 404,
    InvalidActionInputError: 400,
    OutputNotInstallableError: 404,
    OutputInstallRefusedError: 400,
    OutputSourceUnreachableError: 503,
}


def _as_http(exc: Exception) -> HTTPException:
    if isinstance(exc, OutputActionError):
        return HTTPException(status_code=exc.status_code, detail=exc.detail)
    status = next(code for kind, code in _STATUS_BY_ERROR.items() if isinstance(exc, kind))
    return HTTPException(status_code=status, detail=str(exc))


_ACTION_ERRORS = (*_STATUS_BY_ERROR, OutputActionError)

_ACTION_RESULT_NOTE = (
    'Answers the closed `ActionResult` envelope. `status: "error"` is the device\'s verdict (a refused key, '
    "nothing found) at 200; what the server refuses before contacting the device is a 4xx. Secret result "
    "fields carry `secret: true` and are never logged."
)


@router.post(
    "/outputs/{output_id}/boards",
    response_model=OutputBoardResponse,
    status_code=201,
    responses=errors(400, 404, 409),
    summary="Create a board driven by an output plugin",
    description=(
        "Creates a board for an installed output plugin, as one of the device models the plugin declares. "
        "The board's content grid comes from the model (for an LED matrix, as many glyphs as fit), and a "
        "model below the 3x15 minimum is refused, never enlarged. `output_config` is checked against the "
        "plugin's settings schema. Vestaboards are added with `POST /settings/board/add` and FiestaPanels "
        "with `POST /panels`."
    ),
)
async def create_board(output_id: str, request: OutputBoardCreate) -> OutputBoardResponse:
    geometry = request.geometry.model_dump(exclude_none=True) if request.geometry is not None else None
    try:
        board = create_output_board(
            output_id,
            device_model=request.device_model,
            output_config=request.output_config,
            name=request.name,
            geometry=geometry,
        )
    except tuple(_STATUS_BY_ERROR) as exc:
        raise _as_http(exc) from exc
    reinitialize_board_clients()
    return OutputBoardResponse(**describe_board(board))


@router.get(
    "/outputs",
    response_model=list[OutputSummary],
    responses=errors(500),
    summary="List the installed outputs",
    description=(
        "Every output this install can drive a board with: the built-in Vestaboard and FiestaPanel, then output "
        "plugins. Each carries what the add-a-board cards and the board settings screen render from: name, "
        "description, icon, capabilities, device models, the `output_config` settings schema (with its "
        "`ui:sections` / `ui:visible_when` / `ui:widget` annotations) and the screen's actions."
    ),
)
async def get_outputs() -> list[OutputSummary]:
    return [OutputSummary(**output) for output in list_outputs()]


@router.get(
    "/outputs/available",
    response_model=list[AvailableOutput],
    responses=errors(500),
    summary="List the outputs that can be picked, installed or not",
    description=(
        "What the setup wizard's first step offers: the installed outputs (built-ins first), then the first-party "
        "outputs bundled with this image (`source: seed`, installed with no network), then output plugins listed in "
        "the plugin registry (`source: registry`). Each id once. When the registry cannot be read, the installed "
        "and bundled outputs are listed alone."
    ),
)
async def get_available_outputs() -> list[AvailableOutput]:
    return [AvailableOutput(**output) for output in list_available_outputs()]


@router.post(
    "/outputs/{output_id}/install",
    response_model=OutputSummary,
    status_code=201,
    responses=errors(400, 404, 409, 503),
    summary="Install an output so a board can use it",
    description=(
        "Installs an output listed by `GET /outputs/available`: from the image's bundled seed when it holds it "
        "(no network), otherwise from the plugin registry through the normal install path, which refuses a plugin "
        "whose `output_api` this FiestaBoard does not support (400). 201 with the installed output; 200 with it "
        "when it was already installed. Every output that is not bundled needs the output plugins beta (409, "
        "checked before anything is fetched); 503 when the repository could not be downloaded."
    ),
)
async def install_an_output(output_id: str, response: Response) -> OutputSummary:
    try:
        output, created = await asyncio.to_thread(install_output, output_id)
    except tuple(_STATUS_BY_ERROR) as exc:
        raise _as_http(exc) from exc
    if not created:
        response.status_code = 200
    return OutputSummary(**output)


@router.post(
    "/outputs/{output_id}/actions/{action}",
    response_model=ActionResult,
    responses=errors(400, 404, 409, 500, 503),
    summary="Run a board settings action on draft settings",
    description=(
        "Runs one of the output's declared actions (test_connection, discover, identify, detect_geometry, or "
        "the output's own) on settings typed before a board exists. `output_config` is the draft; a masked "
        '`"***"` is refused (nothing is stored to restore it from). ' + _ACTION_RESULT_NOTE
    ),
)
async def run_output_action(output_id: str, action: str, request: DraftActionRequest) -> ActionResult:
    try:
        result = await run_draft_action(
            output_id,
            action,
            output_config=request.output_config,
            inputs=request.input,
            device_model=request.device_model,
        )
    except _ACTION_ERRORS as exc:
        raise _as_http(exc) from exc
    return ActionResult(**result)


@router.post(
    "/boards/{board_id}/actions/{action}",
    response_model=ActionResult,
    responses=errors(400, 404, 409, 500, 503),
    summary="Run a board settings action on a saved board",
    description=(
        "Runs one of the board's output's declared actions on its stored settings, or on edited settings the "
        'body carries (`output_config`), every `"***"` restored from the stored board exactly as saving does. '
        + _ACTION_RESULT_NOTE
    ),
)
async def run_board_action(board_id: str, action: str, request: SavedBoardActionRequest) -> ActionResult:
    try:
        result = await run_saved_action(board_id, action, inputs=request.input, output_config=request.output_config)
    except _ACTION_ERRORS as exc:
        raise _as_http(exc) from exc
    return ActionResult(**result)
