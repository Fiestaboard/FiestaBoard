"""Value-level contract goldens for the three ``/pages/ai/*`` routes.

Phase 2 slice — the last untagged, non-deprecated routes in the app
(``GET /pages/ai/context``, ``POST /pages/ai/generate``,
``POST /pages/ai/chat``). Written to pass against the **unmodified** trunk
before the routes moved into ``src/ai/`` and gained the conventions, so the
conversion has something to be zero-regression *against*.

Why value-level and not shape-level: a shape golden cannot see a wrong
status code, a reworded ``detail`` string or a dropped body key — the exact
class of regression the Phase 1 shape goldens missed. Every assertion below
pins a literal the client can observe: the status code, the whole
``detail`` string, the exact response keys, and for the chat endpoint the
raw SSE bytes.

This file was committed **green against the trunk** before the conversion.
The conventions commit re-pinned only what it deliberately changed, and
every one of those is marked with a ``CHANGED (conventions):`` comment
naming what moved and why. Nothing else in this file moved.

The changes, in full:

1. Structural body/query rejections moved from nine hand-rolled 400s to
   FastAPI's 422, because the two POST bodies are Pydantic models now and
   ``device_type`` is a ``Literal``. None of them is reachable from the
   app — ``global-ai-chat-drawer.tsx`` hardcodes ``device_type``, sends a
   ``surface`` of ``"editor"``/``"global"``, and always sends a non-empty
   ``messages`` array; ``generateAiPage`` has no production caller in
   ``web/src`` at all.
2. ``POST /generate``'s response is a declared ``AIGenerateResponse``, so
   ``page`` is serialized as the ``PageCreate`` it always was — every
   optional field is present-with-null instead of present-only-when-the-
   generator-set-it.

Everything else — the 400 on a whitespace-only prompt, the 400 carrying
the generator's message, the 500 wording, the 429 wording, the SSE bytes,
the stream headers, and every value in every success body — is unchanged
and asserted here to prove it.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.config_manager import ConfigManager

# The module that owns the throttle globals and the config-manager lookup the
# three handlers resolve. Kept in one constant so the move repoints the seam
# in one place rather than in every monkeypatch call.
ROUTES_MODULE = "src.ai.page_routes"

#: Every optional PageCreate field the declared response model fills in with
#: null when the generator did not set it. Listed so the assertion below is a
#: pin on the *shape*, not a restatement of whatever the code produced.
PAGE_NULL_FIELDS = {
    "display_type",
    "rows",
    "transition_strategy",
    "transition_interval_ms",
    "transition_step_size",
    "demo_plugin_id",
    "notes_wide",
    "notes_tall",
}


@pytest.fixture
def cm(tmp_path, monkeypatch):
    """Fresh ConfigManager + a reset throttle for every test.

    The 1-second ``/pages/ai/generate`` throttle is a per-process global, so
    back-to-back tests trip it unless it is reset here.
    """
    manager = ConfigManager(config_path=str(tmp_path / "config.json"))
    monkeypatch.setattr(f"{ROUTES_MODULE}.get_config_manager", lambda: manager)
    monkeypatch.setattr(f"{ROUTES_MODULE}._ai_generate_last_call", 0.0)
    return manager


@pytest.fixture
def client():
    return TestClient(app)


def _seed_provider(manager: ConfigManager) -> None:
    manager.set_ai_providers(
        {
            "enabled": True,
            "providers": [
                {
                    "id": "p1",
                    "name": "Test",
                    "base_url": "https://example.test/v1",
                    "api_key": "secret",
                    "models": ["test-model"],
                    "default_model": "test-model",
                }
            ],
            "default_provider_id": "p1",
        }
    )


#: What the mocked generator hands back. Pinned as a constant so the response
#: assertions below compare against a value, not against themselves.
GENERATED = {
    "page": {
        "name": "AI Time",
        "type": "template",
        "device_type": "flagship",
        "template": ["", "12:34", "", "", "", ""],
        "line_metadata": [{"alignment": "center", "wrap": False} for _ in range(6)],
        "duration_seconds": 60,
    },
    "model_used": "test-model",
    "provider_id": "p1",
    "warnings": ["a repair note"],
    "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
}


# ---------------------------------------------------------------------------
# GET /pages/ai/context
# ---------------------------------------------------------------------------


def test_context_returns_the_flagship_geometry_and_the_debug_prompt(client):
    res = client.get("/pages/ai/context")
    assert res.status_code == 200
    body = res.json()
    # Exact key set: the endpoint serves PromptContext.to_dict() and nothing
    # else. A dropped or added key is a client-visible change.
    assert set(body) == {
        "device_type",
        "rows",
        "cols",
        "user_prompt",
        "variables",
        "exemplars",
        "current_page",
        "system_prompt",
    }
    assert body["device_type"] == "flagship"
    assert body["rows"] == 6
    assert body["cols"] == 22
    assert body["user_prompt"] == "(no prompt — debug context only)"
    assert body["current_page"] is None
    assert isinstance(body["variables"], dict)
    assert isinstance(body["exemplars"], list)
    assert isinstance(body["system_prompt"], str) and body["system_prompt"]


def test_context_honours_the_device_type_query_param(client):
    res = client.get("/pages/ai/context?device_type=note")
    assert res.status_code == 200
    body = res.json()
    assert body["device_type"] == "note"
    assert body["rows"] == 3
    assert body["cols"] == 15


def test_context_never_leaks_a_credential_into_the_system_prompt(client, cm):
    _seed_provider(cm)
    res = client.get("/pages/ai/context")
    body = res.json()
    assert "secret" not in body["system_prompt"]
    assert "Bearer" not in body["system_prompt"]


def test_context_rejects_an_unknown_device_type(client):
    res = client.get("/pages/ai/context?device_type=potato")
    # CHANGED (conventions): was 400 with detail "Invalid device_type:
    # 'potato'" from a hand-rolled membership check. device_type is a typed
    # Literal query parameter now, so the rejection is FastAPI's own schema
    # validation. Nothing in web/src calls this debug endpoint.
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# POST /pages/ai/generate — success
# ---------------------------------------------------------------------------


def test_generate_returns_the_draft_page_and_the_provider_that_made_it(client, cm):
    _seed_provider(cm)

    async def fake_generate(**kwargs):
        return GENERATED

    with patch("src.ai.generator.generate_page", side_effect=fake_generate):
        res = client.post("/pages/ai/generate", json={"prompt": "the time", "device_type": "flagship"})

    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"page", "model_used", "provider_id", "warnings", "usage"}
    assert body["model_used"] == "test-model"
    assert body["provider_id"] == "p1"
    assert body["warnings"] == ["a repair note"]
    assert body["usage"] == {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}
    # The draft page is passed through untouched — the endpoint never
    # persists it and never rewrites it.
    page = body["page"]
    assert page["name"] == "AI Time"
    assert page["type"] == "template"
    assert page["device_type"] == "flagship"
    assert page["template"] == ["", "12:34", "", "", "", ""]
    assert page["line_metadata"] == [{"alignment": "center", "wrap": False} for _ in range(6)]
    assert page["duration_seconds"] == 60
    # CHANGED (conventions): the response is a declared AIGenerateResponse,
    # so `page` is serialized as the PageCreate it has always been — the
    # optional fields the generator left unset are now present as null
    # rather than absent. Additive only; no value the client already read
    # changed.
    assert set(page) == {
        "name",
        "type",
        "device_type",
        "template",
        "line_metadata",
        "duration_seconds",
        *PAGE_NULL_FIELDS,
    }
    assert all(page[field] is None for field in PAGE_NULL_FIELDS)


def test_generate_forwards_the_prompt_device_and_unmasked_provider_block(client, cm):
    _seed_provider(cm)
    seen: dict[str, Any] = {}

    async def fake_generate(**kwargs):
        seen.update(kwargs)
        return GENERATED

    with patch("src.ai.generator.generate_page", side_effect=fake_generate):
        res = client.post(
            "/pages/ai/generate",
            json={
                "prompt": "the time",
                "device_type": "note",
                "provider_id": "p1",
                "model": "test-model",
                "current_page": {"name": "Old", "template": ["hi"]},
            },
        )

    assert res.status_code == 200
    assert seen["user_prompt"] == "the time"
    assert seen["device_type"] == "note"
    assert seen["provider_id"] == "p1"
    assert seen["model"] == "test-model"
    assert seen["current_page"] == {"name": "Old", "template": ["hi"]}
    # The generator needs the real key, not the masked one the GET serves.
    assert seen["providers_block"]["providers"][0]["api_key"] == "secret"


# ---------------------------------------------------------------------------
# POST /pages/ai/generate — failures
# ---------------------------------------------------------------------------


def test_generate_requires_a_prompt(client, cm):
    _seed_provider(cm)
    res = client.post("/pages/ai/generate", json={"device_type": "flagship"})
    # CHANGED (conventions): was 400 "`prompt` is required." from a
    # hand-rolled isinstance check on a free-form body. `prompt` is a
    # required field on AIGenerateRequest now, so a missing one is 422.
    assert res.status_code == 422


def test_generate_rejects_a_blank_prompt(client, cm):
    _seed_provider(cm)
    res = client.post("/pages/ai/generate", json={"prompt": "   ", "device_type": "flagship"})
    assert res.status_code == 400
    assert res.json()["detail"] == "`prompt` is required."


def test_generate_rejects_an_unknown_device_type(client, cm):
    _seed_provider(cm)
    res = client.post("/pages/ai/generate", json={"prompt": "x", "device_type": "billboard"})
    # CHANGED (conventions): was 400 "Invalid device_type: 'billboard'".
    assert res.status_code == 422


def test_generate_rejects_a_non_object_current_page(client, cm):
    _seed_provider(cm)
    res = client.post(
        "/pages/ai/generate",
        json={"prompt": "x", "device_type": "flagship", "current_page": ["not", "a", "dict"]},
    )
    # CHANGED (conventions): was 400 "`current_page` must be an object."
    assert res.status_code == 422


def test_generate_rejects_a_non_object_body(client, cm):
    _seed_provider(cm)
    res = client.post("/pages/ai/generate", json=["not", "an", "object"])
    # CHANGED (conventions): was 400 "Body must be a JSON object."
    assert res.status_code == 422


def test_generate_rejects_malformed_json(client, cm):
    _seed_provider(cm)
    res = client.post(
        "/pages/ai/generate",
        content=b"{not json",
        headers={"Content-Type": "application/json"},
    )
    # CHANGED (conventions): was 400 "Invalid JSON: ...".
    assert res.status_code == 422


def test_generate_surfaces_a_generation_failure_as_a_400_with_the_model_message(client, cm):
    _seed_provider(cm)
    from src.ai.generator import AIGenerationError

    async def fake_generate(**kwargs):
        raise AIGenerationError("Bad model output: foo")

    with patch("src.ai.generator.generate_page", side_effect=fake_generate):
        res = client.post("/pages/ai/generate", json={"prompt": "x", "device_type": "flagship"})

    assert res.status_code == 400
    assert res.json()["detail"] == "Bad model output: foo"


def test_generate_hides_an_unexpected_failure_behind_a_500(client, cm):
    _seed_provider(cm)

    async def boom(**kwargs):
        raise RuntimeError("psycopg2 connection string s3cr3t")

    with patch("src.ai.generator.generate_page", side_effect=boom):
        res = client.post("/pages/ai/generate", json={"prompt": "x", "device_type": "flagship"})

    assert res.status_code == 500
    assert res.json()["detail"] == "Unexpected AI generation error. See server logs for details."
    assert "s3cr3t" not in res.text


def test_generate_throttles_a_second_call_inside_the_minimum_interval(client, cm):
    _seed_provider(cm)

    async def fake_generate(**kwargs):
        return GENERATED

    with patch("src.ai.generator.generate_page", side_effect=fake_generate):
        first = client.post("/pages/ai/generate", json={"prompt": "x", "device_type": "flagship"})
        second = client.post("/pages/ai/generate", json={"prompt": "x", "device_type": "flagship"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"] == "AI generation is rate-limited. Please wait a moment and try again."


def test_generate_rejects_a_malformed_body_without_spending_the_throttle_window(client, cm):
    """A request that never reaches the LLM never costs an LLM call.

    CHANGED (conventions): the ordering flipped, and it could not not. With
    a free-form ``await request.json()`` body the throttle ran first, so a
    malformed second call answered 429 *and* consumed the rate-limit window;
    with a Pydantic body FastAPI validates before the handler is entered, so
    it answers 422 and leaves the window alone. No abuse vector opens —
    spamming *valid* requests is still throttled (the test above) and a
    malformed one could never have reached the provider — and a request the
    server refused no longer eats the budget of the next real one.
    """
    _seed_provider(cm)

    async def fake_generate(**kwargs):
        return GENERATED

    with patch("src.ai.generator.generate_page", side_effect=fake_generate) as gen:
        client.post("/pages/ai/generate", json={"prompt": "x", "device_type": "flagship"})
        second = client.post("/pages/ai/generate", json={"nonsense": True})

    assert second.status_code == 422
    assert gen.call_count == 1


# ---------------------------------------------------------------------------
# POST /pages/ai/chat — the SSE stream
# ---------------------------------------------------------------------------

#: One of every event type ``src.ai.chat.stream_chat`` yields. The five names
#: and their payload keys are the wire contract ``web/src/lib/api-stream.ts``
#: switches on; ``web/src/lib/ai-chat-types.ts`` declares the TS mirror.
STREAMED_EVENTS: list[dict[str, Any]] = [
    {"event": "text", "data": {"delta": "Here is "}},
    {"event": "text", "data": {"delta": "the plan."}},
    {
        "event": "tool_call",
        "data": {"id": "abc123", "op": "replace_page", "args": {"name": "Scripted"}},
    },
    {"event": "warning", "data": {"message": "a recoverable issue"}},
    {
        "event": "done",
        "data": {
            "model_used": "test-model",
            "provider_id": "p1",
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        },
    },
]

CHAT_BODY = {
    "messages": [{"role": "user", "content": "hello"}],
    "device_type": "flagship",
    "surface": "editor",
}


def _fake_stream(events: list[dict[str, Any]]):
    async def stream(**kwargs):
        for evt in events:
            yield evt

    return stream


def _frames(raw: str) -> list[tuple[str, dict[str, Any]]]:
    """Parse an SSE body into ``(event, data)`` pairs."""
    parsed: list[tuple[str, dict[str, Any]]] = []
    for block in raw.split("\n\n"):
        lines = block.split("\n")
        name = next((line[len("event: ") :] for line in lines if line.startswith("event: ")), None)
        payload = next((line[len("data: ") :] for line in lines if line.startswith("data: ")), None)
        if name is None or payload is None:
            continue
        parsed.append((name, json.loads(payload)))
    return parsed


def test_chat_serves_an_event_stream_with_the_no_buffering_headers(client, cm):
    with patch("src.ai.chat.stream_chat", _fake_stream(STREAMED_EVENTS)):
        res = client.post("/pages/ai/chat", json=CHAT_BODY)

    assert res.status_code == 200
    assert res.headers["content-type"] == "text/event-stream; charset=utf-8"
    # Buffering an SSE stream anywhere between here and the browser turns a
    # live chat into a single blob at the end. All three headers matter.
    assert res.headers["cache-control"] == "no-cache, no-transform"
    assert res.headers["x-accel-buffering"] == "no"
    assert res.headers["connection"] == "keep-alive"


def test_chat_frames_are_sse_bytes_in_the_order_the_generator_yielded_them(client, cm):
    with patch("src.ai.chat.stream_chat", _fake_stream(STREAMED_EVENTS)):
        res = client.post("/pages/ai/chat", json=CHAT_BODY)

    # The literal wire format: `event: <name>\ndata: <json>\n\n`. Pinned as
    # raw text because the framing — not just the parsed content — is what
    # @microsoft/fetch-event-source consumes.
    assert res.text == (
        'event: text\ndata: {"delta": "Here is "}\n\n'
        'event: text\ndata: {"delta": "the plan."}\n\n'
        "event: tool_call\n"
        'data: {"id": "abc123", "op": "replace_page", "args": {"name": "Scripted"}}\n\n'
        'event: warning\ndata: {"message": "a recoverable issue"}\n\n'
        "event: done\n"
        'data: {"model_used": "test-model", "provider_id": "p1", '
        '"usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}}\n\n'
    )


def test_chat_emits_every_event_type_the_client_switches_on(client, cm):
    """The five event names are the contract; the TS client ignores others."""
    events = [*STREAMED_EVENTS, {"event": "error", "data": {"message": "fatal"}}]
    with patch("src.ai.chat.stream_chat", _fake_stream(events)):
        res = client.post("/pages/ai/chat", json=CHAT_BODY)

    frames = _frames(res.text)
    assert [name for name, _ in frames] == ["text", "text", "tool_call", "warning", "done", "error"]
    by_name = dict(frames)
    assert set(by_name["text"]) == {"delta"}
    assert set(by_name["tool_call"]) == {"id", "op", "args"}
    assert set(by_name["warning"]) == {"message"}
    assert set(by_name["error"]) == {"message"}
    assert set(by_name["done"]) == {"model_used", "provider_id", "usage"}


def test_chat_forwards_every_context_block_to_the_streamer(client, cm):
    seen: dict[str, Any] = {}

    async def stream(**kwargs):
        seen.update(kwargs)
        yield {"event": "done", "data": {"model_used": "m", "provider_id": "p", "usage": {}}}

    with patch("src.ai.chat.stream_chat", stream):
        res = client.post(
            "/pages/ai/chat",
            json={
                "messages": [{"role": "user", "content": "hi"}],
                "device_type": "note",
                "surface": "global",
                "current_page": {"name": "Old"},
                "available_pages": [{"id": "p1", "name": "One"}],
                "installed_plugins": [{"id": "weather"}],
                "available_schedules": [{"id": "s1"}],
                "available_collections": [{"id": "c1"}],
                "registry_plugins": [{"id": "muni"}],
                "provider_id": "p1",
                "model": "test-model",
            },
        )

    assert res.status_code == 200
    assert seen["messages"] == [{"role": "user", "content": "hi"}]
    assert seen["device_type"] == "note"
    assert seen["surface"] == "global"
    assert seen["current_page"] == {"name": "Old"}
    assert seen["available_pages"] == [{"id": "p1", "name": "One"}]
    assert seen["installed_plugins"] == [{"id": "weather"}]
    assert seen["available_schedules"] == [{"id": "s1"}]
    assert seen["available_collections"] == [{"id": "c1"}]
    assert seen["registry_plugins"] == [{"id": "muni"}]
    assert seen["provider_id"] == "p1"
    assert seen["model"] == "test-model"


def test_chat_defaults_surface_to_global_for_clients_that_omit_it(client, cm):
    seen: dict[str, Any] = {}

    async def stream(**kwargs):
        seen.update(kwargs)
        yield {"event": "done", "data": {"model_used": "m", "provider_id": "p", "usage": {}}}

    with patch("src.ai.chat.stream_chat", stream):
        client.post(
            "/pages/ai/chat",
            json={"messages": [{"role": "user", "content": "hi"}], "device_type": "flagship"},
        )

    assert seen["surface"] == "global"


def test_chat_reports_an_unexpected_streamer_failure_as_an_error_frame(client, cm):
    """A crash mid-stream stays a 200 stream — the headers are already sent."""

    async def boom(**kwargs):
        yield {"event": "text", "data": {"delta": "starting"}}
        raise RuntimeError("connection string s3cr3t")

    with patch("src.ai.chat.stream_chat", boom):
        res = client.post("/pages/ai/chat", json=CHAT_BODY)

    assert res.status_code == 200
    frames = _frames(res.text)
    assert frames[-1] == ("error", {"message": "Unexpected AI chat error. See server logs for details."})
    assert "s3cr3t" not in res.text


def test_chat_is_not_rate_limited_like_generate(client, cm):
    """Conversational turns arrive back-to-back; a 429 mid-chat is not ok."""
    with patch("src.ai.chat.stream_chat", _fake_stream(STREAMED_EVENTS)):
        first = client.post("/pages/ai/chat", json=CHAT_BODY)
        second = client.post("/pages/ai/chat", json=CHAT_BODY)

    assert first.status_code == 200
    assert second.status_code == 200


# ---------------------------------------------------------------------------
# POST /pages/ai/chat — request rejections (before the stream opens)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"messages": "not a list", "device_type": "flagship"}, id="messages-not-a-list"),
        pytest.param({"messages": [], "device_type": "flagship"}, id="messages-empty"),
        pytest.param(
            {"messages": [{"role": "user", "content": "hi"}], "device_type": "watch"},
            id="unknown-device-type",
        ),
        pytest.param(
            {"messages": [{"role": "user", "content": "hi"}], "device_type": "flagship", "surface": "nonsense"},
            id="unknown-surface",
        ),
        pytest.param(
            {"messages": [{"role": "user", "content": "hi"}], "device_type": "flagship", "current_page": []},
            id="current-page-not-an-object",
        ),
        pytest.param(
            {"messages": [{"role": "user", "content": "hi"}], "device_type": "flagship", "available_pages": {}},
            id="available-pages-not-an-array",
        ),
        pytest.param(
            {"messages": [{"role": "user", "content": "hi"}], "device_type": "flagship", "installed_plugins": {}},
            id="installed-plugins-not-an-array",
        ),
        pytest.param(
            {"messages": [{"role": "user", "content": "hi"}], "device_type": "flagship", "available_schedules": {}},
            id="available-schedules-not-an-array",
        ),
        pytest.param(
            {"messages": [{"role": "user", "content": "hi"}], "device_type": "flagship", "available_collections": {}},
            id="available-collections-not-an-array",
        ),
        pytest.param(
            {"messages": [{"role": "user", "content": "hi"}], "device_type": "flagship", "registry_plugins": {}},
            id="registry-plugins-not-an-array",
        ),
        pytest.param(["not", "an", "object"], id="body-not-an-object"),
    ],
)
def test_chat_rejects_a_malformed_request_before_opening_the_stream(client, cm, body):
    """A rejected chat request is a JSON error, never a 200 SSE stream.

    ``api-stream.ts`` distinguishes the two by ``response.ok`` and then by
    ``content-type``: a failure served as a 200 event-stream would be shown
    as an empty assistant turn instead of an error.

    CHANGED (conventions): every case here answered 400 with a hand-rolled
    ``detail`` string read off a free-form JSON body. The body is an
    ``AIChatRequest`` now, so structural rejections are FastAPI's standard
    422. What is asserted here — that the rejection happens *before* the
    stream opens, and arrives as JSON rather than as a 200 event-stream —
    is exactly what it was.
    """
    res = client.post("/pages/ai/chat", json=body)
    assert res.status_code == 422
    assert res.headers["content-type"].startswith("application/json")


def test_chat_rejects_malformed_json(client, cm):
    res = client.post(
        "/pages/ai/chat",
        content=b"{not json",
        headers={"Content-Type": "application/json"},
    )
    # CHANGED (conventions): was 400 "Invalid JSON: ...".
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# The SSE event schema — what stands in for POST /chat's missing response_model
# ---------------------------------------------------------------------------


def test_every_event_stream_chat_can_emit_is_declared_in_the_registry():
    """``src/ai/chat.py`` cannot grow an undocumented event type.

    ``POST /pages/ai/chat`` streams, so it has no ``response_model`` and
    carries a checked-in exception for that rule. ``CHAT_STREAM_EVENTS`` is
    what the exception points at instead, which only means something if it
    is kept honest: this walks every ``{"event": <literal>, ...}`` dict in
    the streamer's own source and asserts the two sets are equal.
    """
    import ast
    import inspect

    from src.ai import chat as chat_module
    from src.ai.page_routes import CHAT_STREAM_EVENTS

    emitted: set[str] = set()
    for node in ast.walk(ast.parse(inspect.getsource(chat_module))):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values, strict=True):
            if isinstance(key, ast.Constant) and key.value == "event" and isinstance(value, ast.Constant):
                emitted.add(value.value)

    assert emitted == set(CHAT_STREAM_EVENTS), (
        "src/ai/chat.py emits event types the published SSE schema does not "
        "declare (or declares ones it never emits). Update CHAT_STREAM_EVENTS "
        "in src/ai/page_routes.py — it is the only schema this endpoint has."
    )


def test_streamed_frames_match_the_declared_event_models(client, cm):
    """Each frame's ``data`` is exactly the fields its model declares."""
    from src.ai.page_routes import CHAT_STREAM_EVENTS

    events = [*STREAMED_EVENTS, {"event": "error", "data": {"message": "fatal"}}]
    with patch("src.ai.chat.stream_chat", _fake_stream(events)):
        res = client.post("/pages/ai/chat", json=CHAT_BODY)

    frames = _frames(res.text)
    assert frames, "no frames to check"
    for name, data in frames:
        model = CHAT_STREAM_EVENTS[name]
        # Validates AND pins the key set: a model that merely accepts the
        # payload would still pass if the wire grew a field nobody declared.
        model.model_validate(data)
        assert set(data) <= set(model.model_fields), f"{name} frame carries undeclared keys: {sorted(data)}"


def test_the_chat_route_declares_the_event_stream_media_type():
    """The 200 documents ``text/event-stream``; a JSON body would be a lie."""
    from src.ai.page_routes import router

    route = next(r for r in router.routes if getattr(r, "path", None) == "/pages/ai/chat")
    assert route.response_model is None
    assert "text/event-stream" in route.responses[200]["content"]
    for name in ("text", "tool_call", "warning", "error", "done"):
        assert f"`{name}`" in route.responses[200]["description"]
