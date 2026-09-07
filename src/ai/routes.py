"""FastAPI router for server-side execution of chat operations.

Phase 2, Task 11. ``src/ops`` was built so "chat and MCP cannot diverge"
(#1764), but until this endpoint existed only MCP called the executors:
the browser ran its own ``switch (call.op)`` over a dozen REST endpoints,
so the ops layer had **zero** production callers on the chat path and the
two surfaces could still drift — and did (see
``tests/test_chat_op_http_parity.py`` for the three divergences that were
live in the shipped browser dispatcher).

This router is the chat surface's execution seam. The web drawer posts a
validated tool call here; the registry validates the args against the same
pydantic models ``parse_tool_call`` uses and dispatches to the one
canonical executor MCP already uses.

Conventions (``docs/internal/reference/API_CONVENTIONS.md``): typed
request model, declared ``response_model``, declared 4xx, and failures as
``HTTPException`` — never a 200 carrying ``{"status": "error"}``. The
executors' error envelope is deliberately *not* forwarded at 200: the
browser's previous per-op REST calls raised on failure, and the chat
drawer's ``chainAfter`` wrapper depends on that to build the
``[Tool result: ... Failed: ...]`` transcript line.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.api_errors import errors
from src.ops import registry
from src.ops.grammar import ToolCallValidationError

router = APIRouter(prefix="/ai", tags=["ai"])

#: Envelope keys that become response fields of their own; everything else
#: an executor returned (``schedule_id``, ``plugin_id``, ``config``, ...) is
#: carried through in ``result``.
_ENVELOPE_KEYS = ("status", "message", "error")


class OperationRequest(BaseModel):
    """One chat-grammar tool call: the op name plus its raw args.

    ``args`` is intentionally free-form here — it is validated one layer
    down against the op's own pydantic model (the exact schema the SSE
    ``tool_call`` frame was validated with), so declaring a union of every
    op's args on this model would duplicate the grammar and let the two
    copies drift.
    """

    model_config = ConfigDict(extra="forbid")

    op: str = Field(..., min_length=1, max_length=100, description="Chat-grammar operation name.")
    args: dict[str, Any] = Field(default_factory=dict, description="Operation arguments, validated by the grammar.")


class OperationResponse(BaseModel):
    """The executed operation's success envelope.

    ``status`` is a constant: a failed operation is an HTTP error, not a
    200 with a sad payload.
    """

    op: str
    status: Literal["success"] = "success"
    message: str
    result: dict[str, Any] = Field(default_factory=dict)


async def _dispatch(op_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Run one operation, keeping blocking executors off the event loop.

    Most executors are synchronous and do file IO (page/schedule/collection
    stores, ``config.json``, plugin installs) — the ``asyncio.to_thread``
    treatment the rest of the codebase gives blocking work. The async ones
    (``install_plugin``, ``update_plugin``, ``update_setting``,
    ``trigger_system_update``) are awaited directly.
    """
    operation = registry.get_operation(op_name)
    if inspect.iscoroutinefunction(operation.executor):
        return await registry.execute(op_name, args)
    return await asyncio.to_thread(registry.execute_sync, op_name, args)


@router.post(
    "/operations",
    response_model=OperationResponse,
    responses=errors(400, 404, 422),
    summary="Execute one chat-grammar operation server-side",
)
async def execute_operation(request: OperationRequest) -> OperationResponse:
    """Validate and execute a chat tool call through the shared ops layer.

    - unknown op, or an op the chat grammar does not spell → **404**
    - an op the web UI applies in the browser → **400** naming the op
    - args that fail the grammar's schema → **422** with pydantic's detail
    - an executor that reported failure → **400** with its message
    """
    try:
        operation = registry.get_operation(request.op)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown operation: {request.op!r}.") from None

    if operation.chat_name != request.op:
        # Canonical/MCP-only spellings (send_message, delete_page, ...) are
        # not part of the chat grammar; serving them here would grow a third
        # surface with no validation schema behind it.
        raise HTTPException(
            status_code=404,
            detail=f"Operation {request.op!r} is not part of the chat operation grammar.",
        )

    if operation.client_side:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Operation {request.op!r} is applied in the browser by the web UI and has no server-side executor."
            ),
        )

    try:
        envelope = await _dispatch(request.op, request.args)
    except ToolCallValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except registry.ClientSideOperationError as exc:  # pragma: no cover - guarded above
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if envelope.get("status") != "success":
        detail = envelope.get("error") or envelope.get("message") or f"Operation {request.op!r} failed."
        raise HTTPException(status_code=400, detail=str(detail))

    return OperationResponse(
        op=request.op,
        message=str(envelope.get("message", "")),
        result={k: v for k, v in envelope.items() if k not in _ENVELOPE_KEYS},
    )
