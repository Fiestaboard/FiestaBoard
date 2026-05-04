"""Unit tests for src/ai/generator.py.

We mock httpx so we can exercise success, malformed-JSON, oversized-line,
and hallucinated-variable paths without hitting any real LLM.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import pytest

from src.ai.generator import (
    AIGenerationError,
    _extract_json_object,
    _find_unknown_variables,
    _line_visible_width,
    _resolve_model,
    _resolve_provider,
    _validate_and_repair,
    generate_page,
    test_provider as ai_test_provider,
)


# ---------------------------------------------------------------------------
# Provider / model resolution
# ---------------------------------------------------------------------------


def test_resolve_provider_raises_when_disabled():
    block = {"enabled": False, "providers": [{"id": "p1"}]}
    with pytest.raises(AIGenerationError, match="not enabled"):
        _resolve_provider(block, None)


def test_resolve_provider_raises_when_no_providers():
    block = {"enabled": True, "providers": []}
    with pytest.raises(AIGenerationError, match="No AI providers"):
        _resolve_provider(block, None)


def test_resolve_provider_uses_default_when_no_id():
    block = {
        "enabled": True,
        "providers": [
            {"id": "p1", "name": "First"},
            {"id": "p2", "name": "Second"},
        ],
        "default_provider_id": "p2",
    }
    assert _resolve_provider(block, None)["id"] == "p2"


def test_resolve_provider_falls_back_to_first_when_no_default():
    block = {
        "enabled": True,
        "providers": [{"id": "p1"}, {"id": "p2"}],
        "default_provider_id": None,
    }
    assert _resolve_provider(block, None)["id"] == "p1"


def test_resolve_provider_explicit_id_wins():
    block = {
        "enabled": True,
        "providers": [{"id": "p1"}, {"id": "p2"}],
        "default_provider_id": "p1",
    }
    assert _resolve_provider(block, "p2")["id"] == "p2"


def test_resolve_provider_unknown_id_raises():
    block = {"enabled": True, "providers": [{"id": "p1"}]}
    with pytest.raises(AIGenerationError, match="not found"):
        _resolve_provider(block, "nope")


def test_resolve_model_prefers_explicit():
    provider = {"models": ["a", "b"], "default_model": "a"}
    assert _resolve_model(provider, "b") == "b"


def test_resolve_model_uses_default_then_first():
    assert _resolve_model({"models": ["a"], "default_model": "z"}, None) == "z"
    assert _resolve_model({"models": ["a", "b"]}, None) == "a"


def test_resolve_model_raises_when_none_configured():
    with pytest.raises(AIGenerationError, match="no models configured"):
        _resolve_model({"id": "p", "name": "P", "models": []}, None)


# ---------------------------------------------------------------------------
# Output parsing / repair
# ---------------------------------------------------------------------------


def test_extract_json_object_strict():
    assert _extract_json_object('{"a": 1}') == {"a": 1}


def test_extract_json_object_handles_markdown_fence():
    text = "```json\n{\"a\": 2}\n```"
    assert _extract_json_object(text) == {"a": 2}


def test_extract_json_object_handles_preamble():
    text = "Here you go!\n\n{\"name\": \"X\", \"template\": []}\nThanks"
    assert _extract_json_object(text) == {"name": "X", "template": []}


def test_extract_json_object_raises_on_garbage():
    with pytest.raises(AIGenerationError):
        _extract_json_object("totally not json")


def test_line_visible_width_ignores_variable_refs():
    # Variables shouldn't be counted (their width varies at render time).
    assert _line_visible_width("{{weather.temp}}F") == 1


def test_line_visible_width_counts_color_tokens_as_one():
    assert _line_visible_width("{red}HI{red}") == 4  # 1 + 'H' + 'I' + 1


def test_validate_and_repair_pads_short_template():
    raw = {
        "name": "Test",
        "type": "template",
        "device_type": "flagship",
        "template": ["only one line"],
    }
    page, warnings = _validate_and_repair(raw, "flagship", {})
    assert len(page["template"]) == 6
    assert any("padded" in w.lower() for w in warnings)


def test_validate_and_repair_truncates_long_template():
    raw = {
        "name": "Test",
        "type": "template",
        "device_type": "flagship",
        "template": ["x"] * 12,
    }
    page, warnings = _validate_and_repair(raw, "flagship", {})
    assert len(page["template"]) == 6
    assert any("truncated" in w.lower() for w in warnings)


def test_validate_and_repair_trims_oversized_line():
    long_line = "A" * 40  # flagship max is 22
    raw = {
        "name": "Test",
        "type": "template",
        "device_type": "flagship",
        "template": [long_line, "", "", "", "", ""],
    }
    page, warnings = _validate_and_repair(raw, "flagship", {})
    assert len(page["template"][0]) == 22
    assert any("trimmed" in w.lower() for w in warnings)


def test_validate_and_repair_preserves_wrap_lines():
    long_line = "B" * 40
    raw = {
        "name": "Test",
        "type": "template",
        "device_type": "flagship",
        "template": [long_line, "", "", "", "", ""],
        "line_metadata": [
            {"alignment": "left", "wrap": True},
            {"alignment": "left", "wrap": False},
            {"alignment": "left", "wrap": False},
            {"alignment": "left", "wrap": False},
            {"alignment": "left", "wrap": False},
            {"alignment": "left", "wrap": False},
        ],
    }
    page, _warnings = _validate_and_repair(raw, "flagship", {})
    # Wrap lines are NOT trimmed.
    assert page["template"][0] == long_line


def test_validate_and_repair_clamps_duration():
    raw = {
        "name": "T",
        "type": "template",
        "device_type": "flagship",
        "template": ["x"] * 6,
        "duration_seconds": 999999,
    }
    page, _ = _validate_and_repair(raw, "flagship", {})
    assert page["duration_seconds"] == 3600


def test_validate_and_repair_coerces_wrong_type_and_device_type():
    raw = {
        "name": "Test",
        "type": "single",  # wrong
        "device_type": "note",  # wrong
        "template": ["a"] * 6,
    }
    page, warnings = _validate_and_repair(raw, "flagship", {})
    assert page["type"] == "template"
    assert page["device_type"] == "flagship"
    assert any("type" in w for w in warnings)
    assert any("device_type" in w for w in warnings)


def test_validate_and_repair_raises_on_missing_template():
    raw = {"name": "T", "type": "template", "device_type": "flagship"}
    with pytest.raises(AIGenerationError, match="template"):
        _validate_and_repair(raw, "flagship", {})


def test_validate_and_repair_flags_unknown_variables():
    raw = {
        "name": "T",
        "type": "template",
        "device_type": "flagship",
        "template": ["{{ghost.field}}", "", "", "", "", ""],
    }
    known: Dict[str, Dict[str, Dict[str, Any]]] = {
        "weather": {"temperature": {"description": "x"}}
    }
    _page, warnings = _validate_and_repair(raw, "flagship", known)
    assert any("ghost.field" in w for w in warnings)


def test_validate_and_repair_supplies_default_name():
    raw = {
        "type": "template",
        "device_type": "flagship",
        "template": ["a"] * 6,
    }
    page, warnings = _validate_and_repair(raw, "flagship", {})
    assert page["name"]
    assert any("name" in w.lower() for w in warnings)


def test_find_unknown_variables_returns_only_unknown():
    known = {"weather": {"temp": {}}}
    template = [
        "{{weather.temp}}",
        "{{weather.notreal}}",
        "{{ghost.x}}",
        "static",
    ]
    unknown = _find_unknown_variables(template, known)
    assert "weather.notreal" in unknown
    assert "ghost.x" in unknown
    assert "weather.temp" not in unknown


# ---------------------------------------------------------------------------
# generate_page() end-to-end with a mocked httpx client
# ---------------------------------------------------------------------------


class _MockResponse:
    def __init__(self, status_code: int, json_body: Any, text: str = ""):
        self.status_code = status_code
        self._json = json_body
        self.text = text or json.dumps(json_body)

    def json(self):
        return self._json


class _MockAsyncClient:
    def __init__(self, responder):
        self._responder = responder
        self.calls = []

    async def post(self, url, headers=None, json=None):  # noqa: A002
        self.calls.append({"url": url, "headers": headers, "json": json})
        return self._responder(url, headers, json)

    async def aclose(self):  # pragma: no cover — not used when client is owned externally
        pass


def _make_chat_response(content: str, usage: Optional[Dict[str, int]] = None):
    return _MockResponse(
        200,
        {
            "choices": [
                {"message": {"role": "assistant", "content": content}}
            ],
            "usage": usage or {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        },
    )


_PROVIDERS_BLOCK = {
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


@pytest.mark.asyncio
async def test_generate_page_happy_path():
    page_json = {
        "name": "Time",
        "type": "template",
        "device_type": "flagship",
        "template": ["", "{{date_time.time_12h}}", "", "", "", ""],
        "line_metadata": [
            {"alignment": "center", "wrap": False} for _ in range(6)
        ],
        "duration_seconds": 60,
    }

    def responder(url, headers, body):
        # Sanity: API key was sent in Authorization header.
        assert headers["Authorization"] == "Bearer secret"
        # Endpoint suffix is correct.
        assert url.endswith("/chat/completions")
        return _make_chat_response(json.dumps(page_json))

    client = _MockAsyncClient(responder)
    result = await generate_page(
        user_prompt="Show me the time",
        device_type="flagship",
        providers_block=_PROVIDERS_BLOCK,
        variables={"date_time": {"time_12h": {"description": "x"}}},
        client=client,
    )
    assert result["page"]["name"] == "Time"
    assert result["model_used"] == "test-model"
    assert result["provider_id"] == "p1"
    assert result["warnings"] == []
    assert result["usage"]["total_tokens"] == 15


@pytest.mark.asyncio
async def test_generate_page_repairs_oversized_lines():
    page_json = {
        "name": "Big",
        "type": "template",
        "device_type": "flagship",
        "template": ["X" * 50, "", "", "", "", ""],
        "line_metadata": [
            {"alignment": "left", "wrap": False} for _ in range(6)
        ],
    }

    def responder(url, headers, body):
        return _make_chat_response(json.dumps(page_json))

    client = _MockAsyncClient(responder)
    result = await generate_page(
        user_prompt="x",
        device_type="flagship",
        providers_block=_PROVIDERS_BLOCK,
        variables={},
        client=client,
    )
    assert len(result["page"]["template"][0]) == 22
    assert any("trimmed" in w.lower() for w in result["warnings"])


@pytest.mark.asyncio
async def test_generate_page_flags_hallucinated_variables():
    page_json = {
        "name": "Halu",
        "type": "template",
        "device_type": "flagship",
        "template": ["{{fake.field}}", "", "", "", "", ""],
    }

    def responder(url, headers, body):
        return _make_chat_response(json.dumps(page_json))

    client = _MockAsyncClient(responder)
    result = await generate_page(
        user_prompt="x",
        device_type="flagship",
        providers_block=_PROVIDERS_BLOCK,
        variables={"weather": {"temp": {"description": "x"}}},
        client=client,
    )
    assert any("fake.field" in w for w in result["warnings"])


@pytest.mark.asyncio
async def test_generate_page_raises_on_malformed_json():
    def responder(url, headers, body):
        return _make_chat_response("absolutely not json")

    client = _MockAsyncClient(responder)
    with pytest.raises(AIGenerationError):
        await generate_page(
            user_prompt="x",
            device_type="flagship",
            providers_block=_PROVIDERS_BLOCK,
            variables={},
            client=client,
        )


@pytest.mark.asyncio
async def test_generate_page_raises_on_provider_error_status():
    def responder(url, headers, body):
        return _MockResponse(
            401,
            {"error": {"message": "Invalid API key"}},
            text='{"error":{"message":"Invalid API key"}}',
        )

    client = _MockAsyncClient(responder)
    with pytest.raises(AIGenerationError, match="Invalid API key"):
        await generate_page(
            user_prompt="x",
            device_type="flagship",
            providers_block=_PROVIDERS_BLOCK,
            variables={},
            client=client,
        )


@pytest.mark.asyncio
async def test_generate_page_rejects_empty_prompt():
    with pytest.raises(AIGenerationError, match="empty"):
        await generate_page(
            user_prompt="   ",
            device_type="flagship",
            providers_block=_PROVIDERS_BLOCK,
        )


@pytest.mark.asyncio
async def test_test_provider_returns_ok_on_success():
    def responder(url, headers, body):
        return _make_chat_response("ok")

    client = _MockAsyncClient(responder)
    result = await ai_test_provider(
        _PROVIDERS_BLOCK["providers"][0], client=client
    )
    assert result["ok"] is True
    assert result["model_used"] == "test-model"


@pytest.mark.asyncio
async def test_test_provider_returns_failure_on_error():
    def responder(url, headers, body):
        return _MockResponse(
            500,
            {"error": {"message": "boom"}},
            text='{"error":{"message":"boom"}}',
        )

    client = _MockAsyncClient(responder)
    result = await ai_test_provider(
        _PROVIDERS_BLOCK["providers"][0], client=client
    )
    assert result["ok"] is False
    assert "boom" in result["message"]
