"""The ``vestaboard`` output's board-settings actions (plan D13).

What the hand-coded Vestaboard form does through its own routes —
``/config/board/test``, ``/config/board/scan``, ``/config/board/enable-local-api``,
``/settings/board/{id}/identify``, ``/settings/board/{id}/detect-size`` —
exposed as the actions every output answers, so the draft and saved-board
action routes (``src/outputs/actions.py``) serve a Vestaboard the same way
they serve a plugin. The legacy routes stay unchanged (pinned by their
goldens); Phase 4 moves the Vestaboard form onto these.

``call.board`` is a Vestaboard board dict: the flat connection fields
(``api_mode``, ``host``, ``port``, ``local_api_key``, ``cloud_key``,
``note_array_token``, ``tiles``) plus geometry, with any masked secret
already restored from the stored board.

Preconditions the server refuses before contacting a device are
:class:`~src.outputs.hooks.OutputActionError` (a 4xx); what the device said
is the outcome, at 200 (API_CONVENTIONS.md, "Probe endpoints").
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

from src.outputs.hooks import (
    ActionCall,
    ActionField,
    ActionOutcome,
    OutputActionError,
    OutputActionSpec,
    ResultFieldSpec,
)

logger = logging.getLogger(__name__)

#: Scan length bounds, the same as ``POST /config/board/scan``.
_SCAN_DEFAULT_S, _SCAN_MIN_S, _SCAN_MAX_S = 4.0, 1.0, 15.0

ACTIONS: tuple[OutputActionSpec, ...] = (
    OutputActionSpec(id="test_connection", label="Test connection"),
    OutputActionSpec(
        id="discover",
        label="Scan network",
        description="Find Vestaboards with the Local API on this network.",
        input_schema={
            "type": "object",
            "properties": {
                "timeout": {
                    "type": "number",
                    "title": "Scan seconds",
                    "minimum": _SCAN_MIN_S,
                    "maximum": _SCAN_MAX_S,
                    "default": _SCAN_DEFAULT_S,
                }
            },
        },
    ),
    OutputActionSpec(
        id="identify",
        label="Identify",
        description="Flash each note-array tile's position on it.",
        input_schema={
            "type": "object",
            "properties": {
                "target": {"type": "string", "enum": ["tile", "all"], "default": "tile"},
                "row": {"type": "integer", "minimum": 0},
                "col": {"type": "integer", "minimum": 0},
                "host": {"type": "string"},
                "port": {"type": "integer", "minimum": 1, "maximum": 65535},
                "local_api_key": {"type": "string", "secret": True},
            },
        },
    ),
    OutputActionSpec(
        id="detect_geometry",
        label="Detect size",
        description="Read the board's current layout and classify its size.",
    ),
    OutputActionSpec(
        id="enable_local_api",
        label="Enable Local API",
        description="Exchange a Local API enablement token for a Local API key.",
        input_schema={
            "type": "object",
            "properties": {
                "enablement_token": {"type": "string", "title": "Enablement token", "secret": True, "minLength": 1},
                "host": {"type": "string", "title": "Board IP address"},
            },
            "required": ["enablement_token"],
        },
        result_fields={"api_key": ResultFieldSpec(secret=True, fills="local_api_key")},
    ),
)


def _draft_driver(board: Mapping[str, Any]):
    from src.outputs.factory import draft_driver

    try:
        return draft_driver(dict(board))
    except ValueError as exc:
        raise OutputActionError(400, "Board connection configuration is invalid.") from exc


async def _test_connection(call: ActionCall) -> ActionOutcome:
    from src.board_guards import validate_board_host

    board = call.board
    if (board.get("api_mode") or "local") == "local" and board.get("host") and not board.get("tiles"):
        validate_board_host(board["host"])
    driver = _draft_driver(board)
    if driver is None:
        raise OutputActionError(400, "Enter the board's connection details first.")
    check = await asyncio.to_thread(driver.check_connection)
    return ActionOutcome.from_check(check)


async def _discover(call: ActionCall) -> ActionOutcome:
    from src.outputs.registry import VESTABOARD, discover_devices

    raw = call.inputs.get("timeout", _SCAN_DEFAULT_S)
    timeout = min(max(float(raw), _SCAN_MIN_S), _SCAN_MAX_S)
    devices = await asyncio.to_thread(discover_devices, VESTABOARD, timeout)
    message = f"Found {len(devices)} board(s)." if devices else "No boards found."
    return ActionOutcome(message=message, devices=tuple(devices))


def _live_driver(board_id: str | None):
    if board_id is None:
        return None
    from src.display_runtime import get_service

    service = get_service()
    runtime = service.runtime_for(board_id) if service is not None else None
    return runtime.client if runtime is not None else None


def _identify_targets(instance: Any, inputs: Mapping[str, Any]) -> tuple[list[dict], bool]:
    """``(targets, override)``: the tiles to flash and whether they are unsaved."""
    from src.board_guards import validate_board_host, validate_board_host_is_local_network

    target = inputs.get("target", "tile")
    row, col = inputs.get("row"), inputs.get("col")
    if inputs.get("host") is not None or inputs.get("local_api_key") is not None:
        if target != "tile" or row is None or col is None:
            raise OutputActionError(400, "Credential override requires target='tile' with row and col")
        if not inputs.get("host") or not inputs.get("local_api_key"):
            raise OutputActionError(400, "host and local_api_key are both required")
        validate_board_host(inputs["host"])
        validate_board_host_is_local_network(inputs["host"])
        tile = {"row": row, "col": col, "host": inputs["host"], "port": inputs.get("port") or 7000}
        return [{**tile, "local_api_key": inputs["local_api_key"]}], True
    configured = instance.configured_tiles()
    if target == "tile":
        if row is None or col is None:
            raise OutputActionError(400, "row and col are required for target='tile'")
        configured = [t for t in configured if t["row"] == row and t["col"] == col]
        if not configured:
            raise OutputActionError(400, f"No configured tile at row={row}, col={col}")
    if not configured:
        raise OutputActionError(400, "Board has no configured tiles to identify")
    return configured, False


def _flash_draft(tile: dict, notes_wide: int) -> bool:
    from src.devices import identify_pattern

    draft = {
        "api_mode": "local",
        "device_type": "note",
        "host": tile["host"],
        "port": tile.get("port"),
        "local_api_key": tile["local_api_key"],
    }
    try:
        driver = _draft_driver(draft)
        return bool(driver.send_characters(identify_pattern(tile["row"], tile["col"], notes_wide), force=True)[0])
    except Exception as exc:
        logger.error("Identify failed for tile (%s,%s): %s", tile["row"], tile["col"], type(exc).__name__)
        return False


async def _identify(call: ActionCall) -> ActionOutcome:
    from src.devices import BoardInstance, is_note_array

    instance = BoardInstance.from_dict(dict(call.board))
    if not is_note_array(instance.device_type) or instance.api_mode != "local":
        raise OutputActionError(400, "Identify is only available for note arrays in local API mode")
    targets, override = _identify_targets(instance, call.inputs)
    if override:
        flashed = {(t["row"], t["col"]): await asyncio.to_thread(_flash_draft, t, instance.notes_wide) for t in targets}
    else:
        driver = _live_driver(call.board_id)
        identify_tiles = getattr(driver, "identify_tiles", None)
        if identify_tiles is None:
            raise OutputActionError(503, "Save the board to identify its assigned tiles.")
        flashed = await asyncio.to_thread(identify_tiles, [(t["row"], t["col"]) for t in targets])
        if call.board_id is not None:
            from src.display_runtime import get_service

            service = get_service()
            if service is not None:
                service.invalidate_board_content(call.board_id)
    failed = [f"Tile {r + 1},{c + 1} did not respond." for (r, c), ok in flashed.items() if not ok]
    if failed and len(failed) == len(flashed):
        return ActionOutcome(status="error", message="No tile responded.", guidance=tuple(failed))
    if failed:
        return ActionOutcome(status="warning", message="Some tiles did not respond.", guidance=tuple(failed))
    return ActionOutcome(message=f"Identified {len(flashed)} tile(s).")


async def _detect_geometry(call: ActionCall) -> ActionOutcome:
    from src.board_send_executor import run_board_send
    from src.devices import BoardInstance, classify_dimensions

    if BoardInstance.from_dict(dict(call.board)).uses_local_tiles:
        raise OutputActionError(
            400,
            "Auto-detect is not available for local-mode note arrays — "
            "the array's size is defined by its tile assignments",
        )
    driver = _live_driver(call.board_id) or _draft_driver(call.board)
    if driver is None:
        raise OutputActionError(400, "Enter the board's connection details first.")
    grid = await run_board_send(driver.read_current_message)
    if not grid:
        return ActionOutcome(status="error", message="The board returned no layout — it may be blank or unreachable.")
    rows, cols = len(grid), len(grid[0])
    try:
        geometry = classify_dimensions(rows, cols)
    except ValueError:
        return ActionOutcome(
            status="error", message=f"The board returned a grid FiestaBoard cannot classify ({rows}×{cols})."
        )
    return ActionOutcome(message="Size detected.", geometry=geometry)


async def _enable_local_api(call: ActionCall) -> ActionOutcome:
    from .local_api import exchange_enablement_token

    host = call.inputs.get("host") or call.board.get("host") or ""
    token = call.inputs.get("enablement_token") or ""
    if not host:
        raise OutputActionError(400, "Enter the board's IP address first.")
    verdict = await exchange_enablement_token(SimpleNamespace(host=host, enablement_token=token))
    if not verdict.get("success"):
        guidance = (verdict["error"],) if verdict.get("error") else ()
        return ActionOutcome(status="error", message=verdict.get("message", ""), guidance=guidance)
    return ActionOutcome(
        message=verdict.get("message", ""),
        fields={"api_key": ActionField(value=verdict.get("api_key"), secret=True)},
    )


_RUNNERS = {
    "test_connection": _test_connection,
    "discover": _discover,
    "identify": _identify,
    "detect_geometry": _detect_geometry,
    "enable_local_api": _enable_local_api,
}


async def dispatch(call: ActionCall) -> ActionOutcome:
    """Run one declared Vestaboard action."""
    return await _RUNNERS[call.action](call)
