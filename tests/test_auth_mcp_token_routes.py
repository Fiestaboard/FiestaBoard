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


# --- Auth-disabled mode (issue #857) --------------------------------------
#
# When the install opted out of login, there's no session cookie to send.
# The mcp-token endpoints must still respond so Settings → Integrations can
# render. Before the fix these 401s triggered an infinite /login bounce.


def test_status_accessible_when_auth_disabled(client, auth_disabled):
    r = client.get("/auth/mcp-token")
    assert r.status_code == 200
    assert r.json() == {"configured": False, "source": "none"}


def test_rotate_accessible_when_auth_disabled(client, auth_disabled):
    r = client.post("/auth/mcp-token")
    assert r.status_code == 201
    token = r.json()["token"]
    assert len(token) >= 32
    assert client.get("/auth/mcp-token").json() == {
        "configured": True,
        "source": "stored",
    }
    bare = TestClient(app, raise_server_exceptions=False)
    assert bare.get("/mcp/", headers={"Authorization": f"Bearer {token}"}).status_code != 401


def test_clear_accessible_when_auth_disabled(client, auth_disabled):
    client.post("/auth/mcp-token")
    r = client.delete("/auth/mcp-token")
    assert r.status_code == 200
    assert client.get("/auth/mcp-token").json() == {
        "configured": False,
        "source": "none",
    }


def test_undecided_mode_still_requires_auth(client, monkeypatch):
    monkeypatch.delenv("FIESTABOARD_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("FIESTABOARD_MCP_TOKEN", raising=False)
    assert client.get("/auth/mcp-token").status_code == 401
    assert client.post("/auth/mcp-token").status_code == 401
    assert client.delete("/auth/mcp-token").status_code == 401
