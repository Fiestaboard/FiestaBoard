"""FastAPI router for the ``/pages/ai`` endpoints (the "Gen AI" feature).

Handlers were moved here verbatim from ``src/api_server.py`` (Phase 2 — the
last three untagged, non-deprecated routes in the app). The move is
deliberately behaviour-preserving: the only edits to a handler body are the
ones relocation forces (``@app`` → ``@router``, relative imports re-anchored
from ``src`` to ``src.ai``, and the ``/pages/ai`` prefix moving onto the
router).

**Why a sibling module rather than ``src/ai/routes.py``.** That file is the
``/ai`` router — the chat *operations* execution seam (Task 11), a different
URL prefix with an unrelated docstring. These three share the ``ai`` OpenAPI
tag, so the conventions ratchet sees them as one domain, but they mount under
``/pages/ai`` and carry their own collaborators (the generate throttle, the
prompt-context collectors, the SSE frame writer). One prefix per module keeps
both readable.

**Collaborators.** All four helpers below (``_ai_generate_throttle_check``,
``_format_sse_event``, ``_collect_ai_variables``, ``_collect_plugin_demos``)
were private to these three handlers in ``api_server`` — nothing else in the
codebase referenced them — so they moved wholesale rather than staying behind
a seam. ``get_config_manager`` is imported from its canonical home. This
module imports nothing from ``src.api_server``; ``tests/test_tail_routers_decoupled.py``
asserts that in a fresh interpreter.

**Conventions** (``docs/internal/reference/API_CONVENTIONS.md``). All three
routes declare their errors; the two POSTs take Pydantic request models in
place of the free-form ``await request.json()`` reads they used to do, so a
malformed body is FastAPI's 422 rather than nine hand-rolled ``isinstance``
checks each raising its own 400. The one 400 that survives on
``/generate`` is the *semantic* rejection of a whitespace-only prompt — a
body that already passed schema validation, which the conventions doc says
is a 400 and not a 422.

``POST /chat`` is the exception, and it is a deliberate one:
:class:`fastapi.responses.StreamingResponse` carries ``text/event-stream``,
not a JSON document, so no ``response_model`` can describe what it sends.
Rather than declare one that would be a lie, the route declares the media
type in ``responses[200]``, and :data:`CHAT_STREAM_EVENTS` below names every
event it emits and the model describing that event's ``data`` payload.
``tests/test_ai_pages_contract.py`` validates real frames against that
registry and cross-checks it against the literal ``{"event": ...}`` dicts in
:mod:`src.ai.chat` and :mod:`src.ai.agent`, so the published schema cannot drift
from the wire. The
matching ``response_model`` exception is recorded in
``tests/conventions_manifest.json``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from src.api_errors import errors
from src.config_manager import get_config_manager
from src.pages.models import PageCreate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pages/ai", tags=["ai"])

#: The two board geometries the AI prompt builder knows how to target. Note
#: arrays are deliberately absent: the prompt carries a fixed rows x cols
#: grid and there is no exemplar corpus for a multi-note canvas.
AIDeviceType = Literal["flagship", "note"]

#: Which chat panel is calling — "editor" (inline panel inside the page
#: editor) vs "global" (global drawer). Steers the AI between in-place page
#: edits and navigation. Old clients that omit it get "global".
ChatSurface = Literal["editor", "global"]


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class AIPromptContextResponse(BaseModel):
    """``GET /context`` — everything that would be sent to the model.

    A debug view of :class:`src.ai.prompt_builder.PromptContext`. It never
    carries a credential: the provider block is resolved at generation time,
    not here.
    """

    device_type: AIDeviceType
    rows: int
    cols: int
    user_prompt: str
    variables: dict[str, dict[str, dict[str, Any]]] = Field(default_factory=dict)
    exemplars: list[dict[str, Any]] = Field(default_factory=list)
    current_page: dict[str, Any] | None = None
    system_prompt: str = ""
    #: The chat's generated tool section, when ``include_tools`` was asked
    #: for. Rendered from the MCP server's own tool list, so this is the
    #: place to check what the model is being taught (and how much of the
    #: context window it costs).
    tool_catalog: str | None = None


class AIGenerateRequest(BaseModel):
    """``POST /generate`` — one prompt plus the geometry to draft for.

    ``current_page`` is free-form on purpose: it is the editor's live,
    possibly-unsaved draft, which the user may have left in a state no
    ``PageCreate`` would accept. It is forwarded to the model as context and
    never persisted, so validating it here would reject exactly the
    half-finished pages the feature exists to help finish.
    """

    prompt: str
    device_type: AIDeviceType = "flagship"
    provider_id: str | None = None
    model: str | None = None
    current_page: dict[str, Any] | None = None


class AIGenerateResponse(BaseModel):
    """``POST /generate`` — the draft page and how it was produced.

    ``page`` is a ``PageCreate``-shaped draft, not a stored page: this
    endpoint never writes, and the editor inserts the draft locally until
    the user clicks Save. ``warnings`` are the repairs the generator made to
    the model's output (padded rows, trimmed lines, unknown variables).
    """

    page: PageCreate
    model_used: str
    provider_id: str | None = None
    warnings: list[str] = Field(default_factory=list)
    usage: dict[str, int | None] = Field(default_factory=dict)


class ChatToolCallRecord(BaseModel):
    """A tool call the assistant made, as the client replays it."""

    id: str
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


ToolMessageStatus = Literal["ok", "blocked", "error", "denied", "interrupted", "answered"]


class ChatMessage(BaseModel):
    """One turn of the conversation as the client replays it.

    There is no server-side session: the client sends the whole transcript
    every request, so the transcript has to be able to say what the server
    did. An ``assistant`` turn carries the ``tool_calls`` it made; each
    outcome is a ``tool`` turn keyed by ``tool_call_id``. The server renders
    both into plain text for the model (:mod:`src.ai.transcript`), exactly
    as it rendered its own steps when it made them.
    """

    role: Literal["user", "assistant", "system", "tool"]
    content: str = ""
    tool_calls: list[ChatToolCallRecord] | None = None
    tool_call_id: str | None = None
    name: str | None = None
    status: ToolMessageStatus | None = None
    result: Any = None

    @model_validator(mode="after")
    def _tool_fields_match_role(self) -> ChatMessage:
        if self.role == "tool":
            if not (self.tool_call_id and self.name and self.status):
                raise ValueError("a tool message needs tool_call_id, name and status")
            if self.tool_calls is not None:
                raise ValueError("a tool message cannot carry tool_calls")
        elif self.role != "assistant" and self.tool_calls is not None:
            raise ValueError(f"a {self.role} message cannot carry tool_calls")
        elif self.role != "tool" and (self.tool_call_id or self.status):
            raise ValueError(f"a {self.role} message cannot carry a tool outcome")
        return self


class ChatAnswer(BaseModel):
    """The user's reply to an ``ask_user`` question (MCP elicitation shape)."""

    action: Literal["accept", "decline", "cancel"]
    content: dict[str, Any] | None = None


class ChatResumeDecision(BaseModel):
    """What the client decided about the tool call the last turn paused on.

    ``approve`` / ``deny`` answer a destructive tool's approval pause;
    ``answer`` carries the reply to an ``ask_user`` question. The
    ``tool_call_id`` must be the call the transcript is still waiting on.
    """

    tool_call_id: str
    decision: Literal["approve", "deny", "answer"]
    answer: ChatAnswer | None = None

    @model_validator(mode="after")
    def _answer_only_with_answer_decision(self) -> ChatResumeDecision:
        if self.decision == "answer" and self.answer is None:
            raise ValueError("decision 'answer' needs an answer")
        if self.decision != "answer" and self.answer is not None:
            raise ValueError("only decision 'answer' carries an answer")
        return self


class AIChatRequest(BaseModel):
    """``POST /chat`` — the conversation plus the context blocks.

    Every ``…_pages`` / ``…_plugins`` / ``…_schedules`` / ``…_collections``
    block is a client-supplied snapshot of what the user can see, rendered
    into the system prompt so the model can name real things. They stay
    free-form dicts for the same reason ``current_page`` does: they are
    projections the browser assembles for the prompt, not resources this
    endpoint reads back or stores, and pinning them to the storage models
    would break the drawer every time an unrelated model gained a field.
    """

    messages: list[ChatMessage] = Field(min_length=1)
    resume: ChatResumeDecision | None = None
    device_type: AIDeviceType = "flagship"
    surface: ChatSurface = "global"
    current_page: dict[str, Any] | None = None
    available_pages: list[dict[str, Any]] | None = None
    installed_plugins: list[dict[str, Any]] | None = None
    available_schedules: list[dict[str, Any]] | None = None
    available_collections: list[dict[str, Any]] | None = None
    registry_plugins: list[dict[str, Any]] | None = None
    provider_id: str | None = None
    model: str | None = None


# ---------------------------------------------------------------------------
# The SSE event schema
#
# POST /chat streams; it has no JSON response body and therefore no
# response_model (see the module docstring and the checked-in exception in
# tests/conventions_manifest.json). These models are what stands in for one:
# each names the `data` payload of one `event:` frame, and the registry below
# is cross-checked against src/ai/chat.py by the contract tests so a new
# event type cannot ship undocumented.
# ---------------------------------------------------------------------------


class ChatStreamTextData(BaseModel):
    """``event: text`` — one token-level prose delta."""

    delta: str


class ChatStreamStatusData(BaseModel):
    """``event: status`` — what the loop is doing, for the step timeline."""

    phase: Literal["thinking", "tool_running", "tool_done"]
    message: str
    tool_call_id: str | None = None
    step: int


class ChatStreamToolCallData(BaseModel):
    """``event: tool_call`` — a validated call, emitted BEFORE it runs.

    The annotation flags come from the MCP tool's own ``ToolAnnotations``;
    ``requires_approval`` is what the client keys its pause UI on.
    """

    id: str
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    title: str
    read_only: bool
    destructive: bool
    requires_approval: bool
    source: Literal["mcp", "chat"]


class ChatStreamToolResultData(BaseModel):
    """``event: tool_result`` — what the call did, emitted after it ran."""

    id: str
    name: str
    status: Literal["ok", "blocked", "error", "denied"]
    summary: str
    result: Any = None
    error: str | None = None


class ChatStreamElicitationData(BaseModel):
    """``event: elicitation`` — the assistant is asking the user a question.

    The same field names as an MCP ``elicitation/create`` request, so the
    client renders ``ask_user`` and (later) tool-driven elicitation alike.
    """

    id: str
    name: str
    message: str
    requested_schema: dict[str, Any]
    allow_free_text: bool = True


class ChatStreamMessageData(BaseModel):
    """``event: warning`` / ``event: error`` — one human-readable line.

    A ``warning`` is recoverable and the stream continues; an ``error`` is
    fatal and the stream closes after it.
    """

    message: str


class ChatStreamDoneData(BaseModel):
    """``event: done`` — the terminal frame, always last on a clean stream.

    ``reason`` says why the turn ended: ``complete`` (nothing pending),
    ``awaiting_approval`` (a destructive tool waits on the user — resume
    with approve/deny), ``awaiting_input`` (an ``ask_user`` question waits —
    resume with an answer), or ``step_limit`` (runaway protection).
    """

    model_used: str
    provider_id: str | None = None
    usage: dict[str, int | None] = Field(default_factory=dict)
    reason: Literal["complete", "awaiting_approval", "awaiting_input", "step_limit"]
    pending_tool_call_id: str | None = None
    steps: int


#: Every event name ``POST /chat`` emits, mapped to the model describing that
#: event's ``data`` payload. This is the published contract that the missing
#: ``response_model`` would otherwise carry, and it is what
#: ``web/src/lib/api-stream.ts`` switches on.
CHAT_STREAM_EVENTS: dict[str, type[BaseModel]] = {
    "text": ChatStreamTextData,
    "status": ChatStreamStatusData,
    "tool_call": ChatStreamToolCallData,
    "tool_result": ChatStreamToolResultData,
    "elicitation": ChatStreamElicitationData,
    "warning": ChatStreamMessageData,
    "error": ChatStreamMessageData,
    "done": ChatStreamDoneData,
}

#: Rendered into the OpenAPI schema for the 200 on ``POST /chat``, where a
#: response_model would normally go.
_CHAT_STREAM_DESCRIPTION = (
    "A Server-Sent Events stream. Each frame is `event: <name>` and "
    "`data: <json>` on their own lines, terminated by a blank line. The "
    "event names are "
    + ", ".join(f"`{name}`" for name in CHAT_STREAM_EVENTS)
    + "; their payloads are described by the ChatStream*Data models in "
    "src/ai/page_routes.py. A clean stream ends with `done`; a fatal one "
    "ends with `error`."
)

# Per-process throttle for /pages/ai/generate. The cap is intentionally
# low because each call costs the user money (BYO-LLM) and a stuck UI
# can otherwise loop. Two concurrent generations across the whole
# instance is plenty for interactive use.
_AI_GENERATE_SEMAPHORE = asyncio.Semaphore(2)
_AI_GENERATE_MIN_INTERVAL_SECONDS = 1.0
_ai_generate_last_call: float = 0.0
_ai_generate_lock = threading.Lock()


def _ai_generate_throttle_check() -> None:
    """Reject a call if it lands less than the min interval after the last.

    Cheap defence against runaway clients without adding a dependency.
    """
    global _ai_generate_last_call
    now = time.monotonic()
    with _ai_generate_lock:
        wait = (_ai_generate_last_call + _AI_GENERATE_MIN_INTERVAL_SECONDS) - now
        if wait > 0:
            raise HTTPException(
                status_code=429,
                detail=("AI generation is rate-limited. Please wait a moment and try again."),
            )
        _ai_generate_last_call = now


@router.get(
    "/context",
    response_model=AIPromptContextResponse,
    responses=errors(422),
    summary="Inspect the prompt context the model would receive",
)
async def get_ai_context(
    device_type: Annotated[AIDeviceType, Query(description="Board geometry to build the prompt for.")] = "flagship",
    include_tools: Annotated[
        bool, Query(description="Also render the chat's tool catalog (imports the MCP server).")
    ] = False,
) -> AIPromptContextResponse:
    """Return the variable list + exemplars that would be sent to the model.

    Useful for debugging the prompt; never includes API keys. An unknown
    ``device_type`` is FastAPI's 422 — the parameter is a Literal, so the
    rejection is schema validation rather than a hand-rolled membership test.
    ``include_tools`` adds the generated tool section the chat appends.
    """
    from .prompt_builder import build_prompt

    variables = _collect_ai_variables()
    demos = _collect_plugin_demos()

    context = build_prompt(
        user_prompt="(no prompt — debug context only)",
        device_type=device_type,
        variables=variables,
        plugin_demos=demos,
    )
    payload = context.to_dict()
    if include_tools:
        from .chat_tools import ChatExtensionBackend
        from .mcp_bridge import CompositeToolBackend, McpToolBackend
        from .tool_catalog import ToolCatalog

        descriptors = await CompositeToolBackend(McpToolBackend(), ChatExtensionBackend()).list_tools()
        payload["tool_catalog"] = ToolCatalog(descriptors).render_addendum("global")
    return AIPromptContextResponse(**payload)


@router.post(
    "/generate",
    response_model=AIGenerateResponse,
    responses=errors(400, 422, 429, 500),
    summary="Draft a template page with the user's configured LLM",
)
async def generate_ai_page(request: AIGenerateRequest) -> AIGenerateResponse:
    """Ask the user's configured LLM for a draft template page.

    Does **not** persist anything: the editor inserts the returned page
    locally and the user must click Save to keep it.

    - a second call inside the minimum interval → **429**
    - a whitespace-only prompt → **400** (a semantic rejection of a body
      that already passed schema validation)
    - AI disabled, no provider configured, or model output the generator
      could not repair → **400** carrying the generator's own message
    - anything unanticipated → **500** with the detail kept out of the body
    """
    _ai_generate_throttle_check()

    prompt = request.prompt
    device_type = request.device_type
    provider_id = request.provider_id
    model = request.model
    current_page = request.current_page

    if not prompt.strip():
        raise HTTPException(status_code=400, detail="`prompt` is required.")

    cm = get_config_manager()
    providers_block = cm.get_ai_providers()
    variables = _collect_ai_variables()
    demos = _collect_plugin_demos()

    from .generator import AIGenerationError, _user_safe_error_message
    from .generator import generate_page as ai_generate_page

    try:
        async with _AI_GENERATE_SEMAPHORE:
            result = await ai_generate_page(
                user_prompt=prompt,
                device_type=device_type,
                providers_block=providers_block,
                variables=variables,
                plugin_demos=demos,
                current_page=current_page,
                provider_id=provider_id,
                model=model,
            )
    except AIGenerationError as exc:
        # Predictable, user-visible failures: 400 with the message in
        # the body so the UI can render it as a warning.  Funnel the message
        # through a sanitizer so static analysis (py/stack-trace-exposure)
        # sees a constant-character flow, not raw exception data.
        raise HTTPException(status_code=400, detail=_user_safe_error_message(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected error in /pages/ai/generate")
        raise HTTPException(
            status_code=500,
            detail=("Unexpected AI generation error. See server logs for details."),
        ) from None

    return AIGenerateResponse.model_validate(result)


@router.post(
    "/chat",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": _CHAT_STREAM_DESCRIPTION,
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        },
        **errors(400, 422),
    },
    summary="Stream a multi-turn AI chat as Server-Sent Events",
)
async def chat_ai_page(request: AIChatRequest) -> StreamingResponse:
    """Run one turn of the AI chat and stream it as Server-Sent Events.

    A turn may span several model calls and tool executions
    (:mod:`src.ai.agent`); every tool runs through the in-process MCP
    server, so the chat and external MCP clients share one implementation.
    The route has no ``response_model`` — :data:`CHAT_STREAM_EVENTS` is the
    published schema, and the matching exception is checked in to
    ``tests/conventions_manifest.json``. Event types:

    - ``text``        — token-level prose deltas
    - ``status``      — loop progress (thinking / running a tool)
    - ``tool_call``   — a validated call, before it runs
    - ``tool_result`` — the outcome, after it ran
    - ``elicitation`` — the assistant asked the user a question
    - ``warning``     — recoverable issue (e.g. malformed tool block)
    - ``error``       — fatal issue, stream is about to close
    - ``done``        — terminal frame: usage, model, and why the turn ended

    A failure that happens *before* the stream opens is a normal JSON error
    response (422 for a malformed body, 400 for a well-formed transcript
    that makes no sense — a ``resume`` naming no pending call, or a
    transcript ending on the assistant's turn); once the 200 and its
    headers are on the wire the only way to report a failure is an
    ``error`` frame.

    Note: we deliberately skip the per-second throttle here. Chat is
    conversational — the user may send several messages back-to-back —
    and a 429 mid-conversation is jarring. The provider semaphore is passed
    into the loop instead, which holds it only around each model call.
    """
    from .transcript import pending_tool_call

    messages = [message.model_dump(exclude_none=True) for message in request.messages]
    pending = pending_tool_call(messages)
    if request.resume is not None:
        if pending is None or pending["id"] != request.resume.tool_call_id:
            raise HTTPException(
                status_code=400,
                detail=f"No tool call {request.resume.tool_call_id!r} is awaiting a decision.",
            )
    else:
        last = messages[-1]
        if last["role"] not in ("user", "tool"):
            raise HTTPException(
                status_code=400,
                detail="Conversation must end with a user message, a tool result, or a resume decision.",
            )
        if last["role"] == "user" and not (last.get("content") or "").strip():
            raise HTTPException(status_code=400, detail="User message is empty.")
        if pending is not None and last["role"] == "user":
            raise HTTPException(
                status_code=400,
                detail=f"Tool call {pending['id']!r} is still awaiting a decision; send a resume with the message.",
            )

    resume = request.resume.model_dump() if request.resume is not None else None
    cm = get_config_manager()
    providers_block = cm.get_ai_providers()
    variables = _collect_ai_variables()
    demos = _collect_plugin_demos()

    # Imported here, not at module scope: ``agent`` pulls in the MCP bridge,
    # and the ``mcp`` package must stay out of the boot path
    # (tests/test_mcp_lazy_mount.py). The first chat turn pays the import.
    from .agent import run_chat_turn
    from .chat_tools import ChatExtensionBackend
    from .mcp_bridge import CompositeToolBackend, McpToolBackend

    backend = CompositeToolBackend(McpToolBackend(), ChatExtensionBackend())

    async def event_source():
        """Render the normalized event stream as SSE bytes."""
        try:
            async for evt in run_chat_turn(
                messages=messages,
                resume=resume,
                device_type=request.device_type,
                surface=request.surface,
                providers_block=providers_block,
                backend=backend,
                variables=variables,
                plugin_demos=demos,
                current_page=request.current_page,
                available_pages=request.available_pages,
                installed_plugins=request.installed_plugins,
                available_schedules=request.available_schedules,
                available_collections=request.available_collections,
                registry_plugins=request.registry_plugins,
                provider_id=request.provider_id,
                model=request.model,
                provider_gate=_AI_GENERATE_SEMAPHORE,
            ):
                yield _format_sse_event(evt["event"], evt["data"])
        except Exception:
            logger.exception("Unexpected error in /pages/ai/chat")
            yield _format_sse_event(
                "error",
                {"message": ("Unexpected AI chat error. See server logs for details.")},
            )

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",  # disable nginx buffering for SSE
            "Connection": "keep-alive",
        },
    )


def _format_sse_event(event: str, data: dict[str, Any]) -> bytes:
    """Serialize a single Server-Sent Event frame.

    SSE requires ``event:``/``data:`` on separate lines and a blank
    line as the frame terminator. JSON-encode ``data`` so multi-line
    strings don't break the framing.
    """
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n".encode()


def _collect_ai_variables() -> dict[str, dict[str, dict[str, Any]]]:
    """Variable registry to pass to the AI prompt builder.

    Mirrors what ``GET /templates/variables`` exposes so the model and
    the UI's variable picker stay in sync.
    """
    try:
        from src.plugins import get_plugin_registry as _get_registry
    except ImportError:
        return {}
    try:
        registry = _get_registry()
        return registry.get_all_variables_with_metadata()
    except Exception as exc:
        logger.warning("Could not collect AI variables: %s", exc)
        return {}


def _collect_plugin_demos() -> list[dict[str, Any]]:
    """Return plugin-supplied demo pages (from each manifest's ``demo`` block).

    Used as exemplars in the prompt. Only demos for *enabled* plugins are
    included so the model doesn't suggest variables the user can't use.
    """
    try:
        from src.plugins import get_plugin_registry as _get_registry
    except ImportError:
        return []
    demos: list[dict[str, Any]] = []
    try:
        registry = _get_registry()
        manifests = getattr(registry, "_manifests", {})
        enabled = getattr(registry, "_enabled", {})
        for plugin_id, manifest in manifests.items():
            if not enabled.get(plugin_id, False):
                continue
            demo = getattr(manifest, "demo", None)
            if demo is None:
                continue
            demos.append(
                {
                    "name": getattr(demo, "name", plugin_id),
                    "device_type": getattr(demo, "device_type", "flagship"),
                    "template": list(getattr(demo, "template", []) or []),
                    "line_metadata": list(getattr(demo, "line_metadata", []) or []),
                    "duration_seconds": getattr(demo, "duration_seconds", 300),
                }
            )
    except Exception as exc:
        logger.warning("Could not collect plugin demos: %s", exc)
    return demos
