"""Tests for the ``/auth/mcp-token`` admin endpoints.

Covers status, rotation, revocation, env-var override, and the
end-to-end "rotate a token → use it against /mcp/" path so we know
the UI's button maps to a token that the middleware actually accepts.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.auth import routes as auth_routes
from src.auth import service as auth_service


@pytest.fixture
def auth_dir(tmp_path, monkeypatch):
    fresh = auth_service.AuthService(auth_file=tmp_path / "auth.json")
    monkeypatch.setattr(auth_service, "_service", fresh)
    auth_routes._FAILED_ATTEMPTS.clear()
    yield tmp_path
    monkeypatch.setattr(auth_service, "_service", None)


@pytest.fixture
def client(auth_dir):
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "true")
    monkeypatch.delenv("FIESTABOARD_MCP_TOKEN", raising=False)
    yield
    monkeypatch.delenv("FIESTABOARD_AUTH_ENABLED", raising=False)


@pytest.fixture
def auth_disabled(monkeypatch):
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "false")
    monkeypatch.delenv("FIESTABOARD_MCP_TOKEN", raising=False)
    yield
    monkeypatch.delenv("FIESTABOARD_AUTH_ENABLED", raising=False)


@pytest.fixture
def signed_in(client, enabled):
    r = client.post("/auth/setup", json={"username": "admin", "password": "Password123!"})
    assert r.status_code in (200, 201), r.text
    # ``/auth/setup`` returns a fresh session cookie; subsequent requests
    # in this client will carry it.


# --- Status ----------------------------------------------------------------


def test_status_requires_auth(client, enabled):
    client.post("/auth/setup", json={"username": "admin", "password": "Password123!"})
    client.cookies.clear()
    r = client.get("/auth/mcp-token")
    assert r.status_code == 401


def test_status_reports_none_when_nothing_set(signed_in, client):
    r = client.get("/auth/mcp-token")
    assert r.status_code == 200
    body = r.json()
    assert body == {"configured": False, "source": "none"}


def test_status_reports_env_when_env_var_set(signed_in, client, monkeypatch):
    monkeypatch.setenv("FIESTABOARD_MCP_TOKEN", "from-env")
    r = client.get("/auth/mcp-token")
    body = r.json()
    assert body == {"configured": True, "source": "env"}


def test_status_reports_stored_when_rotated(signed_in, client):
    rotate = client.post("/auth/mcp-token")
    assert rotate.status_code == 201
    r = client.get("/auth/mcp-token")
    assert r.json() == {"configured": True, "source": "stored"}


# --- Rotate ---------------------------------------------------------------


def test_rotate_requires_auth(client, enabled):
    client.post("/auth/setup", json={"username": "admin", "password": "Password123!"})
    client.cookies.clear()
    r = client.post("/auth/mcp-token")
    assert r.status_code == 401


def test_rotate_returns_token_and_persists(signed_in, client):
    r = client.post("/auth/mcp-token")
    assert r.status_code == 201
    token = r.json()["token"]
    # secrets.token_urlsafe(32) -> 43 chars of url-safe base64. Defensive
    # bound check rather than exact length so we don't break if the helper
    # gets bumped to a longer entropy size.
    assert len(token) >= 32
    # Status now reports it's stored.
    s = client.get("/auth/mcp-token")
    assert s.json() == {"configured": True, "source": "stored"}


def test_rotate_replaces_previous_token(signed_in, client):
    a = client.post("/auth/mcp-token").json()["token"]
    b = client.post("/auth/mcp-token").json()["token"]
    assert a != b
    # The current stored token is the second one; the first must no
    # longer authenticate against /mcp/.
    r_old = client.get("/mcp/", headers={"Authorization": f"Bearer {a}"})
    assert r_old.status_code == 401
    r_new = client.get("/mcp/", headers={"Authorization": f"Bearer {b}"})
    assert r_new.status_code != 401


def test_rotate_blocked_when_env_var_pins_the_token(signed_in, client, monkeypatch):
    monkeypatch.setenv("FIESTABOARD_MCP_TOKEN", "pinned-by-ops")
    r = client.post("/auth/mcp-token")
    assert r.status_code == 409
    # And the env-managed token still wins.
    assert client.get("/auth/mcp-token").json()["source"] == "env"


# --- End-to-end: rotated token actually authenticates ---------------------


def test_rotated_token_passes_mcp_middleware(signed_in, client):
    token = client.post("/auth/mcp-token").json()["token"]
    # Fresh client without the admin session cookie so we're exercising
    # the bearer path, not riding on the rotation call's cookie.
    bare = TestClient(app, raise_server_exceptions=False)
    r = bare.get("/mcp/", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code != 401
    r_bad = bare.get("/mcp/", headers={"Authorization": "Bearer not-it"})
    assert r_bad.status_code == 401
    assert r_bad.headers.get("WWW-Authenticate", "").startswith("Bearer")


# --- Clear ----------------------------------------------------------------


def test_clear_requires_auth(client, enabled):
    client.post("/auth/setup", json={"username": "admin", "password": "Password123!"})
    client.cookies.clear()
    r = client.delete("/auth/mcp-token")
    assert r.status_code == 401


def test_clear_revokes_stored_token(signed_in, client):
    token = client.post("/auth/mcp-token").json()["token"]
    r = client.delete("/auth/mcp-token")
    assert r.status_code == 200
    assert client.get("/auth/mcp-token").json() == {"configured": False, "source": "none"}
    # Old token no longer accepted.
    bare = TestClient(app, raise_server_exceptions=False)
    r2 = bare.get("/mcp/", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 401


def test_clear_blocked_when_env_var_pins_the_token(signed_in, client, monkeypatch):
    monkeypatch.setenv("FIESTABOARD_MCP_TOKEN", "pinned-by-ops")
    r = client.delete("/auth/mcp-token")
    assert r.status_code == 409


# --- Auth-disabled mode (issues #857 / #1825) ------------------------------
#
# When the install opted out of login, there's no session cookie to send.
# While no token exists the mcp-token endpoints must still respond so
# Settings → Integrations can render — before the #857 fix these 401s
# triggered an infinite /login bounce. But once a token IS configured,
# managing it requires presenting the current token as a Bearer (#1825):
# with no session concept, possession of the credential is the credential.

# Obviously-fake token used to seed the store directly in tests.
FAKE_STORED_TOKEN = "test-stored-mcp-token-000000000000000000"


def _store_token():
    auth_service.get_auth_service().set_stored_mcp_token(FAKE_STORED_TOKEN)
    return FAKE_STORED_TOKEN


def test_status_accessible_when_auth_disabled(client, auth_disabled):
    r = client.get("/auth/mcp-token")
    assert r.status_code == 200
    assert r.json() == {"configured": False, "source": "none"}


def test_first_mint_open_when_auth_disabled(client, auth_disabled):
    # With no token configured the whole REST surface is already open, so
    # gating the first mint would protect nothing — it stays anonymous.
    r = client.post("/auth/mcp-token")
    assert r.status_code == 201
    token = r.json()["token"]
    assert len(token) >= 32
    bare = TestClient(app, raise_server_exceptions=False)
    assert bare.get("/mcp/", headers={"Authorization": f"Bearer {token}"}).status_code != 401
    # The mint is a one-shot: now that a token exists, an anonymous second
    # POST must be refused (#1825).
    assert client.post("/auth/mcp-token").status_code == 401


def test_clear_requires_current_token_when_auth_disabled(client, auth_disabled):
    # The previous version of this test ("test_clear_accessible_when_auth_
    # disabled") asserted the opposite: an anonymous DELETE was expected to
    # revoke a stored token. That encoded the vulnerability itself — anyone
    # who could reach the port could revoke the token and re-open /mcp/
    # outright (Fiestaboard/FiestaBoard#1825). Now revocation requires
    # presenting the current token.
    token = _store_token()
    r = client.delete("/auth/mcp-token")
    assert r.status_code == 401
    # The token is still stored and still enforced.
    assert auth_service.mcp_token_source() == "stored"
    # With the current token, revocation works…
    r2 = client.delete("/auth/mcp-token", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    # …and with no token configured, management is open again.
    assert client.get("/auth/mcp-token").json() == {
        "configured": False,
        "source": "none",
    }


def test_status_requires_token_when_auth_disabled_and_token_stored(client, auth_disabled):
    _store_token()
    r = client.get("/auth/mcp-token")
    assert r.status_code == 401
    assert r.headers.get("WWW-Authenticate", "").startswith("Bearer")


def test_rotate_requires_token_when_auth_disabled_and_token_stored(client, auth_disabled):
    _store_token()
    r = client.post("/auth/mcp-token")
    assert r.status_code == 401


def test_management_accepts_current_token_when_auth_disabled(client, auth_disabled):
    old = _store_token()
    headers = {"Authorization": f"Bearer {old}"}
    assert client.get("/auth/mcp-token", headers=headers).status_code == 200
    rotate = client.post("/auth/mcp-token", headers=headers)
    assert rotate.status_code == 201
    new = rotate.json()["token"]
    assert new != old
    # After rotation the OLD token no longer manages…
    assert client.get("/auth/mcp-token", headers=headers).status_code == 401
    # …and the NEW one does.
    new_headers = {"Authorization": f"Bearer {new}"}
    assert client.get("/auth/mcp-token", headers=new_headers).status_code == 200
    assert client.delete("/auth/mcp-token", headers=new_headers).status_code == 200


def test_wrong_bearer_rejected_when_auth_disabled(client, auth_disabled):
    _store_token()
    r = client.get(
        "/auth/mcp-token",
        headers={"Authorization": "Bearer test-not-the-right-token"},
    )
    assert r.status_code == 401


def test_env_pin_still_wins_when_auth_disabled(client, auth_disabled, monkeypatch):
    # An env-pinned token counts as "configured": the possession gate
    # applies first (anonymous callers get 401), and a caller holding the
    # env token still hits the 409 pin on mutation.
    monkeypatch.setenv("FIESTABOARD_MCP_TOKEN", "test-pinned-by-ops-token")
    assert client.post("/auth/mcp-token").status_code == 401
    headers = {"Authorization": "Bearer test-pinned-by-ops-token"}
    assert client.post("/auth/mcp-token", headers=headers).status_code == 409
    assert client.delete("/auth/mcp-token", headers=headers).status_code == 409
    # Status with the env token still reports the source.
    r = client.get("/auth/mcp-token", headers=headers)
    assert r.status_code == 200
    assert r.json() == {"configured": True, "source": "env"}


def test_undecided_mode_still_requires_auth(client, monkeypatch):
    monkeypatch.delenv("FIESTABOARD_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("FIESTABOARD_MCP_TOKEN", raising=False)
    assert client.get("/auth/mcp-token").status_code == 401
    assert client.post("/auth/mcp-token").status_code == 401
    assert client.delete("/auth/mcp-token").status_code == 401
