"""FiestaBot AI sign-in: connection sources, presets, and token use at request time.

Every value here is a ``test_`` placeholder; the provider is a scripted
transport, so nothing leaves the process.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from src.ai import sign_in
from src.ai.generator import AIGenerationError, _post_chat_completion
from src.ai.sign_in import (
    PRESETS,
    AiProviderConnectionSource,
    CompositeConnectionSource,
    forget_removed_providers,
    resolve_provider_auth,
)
from src.oauth.client import ProviderClient
from src.oauth.service import OAuthService
from src.oauth.state import StateSigner
from src.oauth.tokens import TokenSet, TokenStore

NOW = 1_800_000_000.0
BOARD = "http://192.168.1.50:4420"
HOST_ID = "00000000-0000-4000-8000-000000000001"

API_KEY_PROVIDER = {
    "id": "p1",
    "name": "Test",
    "protocol": "openai",
    "base_url": "https://example.test/v1",
    "api_key": "test_key",
    "models": ["test-model"],
}


def _signed_in(preset: str, pid: str = "or1", **extra: Any) -> dict[str, Any]:
    return {"id": pid, "name": "Router", "models": ["test-model"], "sign_in": {"preset": preset}, **extra}


def _block(*providers: dict[str, Any]) -> dict[str, Any]:
    return {"enabled": True, "providers": [dict(p) for p in providers], "default_provider_id": None}


class FakeOAuth:
    def __init__(self, token: str | None = "test_token", refreshed: str | None = None):
        self.token = token
        self.refreshed = refreshed
        self.asked: list[str] = []
        self.rejected: list[str] = []
        self.rejected_tokens: list[str | None] = []
        self.forgotten: list[str] = []

    def get_access_token(self, connection_id: str) -> str | None:
        self.asked.append(connection_id)
        return self.token

    def report_rejected(self, connection_id: str, rejected_token: str | None = None) -> str | None:
        self.rejected.append(connection_id)
        self.rejected_tokens.append(rejected_token)
        return self.refreshed

    def forget(self, connection_id: str) -> bool:
        self.forgotten.append(connection_id)
        return True


class FakeRegistrySource:
    def __init__(self, listed=("plugin:spotify",)):
        self.listed = list(listed)
        self.invalidated: list[str] = []

    def get(self, connection_id):
        return f"plugin:{connection_id}" if connection_id == "spotify" else None

    def all(self):
        return self.listed

    def id_for(self, plugin):
        return "spotify"

    def invalidate(self, connection_id):
        self.invalidated.append(connection_id)


class FakeProvider:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.replies: list[tuple[int, Any]] = []

    def reply(self, body, status=200):
        self.replies.append((status, body))
        return self

    def __call__(self, url, form):
        self.calls.append((url, dict(form)))
        return self.replies.pop(0)


class FakeHttp:
    def __init__(self):
        self.calls: list[tuple] = []
        self.replies: list[tuple[int, Any]] = []

    def __call__(self, method, url, *, headers, form=None, json_body=None):
        self.calls.append((method, url, json_body, headers))
        return self.replies.pop(0)


def _query(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


@pytest.fixture
def providers_block():
    return {"block": _block(API_KEY_PROVIDER)}


@pytest.fixture
def ai_source(providers_block):
    return AiProviderConnectionSource(providers=lambda: providers_block["block"], agent_host_id=lambda: HOST_ID)


@pytest.fixture
def transport():
    return FakeProvider()


@pytest.fixture
def http():
    return FakeHttp()


@pytest.fixture
def service(tmp_path, ai_source, transport, http):
    return OAuthService(
        source=CompositeConnectionSource(FakeRegistrySource(listed=()), ai_source),
        store=TokenStore(tmp_path / "oauth_tokens.json"),
        signer=StateSigner(b"k" * 32),
        client=ProviderClient(transport, http=http),
        clock=lambda: NOW,
        redirect_uri="https://relay.example/oauth/redirect",
        poll_in_background=False,
    )


# ── resolve_provider_auth: the api_key path is untouched ────────────────────


def test_api_key_provider_is_returned_as_the_same_object():
    fake = FakeOAuth()
    provider = dict(API_KEY_PROVIDER)
    assert resolve_provider_auth(provider, service=fake) is provider
    assert provider == API_KEY_PROVIDER
    assert fake.asked == []


def test_unknown_preset_is_left_on_the_api_key_path():
    fake = FakeOAuth()
    provider = {**API_KEY_PROVIDER, "sign_in": {"preset": "test_not_a_preset"}}
    assert resolve_provider_auth(provider, service=fake) is provider
    assert fake.asked == []


def test_signed_in_provider_gets_the_connection_token_as_its_key():
    fake = FakeOAuth(token="test_token")
    provider = _signed_in("openrouter", api_key="test_pasted_key")
    resolved = resolve_provider_auth(provider, service=fake)
    assert fake.asked == ["ai.or1"]
    assert resolved["api_key"] == "test_token"
    assert provider["api_key"] == "test_pasted_key"  # the stored dict is not mutated


def test_signed_in_provider_takes_base_url_and_protocol_from_the_preset_when_missing():
    resolved = resolve_provider_auth(_signed_in("openrouter"), service=FakeOAuth())
    assert resolved["base_url"] == "https://openrouter.ai/api/v1"
    assert resolved["protocol"] == "openai"


def test_signed_in_provider_keeps_its_own_base_url_on_the_presets_host():
    provider = _signed_in("huggingface", base_url="https://router.huggingface.co/v1/")
    resolved = resolve_provider_auth(provider, service=FakeOAuth())
    assert resolved["base_url"] == "https://router.huggingface.co/v1/"


@pytest.mark.parametrize(
    "base_url",
    ["https://example.test/v1", "http://openrouter.ai/api/v1", "https://openrouter.ai.example.test/api/v1"],
)
def test_signed_in_token_is_never_sent_to_another_host(base_url):
    fake = FakeOAuth(token="test_token")
    with pytest.raises(AIGenerationError, match="only works with"):
        resolve_provider_auth(_signed_in("openrouter", base_url=base_url), service=fake)
    assert fake.asked == []


def test_signed_out_provider_raises_a_sign_in_again_error():
    with pytest.raises(AIGenerationError, match="Sign in to Router again"):
        resolve_provider_auth(_signed_in("openrouter"), service=FakeOAuth(token=None))


# ── connection sources ──────────────────────────────────────────────────────


def test_ai_source_builds_a_target_only_for_signed_in_providers(ai_source, providers_block):
    providers_block["block"] = _block(API_KEY_PROVIDER, _signed_in("openrouter"))
    assert ai_source.get("ai.p1") is None
    target = ai_source.get("ai.or1")
    assert target.kind == "ai"
    assert target.plugin_id == "ai"
    assert target.plugin_name == "Router (FiestaBot)"
    assert target.provider.flows == ("key_exchange",)
    assert [t.connection_id for t in ai_source.all()] == ["ai.or1"]


def test_ai_source_ignores_ids_without_the_prefix(ai_source, providers_block):
    providers_block["block"] = _block(_signed_in("openrouter", pid="spotify"))
    assert ai_source.get("spotify") is None
    assert ai_source.id_for(object()) is None


def test_composite_routes_ai_ids_to_the_ai_source(ai_source, providers_block):
    providers_block["block"] = _block(_signed_in("openrouter"))
    registry = FakeRegistrySource()
    composite = CompositeConnectionSource(registry, ai_source)
    assert composite.get("spotify") == "plugin:spotify"
    assert composite.get("ai.or1").kind == "ai"
    assert composite.get("ai.spotify") is None
    assert len(composite.all()) == 2
    assert composite.id_for(object()) == "spotify"
    composite.invalidate("ai.or1")
    composite.invalidate("spotify")
    assert registry.invalidated == ["spotify"]


def test_removing_a_provider_or_its_sign_in_forgets_its_tokens():
    fake = FakeOAuth()
    before = _block(
        _signed_in("openrouter", pid="a"), _signed_in("openrouter", pid="b"), _signed_in("huggingface", pid="c")
    )
    after = _block(_signed_in("huggingface", pid="c"), {"id": "b", "name": "B", "api_key": "test_key"})
    forget_removed_providers(before, after, service=fake)
    assert sorted(fake.forgotten) == ["ai.a", "ai.b"]


def test_switching_a_provider_to_another_sign_in_preset_forgets_its_tokens():
    fake = FakeOAuth()
    before = _block(_signed_in("openrouter", pid="p1"), _signed_in("huggingface", pid="p2"))
    after = _block(_signed_in("huggingface", pid="p1"), _signed_in("huggingface", pid="p2"))
    forget_removed_providers(before, after, service=fake)
    assert fake.forgotten == ["ai.p1"]


# ── presets through the real OAuth service ──────────────────────────────────


def test_openrouter_sign_in_needs_no_client_id_and_stores_the_key(service, providers_block, transport, http):
    providers_block["block"] = _block(_signed_in("openrouter"))
    start = service.start("ai.or1", board_url=BOARD)
    assert start.flow == "key_exchange"
    assert start.authorization_url.startswith("https://openrouter.ai/auth?")
    http.replies.append((200, {"key": "test_or_key"}))
    status = service.complete_pasted(
        "ai.or1", f"{BOARD}/?code=test_code&state={_query(start.authorization_url)['state']}"
    )
    assert status.status == "connected"
    assert status.kind == "ai"
    assert service.get_access_token("ai.or1") == "test_or_key"


def test_openrouter_sign_in_finishes_from_a_pasted_address_without_state(service, providers_block, http):
    # If OpenRouter returns without state the relay cannot route back; the
    # paste box must still finish it (PKCE binds the code to this start).
    providers_block["block"] = _block(_signed_in("openrouter"))
    service.start("ai.or1", board_url=BOARD)
    http.replies.append((200, {"key": "test_or_key"}))
    status = service.complete_pasted("ai.or1", "https://fiestaboard.app/auth/oauth/redirect?code=test_code")
    assert status.status == "connected"


def test_huggingface_sign_in_uses_the_hosted_client_id_and_inference_scope(service, providers_block):
    providers_block["block"] = _block(_signed_in("huggingface", pid="hf"))
    query = _query(service.start("ai.hf", board_url=BOARD).authorization_url)
    assert query["client_id"] == "https://fiestaboard.app/auth/clients/huggingface.json"
    assert query["scope"] == "inference-api"
    assert query["redirect_uri"] == "https://relay.example/oauth/redirect"


def _chatgpt_start(service, providers_block):
    providers_block["block"] = _block(_signed_in("openai_chatgpt", pid="gpt"))
    return service.start("ai.gpt", board_url=BOARD)


def test_chatgpt_start_uses_the_loopback_redirect_and_asks_for_a_paste(service, providers_block):
    start = _chatgpt_start(service, providers_block)
    query = _query(start.authorization_url)
    assert start.authorization_url.startswith("https://auth.openai.com/api/accounts/authorize?")
    assert start.paste_expected is True
    assert query["redirect_uri"] == "http://127.0.0.1:1455/auth/callback"
    assert query["client_id"] == "dynamic_agent_client"
    assert query["agent_name_hint"] == "FiestaBoard"
    assert query["ext_agent_host_id"] == f"urn:uuid:{HOST_ID}"
    assert query["resource"] == "https://api.openai.com/v1"
    assert query["scope"] == "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
    assert query["code_challenge_method"] == "S256"


def test_chatgpt_start_works_without_a_board_url(service, providers_block):
    providers_block["block"] = _block(_signed_in("openai_chatgpt", pid="gpt"))
    assert service.start("ai.gpt").paste_expected is True


def _chatgpt_connect(service, providers_block, transport):
    start = _chatgpt_start(service, providers_block)
    state = _query(start.authorization_url)["state"]
    transport.reply(
        {"access_token": "test_at", "refresh_token": "test_rt", "expires_in": 3600, "id_token": "test_id_token"}
    )
    pasted = f"http://127.0.0.1:1455/auth/callback?code=test_code&state={state}&client_id=oaiapp_test"
    return service.complete_pasted("ai.gpt", pasted)


def test_chatgpt_paste_exchanges_with_the_issued_client_and_resource(service, providers_block, transport):
    assert _chatgpt_connect(service, providers_block, transport).status == "connected"
    url, form = transport.calls[0]
    assert url == "https://auth.openai.com/api/accounts/oauth/token"
    assert form["client_id"] == "oaiapp_test"
    assert form["resource"] == "https://api.openai.com/v1"
    assert form["redirect_uri"] == "http://127.0.0.1:1455/auth/callback"


def test_chatgpt_refresh_uses_the_issued_client(service, providers_block, transport, tmp_path):
    _chatgpt_connect(service, providers_block, transport)
    tokens = service._store.get("ai.gpt")
    assert tokens.client_id == "oaiapp_test"
    service._store.put("ai.gpt", TokenSet(**{**tokens.__dict__, "expires_at": NOW - 1}))
    transport.reply({"access_token": "test_at2", "expires_in": 3600})
    assert service.get_access_token("ai.gpt") == "test_at2"
    assert transport.calls[1][1]["client_id"] == "oaiapp_test"


def test_chatgpt_id_token_is_never_stored(service, providers_block, transport, tmp_path):
    _chatgpt_connect(service, providers_block, transport)
    assert "test_id_token" not in (tmp_path / "oauth_tokens.json").read_text()


def test_chatgpt_sign_in_again_reuses_the_issued_client(service, providers_block, transport):
    _chatgpt_connect(service, providers_block, transport)
    query = _query(service.start("ai.gpt").authorization_url)
    assert query["client_id"] == "oaiapp_test"
    assert "agent_name_hint" not in query


def test_chatgpt_sign_in_again_keeps_the_issued_client_when_none_is_sent_back(service, providers_block, transport):
    _chatgpt_connect(service, providers_block, transport)
    state = _query(service.start("ai.gpt").authorization_url)["state"]
    transport.reply({"access_token": "test_at2", "refresh_token": "test_rt2", "expires_in": 3600})
    # OpenAI only names the client when it issues one (the first sign-in).
    service.complete_pasted("ai.gpt", f"http://127.0.0.1:1455/auth/callback?code=test_code2&state={state}")
    assert transport.calls[1][1]["client_id"] == "oaiapp_test"
    assert service._store.get("ai.gpt").client_id == "oaiapp_test"


# ── Sign in with ChatGPT through FiestaBoard's registered OpenAI app ───────

REGISTERED = "app_test_registered"


@pytest.fixture
def registered(monkeypatch):
    """FiestaBoard's OpenAI app approved: the constant holds its public client ID."""
    monkeypatch.delenv("FIESTABOARD_OPENAI_CLIENT_ID", raising=False)
    monkeypatch.setattr(sign_in, "OPENAI_REGISTERED_CLIENT_ID", REGISTERED)
    return REGISTERED


def test_chatgpt_without_a_registered_client_keeps_the_paste_flow(service, providers_block, monkeypatch):
    monkeypatch.delenv("FIESTABOARD_OPENAI_CLIENT_ID", raising=False)
    assert sign_in.OPENAI_REGISTERED_CLIENT_ID == ""
    assert sign_in.openai_registered_client_id() == ""
    start = _chatgpt_start(service, providers_block)
    assert start.paste_expected is True
    assert _query(start.authorization_url)["client_id"] == "dynamic_agent_client"
    assert service.get_connection("ai.gpt").paste_expected is True


def test_chatgpt_with_a_registered_client_comes_back_through_the_relay(service, providers_block, registered):
    start = _chatgpt_start(service, providers_block)
    query = _query(start.authorization_url)
    assert start.authorization_url.startswith("https://auth.openai.com/api/accounts/authorize?")
    assert start.paste_expected is False
    assert start.paste_hint == ""
    assert query["client_id"] == REGISTERED
    assert query["redirect_uri"] == "https://relay.example/oauth/redirect"
    assert query["resource"] == "https://api.openai.com/v1"
    assert query["scope"] == "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
    assert query["code_challenge_method"] == "S256"
    # The dynamic-client hints belong to the fallback only.
    assert "agent_name_hint" not in query
    assert "ext_agent_host_id" not in query


def test_chatgpt_with_a_registered_client_is_not_a_paste_connection(service, providers_block, registered):
    providers_block["block"] = _block(_signed_in("openai_chatgpt", pid="gpt"))
    status = service.get_connection("ai.gpt")
    assert status.paste_expected is False
    assert status.configured is True


def _chatgpt_registered_connect(service, providers_block, transport):
    start = _chatgpt_start(service, providers_block)
    state = _query(start.authorization_url)["state"]
    transport.reply({"access_token": "test_at", "refresh_token": "test_rt", "expires_in": 3600})
    return service.complete_authorization(state=state, code="test_code", error=None)


def test_chatgpt_registered_relay_exchanges_with_the_registered_client(service, providers_block, transport, registered):
    outcome = _chatgpt_registered_connect(service, providers_block, transport)
    assert outcome.connected is True
    assert outcome.connection_id == "ai.gpt"
    assert service.get_connection("ai.gpt").status == "connected"
    url, form = transport.calls[0]
    assert url == "https://auth.openai.com/api/accounts/oauth/token"
    assert form["client_id"] == REGISTERED
    assert form["redirect_uri"] == "https://relay.example/oauth/redirect"
    assert form["resource"] == "https://api.openai.com/v1"


def test_chatgpt_registered_refresh_and_sign_in_again_use_the_registered_client(
    service, providers_block, transport, registered
):
    _chatgpt_registered_connect(service, providers_block, transport)
    tokens = service._store.get("ai.gpt")
    service._store.put("ai.gpt", TokenSet(**{**tokens.__dict__, "expires_at": NOW - 1}))
    transport.reply({"access_token": "test_at2", "expires_in": 3600})
    assert service.get_access_token("ai.gpt") == "test_at2"
    assert transport.calls[1][1]["client_id"] == REGISTERED
    assert _query(service.start("ai.gpt", board_url=BOARD).authorization_url)["client_id"] == REGISTERED


def test_chatgpt_registered_client_ignores_a_client_id_in_the_redirect(service, providers_block, transport, registered):
    """No dynamic clients once registered: a client_id coming back is never adopted."""
    start = _chatgpt_start(service, providers_block)
    state = _query(start.authorization_url)["state"]
    transport.reply({"access_token": "test_at", "refresh_token": "test_rt", "expires_in": 3600})
    service.complete_pasted("ai.gpt", f"https://relay.example/oauth/redirect?code=c&state={state}&client_id=oaiapp_x")
    assert transport.calls[0][1]["client_id"] == REGISTERED
    assert service._store.get("ai.gpt").client_id in ("", REGISTERED)


def test_the_env_var_overrides_the_registered_client(service, providers_block, monkeypatch):
    monkeypatch.setattr(sign_in, "OPENAI_REGISTERED_CLIENT_ID", "")
    monkeypatch.setenv("FIESTABOARD_OPENAI_CLIENT_ID", "  app_test_from_env  ")
    assert sign_in.openai_registered_client_id() == "app_test_from_env"
    start = _chatgpt_start(service, providers_block)
    query = _query(start.authorization_url)
    assert start.paste_expected is False
    assert query["client_id"] == "app_test_from_env"
    assert query["redirect_uri"] == "https://relay.example/oauth/redirect"


def test_the_env_var_wins_over_the_constant(monkeypatch):
    monkeypatch.setattr(sign_in, "OPENAI_REGISTERED_CLIENT_ID", REGISTERED)
    monkeypatch.setenv("FIESTABOARD_OPENAI_CLIENT_ID", "app_test_from_env")
    assert sign_in.openai_registered_client_id() == "app_test_from_env"


def test_a_blank_env_var_falls_back_to_the_constant(monkeypatch):
    monkeypatch.setattr(sign_in, "OPENAI_REGISTERED_CLIENT_ID", REGISTERED)
    monkeypatch.setenv("FIESTABOARD_OPENAI_CLIENT_ID", "   ")
    assert sign_in.openai_registered_client_id() == REGISTERED


def test_ai_connection_status_reports_kind_ai(service, providers_block):
    providers_block["block"] = _block(_signed_in("openrouter"))
    assert [c.kind for c in service.list_connections()] == ["ai"]


def test_presets_have_the_documented_protocols():
    assert PRESETS["openrouter"].protocol == "openai"
    assert PRESETS["huggingface"].base_url == "https://router.huggingface.co/v1"
    assert PRESETS["openai_chatgpt"].protocol == "openai_responses"


def test_agent_host_id_is_created_once_and_private(tmp_path):
    first = sign_in.load_agent_host_id(tmp_path)
    assert sign_in.load_agent_host_id(tmp_path) == first
    assert (tmp_path / ".oauth_agent_host_id").stat().st_mode & 0o777 == 0o600


# ── request time: one-shot generator ────────────────────────────────────────


def _capture(status: int = 200, body: dict | None = None):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body or {"choices": [{"message": {"content": "ok"}}]})

    return seen, httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_api_key_request_is_unchanged(monkeypatch):
    fake = FakeOAuth()
    monkeypatch.setattr(sign_in, "_oauth", lambda: fake)
    seen, client = _capture()
    payload = {"model": "test-model", "messages": []}
    async with client:
        await _post_chat_completion(dict(API_KEY_PROVIDER), payload, client=client)
    assert str(seen[0].url) == "https://example.test/v1/chat/completions"
    assert seen[0].headers["authorization"] == "Bearer test_key"
    assert json.loads(seen[0].content) == payload
    assert fake.asked == [] and fake.rejected == []


@pytest.mark.asyncio
async def test_signed_in_request_sends_the_token(monkeypatch):
    monkeypatch.setattr(sign_in, "_oauth", lambda: FakeOAuth(token="test_token"))
    seen, client = _capture()
    async with client:
        await _post_chat_completion(_signed_in("openrouter", api_key="test_pasted"), {"model": "m"}, client=client)
    assert str(seen[0].url) == "https://openrouter.ai/api/v1/chat/completions"
    assert seen[0].headers["authorization"] == "Bearer test_token"


@pytest.mark.asyncio
async def test_signed_in_401_reports_the_token_rejected(monkeypatch):
    fake = FakeOAuth()
    monkeypatch.setattr(sign_in, "_oauth", lambda: fake)
    _, client = _capture(401, {"error": {"message": "bad token"}})
    async with client:
        with pytest.raises(AIGenerationError):
            await _post_chat_completion(_signed_in("openrouter"), {"model": "m"}, client=client)
    assert fake.rejected == ["ai.or1"]
    assert fake.rejected_tokens == ["test_token"]


@pytest.mark.asyncio
async def test_a_draft_pointed_at_another_host_sends_nothing_and_reports_nothing(monkeypatch):
    fake = FakeOAuth()
    monkeypatch.setattr(sign_in, "_oauth", lambda: fake)
    seen, client = _capture(401, {"error": {"message": "bad token"}})
    async with client:
        with pytest.raises(AIGenerationError):
            await _post_chat_completion(
                _signed_in("openrouter", base_url="https://example.test/v1"), {"model": "m"}, client=client
            )
    assert seen == [] and fake.asked == [] and fake.rejected == []


@pytest.mark.asyncio
async def test_api_key_401_reports_nothing(monkeypatch):
    fake = FakeOAuth()
    monkeypatch.setattr(sign_in, "_oauth", lambda: fake)
    _, client = _capture(401, {"error": {"message": "bad key"}})
    async with client:
        with pytest.raises(AIGenerationError):
            await _post_chat_completion(dict(API_KEY_PROVIDER), {"model": "m"}, client=client)
    assert fake.rejected == []


@pytest.mark.asyncio
async def test_signed_out_generator_call_raises_before_any_request(monkeypatch):
    monkeypatch.setattr(sign_in, "_oauth", lambda: FakeOAuth(token=None))
    seen, client = _capture()
    async with client:
        with pytest.raises(AIGenerationError, match="Sign in"):
            await _post_chat_completion(_signed_in("openrouter"), {"model": "m"}, client=client)
    assert seen == []


# ── request time: FiestaBot chat stream ─────────────────────────────────────


async def _chat(provider: dict[str, Any], status: int = 200) -> tuple[list[httpx.Request], list[dict]]:
    from src.ai.chat import _FenceParser, stream_model
    from src.ai.protocols import get_protocol

    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "test_denied"}})
        return httpx.Response(200, content=b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\ndata: [DONE]\n\n')

    usage = {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        events = [
            e
            async for e in stream_model(
                protocol=get_protocol(provider.get("protocol")),
                provider=provider,
                model="test-model",
                messages=[{"role": "user", "content": "hi"}],
                parser=_FenceParser(lambda payload: payload),
                usage=usage,
                client=client,
            )
        ]
    return seen, events


@pytest.mark.asyncio
async def test_chat_stream_sends_the_signed_in_token(monkeypatch):
    monkeypatch.setattr(sign_in, "_oauth", lambda: FakeOAuth(token="test_token"))
    seen, _ = await _chat(_signed_in("openrouter"))
    assert seen[0].headers["authorization"] == "Bearer test_token"
    assert str(seen[0].url) == "https://openrouter.ai/api/v1/chat/completions"


@pytest.mark.asyncio
async def test_chat_stream_api_key_provider_is_unchanged(monkeypatch):
    fake = FakeOAuth()
    monkeypatch.setattr(sign_in, "_oauth", lambda: fake)
    seen, events = await _chat(dict(API_KEY_PROVIDER))
    assert seen[0].headers["authorization"] == "Bearer test_key"
    assert [e["data"]["delta"] for e in events if e["event"] == "text"] == ["hi"]
    assert fake.asked == []


@pytest.mark.asyncio
async def test_chat_stream_401_reports_the_token_rejected(monkeypatch):
    fake = FakeOAuth()
    monkeypatch.setattr(sign_in, "_oauth", lambda: fake)
    _, events = await _chat(_signed_in("openrouter"), status=401)
    assert events[-1]["event"] == "error"
    assert fake.rejected == ["ai.or1"]
    assert fake.rejected_tokens == ["test_token"]


@pytest.mark.asyncio
async def test_chat_stream_signed_out_is_an_error_without_a_request(monkeypatch):
    monkeypatch.setattr(sign_in, "_oauth", lambda: FakeOAuth(token=None))
    seen, events = await _chat(_signed_in("openrouter"))
    assert seen == []
    assert "Sign in to Router again" in events[-1]["data"]["message"]


# ── Model list (GET /settings/ai/providers/{id}/models) ─────────────────────


def _models_client(status: int, body: Any):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body)

    return seen, httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_model_list_uses_the_signed_in_token_and_keeps_listed_models(monkeypatch):
    from src.ai.generator import list_models

    monkeypatch.setattr(sign_in, "_oauth", lambda: FakeOAuth())
    body = {
        "data": [
            {"slug": "gpt-test", "display_name": "GPT Test", "visibility": "list"},
            {"slug": "gpt-hidden", "display_name": "Hidden", "visibility": "hide"},
            {"id": "plain-model"},
        ]
    }
    seen, client = _models_client(200, body)
    async with client:
        models = await list_models(_signed_in("openai_chatgpt"), client=client)
    assert str(seen[0].url) == "https://api.openai.com/v1/models"
    assert seen[0].headers["authorization"] == "Bearer test_token"
    assert models == [{"id": "gpt-test", "name": "GPT Test"}, {"id": "plain-model", "name": "plain-model"}]


@pytest.mark.asyncio
async def test_model_list_works_for_an_api_key_provider():
    from src.ai.generator import list_models

    seen, client = _models_client(200, {"data": [{"id": "m1"}]})
    async with client:
        models = await list_models(API_KEY_PROVIDER, client=client)
    assert str(seen[0].url) == "https://example.test/v1/models"
    assert seen[0].headers["authorization"] == "Bearer test_key"
    assert models == [{"id": "m1", "name": "m1"}]


@pytest.mark.asyncio
async def test_model_list_401_reports_the_sign_in_rejected(monkeypatch):
    from src.ai.generator import list_models

    fake = FakeOAuth()
    monkeypatch.setattr(sign_in, "_oauth", lambda: fake)
    _, client = _models_client(401, {"error": {"message": "bad"}})
    async with client:
        with pytest.raises(AIGenerationError):
            await list_models(_signed_in("openai_chatgpt"), client=client)
    assert fake.rejected == ["ai.or1"]


@pytest.mark.asyncio
async def test_model_list_rejects_an_unexpected_body():
    from src.ai.generator import list_models

    _, client = _models_client(200, {"nope": True})
    async with client:
        with pytest.raises(AIGenerationError):
            await list_models(API_KEY_PROVIDER, client=client)
