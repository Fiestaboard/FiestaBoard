"""The server-side agent loop behind ``POST /pages/ai/chat``.

One user turn used to be one provider request: the model's reply streamed
to the browser, the browser executed any tool block it contained, and the
browser re-POSTed the whole transcript with a ``[Tool result: …]`` line to
let the model continue. The loop lived in React, and the server never
learned whether a tool had run.

Now the loop lives here. One SSE stream spans as many model calls and tool
executions as the turn needs, and every tool runs through the same
in-process MCP server external clients use (:mod:`src.ai.mcp_bridge`). The
browser's job becomes showing the work — it receives a ``tool_call`` frame
*before* each execution and a ``tool_result`` frame after — and answering
the two questions only a person can: approve a destructive tool, or reply
to ``ask_user``. Both pause the loop by ending the stream with a ``done``
frame whose ``reason`` says what is awaited; the client resumes by
re-POSTing the transcript with a ``resume`` decision.

Design points worth knowing before editing:

- **Read-only tools run freely, destructive tools wait.** The MCP tool
  annotations decide which is which (``ToolDescriptor.requires_approval``);
  this module keeps no list of its own.
- **The provider gate is held only around the model call.** The semaphore
  ``page_routes`` shares with ``/generate`` used to be held for a whole
  stream; a slow plugin install inside the loop would have starved the
  editor's one-shot generation.
- **A tool already running finishes even if the browser leaves.** Starlette
  cancels the response task on disconnect; the call is shielded so a write
  is never left half-applied. The client's copy of the transcript already
  holds the ``tool_call``, and renders it as *interrupted* next turn.
- **Every event name emitted here is a literal in a ``{"event": ...}``
  dict.** ``tests/test_ai_pages_contract.py`` walks this module's source to
  keep :data:`~src.ai.page_routes.CHAT_STREAM_EVENTS` honest; a helper that
  built the dict dynamically would blind that test.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator, Awaitable
from dataclasses import dataclass
from typing import Any

import httpx

from src.devices import DeviceType

from .chat import _DEFAULT_TIMEOUT_SECONDS, _FenceParser, stream_model
from .chat_tools import ASK_USER
from .generator import AIGenerationError, _resolve_model, _resolve_provider, _user_safe_error_message
from .mcp_bridge import ToolBackend, ToolBackendUnavailable, ToolDescriptor, ToolOutcome
from .prompt_builder import build_prompt
from .protocols import get_protocol
from .tool_catalog import ChatSurface, ToolCatalog
from .transcript import pending_tool_call, render_transcript

logger = logging.getLogger(__name__)

#: Longest ``result`` payload put on the wire. The transcript has its own,
#: tighter cap (:data:`src.ai.transcript.MAX_RESULT_CHARS`).
MAX_WIRE_RESULT_CHARS = 16_000


@dataclass(frozen=True)
class TurnLimits:
    """Runaway protection for one turn. Each is a count, not a budget."""

    max_model_calls: int = 8
    max_tool_calls: int = 12
    max_self_corrections: int = 2


async def run_chat_turn(
    *,
    client: httpx.AsyncClient | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    **kwargs: Any,
) -> AsyncIterator[dict[str, Any]]:
    """Run one chat turn; see :func:`_run_chat_turn` for the parameters.

    Owns one HTTP client for the whole turn when the caller passes none, so
    the (up to ``max_model_calls``) provider requests of a turn reuse a
    connection instead of paying a TCP + TLS handshake each.
    """
    if client is not None:
        async for event in _run_chat_turn(client=client, timeout_seconds=timeout_seconds, **kwargs):
            yield event
        return
    async with httpx.AsyncClient(timeout=timeout_seconds) as owned:
        async for event in _run_chat_turn(client=owned, timeout_seconds=timeout_seconds, **kwargs):
            yield event


async def _run_chat_turn(
    *,
    messages: list[dict[str, Any]],
    resume: dict[str, Any] | None,
    device_type: DeviceType,
    surface: ChatSurface,
    providers_block: dict[str, Any],
    backend: ToolBackend,
    variables: dict[str, dict[str, dict[str, Any]]] | None = None,
    plugin_demos: list[dict[str, Any]] | None = None,
    current_page: dict[str, Any] | None = None,
    available_pages: list[dict[str, Any]] | None = None,
    installed_plugins: list[dict[str, Any]] | None = None,
    available_schedules: list[dict[str, Any]] | None = None,
    available_collections: list[dict[str, Any]] | None = None,
    registry_plugins: list[dict[str, Any]] | None = None,
    provider_id: str | None = None,
    model: str | None = None,
    provider_gate: asyncio.Semaphore | None = None,
    client: httpx.AsyncClient | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    limits: TurnLimits = TurnLimits(),
) -> AsyncIterator[dict[str, Any]]:
    """Run one user turn to completion or to a pause. Yields stream events."""
    try:
        provider = _resolve_provider(providers_block, provider_id)
        chosen_model = _resolve_model(provider, model)
    except AIGenerationError as exc:
        yield {"event": "error", "data": {"message": _user_safe_error_message(exc)}}
        return
    protocol = get_protocol(provider.get("protocol"))

    try:
        catalog = ToolCatalog(await backend.list_tools())
    except ToolBackendUnavailable as exc:
        logger.error("AI chat has no tool backend: %s", exc)
        yield {"event": "error", "data": {"message": "AI chat needs the MCP server, which failed to initialise."}}
        return

    transcript: list[dict[str, Any]] = [dict(m) for m in messages]
    usage: dict[str, int | None] = {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}
    steps = 0
    tool_calls_made = 0
    self_corrections = 0

    # -- a decision the client is sending back -------------------------------
    if resume is not None:
        pending = pending_tool_call(transcript)
        wanted = resume.get("tool_call_id")
        if pending is None or pending["id"] != wanted:
            yield {"event": "error", "data": {"message": f"No tool call {wanted!r} is awaiting a decision."}}
            return
        decision = resume.get("decision")
        if decision == "approve":
            yield {
                "event": "status",
                "data": {
                    "phase": "tool_running",
                    "message": f"Running {pending['name']}…",
                    "tool_call_id": pending["id"],
                    "step": steps,
                },
            }
            outcome = await _run_shielded(
                backend.call_tool(pending["name"], pending.get("args") or {}), pending["name"]
            )
            tool_calls_made += 1
            yield {"event": "tool_result", "data": _tool_result_data(pending["id"], pending["name"], outcome)}
            _record_outcome(transcript, pending["id"], _tool_message(pending, outcome))
        elif decision == "deny":
            denied = ToolOutcome(status="denied")
            yield {"event": "tool_result", "data": _tool_result_data(pending["id"], pending["name"], denied)}
            _record_outcome(transcript, pending["id"], _tool_message(pending, denied))
        elif decision == "answer":
            _record_outcome(transcript, pending["id"], _answer_message(pending, resume.get("answer") or {}))
        else:
            yield {"event": "error", "data": {"message": f"Unknown resume decision {decision!r}."}}
            return

    # -- the system prompt, once per turn --------------------------------------
    last_user_text = next((m.get("content") or "" for m in reversed(transcript) if m.get("role") == "user"), "")
    context = build_prompt(
        user_prompt=last_user_text or "(continue)",
        device_type=device_type,
        variables=variables,
        plugin_demos=plugin_demos,
        current_page=current_page,
        available_pages=available_pages,
        installed_plugins=installed_plugins,
        available_schedules=available_schedules,
        available_collections=available_collections,
        registry_plugins=registry_plugins,
        mode="chat",
    )
    system_message = {"role": "system", "content": context.system_prompt + catalog.render_addendum(surface)}
    # ``to_messages`` puts the "refining an existing page" note just before
    # the prompt; keep that placement so the draft stays adjacent to the ask.
    page_note = context.to_messages()[1] if current_page is not None else None

    # -- the loop ----------------------------------------------------------------
    while steps < limits.max_model_calls:
        steps += 1
        yield {
            "event": "status",
            "data": {"phase": "thinking", "message": "Thinking…", "tool_call_id": None, "step": steps},
        }

        rendered = render_transcript(transcript)
        provider_messages = [system_message, *rendered[:-1], *([page_note] if page_note else []), rendered[-1]]
        parser = _FenceParser(catalog.validate)
        call_usage: dict[str, int | None] = {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}
        text_parts: list[str] = []
        calls: list[dict[str, Any]] = []
        grammar_warnings: list[str] = []
        fatal = False

        async with _gate(provider_gate):
            async for event in stream_model(
                protocol=protocol,
                provider=provider,
                model=chosen_model,
                messages=provider_messages,
                parser=parser,
                usage=call_usage,
                client=client,
                timeout_seconds=timeout_seconds,
            ):
                kind = event["event"]
                if kind == "text":
                    text_parts.append(event["data"]["delta"])
                    yield event
                elif kind == "tool_call":
                    calls.append(event["data"])
                elif kind == "warning":
                    grammar_warnings.append(event["data"]["message"])
                    yield event
                else:  # error — fatal by contract, stream ends
                    yield event
                    fatal = True
                    break
        if fatal:
            return
        _absorb_usage(usage, call_usage)

        transcript.append(
            {
                "role": "assistant",
                "content": "".join(text_parts),
                "tool_calls": [{"id": c["id"], "name": c["name"], "args": c["args"]} for c in calls] or None,
            }
        )

        if not calls:
            if grammar_warnings and self_corrections < limits.max_self_corrections:
                # The model tried to act and got the block wrong. Show it the
                # parser's own message once or twice; a model that keeps
                # failing gets a normal prose turn, not an endless loop.
                self_corrections += 1
                transcript.append(
                    {
                        "role": "user",
                        "content": "[Tool error] "
                        + " ".join(grammar_warnings)
                        + " Fix the block and try again, or reply in prose.",
                    }
                )
                continue
            yield {"event": "done", "data": _done(chosen_model, provider, usage, "complete", None, steps)}
            return

        for index, call in enumerate(calls):
            descriptor = catalog.get(call["name"])
            assert descriptor is not None  # the parser only yields catalog names
            wire = _tool_call_data(call, descriptor)
            remaining = len(calls) - index - 1

            if call["name"] == ASK_USER:
                yield {"event": "tool_call", "data": wire}
                yield {"event": "elicitation", "data": _elicitation_data(call)}
                if remaining:
                    yield {
                        "event": "warning",
                        "data": {"message": _ignored(remaining, call["name"], "a question for the user")},
                    }
                yield {
                    "event": "done",
                    "data": _done(chosen_model, provider, usage, "awaiting_input", call["id"], steps),
                }
                return

            if descriptor.requires_approval:
                yield {"event": "tool_call", "data": wire}
                if remaining:
                    yield {"event": "warning", "data": {"message": _ignored(remaining, call["name"], "approval")}}
                yield {
                    "event": "done",
                    "data": _done(chosen_model, provider, usage, "awaiting_approval", call["id"], steps),
                }
                return

            if tool_calls_made >= limits.max_tool_calls:
                yield {
                    "event": "warning",
                    "data": {"message": f"Stopped after {tool_calls_made} tool calls (the per-turn limit)."},
                }
                yield {"event": "done", "data": _done(chosen_model, provider, usage, "step_limit", None, steps)}
                return

            yield {"event": "tool_call", "data": wire}
            yield {
                "event": "status",
                "data": {
                    "phase": "tool_running",
                    "message": f"Running {call['name']}…",
                    "tool_call_id": call["id"],
                    "step": steps,
                },
            }
            outcome = await _run_shielded(backend.call_tool(call["name"], call["args"]), call["name"])
            tool_calls_made += 1
            yield {"event": "tool_result", "data": _tool_result_data(call["id"], call["name"], outcome)}
            transcript.append(_tool_message(call, outcome))

    yield {"event": "warning", "data": {"message": f"Stopped after {steps} model calls (the per-turn limit)."}}
    yield {"event": "done", "data": _done(chosen_model, provider, usage, "step_limit", None, steps)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gate(semaphore: asyncio.Semaphore | None) -> Any:
    return semaphore if semaphore is not None else contextlib.nullcontext()


async def _run_shielded(call: Awaitable[ToolOutcome], name: str) -> ToolOutcome:
    """Run a tool so that a client disconnect cannot cut it in half.

    Starlette cancels the response task when the browser goes away, which
    raises ``CancelledError`` at whatever ``await`` the generator is on.
    The tool keeps running in its own task; the orphaned outcome is logged
    by a done-callback (never awaited — the cancelled scope re-raises on
    the next await).
    """
    task = asyncio.ensure_future(call)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        task.add_done_callback(lambda t: _log_orphan(name, t))
        raise


def _log_orphan(name: str, task: asyncio.Task[ToolOutcome]) -> None:
    if task.cancelled():
        logger.info("AI chat: tool %s was cancelled after the client left", name)
        return
    exc = task.exception()
    if exc is not None:
        logger.warning("AI chat: tool %s failed after the client left: %s", name, exc)
    else:
        logger.info("AI chat: tool %s finished after the client left: %s", name, task.result().status)


def _absorb_usage(total: dict[str, int | None], call: dict[str, int | None]) -> None:
    for key in ("prompt_tokens", "completion_tokens"):
        if isinstance(call.get(key), int):
            total[key] = (total[key] or 0) + call[key]  # type: ignore[operator]
    p, c = total["prompt_tokens"], total["completion_tokens"]
    total["total_tokens"] = p + c if isinstance(p, int) and isinstance(c, int) else None


def _done(
    model: str, provider: dict[str, Any], usage: dict[str, int | None], reason: str, pending: str | None, steps: int
) -> dict[str, Any]:
    return {
        "model_used": model,
        "provider_id": provider.get("id"),
        "usage": dict(usage),
        "reason": reason,
        "pending_tool_call_id": pending,
        "steps": steps,
    }


def _tool_call_data(call: dict[str, Any], descriptor: ToolDescriptor) -> dict[str, Any]:
    return {
        "id": call["id"],
        "name": call["name"],
        "args": call["args"],
        "title": descriptor.title,
        "read_only": descriptor.read_only,
        "destructive": descriptor.destructive,
        "requires_approval": descriptor.requires_approval,
        "source": descriptor.source,
    }


def _tool_result_data(call_id: str, name: str, outcome: ToolOutcome) -> dict[str, Any]:
    return {
        "id": call_id,
        "name": name,
        "status": outcome.status,
        "summary": _summary(name, outcome),
        "result": _cap(outcome.result),
        "error": outcome.error,
    }


def _summary(name: str, outcome: ToolOutcome) -> str:
    if outcome.status == "denied":
        return "Not run."
    if outcome.status == "error":
        return outcome.error or f"{name} failed."
    result = outcome.result
    if isinstance(result, dict) and isinstance(result.get("message"), str):
        return result["message"]
    if outcome.status == "blocked":
        return f"{name} was blocked."
    if isinstance(result, list):
        return f"{name} returned {len(result)} items."
    return f"{name} completed."


def _cap(result: Any) -> Any:
    if result is None:
        return None
    text = json.dumps(result, ensure_ascii=False)
    if len(text) <= MAX_WIRE_RESULT_CHARS:
        return result
    return {"truncated": True, "preview": text[:MAX_WIRE_RESULT_CHARS]}


def _tool_message(call: dict[str, Any], outcome: ToolOutcome) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": call["id"],
        "name": call["name"],
        "status": outcome.status,
        "result": outcome.result if outcome.status != "error" else {"error": outcome.error},
    }


def _record_outcome(transcript: list[dict[str, Any]], call_id: str, message: dict[str, Any]) -> None:
    """Put a call's outcome where the server would have put it: right after
    the assistant turn that made the call (after any outcomes already
    there), not at the end.

    Stop-then-type sends the decision *with* a new user message; appending
    the outcome after that message would let the renderer flush the call as
    "interrupted" before it sees the denial, and the model would be told
    both.
    """
    for index, entry in enumerate(transcript):
        if entry.get("role") != "assistant":
            continue
        if any(call.get("id") == call_id for call in entry.get("tool_calls") or []):
            insert_at = index + 1
            while insert_at < len(transcript) and transcript[insert_at].get("role") == "tool":
                insert_at += 1
            transcript.insert(insert_at, message)
            return
    transcript.append(message)


def _answer_message(call: dict[str, Any], answer: dict[str, Any]) -> dict[str, Any]:
    action = answer.get("action", "accept")
    content = answer.get("content")
    if action == "accept" and content is not None:
        value = content.get("answer", content) if isinstance(content, dict) else content
    elif action == "cancel":
        value = "(the user cancelled the question; continue without an answer)"
    else:
        value = "(the user declined to answer; continue without it)"
    return {
        "role": "tool",
        "tool_call_id": call["id"],
        "name": call["name"],
        "status": "answered",
        "result": {"answer": value},
    }


def _elicitation_data(call: dict[str, Any]) -> dict[str, Any]:
    """``ask_user`` in the shape of an MCP elicitation request.

    Same field names as ``elicitation/create`` so the client renders both
    with one component once in-process MCP elicitation lands.
    """
    args = call.get("args") or {}
    options = args.get("options")
    answer: dict[str, Any] = {"type": "string", "title": "Answer"}
    if isinstance(options, list) and options:
        answer["enum"] = [str(o) for o in options]
    return {
        "id": call["id"],
        "name": call["name"],
        "message": str(args.get("question") or ""),
        "requested_schema": {"type": "object", "properties": {"answer": answer}, "required": ["answer"]},
        "allow_free_text": bool(args.get("allow_free_text", True)),
    }


def _ignored(count: int, name: str, why: str) -> str:
    return f"Ignored {count} further tool block(s) after {name}, which is waiting on {why}; they can be re-issued next turn."


__all__ = ["TurnLimits", "run_chat_turn"]
