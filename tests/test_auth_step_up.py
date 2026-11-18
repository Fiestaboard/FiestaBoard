"""H21s: a phone steps up (re-enters the password) before tier-2 actions.

Pinned here:

* only a signed-in phone can step up, read or end its own elevation;
* wrong passwords count toward the shared login lockout;
* a tier-2 route answers ``403 step_up_required`` until the phone steps up, and
  again once the ten minutes pass, the step-up is ended, or the sign-in is revoked;
* the elevation belongs to one phone sign-in: another phone, a TV or a browser
  never inherits it, and nothing token-like is ever returned.
"""

import re

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.auth import routes as routes_module
from src.auth import scopes
from src.auth import service as auth_module
from src.auth.step_up import STEP_UP_SECONDS

PASSWORD = "correct-password"
IOS = {"client_id": "fiestaboard-ios", "device_name": "Maya's iPhone", "app_version": "1.0"}
ANDROID = {"client_id": "fiestaboard-android", "device_name": "Pixel", "app_version": "1.0"}
TV = {"client_id": "fiestaboard-tvos", "device_name": "Living room", "app_version": "1.0"}

# A harmless, read-only route made tier 2 for these tests. Real tier-2 rows are
# added (with their own tests) by the tickets that widen the phone.
TIER2 = ("GET", "/logs")


@pytest.fixture
def auth(tmp_path, monkeypatch):
    svc = auth_module.AuthService(tmp_path / "auth.json")
    svc.create_initial_user("admin", PASSWORD)
    svc.sessions.set_enrollment(True)
    monkeypatch.setattr(auth_module, "_service", svc)
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "true")
    monkeypatch.delenv("FIESTABOARD_MCP_TOKEN", raising=False)
    routes_module._FAILED_ATTEMPTS.clear()
    yield svc
    routes_module._FAILED_ATTEMPTS.clear()


@pytest.fixture
def tier2(monkeypatch):
    monkeypatch.setattr(scopes, "CONTROL_STEP_UP_RULES", scopes._rules(TIER2))
    return TIER2


def sign_in(metadata):
    response = TestClient(app).post("/auth/device/login", json={**metadata, "username": "admin", "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


def bearer(token):
    return TestClient(app, headers={"Authorization": "Bearer " + token}, raise_server_exceptions=False)


@pytest.fixture
def phone(auth):
    token = sign_in(IOS)
    return bearer(token["access_token"]), token


def elevate(client, password=PASSWORD):
    return client.post("/auth/device/elevate", json={"password": password})


# --- The step-up endpoint ----------------------------------------------------


def test_phone_steps_up_for_ten_minutes(phone):
    client, _ = phone
    assert client.get("/auth/device/elevate").json() == {"elevated": False, "elevated_until": None, "expires_in": 0}
    response = elevate(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["elevated"] is True and body["expires_in"] == STEP_UP_SECONDS == 600
    assert set(body) == {"elevated", "elevated_until", "expires_in"}  # nothing token-like
    assert client.get("/auth/device/elevate").json()["elevated"] is True
    assert response.headers["cache-control"] == "no-store"


def test_wrong_password_is_refused(phone):
    client, _ = phone
    response = elevate(client, "wrong-password")
    assert response.status_code == 401
    assert response.json()["error"] == "invalid_credentials"
    assert client.get("/auth/device/elevate").json()["elevated"] is False


def test_step_up_shares_the_login_lockout(auth, phone):
    client, _ = phone
    for _ in range(10):
        assert elevate(client, "wrong-password").status_code in (401, 429)
    assert elevate(client).status_code == 429
    # The bucket is the browser login's and the phone sign-in's too.
    assert TestClient(app).post("/auth/login", json={"username": "admin", "password": PASSWORD}).status_code == 429
    login = TestClient(app).post("/auth/device/login", json={**IOS, "username": "admin", "password": PASSWORD})
    assert login.status_code == 429


def test_a_browser_lockout_blocks_step_up(auth, phone):
    client, _ = phone
    browser = TestClient(app)
    for _ in range(10):
        browser.post("/auth/login", json={"username": "admin", "password": "wrong-password"})
    assert elevate(client).status_code == 429


def test_step_up_is_rate_limited_per_phone(auth, phone, monkeypatch):
    client, _ = phone
    # Keep the IP lockout out of the way to see the per-sign-in limit.
    monkeypatch.setattr(routes_module, "_check_lockout", lambda ip: None)
    for _ in range(10):
        assert elevate(client, "wrong-password").status_code == 401
    assert elevate(client).status_code == 429


def test_password_is_bounded(phone):
    client, _ = phone
    assert elevate(client, "").status_code == 422
    assert elevate(client, "x" * 1025).status_code == 422
    extra = client.post("/auth/device/elevate", json={"password": PASSWORD, "username": "someone"})
    assert extra.status_code == 422


def test_ending_step_up(phone):
    client, _ = phone
    assert elevate(client).status_code == 200
    assert client.delete("/auth/device/elevate").json()["elevated"] is False
    assert client.get("/auth/device/elevate").json()["elevated"] is False


@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
def test_only_a_phone_can_step_up(auth, method):
    body = {"password": PASSWORD} if method == "POST" else None
    # No credential at all.
    assert TestClient(app).request(method, "/auth/device/elevate", json=body).status_code == 401
    # A browser session: step-up is a phone concept, never a browser one.
    browser = TestClient(app)
    assert browser.post("/auth/login", json={"username": "admin", "password": PASSWORD}).status_code == 200
    assert browser.request(method, "/auth/device/elevate", json=body).status_code == 401
    # A TV: outside its scope.
    tv = bearer(sign_in(TV)["access_token"])
    assert tv.request(method, "/auth/device/elevate", json=body).status_code == 403
    # A forged phone token.
    assert bearer("fb_mob_forged").request(method, "/auth/device/elevate", json=body).status_code == 401


# --- Enforcement on tier-2 routes ------------------------------------------------


def test_tier2_needs_a_step_up(phone, tier2):
    client, _ = phone
    method, path = tier2
    refused = client.request(method, path)
    assert refused.status_code == 403
    assert refused.json()["error"] == "step_up_required" and refused.json()["code"] == "step_up_required"
    assert elevate(client).status_code == 200
    assert client.request(method, path).status_code not in (401, 403)
    # The nginx /api double form is the same route.
    assert client.request(method, "/api" + path).status_code not in (401, 403)


def test_tier2_without_rules_is_plain_forbidden(phone):
    client, _ = phone
    assert elevate(client).status_code == 200
    # Without a step-up rule, an elevation reaches nothing extra.
    response = client.request(*TIER2)
    assert response.status_code == 403 and response.json()["error"] == "forbidden"


def test_step_up_lapses_after_ten_minutes(auth, phone, tier2):
    client, _ = phone
    now = auth.sessions.clock_ms()
    auth.sessions.clock_ms = lambda: now
    assert elevate(client).status_code == 200
    auth.sessions.clock_ms = lambda: now + STEP_UP_SECONDS * 1000 - 1
    assert client.request(*tier2).status_code not in (401, 403)
    auth.sessions.clock_ms = lambda: now + STEP_UP_SECONDS * 1000
    assert client.request(*tier2).json()["error"] == "step_up_required"
    assert client.get("/auth/device/elevate").json()["elevated"] is False


def test_ending_step_up_closes_tier2(phone, tier2):
    client, _ = phone
    assert elevate(client).status_code == 200
    client.delete("/auth/device/elevate")
    assert client.request(*tier2).json()["error"] == "step_up_required"


def test_revoked_phone_loses_its_step_up(auth, phone, tier2):
    client, token = phone
    assert elevate(client).status_code == 200
    auth.sessions.revoke_session("admin", token["session_id"])
    assert client.request(*tier2).status_code == 401
    assert auth.sessions.elevated_until(token["session_id"]) is None


def test_account_rotation_ends_step_up(auth, phone, tier2):
    client, _ = phone
    assert elevate(client).status_code == 200
    auth.invalidate_all_sessions("admin")
    assert client.request(*tier2).status_code == 401


def test_step_up_belongs_to_one_phone(auth, phone, tier2):
    client, _ = phone
    other = bearer(sign_in(ANDROID)["access_token"])
    assert elevate(client).status_code == 200
    assert other.request(*tier2).json()["error"] == "step_up_required"
    assert other.get("/auth/device/elevate").json()["elevated"] is False


def test_a_tv_never_reaches_tier2(auth, tier2):
    tv = bearer(sign_in(TV)["access_token"])
    response = tv.request(*tier2)
    assert response.status_code == 403 and response.json()["error"] == "forbidden"


def test_browser_sessions_are_unaffected(auth, tier2):
    browser = TestClient(app, raise_server_exceptions=False)
    assert browser.post("/auth/login", json={"username": "admin", "password": PASSWORD}).status_code == 200
    assert browser.request(*tier2).status_code not in (401, 403)


def test_step_up_rule_wins_over_an_ordinary_rule(phone, monkeypatch):
    client, _ = phone
    assert scopes.permits(scopes.CONTROL, "GET", "/status")
    monkeypatch.setattr(scopes, "CONTROL_STEP_UP_RULES", scopes._rules(("GET", "/status")))
    assert scopes.requires_step_up(scopes.CONTROL, "GET", "/status")
    assert client.get("/status").json()["error"] == "step_up_required"


def test_requires_step_up_is_control_only(tier2):
    method, path = tier2
    assert scopes.requires_step_up(scopes.CONTROL, method, path)
    assert scopes.requires_step_up(scopes.CONTROL, method.lower(), "/api" + path)
    assert not scopes.requires_step_up(scopes.TV_PANELS, method, path)
    assert not scopes.permits(scopes.TV_PANELS, method, path)


# --- The table ---------------------------------------------------------------------


def _routes():
    schema = TestClient(app).get("/internal/openapi.json").json()
    for path, operations in schema["paths"].items():
        for method in operations:
            yield method.upper(), re.sub(r"\{[^}]+\}", "sample", path)


def test_every_step_up_rule_names_a_real_route():
    routes = list(_routes())
    for rule in scopes.CONTROL_STEP_UP_RULES:
        assert any(rule.matches(m, p) for m, p in routes), f"dead step-up rule: {rule}"


def test_step_up_never_reaches_account_or_credential_management():
    # Tier 2 is for the hub's own operations. Accounts, passwords, sessions,
    # pairing and the API token stay with a browser, stepped up or not.
    for method, path in _routes():
        if scopes.requires_step_up(scopes.CONTROL, method, path):
            assert not path.startswith(("/auth/", "/mcp")), (method, path)
            assert path != "/plugins/install", "Install from Git stays browser-only"
