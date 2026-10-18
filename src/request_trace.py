"""Bounded diagnostics for page saves and v1 message requests.

These phase logs localize a stalled request, not its cause. No user-supplied
identifiers, paths, headers or payloads are logged. Context propagation into
the existing send pool keeps worker phases correlated without a new pool.
"""

from __future__ import annotations

import asyncio
import logging
import re
from contextvars import ContextVar
from dataclasses import dataclass
from time import monotonic
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Trace:
    trace_id: str
    operation: str
    started: float


_current: ContextVar[_Trace | None] = ContextVar("request_trace", default=None)


def trace_phase(phase: str) -> None:
    """Emit a fixed, developer-owned phase label; no-op outside traced requests."""
    trace = _current.get()
    if trace is None:
        return
    elapsed_ms = (monotonic() - trace.started) * 1000
    logger.info(
        "Request trace id=%s operation=%s phase=%s elapsed_ms=%.3f",
        trace.trace_id,
        trace.operation,
        phase,
        elapsed_ms,
        extra={"trace_id": trace.trace_id, "trace_phase": phase, "elapsed_ms": elapsed_ms},
    )


class RequestTraceMiddleware:
    """Trace only the two incident request families; never consume the body."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        operation = None
        if scope["type"] == "http":
            method, path = scope["method"], scope["path"]
            if method == "PUT" and re.fullmatch(r"/(?:v1/)?pages/[^/]+", path):
                operation = "page_save"
            elif method == "POST" and re.fullmatch(r"/v1/boards/[^/]+/message", path):
                operation = "board_message"
        if operation is None:
            await self.app(scope, receive, send)
            return

        trace = _Trace(uuid4().hex, operation, monotonic())
        token = _current.set(trace)

        async def traced_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                trace_phase("response_started")
                message = dict(message)
                message["headers"] = [
                    *message.get("headers", []),
                    (b"x-fiestaboard-trace-id", trace.trace_id.encode("ascii")),
                ]
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                # ASGI send returned; this does NOT establish client receipt.
                trace_phase("response_body_sent")

        try:
            trace_phase("request_started")
            await self.app(scope, receive, traced_send)
        except asyncio.CancelledError:
            trace_phase("request_cancelled")
            raise
        except BaseException:
            trace_phase("request_failed")
            raise
        finally:
            _current.reset(token)
