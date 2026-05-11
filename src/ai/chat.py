"""Streaming AI chat for the page editor.

Drives ``POST /pages/ai/chat``. Provides multi-turn, streaming
conversations on top of the same provider plumbing used by
:mod:`src.ai.generator`.

The output is a normalized event stream — independent of which provider
is upstream — that the API layer serializes as Server-Sent Events:

    event: text       data: {"delta": "..."}
    event: tool_call  data: {"id": "...", "op": "...", "args": {...}}
    event: warning    data: {"message": "..."}
    event: error      data: {"message": "..."}
    event: done       data: {"usage": {...}, "model_used": "..."}

Tool calls are emitted by the model as triple-backtick ``fiestaboard``
fenced JSON blocks. We keep a small streaming state machine that buffers
fence content as text deltas arrive, and on the closing fence parses
+ validates the JSON via :mod:`src.ai.chat_ops`.

Validation failures yield a ``warning`` event but do **not** abort the
stream — the model often follows a bad block with corrective prose.
"""

from __future__ import annotations

import json
import logging
import re
import secrets
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from ..devices import DeviceType
from .chat_ops import ToolCallValidationError, parse_tool_call, supported_ops
from .generator import (
    AIGenerationError,
    _resolve_model,
    _resolve_provider,
)
from .prompt_builder import build_prompt
from .protocols import Protocol, get_protocol

logger = logging.getLogger(__name__)


_DEFAULT_TEMPERATURE = 0.7
_DEFAULT_MAX_TOKENS = 2000
_DEFAULT_TIMEOUT_SECONDS = 120.0


# ---------------------------------------------------------------------------
# System-prompt addendum describing the tool grammar.
# ---------------------------------------------------------------------------


_TOOL_GRAMMAR_ADDENDUM = """

CHAT MODE — TOOL GRAMMAR

You are now in an interactive chat with the user. They may ask you to
generate a page, refine the page they're currently editing, suggest
plugin variables, navigate to pages, install plugins, or change settings.

To take ACTION, emit a fenced JSON block with the language tag
`fiestaboard`. Each block must contain exactly one of these operations:

PAGE EDITING (use when in the page editor context):

1. Replace the entire page (use when the user asks for a brand-new page
   or a full rewrite):

   ```fiestaboard
   {"op": "replace_page", "args": {
     "name": "...",
     "template": ["...", "..."],
     "line_metadata": [{"alignment": "left", "wrap": false}],
     "duration_seconds": 300
   }}
   ```

2. Apply targeted edits to the page the user is currently editing:

   ```fiestaboard
   {"op": "apply_patch", "args": {
     "rename": "Optional new name",
     "changes": [
       {"type": "replace_line", "index": 0, "text": "NEW LINE",
        "alignment": "center", "wrap": false},
       {"type": "insert_line", "index": 1, "text": "INSERTED"},
       {"type": "delete_line", "index": 4},
       {"type": "update_line_metadata", "index": 2, "alignment": "right"}
     ]
   }}
   ```

   `index` is zero-based. `insert_line` shifts later lines down;
   `delete_line` shifts later lines up. `alignment`/`wrap` are optional
   on replace/insert and only update what you supply on
   update_line_metadata.

3. Suggest plugin variables to the user (no edit applied):

   ```fiestaboard
   {"op": "suggest_variables", "args": {
     "suggestions": [
       {"ref": "weather.temperature", "description": "Current temp in F",
        "example": "72"}
     ]
   }}
   ```

NAVIGATION (use when the user wants to edit or create a specific page):

4. Navigate to a page in the editor:

   ```fiestaboard
   {"op": "navigate_to_page", "args": {
     "page_id": "abc123"
   }}
   ```

   Use `"page_id": "new"` to open a blank new page. Only emit this when
   the user explicitly asks to edit or create a page.

   IMPORTANT — "make" bias: when the user asks to CREATE, MAKE, DESIGN,
   or BUILD any page, display, layout, or visual — default to opening the
   page editor with `"page_id": "new"`. The page editor is the canvas
   where users author content. Do NOT attempt to write template content
   remotely from the global panel; instead open the editor and offer to
   help there. Example: "make me a weather page" → navigate_to_page new.

PLUGIN MANAGEMENT (always show a confirmation before installing):

5. Install a plugin from the official registry:

   ```fiestaboard
   {"op": "install_plugin", "args": {
     "plugin_id": "openweather",
     "source": "registry",
     "auto_enable": true
   }}
   ```

   Only propose plugins listed in PLUGIN REGISTRY above. Use the exact
   `id` from that list as `plugin_id`. Always explain in prose what the
   plugin does and why you are proposing it before emitting this block.
   The user will be asked to confirm before installation happens.

6. Configure an already-installed plugin:

   ```fiestaboard
   {"op": "update_plugin_config", "args": {
     "plugin_id": "openweather",
     "config": {"api_key": "...", "location": "New York, NY"}
   }}
   ```

   The user will be asked to confirm before changes are applied. Never
   include real or guessed API keys — only include values the user has
   explicitly told you.

7. Update (upgrade) an installed plugin to its latest registry version:

   ```fiestaboard
   {"op": "update_plugin", "args": {
     "plugin_id": "openweather"
   }}
   ```

   Only propose when the user asks to update/upgrade a specific plugin
   or when you can see from context that an update is available. The
   user will be asked to confirm before the update runs.

SETTINGS (non-credential settings only):

8. Change a system setting:

   ```fiestaboard
   {"op": "update_setting", "args": {
     "category": "display",
     "values": {"reduce_motion": true}
   }}
   ```

   Valid categories and their representative keys:
   - "display": reduce_motion (bool)
   - "transitions": transition_type (string), duration_ms (int)
   - "output": target ("ui"|"board"|"both")
   - "polling": interval_seconds (int)
   - "location": latitude (float), longitude (float)
   - "silence_schedule": enabled (bool), start_time (HH:MM), end_time (HH:MM)
   - "active_page": page_id (string)

   NEVER use this for AI provider settings, MQTT, or board API
   credentials — tell the user to configure those manually in Settings.
   The user will be asked to confirm before changes are applied.

CAROUSELS (playlists of pages that rotate automatically):

9. Create a new carousel:

   ```fiestaboard
   {"op": "create_carousel", "args": {
     "name": "Morning Rotation",
     "page_ids": ["abc123", "def456"],
     "interval_seconds": 30
   }}
   ```

   `page_ids` is the ordered list of page IDs to rotate through.
   `interval_seconds` (5–3600) controls how long each page shows.
   The user will be asked to confirm before creation.

10. Update an existing carousel (rename, reorder pages, change interval):

    ```fiestaboard
    {"op": "update_carousel", "args": {
      "carousel_id": "carousel:abc123",
      "page_ids": ["def456", "abc123"],
      "interval_seconds": 45
    }}
    ```

    All fields except `carousel_id` are optional — only include what
    should change. Use the carousel IDs from AVAILABLE CAROUSELS above.
    The user will be asked to confirm before changes are applied.

SCHEDULE (control which page/carousel shows at what time):

11. Create a new schedule entry:

    ```fiestaboard
    {"op": "create_schedule", "args": {
      "page_id": "abc123",
      "start_time": "07:00",
      "end_time": "09:00",
      "day_pattern": "weekdays"
    }}
    ```

    Times are 24h HH:MM. `end_time` may be null for open-ended (runs
    until replaced by another schedule or midnight).
    `day_pattern`: "all" | "weekdays" | "weekends" | "custom".
    When "custom", include `custom_days`: ["monday", "wednesday", ...].
    `page_id` may be a carousel ID (e.g. "carousel:abc123") to rotate
    a playlist at that time.
    The user will be asked to confirm.

12. Update an existing schedule entry:

    ```fiestaboard
    {"op": "update_schedule", "args": {
      "schedule_id": "sch-abc123",
      "start_time": "08:00",
      "enabled": false
    }}
    ```

    All fields except `schedule_id` are optional. Use IDs from
    AVAILABLE SCHEDULES above. The user will be asked to confirm.

13. Delete a schedule entry:

    ```fiestaboard
    {"op": "delete_schedule", "args": {
      "schedule_id": "sch-abc123"
    }}
    ```

    This is destructive — always explain what will be removed and why
    before emitting this block. The user will be asked to confirm.

SYSTEM:

14. Trigger a FiestaBoard system update:

    ```fiestaboard
    {"op": "trigger_system_update", "args": {}}
    ```

    Only propose this when the user explicitly asks to update FiestaBoard
    or asks you to check for/apply updates. Always explain that the system
    will restart briefly during the update. The user will be asked to
    confirm before it runs.

RULES
- Only emit ops the user actually asked for. If they ask a question or
  want an explanation, just answer in prose — do not emit a tool block.
- Prefer `apply_patch` over `replace_page` when the user is iterating
  on an existing page. `replace_page` is destructive.
- You may emit at most one tool block per response. Put any explanation
  text before or after the block.
- If you emit a tool block, it must be valid JSON parseable on its own.
  Do not put comments inside the block.
- Always explain what you are about to do before emitting any block that
  requires confirmation. The user must understand the change before
  confirming.
- For destructive ops (delete_schedule), be especially clear about what
  will be permanently removed.
- Stick to the same character-set, layout, and variable rules described
  above.
"""


# ---------------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------------


async def stream_chat(
    *,
    messages: List[Dict[str, str]],
    device_type: DeviceType,
    providers_block: Dict[str, Any],
    variables: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None,
    plugin_demos: Optional[List[Dict[str, Any]]] = None,
    current_page: Optional[Dict[str, Any]] = None,
    available_pages: Optional[List[Dict[str, Any]]] = None,
    installed_plugins: Optional[List[Dict[str, Any]]] = None,
    available_schedules: Optional[List[Dict[str, Any]]] = None,
    available_carousels: Optional[List[Dict[str, Any]]] = None,
    registry_plugins: Optional[List[Dict[str, Any]]] = None,
    provider_id: Optional[str] = None,
    model: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
) -> AsyncIterator[Dict[str, Any]]:
    """Stream a chat completion from the user's configured LLM.

    Yields normalized events (see module docstring). Always yields a
    final ``done`` or ``error`` event so the API layer can close the SSE
    stream cleanly.
    """
    if not messages:
        yield {"event": "error", "data": {"message": "No messages provided."}}
        return

    # Validate message shape early — we can't recover from bad inputs
    # later in the stream.
    cleaned: List[Dict[str, str]] = []
    for msg in messages:
        if not isinstance(msg, dict):
            yield {
                "event": "error",
                "data": {"message": "Each message must be an object."},
            }
            return
        role = msg.get("role")
        content = msg.get("content", "")
        if role not in ("user", "assistant", "system"):
            yield {
                "event": "error",
                "data": {"message": f"Invalid message role: {role!r}"},
            }
            return
        if not isinstance(content, str):
            yield {
                "event": "error",
                "data": {"message": "Message content must be a string."},
            }
            return
        cleaned.append({"role": role, "content": content})

    # The final message must be from the user — that's the prompt the
    # model is being asked to respond to. Earlier messages become
    # conversation history.
    if cleaned[-1]["role"] != "user":
        yield {
            "event": "error",
            "data": {"message": "Conversation must end with a user message."},
        }
        return

    history = cleaned[:-1]
    user_prompt = cleaned[-1]["content"].strip()
    if not user_prompt:
        yield {
            "event": "error",
            "data": {"message": "User message is empty."},
        }
        return

    try:
        provider = _resolve_provider(providers_block, provider_id)
        chosen_model = _resolve_model(provider, model)
    except AIGenerationError as exc:
        yield {"event": "error", "data": {"message": str(exc)}}
        return

    protocol = get_protocol(provider.get("protocol"))

    context = build_prompt(
        user_prompt=user_prompt,
        device_type=device_type,
        variables=variables,
        plugin_demos=plugin_demos,
        current_page=current_page,
        available_pages=available_pages,
        installed_plugins=installed_plugins,
        available_schedules=available_schedules,
        available_carousels=available_carousels,
        registry_plugins=registry_plugins,
    )

    # Compose the message list we'll actually send: extend the
    # system prompt with the tool grammar, then prepend any history
    # before the current-page-context message + final user prompt that
    # ``PromptContext.to_messages`` produces.
    base_messages = list(context.to_messages())
    base_messages[0] = {
        "role": "system",
        "content": base_messages[0]["content"] + _TOOL_GRAMMAR_ADDENDUM,
    }
    if history:
        # Keep history right after the system prompt so the model sees
        # the conversation in order.
        full_messages = (
            [base_messages[0]] + history + base_messages[1:]
        )
    else:
        full_messages = base_messages

    payload = protocol.build_body(
        chosen_model,
        full_messages,
        _DEFAULT_TEMPERATURE,
        _DEFAULT_MAX_TOKENS,
    )
    # Streaming flag — both adapters honor it (Anthropic Messages API
    # accepts ``stream: true``; OpenAI-compatible too).
    payload["stream"] = True
    # The legacy generator forces ``response_format: json_object`` for
    # OpenAI; that breaks chat (we want prose around the tool block).
    payload.pop("response_format", None)

    fence_parser = _FenceParser()

    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=timeout_seconds)

    last_warning: Optional[str] = None
    usage: Dict[str, Optional[int]] = {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
    }

    try:
        url = f"{(provider.get('base_url') or '').rstrip('/')}{protocol.request_path}"
        if not provider.get("base_url"):
            yield {
                "event": "error",
                "data": {"message": "AI provider has no base_url configured."},
            }
            return
        extra = provider.get("headers") or {}
        headers = protocol.build_headers(
            provider.get("api_key") or "",
            extra if isinstance(extra, dict) else {},
        )

        try:
            async with client.stream(
                "POST", url, headers=headers, json=payload
            ) as response:
                if response.status_code >= 400:
                    err_msg = await _extract_error_message(response, protocol)
                    yield {
                        "event": "error",
                        "data": {
                            "message": (
                                f"AI provider returned {response.status_code}: "
                                f"{err_msg}"
                            )
                        },
                    }
                    return

                async for delta_event in _iter_provider_stream(
                    response, protocol, usage
                ):
                    if delta_event["kind"] == "text":
                        text = delta_event["text"]
                        for emit in fence_parser.feed(text):
                            yield emit
                    elif delta_event["kind"] == "warning":
                        last_warning = delta_event["message"]

                # Stream closed — flush any remaining unfenced text and
                # validate any open fence.
                for emit in fence_parser.flush():
                    yield emit
        except httpx.HTTPError as exc:
            logger.warning("AI chat HTTP error: %s", exc)
            yield {
                "event": "error",
                "data": {"message": "Could not reach AI provider."},
            }
            return

        if last_warning:
            yield {"event": "warning", "data": {"message": last_warning}}

        yield {
            "event": "done",
            "data": {
                "model_used": chosen_model,
                "provider_id": provider.get("id"),
                "usage": usage,
            },
        }
    finally:
        if owns_client:
            await client.aclose()


# ---------------------------------------------------------------------------
# Provider stream parser — normalizes upstream SSE chunks into text deltas.
# ---------------------------------------------------------------------------


async def _extract_error_message(
    response: httpx.Response, protocol: Protocol
) -> str:
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
    usage: Dict[str, Optional[int]],
) -> AsyncIterator[Dict[str, Any]]:
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


def _openai_delta_text(event: Dict[str, Any]) -> str:
    choices = event.get("choices") or []
    if not choices:
        return ""
    delta = choices[0].get("delta") or {}
    content = delta.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") in (None, "text"):
                text = part.get("text", "")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def _absorb_openai_usage(
    event: Dict[str, Any], usage: Dict[str, Optional[int]]
) -> None:
    u = event.get("usage")
    if isinstance(u, dict):
        if isinstance(u.get("prompt_tokens"), int):
            usage["prompt_tokens"] = u["prompt_tokens"]
        if isinstance(u.get("completion_tokens"), int):
            usage["completion_tokens"] = u["completion_tokens"]
        if isinstance(u.get("total_tokens"), int):
            usage["total_tokens"] = u["total_tokens"]


def _anthropic_delta_text(event: Dict[str, Any]) -> str:
    if event.get("type") == "content_block_delta":
        delta = event.get("delta") or {}
        if delta.get("type") == "text_delta":
            text = delta.get("text", "")
            if isinstance(text, str):
                return text
    return ""


def _absorb_anthropic_usage(
    event: Dict[str, Any], usage: Dict[str, Optional[int]]
) -> None:
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

    def __init__(self) -> None:
        self._buffer: str = ""
        self._in_fence: bool = False
        self._fence_buffer: str = ""

    def feed(self, chunk: str) -> List[Dict[str, Any]]:
        """Feed a text delta; return zero or more events to emit.

        While outside a fence we emit text deltas as soon as we know they
        can't be part of an opening fence marker. Inside a fence we
        accumulate silently until the closing triple-backtick, then
        validate and emit either a ``tool_call`` or a ``warning``.
        """
        events: List[Dict[str, Any]] = []
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
                self._buffer = self._buffer[close.end():]
                events.append(self._finalize_fence())
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
                        events.append(
                            {"event": "text", "data": {"delta": self._buffer}}
                        )
                    self._buffer = ""
                return events

            # Emit any prose before the fence.
            prose = self._buffer[: m.start()]
            if prose:
                events.append({"event": "text", "data": {"delta": prose}})
            # Skip past the fence open marker; allow optional trailing
            # newline before the body starts.
            after = self._buffer[m.end():]
            if after.startswith("\r\n"):
                after = after[2:]
            elif after.startswith("\n"):
                after = after[1:]
            self._buffer = after
            self._in_fence = True
            self._fence_buffer = ""

    def flush(self) -> List[Dict[str, Any]]:
        """Drain any remaining buffered text after the stream closes."""
        events: List[Dict[str, Any]] = []
        if self._in_fence:
            # Unterminated fence — surface as a warning rather than
            # losing the content silently.
            events.append(
                {
                    "event": "warning",
                    "data": {
                        "message": (
                            "Model emitted an unterminated `fiestaboard` "
                            "fence; ignored."
                        )
                    },
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

    def _finalize_fence(self) -> Dict[str, Any]:
        body = self._fence_buffer.strip()
        if not body:
            return {
                "event": "warning",
                "data": {"message": "Empty fiestaboard tool block; ignored."},
            }
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            return {
                "event": "warning",
                "data": {
                    "message": (
                        f"Could not parse fiestaboard tool block: {exc.msg}"
                    )
                },
            }
        try:
            tool = parse_tool_call(parsed)
        except ToolCallValidationError as exc:
            return {
                "event": "warning",
                "data": {
                    "message": f"Invalid fiestaboard tool block: {exc}"
                },
            }
        return {
            "event": "tool_call",
            "data": {
                "id": secrets.token_urlsafe(8),
                "op": tool.op,
                "args": tool.args.model_dump(mode="json"),
            },
        }


__all__ = [
    "stream_chat",
    "supported_ops",
    "_FenceParser",
]
