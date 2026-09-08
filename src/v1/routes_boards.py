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

from fastapi import HTTPException

from src import display_runtime as runtime
from src.api_errors import errors
from src.board_chars import characters_to_message
from src.ops import executors
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
)
from .router import router

logger = logging.getLogger(__name__)

UI_ONLY_REASON = "The install's output target is UI only, so nothing was written to the board."
UNCHANGED_REASON = "The board already shows this exact content. Send force=true to write it anyway."


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
    return BoardSummary(
        id=board_id,
        name=board.get("name") or board_id,
        device_type=board.get("device_type") or "flagship",
        rows=dims.rows,
        cols=dims.cols,
        is_primary=board_id == primary_id,
        paused=settings_service.is_paused(board_id=board_id) is True,
        schedule_enabled=bool(settings_service.is_schedule_enabled(board_id=board_id)),
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

    service = runtime.get_service()
    characters: list[list[int]] | None = None
    expected_characters: list[list[int]] | None = None
    read_at: str | None = None
    if service is not None:
        rt = service.get_runtime(board_id)
        if rt is not None:
            # What was *sent* and what the board *shows* are two different
            # facts, and the difference is the only way a caller can notice
            # the board has drifted — a flap that did not turn, or another
            # writer. GET /board/current-message publishes both; so does this.
            expected_characters = getattr(rt.client, "_last_characters", None) if rt.client is not None else None
            characters = rt.polled_characters
            if characters is not None and rt.polled_at is not None:
                read_at = datetime.fromtimestamp(rt.polled_at, tz=UTC).isoformat()
            if characters is None:
                characters = expected_characters

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


def _grid_for(request: MessageRequest, rows: int, cols: int) -> tuple[list[list[int]], str, list[str] | None]:
    """``(characters, text, template_lines)`` for whichever content field was sent.

    ``template_lines`` is the form a timed message can be stored as; it is
    ``None`` for the two raw-grid forms, which the temporary-override store
    has no representation for.
    """
    if request.text is not None:
        wrapped = wrap_message_text(request.text, rows=rows, cols=cols)
        return text_to_board_array(wrapped, rows=rows, cols=cols), wrapped, wrapped.split("\n")

    if request.lines is not None:
        joined = "\n".join(request.lines)
        return text_to_board_array(joined, rows=rows, cols=cols), joined, list(request.lines)

    if request.fill is not None:
        grid = [[request.fill] * cols for _ in range(rows)]
        return grid, characters_to_message(grid), None

    if request.characters is not None:
        _validate_grid(request.characters, rows, cols)
        return request.characters, characters_to_message(request.characters), None

    # page_id — the remaining form, guaranteed by the request model.
    from src.pages.service import get_page_service

    page_service = get_page_service()
    result = page_service.preview_page(request.page_id, force_refresh=True)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Page not found: {request.page_id}")
    if not result.available:
        raise HTTPException(status_code=503, detail=result.error or "Page rendering failed")
    return (
        text_to_board_array(result.formatted, rows=rows, cols=cols),
        result.formatted,
        result.formatted.split("\n"),
    )


def _raise_for_executor(result: dict[str, Any]) -> None:
    """Turn an executor refusal into the status code it deserves.

    Blocked is policy, not breakage: silence and pause are both 409, the same
    verdict ``POST /send-message`` and ``POST /debug/fill`` give. Anything
    else the executor calls an error is a 500 — the 503 cases (no service, no
    client) are checked before it is ever called, so they cannot arrive here.
    """
    if result.get("status") == "blocked":
        raise HTTPException(status_code=409, detail=str(result.get("message")))
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=str(result.get("error") or "Failed to send to the board."))


def _raise_if_throttled(client) -> None:
    """A write the client-side send floor dropped is a 429 (#1868, #1754).

    Reuses the debug router's helper rather than restating its Retry-After
    arithmetic, so all three manual senders answer the same way.
    """
    from src.debug.routes import _raise_if_throttled as _debug_raise_if_throttled

    _debug_raise_if_throttled(client)


@router.post(
    "/boards/{board}/message",
    response_model=MessageResponse,
    responses=errors(400, 404, 409, 429, 500, 503),
    summary="Put something on a board",
    description=(
        "The one way to write to a board. Send exactly one of `text` (word-wrapped for you), `lines` (one string "
        "per row), `characters` (a raw flap grid), `page_id` (render a saved page) or `fill` (one flap code "
        "everywhere; 0 blanks the board).\n\n"
        "Add `duration_minutes` to make it temporary — it reverts to your schedule, a chosen page, or a blank board "
        "when the time is up. `board` may be a board id or the literal `primary`.\n\n"
        "`sent` in the response tells you whether flaps actually moved. It is false, with a `reason`, when the "
        "install's output target is UI-only and when the board already showed this exact content. A board that is "
        "paused or inside its silence window refuses the write with 409 rather than lying about it."
    ),
)
async def send_to_board(board: str, request: MessageRequest) -> MessageResponse:
    board_id, entry = resolve_board(board)
    settings_service = _settings_service()

    if request.revert_mode is not None and request.duration_minutes is None:
        raise HTTPException(status_code=400, detail="revert_mode requires duration_minutes")
    if request.revert_page_id is not None and request.revert_mode != "page":
        raise HTTPException(status_code=400, detail='revert_page_id requires revert_mode "page"')

    service = runtime.get_service()
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    if service.get_board_client(board_id) is None:
        raise HTTPException(status_code=503, detail=f"Board client not initialized: {board_id}")

    dims = board_dimensions(entry)
    characters, text, template_lines = _grid_for(request, dims.rows, dims.cols)

    expires_at = None
    if request.duration_minutes is not None:
        expires_at = await _arm_temporary_override(board_id, request, template_lines)

    if not settings_service.should_send_to_board():
        return MessageResponse(
            sent=False,
            board_id=board_id,
            characters=characters,
            text=text,
            expires_at=expires_at,
            reason=UI_ONLY_REASON,
        )

    transition = request.transition
    send_kwargs = {
        "strategy": transition.strategy if transition else None,
        "step_interval_ms": transition.interval_ms if transition else None,
        "step_size": transition.step_size if transition else None,
        "force": request.force,
    }

    from src.board_send_executor import run_board_send

    if request.text is not None:
        result = await run_board_send(executors.send_message, request.text, board_id, **send_kwargs)
    else:
        result = await run_board_send(executors.send_characters, characters, board_id, **send_kwargs)

    _raise_for_executor(result)

    if result.get("skipped"):
        _raise_if_throttled(service.get_board_client(board_id))
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


async def _arm_temporary_override(board_id: str, request: MessageRequest, template_lines: list[str] | None) -> str:
    """Store the timed-message state, and return when it expires.

    Delegates to ``POST /settings/temporary-override`` — the existing home of
    duration, revert mode and the inline one-off content of #1787 — rather
    than restating its validation. Two limits come from that mechanism and
    are reported rather than papered over: it is stored globally and applied
    by the display loop for the **primary** board only, and it can only hold
    text, so the raw-grid forms cannot be timed.
    """
    from src.settings.models import TemporaryOverrideRequest
    from src.settings.routes import set_temporary_override

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
        body["device_type"] = board.get("device_type") or "flagship"
        body["notes_wide"] = board.get("notes_wide") or 1
        body["notes_tall"] = board.get("notes_tall") or 1

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
        "the render or send failure when it is false."
    ),
)
async def set_board_active_page(board: str, request: ActivePageRequest) -> ActivePageResponse:
    from src.settings.models import SetActivePageRequest
    from src.settings.routes import set_active_page

    board_id = resolve_board_id(board)
    response = await set_active_page(SetActivePageRequest(page_id=request.page_id, board_id=board_id))
    return ActivePageResponse(
        board_id=board_id,
        page_id=response.get("page_id"),
        sent=bool(response.get("sent_to_board")),
        # #1791 added this to the internal response precisely so a 200 that
        # never reached the board is detectable. Dropping it made every v1
        # pin look like a success.
        error=response.get("error"),
        warnings=list(response.get("warnings") or []),
    )
