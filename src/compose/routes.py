"""Explicit Compose intent, with actor-bound polling and no mutation replay."""

from uuid import UUID

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from src.api_errors import errors
from src.board_send_executor import run_board_send
from src.override_undo import actor_identity
from src.v1.boards import resolve_board
from src.v1.router import router

from .ledger import ComposeHistoryFull, ComposeRequestConflict
from .models import ComposeError, ComposeReceipt, ComposeRequest, InvalidComposeDuration
from .service import recorded_outcome, submit

NO_STORE = {"Cache-Control": "no-store"}


@router.post(
    "/boards/{board}/compose",
    response_model=ComposeReceipt,
    responses={
        202: {"model": ComposeReceipt},
        **errors(404, 409, 429, 502, 503, models=dict.fromkeys((409, 429, 502, 503), ComposeError)),
    },
    summary="Show one captured Compose intent",
    description=(
        "Preserve original template formatting, captured display geometry, explicit duration and silence consent "
        "as one durable request UUID. Relative duration starts on accepted delivery, including a later Hold "
        "release. Exact duplicates read their original outcome and never send hardware again. A pending or "
        "unknown outcome is not physical success; poll the authenticated request outcome rather than replaying."
    ),
)
async def compose(board: str, request: ComposeRequest, raw_request: Request):
    board_id, _ = resolve_board(board)
    try:
        receipt = await run_board_send(submit, request, board_id=board_id, actor=actor_identity(raw_request))
    except (ComposeRequestConflict, InvalidComposeDuration) as exc:
        raise HTTPException(status_code=409, detail=str(exc), headers=NO_STORE) from exc
    except (ComposeHistoryFull, OSError, ValueError) as exc:
        raise HTTPException(
            status_code=503, detail="Compose history is unavailable; nothing was replayed", headers=NO_STORE
        ) from exc
    if receipt.status in {"sent", "unchanged"}:
        code = 200
    elif receipt.status in {"preparing", "dispatching", "held"}:
        code = 202
    elif receipt.retry_after_seconds is not None:
        code = 429
    elif receipt.status in {"expired", "superseded", "rejected"}:
        code = 409
    elif receipt.status in {"partial", "not_sent"}:
        code = 502
    else:
        code = 503
    body = receipt.model_dump(mode="json")
    headers = dict(NO_STORE)
    if receipt.retry_after_seconds is not None:
        headers["Retry-After"] = str(receipt.retry_after_seconds)
    return JSONResponse(body if code < 400 else {"detail": body}, status_code=code, headers=headers)


@router.get(
    "/boards/{board}/compose/{request_id}",
    response_model=ComposeReceipt,
    responses=errors(404, 409, 503),
    summary="Read this session's one-shot Compose outcome",
    description=(
        "Read the durable outcome of one Compose UUID issued by this authenticated session and target. "
        "This never dispatches hardware. Held, pending, accepted, unchanged, partial, expired and unknown "
        "outcomes remain distinct, and a replaced held intent is reported as superseded."
    ),
)
async def compose_outcome(board: str, request_id: UUID, raw_request: Request):
    board_id, _ = resolve_board(board)
    try:
        receipt = recorded_outcome(request_id, board_id=board_id, actor=actor_identity(raw_request))
    except ComposeRequestConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc), headers=NO_STORE) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Compose history is unavailable", headers=NO_STORE) from exc
    if receipt is None:
        raise HTTPException(status_code=404, detail="Compose request not found", headers=NO_STORE)
    return JSONResponse(receipt.model_dump(mode="json"), headers=NO_STORE)
