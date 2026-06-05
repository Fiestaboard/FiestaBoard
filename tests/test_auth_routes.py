"""End-to-end tests for the auth HTTP layer (routes + middleware).

These exercise the API surface via FastAPI's TestClient and verify that:

* ``/auth/*`` endpoints work as advertised.
* The middleware lets requests through when auth is disabled.
* The middleware blocks protected endpoints when auth is enabled until a
  valid session cookie is presented.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.auth import routes as auth_routes
from src.auth import service as auth_service


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
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "false")
    yield
    monkeypatch.delenv("FIESTABOARD_AUTH_ENABLED", raising=False)


@pytest.fixture
def undecided(monkeypatch):
    """No env override + no stored preference => first-run mode."""
    monkeypatch.delenv("FIESTABOARD_AUTH_ENABLED", raising=False)


# --- /auth/status ----------------------------------------------------------


def test_status_disabled_no_user(client, disabled):
    r = client.get("/auth/status")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False
    assert body["setup_required"] is False
    assert body["authenticated"] is False
    assert body["mode"] == "disabled"
    assert body["first_run"] is False


def test_status_enabled_setup_required(client, enabled):
    r = client.get("/auth/status")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert body["setup_required"] is True
    assert body["authenticated"] is False
    assert body["mode"] == "enabled"
    # first_run is reserved for the *undecided* case.
    assert body["first_run"] is False


def test_status_undecided_first_run(client, undecided):
    """No env var + no stored preference + no user => first_run picker."""
    r = client.get("/auth/status")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True  # secure-by-default
    assert body["setup_required"] is True
    assert body["mode"] == "undecided"
    assert body["first_run"] is True


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


def _session_set_cookie(response) -> str:
    """Return the ``Set-Cookie`` header for the session cookie."""
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(f"{auth_service.SESSION_COOKIE_NAME}="):
            return header
    raise AssertionError("No session Set-Cookie header found")


def test_login_remember_me_sets_persistent_cookie(client, enabled):
    client.post("/auth/setup", json={"username": "admin", "password": "supersecret"})
    client.cookies.clear()
    r = client.post(
        "/auth/login",
        json={"username": "admin", "password": "supersecret", "remember_me": True},
    )
    assert r.status_code == 200
    cookie = _session_set_cookie(r)
    # 30-day default remember-me window.
    assert "Max-Age=2592000" in cookie


def test_login_without_remember_me_sets_session_cookie(client, enabled):
    client.post("/auth/setup", json={"username": "admin", "password": "supersecret"})
    client.cookies.clear()
    r = client.post(
        "/auth/login",
        json={"username": "admin", "password": "supersecret", "remember_me": False},
    )
    assert r.status_code == 200
    cookie = _session_set_cookie(r)
    # A session cookie carries neither Max-Age nor Expires.
    assert "Max-Age" not in cookie
    assert "expires" not in cookie.lower()


def test_login_remember_me_defaults_to_session_cookie(client, enabled):
    """Omitting the field behaves like remember_me=False for API clients."""
    client.post("/auth/setup", json={"username": "admin", "password": "supersecret"})
    client.cookies.clear()
    r = client.post("/auth/login", json={"username": "admin", "password": "supersecret"})
    assert r.status_code == 200
    cookie = _session_set_cookie(r)
    assert "Max-Age" not in cookie
    # And the cookie still authenticates subsequent requests.
    assert client.get("/auth/status").json()["authenticated"] is True


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
    r2 = client.post("/auth/login", json={"username": "admin", "password": "brandnewpassword"})
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


def test_middleware_first_run_includes_marker(client, undecided):
    """Undecided + no user => 409 with first_run=true so the UI shows the picker."""
    r = client.get("/status")
    assert r.status_code == 409
    body = r.json()
    assert body["setup_required"] is True
    assert body["first_run"] is True


# --- /auth/preference (first-run opt-in/opt-out) ---------------------------


def test_preference_disable_short_circuits_auth(client, undecided):
    """Opting out persists and turns the middleware into a no-op."""
    r = client.post("/auth/preference", json={"enabled": False})
    assert r.status_code == 200
    # The decision is reflected in /auth/status without restart.
    status_body = client.get("/auth/status").json()
    assert status_body["mode"] == "disabled"
    assert status_body["enabled"] is False
    # Protected endpoints are now reachable without a session cookie.
    r2 = client.get("/status")
    assert r2.status_code != 401
    assert r2.status_code != 409


def test_preference_enable_persists_pending_setup(client, undecided):
    """Opting in records the choice but still requires /auth/setup."""
    r = client.post("/auth/preference", json={"enabled": True})
    assert r.status_code == 200
    status_body = client.get("/auth/status").json()
    assert status_body["mode"] == "enabled"
    assert status_body["first_run"] is False
    assert status_body["setup_required"] is True


def test_preference_rejected_when_env_var_set(client, enabled):
    r = client.post("/auth/preference", json={"enabled": False})
    assert r.status_code == 409


def test_preference_rejected_after_setup(client, enabled):
    client.post("/auth/setup", json={"username": "admin", "password": "supersecret"})
    r = client.post("/auth/preference", json={"enabled": False})
    assert r.status_code == 409


# --- /auth/change-username -------------------------------------------------


def test_change_username_flow(client, enabled):
    client.post("/auth/setup", json={"username": "admin", "password": "supersecret"})
    r = client.post(
        "/auth/change-username",
        json={"current_password": "supersecret", "new_username": "owner"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["username"] == "owner"
    # The fresh cookie keeps the user signed in.
    status_body = client.get("/auth/status").json()
    assert status_body["authenticated"] is True
    assert status_body["username"] == "owner"


def test_change_username_requires_auth(client, enabled):
    client.post("/auth/setup", json={"username": "admin", "password": "supersecret"})
    client.cookies.clear()
    r = client.post(
        "/auth/change-username",
        json={"current_password": "supersecret", "new_username": "owner"},
    )
    assert r.status_code == 401


def test_change_username_wrong_password(client, enabled):
    client.post("/auth/setup", json={"username": "admin", "password": "supersecret"})
    r = client.post(
        "/auth/change-username",
        json={"current_password": "wrong", "new_username": "owner"},
    )
    assert r.status_code == 401


def test_change_username_rejects_invalid(client, enabled):
    client.post("/auth/setup", json={"username": "admin", "password": "supersecret"})
    r = client.post(
        "/auth/change-username",
        json={"current_password": "supersecret", "new_username": "has space"},
    )
    assert r.status_code == 400


# --- /auth/disable ---------------------------------------------------------


def test_disable_auth_happy_path(client, enabled, monkeypatch):
    client.post("/auth/setup", json={"username": "admin", "password": "supersecret"})
    # Clear the env-var pin so set_auth_preference("disabled") actually
    # takes effect for the next /auth/status call.
    monkeypatch.delenv("FIESTABOARD_AUTH_ENABLED", raising=False)
    r = client.post("/auth/disable", json={"current_password": "supersecret"})
    assert r.status_code == 200, r.text
    # The session cookie was cleared and the user record removed.
    status_body = client.get("/auth/status").json()
    assert status_body["enabled"] is False
    assert status_body["authenticated"] is False
    assert status_body["setup_required"] is False
    assert status_body["mode"] == "disabled"


def test_disable_auth_requires_password(client, enabled, monkeypatch):
    client.post("/auth/setup", json={"username": "admin", "password": "supersecret"})
    # Clear the env pin so the env-pinned 409 doesn't shadow the
    # actual code path under test.
    monkeypatch.delenv("FIESTABOARD_AUTH_ENABLED", raising=False)
    r = client.post("/auth/disable", json={"current_password": "wrong"})
    assert r.status_code == 401
    # Still signed in and auth still enforced (pref is "enabled" after setup).
    assert client.get("/auth/status").json()["authenticated"] is True


def test_disable_auth_requires_auth(client, enabled, monkeypatch):
    client.post("/auth/setup", json={"username": "admin", "password": "supersecret"})
    monkeypatch.delenv("FIESTABOARD_AUTH_ENABLED", raising=False)
    client.cookies.clear()
    r = client.post("/auth/disable", json={"current_password": "supersecret"})
    assert r.status_code == 401


def test_disable_auth_blocked_when_env_pinned(client, enabled):
    """The env var always wins — UI can't override an ops-pinned mode."""
    client.post("/auth/setup", json={"username": "admin", "password": "supersecret"})
    # `enabled` fixture sets FIESTABOARD_AUTH_ENABLED=true and leaves it set.
    r = client.post("/auth/disable", json={"current_password": "supersecret"})
    assert r.status_code == 409
    assert "FIESTABOARD_AUTH_ENABLED" in r.json()["detail"]
