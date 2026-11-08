"""Native HTTP request sequences against the real session and OAuth routes.

The prefix adapter models nginx's path stripping only. It is deliberately not
evidence of Home Assistant ingress authentication or a real reverse proxy.
Provider transport is the deterministic fixture used by the OAuth route suite.
These pin existing behavior; no native authentication bypass is introduced.
"""

from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.auth import routes as auth_routes
from src.auth import service as auth_service
from src.auth.service import SESSION_COOKIE_NAME
from tests.test_oauth_routes import provider, registry, service  # noqa: F401


class StripAPIPath:
    """Test-only counterpart of the reverse proxy's API path rewrite."""

    def __init__(self, application, prefix):
        self.application = application
        self.prefix = prefix

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            assert scope["path"].startswith(self.prefix + "/")
            scope = dict(scope)
            scope["path"] = scope["path"][len(self.prefix) :]
            scope["raw_path"] = scope["path"].encode()
        await self.application(scope, receive, send)


@pytest.fixture(params=["/api", "/board/kitchen/api"])
def native(request, service, tmp_path, monkeypatch):  # noqa: F811 - imported pytest fixture
    auth = auth_service.AuthService(tmp_path / "native-auth.json")
    auth.create_initial_user("native-admin", "native-fixture-password")
    monkeypatch.setattr(auth_service, "_service", auth)
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "true")
    monkeypatch.delenv("FIESTABOARD_MCP_TOKEN", raising=False)
    monkeypatch.delenv("FIESTABOARD_CORS_ORIGINS", raising=False)
    auth_routes._FAILED_ATTEMPTS.clear()
    prefix = request.param
    client = TestClient(StripAPIPath(app, prefix), base_url="https://board.example", follow_redirects=False)
    yield client, prefix
    client.close()


def login(client, prefix):
    response = client.post(
        prefix + "/auth/login",
        json={"username": "native-admin", "password": "native-fixture-password", "remember_me": False},
    )
    assert response.status_code == 200, response.text
    assert client.cookies.get(SESSION_COOKIE_NAME)


def test_native_cookie_login_read_logout_and_copied_cookie_revocation(native):
    client, prefix = native
    assert client.get(prefix + "/v1/pages").status_code == 401
    login(client, prefix)
    assert client.get(prefix + "/auth/status").json()["authenticated"] is True
    assert client.get(prefix + "/v1/pages").status_code == 200
    assert client.get(prefix + "/oauth/connections").status_code == 200
    copied = client.cookies.get(SESSION_COOKIE_NAME)
    assert client.post(prefix + "/auth/logout").status_code == 200
    client.cookies.set(SESSION_COOKIE_NAME, copied)
    assert client.get(prefix + "/v1/pages").status_code == 401
    assert client.get(prefix + "/oauth/connections").status_code == 401


def test_native_session_management_requires_origin_and_current_session_csrf(native):
    client, prefix = native
    login(client, prefix)
    session_id = client.get(prefix + "/auth/sessions").json()["current_session_id"]
    nonce = client.get(prefix + "/auth/sessions/context").json()["csrf_token"]
    path = prefix + "/auth/sessions/" + session_id
    assert client.delete(path).status_code == 403
    assert client.delete(path, headers={"Origin": "https://board.example"}).status_code == 403
    assert (
        client.delete(path, headers={"Origin": "https://unrelated.example", "X-CSRF-Token": nonce}).status_code == 403
    )
    assert client.get(prefix + "/v1/pages").status_code == 200
    response = client.delete(path, headers={"Origin": "https://board.example", "X-CSRF-Token": nonce})
    assert response.status_code == 200, response.text
    assert client.get(prefix + "/v1/pages").status_code == 401


def test_native_oauth_manual_completion_poll_disconnect_and_replay(native, provider):  # noqa: F811
    client, prefix = native
    login(client, prefix)
    base = prefix + "/oauth/connections/music"
    started = client.post(base + "/authorize", json={"board_url": "https://board.example"})
    assert started.status_code == 200, started.text
    state = parse_qs(urlsplit(started.json()["authorization_url"]).query)["state"][0]
    pasted = "https://fiestaboard.app/auth/oauth/redirect?" + urlencode({"code": "fixture-code", "state": state})
    provider.replies.append((200, {"access_token": "native-provider-secret", "expires_in": 3600}))
    completed = client.post(base + "/complete", json={"pasted": pasted})
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "connected"
    assert "native-provider-secret" not in completed.text
    assert client.get(base).json()["status"] == "connected"
    assert client.post(base + "/complete", json={"pasted": pasted}).status_code == 400
    assert len(provider.calls) == 1
    assert client.delete(base).json()["status"] == "disconnected"
    assert client.get(base).json()["status"] == "disconnected"


@pytest.mark.parametrize(
    "method,suffix",
    [("GET", ""), ("GET", "/music"), ("POST", "/music/authorize"), ("POST", "/music/complete"), ("DELETE", "/music")],
)
def test_native_oauth_operations_remain_session_protected(native, method, suffix):
    client, prefix = native
    response = client.request(method, prefix + "/oauth/connections" + suffix, json={} if method == "POST" else None)
    assert response.status_code == 401
