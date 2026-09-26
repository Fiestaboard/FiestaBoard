"""Tests for src/ai/chat.py and src/ai/chat_ops.py.

The fence parser and tool-call validator are pure functions, so they're
exercised directly. ``stream_chat`` is end-to-end tested with an
``httpx.MockTransport`` that returns a synthetic SSE stream — exactly
what a real provider would emit.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from src.ai.chat import _FenceParser, stream_model
from src.ai.chat_ops import (
    ToolCallValidationError,
    parse_tool_call,
)
from src.ai.mcp_bridge import ToolDescriptor
from src.ai.protocols import get_protocol
from src.ai.tool_catalog import ParsedToolCall, ToolCatalog
from src.ai.tool_catalog import ToolCallValidationError as CatalogValidationError

_PROVIDERS_BLOCK_OPENAI: dict[str, Any] = {
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


_PROVIDERS_BLOCK_ANTHROPIC: dict[str, Any] = {
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
        parse_tool_call({"op": "update_setting", "args": {"category": "mqtt", "values": {}}})


def test_parse_tool_call_create_collection():
    call = parse_tool_call(
        {
            "op": "create_collection",
            "args": {
                "name": "Morning",
                "page_ids": ["abc", "def"],
                "interval_seconds": 45,
            },
        }
    )
    assert call.op == "create_collection"
    assert call.args.name == "Morning"
    assert call.args.page_ids == ["abc", "def"]
    assert call.args.interval_seconds == 45


def test_parse_tool_call_update_collection():
    call = parse_tool_call(
        {
            "op": "update_collection",
            "args": {
                "collection_id": "collection:abc",
                "page_ids": ["x", "y"],
            },
        }
    )
    assert call.op == "update_collection"
    assert call.args.collection_id == "collection:abc"
    assert call.args.page_ids == ["x", "y"]
    assert call.args.name is None


def test_parse_tool_call_create_schedule():
    call = parse_tool_call(
        {
            "op": "create_schedule",
            "args": {
                "page_id": "abc123",
                "start_time": "07:00",
                "end_time": "09:00",
                "day_pattern": "weekdays",
                "enabled": True,
            },
        }
    )
    assert call.op == "create_schedule"
    assert call.args.page_id == "abc123"
    assert call.args.start_time == "07:00"
    assert call.args.end_time == "09:00"
    assert call.args.day_pattern == "weekdays"


def test_parse_tool_call_create_schedule_open_ended():
    call = parse_tool_call(
        {
            "op": "create_schedule",
            "args": {
                "page_id": "abc123",
                "start_time": "08:00",
                "day_pattern": "all",
                "enabled": True,
            },
        }
    )
    assert call.args.end_time is None


def test_parse_tool_call_update_schedule():
    call = parse_tool_call(
        {
            "op": "update_schedule",
            "args": {
                "schedule_id": "sch-abc",
                "enabled": False,
            },
        }
    )
    assert call.op == "update_schedule"
    assert call.args.schedule_id == "sch-abc"
    assert call.args.enabled is False
    assert call.args.start_time is None


def test_parse_tool_call_delete_schedule():
    call = parse_tool_call(
        {
            "op": "delete_schedule",
            "args": {"schedule_id": "sch-xyz"},
        }
    )
    assert call.op == "delete_schedule"
    assert call.args.schedule_id == "sch-xyz"


def test_parse_tool_call_update_plugin():
    call = parse_tool_call(
        {
            "op": "update_plugin",
            "args": {"plugin_id": "openweather"},
        }
    )
    assert call.op == "update_plugin"
    assert call.args.plugin_id == "openweather"


def test_parse_tool_call_trigger_system_update():
    call = parse_tool_call(
        {
            "op": "trigger_system_update",
            "args": {},
        }
    )
    assert call.op == "trigger_system_update"


def test_parse_tool_call_enable_plugin():
    call = parse_tool_call(
        {
            "op": "enable_plugin",
            "args": {"plugin_id": "openweather"},
        }
    )
    assert call.op == "enable_plugin"
    assert call.args.plugin_id == "openweather"


def test_parse_tool_call_disable_plugin():
    call = parse_tool_call(
        {
            "op": "disable_plugin",
            "args": {"plugin_id": "stocks"},
        }
    )
    assert call.op == "disable_plugin"
    assert call.args.plugin_id == "stocks"


def test_parse_tool_call_uninstall_plugin():
    call = parse_tool_call(
        {
            "op": "uninstall_plugin",
            "args": {"plugin_id": "old_plugin"},
        }
    )
    assert call.op == "uninstall_plugin"
    assert call.args.plugin_id == "old_plugin"


def test_parse_tool_call_unknown_op():
    with pytest.raises(ToolCallValidationError, match="Unknown tool op"):
        parse_tool_call({"op": "drop_table", "args": {}})


def test_parse_tool_call_missing_op():
    with pytest.raises(ToolCallValidationError, match=r"missing.*op"):
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
                "args": {"changes": [{"type": "replace_line", "index": -1, "text": "X"}]},
            }
        )


# ---------------------------------------------------------------------------
# _FenceParser
#
# The parser knows fences; the catalog knows tools. A small catalog stands
# in for the MCP server's here so the tests pin parser behaviour, not the
# real tool list.
# ---------------------------------------------------------------------------


def _descriptor(name: str, schema: dict[str, Any], *, read_only: bool = False) -> ToolDescriptor:
    return ToolDescriptor(
        name=name,
        title=name,
        description=f"{name}.",
        input_schema=schema,
        read_only=read_only,
        destructive=False,
        idempotent=read_only,
        open_world=False,
        source="mcp",
    )


_CATALOG = ToolCatalog(
    [
        _descriptor("list_pages", {"type": "object", "properties": {}}, read_only=True),
        _descriptor(
            "create_page",
            {
                "type": "object",
                "properties": {"name": {"type": "string"}, "template_lines": {"type": "array"}},
                "required": ["name", "template_lines"],
            },
        ),
        _descriptor(
            "validate_template",
            {"type": "object", "properties": {"template": {"type": "string"}, "device_type": {"type": "string"}}},
        ),
        _descriptor(
            "render_page_preview",
            {"type": "object", "properties": {"template_lines": {"type": "array"}}, "required": ["template_lines"]},
            read_only=True,
        ),
    ]
)


def _parser() -> _FenceParser:
    return _FenceParser(_CATALOG.validate)


def _events(parser: _FenceParser, *chunks: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in chunks:
        out.extend(parser.feed(c))
    out.extend(parser.flush())
    return out


def test_fence_parser_passes_through_plain_text():
    events = _events(_parser(), "Hello, ", "world!")
    deltas = [e["data"]["delta"] for e in events if e["event"] == "text"]
    assert "".join(deltas) == "Hello, world!"
    assert all(e["event"] == "text" for e in events)


def test_fence_parser_emits_tool_call():
    body = json.dumps({"op": "create_page", "args": {"name": "A", "template_lines": ["HI"]}})
    chunk = f"Here you go:\n```fiestaboard\n{body}\n```\nDone!"
    events = _events(_parser(), chunk)
    text = "".join(e["data"]["delta"] for e in events if e["event"] == "text")
    tools = [e for e in events if e["event"] == "tool_call"]
    assert "Here you go" in text
    assert "Done!" in text
    assert len(tools) == 1
    assert tools[0]["data"]["name"] == "create_page"
    assert tools[0]["data"]["args"] == {"name": "A", "template_lines": ["HI"]}
    assert "id" in tools[0]["data"]


def test_fence_parser_accepts_catalog_tool_names_only():
    events = _events(_parser(), "```fiestaboard\n" + json.dumps({"op": "list_pages", "args": {}}) + "\n```")
    assert [e["event"] for e in events] == ["tool_call"]


def test_fence_parser_handles_chunked_fence_open():
    """Fence open marker straddles multiple chunks."""
    body = '{"op":"list_pages","args":{}}'
    events = _events(_parser(), "Look:\n``", "`fiest", "aboard\n", body, "\n```\nbye")
    tools = [e for e in events if e["event"] == "tool_call"]
    assert len(tools) == 1
    assert tools[0]["data"]["name"] == "list_pages"
    text = "".join(e["data"]["delta"] for e in events if e["event"] == "text")
    assert text.startswith("Look:\n")
    assert text.endswith("bye")


def test_fence_parser_chunked_close():
    body = '{"op":"list_pages","args":{}}'
    events = _events(_parser(), f"```fiestaboard\n{body}\n``", "`\nokay")
    tools = [e for e in events if e["event"] == "tool_call"]
    assert len(tools) == 1


def test_fence_parser_invalid_json_emits_warning():
    events = _events(_parser(), "```fiestaboard\nnot json {{{\n```")
    warnings = [e for e in events if e["event"] == "warning"]
    assert len(warnings) == 1
    assert "parse" in warnings[0]["data"]["message"].lower()


def test_fence_parser_unknown_tool_emits_warning_with_closest_match():
    chunk = "```fiestaboard\n" + json.dumps({"op": "creat_page", "args": {}}) + "\n```"
    events = _events(_parser(), chunk)
    warnings = [e for e in events if e["event"] == "warning"]
    assert len(warnings) == 1
    assert "Unknown tool 'creat_page'" in warnings[0]["data"]["message"]
    assert "create_page" in warnings[0]["data"]["message"]


def test_fence_parser_retired_op_emits_warning_naming_the_replacement():
    chunk = "```fiestaboard\n" + json.dumps({"op": "replace_page", "args": {"template": ["x"]}}) + "\n```"
    events = _events(_parser(), chunk)
    warnings = [e for e in events if e["event"] == "warning"]
    assert len(warnings) == 1
    assert "retired" in warnings[0]["data"]["message"]
    assert "update_page" in warnings[0]["data"]["message"]


def test_fence_parser_missing_required_arg_emits_warning():
    chunk = "```fiestaboard\n" + json.dumps({"op": "create_page", "args": {"name": "A"}}) + "\n```"
    events = _events(_parser(), chunk)
    warnings = [e for e in events if e["event"] == "warning"]
    assert len(warnings) == 1
    assert "template_lines" in warnings[0]["data"]["message"]


def test_fence_parser_schema_failure_does_not_leak_raw_exception_text():
    """A validation failure reaches the client sanitized, not verbatim.

    The warning event is streamed straight to the browser over SSE, so it
    must be a single bounded line of printable ASCII whatever the validator
    raised — this is CodeQL's ``py/stack-trace-exposure`` sink.
    """

    def noisy_validate(payload: object) -> ParsedToolCall:
        raise CatalogValidationError("2 validation errors\nname\n  Input should be a valid string\n" + "x" * 2000)

    p = _FenceParser(noisy_validate)
    events = _events(p, "```fiestaboard\n" + json.dumps({"op": "create_page", "args": {}}) + "\n```")

    warnings = [e for e in events if e["event"] == "warning"]
    assert len(warnings) == 1
    message = warnings[0]["data"]["message"]
    assert message.startswith("Invalid fiestaboard tool block: ")
    assert "\n" not in message and "\r" not in message
    assert all(" " <= ch <= "~" for ch in message)
    assert len(message) <= len("Invalid fiestaboard tool block: ") + 500


def test_fence_parser_unterminated_fence():
    events = _events(_parser(), "```fiestaboard\nstart of json...")
    warnings = [e for e in events if e["event"] == "warning"]
    assert any("unterminated" in w["data"]["message"].lower() for w in warnings)


def test_fence_parser_empty_block_warning():
    events = _events(_parser(), "```fiestaboard\n\n```")
    warnings = [e for e in events if e["event"] == "warning"]
    assert len(warnings) == 1
    assert "empty" in warnings[0]["data"]["message"].lower()


def test_fence_parser_repairs_create_page_filled_color():
    """``{{filled:green.}}`` in a create_page call is repaired in place and
    a warning event is emitted alongside the tool_call."""
    body = json.dumps(
        {"op": "create_page", "args": {"name": "Test", "template_lines": ["Title{{filled:green.}}99", "OK"]}}
    )
    events = _events(_parser(), f"```fiestaboard\n{body}\n```")
    tools = [e for e in events if e["event"] == "tool_call"]
    warnings = [e for e in events if e["event"] == "warning"]
    assert len(tools) == 1
    assert tools[0]["data"]["args"]["template_lines"][0] == "Title{{filled:green}}99"
    assert len(warnings) == 1
    assert "green" in warnings[0]["data"]["message"]


def test_fence_parser_streams_drafts_while_a_block_is_open():
    """While the model is still inside a fence the parser emits
    ``tool_streaming`` frames — the block so far plus the tool name once it
    is legible — so the UI can move before the call completes. The frames
    stop at the close, and the validated ``tool_call`` follows."""
    body = json.dumps({"op": "create_page", "args": {"name": "Morning", "template_lines": ["HELLO", "WORLD"]}})
    text = "Sure.\n```fiestaboard\n" + body + "\n```\nDone."
    parser = _parser()
    events: list[dict[str, Any]] = []
    for i in range(0, len(text), 5):
        events.extend(parser.feed(text[i : i + 5]))
    events.extend(parser.flush())
    drafts = [e["data"] for e in events if e["event"] == "tool_streaming"]
    assert len(drafts) >= 3, [e["event"] for e in events]
    assert drafts[0]["text"].startswith("{")
    assert body.startswith(drafts[-1]["text"]), "every draft is a prefix of the block"
    assert drafts[-1]["op"] == "create_page"
    assert any(d["op"] is None for d in drafts), "the name is unknown until it has been written"
    kinds = [e["event"] for e in events]
    assert kinds.index("tool_call") > kinds.index("tool_streaming")
    assert "tool_streaming" not in kinds[kinds.index("tool_call") :]


def test_fence_parser_leaves_a_read_only_preview_unrepaired():
    """render_page_preview carries template_lines like create_page does, but
    it is a viewer, not a writer: it renders what the model wrote."""
    body = json.dumps({"op": "render_page_preview", "args": {"template_lines": ["X{{filled:red.}}", "OK"]}})
    events = _events(_parser(), f"```fiestaboard\n{body}\n```")
    tools = [e for e in events if e["event"] == "tool_call"]
    assert len(tools) == 1
    assert tools[0]["data"]["args"]["template_lines"] == ["X{{filled:red.}}", "OK"]
    assert [e for e in events if e["event"] == "warning"] == []


def test_fence_parser_leaves_validate_template_exactly_as_written():
    """The checker must see the model's own text: repairing it first would
    report a mistake as valid and the model would keep making it."""
    body = json.dumps(
        {"op": "validate_template", "args": {"template": "X{{filled:red.}}\nOK", "device_type": "flagship"}}
    )
    events = _events(_parser(), f"```fiestaboard\n{body}\n```")
    tools = [e for e in events if e["event"] == "tool_call"]
    warnings = [e for e in events if e["event"] == "warning"]
    assert len(tools) == 1
    assert tools[0]["data"]["args"]["template"] == "X{{filled:red.}}\nOK"
    assert warnings == []


# ---------------------------------------------------------------------------
# stream_model() — one provider request
# ---------------------------------------------------------------------------


def _openai_sse(text_chunks: list[str], usage: dict[str, int] | None = None) -> bytes:
    """Build a minimal OpenAI-compatible SSE response body."""
    lines: list[str] = []
    for text in text_chunks:
        chunk = {"choices": [{"delta": {"content": text}}]}
        lines.append(f"data: {json.dumps(chunk)}\n\n")
    if usage:
        lines.append(f"data: {json.dumps({'choices': [], 'usage': usage})}\n\n")
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode("utf-8")


def _anthropic_sse(text_chunks: list[str]) -> bytes:
    """Build a minimal Anthropic-shape SSE response body."""
    lines: list[str] = [
        "event: message_start\n",
        "data: " + json.dumps({"type": "message_start", "message": {"usage": {"input_tokens": 7}}}) + "\n\n",
    ]
    for text in text_chunks:
        ev = {
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": text},
        }
        lines.append("event: content_block_delta\n")
        lines.append(f"data: {json.dumps(ev)}\n\n")
    lines.append("event: message_delta\n")
    lines.append("data: " + json.dumps({"type": "message_delta", "usage": {"output_tokens": 3}}) + "\n\n")
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


def _fresh_usage() -> dict[str, int | None]:
    return {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}


async def _stream(handler, provider: dict[str, Any], messages: list[dict[str, str]], usage: dict[str, int | None]):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        return [
            evt
            async for evt in stream_model(
                protocol=get_protocol(provider.get("protocol")),
                provider=provider,
                model="test-model",
                messages=messages,
                parser=_parser(),
                usage=usage,
                client=client,
            )
        ]
    finally:
        await client.aclose()


_OPENAI = _PROVIDERS_BLOCK_OPENAI["providers"][0]
_ANTHROPIC = _PROVIDERS_BLOCK_ANTHROPIC["providers"][0]
_MESSAGES = [{"role": "system", "content": "sys"}, {"role": "user", "content": "make line 1 say hello"}]


@pytest.mark.asyncio
async def test_stream_model_emits_text_and_tool_call_and_records_usage():
    body = (
        "Sure!\n```fiestaboard\n"
        + json.dumps({"op": "create_page", "args": {"name": "A", "template_lines": ["HELLO"]}})
        + "\n```\nAll set."
    )
    sse = _openai_sse(
        [body[:5], body[5:30], body[30:]], usage={"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14}
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        sent = json.loads(request.content)
        assert sent.get("stream") is True
        assert "response_format" not in sent
        assert sent["messages"] == _MESSAGES  # forwarded verbatim; the agent owns the prompt
        return _stream_response(sse)

    usage = _fresh_usage()
    events = await _stream(handler, _OPENAI, _MESSAGES, usage)

    assert usage["total_tokens"] == 14
    assert "done" not in {e["event"] for e in events}  # the loop, not the call, ends a turn
    tool_calls = [e for e in events if e["event"] == "tool_call"]
    assert len(tool_calls) == 1
    assert tool_calls[0]["data"]["name"] == "create_page"
    text = "".join(e["data"]["delta"] for e in events if e["event"] == "text")
    assert "Sure!" in text
    assert "All set" in text


@pytest.mark.asyncio
async def test_stream_model_anthropic_protocol():
    sse = _anthropic_sse(["Hel", "lo ", "there"])

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/messages")
        assert request.headers.get("x-api-key") == "secret"
        return _stream_response(sse)

    usage = _fresh_usage()
    events = await _stream(handler, _ANTHROPIC, _MESSAGES, usage)

    text = "".join(e["data"]["delta"] for e in events if e["event"] == "text")
    assert text == "Hello there"
    assert usage == {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}


@pytest.mark.asyncio
async def test_stream_model_invalid_tool_emits_warning_but_continues():
    bad = json.dumps({"op": "self_destruct", "args": {}})
    body = f"Trying...\n```fiestaboard\n{bad}\n```\nNever mind."

    def handler(request: httpx.Request) -> httpx.Response:
        return _stream_response(_openai_sse([body]))

    events = await _stream(handler, _OPENAI, _MESSAGES, _fresh_usage())

    warnings = [e for e in events if e["event"] == "warning"]
    assert any("Unknown tool 'self_destruct'" in w["data"]["message"] for w in warnings)
    assert "error" not in {e["event"] for e in events}
    text = "".join(e["data"]["delta"] for e in events if e["event"] == "text")
    assert "Never mind" in text


@pytest.mark.asyncio
async def test_stream_model_provider_error_emits_error_event():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Bad API key"}})

    events = await _stream(handler, _OPENAI, _MESSAGES, _fresh_usage())

    assert [e["event"] for e in events] == ["error"]
    assert "401" in events[0]["data"]["message"]
    assert "Bad API key" in events[0]["data"]["message"]


@pytest.mark.asyncio
async def test_stream_model_without_base_url_is_an_error_event():
    events = await _stream(
        lambda r: _stream_response(_openai_sse(["x"])), {**_OPENAI, "base_url": ""}, _MESSAGES, _fresh_usage()
    )
    assert [e["event"] for e in events] == ["error"]


# ---------------------------------------------------------------------------
# Endpoint smoke test
# ---------------------------------------------------------------------------


@pytest.fixture
def reset_throttle(monkeypatch):
    monkeypatch.setattr("src.ai.page_routes._ai_generate_last_call", 0.0)


def test_chat_endpoint_validates_body(reset_throttle):
    from fastapi.testclient import TestClient

    from src.api_server import app

    client = TestClient(app)
    r = client.post("/pages/ai/chat", json={"messages": "not a list"})
    # 422 since the conventions pass typed the body as AIChatRequest; the
    # hand-rolled 400 "`messages` must be a non-empty array." is gone.
    assert r.status_code == 422


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
    # 422 since the conventions pass made device_type a Literal. FastAPI's
    # validation detail still names the field, which is what this asserts.
    assert r.status_code == 422
    assert "device_type" in r.text
