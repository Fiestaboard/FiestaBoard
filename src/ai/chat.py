"""Streaming model calls for the AI chat.

One provider request, normalized. :func:`stream_model` sends a prepared
message list to the user's configured LLM and yields events the agent loop
(:mod:`src.ai.agent`) consumes:

    event: text       data: {"delta": "..."}
    event: tool_call  data: {"id": "...", "name": "...", "args": {...}}
    event: warning    data: {"message": "..."}
    event: error      data: {"message": "..."}

The loop — which tools exist, running them, pausing for approval, calling
the model again — lives in ``agent.py``. What lives here is the wire: the
two provider protocols' SSE framing (:mod:`src.ai.protocols`) and the
streaming state machine that splits the model's prose from its
triple-backtick ``fiestaboard`` fenced JSON blocks. A completed block is
handed to the validator the caller supplied (the tool catalog's, built from
the MCP server's own tool list) so the parser never carries a grammar of
its own.

Validation failures yield a ``warning`` event but do **not** abort the
stream — the model often follows a bad block with corrective prose, and
the loop feeds the warning back for one self-correction.
"""

from __future__ import annotations

import json
import logging
import re
import secrets
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx

from .generator import _user_safe_error_message
from .protocols import Protocol
from .template_validator import repair_template_lines
from .tool_catalog import ParsedToolCall, ToolCallValidationError

logger = logging.getLogger(__name__)


_DEFAULT_TEMPERATURE = 0.7
_DEFAULT_MAX_TOKENS = 2000
_DEFAULT_TIMEOUT_SECONDS = 120.0


# ---------------------------------------------------------------------------
# One model call.
# ---------------------------------------------------------------------------


async def stream_model(
    *,
    protocol: Protocol,
    provider: dict[str, Any],
    model: str,
    messages: list[dict[str, str]],
    parser: _FenceParser,
    usage: dict[str, int | None],
    client: httpx.AsyncClient | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
) -> AsyncIterator[dict[str, Any]]:
    """Stream one completion; yield ``text`` / ``tool_call`` / ``warning`` /
    ``error`` events. Token counts land in ``usage`` (mutated in place — an
    async generator cannot return a value).

    An ``error`` event is terminal: nothing follows it and the caller must
    not call the model again on this turn.
    """
    payload = protocol.build_body(model, messages, _DEFAULT_TEMPERATURE, _DEFAULT_MAX_TOKENS)
    # Both adapters honor ``stream: true``. The one-shot generator forces
    # ``response_format: json_object`` for OpenAI; chat wants prose around
    # the tool block, so it goes.
    payload["stream"] = True
    payload.pop("response_format", None)

    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=timeout_seconds)
    assert client is not None

    last_warning: str | None = None
    try:
        if not provider.get("base_url"):
            yield {"event": "error", "data": {"message": "AI provider has no base_url configured."}}
            return
        url = f"{(provider.get('base_url') or '').rstrip('/')}{protocol.request_path}"
        extra = provider.get("headers") or {}
        headers = protocol.build_headers(
            provider.get("api_key") or "",
            extra if isinstance(extra, dict) else {},
        )

        try:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                if response.status_code >= 400:
                    err_msg = await _extract_error_message(response, protocol)
                    yield {
                        "event": "error",
                        "data": {"message": (f"AI provider returned {response.status_code}: {err_msg}")},
                    }
                    return

                async for delta_event in _iter_provider_stream(response, protocol, usage):
                    if delta_event["kind"] == "text":
                        for emit in parser.feed(delta_event["text"]):
                            yield emit
                    elif delta_event["kind"] == "warning":
                        last_warning = delta_event["message"]

                for emit in parser.flush():
                    yield emit
        except httpx.HTTPError as exc:
            logger.warning("AI chat HTTP error: %s", exc)
            yield {"event": "error", "data": {"message": "Could not reach AI provider."}}
            return

        if last_warning:
            yield {"event": "warning", "data": {"message": last_warning}}
    finally:
        if owns_client:
            await client.aclose()


# ---------------------------------------------------------------------------
# Provider stream parser — normalizes upstream SSE chunks into text deltas.
# ---------------------------------------------------------------------------


async def _extract_error_message(response: httpx.Response, protocol: Protocol) -> str:
    """Best-effort extraction of an upstream error message."""
    try:
        body = await response.aread()
    except Exception:
        return "(no body)"
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            msg = protocol.parse_error(parsed)
            if msg:
                return msg
    except Exception:
        pass
    try:
        return body.decode("utf-8", errors="replace")[:500]
    except Exception:
        return "(unreadable body)"


async def _iter_provider_stream(
    response: httpx.Response,
    protocol: Protocol,
    usage: dict[str, int | None],
) -> AsyncIterator[dict[str, Any]]:
    """Yield ``{"kind": "text", "text": "..."}`` events as deltas arrive.

    Both supported protocols emit SSE-formatted streams:

    - OpenAI-compatible: ``data: {choices: [{delta: {content: "..."}}]}``
      lines, terminated by ``data: [DONE]``.
    - Anthropic: typed events (``content_block_delta``,
      ``message_delta``, ``message_stop``, …) where the text deltas are
      in ``delta.text``.

    We dispatch on protocol name. Anything we can't parse is silently
    skipped — we don't want a malformed keepalive to abort the stream.
    """
    proto_name = protocol.name
    async for line in response.aiter_lines():
        if not line:
            continue
        line = line.strip()
        if not line.startswith("data:") and proto_name == "openai":
            # Some servers prefix with `event: ...` lines we can ignore.
            continue
        # Strip ``data: `` prefix; Anthropic also uses ``event: ...`` +
        # ``data: ...`` pairs but only the data line matters to us.
        if line.startswith("event:"):
            continue
        if line.startswith("data:"):
            line = line[5:].strip()
        if not line:
            continue
        if line == "[DONE]":
            return
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        if proto_name == "anthropic":
            text = _anthropic_delta_text(event)
            if text:
                yield {"kind": "text", "text": text}
            _absorb_anthropic_usage(event, usage)
        else:
            text = _openai_delta_text(event)
            if text:
                yield {"kind": "text", "text": text}
            _absorb_openai_usage(event, usage)


def _openai_delta_text(event: dict[str, Any]) -> str:
    choices = event.get("choices") or []
    if not choices:
        return ""
    delta = choices[0].get("delta") or {}
    content = delta.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") in (None, "text"):
                text = part.get("text", "")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def _absorb_openai_usage(event: dict[str, Any], usage: dict[str, int | None]) -> None:
    u = event.get("usage")
    if isinstance(u, dict):
        if isinstance(u.get("prompt_tokens"), int):
            usage["prompt_tokens"] = u["prompt_tokens"]
        if isinstance(u.get("completion_tokens"), int):
            usage["completion_tokens"] = u["completion_tokens"]
        if isinstance(u.get("total_tokens"), int):
            usage["total_tokens"] = u["total_tokens"]


def _anthropic_delta_text(event: dict[str, Any]) -> str:
    if event.get("type") == "content_block_delta":
        delta = event.get("delta") or {}
        if delta.get("type") == "text_delta":
            text = delta.get("text", "")
            if isinstance(text, str):
                return text
    return ""


def _absorb_anthropic_usage(event: dict[str, Any], usage: dict[str, int | None]) -> None:
    if event.get("type") == "message_start":
        msg = event.get("message") or {}
        u = msg.get("usage") or {}
        if isinstance(u.get("input_tokens"), int):
            usage["prompt_tokens"] = u["input_tokens"]
    if event.get("type") == "message_delta":
        u = event.get("usage") or {}
        if isinstance(u.get("output_tokens"), int):
            usage["completion_tokens"] = u["output_tokens"]
    p = usage.get("prompt_tokens")
    c = usage.get("completion_tokens")
    if isinstance(p, int) and isinstance(c, int):
        usage["total_tokens"] = p + c


# ---------------------------------------------------------------------------
# Streaming fence parser.
# ---------------------------------------------------------------------------


_FENCE_OPEN_RE = re.compile(r"```fiestaboard\b")
_FENCE_CLOSE_RE = re.compile(r"```")


class _FenceParser:
    """Buffer streamed text and split it into prose vs. fenced JSON.

    Why a class: fences may straddle chunk boundaries, so we keep state
    (current mode + a small look-back) across ``feed()`` calls.

    Emits dicts in the same shape as the public event stream, so the
    caller can yield them straight through.
    """

    def __init__(self, validate: Callable[[object], ParsedToolCall]) -> None:
        # The validator is the catalog's: it knows which tools exist this
        # turn and what they take. The parser only knows fences.
        self._validate = validate
        self._buffer: str = ""
        self._in_fence: bool = False
        self._fence_buffer: str = ""

    def feed(self, chunk: str) -> list[dict[str, Any]]:
        """Feed a text delta; return zero or more events to emit.

        While outside a fence we emit text deltas as soon as we know they
        can't be part of an opening fence marker. Inside a fence we
        accumulate silently until the closing triple-backtick, then
        validate and emit either a ``tool_call`` or a ``warning``.
        """
        events: list[dict[str, Any]] = []
        self._buffer += chunk
        while True:
            if self._in_fence:
                close = _FENCE_CLOSE_RE.search(self._buffer)
                if not close:
                    # Move everything except a trailing ``` candidate
                    # into the fence buffer so we can complete on the
                    # next chunk.
                    safe_len = max(0, len(self._buffer) - 3)
                    self._fence_buffer += self._buffer[:safe_len]
                    self._buffer = self._buffer[safe_len:]
                    return events
                # Close: text up to start of ``` is the final fence
                # contents.
                self._fence_buffer += self._buffer[: close.start()]
                self._buffer = self._buffer[close.end() :]
                events.extend(self._finalize_fence())
                self._in_fence = False
                self._fence_buffer = ""
                # Loop back in case the buffer also contains another
                # fence open after the close.
                continue

            # Outside a fence: look for an opening marker.
            m = _FENCE_OPEN_RE.search(self._buffer)
            if not m:
                # Hold back the last few chars in case a fence open
                # straddles the chunk boundary (``\`\`\`f`` etc.).
                hold = min(len(self._buffer), len(self._safe_open_tail()))
                if hold > 0:
                    safe = self._buffer[:-hold]
                    if safe:
                        events.append({"event": "text", "data": {"delta": safe}})
                    self._buffer = self._buffer[-hold:]
                else:
                    if self._buffer:
                        events.append({"event": "text", "data": {"delta": self._buffer}})
                    self._buffer = ""
                return events

            # Emit any prose before the fence.
            prose = self._buffer[: m.start()]
            if prose:
                events.append({"event": "text", "data": {"delta": prose}})
            # Skip past the fence open marker; allow optional trailing
            # newline before the body starts.
            after = self._buffer[m.end() :]
            if after.startswith("\r\n"):
                after = after[2:]
            elif after.startswith("\n"):
                after = after[1:]
            self._buffer = after
            self._in_fence = True
            self._fence_buffer = ""

    def flush(self) -> list[dict[str, Any]]:
        """Drain any remaining buffered text after the stream closes."""
        events: list[dict[str, Any]] = []
        if self._in_fence:
            # Unterminated fence — surface as a warning rather than
            # losing the content silently.
            events.append(
                {
                    "event": "warning",
                    "data": {"message": ("Model emitted an unterminated `fiestaboard` fence; ignored.")},
                }
            )
            self._in_fence = False
            self._fence_buffer = ""
        elif self._buffer:
            events.append({"event": "text", "data": {"delta": self._buffer}})
        self._buffer = ""
        return events

    def _safe_open_tail(self) -> str:
        """Longest prefix of the open marker we might be straddling.

        We don't know yet whether ``self._buffer`` ends with the start
        of a fence (e.g. ```` ```fiestabo ````), so retain enough
        trailing chars to disambiguate on the next ``feed``.
        """
        marker = "```fiestaboard"
        for size in range(min(len(marker), len(self._buffer)), 0, -1):
            if self._buffer.endswith(marker[:size]):
                return marker[:size]
        return ""

    def _finalize_fence(self) -> list[dict[str, Any]]:
        """Parse, validate, and repair a completed fenced block.

        Returns a list of events: zero or one ``warning`` events for
        each template repair we performed, plus exactly one terminal
        event — either ``tool_call`` (on success) or ``warning`` (on
        parse/validation failure).
        """
        body = self._fence_buffer.strip()
        if not body:
            return [
                {
                    "event": "warning",
                    "data": {"message": "Empty fiestaboard tool block; ignored."},
                }
            ]
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            return [
                {
                    "event": "warning",
                    "data": {"message": (f"Could not parse fiestaboard tool block: {exc.msg}")},
                }
            ]
        try:
            tool = self._validate(parsed)
        except ToolCallValidationError as exc:
            # The validator's messages are written for the model ("Unknown
            # tool 'replace_page'. Closest: create_page …"), but anything
            # unexpected that escapes as this type is bounded before it goes
            # on the wire (CodeQL: py/stack-trace-exposure).
            logger.warning("Invalid fiestaboard tool block: %s", exc)
            detail = _user_safe_error_message(exc, fallback="schema validation failed")
            return [
                {
                    "event": "warning",
                    "data": {"message": f"Invalid fiestaboard tool block: {detail}"},
                }
            ]

        # Repair common ``{{filled:...}}`` mistakes in any template lines the
        # call carries. The args are mutated in place and a warning is
        # emitted per repair so the user (and, via the transcript, the
        # model) sees what changed.
        events: list[dict[str, Any]] = []
        for warning in _repair_tool_template_lines(tool):
            events.append({"event": "warning", "data": {"message": warning}})
        events.append(
            {
                "event": "tool_call",
                "data": {
                    "id": secrets.token_urlsafe(8),
                    "name": tool.name,
                    "args": tool.args,
                },
            }
        )
        return events


#: The tools whose ``template_lines`` the parser repairs before they run.
#: Only the page writers: a read-only checker such as ``validate_template``
#: must see exactly what the model wrote, or it reports the mistake fixed.
REPAIRED_TEMPLATE_TOOLS = frozenset({"create_page", "update_page"})


def _repair_tool_template_lines(tool: ParsedToolCall) -> list[str]:
    """Repair template text carried by a page-writing tool call, in place.

    ``create_page`` and ``update_page`` get the conservative
    ``{{filled:...}}`` repairs from :mod:`src.ai.template_validator` on their
    ``template_lines``. Every other tool is untouched — in particular
    ``validate_template`` and ``render_page_preview``, which exist to show
    the model what its text actually does.
    """
    if tool.name not in REPAIRED_TEMPLATE_TOOLS:
        return []
    args = tool.args
    lines = args.get("template_lines")
    if not (isinstance(lines, list) and lines and all(isinstance(line, str) for line in lines)):
        return []
    repaired, found = repair_template_lines(lines)
    if found:
        args["template_lines"] = repaired
    return list(found)


__all__ = [
    "_FenceParser",
    "stream_model",
]
