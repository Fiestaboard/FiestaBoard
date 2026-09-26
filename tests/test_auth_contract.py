"""Value-level contract goldens for the ``/auth`` API (conventions ratchet, #1926).

``auth`` predates the ratchet: it was already a router with ``response_model``
on all eleven routes when the ratchet landed, so it never went through a
conversion slice and nothing pinned its wire contract by value. These are the
pins. Every assertion below was **recorded against the unconverted trunk and
passed there before a line of production code changed** — the zero-regression
protocol ``docs/internal/reference/API_CONVENTIONS.md`` prescribes. Opting the
domain in adds ``responses=errors(...)`` declarations only, so nothing here is
re-pinned: no status code, no ``detail`` string, no body key, no cookie
attribute changed.

Values, not shapes: a shape golden cannot see a 403 that became a 401, a
``detail`` that stopped naming the fix, a ``mode`` that reads ``"enabled"``
when the install is still closed, or a session cookie that lost ``HttpOnly``.
The web client (``web/src/lib/api/auth.ts``) and the setup wizard read every
one of these values.

Covers all 11 routes the ``auth`` router serves, success and failure paths:

* ``GET /auth/status``
* ``POST /auth/preference`` — including the stored-MCP-token possession gate
  (#1880) on the enable direction
* ``POST /auth/setup`` — including the same gate
* ``POST /auth/login`` — including the brute-force throttle
* ``POST /auth/logout``
* ``POST /auth/change-password``
* ``POST /auth/change-username``
* ``POST /auth/disable``
* ``GET`` / ``POST`` / ``DELETE /auth/mcp-token`` — session-gated when the
  login is on, possession-gated when it is off (#1825), refused when the
  token is env-pinned
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.auth import routes as auth_routes
from src.auth import service as auth_service
from src.auth.service import SESSION_COOKIE_NAME

USERNAME = "admin"
PASSWORD = "correct-horse-battery"
STORED_TOKEN = "stored-mcp-token-for-contract"

OK_NO_USER = {"status": "ok", "username": None}


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def auth_dir(tmp_path, monkeypatch):
    """A fresh AuthService bound to a temp file, installed as the singleton."""
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
    """``FIESTABOARD_AUTH_ENABLED=true`` — the env pin wins over any preference."""
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "true")
    monkeypatch.delenv("FIESTABOARD_MCP_TOKEN", raising=False)


@pytest.fixture
def disabled(monkeypatch):
    """``FIESTABOARD_AUTH_ENABLED=false``."""
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "false")
    monkeypatch.delenv("FIESTABOARD_MCP_TOKEN", raising=False)


@pytest.fixture
def undecided(monkeypatch):
    """No env pin and no stored preference — the first-run picker state."""
    monkeypatch.delenv("FIESTABOARD_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("FIESTABOARD_MCP_TOKEN", raising=False)


@pytest.fixture
def signed_in(client, enabled):
    """Provision the first admin; the client now carries its session cookie."""
    response = client.post("/auth/setup", json={"username": USERNAME, "password": PASSWORD})
    assert response.status_code == 201, response.text


@pytest.fixture
def opted_in_and_signed_in(client, undecided):
    """The no-env-pin equivalent of ``signed_in``, so ``/auth/disable`` is reachable."""
    assert client.post("/auth/preference", json={"enabled": True}).status_code == 200
    response = client.post("/auth/setup", json={"username": USERNAME, "password": PASSWORD})
    assert response.status_code == 201, response.text


def _disabled_with_stored_token() -> None:
    """Persist a 'disabled' preference plus a stored MCP token — the #1880 install."""
    svc = auth_service.get_auth_service()
    svc.set_auth_preference("disabled")
    svc.set_stored_mcp_token(STORED_TOKEN)


def _session_set_cookie(response) -> str:
    """The ``Set-Cookie`` header for the session cookie, or fail loudly."""
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(f"{SESSION_COOKIE_NAME}="):
            return header
    raise AssertionError(f"no {SESSION_COOKIE_NAME} Set-Cookie header in {response.headers}")


# ── GET /auth/status ────────────────────────────────────────────────────────


def test_status_on_a_disabled_install_reports_every_flag_off(client, disabled):
    response = client.get("/auth/status")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "setup_required": False,
        "authenticated": False,
        "username": None,
        "mode": "disabled",
        "first_run": False,
    }


def test_status_on_a_first_run_install_is_secure_by_default_and_flags_first_run(client, undecided):
    response = client.get("/auth/status")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "setup_required": True,
        "authenticated": False,
        "username": None,
        "mode": "undecided",
        "first_run": True,
    }


def test_status_after_setup_names_the_signed_in_user(client, signed_in):
    body = client.get("/auth/status").json()

    assert body == {
        "enabled": True,
        "setup_required": False,
        "authenticated": True,
        "username": USERNAME,
        "mode": "enabled",
        "first_run": False,
    }


# ── POST /auth/preference ───────────────────────────────────────────────────


def test_preference_enable_records_the_choice(client, undecided):
    response = client.post("/auth/preference", json={"enabled": True})

    assert response.status_code == 200, response.text
    assert response.json() == OK_NO_USER
    status = client.get("/auth/status").json()
    assert status["mode"] == "enabled"
    assert status["first_run"] is False
    assert status["setup_required"] is True


def test_preference_disable_opens_the_install(client, undecided):
    response = client.post("/auth/preference", json={"enabled": False})

    assert response.status_code == 200, response.text
    assert response.json() == OK_NO_USER
    status = client.get("/auth/status").json()
    assert status["mode"] == "disabled"
    assert status["enabled"] is False
    assert status["setup_required"] is False


def test_preference_is_409_when_the_env_pin_is_set(client, enabled):
    response = client.post("/auth/preference", json={"enabled": False})

    assert response.status_code == 409
    assert response.json() == {"detail": "Auth mode is pinned by FIESTABOARD_AUTH_ENABLED."}


def test_preference_is_409_once_a_user_exists(client, opted_in_and_signed_in):
    response = client.post("/auth/preference", json={"enabled": False})

    assert response.status_code == 409
    assert response.json() == {
        "detail": "A user already exists. Sign in and use the account settings to change preferences."
    }


def test_preference_enable_is_403_while_a_stored_token_exists_and_is_not_presented(client, undecided):
    _disabled_with_stored_token()

    response = client.post("/auth/preference", json={"enabled": True})

    assert response.status_code == 403
    assert response.json() == {
        "detail": "This install has a stored MCP token. Present it as a Bearer token to enable login, or clear the token first."
    }
    # The refusal is not a side-effecting refusal: the install stays closed.
    assert client.get("/auth/status").json()["mode"] == "disabled"


def test_preference_enable_is_403_when_the_wrong_token_is_presented(client, undecided):
    _disabled_with_stored_token()

    response = client.post(
        "/auth/preference",
        json={"enabled": True},
        headers={"Authorization": "Bearer not-the-stored-token"},
    )

    assert response.status_code == 403
    assert client.get("/auth/status").json()["mode"] == "disabled"


def test_preference_enable_succeeds_when_the_stored_token_is_presented(client, undecided):
    _disabled_with_stored_token()

    response = client.post(
        "/auth/preference",
        json={"enabled": True},
        headers={"Authorization": f"Bearer {STORED_TOKEN}"},
    )

    assert response.status_code == 200, response.text
    assert response.json() == OK_NO_USER
    assert client.get("/auth/status").json()["mode"] == "enabled"


def test_preference_disable_is_never_gated_by_the_stored_token(client, undecided):
    _disabled_with_stored_token()

    response = client.post("/auth/preference", json={"enabled": False})

    assert response.status_code == 200, response.text
    assert response.json() == OK_NO_USER


def test_preference_rejects_a_body_without_enabled_with_422(client, undecided):
    response = client.post("/auth/preference", json={})

    assert response.status_code == 422
    assert [entry["loc"] for entry in response.json()["detail"]] == [["body", "enabled"]]


# ── POST /auth/setup ────────────────────────────────────────────────────────


def test_setup_creates_the_first_admin_and_issues_a_persistent_session(client, enabled):
    response = client.post("/auth/setup", json={"username": USERNAME, "password": PASSWORD})

    assert response.status_code == 201, response.text
    assert response.json() == {"status": "ok", "username": USERNAME}
    cookie = _session_set_cookie(response)
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/" in cookie
    # New admins are remembered (Max-Age present); plain http gets no Secure flag.
    assert "Max-Age=" in cookie
    assert "Secure" not in cookie
    assert client.get("/auth/status").json()["authenticated"] is True


def test_setup_is_409_once_a_user_exists(client, signed_in):
    response = client.post("/auth/setup", json={"username": "second", "password": PASSWORD})

    assert response.status_code == 409
    assert response.json() == {"detail": "A user has already been created. Use /auth/login."}


def test_setup_is_403_while_a_stored_token_exists_and_is_not_presented(client, undecided):
    _disabled_with_stored_token()

    response = client.post("/auth/setup", json={"username": "attacker", "password": PASSWORD})

    assert response.status_code == 403
    assert response.json() == {
        "detail": "This install has a stored MCP token. Present it as a Bearer token to enable login, or clear the token first."
    }
    status = client.get("/auth/status").json()
    assert status["mode"] == "disabled"
    assert status["setup_required"] is False


def test_setup_succeeds_when_the_stored_token_is_presented(client, undecided):
    _disabled_with_stored_token()

    response = client.post(
        "/auth/setup",
        json={"username": "owner", "password": PASSWORD},
        headers={"Authorization": f"Bearer {STORED_TOKEN}"},
    )

    assert response.status_code == 201, response.text
    assert response.json() == {"status": "ok", "username": "owner"}
    assert client.get("/auth/status").json()["mode"] == "enabled"


def test_setup_rejects_a_username_the_service_refuses_with_400(client, enabled):
    # Passes Pydantic (1..64 chars) but fails the service's character rule —
    # the 400 arm, not the 422 one.
    response = client.post("/auth/setup", json={"username": "bad name!", "password": PASSWORD})

    assert response.status_code == 400
    assert response.json() == {"detail": "username may only contain letters, digits, '.', '_', '-', '@'"}
    assert client.get("/auth/status").json()["setup_required"] is True


def test_setup_rejects_a_short_password_with_422(client, enabled):
    response = client.post("/auth/setup", json={"username": USERNAME, "password": "short"})

    assert response.status_code == 422
    assert [entry["loc"] for entry in response.json()["detail"]] == [["body", "password"]]


# ── POST /auth/login ────────────────────────────────────────────────────────


def test_login_issues_a_browser_session_cookie_by_default(client, signed_in):
    client.cookies.clear()

    response = client.post("/auth/login", json={"username": USERNAME, "password": PASSWORD})

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok", "username": USERNAME}
    cookie = _session_set_cookie(response)
    assert "HttpOnly" in cookie
    # remember_me defaults to false: a session cookie, no Max-Age / Expires.
    assert "Max-Age=" not in cookie
    assert "expires=" not in cookie.lower()
    assert client.get("/auth/status").json()["username"] == USERNAME


def test_login_with_remember_me_issues_a_persistent_cookie(client, signed_in):
    client.cookies.clear()

    response = client.post(
        "/auth/login",
        json={"username": USERNAME, "password": PASSWORD, "remember_me": True},
    )

    assert response.status_code == 200, response.text
    assert "Max-Age=" in _session_set_cookie(response)


def test_login_before_setup_is_409_pointing_at_setup(client, enabled):
    response = client.post("/auth/login", json={"username": USERNAME, "password": PASSWORD})

    assert response.status_code == 409
    assert response.json() == {"detail": "No user has been created. Call /auth/setup first."}


def test_login_with_a_wrong_password_is_401_and_issues_no_cookie(client, signed_in):
    client.cookies.clear()

    response = client.post("/auth/login", json={"username": USERNAME, "password": "wrong-password"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid username or password"}
    assert not any(h.startswith(f"{SESSION_COOKIE_NAME}=") for h in response.headers.get_list("set-cookie"))
    assert client.get("/auth/status").json()["authenticated"] is False


def test_login_is_429_after_ten_failures_from_one_address(client, signed_in):
    client.cookies.clear()
    for _ in range(10):
        failed = client.post("/auth/login", json={"username": USERNAME, "password": "wrong-password"})
        assert failed.status_code == 401

    response = client.post("/auth/login", json={"username": USERNAME, "password": PASSWORD})

    # Even the right password is refused while locked out.
    assert response.status_code == 429
    assert response.json() == {"detail": "Too many failed login attempts. Try again later."}


def test_login_rejects_an_empty_password_with_422(client, signed_in):
    response = client.post("/auth/login", json={"username": USERNAME, "password": ""})

    assert response.status_code == 422
    assert [entry["loc"] for entry in response.json()["detail"]] == [["body", "password"]]


# ── POST /auth/logout ───────────────────────────────────────────────────────


def test_logout_clears_the_session_cookie(client, signed_in):
    response = client.post("/auth/logout")

    assert response.status_code == 200, response.text
    assert response.json() == OK_NO_USER
    cookie = _session_set_cookie(response)
    assert "Max-Age=0" in cookie
    assert client.get("/auth/status").json()["authenticated"] is False


def test_logout_without_a_session_is_still_200(client, enabled):
    response = client.post("/auth/logout")

    assert response.status_code == 200
    assert response.json() == OK_NO_USER


# ── POST /auth/change-password ──────────────────────────────────────────────


def test_change_password_rotates_the_credential_and_keeps_the_user_signed_in(client, signed_in):
    response = client.post(
        "/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "brand-new-password"},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok", "username": USERNAME}
    # A fresh session cookie is minted under the new watermark.
    _session_set_cookie(response)
    assert client.get("/auth/status").json()["authenticated"] is True
    client.cookies.clear()
    assert client.post("/auth/login", json={"username": USERNAME, "password": PASSWORD}).status_code == 401
    assert client.post("/auth/login", json={"username": USERNAME, "password": "brand-new-password"}).status_code == 200


def test_change_password_without_a_session_is_401(client, signed_in):
    client.cookies.clear()

    response = client.post(
        "/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "brand-new-password"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_change_password_with_a_wrong_current_password_is_401(client, signed_in):
    response = client.post(
        "/auth/change-password",
        json={"current_password": "wrong-password", "new_password": "brand-new-password"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Current password is incorrect"}
    # Still signed in, and the password did not change.
    client.cookies.clear()
    assert client.post("/auth/login", json={"username": USERNAME, "password": PASSWORD}).status_code == 200


def test_change_password_maps_a_service_rejection_to_400(client, signed_in, monkeypatch):
    """The handler's ``ValueError -> 400`` arm.

    Over HTTP the request model already enforces the same length limits the
    service checks, so the arm is defence in depth; it is pinned by making
    the service refuse, exactly as the pages contract pins its own 400.
    """

    def refuse(*_args, **_kwargs):
        raise ValueError("password must be at least 8 characters")

    monkeypatch.setattr(auth_service.get_auth_service(), "change_password", refuse)

    response = client.post(
        "/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "brand-new-password"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "password must be at least 8 characters"}


def test_change_password_rejects_a_short_new_password_with_422(client, signed_in):
    response = client.post("/auth/change-password", json={"current_password": PASSWORD, "new_password": "short"})

    assert response.status_code == 422
    assert [entry["loc"] for entry in response.json()["detail"]] == [["body", "new_password"]]


# ── POST /auth/change-username ──────────────────────────────────────────────


def test_change_username_renames_the_user_and_reissues_the_session(client, signed_in):
    response = client.post(
        "/auth/change-username",
        json={"current_password": PASSWORD, "new_username": "renamed"},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok", "username": "renamed"}
    _session_set_cookie(response)
    status = client.get("/auth/status").json()
    assert status["authenticated"] is True
    assert status["username"] == "renamed"


def test_change_username_without_a_session_is_401(client, signed_in):
    client.cookies.clear()

    response = client.post(
        "/auth/change-username",
        json={"current_password": PASSWORD, "new_username": "renamed"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_change_username_with_a_wrong_password_is_401(client, signed_in):
    response = client.post(
        "/auth/change-username",
        json={"current_password": "wrong-password", "new_username": "renamed"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Password is incorrect"}
    assert client.get("/auth/status").json()["username"] == USERNAME


def test_change_username_to_a_name_the_service_refuses_is_400(client, signed_in):
    response = client.post(
        "/auth/change-username",
        json={"current_password": PASSWORD, "new_username": "bad name!"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "username may only contain letters, digits, '.', '_', '-', '@'"}
    assert client.get("/auth/status").json()["username"] == USERNAME


# ── POST /auth/disable ──────────────────────────────────────────────────────


def test_disable_turns_auth_off_deletes_the_user_and_clears_the_cookie(client, opted_in_and_signed_in):
    response = client.post("/auth/disable", json={"current_password": PASSWORD})

    assert response.status_code == 200, response.text
    assert response.json() == OK_NO_USER
    assert "Max-Age=0" in _session_set_cookie(response)
    assert client.get("/auth/status").json() == {
        "enabled": False,
        "setup_required": False,
        "authenticated": False,
        "username": None,
        "mode": "disabled",
        "first_run": False,
    }


def test_disable_is_409_when_the_env_pin_is_set(client, signed_in):
    response = client.post("/auth/disable", json={"current_password": PASSWORD})

    assert response.status_code == 409
    assert response.json() == {"detail": "Auth mode is pinned by FIESTABOARD_AUTH_ENABLED."}
    assert client.get("/auth/status").json()["authenticated"] is True


def test_disable_without_a_session_is_401(client, opted_in_and_signed_in):
    client.cookies.clear()

    response = client.post("/auth/disable", json={"current_password": PASSWORD})

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_disable_with_a_wrong_password_is_401_and_changes_nothing(client, opted_in_and_signed_in):
    response = client.post("/auth/disable", json={"current_password": "wrong-password"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Password is incorrect"}
    status = client.get("/auth/status").json()
    assert status["mode"] == "enabled"
    assert status["authenticated"] is True


# ── GET /auth/mcp-token ─────────────────────────────────────────────────────


def test_mcp_token_status_reports_none_before_any_mint(client, signed_in):
    response = client.get("/auth/mcp-token")

    assert response.status_code == 200
    assert response.json() == {"configured": False, "source": "none"}


def test_mcp_token_status_reports_env_when_the_variable_is_set(client, signed_in, monkeypatch):
    monkeypatch.setenv("FIESTABOARD_MCP_TOKEN", "pinned-by-ops")

    assert client.get("/auth/mcp-token").json() == {"configured": True, "source": "env"}


def test_mcp_token_status_without_a_session_is_401_when_login_is_on(client, signed_in):
    client.cookies.clear()

    response = client.get("/auth/mcp-token")

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_mcp_token_status_is_open_on_a_disabled_install_with_no_token(client, disabled):
    response = client.get("/auth/mcp-token")

    assert response.status_code == 200
    assert response.json() == {"configured": False, "source": "none"}


def test_mcp_token_status_on_a_disabled_install_demands_the_stored_token(client, disabled):
    auth_service.get_auth_service().set_stored_mcp_token(STORED_TOKEN)

    response = client.get("/auth/mcp-token")

    assert response.status_code == 401
    assert response.json() == {"detail": "MCP token management requires the current token when auth is disabled"}
    assert response.headers["WWW-Authenticate"] == 'Bearer realm="FiestaBoard MCP token management"'


def test_mcp_token_status_on_a_disabled_install_accepts_the_stored_token(client, disabled):
    auth_service.get_auth_service().set_stored_mcp_token(STORED_TOKEN)

    response = client.get("/auth/mcp-token", headers={"Authorization": f"Bearer {STORED_TOKEN}"})

    assert response.status_code == 200
    assert response.json() == {"configured": True, "source": "stored"}


# ── POST /auth/mcp-token ────────────────────────────────────────────────────


def test_mcp_token_rotate_returns_the_plaintext_once_and_stores_it(client, signed_in):
    response = client.post("/auth/mcp-token")

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == {"token"}
    assert isinstance(body["token"], str) and len(body["token"]) >= 32
    assert client.get("/auth/mcp-token").json() == {"configured": True, "source": "stored"}
    # The stored value is exactly what was handed back.
    assert auth_service.get_auth_service().get_stored_mcp_token() == body["token"]


def test_mcp_token_rotate_replaces_the_previous_token(client, signed_in):
    first = client.post("/auth/mcp-token").json()["token"]

    second = client.post("/auth/mcp-token").json()["token"]

    assert second != first
    assert auth_service.get_auth_service().get_stored_mcp_token() == second


def test_mcp_token_rotate_is_409_while_the_env_pin_is_set(client, signed_in, monkeypatch):
    monkeypatch.setenv("FIESTABOARD_MCP_TOKEN", "pinned-by-ops")

    response = client.post("/auth/mcp-token")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "MCP token is pinned by FIESTABOARD_MCP_TOKEN environment variable. Unset it before managing the token from the UI."
    }
    assert auth_service.get_auth_service().get_stored_mcp_token() is None


def test_mcp_token_rotate_without_a_session_is_401_when_login_is_on(client, signed_in):
    client.cookies.clear()

    response = client.post("/auth/mcp-token")

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_mcp_token_first_mint_is_open_on_a_disabled_install(client, disabled):
    response = client.post("/auth/mcp-token")

    assert response.status_code == 201, response.text
    assert set(response.json()) == {"token"}


def test_mcp_token_rotate_on_a_disabled_install_demands_the_current_token(client, disabled):
    auth_service.get_auth_service().set_stored_mcp_token(STORED_TOKEN)

    response = client.post("/auth/mcp-token")

    assert response.status_code == 401
    assert response.json() == {"detail": "MCP token management requires the current token when auth is disabled"}
    assert auth_service.get_auth_service().get_stored_mcp_token() == STORED_TOKEN


# ── DELETE /auth/mcp-token ──────────────────────────────────────────────────


def test_mcp_token_clear_revokes_the_stored_token(client, signed_in):
    client.post("/auth/mcp-token")

    response = client.delete("/auth/mcp-token")

    assert response.status_code == 200, response.text
    assert response.json() == OK_NO_USER
    assert client.get("/auth/mcp-token").json() == {"configured": False, "source": "none"}
    assert auth_service.get_auth_service().get_stored_mcp_token() is None


def test_mcp_token_clear_is_idempotent(client, signed_in):
    response = client.delete("/auth/mcp-token")

    assert response.status_code == 200
    assert response.json() == OK_NO_USER


def test_mcp_token_clear_is_409_while_the_env_pin_is_set(client, signed_in, monkeypatch):
    monkeypatch.setenv("FIESTABOARD_MCP_TOKEN", "pinned-by-ops")

    response = client.delete("/auth/mcp-token")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "MCP token is pinned by FIESTABOARD_MCP_TOKEN environment variable. Unset it before managing the token from the UI."
    }


def test_mcp_token_clear_without_a_session_is_401_when_login_is_on(client, signed_in):
    client.cookies.clear()

    response = client.delete("/auth/mcp-token")

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_mcp_token_clear_on_a_disabled_install_accepts_the_current_token(client, disabled):
    auth_service.get_auth_service().set_stored_mcp_token(STORED_TOKEN)

    response = client.delete("/auth/mcp-token", headers={"Authorization": f"Bearer {STORED_TOKEN}"})

    assert response.status_code == 200, response.text
    assert response.json() == OK_NO_USER
    assert auth_service.get_auth_service().get_stored_mcp_token() is None


def test_mcp_token_clear_on_a_disabled_install_demands_the_current_token(client, disabled):
    auth_service.get_auth_service().set_stored_mcp_token(STORED_TOKEN)

    response = client.delete("/auth/mcp-token")

    assert response.status_code == 401
    assert auth_service.get_auth_service().get_stored_mcp_token() == STORED_TOKEN
