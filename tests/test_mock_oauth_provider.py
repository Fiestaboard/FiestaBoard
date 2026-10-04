"""scripts/mock_oauth_provider.py: every flow core speaks, served locally.

The mock runs on a loopback port in a thread; requests talk to it over HTTP
the way a board would.
"""

import base64
import hashlib
import importlib.util
import json
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "mock_oauth_provider.py"


def _load():
    spec = importlib.util.spec_from_file_location("mock_oauth_provider", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def base():
    mock = _load()
    server = mock.ThreadingHTTPServer(("127.0.0.1", 0), mock.make_handler(mock.Provider(60), 0))
    port = server.server_address[1]
    server.RequestHandlerClass = mock.make_handler(mock.Provider(60), port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


VERIFIER = "v" * 50
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b"=").decode()


def _redirect_query(response):
    assert response.status_code == 302
    return {k: v[0] for k, v in parse_qs(urlsplit(response.headers["Location"]).query).items()}


def _authorize(base, path="/authorize", client_id="test_client", **extra):
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": "https://relay.example/redirect",
        "state": "s1",
        "code_challenge": CHALLENGE,
        "code_challenge_method": "S256",
        **extra,
    }
    return requests.get(f"{base}{path}", params=params, allow_redirects=False, timeout=5)


def _exchange(base, code, path="/token", client_id="test_client", **kwargs):
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": "https://relay.example/redirect",
        "client_id": client_id,
        "code_verifier": VERIFIER,
    }
    return requests.post(f"{base}{path}", data=form, timeout=5, **kwargs)


# ── key_exchange (OpenRouter) ───────────────────────────────────────────────


def test_key_exchange_redirects_to_the_callback_and_trades_the_code_for_a_key(base):
    response = requests.get(
        f"{base}/auth",
        params={
            "callback_url": "https://relay.example/cb",
            "code_challenge": CHALLENGE,
            "code_challenge_method": "S256",
            "state": "s1",
        },
        allow_redirects=False,
        timeout=5,
    )
    query = _redirect_query(response)
    assert query["state"] == "s1"
    keys = requests.post(
        f"{base}/api/v1/auth/keys",
        json={"code": query["code"], "code_verifier": VERIFIER, "code_challenge_method": "S256"},
        timeout=5,
    )
    assert keys.status_code == 200
    assert keys.json()["key"].startswith("sk-or-mock-")


def test_key_exchange_without_a_callback_shows_the_code(base):
    response = requests.get(
        f"{base}/auth", params={"code_challenge": CHALLENGE, "code_challenge_method": "S256"}, timeout=5
    )
    assert response.status_code == 200
    code = response.json()["code"]
    bad = requests.post(f"{base}/api/v1/auth/keys", json={"code": code, "code_verifier": "wrong" * 10}, timeout=5)
    assert bad.status_code == 400
    assert isinstance(bad.json()["error"], dict)


# ── plex_pin ────────────────────────────────────────────────────────────────


def test_a_plex_pin_gets_a_token_once_approved(base):
    headers = {"Accept": "application/json", "X-Plex-Client-Identifier": "test-install", "X-Plex-Product": "FB"}
    pin = requests.post(f"{base}/api/v2/pins?strong=true", headers=headers, timeout=5).json()
    assert pin["code"] and pin["expiresIn"] > 0
    assert requests.get(f"{base}/api/v2/pins/{pin['id']}", headers=headers, timeout=5).json()["authToken"] is None
    page = requests.get(f"{base}/plex/auth", timeout=5)
    assert page.status_code == 200 and "location.hash" in page.text
    assert requests.get(f"{base}/plex/approve", params={"code": pin["code"]}, timeout=5).status_code == 200
    assert requests.get(f"{base}/api/v2/pins/{pin['id']}", headers=headers, timeout=5).json()["authToken"]
    assert requests.get(f"{base}/api/v2/pins/999999", headers=headers, timeout=5).status_code == 404


# ── Home Assistant, Hugging Face and ChatGPT paths ──────────────────────────


@pytest.mark.parametrize(
    ("authorize", "token"),
    [("/auth/authorize", "/auth/token"), ("/oauth/authorize", "/oauth/token")],
)
def test_provider_style_paths_run_the_standard_flow(base, authorize, token):
    code = _redirect_query(_authorize(base, authorize))["code"]
    answer = _exchange(base, code, token)
    assert answer.status_code == 200
    assert answer.json()["access_token"]


def test_chatgpt_issues_a_client_during_sign_in(base):
    query = _redirect_query(_authorize(base, "/api/accounts/authorize", client_id="dynamic_agent_client"))
    issued = query["client_id"]
    assert issued.startswith("oaiapp_mock_")
    answer = _exchange(base, query["code"], "/api/accounts/oauth/token", client_id=issued)
    assert answer.status_code == 200


def test_the_token_endpoint_accepts_http_basic_client_auth(base):
    code = _redirect_query(_authorize(base))["code"]
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": "https://relay.example/redirect",
        "code_verifier": VERIFIER,
    }
    answer = requests.post(f"{base}/token", data=form, auth=("test_client", "test_secret"), timeout=5)
    assert answer.status_code == 200


# ── OpenAI Responses and model list ─────────────────────────────────────────


def _token(base):
    code = _redirect_query(_authorize(base))["code"]
    return _exchange(base, code).json()["access_token"]


def test_responses_streams_text_deltas_then_completed(base):
    token = _token(base)
    response = requests.post(
        f"{base}/v1/responses",
        headers={"Authorization": f"Bearer {token}"},
        json={"model": "mock-gpt", "input": [{"role": "user", "content": "hi"}], "stream": True},
        stream=True,
        timeout=5,
    )
    assert response.headers["Content-Type"].startswith("text/event-stream")
    events = [json.loads(line[6:]) for line in response.iter_lines(decode_unicode=True) if line.startswith("data: ")]
    kinds = [event["type"] for event in events]
    assert kinds[0] == "response.created" and kinds[-1] == "response.completed"
    assert "".join(e["delta"] for e in events if e["type"] == "response.output_text.delta")
    assert events[-1]["response"]["usage"]["output_tokens"] > 0


def test_responses_needs_a_live_token(base):
    response = requests.post(f"{base}/v1/responses", json={"stream": True}, timeout=5)
    assert response.status_code == 401


def test_models_lists_visible_and_hidden_entries(base):
    body = requests.get(f"{base}/v1/models", headers={"Authorization": f"Bearer {_token(base)}"}, timeout=5).json()
    assert {m["visibility"] for m in body["data"]} == {"list", "hide"}


def test_chat_completions_answer_with_an_openrouter_key(base):
    code = requests.get(
        f"{base}/auth", params={"code_challenge": CHALLENGE, "code_challenge_method": "S256"}, timeout=5
    ).json()["code"]
    key = requests.post(f"{base}/api/v1/auth/keys", json={"code": code, "code_verifier": VERIFIER}, timeout=5).json()[
        "key"
    ]
    response = requests.post(
        f"{base}/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
        timeout=5,
    )
    assert response.json()["choices"][0]["message"]["content"]


# ── Core against the mock, over real HTTP ───────────────────────────────────


class _Source:
    def __init__(self, target):
        self.target = target

    def get(self, connection_id):
        return self.target if connection_id == self.target.connection_id else None

    def all(self):
        return [self.target]

    def id_for(self, plugin):
        return None

    def invalidate(self, connection_id):
        pass


def _service(tmp_path, target):
    from src.oauth.service import OAuthService
    from src.oauth.state import StateSigner
    from src.oauth.tokens import TokenStore

    return OAuthService(
        source=_Source(target),
        store=TokenStore(tmp_path / "tokens.json"),
        signer=StateSigner(b"k" * 32),
        redirect_uri="https://relay.example/redirect",
        poll_in_background=False,
        plex_client_identifier=lambda: "test-install",
    )


def _target(connection_id, block, config):
    from src.oauth.provider import parse_provider_block
    from src.oauth.service import ConnectionTarget

    return ConnectionTarget(
        connection_id=connection_id,
        plugin_id=connection_id,
        instance_label=None,
        plugin_name=connection_id,
        provider=parse_provider_block(block, connection_id),
        config=config,
    )


def test_core_signs_in_to_a_home_assistant_style_mock_with_basic_auth_and_refreshes(base, tmp_path):
    block = {
        "flows": ["relay"],
        "endpoint_base_setting": "base_url",
        "authorization_url": "/auth/authorize",
        "token_url": "/auth/token",
        "client_secret_setting": "client_secret",
        "token_auth_method": "basic",
        "refresh_params": {"scope": "offline"},
    }
    config = {"base_url": base, "client_id": "test_client", "client_secret": "test_secret"}
    service = _service(tmp_path, _target("ha", block, config))
    start = service.start("ha", board_url="http://192.168.1.50:4420")
    query = _redirect_query(requests.get(start.authorization_url, allow_redirects=False, timeout=5))
    assert service.complete_authorization(state=query["state"], code=query["code"], error=None).connected
    first = service.get_access_token("ha")
    assert requests.get(f"{base}/me", headers={"Authorization": f"Bearer {first}"}, timeout=5).status_code == 200
    assert service.report_rejected("ha") not in (None, first), "a forced refresh gets a rotated token"


def test_core_plex_pin_against_the_mock(base, tmp_path, monkeypatch):
    monkeypatch.setenv(
        "FIESTABOARD_OAUTH_URL_OVERRIDES", json.dumps({"https://plex.tv": base, "https://app.plex.tv": f"{base}/plex"})
    )
    service = _service(tmp_path, _target("plex", {"flows": ["plex_pin"]}, {}))
    start = service.start("plex", board_url="http://192.168.1.50:4420")
    assert start.authorization_url.startswith(f"{base}/plex/auth#?")
    code = parse_qs(start.authorization_url.split("#?", 1)[1])["code"][0]
    assert service.poll_device("plex") is True
    requests.get(f"{base}/plex/approve", params={"code": code}, timeout=5)
    assert service.poll_device("plex") is False
    assert service.get_access_token("plex").startswith("plex-mock-")


def test_core_openrouter_key_exchange_against_the_mock(base, tmp_path, monkeypatch):
    from src.ai.sign_in import PRESETS
    from src.oauth.service import ConnectionTarget

    monkeypatch.setenv("FIESTABOARD_OAUTH_URL_OVERRIDES", json.dumps({"https://openrouter.ai": base}))
    target = ConnectionTarget(
        connection_id="ai.or1",
        plugin_id="ai",
        instance_label=None,
        plugin_name="OpenRouter",
        provider=PRESETS["openrouter"].provider,
        kind="ai",
    )
    service = _service(tmp_path, target)
    start = service.start("ai.or1", headless=True)
    shown = requests.get(start.authorization_url, timeout=5).json()["code"]
    service.complete_pasted("ai.or1", shown)
    assert service.get_access_token("ai.or1").startswith("sk-or-mock-")


# ── Sign in with ChatGPT: the loopback redirect, finished by paste ──────────


def _chatgpt_board(base, tmp_path, monkeypatch):
    """A board whose one AI provider signs in with ChatGPT, its OpenAI hosts pointed at the mock."""
    from fastapi.testclient import TestClient

    from src.ai.sign_in import AiProviderConnectionSource
    from src.api_server import app
    from src.oauth.service import OAuthService
    from src.oauth.state import StateSigner
    from src.oauth.tokens import TokenStore

    monkeypatch.setenv(
        "FIESTABOARD_OAUTH_URL_OVERRIDES",
        json.dumps({"https://auth.openai.com": base, "https://api.openai.com": base}),
    )
    providers = {
        "providers": [
            {"id": "gpt", "name": "ChatGPT", "sign_in": {"preset": "openai_chatgpt"}},
            {"id": "hf", "name": "Hugging Face", "sign_in": {"preset": "huggingface"}},
        ]
    }
    service = OAuthService(
        source=AiProviderConnectionSource(
            providers=lambda: providers, agent_host_id=lambda: "00000000-0000-4000-8000-000000000000"
        ),
        store=TokenStore(tmp_path / "tokens.json"),
        signer=StateSigner(b"k" * 32),
        redirect_uri="https://relay.example/redirect",
        poll_in_background=False,
    )
    monkeypatch.setattr("src.oauth.routes.get_oauth_service", lambda: service)
    return service, TestClient(app)


def test_chatgpt_tells_the_ui_before_it_starts_that_the_sign_in_ends_by_paste(base, tmp_path, monkeypatch):
    _, client = _chatgpt_board(base, tmp_path, monkeypatch)
    connections = {c["id"]: c for c in client.get("/oauth/connections").json()["connections"]}
    # Known up front, so the UI can open the provider in a new tab from the click itself.
    assert connections["ai.gpt"]["paste_expected"] is True
    # A provider that comes back by way of the relay does not.
    assert connections["ai.hf"]["paste_expected"] is False


def test_core_chatgpt_sign_in_finishes_from_the_pasted_loopback_address(base, tmp_path, monkeypatch):
    """The reported dead end: the browser lands on 127.0.0.1:1455, which never loads; pasting it signs in."""
    service, client = _chatgpt_board(base, tmp_path, monkeypatch)

    start = client.post("/oauth/connections/ai.gpt/authorize", json={"board_url": "http://192.168.1.50:4420"})
    assert start.status_code == 200
    assert start.json()["paste_expected"] is True

    # What the browser is sent to after approving: OpenAI's loopback-only redirect.
    landed = requests.get(start.json()["authorization_url"], allow_redirects=False, timeout=5).headers["Location"]
    assert landed.startswith("http://127.0.0.1:1455/auth/callback?code=")
    assert "client_id=oaiapp_mock_" in landed

    done = client.post("/oauth/connections/ai.gpt/complete", json={"pasted": landed})
    assert done.status_code == 200
    assert done.json()["status"] == "connected"
    token = service.get_access_token("ai.gpt")
    assert requests.get(f"{base}/v1/models", headers={"Authorization": f"Bearer {token}"}, timeout=5).status_code == 200
