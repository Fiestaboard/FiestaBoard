"""The public plugin AI API: ``PluginBase.ai_complete`` and the provider picker.

Every value is a ``test_`` placeholder and every provider is an
``httpx.MockTransport``, so nothing leaves the process.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from src.ai import plugin_api, sign_in
from src.ai.generator import AIGenerationError
from src.ai.plugin_api import (
    AICompletion,
    AIError,
    AINotConfiguredError,
    AIProviderError,
    AIRejectedError,
)
from src.plugins.base import (
    OptionsRequest,
    OptionsUnavailable,
    PluginBase,
    PluginResult,
)

OPENAI = {
    "id": "oa",
    "name": "Test OpenAI",
    "protocol": "openai",
    "base_url": "https://example.test/v1",
    "api_key": "test_key",
    "models": ["test-model", "test-model-2"],
    "default_model": "test-model",
}
ANTHROPIC = {
    "id": "an",
    "name": "Test Anthropic",
    "protocol": "anthropic",
    "base_url": "https://anthropic.test/v1",
    "api_key": "test_anthropic_key",
    "models": ["test-claude"],
}
RESPONSES = {
    "id": "rs",
    "name": "Test Responses",
    "protocol": "openai_responses",
    "base_url": "https://responses.test/v1",
    "api_key": "test_responses_key",
    "models": ["test-gpt"],
}
SIGNED_IN = {"id": "or1", "name": "Router", "models": ["test-or-model"], "sign_in": {"preset": "openrouter"}}


def _block(*providers: dict[str, Any], enabled: bool = True, default: str | None = None) -> dict[str, Any]:
    return {"enabled": enabled, "providers": [dict(p) for p in providers], "default_provider_id": default}


class FakeOAuth:
    def __init__(self, token: str | None = "test_token", refreshed: str | None = None):
        self.token = token
        self.refreshed = refreshed
        self.rejected: list[str] = []

    def get_access_token(self, connection_id: str) -> str | None:
        return self.token

    def report_rejected(self, connection_id: str, rejected_token: str | None = None) -> str | None:
        self.rejected.append(connection_id)
        if self.refreshed:
            self.token = self.refreshed
        else:
            self.token = None
        return self.refreshed


def _openai_reply(text: str = "test reply") -> dict[str, Any]:
    return {
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    }


class Provider:
    """A scripted provider: replies are popped in order; every request is kept."""

    def __init__(self, *replies: httpx.Response | Exception):
        self.replies = list(replies) or [httpx.Response(200, json=_openai_reply())]
        self.seen: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return reply

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))

    def body(self, index: int = 0) -> dict[str, Any]:
        return json.loads(self.seen[index].content)


async def _complete(block: dict[str, Any], provider: Provider, messages: Any = "hi", **kwargs: Any) -> AICompletion:
    async with provider.client() as client:
        return await plugin_api.complete_async(messages, providers_block=block, client=client, **kwargs)


@pytest.fixture
def oauth(monkeypatch):
    fake = FakeOAuth()
    monkeypatch.setattr(sign_in, "_oauth", lambda: fake)
    return fake


# ── FiestaBot's settings decide what is used ────────────────────────────────


@pytest.mark.asyncio
async def test_disabled_ai_is_not_configured_and_sends_nothing():
    provider = Provider()
    with pytest.raises(AINotConfiguredError, match="not enabled"):
        await _complete(_block(OPENAI, enabled=False), provider)
    assert provider.seen == []


@pytest.mark.asyncio
async def test_no_providers_is_not_configured():
    with pytest.raises(AINotConfiguredError):
        await _complete(_block(), Provider())


@pytest.mark.asyncio
async def test_unknown_provider_id_is_not_configured():
    with pytest.raises(AINotConfiguredError, match="not found"):
        await _complete(_block(OPENAI), Provider(), provider_id="gone")


@pytest.mark.asyncio
async def test_provider_without_a_model_is_not_configured():
    bare = {**OPENAI, "models": [], "default_model": None}
    with pytest.raises(AINotConfiguredError, match="no models"):
        await _complete(_block(bare), Provider())


@pytest.mark.asyncio
async def test_none_uses_fiestabots_default_provider():
    provider = Provider(httpx.Response(200, json={"content": [{"type": "text", "text": "test claude"}]}))
    result = await _complete(_block(OPENAI, ANTHROPIC, default="an"), provider)
    assert result.provider_id == "an"
    assert str(provider.seen[0].url) == "https://anthropic.test/v1/messages"


@pytest.mark.asyncio
async def test_explicit_provider_id_and_model_win():
    provider = Provider()
    result = await _complete(_block(ANTHROPIC, OPENAI, default="an"), provider, provider_id="oa", model="test-model-2")
    assert (result.provider_id, result.model) == ("oa", "test-model-2")
    assert provider.body()["model"] == "test-model-2"


# ── the three protocols ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_openai_request_and_result():
    provider = Provider()
    messages = [{"role": "system", "content": "test sys"}, {"role": "user", "content": "test ask"}]
    result = await _complete(_block(OPENAI), provider, messages, temperature=0.1, max_tokens=42)
    request = provider.seen[0]
    assert str(request.url) == "https://example.test/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer test_key"
    body = provider.body()
    assert body["messages"] == messages
    assert (body["model"], body["temperature"], body["max_tokens"]) == ("test-model", 0.1, 42)
    assert result.text == "test reply" and str(result) == "test reply"
    assert result.usage == {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}
    assert result.data is None


@pytest.mark.asyncio
async def test_a_plain_string_is_one_user_message():
    provider = Provider()
    await _complete(_block(OPENAI), provider, "test ask")
    assert provider.body()["messages"] == [{"role": "user", "content": "test ask"}]


@pytest.mark.asyncio
async def test_anthropic_protocol_splits_the_system_prompt():
    provider = Provider(httpx.Response(200, json={"content": [{"type": "text", "text": "test claude"}]}))
    messages = [{"role": "system", "content": "test sys"}, {"role": "user", "content": "test ask"}]
    result = await _complete(_block(ANTHROPIC), provider, messages)
    assert provider.seen[0].headers["x-api-key"] == "test_anthropic_key"
    body = provider.body()
    assert [part["text"] for part in body["system"]] == ["test sys"]
    assert body["messages"] == [{"role": "user", "content": "test ask"}]
    assert result.text == "test claude"


def _sse(*events: dict[str, Any]) -> bytes:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


@pytest.mark.asyncio
async def test_openai_responses_protocol_reads_the_stream():
    stream = _sse(
        {"type": "response.output_text.delta", "delta": "test "},
        {"type": "response.output_text.delta", "delta": "stream"},
        {"type": "response.completed", "response": {"usage": {"input_tokens": 4, "output_tokens": 2}}},
    )
    provider = Provider(httpx.Response(200, content=stream, headers={"content-type": "text/event-stream"}))
    result = await _complete(_block(RESPONSES), provider)
    assert str(provider.seen[0].url) == "https://responses.test/v1/responses"
    assert provider.body()["stream"] is True
    assert result.text == "test stream"


# ── sign-in ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_signed_in_provider_sends_the_sign_in_token(oauth):
    provider = Provider()
    await _complete(_block(SIGNED_IN), provider)
    assert str(provider.seen[0].url) == "https://openrouter.ai/api/v1/chat/completions"
    assert provider.seen[0].headers["authorization"] == "Bearer test_token"


@pytest.mark.asyncio
async def test_signed_out_provider_needs_reconnect_and_sends_nothing(oauth):
    oauth.token = None
    provider = Provider()
    with pytest.raises(AIRejectedError, match="Sign in"):
        await _complete(_block(SIGNED_IN), provider)
    assert provider.seen == []


@pytest.mark.asyncio
async def test_signed_in_401_is_retried_once_with_the_refreshed_token(oauth):
    oauth.refreshed = "test_fresh"
    provider = Provider(
        httpx.Response(401, json={"error": {"message": "expired"}}), httpx.Response(200, json=_openai_reply())
    )
    result = await _complete(_block(SIGNED_IN), provider)
    assert [r.headers["authorization"] for r in provider.seen] == ["Bearer test_token", "Bearer test_fresh"]
    assert oauth.rejected == ["ai.or1"]
    assert result.text == "test reply"


@pytest.mark.asyncio
async def test_signed_in_401_without_a_refresh_needs_reconnect(oauth):
    provider = Provider(httpx.Response(401, json={"error": {"message": "revoked"}}))
    with pytest.raises(AIRejectedError):
        await _complete(_block(SIGNED_IN), provider)
    assert len(provider.seen) == 1


@pytest.mark.asyncio
async def test_api_key_401_is_rejected_without_a_retry(oauth):
    provider = Provider(httpx.Response(401, json={"error": {"message": "bad key"}}))
    with pytest.raises(AIRejectedError, match="401"):
        await _complete(_block(OPENAI), provider)
    assert len(provider.seen) == 1 and oauth.rejected == []


# ── provider errors ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_server_error_is_a_provider_error():
    with pytest.raises(AIProviderError, match="500"):
        await _complete(_block(OPENAI), Provider(httpx.Response(500, json={"error": {"message": "boom"}})))


@pytest.mark.asyncio
async def test_unreachable_provider_is_a_provider_error():
    with pytest.raises(AIProviderError, match="Could not reach"):
        await _complete(_block(OPENAI), Provider(httpx.ConnectError("test down")))


@pytest.mark.asyncio
async def test_empty_answer_is_a_provider_error():
    with pytest.raises(AIProviderError, match="empty"):
        await _complete(_block(OPENAI), Provider(httpx.Response(200, json=_openai_reply(""))))


def test_every_error_is_an_ai_error_and_an_ai_generation_error():
    for cls in (AINotConfiguredError, AIRejectedError, AIProviderError):
        assert issubclass(cls, AIError)
        assert issubclass(cls, AIGenerationError)


# ── json=True ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_json_asks_for_an_object_and_parses_it():
    provider = Provider(httpx.Response(200, json=_openai_reply('```json\n{"a": 1}\n```')))
    result = await _complete(_block(OPENAI), provider, "test ask", json=True)
    assert result.data == {"a": 1}
    messages = provider.body()["messages"]
    assert messages[0]["role"] == "system" and "JSON" in messages[0]["content"]
    assert messages[-1] == {"role": "user", "content": "test ask"}
    # Never json_object: LM Studio 400s it (#1560); the prompt asks instead.
    assert provider.body()["response_format"] == {"type": "text"}


@pytest.mark.asyncio
async def test_json_that_does_not_parse_is_a_provider_error():
    with pytest.raises(AIProviderError):
        await _complete(_block(OPENAI), Provider(httpx.Response(200, json=_openai_reply("no json"))), json=True)


# ── input checks ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "messages",
    [[], [{"role": "tool", "content": "x"}], [{"role": "user"}], [{"role": "user", "content": 3}], 7, "  "],
)
@pytest.mark.asyncio
async def test_bad_messages_are_a_value_error(messages):
    provider = Provider()
    with pytest.raises(ValueError):
        await _complete(_block(OPENAI), provider, messages)
    assert provider.seen == []


# ── PluginBase ──────────────────────────────────────────────────────────────


class _Plugin(PluginBase):
    @property
    def plugin_id(self) -> str:
        return "test_plugin"

    def fetch_data(self) -> PluginResult:
        return PluginResult(available=True)


@pytest.fixture
def plugin(monkeypatch):
    seen: dict[str, Any] = {}

    async def fake_complete_async(messages, **kwargs):
        seen["messages"], seen["kwargs"] = messages, kwargs
        return AICompletion(text="test sync", model="m", provider_id="p", usage={})

    monkeypatch.setattr(plugin_api, "complete_async", fake_complete_async)
    instance = _Plugin({"id": "test_plugin"})
    instance.seen = seen
    return instance


def test_plugin_ai_complete_runs_outside_an_event_loop(plugin):
    result = plugin.ai_complete("hi", provider_id="p", model="m", temperature=0.2, max_tokens=9, json=True)
    assert result.text == "test sync"
    assert plugin.seen["kwargs"] == {
        "provider_id": "p",
        "model": "m",
        "temperature": 0.2,
        "max_tokens": 9,
        "json": True,
        "timeout": 60.0,
    }


@pytest.mark.asyncio
async def test_plugin_ai_complete_runs_inside_a_running_event_loop(plugin):
    assert plugin.ai_complete("hi").text == "test sync"
    assert (await plugin.ai_complete_async("hi")).text == "test sync"


def test_ai_complete_reads_fiestabots_settings(monkeypatch):
    class CM:
        def get_ai_providers(self):
            return _block(OPENAI, enabled=False)

    monkeypatch.setattr("src.config_manager.get_config_manager", lambda: CM())
    with pytest.raises(AINotConfiguredError):
        asyncio.run(plugin_api.complete_async("hi"))


# ── listing providers and the ai_providers picker ───────────────────────────


@pytest.fixture
def configured(monkeypatch):
    state = {"block": _block(OPENAI, ANTHROPIC, RESPONSES, SIGNED_IN, default="an")}
    monkeypatch.setattr(plugin_api, "_providers_block", lambda: state["block"])
    return state


def test_providers_lists_every_protocol_without_secrets(configured):
    providers = plugin_api.providers()
    assert [p["id"] for p in providers] == ["oa", "an", "rs", "or1"]
    assert {p["protocol"] for p in providers} == {"openai", "anthropic", "openai_responses"}
    assert all("api_key" not in p for p in providers)
    by_id = {p["id"]: p for p in providers}
    assert by_id["an"]["default"] is True and by_id["oa"]["default"] is False
    assert by_id["or1"]["sign_in"] == "openrouter" and by_id["or1"]["protocol"] == "openai"
    assert by_id["oa"]["model"] == "test-model"


def test_providers_is_empty_when_ai_is_off(configured):
    configured["block"] = _block(OPENAI, enabled=False)
    assert plugin_api.providers() == []


def test_default_get_options_serves_ai_providers(configured):
    plugin = _Plugin({"id": "test_plugin"})
    result = plugin.get_options(OptionsRequest(options_id="ai_providers"))
    assert [o.value for o in result.options] == ["oa", "an", "rs", "or1"]
    assert "default" in (next(o for o in result.options if o.value == "an").description or "")


def test_ai_providers_options_filter_by_query(configured):
    plugin = _Plugin({"id": "test_plugin"})
    result = plugin.ai_provider_options(OptionsRequest(options_id="ai_providers", query="anthrop"))
    assert [o.value for o in result.options] == ["an"]


def test_ai_providers_options_explain_when_ai_is_off(configured):
    configured["block"] = _block(OPENAI, enabled=False)
    with pytest.raises(OptionsUnavailable, match="turned off"):
        _Plugin({"id": "test_plugin"}).get_options(OptionsRequest(options_id="ai_providers"))


def test_other_options_ids_still_raise_not_implemented():
    with pytest.raises(NotImplementedError):
        _Plugin({"id": "test_plugin"}).get_options(OptionsRequest(options_id="other"))


def test_plugins_import_the_ai_names_from_plugin_base():
    from src.plugins import base

    assert base.AIError is AIError
    assert base.AIRejectedError is AIRejectedError
    assert base.AICompletion is AICompletion
    with pytest.raises(AttributeError):
        _ = base.NoSuchName
