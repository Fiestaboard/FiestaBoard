"""Real HTTP boundary for native credentials, approval and management."""

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.auth import routes as routes_module
from src.auth import service as auth_module

PASSWORD = "correct-password"
META = {"client_id": "fiestaboard-tvos", "device_name": "Living room", "app_version": "1.0"}


@pytest.fixture
def auth(tmp_path, monkeypatch):
    svc = auth_module.AuthService(tmp_path / "auth.json")
    svc.create_initial_user("admin", PASSWORD)
    monkeypatch.setattr(auth_module, "_service", svc)
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "true")
    routes_module._FAILED_ATTEMPTS.clear()
    return svc


@pytest.fixture
def browser(auth):
    client = TestClient(app, headers={"User-Agent": "Mozilla/5.0 Test browser"})
    assert client.post("/auth/login", json={"username": "admin", "password": PASSWORD}).status_code == 200
    context = client.get("/auth/sessions/context")
    assert context.status_code == 200
    client.headers.update({"Origin": "http://testserver", "X-CSRF-Token": context.json()["csrf_token"]})
    return client


@pytest.fixture
def enabled(auth, browser):
    response = browser.put("/auth/device/settings", json={"enabled": True})
    assert response.status_code == 200, response.text
    return TestClient(app)


def password_token(client):
    response = client.post("/auth/device/login", json={**META, "username": "admin", "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


def test_enrollment_default_off_and_additive_capability(auth):
    client = TestClient(app)
    status = client.get("/auth/status").json()
    assert status["tv_sign_in"] == {"supported": True, "enabled": False, "protocol_version": 1}
    assert status["session_management_supported"] is True
    assert client.post("/auth/device/authorize", json=META).status_code == 403
    assert (
        client.post("/auth/device/login", json={**META, "username": "admin", "password": PASSWORD}).status_code == 403
    )


def test_qr_and_manual_code_approval_issue_scoped_credential(auth, browser, enabled, monkeypatch):
    challenge = enabled.post("/auth/device/authorize", json=META).json()
    assert challenge["expires_in"] == 600 and challenge["interval"] == 5
    assert challenge["verification_path"] == "/activate"
    assert challenge["device_code"] not in challenge["verification_path_complete"]
    body = {"device_code": challenge["device_code"], "client_id": META["client_id"]}
    assert enabled.post("/auth/device/token", json=body).json()["error"] == "authorization_pending"
    code = challenge["user_code"].lower().replace("-", " ")
    inspected = browser.post("/auth/device/inspect", json={"user_code": code})
    assert inspected.status_code == 200 and inspected.json()["device_name"] == "Living room"
    assert browser.post("/auth/device/approve", json={"user_code": code}).status_code == 200
    # Advance only the registry's clock: no sleeps or expiry races in this test.
    now = auth.sessions.clock_ms()
    monkeypatch.setattr(auth.sessions, "clock_ms", lambda: now + 5001)
    result = enabled.post("/auth/device/token", json=body)
    assert result.status_code == 200, result.text
    token = result.json()["access_token"]
    assert token.startswith("fb_tv_") and result.json()["scope"] == "tv_panels"
    assert result.json()["expires_in"] == 31536000
    enabled.headers["Authorization"] = f"Bearer {token}"
    assert enabled.get("/auth/status").json()["auth_kind"] == "tv"
    assert enabled.get("/panels").status_code == 200
    enabled.headers.pop("Authorization")
    assert enabled.post("/auth/device/token", json=body).json()["error"] == "invalid_grant"


def test_direct_password_sign_in_and_revocation(auth, browser, enabled):
    result = password_token(enabled)
    enabled.headers["Authorization"] = "Bearer " + result["access_token"]
    rows = browser.get("/auth/sessions").json()
    row = next(row for row in rows["sessions"] if row["id"] == result["session_id"])
    assert row["kind"] == "tv" and row["method"] == "password"
    assert "digest" not in row and "access_token" not in row
    assert browser.delete("/auth/sessions/" + row["id"]).status_code == 200
    assert enabled.get("/panels").status_code == 401
    assert enabled.get("/panel/nonexistent/frame").status_code == 401
    assert browser.get("/auth/status").json()["authenticated"] is True


def test_sensitive_routes_require_cookie_origin_and_csrf(auth, browser, enabled):
    assert enabled.get("/auth/sessions").status_code == 401
    assert enabled.put("/auth/device/settings", json={"enabled": True}).status_code == 401
    before = browser.get("/auth/sessions").json()
    for headers in ({"Origin": "https://evil.invalid"}, {"X-CSRF-Token": "wrong"}, {"Origin": ""}):
        response = browser.post("/auth/sessions/revoke", json={"include_current": True}, headers=headers)
        assert response.status_code == 403
    assert browser.get("/auth/sessions").json()["current_session_id"] == before["current_session_id"]


def test_disable_enrollment_preserves_tokens_and_cancels_challenges(auth, browser, enabled):
    result = password_token(enabled)
    challenge = enabled.post("/auth/device/authorize", json=META).json()
    assert browser.put("/auth/device/settings", json={"enabled": False}).status_code == 200
    enabled.headers["Authorization"] = "Bearer " + result["access_token"]
    assert enabled.get("/panels").status_code == 200
    enabled.headers.pop("Authorization")
    assert (
        enabled.post(
            "/auth/device/token", json={"device_code": challenge["device_code"], "client_id": META["client_id"]}
        ).json()["error"]
        == "feature_disabled"
    )
    assert browser.put("/auth/device/settings", json={"enabled": True}).status_code == 200
    assert (
        enabled.post(
            "/auth/device/token", json={"device_code": challenge["device_code"], "client_id": META["client_id"]}
        ).json()["error"]
        == "invalid_grant"
    )


def test_all_auth_responses_are_not_cached(auth, browser):
    for path in ("/auth/status", "/auth/sessions", "/auth/sessions/context"):
        assert browser.get(path).headers["cache-control"] == "no-store"
