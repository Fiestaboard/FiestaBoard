"""Tests for the protocol adapter registry.

Verifies that adding the Anthropic Messages API does not require
branching elsewhere — all wire-format differences are isolated to
``src/ai/protocols.py``.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from src.ai.protocols import (
    DEFAULT_PROTOCOL,
    PROTOCOLS,
    Protocol,
    get_protocol,
    supported_protocols,
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_supported_protocols_includes_openai_and_anthropic():
    names = supported_protocols()
    assert "openai" in names
    assert "anthropic" in names


def test_get_protocol_defaults_to_openai_when_missing():
    assert get_protocol(None).name == DEFAULT_PROTOCOL
    assert get_protocol("").name == DEFAULT_PROTOCOL


def test_get_protocol_falls_back_for_unknown_name():
    # Forward-compat: unknown protocol names should not crash; they
    # fall back to OpenAI-compatible.
    assert get_protocol("totally-made-up").name == DEFAULT_PROTOCOL


def test_get_protocol_returns_anthropic_when_requested():
    proto = get_protocol("anthropic")
    assert proto.name == "anthropic"
    assert proto.request_path == "/messages"


# ---------------------------------------------------------------------------
# OpenAI adapter
# ---------------------------------------------------------------------------


def test_openai_headers_use_bearer_auth():
    proto = PROTOCOLS["openai"]
    headers = proto.build_headers("sk-test", {"X-Foo": "bar"})
    assert headers["Authorization"] == "Bearer sk-test"
    assert headers["Content-Type"] == "application/json"
    assert headers["X-Foo"] == "bar"


def test_openai_headers_omit_auth_when_no_key():
    proto = PROTOCOLS["openai"]
    headers = proto.build_headers("", {})
    assert "Authorization" not in headers


def test_openai_body_keeps_messages_unchanged_and_requests_json_object():
    proto = PROTOCOLS["openai"]
    messages = [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "hi"},
    ]
    body = proto.build_body("gpt-4o-mini", messages, 0.7, 100)
    assert body["model"] == "gpt-4o-mini"
    assert body["messages"] == messages
    assert body["max_tokens"] == 100
    assert body["response_format"] == {"type": "json_object"}


def test_openai_parse_content_string():
    proto = PROTOCOLS["openai"]
    api_response = {
        "choices": [{"message": {"content": "hello"}}],
    }
    assert proto.parse_content(api_response) == "hello"


def test_openai_parse_content_list_parts():
    proto = PROTOCOLS["openai"]
    api_response = {
        "choices": [
            {
                "message": {
                    "content": [
                        {"type": "text", "text": "foo"},
                        {"type": "text", "text": "bar"},
                    ]
                }
            }
        ],
    }
    assert proto.parse_content(api_response) == "foobar"


def test_openai_parse_usage():
    proto = PROTOCOLS["openai"]
    usage = proto.parse_usage(
        {"usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}}
    )
    assert usage == {
        "prompt_tokens": 10,
        "completion_tokens": 20,
        "total_tokens": 30,
    }


def test_openai_parse_error_extracts_message():
    proto = PROTOCOLS["openai"]
    assert (
        proto.parse_error({"error": {"message": "bad key"}}) == "bad key"
    )
    assert proto.parse_error({"error": "string"}) is None
    assert proto.parse_error({}) is None


# ---------------------------------------------------------------------------
# Anthropic adapter
# ---------------------------------------------------------------------------


def test_anthropic_headers_use_x_api_key_and_version():
    proto = PROTOCOLS["anthropic"]
    headers = proto.build_headers("sk-ant-test", {"X-Foo": "bar"})
    assert headers["x-api-key"] == "sk-ant-test"
    assert "anthropic-version" in headers
    assert "Authorization" not in headers
    assert headers["X-Foo"] == "bar"


def test_anthropic_body_lifts_system_to_top_level():
    proto = PROTOCOLS["anthropic"]
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "again"},
    ]
    body = proto.build_body("claude-3-5-sonnet-20241022", messages, 0.5, 200)
    assert body["model"] == "claude-3-5-sonnet-20241022"
    assert body["max_tokens"] == 200
    assert body["temperature"] == 0.5
    assert body["system"] == "be brief"
    # ``messages`` must not contain a system role.
    roles = [m["role"] for m in body["messages"]]
    assert "system" not in roles
    assert roles == ["user", "assistant", "user"]
    # Anthropic does not accept ``response_format``.
    assert "response_format" not in body


def test_anthropic_body_concatenates_multiple_systems():
    proto = PROTOCOLS["anthropic"]
    messages = [
        {"role": "system", "content": "rule 1"},
        {"role": "system", "content": "rule 2"},
        {"role": "user", "content": "go"},
    ]
    body = proto.build_body("claude", messages, 0.0, 50)
    assert body["system"] == "rule 1\n\nrule 2"


def test_anthropic_body_omits_system_when_none():
    proto = PROTOCOLS["anthropic"]
    body = proto.build_body(
        "claude", [{"role": "user", "content": "hi"}], 0.0, 50
    )
    assert "system" not in body


def test_anthropic_body_coerces_unexpected_roles_to_user():
    proto = PROTOCOLS["anthropic"]
    body = proto.build_body(
        "claude",
        [{"role": "tool", "content": "x"}, {"role": "user", "content": "y"}],
        0.0,
        50,
    )
    assert body["messages"][0]["role"] == "user"
    assert body["messages"][0]["content"] == "x"


def test_anthropic_parse_content_concatenates_text_blocks():
    proto = PROTOCOLS["anthropic"]
    api_response = {
        "content": [
            {"type": "text", "text": "one "},
            {"type": "text", "text": "two"},
            {"type": "tool_use", "id": "ignored"},
        ],
    }
    assert proto.parse_content(api_response) == "one two"


def test_anthropic_parse_content_handles_missing_content():
    proto = PROTOCOLS["anthropic"]
    assert proto.parse_content({}) == ""
    assert proto.parse_content({"content": "not a list"}) == ""


def test_anthropic_parse_usage_normalizes_to_common_shape():
    proto = PROTOCOLS["anthropic"]
    usage = proto.parse_usage(
        {"usage": {"input_tokens": 7, "output_tokens": 13}}
    )
    assert usage == {
        "prompt_tokens": 7,
        "completion_tokens": 13,
        "total_tokens": 20,
    }


def test_anthropic_parse_usage_handles_missing_fields():
    proto = PROTOCOLS["anthropic"]
    usage = proto.parse_usage({})
    assert usage == {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
    }


def test_anthropic_parse_error_extracts_message():
    proto = PROTOCOLS["anthropic"]
    assert (
        proto.parse_error({"error": {"type": "invalid_request_error", "message": "bad"}})
        == "bad"
    )
    assert proto.parse_error({}) is None


# ---------------------------------------------------------------------------
# Generator integration: the generator should drive the right wire format
# purely from the provider's ``protocol`` field — no other code changes.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_page_uses_anthropic_wire_format(monkeypatch):
    """End-to-end: when protocol='anthropic', the generator should hit
    /messages with x-api-key, parse content blocks, and normalize usage.
    """
    import httpx

    from src.ai import generator as gen_mod

    captured: Dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        import json as _json

        captured["body"] = _json.loads(request.content.decode())
        # Return an Anthropic-shaped successful response with valid
        # PageCreate JSON in the assistant text.
        page_json = {
            "name": "Hi",
            "type": "template",
            "device_type": "flagship",
            "template": ["", "HELLO", "", "", "", ""],
            "line_metadata": [
                {"alignment": "center", "wrap": False} for _ in range(6)
            ],
            "duration_seconds": 60,
        }
        import json as _json2

        return httpx.Response(
            200,
            json={
                "id": "msg_123",
                "type": "message",
                "role": "assistant",
                "model": "claude-3-5-sonnet-20241022",
                "content": [
                    {"type": "text", "text": _json2.dumps(page_json)}
                ],
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await gen_mod.generate_page(
            user_prompt="say hi",
            device_type="flagship",
            providers_block={
                "enabled": True,
                "providers": [
                    {
                        "id": "anth",
                        "name": "Anthropic",
                        "protocol": "anthropic",
                        "base_url": "https://api.anthropic.com/v1",
                        "api_key": "sk-ant-x",
                        "models": ["claude-3-5-sonnet-20241022"],
                        "default_model": "claude-3-5-sonnet-20241022",
                    }
                ],
                "default_provider_id": "anth",
            },
            variables={},
            client=client,
        )

    # Hit the Anthropic Messages endpoint with the correct auth header.
    assert captured["url"].endswith("/messages")
    assert captured["headers"]["x-api-key"] == "sk-ant-x"
    assert "authorization" not in {k.lower() for k in captured["headers"]}
    assert "anthropic-version" in {k.lower() for k in captured["headers"]}
    # System prompt is lifted to the top-level field.
    assert "system" in captured["body"]
    assert all(m["role"] != "system" for m in captured["body"]["messages"])
    # Usage normalized into the common shape.
    assert result["usage"] == {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
    }
    assert result["model_used"] == "claude-3-5-sonnet-20241022"
    assert result["provider_id"] == "anth"


def test_openai_parse_content_ignores_non_text_blocks():
    """Image/tool_use blocks in an OpenAI content list must be skipped."""
    proto = PROTOCOLS["openai"]
    api_response = {
        "choices": [
            {
                "message": {
                    "content": [
                        {"type": "image_url", "image_url": {"url": "http://example.com/img.png"}},
                        {"type": "text", "text": "hello"},
                        {"type": "tool_use", "id": "call_1"},
                        {"type": "text", "text": " world"},
                    ]
                }
            }
        ],
    }
    assert proto.parse_content(api_response) == "hello world"


def test_openai_parse_usage_handles_missing_usage_key():
    """Response without a 'usage' field should return None for all counts."""
    proto = PROTOCOLS["openai"]
    usage = proto.parse_usage({})
    assert usage == {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
    }


def test_openai_parse_usage_handles_partial_usage():
    """Partial usage (only some fields present) should return None for missing ones."""
    proto = PROTOCOLS["openai"]
    usage = proto.parse_usage({"usage": {"prompt_tokens": 5}})
    assert usage["prompt_tokens"] == 5
    assert usage["completion_tokens"] is None
    assert usage["total_tokens"] is None


def test_anthropic_body_does_not_include_response_format():
    """Anthropic does not accept response_format — must be absent."""
    proto = PROTOCOLS["anthropic"]
    body = proto.build_body(
        "claude-3-5-haiku-20241022",
        [{"role": "user", "content": "hi"}],
        0.5,
        100,
    )
    assert "response_format" not in body


def test_openai_headers_with_empty_extra_headers():
    proto = PROTOCOLS["openai"]
    headers = proto.build_headers("sk-test", {})
    assert headers["Authorization"] == "Bearer sk-test"
    assert "Content-Type" in headers


def test_anthropic_parse_error_with_non_dict_error_field():
    """Error field that is a plain string should return None (no crash)."""
    proto = PROTOCOLS["anthropic"]
    assert proto.parse_error({"error": "some plain string"}) is None


def test_anthropic_parse_content_with_empty_content_list():
    proto = PROTOCOLS["anthropic"]
    assert proto.parse_content({"content": []}) == ""


@pytest.mark.asyncio
async def test_generate_page_still_uses_openai_format_by_default(monkeypatch):
    """No ``protocol`` field on the provider → OpenAI-compatible path."""
    import httpx

    from src.ai import generator as gen_mod

    captured: Dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        page_json = {
            "name": "Hi",
            "type": "template",
            "device_type": "flagship",
            "template": ["", "HELLO", "", "", "", ""],
            "line_metadata": [
                {"alignment": "center", "wrap": False} for _ in range(6)
            ],
            "duration_seconds": 60,
        }
        import json as _json

        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": _json.dumps(page_json)}}
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 2,
                    "total_tokens": 3,
                },
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        await gen_mod.generate_page(
            user_prompt="say hi",
            device_type="flagship",
            providers_block={
                "enabled": True,
                "providers": [
                    {
                        "id": "p",
                        "name": "OpenAI",
                        "base_url": "https://api.openai.com/v1",
                        "api_key": "sk-x",
                        "models": ["gpt-4o-mini"],
                        "default_model": "gpt-4o-mini",
                    }
                ],
                "default_provider_id": "p",
            },
            variables={},
            client=client,
        )

    assert captured["url"].endswith("/chat/completions")
    assert captured["headers"]["authorization"] == "Bearer sk-x"
