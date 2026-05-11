"""End-to-end tests for the auth HTTP layer (routes + middleware).

These exercise the API surface via FastAPI's TestClient and verify that:

* ``/auth/*`` endpoints work as advertised.
* The middleware lets requests through when auth is disabled.
* The middleware blocks protected endpoints when auth is enabled until a
  valid session cookie is presented.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.auth import service as auth_service
from src.auth import routes as auth_routes


@pytest.fixture
def auth_dir(tmp_path, monkeypatch):
    """Point the auth service at a tmp dir and reset the singleton."""
    # Build a fresh AuthService bound to tmp_path and install it as the singleton.
    fresh = auth_service.AuthService(auth_file=tmp_path / "auth.json")
    monkeypatch.setattr(auth_service, "_service", fresh)
    # Clear any cross-test brute-force state.
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
def disabled(monkeypatch):
    monkeypatch.delenv("FIESTABOARD_AUTH_ENABLED", raising=False)


# --- /auth/status ----------------------------------------------------------


def test_status_disabled_no_user(client, disabled):
    r = client.get("/auth/status")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False
    assert body["setup_required"] is False
    assert body["authenticated"] is False


def test_status_enabled_setup_required(client, enabled):
    r = client.get("/auth/status")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert body["setup_required"] is True
    assert body["authenticated"] is False


# --- /auth/setup -----------------------------------------------------------


def test_setup_creates_user_and_logs_in(client, enabled):
    r = client.post("/auth/setup", json={"username": "admin", "password": "supersecret"})
    assert r.status_code == 201, r.text
    assert r.json()["username"] == "admin"
    # Session cookie should be set; subsequent /auth/status reports authenticated.
    r2 = client.get("/auth/status")
    body = r2.json()
    assert body["authenticated"] is True
    assert body["username"] == "admin"


def test_setup_rejected_if_user_exists(client, enabled):
    client.post("/auth/setup", json={"username": "admin", "password": "supersecret"})
    r = client.post("/auth/setup", json={"username": "admin2", "password": "anothersecret"})
    assert r.status_code == 409


def test_setup_short_password(client, enabled):
    r = client.post("/auth/setup", json={"username": "admin", "password": "short"})
    # Pydantic min_length=8 -> 422
    assert r.status_code == 422


# --- /auth/login -----------------------------------------------------------


def test_login_happy_path(client, enabled):
    client.post("/auth/setup", json={"username": "admin", "password": "supersecret"})
    # Wipe cookies so we start from a clean slate.
    client.cookies.clear()
    r = client.post("/auth/login", json={"username": "admin", "password": "supersecret"})
    assert r.status_code == 200
    assert auth_service.SESSION_COOKIE_NAME in r.cookies or any(
        c.name == auth_service.SESSION_COOKIE_NAME for c in client.cookies.jar
    )


def test_login_bad_password(client, enabled):
    client.post("/auth/setup", json={"username": "admin", "password": "supersecret"})
    client.cookies.clear()
    r = client.post("/auth/login", json={"username": "admin", "password": "wrongwrong"})
    assert r.status_code == 401


def test_login_before_setup(client, enabled):
    r = client.post("/auth/login", json={"username": "admin", "password": "supersecret"})
    assert r.status_code == 409


def test_login_brute_force_lockout(client, enabled):
    client.post("/auth/setup", json={"username": "admin", "password": "supersecret"})
    client.cookies.clear()
    # 10 failures -> next request is 429.
    for _ in range(10):
        r = client.post("/auth/login", json={"username": "admin", "password": "badbadbad"})
        assert r.status_code == 401
    r = client.post("/auth/login", json={"username": "admin", "password": "badbadbad"})
    assert r.status_code == 429


# --- /auth/logout ----------------------------------------------------------


def test_logout_clears_cookie(client, enabled):
    client.post("/auth/setup", json={"username": "admin", "password": "supersecret"})
    assert client.get("/auth/status").json()["authenticated"] is True
    r = client.post("/auth/logout")
    assert r.status_code == 200
    # TestClient honours Set-Cookie deletions.
    assert client.get("/auth/status").json()["authenticated"] is False


# --- /auth/change-password -------------------------------------------------


def test_change_password_flow(client, enabled):
    client.post("/auth/setup", json={"username": "admin", "password": "oldpassword"})
    r = client.post(
        "/auth/change-password",
        json={"current_password": "oldpassword", "new_password": "brandnewpassword"},
    )
    assert r.status_code == 200
    # Log out, log back in with new password.
    client.post("/auth/logout")
    r2 = client.post(
        "/auth/login", json={"username": "admin", "password": "brandnewpassword"}
    )
    assert r2.status_code == 200


def test_change_password_requires_auth(client, enabled):
    client.post("/auth/setup", json={"username": "admin", "password": "oldpassword"})
    client.cookies.clear()
    r = client.post(
        "/auth/change-password",
        json={"current_password": "oldpassword", "new_password": "brandnewpassword"},
    )
    assert r.status_code == 401


def test_change_password_wrong_current(client, enabled):
    client.post("/auth/setup", json={"username": "admin", "password": "oldpassword"})
    r = client.post(
        "/auth/change-password",
        json={"current_password": "wrong", "new_password": "brandnewpassword"},
    )
    assert r.status_code == 401


# --- Middleware ------------------------------------------------------------


def test_middleware_disabled_allows_everything(client, disabled):
    # /health is public regardless, /status is a protected endpoint when auth is on.
    r = client.get("/health")
    assert r.status_code == 200
    r2 = client.get("/status")
    # Whatever the response, it must NOT be a 401 from the auth layer.
    assert r2.status_code != 401


def test_middleware_blocks_protected_when_no_user(client, enabled):
    # Auth on, no user yet -> protected endpoint should 409 (setup required).
    r = client.get("/status")
    assert r.status_code == 409
    assert r.json().get("setup_required") is True


def test_middleware_blocks_without_cookie(client, enabled):
    client.post("/auth/setup", json={"username": "admin", "password": "supersecret"})
    client.cookies.clear()
    r = client.get("/status")
    assert r.status_code == 401


def test_middleware_allows_with_valid_cookie(client, enabled):
    client.post("/auth/setup", json={"username": "admin", "password": "supersecret"})
    # Cookie set by setup endpoint; should now pass through to /status.
    r = client.get("/status")
    # /status itself may return non-200 due to unrelated state, but it must
    # not be 401 or 409 from the middleware.
    assert r.status_code not in (401, 409)


def test_middleware_public_paths_when_enabled(client, enabled):
    for path in ("/", "/health", "/auth/status", "/openapi.json"):
        r = client.get(path)
        assert r.status_code != 401, f"{path} was incorrectly blocked"


def test_middleware_options_preflight_passes(client, enabled):
    r = client.options(
        "/status",
        headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.status_code != 401
