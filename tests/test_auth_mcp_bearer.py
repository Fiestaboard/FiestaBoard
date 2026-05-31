"""Tests for MCP bearer-token auth on the ``/mcp`` endpoint.

Verifies:
  * ``FIESTABOARD_MCP_TOKEN`` unset -> the existing cookie-auth path is
    unaffected (no behaviour change for installs that don't use MCP).
  * ``FIESTABOARD_MCP_TOKEN`` set -> a valid ``Authorization: Bearer``
    header passes the middleware without a session cookie.
  * Wrong / missing token -> 401 with ``WWW-Authenticate: Bearer realm=...``
    so MCP clients send a token instead of starting OAuth discovery.
  * Non-``/mcp`` paths still require the cookie even when the token env
    var is set (token grants access to MCP only, not the whole API).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.auth import routes as auth_routes
from src.auth import service as auth_service

TOKEN = "test-token-abc123"


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
    yield
    monkeypatch.delenv("FIESTABOARD_AUTH_ENABLED", raising=False)


@pytest.fixture
def with_token(monkeypatch):
    monkeypatch.setenv("FIESTABOARD_MCP_TOKEN", TOKEN)
    yield TOKEN
    monkeypatch.delenv("FIESTABOARD_MCP_TOKEN", raising=False)


@pytest.fixture
def no_token(monkeypatch):
    """Ensure the env var is *unset* even if the dev's local .env had one.

    api_server.py calls ``load_dotenv()`` at import time, which can leak
    ``FIESTABOARD_MCP_TOKEN`` from the developer's ``.env`` into pytest's
    process environment. Tests that assert "no token configured" must use
    this fixture to neutralise that.
    """
    monkeypatch.delenv("FIESTABOARD_MCP_TOKEN", raising=False)


@pytest.fixture
def setup_user(client, enabled):
    """Provision an admin user so middleware doesn't 409 for setup.

    ``/auth/setup`` auto-logs the new user in. We drop the session cookie
    so subsequent assertions in the test exercise the unauthenticated
    code path (cookie-less request -> 401) rather than riding on the
    setup-time session.
    """
    r = client.post("/auth/setup", json={"username": "admin", "password": "Password123!"})
    assert r.status_code in (200, 201), r.text
    client.cookies.clear()


# --- Cookie path is unaffected when no token is configured ----------------


def test_mcp_without_token_env_still_requires_cookie(client, setup_user, no_token):
    """No FIESTABOARD_MCP_TOKEN set -> /mcp falls back to cookie auth."""
    r = client.get("/mcp/")
    # Cookie missing -> standard 401, no Bearer challenge.
    assert r.status_code == 401
    assert "www-authenticate" not in {k.lower() for k in r.headers}


# --- Bearer auth path ------------------------------------------------------


def test_mcp_with_valid_bearer_passes_middleware(client, setup_user, with_token):
    """Correct token -> middleware passes through (downstream may still
    refuse the request for other reasons, but it's not a 401)."""
    r = client.get("/mcp/", headers={"Authorization": f"Bearer {with_token}"})
    assert r.status_code != 401


def test_mcp_with_wrong_bearer_returns_401_with_challenge(client, setup_user, with_token):
    r = client.get("/mcp/", headers={"Authorization": "Bearer not-the-real-token"})
    assert r.status_code == 401
    assert r.headers.get("WWW-Authenticate", "").startswith("Bearer")
    assert 'realm="FiestaBoard MCP"' in r.headers["WWW-Authenticate"]


def test_mcp_with_no_auth_header_returns_401_with_challenge(client, setup_user, with_token):
    """When a token is configured, even an un-authenticated request gets
    the Bearer challenge (no cookie fallback)."""
    r = client.get("/mcp/")
    assert r.status_code == 401
    assert r.headers.get("WWW-Authenticate", "").startswith("Bearer")


def test_mcp_bearer_does_not_expose_oauth_resource_metadata(client, setup_user, with_token):
    """The challenge must NOT advertise OAuth metadata, otherwise spec-
    compliant MCP clients will try OAuth dynamic client registration."""
    r = client.get("/mcp/", headers={"Authorization": "Bearer wrong"})
    assert "resource_metadata" not in r.headers.get("WWW-Authenticate", "")


def test_bearer_works_for_unstripped_api_mcp_path(client, setup_user, with_token):
    """Behind nginx the MCP endpoint is reachable at ``/api/mcp/...`` *without*
    the prefix being stripped (so Starlette's Mount can compute the sub-app's
    root_path correctly). The middleware must accept the bearer header on
    that path too, not only on ``/mcp/``."""
    r = client.get("/api/mcp/", headers={"Authorization": f"Bearer {with_token}"})
    # Middleware lets us through; downstream MCP may 405 the GET or otherwise
    # respond, but it must not be the auth-layer 401.
    assert r.status_code != 401
    r2 = client.get("/api/mcp/", headers={"Authorization": "Bearer wrong"})
    assert r2.status_code == 401
    assert r2.headers.get("WWW-Authenticate", "").startswith("Bearer")


# --- Token scope: MCP only -------------------------------------------------


def test_bearer_does_not_grant_access_to_non_mcp_paths(client, setup_user, with_token):
    """The MCP token must not let a caller bypass cookie auth on the rest
    of the API. /api/pages should still 401 even with a valid Bearer."""
    r = client.get("/pages", headers={"Authorization": f"Bearer {with_token}"})
    # Cookie still required; either standard 401 or a non-Bearer challenge.
    assert r.status_code == 401
    assert not r.headers.get("WWW-Authenticate", "").startswith("Bearer")


# --- Auth disabled -> token irrelevant -----------------------------------


def test_token_irrelevant_when_auth_disabled(client, monkeypatch, with_token):
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "false")
    r = client.get("/mcp/")
    # No auth means the middleware is a no-op; downstream may 404 or 405
    # but should not 401.
    assert r.status_code != 401
