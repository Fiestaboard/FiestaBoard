"""H10b: a phone lists and revokes the account's signed-in TVs.

Per Jev D14, phones manage TVs through a narrow surface: TV sessions only.
``/auth/sessions`` stays browser-only, and a phone can never see or revoke a
browser or a phone. A phone signs itself out with ``DELETE /auth/device/session``.
"""

import logging

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.auth import routes as routes_module
from src.auth import scopes
from src.auth import service as auth_module

PASSWORD = "correct-password"
IOS = {"client_id": "fiestaboard-ios", "device_name": "Maya's iPhone", "app_version": "1.0"}
ANDROID = {"client_id": "fiestaboard-android", "device_name": "Pixel", "app_version": "1.0"}
TV = {"client_id": "fiestaboard-tvos", "device_name": "Living room", "app_version": "1.0"}
GTV = {"client_id": "fiestaboard-androidtv", "device_name": "Bedroom", "app_version": "2.0"}


@pytest.fixture
def auth(tmp_path, monkeypatch):
    svc = auth_module.AuthService(tmp_path / "auth.json")
    svc.create_initial_user("admin", PASSWORD)
    svc.sessions.set_enrollment(True)
    monkeypatch.setattr(auth_module, "_service", svc)
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "true")
    monkeypatch.delenv("FIESTABOARD_MCP_TOKEN", raising=False)
    monkeypatch.setenv("FIESTABOARD_DATA_DIR", str(tmp_path / "data"))
    routes_module._FAILED_ATTEMPTS.clear()
    return svc


@pytest.fixture
def browser(auth):
    client = TestClient(app, headers={"User-Agent": "Mozilla/5.0 Test browser"})
    assert client.post("/auth/login", json={"username": "admin", "password": PASSWORD}).status_code == 200
    context = client.get("/auth/sessions/context")
    client.headers.update({"Origin": "http://testserver", "X-CSRF-Token": context.json()["csrf_token"]})
    return client


def bearer_client(token):
    return TestClient(app, headers={"Authorization": "Bearer " + token}, raise_server_exceptions=False)


def sign_in(metadata):
    response = TestClient(app).post("/auth/device/login", json={**metadata, "username": "admin", "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def phone(auth):
    token = sign_in(IOS)
    return bearer_client(token["access_token"]), token


def approved_tv(auth, approver, metadata=TV):
    """A TV signed in with a code that *approver* (a phone or browser client) approved."""
    grant = TestClient(app).post("/auth/device/authorize", json=metadata).json()
    assert approver.post("/auth/device/approve", json={"user_code": grant["user_code"]}).status_code == 200
    now = auth.sessions.clock_ms()
    auth.sessions.clock_ms = lambda: now + 6_000
    token = TestClient(app).post(
        "/auth/device/token", json={"device_code": grant["device_code"], "client_id": metadata["client_id"]}
    )
    assert token.status_code == 200, token.text
    return token.json()


def tvs(client):
    response = client.get("/auth/device/tvs")
    assert response.status_code == 200, response.text
    return response.json()["tvs"]


# --- Listing -------------------------------------------------------------------


def test_a_phone_lists_tvs_only(auth, browser, phone):
    client, _ = phone
    sign_in(ANDROID)
    tv = sign_in(TV)
    rows = tvs(client)
    assert [row["id"] for row in rows] == [tv["session_id"]]
    row = rows[0]
    assert row["device_name"] == TV["device_name"] and row["client_id"] == TV["client_id"]
    assert row["app_version"] == TV["app_version"] and row["method"] == "password"
    assert {"created_at", "last_active_at", "expires_at", "last_shown_at", "shown_panels"} <= set(row)
    for secret in ("digest", "username", "access_token", "account_generation", "approver_session_id", "kind"):
        assert secret not in row


def test_newest_tv_first(auth, phone):
    client, _ = phone
    first = sign_in(TV)
    now = auth.sessions.clock_ms()
    auth.sessions.clock_ms = lambda: now + 1_000
    second = sign_in(GTV)
    assert [row["id"] for row in tvs(client)] == [second["session_id"], first["session_id"]]


def test_approved_by_you_marks_the_approving_phone(auth, browser, phone):
    client, _ = phone
    mine = approved_tv(auth, client)
    theirs = approved_tv(auth, browser, GTV)
    rows = {row["id"]: row for row in tvs(client)}
    assert rows[mine["session_id"]]["approved_by_you"] is True
    assert rows[theirs["session_id"]]["approved_by_you"] is False
    other = bearer_client(sign_in(ANDROID)["access_token"])
    assert all(row["approved_by_you"] is False for row in tvs(other))


def test_a_password_tv_is_not_approved_by_anyone(auth, phone):
    client, _ = phone
    sign_in(TV)
    assert tvs(client)[0]["approved_by_you"] is False


def test_other_generations_are_hidden(auth, phone):
    sign_in(TV)
    auth.invalidate_all_sessions("admin")
    client = bearer_client(sign_in(IOS)["access_token"])
    assert tvs(client) == []


# --- Revoking ------------------------------------------------------------------


def test_a_phone_signs_out_a_tv(auth, phone):
    client, _ = phone
    tv = sign_in(TV)
    tv_client = bearer_client(tv["access_token"])
    assert tv_client.get("/panels").status_code == 200
    assert client.delete("/auth/device/tvs/" + tv["session_id"]).status_code == 200
    assert tv_client.get("/panels").status_code == 401
    assert tvs(client) == []


def test_a_phone_may_sign_out_a_tv_it_did_not_approve(auth, browser, phone):
    client, _ = phone
    tv = approved_tv(auth, browser)
    assert client.delete("/auth/device/tvs/" + tv["session_id"]).status_code == 200


def _not_found(response):
    assert response.status_code == 404, response.text
    assert response.json()["error"] == "not_found"


def test_a_phone_cannot_sign_out_a_browser(auth, browser, phone):
    client, _ = phone
    browser_id = browser.get("/auth/sessions").json()["current_session_id"]
    _not_found(client.delete("/auth/device/tvs/" + browser_id))
    assert browser.get("/auth/sessions").status_code == 200


def test_a_phone_cannot_sign_out_another_phone(auth, phone):
    client, _ = phone
    other = sign_in(ANDROID)
    _not_found(client.delete("/auth/device/tvs/" + other["session_id"]))
    assert bearer_client(other["access_token"]).get("/v1/status").status_code == 200


def test_a_phone_cannot_sign_itself_out_here(auth, phone):
    client, token = phone
    _not_found(client.delete("/auth/device/tvs/" + token["session_id"]))
    assert client.get("/v1/status").status_code == 200


@pytest.mark.parametrize("session_id", ["nope", "A" * 22])
def test_unknown_ids_are_not_found(auth, phone, session_id):
    client, _ = phone
    _not_found(client.delete("/auth/device/tvs/" + session_id))


def test_a_signed_out_tv_is_not_found(auth, phone):
    client, _ = phone
    tv = sign_in(TV)
    assert client.delete("/auth/device/tvs/" + tv["session_id"]).status_code == 200
    _not_found(client.delete("/auth/device/tvs/" + tv["session_id"]))


def test_an_old_generation_tv_is_not_found(auth):
    tv = sign_in(TV)
    with auth.sessions.transaction() as db:
        db.execute("UPDATE sessions SET account_generation=account_generation-1 WHERE id=?", (tv["session_id"],))
    client = bearer_client(sign_in(IOS)["access_token"])
    _not_found(client.delete("/auth/device/tvs/" + tv["session_id"]))


def test_revokes_are_rate_limited_per_phone(auth, phone):
    client, _ = phone
    for _ in range(20):
        client.delete("/auth/device/tvs/nope")
    response = client.delete("/auth/device/tvs/nope")
    assert response.status_code == 429 and response.headers["retry-after"] == "60"
    # The limit is the phone's, not the address's: another phone is unaffected.
    other = bearer_client(sign_in(ANDROID)["access_token"])
    _not_found(other.delete("/auth/device/tvs/nope"))


def test_a_revoke_is_logged_without_the_token(auth, phone, caplog):
    client, token = phone
    tv = sign_in(TV)
    with caplog.at_level(logging.INFO, logger="src.auth.device_routes"):
        assert client.delete("/auth/device/tvs/" + tv["session_id"]).status_code == 200
    lines = [r.getMessage() for r in caplog.records if r.name == "src.auth.device_routes"]
    assert any(tv["session_id"] in line and token["session_id"] in line for line in lines)
    assert all(tv["access_token"] not in line and token["access_token"] not in line for line in lines)


# --- Who may call ----------------------------------------------------------------


def test_control_has_exactly_the_two_new_rules():
    assert scopes.permits(scopes.CONTROL, "GET", "/auth/device/tvs")
    assert scopes.permits(scopes.CONTROL, "DELETE", "/auth/device/tvs/x")
    assert not scopes.permits(scopes.CONTROL, "POST", "/auth/device/tvs")
    assert not scopes.permits(scopes.CONTROL, "DELETE", "/auth/device/tvs")
    assert not scopes.permits(scopes.TV_PANELS, "GET", "/auth/device/tvs")
    assert not scopes.permits(scopes.TV_PANELS, "DELETE", "/auth/device/tvs/x")
    # The browser's session management stays out of the phone's reach.
    assert not scopes.permits(scopes.CONTROL, "GET", "/auth/sessions")
    assert not scopes.permits(scopes.CONTROL, "DELETE", "/auth/sessions/x")


def test_a_tv_cannot_list_or_revoke(auth):
    tv = bearer_client(sign_in(TV)["access_token"])
    other = sign_in(GTV)
    assert tv.get("/auth/device/tvs").status_code == 403
    assert tv.delete("/auth/device/tvs/" + other["session_id"]).status_code == 403


def test_a_browser_uses_its_own_route(auth, browser):
    tv = sign_in(TV)
    assert browser.get("/auth/device/tvs").status_code == 401
    assert browser.delete("/auth/device/tvs/" + tv["session_id"]).status_code == 401


def test_no_credential_is_401(auth):
    assert TestClient(app).get("/auth/device/tvs").status_code == 401


def test_a_revoked_phone_cannot_list(auth, browser, phone):
    client, token = phone
    assert browser.delete("/auth/sessions/" + token["session_id"]).status_code == 200
    assert client.get("/auth/device/tvs").status_code == 401
