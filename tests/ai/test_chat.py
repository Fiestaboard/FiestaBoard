"""Tests for src/ai/chat.py and src/ai/chat_ops.py.

The fence parser and tool-call validator are pure functions, so they're
exercised directly. ``stream_chat`` is end-to-end tested with an
``httpx.MockTransport`` that returns a synthetic SSE stream — exactly
what a real provider would emit.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import httpx
import pytest

from src.ai.chat import _FenceParser, stream_chat
from src.ai.chat_ops import (
    ToolCallValidationError,
    parse_tool_call,
)


_PROVIDERS_BLOCK_OPENAI: Dict[str, Any] = {
    "enabled": True,
    "providers": [
        {
            "id": "p1",
            "name": "Test",
            "protocol": "openai",
            "base_url": "https://example.test/v1",
            "api_key": "secret",
            "models": ["test-model"],
            "default_model": "test-model",
        }
    ],
    "default_provider_id": "p1",
}


_PROVIDERS_BLOCK_ANTHROPIC: Dict[str, Any] = {
    "enabled": True,
    "providers": [
        {
            "id": "p1",
            "name": "Anth",
            "protocol": "anthropic",
            "base_url": "https://example.test/v1",
            "api_key": "secret",
            "models": ["claude-test"],
            "default_model": "claude-test",
        }
    ],
    "default_provider_id": "p1",
}


# ---------------------------------------------------------------------------
# parse_tool_call
# ---------------------------------------------------------------------------


def test_parse_tool_call_replace_page():
    payload = {
        "op": "replace_page",
        "args": {
            "name": "Hi",
            "template": ["A", "B"],
            "line_metadata": [
                {"alignment": "center", "wrap": False},
                {"alignment": "left", "wrap": True},
            ],
            "duration_seconds": 120,
        },
    }
    tool = parse_tool_call(payload)
    assert tool.op == "replace_page"
    assert tool.args.name == "Hi"
    assert tool.args.template == ["A", "B"]
    assert tool.args.duration_seconds == 120


def test_parse_tool_call_apply_patch():
    payload = {
        "op": "apply_patch",
        "args": {
            "rename": "New",
            "changes": [
                {"type": "replace_line", "index": 0, "text": "X"},
                {"type": "insert_line", "index": 1, "text": "Y", "wrap": True},
                {"type": "delete_line", "index": 4},
                {
                    "type": "update_line_metadata",
                    "index": 2,
                    "alignment": "right",
                },
            ],
        },
    }
    tool = parse_tool_call(payload)
    assert tool.op == "apply_patch"
    assert tool.args.rename == "New"
    assert len(tool.args.changes) == 4
    assert tool.args.changes[0].type == "replace_line"
    assert tool.args.changes[3].alignment == "right"


def test_parse_tool_call_suggest_variables():
    payload = {
        "op": "suggest_variables",
        "args": {
            "suggestions": [
                {"ref": "weather.temperature", "description": "Temp"},
            ]
        },
    }
    tool = parse_tool_call(payload)
    assert tool.op == "suggest_variables"
    assert tool.args.suggestions[0].ref == "weather.temperature"


def test_parse_tool_call_navigate_to_page():
    payload = {"op": "navigate_to_page", "args": {"page_id": "abc123"}}
    tool = parse_tool_call(payload)
    assert tool.op == "navigate_to_page"
    assert tool.args.page_id == "abc123"


def test_parse_tool_call_navigate_to_page_new():
    payload = {"op": "navigate_to_page", "args": {"page_id": "new"}}
    tool = parse_tool_call(payload)
    assert tool.args.page_id == "new"


def test_parse_tool_call_navigate_to_schedule_no_prefill():
    payload = {"op": "navigate_to_schedule", "args": {}}
    tool = parse_tool_call(payload)
    assert tool.op == "navigate_to_schedule"
    assert tool.args.prefill is None


def test_parse_tool_call_navigate_to_schedule_with_prefill():
    payload = {
        "op": "navigate_to_schedule",
        "args": {
            "prefill": {
                "page_id": "abc123",
                "start_time": "07:00",
                "end_time": "09:00",
                "day_pattern": "weekdays",
            }
        },
    }
    tool = parse_tool_call(payload)
    assert tool.op == "navigate_to_schedule"
    assert tool.args.prefill == {
        "page_id": "abc123",
        "start_time": "07:00",
        "end_time": "09:00",
        "day_pattern": "weekdays",
    }


def test_parse_tool_call_install_plugin():
    payload = {
        "op": "install_plugin",
        "args": {
            "plugin_id": "openweather",
            "source": "registry",
            "auto_enable": True,
        },
    }
    tool = parse_tool_call(payload)
    assert tool.op == "install_plugin"
    assert tool.args.plugin_id == "openweather"
    assert tool.args.source == "registry"
    assert tool.args.auto_enable is True


def test_parse_tool_call_install_plugin_defaults():
    payload = {"op": "install_plugin", "args": {"plugin_id": "myplugin"}}
    tool = parse_tool_call(payload)
    assert tool.args.source == "registry"
    assert tool.args.auto_enable is True
    assert tool.args.initial_config is None


def test_parse_tool_call_update_plugin_config():
    payload = {
        "op": "update_plugin_config",
        "args": {"plugin_id": "weather", "config": {"api_key": "k", "city": "NYC"}},
    }
    tool = parse_tool_call(payload)
    assert tool.op == "update_plugin_config"
    assert tool.args.plugin_id == "weather"
    assert tool.args.config["city"] == "NYC"


def test_parse_tool_call_update_setting():
    payload = {
        "op": "update_setting",
        "args": {"category": "display", "values": {"reduce_motion": True}},
    }
    tool = parse_tool_call(payload)
    assert tool.op == "update_setting"
    assert tool.args.category == "display"
    assert tool.args.values["reduce_motion"] is True


def test_parse_tool_call_update_setting_invalid_category():
    with pytest.raises(ToolCallValidationError):
        parse_tool_call(
            {"op": "update_setting", "args": {"category": "mqtt", "values": {}}}
        )


def test_parse_tool_call_create_carousel():
    call = parse_tool_call({
        "op": "create_carousel",
        "args": {
            "name": "Morning",
            "page_ids": ["abc", "def"],
            "interval_seconds": 45,
        },
    })
    assert call.op == "create_carousel"
    assert call.args.name == "Morning"
    assert call.args.page_ids == ["abc", "def"]
    assert call.args.interval_seconds == 45


def test_parse_tool_call_update_carousel():
    call = parse_tool_call({
        "op": "update_carousel",
        "args": {
            "carousel_id": "carousel:abc",
            "page_ids": ["x", "y"],
        },
    })
    assert call.op == "update_carousel"
    assert call.args.carousel_id == "carousel:abc"
    assert call.args.page_ids == ["x", "y"]
    assert call.args.name is None


def test_parse_tool_call_create_schedule():
    call = parse_tool_call({
        "op": "create_schedule",
        "args": {
            "page_id": "abc123",
            "start_time": "07:00",
            "end_time": "09:00",
            "day_pattern": "weekdays",
            "enabled": True,
        },
    })
    assert call.op == "create_schedule"
    assert call.args.page_id == "abc123"
    assert call.args.start_time == "07:00"
    assert call.args.end_time == "09:00"
    assert call.args.day_pattern == "weekdays"


def test_parse_tool_call_create_schedule_open_ended():
    call = parse_tool_call({
        "op": "create_schedule",
        "args": {
            "page_id": "abc123",
            "start_time": "08:00",
            "day_pattern": "all",
            "enabled": True,
        },
    })
    assert call.args.end_time is None


def test_parse_tool_call_update_schedule():
    call = parse_tool_call({
        "op": "update_schedule",
        "args": {
            "schedule_id": "sch-abc",
            "enabled": False,
        },
    })
    assert call.op == "update_schedule"
    assert call.args.schedule_id == "sch-abc"
    assert call.args.enabled is False
    assert call.args.start_time is None


def test_parse_tool_call_delete_schedule():
    call = parse_tool_call({
        "op": "delete_schedule",
        "args": {"schedule_id": "sch-xyz"},
    })
    assert call.op == "delete_schedule"
    assert call.args.schedule_id == "sch-xyz"


def test_parse_tool_call_update_plugin():
    call = parse_tool_call({
        "op": "update_plugin",
        "args": {"plugin_id": "openweather"},
    })
    assert call.op == "update_plugin"
    assert call.args.plugin_id == "openweather"


def test_parse_tool_call_trigger_system_update():
    call = parse_tool_call({
        "op": "trigger_system_update",
        "args": {},
    })
    assert call.op == "trigger_system_update"


def test_parse_tool_call_enable_plugin():
    call = parse_tool_call({
        "op": "enable_plugin",
        "args": {"plugin_id": "openweather"},
    })
    assert call.op == "enable_plugin"
    assert call.args.plugin_id == "openweather"


def test_parse_tool_call_disable_plugin():
    call = parse_tool_call({
        "op": "disable_plugin",
        "args": {"plugin_id": "stocks"},
    })
    assert call.op == "disable_plugin"
    assert call.args.plugin_id == "stocks"


def test_parse_tool_call_uninstall_plugin():
    call = parse_tool_call({
        "op": "uninstall_plugin",
        "args": {"plugin_id": "old_plugin"},
    })
    assert call.op == "uninstall_plugin"
    assert call.args.plugin_id == "old_plugin"


def test_parse_tool_call_unknown_op():
    with pytest.raises(ToolCallValidationError, match="Unknown tool op"):
        parse_tool_call({"op": "drop_table", "args": {}})


def test_parse_tool_call_missing_op():
    with pytest.raises(ToolCallValidationError, match="missing.*op"):
        parse_tool_call({"args": {}})


def test_parse_tool_call_not_object():
    with pytest.raises(ToolCallValidationError, match="JSON object"):
        parse_tool_call(["not", "an", "object"])


def test_parse_tool_call_bad_arg_types():
    # Negative index should fail validation.
    with pytest.raises(ToolCallValidationError):
        parse_tool_call(
            {
                "op": "apply_patch",
                "args": {
                    "changes": [
                        {"type": "replace_line", "index": -1, "text": "X"}
                    ]
                },
            }
        )


# ---------------------------------------------------------------------------
# _FenceParser
# ---------------------------------------------------------------------------


def _events(parser: _FenceParser, *chunks: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for c in chunks:
        out.extend(parser.feed(c))
    out.extend(parser.flush())
    return out


def test_fence_parser_passes_through_plain_text():
    p = _FenceParser()
    events = _events(p, "Hello, ", "world!")
    deltas = [e["data"]["delta"] for e in events if e["event"] == "text"]
    assert "".join(deltas) == "Hello, world!"
    assert all(e["event"] == "text" for e in events)


def test_fence_parser_emits_tool_call():
    p = _FenceParser()
    body = json.dumps(
        {
            "op": "apply_patch",
            "args": {
                "changes": [
                    {"type": "replace_line", "index": 0, "text": "HI"}
                ]
            },
        }
    )
    chunk = f"Here you go:\n```fiestaboard\n{body}\n```\nDone!"
    events = _events(p, chunk)
    text = "".join(
        e["data"]["delta"] for e in events if e["event"] == "text"
    )
    tools = [e for e in events if e["event"] == "tool_call"]
    assert "Here you go" in text
    assert "Done!" in text
    assert len(tools) == 1
    assert tools[0]["data"]["op"] == "apply_patch"
    assert "id" in tools[0]["data"]


def test_fence_parser_handles_chunked_fence_open():
    """Fence open marker straddles multiple chunks."""
    p = _FenceParser()
    body = '{"op":"suggest_variables","args":{"suggestions":[]}}'
    # Split right in the middle of the marker.
    events = _events(
        p, "Look:\n``", "`fiest", "aboard\n", body, "\n```\nbye"
    )
    tools = [e for e in events if e["event"] == "tool_call"]
    assert len(tools) == 1
    assert tools[0]["data"]["op"] == "suggest_variables"
    text = "".join(
        e["data"]["delta"] for e in events if e["event"] == "text"
    )
    assert text.startswith("Look:\n")
    assert text.endswith("bye")


def test_fence_parser_chunked_close():
    p = _FenceParser()
    body = '{"op":"apply_patch","args":{"changes":[]}}'
    events = _events(p, f"```fiestaboard\n{body}\n``", "`\nokay")
    tools = [e for e in events if e["event"] == "tool_call"]
    assert len(tools) == 1


def test_fence_parser_invalid_json_emits_warning():
    p = _FenceParser()
    chunk = "```fiestaboard\nnot json {{{\n```"
    events = _events(p, chunk)
    warnings = [e for e in events if e["event"] == "warning"]
    assert len(warnings) == 1
    assert "parse" in warnings[0]["data"]["message"].lower()


def test_fence_parser_invalid_op_emits_warning():
    p = _FenceParser()
    chunk = (
        "```fiestaboard\n"
        + json.dumps({"op": "self_destruct", "args": {}})
        + "\n```"
    )
    events = _events(p, chunk)
    warnings = [e for e in events if e["event"] == "warning"]
    assert len(warnings) == 1
    assert "Unknown tool op" in warnings[0]["data"]["message"]


def test_fence_parser_unterminated_fence():
    p = _FenceParser()
    events = _events(p, "```fiestaboard\nstart of json...")
    warnings = [e for e in events if e["event"] == "warning"]
    assert any("unterminated" in w["data"]["message"].lower() for w in warnings)


def test_fence_parser_empty_block_warning():
    p = _FenceParser()
    chunk = "```fiestaboard\n\n```"
    events = _events(p, chunk)
    warnings = [e for e in events if e["event"] == "warning"]
    assert len(warnings) == 1
    assert "empty" in warnings[0]["data"]["message"].lower()


def test_fence_parser_repairs_replace_page_filled_color():
    """The reported bug: ``{{filled:green.}}`` in a replace_page tool call
    is repaired in-place and a warning event is emitted alongside the
    tool_call."""
    p = _FenceParser()
    body = json.dumps(
        {
            "op": "replace_page",
            "args": {
                "name": "Test",
                "template": [
                    "Title{{filled:green.}}99",
                    "OK",
                ],
            },
        }
    )
    events = _events(p, f"```fiestaboard\n{body}\n```")
    tools = [e for e in events if e["event"] == "tool_call"]
    warnings = [e for e in events if e["event"] == "warning"]
    assert len(tools) == 1
    assert tools[0]["data"]["args"]["template"][0] == "Title{{filled:green}}99"
    assert len(warnings) == 1
    assert "green" in warnings[0]["data"]["message"]


def test_fence_parser_repairs_apply_patch_filled_color():
    p = _FenceParser()
    body = json.dumps(
        {
            "op": "apply_patch",
            "args": {
                "changes": [
                    {
                        "type": "replace_line",
                        "index": 0,
                        "text": "X{{filled:red.}}",
                    },
                    {"type": "delete_line", "index": 1},
                ]
            },
        }
    )
    events = _events(p, f"```fiestaboard\n{body}\n```")
    tools = [e for e in events if e["event"] == "tool_call"]
    warnings = [e for e in events if e["event"] == "warning"]
    assert len(tools) == 1
    changes = tools[0]["data"]["args"]["changes"]
    assert changes[0]["text"] == "X{{filled:red}}"
    assert changes[1]["type"] == "delete_line"
    assert len(warnings) == 1


# ---------------------------------------------------------------------------
# stream_chat() end-to-end
# ---------------------------------------------------------------------------


def _openai_sse(text_chunks: List[str], usage: Dict[str, int] | None = None) -> bytes:
    """Build a minimal OpenAI-compatible SSE response body."""
    lines: List[str] = []
    for text in text_chunks:
        chunk = {"choices": [{"delta": {"content": text}}]}
        lines.append(f"data: {json.dumps(chunk)}\n\n")
    if usage:
        lines.append(f"data: {json.dumps({'choices': [], 'usage': usage})}\n\n")
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode("utf-8")


def _anthropic_sse(text_chunks: List[str]) -> bytes:
    """Build a minimal Anthropic-shape SSE response body."""
    lines: List[str] = [
        "event: message_start\n",
        "data: "
        + json.dumps({"type": "message_start", "message": {"usage": {"input_tokens": 7}}})
        + "\n\n",
    ]
    for text in text_chunks:
        ev = {
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": text},
        }
        lines.append("event: content_block_delta\n")
        lines.append(f"data: {json.dumps(ev)}\n\n")
    lines.append("event: message_delta\n")
    lines.append(
        "data: "
        + json.dumps({"type": "message_delta", "usage": {"output_tokens": 3}})
        + "\n\n"
    )
    lines.append("event: message_stop\n")
    lines.append('data: {"type": "message_stop"}\n\n')
    return "".join(lines).encode("utf-8")


class _AsyncByteStream(httpx.AsyncByteStream):
    """Minimal AsyncByteStream that splits a fixed body into small chunks.

    httpx's async client requires an AsyncByteStream when the response
    is consumed with `aiter_lines`/`aiter_bytes`. The 16-byte chunk size
    is intentional — it forces our SSE parser to buffer across chunk
    boundaries, exercising the line-reassembly path.
    """

    def __init__(self, body: bytes, chunk_size: int = 16):
        self._body = body
        self._chunk_size = chunk_size

    async def __aiter__(self):
        for i in range(0, len(self._body), self._chunk_size):
            yield self._body[i : i + self._chunk_size]

    async def aclose(self) -> None:
        pass


def _stream_response(body: bytes) -> httpx.Response:
    return httpx.Response(200, stream=_AsyncByteStream(body))


@pytest.mark.asyncio
async def test_stream_chat_emits_text_and_tool_call():
    body = "Sure!\n```fiestaboard\n" + json.dumps(
        {
            "op": "apply_patch",
            "args": {
                "changes": [
                    {"type": "replace_line", "index": 0, "text": "HELLO"}
                ]
            },
        }
    ) + "\n```\nAll set."
    sse = _openai_sse([body[:5], body[5:30], body[30:]], usage={
        "prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14,
    })

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        # Verify stream flag was sent.
        sent = json.loads(request.content)
        assert sent.get("stream") is True
        return _stream_response(sse)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    try:
        events: List[Dict[str, Any]] = []
        async for evt in stream_chat(
            messages=[{"role": "user", "content": "make line 1 say hello"}],
            device_type="flagship",
            providers_block=_PROVIDERS_BLOCK_OPENAI,
            variables={},
            current_page={
                "name": "P",
                "template": ["", "", "", "", "", ""],
                "line_metadata": [],
            },
            client=client,
        ):
            events.append(evt)
    finally:
        await client.aclose()

    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["model_used"] == "test-model"
    assert events[-1]["data"]["provider_id"] == "p1"
    assert events[-1]["data"]["usage"]["total_tokens"] == 14

    tool_calls = [e for e in events if e["event"] == "tool_call"]
    assert len(tool_calls) == 1
    assert tool_calls[0]["data"]["op"] == "apply_patch"

    text = "".join(
        e["data"]["delta"] for e in events if e["event"] == "text"
    )
    assert "Sure!" in text
    assert "All set" in text


@pytest.mark.asyncio
async def test_stream_chat_anthropic_protocol():
    body = "Hello there"
    sse = _anthropic_sse(["Hel", "lo ", "there"])

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/messages")
        # Anthropic auth header check.
        assert request.headers.get("x-api-key") == "secret"
        return _stream_response(sse)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    try:
        events = [
            evt
            async for evt in stream_chat(
                messages=[{"role": "user", "content": "hi"}],
                device_type="flagship",
                providers_block=_PROVIDERS_BLOCK_ANTHROPIC,
                variables={},
                client=client,
            )
        ]
    finally:
        await client.aclose()

    text = "".join(
        e["data"]["delta"] for e in events if e["event"] == "text"
    )
    assert text == body
    done = [e for e in events if e["event"] == "done"][0]
    assert done["data"]["usage"]["prompt_tokens"] == 7
    assert done["data"]["usage"]["completion_tokens"] == 3
    assert done["data"]["usage"]["total_tokens"] == 10


@pytest.mark.asyncio
async def test_stream_chat_invalid_tool_emits_warning_but_continues():
    bad = json.dumps({"op": "self_destruct", "args": {}})
    body = f"Trying...\n```fiestaboard\n{bad}\n```\nNever mind."
    sse = _openai_sse([body])

    def handler(request: httpx.Request) -> httpx.Response:
        return _stream_response(sse)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    try:
        events = [
            evt
            async for evt in stream_chat(
                messages=[{"role": "user", "content": "x"}],
                device_type="flagship",
                providers_block=_PROVIDERS_BLOCK_OPENAI,
                variables={},
                client=client,
            )
        ]
    finally:
        await client.aclose()

    warnings = [e for e in events if e["event"] == "warning"]
    assert len(warnings) >= 1
    assert any("Unknown tool op" in w["data"]["message"] for w in warnings)
    # Stream still finished cleanly.
    assert events[-1]["event"] == "done"
    text = "".join(
        e["data"]["delta"] for e in events if e["event"] == "text"
    )
    assert "Never mind" in text


@pytest.mark.asyncio
async def test_stream_chat_provider_error_emits_error_event():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401, json={"error": {"message": "Bad API key"}}
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    try:
        events = [
            evt
            async for evt in stream_chat(
                messages=[{"role": "user", "content": "x"}],
                device_type="flagship",
                providers_block=_PROVIDERS_BLOCK_OPENAI,
                variables={},
                client=client,
            )
        ]
    finally:
        await client.aclose()

    errors = [e for e in events if e["event"] == "error"]
    assert len(errors) == 1
    assert "401" in errors[0]["data"]["message"]
    assert "Bad API key" in errors[0]["data"]["message"]


@pytest.mark.asyncio
async def test_stream_chat_rejects_empty_messages():
    events = [
        evt
        async for evt in stream_chat(
            messages=[],
            device_type="flagship",
            providers_block=_PROVIDERS_BLOCK_OPENAI,
            variables={},
        )
    ]
    assert events == [
        {"event": "error", "data": {"message": "No messages provided."}}
    ]


@pytest.mark.asyncio
async def test_stream_chat_rejects_when_no_user_last():
    events = [
        evt
        async for evt in stream_chat(
            messages=[
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ],
            device_type="flagship",
            providers_block=_PROVIDERS_BLOCK_OPENAI,
            variables={},
        )
    ]
    assert any(
        e["event"] == "error"
        and "must end with a user message" in e["data"]["message"]
        for e in events
    )


@pytest.mark.asyncio
async def test_stream_chat_includes_history_in_request():
    """History messages should be forwarded to the provider verbatim."""
    sse = _openai_sse(["ok"])
    captured: Dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _stream_response(sse)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    try:
        async for _ in stream_chat(
            messages=[
                {"role": "user", "content": "first turn"},
                {"role": "assistant", "content": "ok i did it"},
                {"role": "user", "content": "now do it again"},
            ],
            device_type="flagship",
            providers_block=_PROVIDERS_BLOCK_OPENAI,
            variables={},
            client=client,
        ):
            pass
    finally:
        await client.aclose()

    sent_messages = captured["body"]["messages"]
    roles = [m["role"] for m in sent_messages]
    contents = [m["content"] for m in sent_messages]
    # First entry is system; "first turn" and "ok i did it" must appear,
    # then the latest user prompt at the end.
    assert roles[0] == "system"
    assert "first turn" in contents
    assert "ok i did it" in contents
    assert sent_messages[-1]["content"] == "now do it again"


# ---------------------------------------------------------------------------
# Endpoint smoke test
# ---------------------------------------------------------------------------


@pytest.fixture
def reset_throttle(monkeypatch):
    monkeypatch.setattr("src.api_server._ai_generate_last_call", 0.0)


def test_chat_endpoint_validates_body(reset_throttle):
    from fastapi.testclient import TestClient
    from src.api_server import app

    client = TestClient(app)
    r = client.post("/pages/ai/chat", json={"messages": "not a list"})
    assert r.status_code == 400


def test_chat_endpoint_rejects_invalid_device_type(reset_throttle):
    from fastapi.testclient import TestClient
    from src.api_server import app

    client = TestClient(app)
    r = client.post(
        "/pages/ai/chat",
        json={
            "messages": [{"role": "user", "content": "hi"}],
            "device_type": "watch",
        },
    )
    assert r.status_code == 400
    assert "device_type" in r.json()["detail"]
