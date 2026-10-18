"""``/v1/boards`` — the front door.

Six operations replace sixteen ways to write to a board and ten ways to read
one. Every one of them is an adapter: the write goes through
:mod:`src.ops.executors`, which already mirrors ``POST /send-message`` gate
for gate and is already board-aware; the read composes three existing reads;
the patch calls three existing setters.

The one rule this surface states that the internal API never did: **a v1
write honours the install's output target.** ``should_send_to_board()`` is
checked before anything is written, and ``sent`` in the response says what
actually happened. Today ``POST /pages/{id}/send``, ``POST /debug/fill`` and
``POST /debug/blank`` honour it while ``POST /send-message`` ignores it — the
same action behaving two ways. v1 picks one and tells the caller.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, Response

from src import display_runtime as runtime
from src.api_errors import errors
from src.board_chars import characters_to_message
from src.board_state import read_board_state
from src.devices import geometry_of
from src.ops import executors
from src.outputs.board_profile import board_profile
from src.outputs.cells import extended_markup_kw, project_for_output
from src.outputs.display_profile import board_layers_json
from src.outputs.registry import resolve_output_id
from src.text_to_board import text_to_board_array, wrap_message_text

from .boards import board_dimensions, resolve_board, resolve_board_id
from .models import (
    ActivePageRequest,
    ActivePageResponse,
    BoardDetail,
    BoardListResponse,
    BoardSummary,
    BoardUpdate,
    MessageRequest,
    MessageResponse,
    PartialWriteError,
)
from .router import router

logger = logging.getLogger(__name__)

HELD_REASON = "Held: the board is silenced until {time} UTC; this will show when silence ends."
UI_ONLY_REASON = "The install's output target is UI only, so nothing was written to the board."
UNCHANGED_REASON = "The board already shows this exact content. Send force=true to write it anyway."
PAUSED_PREVIEW_REASON = "The board is paused, so nothing was written. This is what it would have shown."
SILENCED_PIN_REASON = (
    "The board is silenced until {time} UTC, so nothing was written. The page is pinned and will show when "
    "silence ends. Send override_silence=true to show it now."
)


def _settings_service():
    from src.settings.service import get_settings_service

    return get_settings_service()


def _schedule_service():
    from src.schedules.service import get_schedule_service

    return get_schedule_service()


def _summary(board: dict[str, Any], primary_id: str | None) -> BoardSummary:
    """Project one stored board entry into the consumer view."""
    settings_service = _settings_service()
    board_id = board.get("id") or ""
    dims = board_dimensions(board)
    profile = board_profile(board)
    return BoardSummary(
        id=board_id,
        name=board.get("name") or board_id,
        device_type=board.get("device_type") or "flagship",
        rows=dims.rows,
        cols=dims.cols,
        is_primary=board_id == primary_id,
        paused=settings_service.is_paused(board_id=board_id) is True,
        schedule_enabled=bool(settings_service.is_schedule_enabled(board_id=board_id)),
        output=resolve_output_id(board),
        device_model=profile.device_model,
        charset=profile.charset,
    )


@router.get(
    "/boards",
    response_model=BoardListResponse,
    responses=errors(503),
    summary="List the boards this install drives",
    description=(
        "Every configured board, with the id you use in the rest of this API, its grid size, and whether it is "
        "currently paused or following its schedule. The board marked `is_primary` is the one the literal path "
        "segment `primary` resolves to, so a single-board install never has to look an id up at all."
    ),
)
async def list_boards() -> BoardListResponse:
    try:
        settings_service = _settings_service()
        boards = settings_service.get_board_settings().boards or []
        primary_id = settings_service.get_primary_board_id()
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Could not read the boards store: %s", exc)
        raise HTTPException(status_code=503, detail="Board settings are unavailable.") from exc

    entries = [_summary(b, primary_id) for b in boards if isinstance(b, dict) and b.get("id")]
    return BoardListResponse(boards=entries, total=len(entries))


@router.get(
    "/boards/{board}",
    response_model=BoardDetail,
    responses=errors(404, 503),
    summary="Read a board and everything it is doing",
    description=(
        "One answer to 'what is this board showing, and why'. It merges what the internal API splits across three "
        "endpoints: the flaps currently on the board, the page pinned to it by hand, and the page its schedule "
        "selects for right now. `source` says which of the two won. `board` may be a board id or the literal "
        "`primary`."
    ),
)
async def get_board(board: str) -> BoardDetail:
    from src.collections.service import (
        get_collection_service,
        resolve_active_page_id,
        resolve_next_check_seconds,
    )
    from src.time_service import get_time_service

    board_id, entry = resolve_board(board)
    settings_service = _settings_service()
    schedule_service = _schedule_service()
    primary_id = settings_service.get_primary_board_id()
    base = _summary(entry, primary_id)

    # What was *sent* and what the board *shows* are two different facts,
    # and the difference is the only way a caller can notice the board has
    # drifted — a flap that did not turn, or another writer. GET
    # /board/current-message publishes both; so does this.
    state = read_board_state(board_id, want="board", service=runtime.get_service())
    characters = state.characters
    expected_characters = state.expected_characters
    read_at = datetime.fromtimestamp(state.polled_at, tz=UTC).isoformat() if state.polled_at is not None else None

    active_page_id = settings_service.get_active_page_id(board_id=board_id)
    scheduled_page_id = None
    if settings_service.is_schedule_enabled(board_id=board_id):
        now = get_time_service().get_current_time()
        scheduled_page_id = schedule_service.get_active_page_id(
            now.time(), now.strftime("%A").lower(), board_id=board_id
        )

    if active_page_id:
        source = "manual"
        chosen = active_page_id
    elif scheduled_page_id:
        source = "schedule"
        chosen = scheduled_page_id
    else:
        source = "none"
        chosen = None

    override = settings_service.get_temporary_override()
    return BoardDetail(
        **base.model_dump(),
        characters=characters,
        text=characters_to_message(characters) if characters else None,
        expected_characters=expected_characters,
        read_at=read_at,
        active_page_id=active_page_id,
        scheduled_page_id=scheduled_page_id,
        resolved_page_id=resolve_active_page_id(chosen, get_collection_service),
        resolved_next_check_seconds=resolve_next_check_seconds(chosen, get_collection_service),
        source=source,
        default_page_id=schedule_service.get_default_page(board_id=board_id),
        override_expires_at=(override.expires_at if override is not None and board_id == primary_id else None),
        layers=board_layers_json(entry, state.cells if state.characters is not None else None),
    )


@router.patch(
    "/boards/{board}",
    response_model=BoardDetail,
    responses=errors(400, 404, 503),
    summary="Change how a board behaves",
    description=(
        "Rename a board, pause or resume it, turn its schedule on or off, or set the page it falls back to when the "
        "schedule has a gap. Only the fields you send are applied; omit the rest. Pausing stops every write to the "
        "board from every code path — the display loop, schedules, plugin triggers, MQTT and this API alike."
    ),
)
async def update_board(board: str, request: BoardUpdate) -> BoardDetail:
    board_id = resolve_board_id(board)
    settings_service = _settings_service()
    provided = request.model_dump(exclude_unset=True)

    if "paused" in provided and provided["paused"] is not None:
        settings_service.set_paused(provided["paused"], board_id=board_id)

    if "schedule_enabled" in provided and provided["schedule_enabled"] is not None:
        settings_service.set_schedule_enabled(provided["schedule_enabled"], board_id=board_id)

    if "default_page_id" in provided:
        page_id = provided["default_page_id"]
        if page_id is not None:
            _require_page_ref(page_id)
        _schedule_service().set_default_page(page_id, board_id=board_id)

    if "name" in provided and provided["name"] is not None:
        boards = [dict(b) for b in (settings_service.get_board_settings().boards or []) if isinstance(b, dict)]
        for candidate in boards:
            if candidate.get("id") == board_id:
                candidate["name"] = provided["name"]
        try:
            settings_service.set_boards(boards)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return await get_board(board)


def _require_page_ref(page_id: str) -> None:
    """404 unless *page_id* names a page or a collection that exists."""
    from src.collections.models import is_collection_id
    from src.collections.service import get_collection_service
    from src.pages.service import get_page_service

    if is_collection_id(page_id):
        if not get_collection_service().get_collection(page_id):
            raise HTTPException(status_code=404, detail=f"Collection not found: {page_id}")
        return
    if not get_page_service().get_page(page_id):
        raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")


def _validate_grid(characters: list[list[int]], rows: int, cols: int) -> None:
    """Reject a supplied grid the board cannot display.

    A 400, not a 422: the body already passed schema validation (flap codes
    are range-checked by the request model), and whether the grid *fits* is a
    fact about the board, not about the JSON. 422 belongs to FastAPI —
    API_CONVENTIONS.md, "Error contract".
    """
    if len(characters) != rows or any(len(row) != cols for row in characters):
        got = f"{len(characters)}x{len(characters[0]) if characters else 0}"
        raise HTTPException(
            status_code=400,
            detail=f"characters must be a {rows}x{cols} grid for this board, got {got}",
        )


def _render_plugin_template(lines: list[str], entry: dict[str, Any]) -> str:
    """Fill a ``template`` request's plugin variables, the way a template page is rendered."""
    from src.templates.engine import get_template_engine

    geometry = geometry_of(entry)
    try:
        return get_template_engine().render_lines(
            list(lines),
            device_type=geometry.device_type,
            notes_wide=geometry.notes_wide,
            notes_tall=geometry.notes_tall,
            grid_rows=geometry.grid_rows,
            grid_cols=geometry.grid_cols,
        )
    except Exception as exc:  # a bad template is the caller's 400, not our 500
        raise HTTPException(status_code=400, detail=f"Template rendering failed: {exc}") from exc


def _grid_for(
    request: MessageRequest,
    rows: int,
    cols: int,
    client: Any = None,
    entry: dict[str, Any] | None = None,
) -> tuple[list[list[int]], str, list[str] | None, dict[str, Any]]:
    """``(characters, text, template_lines, rich)`` for whichever content field was sent.

    ``template_lines`` is the form a timed message can be stored as; it is
    ``None`` for the two raw-grid forms, which the temporary-override store
    has no representation for. ``rich`` holds the send keywords carrying the
    rich cells of a text form, for a board (*client*) whose output draws a
    rich character set; empty otherwise, and always for the raw grids.
    """
    if request.text is not None:
        wrapped = wrap_message_text(request.text, rows=rows, cols=cols)
        grid, rich = project_for_output(client, wrapped, rows, cols, flap=text_to_board_array)
        return grid, wrapped, wrapped.split("\n"), rich

    if request.lines is not None:
        joined = "\n".join(request.lines)
        grid, rich = project_for_output(client, joined, rows, cols, flap=text_to_board_array)
        return grid, joined, list(request.lines), rich

    if request.plugin_id is not None:
        from src.devices import board_context_for
        from src.displays.service import get_display_service

        # Sized to THIS board, the way a page renders a plugin (#2072).
        board_ctx = board_context_for(*geometry_of(entry or {}))
        result = get_display_service().get_display(request.plugin_id, board=board_ctx)
        if not result.available and result.error and "Unknown display type" in result.error:
            raise HTTPException(status_code=404, detail=f"Plugin not found: {request.plugin_id}")
        if not result.available:
            raise HTTPException(status_code=503, detail=result.error or "Plugin data not available")
        grid, rich = project_for_output(client, result.formatted, rows, cols, flap=text_to_board_array)
        return grid, result.formatted, result.formatted.split("\n"), rich

    if request.template is not None:
        rendered = _render_plugin_template(request.template, entry or {})
        grid, rich = project_for_output(client, rendered, rows, cols, flap=text_to_board_array)
        return grid, rendered, rendered.split("\n"), rich

    if request.fill is not None:
        grid = [[request.fill] * cols for _ in range(rows)]
        return grid, characters_to_message(grid), None, {}

    if request.characters is not None:
        _validate_grid(request.characters, rows, cols)
        return request.characters, characters_to_message(request.characters), None, {}

    # page_id — the remaining form, guaranteed by the request model.
    from src.pages.service import get_page_service

    page_service = get_page_service()
    result = page_service.preview_page(request.page_id, force_refresh=True, **extended_markup_kw(client))
    if result is None:
        raise HTTPException(status_code=404, detail=f"Page not found: {request.page_id}")
    if not result.available:
        raise HTTPException(status_code=503, detail=result.error or "Page rendering failed")
    grid, rich = project_for_output(client, result.formatted, rows, cols, flap=text_to_board_array)
    return grid, result.formatted, result.formatted.split("\n"), rich


def _raise_for_executor(result: dict[str, Any]) -> None:
    """Turn an executor refusal into the status code it deserves.

    Blocked is policy, not breakage: silence and pause are both 409, the same
    verdict ``POST /send-message`` and ``POST /debug/fill`` give. A write the
    board's send floor dropped arrives as an error envelope carrying
    ``retry_after_seconds`` (#1931) and is the 429 + ``Retry-After`` the
    other manual senders answer — this route used to derive that itself from
    the client after a ``skipped`` result, before the executor gated it.
    A write superseded by a newer one is a 409: its content never landed.
    A write that reached only part of the board (``partial``, a local note
    array with a failed tile) is a 502 whose structured detail names the
    cells that did not update — it used to be a bare 500 indistinguishable
    from a write that changed nothing. Anything else the executor calls an
    error is a 500 — the 503 cases (no service, no client) are checked
    before it is ever called, so they cannot arrive here.
    """
    if result.get("status") == "blocked":
        if result.get("silence_mode"):
            from src.board_guards import SILENCE_DETAIL, SILENCE_OVERRIDE_HINT

            raise HTTPException(status_code=409, detail=SILENCE_DETAIL + SILENCE_OVERRIDE_HINT)
        raise HTTPException(status_code=409, detail=str(result.get("message")))
    if result.get("status") == "error" and result.get("superseded"):
        raise HTTPException(status_code=409, detail=str(result["error"]))
    if result.get("status") == "error" and result.get("partial"):
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(result.get("error")),
                "partial": True,
                "failed_regions": list(result.get("failed_regions") or []),
            },
        )
    if result.get("status") == "error":
        detail = str(result.get("error") or "Failed to send to the board.")
        retry_after = result.get("retry_after_seconds")
        if retry_after is not None:
            raise HTTPException(status_code=429, detail=detail, headers={"Retry-After": str(int(retry_after))})
        raise HTTPException(status_code=500, detail=detail)


@router.post(
    "/boards/{board}/message",
    response_model=MessageResponse,
    responses={
        202: {"model": MessageResponse, "description": "Held: the board is silenced and will show this when it ends."},
        **errors(400, 404, 409, 429, 500, 502, 503, models={502: PartialWriteError}),
    },
    summary="Put something on a board",
    description=(
        "The one way to write to a board. Send exactly one of `text` (word-wrapped for you), `lines` (one string "
        "per row), `characters` (a raw flap grid), `page_id` (render a saved page), `fill` (one flap code "
        "everywhere; 0 blanks the board), `plugin_id` (a plugin's live data, formatted the way the plugin displays "
        "itself) or `template` (one line per row with plugin variables like "
        "`{{weather.temperature}}` filled from live plugin data).\n\n"
        "Add `duration_minutes` to make it temporary — it reverts to your schedule, a chosen page, or a blank board "
        "when the time is up. `board` may be a board id or the literal `primary`.\n\n"
        "`sent` in the response tells you whether flaps actually moved. It is false, with a `reason`, when the "
        "install's output target is UI-only and when the board already showed this exact content. A board that is "
        "paused or inside its silence window refuses the write with 409 rather than lying about it. Send "
        '`if_paused: "preview"` to get a 200 instead for a paused board: `sent` is false, `reason` says the board '
        "is paused, and `characters` is what it would have shown. Nothing is written.\n\n"
        "A write superseded by a newer write returns 409: its content did not reach the board. "
        "A silenced board is left alone. When its silence schedule holds messages (`show_queued_on_exit`) the "
        "write is accepted for later: 202, `sent: false`, `held: true`, and it shows when silence ends. "
        "Otherwise it is a 409. Send `override_silence: true` to write anyway. A board made "
        "of several devices (a local note array) that takes the write on only some of them answers 502, and "
        "`detail.failed_regions` names the cells that did not update; sending again retries only those."
    ),
)
async def send_to_board(board: str, request: MessageRequest, response: Response) -> MessageResponse:
    board_id, entry = resolve_board(board)
    settings_service = _settings_service()

    if request.revert_mode is not None and request.duration_minutes is None:
        raise HTTPException(status_code=400, detail="revert_mode requires duration_minutes")
    if request.revert_page_id is not None and request.revert_mode != "page":
        raise HTTPException(status_code=400, detail='revert_page_id requires revert_mode "page"')

    service = runtime.get_service()
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    board_client = service.get_board_client(board_id)
    if board_client is None:
        raise HTTPException(status_code=503, detail=f"Board client not initialized: {board_id}")

    dims = board_dimensions(entry)
    characters, text, template_lines, rich = _grid_for(request, dims.rows, dims.cols, board_client, entry)

    # A timed message is validated up front (its 400s must precede any
    # write) but ARMED only after the write is in. It used to be armed and
    # persisted before the executor ran, and nothing rolled it back on a
    # refusal — so a write the send floor dropped (429) still landed on the
    # next display tick, for the full duration (#1931 review).
    expires_at = None
    if request.duration_minutes is not None:
        _check_timed_request(board_id, template_lines)

    if not settings_service.should_send_to_board():
        if request.duration_minutes is not None:
            expires_at = await _arm_temporary_override(board_id, request, template_lines)
        return MessageResponse(
            sent=False,
            board_id=board_id,
            characters=characters,
            text=text,
            expires_at=expires_at,
            reason=UI_ONLY_REASON,
        )

    # if_paused="preview" (#2072): the non-409 answer for a paused board. It
    # says what *would* have happened and writes nothing — no send, no timed
    # override armed. The default, "reject", leaves the 409 below untouched.
    if request.if_paused == "preview" and settings_service.is_paused(board_id=board_id) is True:
        return MessageResponse(
            sent=False,
            board_id=board_id,
            characters=characters,
            text=text,
            expires_at=None,
            reason=PAUSED_PREVIEW_REASON,
        )

    transition = request.transition
    send_kwargs = {
        "strategy": transition.strategy if transition else None,
        "step_interval_ms": transition.interval_ms if transition else None,
        "step_size": transition.step_size if transition else None,
        "force": request.force,
        "override_silence": request.override_silence,
    }

    from src.board_send_executor import run_board_send

    if request.text is not None:
        result = await run_board_send(executors.send_message, request.text, board_id, **send_kwargs)
    else:
        hold = _held_intent(request, board_id, characters, template_lines)
        result = await run_board_send(executors.send_characters, characters, board_id, **send_kwargs, **rich, hold=hold)

    if result.get("status") == "blocked" and result.get("held"):
        from src.board_guards import silence_ends_hhmm

        response.status_code = 202
        return MessageResponse(
            sent=False,
            board_id=board_id,
            characters=characters,
            text=text,
            expires_at=None,
            reason=HELD_REASON.format(time=silence_ends_hhmm(result.get("silence_ends_at"))),
            silenced=True,
            held=True,
        )

    _raise_for_executor(result)

    if request.duration_minutes is not None:
        expires_at = await _arm_temporary_override(board_id, request, template_lines)

    if result.get("skipped"):
        return MessageResponse(
            sent=False,
            board_id=board_id,
            characters=characters,
            text=text,
            expires_at=expires_at,
            reason=UNCHANGED_REASON,
        )

    return MessageResponse(
        sent=True,
        board_id=board_id,
        characters=characters,
        text=text,
        expires_at=expires_at,
        reason=None,
    )


def _held_intent(
    request: MessageRequest,
    board_id: str,
    characters: list[list[int]],
    template_lines: list[str] | None,
):
    """What to hold for a non-text write silence refuses (#1944).

    An *intent*, not the frame: a page or plugin is rendered again when
    silence ends, so the morning shows the morning's data.
    """
    from src.silence_queue import HeldSend

    if request.page_id is not None:
        return HeldSend.page(request.page_id, board_id=board_id)
    if request.plugin_id is not None:
        return HeldSend.display(request.plugin_id, board_id=board_id)
    if request.lines is not None:
        return HeldSend.lines(list(request.lines), board_id=board_id)
    if request.template is not None and template_lines is not None:
        return HeldSend.lines(template_lines, board_id=board_id)
    # The raw-grid forms (characters, fill) carry no rich cells.
    return HeldSend.grid(characters, board_id=board_id)


def _check_timed_request(board_id: str, template_lines: list[str] | None) -> None:
    """The 400s a ``duration_minutes`` request can earn, before anything is sent.

    Two limits come from the override mechanism and are reported rather than
    papered over: it is stored globally and applied by the display loop for
    the **primary** board only, and it can only hold text, so the raw-grid
    forms cannot be timed.
    """
    settings_service = _settings_service()
    if board_id != settings_service.get_primary_board_id():
        raise HTTPException(
            status_code=400,
            detail=(
                "duration_minutes is only supported on the primary board — "
                "timed messages are applied by the display loop for the primary board only."
            ),
        )
    if template_lines is None:
        raise HTTPException(
            status_code=400,
            detail="duration_minutes cannot be combined with characters or fill; use text, lines or page_id",
        )


async def _arm_temporary_override(board_id: str, request: MessageRequest, template_lines: list[str] | None) -> str:
    """Store the timed-message state, and return when it expires.

    Delegates to ``POST /settings/temporary-override`` — the existing home of
    duration, revert mode and the inline one-off content of #1787 — rather
    than restating its validation. Called only once the write is in (or the
    install is UI-only and there is no write to wait for); see
    :func:`_check_timed_request` for the refusals, which run first.
    """
    from src.settings.models import TemporaryOverrideRequest
    from src.settings.routes import set_temporary_override

    _check_timed_request(board_id, template_lines)

    body: dict[str, Any] = {
        "duration_minutes": request.duration_minutes,
        "revert_mode": request.revert_mode or "schedule",
    }
    if request.revert_page_id is not None:
        body["revert_page_id"] = request.revert_page_id
    if request.page_id is not None:
        body["page_id"] = request.page_id
    else:
        body["template"] = template_lines
        board = resolve_board(board_id)[1]
        geometry = geometry_of(board)
        body["device_type"] = geometry.device_type
        body["notes_wide"] = geometry.notes_wide
        body["notes_tall"] = geometry.notes_tall
        body["grid_rows"] = geometry.grid_rows
        body["grid_cols"] = geometry.grid_cols

    await set_temporary_override(TemporaryOverrideRequest(**body))
    return (datetime.now(UTC) + timedelta(minutes=int(request.duration_minutes))).isoformat()


@router.delete(
    "/boards/{board}/message",
    response_model=MessageResponse,
    responses=errors(404, 500, 503),
    summary="Clear a board and let its schedule take over",
    description=(
        "Undoes a `POST` to this path. Any timed message is cancelled, the board's content cache is dropped, and "
        "the display loop re-renders whatever the schedule or the pinned page says should be there — which is a "
        "blank board when nothing is scheduled. `sent` reports whether that re-render reached the board."
    ),
)
async def clear_board_message(board: str) -> MessageResponse:
    from src.service_api.routes import refresh_display

    board_id, entry = resolve_board(board)
    settings_service = _settings_service()

    # A timed message is the one piece of state a POST leaves behind.
    if board_id == settings_service.get_primary_board_id():
        settings_service.clear_temporary_override()

    service = runtime.get_service()
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    rt = service.get_runtime(board_id)
    if rt is not None:
        # Drop the dedupe cache so the next render is not skipped as unchanged
        # — the out-of-band write left the board showing content the loop did
        # not put there (#1794).
        rt.last_active_page_content = None

    refreshed = await refresh_display(board_id=board_id)
    dims = board_dimensions(entry)
    return MessageResponse(
        sent=bool(refreshed.sent),
        board_id=board_id,
        characters=[[0] * dims.cols for _ in range(dims.rows)],
        text="",
        expires_at=None,
        reason=None if refreshed.sent else "Nothing changed on the board — it already showed the scheduled content.",
    )


@router.put(
    "/boards/{board}/active-page",
    response_model=ActivePageResponse,
    responses=errors(400, 404, 502),
    summary="Pin a page to a board",
    description=(
        "Sets the page (or collection) this board shows until something changes it — the sticky selection a "
        "schedule falls back from. The page is rendered and sent immediately. Send `null` to unpin, after which "
        "the board follows its schedule again. Pinning a page whose size does not match the board is rejected.\n\n"
        "The selection is stored whether or not the send succeeded, so check `sent` — and `error`, which names "
        "the render or send failure when it is false.\n\n"
        "While the board is silenced the page is pinned but not shown: `sent` is false, `silenced` is true and "
        "`reason` says when it will appear. Send `override_silence: true` to show it now anyway."
    ),
)
async def set_board_active_page(board: str, request: ActivePageRequest) -> ActivePageResponse:
    from src.settings.models import SetActivePageRequest
    from src.settings.routes import set_active_page

    board_id = resolve_board_id(board)
    response = await set_active_page(
        SetActivePageRequest(page_id=request.page_id, board_id=board_id, override_silence=request.override_silence)
    )
    silenced = bool(response.get("silenced"))
    reason = None
    if silenced:
        from src import board_guards

        reason = SILENCED_PIN_REASON.format(
            time=board_guards.silence_ends_hhmm(board_guards.silence_window_end(board_id))
        )
    return ActivePageResponse(
        board_id=board_id,
        page_id=response.get("page_id"),
        sent=bool(response.get("sent_to_board")),
        silenced=silenced,
        reason=reason,
        # #1791 added this to the internal response precisely so a 200 that
        # never reached the board is detectable. Dropping it made every v1
        # pin look like a success.
        error=response.get("error"),
        warnings=list(response.get("warnings") or []),
    )
