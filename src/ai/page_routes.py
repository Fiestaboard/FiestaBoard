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
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from src.config_manager import get_config_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pages/ai")

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


@router.get("/context")
async def get_ai_context(device_type: str = "flagship"):
    """Return the variable list + exemplars that would be sent to the model.

    Useful for debugging the prompt; never includes API keys.
    """
    if device_type not in ("flagship", "note"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid device_type: {device_type!r}",
        )

    from .prompt_builder import build_prompt

    variables = _collect_ai_variables()
    demos = _collect_plugin_demos()

    context = build_prompt(
        user_prompt="(no prompt — debug context only)",
        device_type=device_type,  # type: ignore[arg-type]
        variables=variables,
        plugin_demos=demos,
    )
    return context.to_dict()


@router.post("/generate")
async def generate_ai_page(request: Request):
    """Ask the user's configured LLM for a draft template page.

    Body: ``{prompt, device_type, provider_id?, model?, current_page?}``.
    Returns ``{page, model_used, provider_id, warnings, usage}``.

    Does **not** persist anything: the editor inserts the returned page
    locally and the user must click Save to keep it.
    """
    _ai_generate_throttle_check()

    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object.")

    prompt = body.get("prompt")
    device_type = body.get("device_type", "flagship")
    provider_id = body.get("provider_id")
    model = body.get("model")
    current_page = body.get("current_page")

    if not isinstance(prompt, str) or not prompt.strip():
        raise HTTPException(status_code=400, detail="`prompt` is required.")
    if device_type not in ("flagship", "note"):
        raise HTTPException(status_code=400, detail=f"Invalid device_type: {device_type!r}")
    if current_page is not None and not isinstance(current_page, dict):
        raise HTTPException(status_code=400, detail="`current_page` must be an object.")

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

    return result


@router.post("/chat")
async def chat_ai_page(request: Request):
    """Stream a multi-turn AI chat for refining/building a page.

    Body: ``{messages: [{role, content}], device_type, current_page?,
    provider_id?, model?}``.

    Returns a Server-Sent Events stream. Event types match what
    :func:`src.ai.chat.stream_chat` yields:

    - ``text``      — token-level prose deltas
    - ``tool_call`` — a validated structured operation
                       (see :mod:`src.ai.chat_ops`)
    - ``warning``   — recoverable issue (e.g. malformed tool block)
    - ``error``     — fatal issue, stream is about to close
    - ``done``      — terminal frame with usage + model_used

    Like ``/pages/ai/generate``, this never persists anything: the
    editor applies tool calls locally and the user must click Save.

    Note: we deliberately skip the per-second throttle here. Chat is
    conversational — the user may send several messages back-to-back
    (especially when iterating on a design), and a 429 mid-conversation
    is jarring. The semaphore below caps concurrent streams instead,
    which is the real protection against runaway clients.
    """

    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object.")

    messages = body.get("messages")
    device_type = body.get("device_type", "flagship")
    provider_id = body.get("provider_id")
    model = body.get("model")
    current_page = body.get("current_page")
    available_pages = body.get("available_pages")
    installed_plugins = body.get("installed_plugins")
    available_schedules = body.get("available_schedules")
    available_collections = body.get("available_collections")
    registry_plugins = body.get("registry_plugins")
    # Which chat panel is calling us — "editor" (inline panel inside the
    # page editor) vs "global" (global drawer). Steers the AI's choice
    # between in-place page edits and navigation. Defaults to "global"
    # for old clients that don't send it.
    surface = body.get("surface", "global")
    if surface not in ("editor", "global"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid surface: {surface!r} (expected 'editor' or 'global').",
        )

    if not isinstance(messages, list) or not messages:
        raise HTTPException(status_code=400, detail="`messages` must be a non-empty array.")
    if device_type not in ("flagship", "note"):
        raise HTTPException(status_code=400, detail=f"Invalid device_type: {device_type!r}")
    if current_page is not None and not isinstance(current_page, dict):
        raise HTTPException(status_code=400, detail="`current_page` must be an object.")
    if available_pages is not None and not isinstance(available_pages, list):
        raise HTTPException(status_code=400, detail="`available_pages` must be an array.")
    if installed_plugins is not None and not isinstance(installed_plugins, list):
        raise HTTPException(status_code=400, detail="`installed_plugins` must be an array.")
    if available_schedules is not None and not isinstance(available_schedules, list):
        raise HTTPException(status_code=400, detail="`available_schedules` must be an array.")
    if available_collections is not None and not isinstance(available_collections, list):
        raise HTTPException(status_code=400, detail="`available_collections` must be an array.")
    if registry_plugins is not None and not isinstance(registry_plugins, list):
        raise HTTPException(status_code=400, detail="`registry_plugins` must be an array.")

    cm = get_config_manager()
    providers_block = cm.get_ai_providers()
    variables = _collect_ai_variables()
    demos = _collect_plugin_demos()

    from .chat import stream_chat as ai_stream_chat

    async def event_source():
        """Render the normalized event stream as SSE bytes.

        Holds the AI semaphore for the duration of the stream so a
        client that drops mid-response still releases the slot via
        ``finally`` when the generator is closed.
        """
        try:
            await _AI_GENERATE_SEMAPHORE.acquire()
        except Exception:
            yield _format_sse_event("error", {"message": "Could not acquire AI lock."})
            return
        try:
            try:
                async for evt in ai_stream_chat(
                    messages=messages,
                    device_type=device_type,
                    providers_block=providers_block,
                    variables=variables,
                    plugin_demos=demos,
                    current_page=current_page,
                    available_pages=available_pages,
                    installed_plugins=installed_plugins,
                    available_schedules=available_schedules,
                    available_collections=available_collections,
                    registry_plugins=registry_plugins,
                    surface=surface,
                    provider_id=provider_id,
                    model=model,
                ):
                    yield _format_sse_event(evt["event"], evt["data"])
            except Exception:
                logger.exception("Unexpected error in /pages/ai/chat")
                yield _format_sse_event(
                    "error",
                    {"message": ("Unexpected AI chat error. See server logs for details.")},
                )
        finally:
            _AI_GENERATE_SEMAPHORE.release()

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
