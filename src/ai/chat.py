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
from collections.abc import AsyncIterator
from typing import Any, Literal

import httpx

from src.devices import DeviceType

from .chat_ops import ToolCallValidationError, parse_tool_call, supported_ops
from .generator import (
    AIGenerationError,
    _resolve_model,
    _resolve_provider,
)
from .prompt_builder import build_prompt
from .protocols import Protocol, get_protocol
from .template_validator import repair_template_lines

# Where the chat is being invoked from. The page editor's inline chat
# wants in-place edits (apply_patch / replace_page); the global drawer
# usually wants navigation (navigate_to_page). The addendum is built
# differently for each so the model picks the right op without guessing.
ChatSurface = Literal["editor", "global"]

logger = logging.getLogger(__name__)


_DEFAULT_TEMPERATURE = 0.7
_DEFAULT_MAX_TOKENS = 2000
_DEFAULT_TIMEOUT_SECONDS = 120.0


# ---------------------------------------------------------------------------
# System-prompt addendum describing the tool grammar.
# ---------------------------------------------------------------------------


# Body of the chat tool-grammar addendum. Split into "head" (everything
# before the navigation creation-bias paragraph) and "tail" (everything
# after) so we can inject a surface-specific bias without f-string
# escaping every JSON example. Both halves are plain literals — they
# must not be passed to ``.format()`` or used as f-strings.


_TOOL_GRAMMAR_BODY_HEAD = """
You may be asked to generate a page, refine the page being edited,
suggest plugin variables, navigate to pages, install/enable/disable/
uninstall plugins, or change settings. To take ACTION, emit a fenced
JSON block with the language tag `fiestaboard`. Each block must contain
exactly one of these operations:

IMPORTANT — TOOL RESULT MESSAGES: When you see a user message starting
with "[Tool result:", it is an automated result from a tool you
previously executed — NOT a new human request. Read the result and
decide whether to take another action or summarise what was
accomplished. Do NOT re-explain what you did; just continue the task.

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
"""


_TOOL_GRAMMAR_BODY_TAIL = """
5. Navigate to the schedule editor (optionally pre-filling a new entry):

   ```fiestaboard
   {"op": "navigate_to_schedule", "args": {
     "prefill": {
       "page_id": "abc123",
       "start_time": "07:00",
       "end_time": "09:00",
       "day_pattern": "weekdays"
     }
   }}
   ```

   Use this after creating or editing a page when the user's intent
   includes scheduling it. `prefill` is optional — omit it to open the
   schedule page without pre-filling. When the user is already on the
   schedule page, this opens the new-entry form in-place without
   navigation. Always explain what will be pre-filled before emitting
   this block.

   `day_pattern`: "all" | "weekdays" | "weekends" | "custom".
   Times are 24h HH:MM. `end_time` may be null for open-ended.
   `page_id` may be a carousel ID (e.g. "carousel:abc123").

PLUGIN MANAGEMENT (always show a confirmation before any plugin action):

6. Install a plugin from the official registry:

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

7. Configure an already-installed plugin:

   ```fiestaboard
   {"op": "update_plugin_config", "args": {
     "plugin_id": "openweather",
     "config": {"api_key": "...", "location": "New York, NY"}
   }}
   ```

   The user will be asked to confirm before changes are applied. Never
   include real or guessed API keys — only include values the user has
   explicitly told you.

8. Update (upgrade) an installed plugin to its latest registry version:

   ```fiestaboard
   {"op": "update_plugin", "args": {
     "plugin_id": "openweather"
   }}
   ```

   Only propose when the user asks to update/upgrade a specific plugin
   or when you can see from context that an update is available. The
   user will be asked to confirm before the update runs.

9. Enable an already-installed but currently-disabled plugin:

   ```fiestaboard
   {"op": "enable_plugin", "args": {
     "plugin_id": "openweather"
   }}
   ```

   Use when the user asks to enable or turn on a plugin that appears as
   "disabled" in INSTALLED PLUGINS. The user will be asked to confirm.

10. Disable an installed plugin without uninstalling it:

   ```fiestaboard
   {"op": "disable_plugin", "args": {
     "plugin_id": "openweather"
   }}
   ```

   Use when the user asks to disable or turn off a plugin while keeping
   it installed. The plugin can be re-enabled later. The user will be
   asked to confirm.

11. Permanently uninstall a plugin:

   ```fiestaboard
   {"op": "uninstall_plugin", "args": {
     "plugin_id": "openweather"
   }}
   ```

   ONLY use when the user explicitly asks to remove or uninstall a
   plugin. This is destructive and cannot be undone. Built-in plugins
   cannot be uninstalled. The user will be asked to confirm.

SETTINGS (non-credential settings only):

9. Change a system setting:

   ```fiestaboard
   {"op": "update_setting", "args": {
     "category": "display",
     "values": {"reduce_motion": true}
   }}
   ```

   Valid categories and their representative keys:
   - "display": display preferences. `reduce_motion` (bool) disables
     animated transitions.
   - "transitions": how pages animate in. `transition_type` (string),
     `duration_ms` (int).
   - "output": where rendered pages are sent. `target` is "ui",
     "board", or "both".
   - "polling": how often plugins refresh their data.
     `interval_seconds` (int).
   - "location": default lat/long used by location-aware plugins.
     `latitude` (float), `longitude` (float).
   - "silence_schedule": a daily "do not disturb" window. `enabled`
     (bool), `start_time`/`end_time` (HH:MM).
   - "active_page": which page is currently displayed.
     `page_id` (string).

   NEVER use this for AI provider settings, MQTT, or board API
   credentials — tell the user to configure those manually in Settings.
   The user will be asked to confirm before changes are applied.

CAROUSELS (playlists of pages that rotate automatically):

10. Create a new carousel:

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

11. Update an existing carousel (rename, reorder pages, change interval):

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

12. Create a new schedule entry:

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

13. Update an existing schedule entry:

    ```fiestaboard
    {"op": "update_schedule", "args": {
      "schedule_id": "sch-abc123",
      "start_time": "08:00",
      "enabled": false
    }}
    ```

    All fields except `schedule_id` are optional. Use IDs from
    AVAILABLE SCHEDULES above. The user will be asked to confirm.

14. Delete a schedule entry:

    ```fiestaboard
    {"op": "delete_schedule", "args": {
      "schedule_id": "sch-abc123"
    }}
    ```

    This is destructive — always explain what will be removed and why
    before emitting this block. The user will be asked to confirm.

SYSTEM:

15. Trigger a FiestaBoard system update:

    ```fiestaboard
    {"op": "trigger_system_update", "args": {}}
    ```

    Only propose this when the user explicitly asks to update FiestaBoard
    or asks you to check for/apply updates. Always explain that the system
    will restart briefly during the update. The user will be asked to
    confirm before it runs.

TASK TRACKING (for multi-step sequences of 3 or more actions):

16. Announce and update a running todo list across sequential steps:

    ```fiestaboard
    {"op": "update_task_list", "args": {
      "tasks": [
        {"id": "1", "label": "Create morning page", "status": "done"},
        {"id": "2", "label": "Schedule 07:00-09:00", "status": "in_progress"},
        {"id": "3", "label": "Schedule 09:00-12:00", "status": "pending"}
      ]
    }}
    ```

    Use this when performing 3 or more sequential steps:
    - Emit at the BEGINNING of your plan with all tasks as "pending"
    - Re-emit BEFORE each step: mark the current task "in_progress", completed
      tasks "done", remaining tasks "pending"
    - Use "failed" if a step fails; leave the rest "pending"
    - Keep `id` values stable across updates (same id = same task)
    - `update_task_list` does NOT count toward the one-block-per-response
      limit — you may emit it in the SAME response as one action block

RULES
- Only emit ops the user actually asked for. If they ask a question or
  want an explanation, just answer in prose — do not emit a tool block.
- Prefer `apply_patch` over `replace_page` when the user is iterating
  on an existing page. `replace_page` is destructive.
- You may emit at most one ACTION tool block per response. `update_task_list`
  is a status-only block and does not count as an action — you may emit it
  in the same response alongside one action block. Put any explanation text
  before or after the block(s).
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


_EDITOR_SURFACE_INTRO = (
    "SURFACE — You are the inline chat panel inside the page editor.\n"
    "The user is actively editing one page; that page (if any) is sent\n"
    "above as `current_page`. Default to in-place edits of THAT page;\n"
    "do not navigate away from it unless the user clearly asks to switch\n"
    "to a different page.\n"
)


_GLOBAL_SURFACE_INTRO = (
    "SURFACE — You are the global chat drawer, accessible from any view\n"
    "in the app. There may be no page in focus. Prefer navigation and\n"
    "configuration actions; only edit a page in-place when `current_page`\n"
    "is present AND the user is clearly iterating on that exact page.\n"
)


_EDITOR_CREATION_BIAS = (
    "   When the user asks to CREATE, MAKE, DESIGN, or BUILD a page from\n"
    "   inside the editor, they almost always mean \"turn the page I'm\n"
    '   editing into that" — use `replace_page` (or `apply_patch` for an\n'
    "   incremental change). Reserve `navigate_to_page` for explicit\n"
    '   requests like "open my weather page" or "start a new page".\n'
)


_GLOBAL_CREATION_BIAS = (
    '   IMPORTANT — "make" bias: when the user asks to CREATE, MAKE,\n'
    "   DESIGN, or BUILD a page, display, layout, or visual, default to\n"
    '   opening the page editor with `"page_id": "new"`. The page\n'
    "   editor is the canvas where users author content; do not write\n"
    "   template content remotely from the global drawer. Example:\n"
    '   "make me a weather page" → navigate_to_page with page_id: "new".\n'
)


def _build_tool_grammar_addendum(surface: ChatSurface) -> str:
    """Render the chat tool-grammar addendum for a specific surface.

    The two surfaces are the inline chat panel inside the page editor
    (``"editor"``) and the global drawer accessible from any view
    (``"global"``). They share the same tool grammar but differ in one
    important way: when the user asks to "make" or "build" something,
    the editor wants in-place edits (``apply_patch`` / ``replace_page``)
    on the page they are currently editing, while the global drawer
    wants to navigate to the page editor first so the user can author
    there. Folding this branch into the prompt — rather than relying on
    the model to infer it from the presence of ``current_page`` —
    reduces wrong-op selections.
    """
    if surface == "editor":
        intro = _EDITOR_SURFACE_INTRO
        bias = _EDITOR_CREATION_BIAS
    else:
        intro = _GLOBAL_SURFACE_INTRO
        bias = _GLOBAL_CREATION_BIAS
    return "\n\nCHAT MODE — TOOL GRAMMAR\n\n" + intro + _TOOL_GRAMMAR_BODY_HEAD + bias + _TOOL_GRAMMAR_BODY_TAIL


# ---------------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------------


async def stream_chat(
    *,
    messages: list[dict[str, str]],
    device_type: DeviceType,
    providers_block: dict[str, Any],
    variables: dict[str, dict[str, dict[str, Any]]] | None = None,
    plugin_demos: list[dict[str, Any]] | None = None,
    current_page: dict[str, Any] | None = None,
    available_pages: list[dict[str, Any]] | None = None,
    installed_plugins: list[dict[str, Any]] | None = None,
    available_schedules: list[dict[str, Any]] | None = None,
    available_carousels: list[dict[str, Any]] | None = None,
    registry_plugins: list[dict[str, Any]] | None = None,
    surface: ChatSurface = "global",
    provider_id: str | None = None,
    model: str | None = None,
    client: httpx.AsyncClient | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
) -> AsyncIterator[dict[str, Any]]:
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
    cleaned: list[dict[str, str]] = []
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
        mode="chat",
    )

    # Compose the message list we'll actually send: extend the
    # system prompt with the tool grammar, then prepend any history
    # before the current-page-context message + final user prompt that
    # ``PromptContext.to_messages`` produces.
    base_messages = list(context.to_messages())
    base_messages[0] = {
        "role": "system",
        "content": (base_messages[0]["content"] + _build_tool_grammar_addendum(surface)),
    }
    if history:
        # Keep history right after the system prompt so the model sees
        # the conversation in order.
        full_messages = [base_messages[0]] + history + base_messages[1:]
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

    last_warning: str | None = None
    usage: dict[str, int | None] = {
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

    def __init__(self) -> None:
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
            tool = parse_tool_call(parsed)
        except ToolCallValidationError as exc:
            return [
                {
                    "event": "warning",
                    "data": {"message": f"Invalid fiestaboard tool block: {exc}"},
                }
            ]

        # Repair common ``{{filled:...}}`` mistakes in any template
        # lines the tool call carries. We mutate the validated args
        # in-place and emit a warning event per repair so the user
        # (and, via the chat transcript, the model on the next turn)
        # sees what was changed.
        events: list[dict[str, Any]] = []
        for warning in _repair_tool_template_lines(tool):
            events.append({"event": "warning", "data": {"message": warning}})
        events.append(
            {
                "event": "tool_call",
                "data": {
                    "id": secrets.token_urlsafe(8),
                    "op": tool.op,
                    "args": tool.args.model_dump(mode="json"),
                },
            }
        )
        return events


def _repair_tool_template_lines(tool: Any) -> list[str]:
    """Repair template lines carried by a validated tool call.

    Supports the two ops that ship template text: ``replace_page``
    (full ``template`` list) and ``apply_patch`` (per-line
    ``replace_line`` / ``insert_line`` edits). Other ops are
    untouched.
    """
    op = getattr(tool, "op", None)
    args = getattr(tool, "args", None)
    if args is None:
        return []
    if op == "replace_page":
        template = getattr(args, "template", None)
        if not isinstance(template, list) or not template:
            return []
        repaired, warnings = repair_template_lines(template)
        if warnings:
            args.template = repaired
        return warnings
    if op == "apply_patch":
        changes = getattr(args, "changes", None) or []
        patch_warnings: list[str] = []
        for change in changes:
            change_type = getattr(change, "type", None)
            if change_type not in ("replace_line", "insert_line"):
                continue
            text = getattr(change, "text", None)
            if not isinstance(text, str):
                continue
            repaired, change_warnings = repair_template_lines([text])
            if change_warnings:
                change.text = repaired[0]
                patch_warnings.extend(change_warnings)
        return patch_warnings
    return []


__all__ = [
    "_FenceParser",
    "stream_chat",
    "supported_ops",
]
