"""The outputs router: boards for output plugins.

HTTP only: the service (:mod:`src.outputs.service`) does the work and raises
domain errors, mapped to status codes by ``_STATUS_BY_ERROR``.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.api_errors import errors
from src.display_runtime import reinitialize_board_clients

from .errors import (
    BuiltinOutputError,
    GeometryError,
    InvalidOutputConfigError,
    OutputNotInstalledError,
    OutputPluginsDisabledError,
    UndeclaredDeviceModelError,
)
from .models import OutputBoardCreate, OutputBoardResponse
from .service import create_output_board, describe_board

router = APIRouter(tags=["outputs"])

_STATUS_BY_ERROR: dict[type[Exception], int] = {
    OutputNotInstalledError: 404,
    OutputPluginsDisabledError: 409,
    BuiltinOutputError: 400,
    UndeclaredDeviceModelError: 400,
    GeometryError: 400,
    InvalidOutputConfigError: 400,
}


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
        status = next(code for kind, code in _STATUS_BY_ERROR.items() if isinstance(exc, kind))
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    reinitialize_board_clients()
    return OutputBoardResponse(**describe_board(board))
