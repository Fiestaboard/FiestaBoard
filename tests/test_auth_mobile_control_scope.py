"""Phone sign-ins hold a ``control`` credential: wider than a TV, narrower than a browser.

The suite pins four properties:

* the iOS and Android client ids issue an ``fb_mob_`` Bearer with scope ``control``;
* that Bearer reaches exactly the routes in ``src/auth/scopes.py`` and nothing else,
  including none of the account, credential, backup, network or system routes;
* a TV Bearer still reaches only the panel routes;
* revocation works the way it does for TVs: per session, by self-revoke, by
  "sign out everywhere" and by an account rotation, and a cookie cannot rescue it.
"""

import re

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.auth import routes as routes_module
from src.auth import scopes
from src.auth import service as auth_module
from src.auth.device_models import AuthFlowError, DeviceMetadata
from src.auth.device_service import DeviceService
from src.plugins import routes as plugin_routes
from src.system import update_service
from src.system.models import UpdateCheckResponse

PASSWORD = "correct-password"
IOS = {"client_id": "fiestaboard-ios", "device_name": "Maya's iPhone", "app_version": "1.0"}
ANDROID = {"client_id": "fiestaboard-android", "device_name": "Pixel", "app_version": "1.0"}
TV = {"client_id": "fiestaboard-tvos", "device_name": "Living room", "app_version": "1.0"}


@pytest.fixture
def auth(tmp_path, monkeypatch):
    svc = auth_module.AuthService(tmp_path / "auth.json")
    svc.create_initial_user("admin", PASSWORD)
    svc.sessions.set_enrollment(True)
    monkeypatch.setattr(auth_module, "_service", svc)
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "true")
    monkeypatch.delenv("FIESTABOARD_MCP_TOKEN", raising=False)
    routes_module._FAILED_ATTEMPTS.clear()
    return svc


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Allowed routes that would call out to Docker Hub, GitHub or the plugin registry."""

    async def update_check():
        return UpdateCheckResponse(
            current_version="0.0.0", latest_version=None, update_available=False, package_url="", is_production=False
        )

    class Registry:
        def get_registry_entries(self):
            return []

    monkeypatch.setattr(update_service, "_perform_update_check", update_check)
    monkeypatch.setattr(plugin_routes, "_require_plugin_system", lambda: None)
    monkeypatch.setattr(plugin_routes, "get_plugin_registry", lambda: Registry())


@pytest.fixture
def browser(auth):
    client = TestClient(app, headers={"User-Agent": "Mozilla/5.0 Test browser"})
    assert client.post("/auth/login", json={"username": "admin", "password": PASSWORD}).status_code == 200
    context = client.get("/auth/sessions/context")
    client.headers.update({"Origin": "http://testserver", "X-CSRF-Token": context.json()["csrf_token"]})
    return client


def sign_in(metadata):
    response = TestClient(app).post("/auth/device/login", json={**metadata, "username": "admin", "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


def bearer_client(token):
    # Handlers that need hardware or plugins may fail; that is not an auth answer.
    return TestClient(app, headers={"Authorization": "Bearer " + token}, raise_server_exceptions=False)


@pytest.fixture
def phone(auth):
    token = sign_in(IOS)
    return bearer_client(token["access_token"]), token


@pytest.fixture
def tv(auth):
    token = sign_in(TV)
    return bearer_client(token["access_token"]), token


# --- Issuing ---------------------------------------------------------------


@pytest.mark.parametrize("metadata", [IOS, ANDROID])
def test_mobile_password_sign_in_issues_a_control_credential(auth, browser, metadata):
    token = sign_in(metadata)
    assert token["access_token"].startswith("fb_mob_")
    assert token["scope"] == "control"
    assert token["token_type"] == "Bearer" and token["expires_in"] == 31536000
    row = next(r for r in browser.get("/auth/sessions").json()["sessions"] if r["id"] == token["session_id"])
    assert row["kind"] == "mobile" and row["client_id"] == metadata["client_id"] and row["method"] == "password"
    assert "digest" not in row and "access_token" not in row


def test_tv_sign_in_is_unchanged(auth):
    token = sign_in(TV)
    assert token["access_token"].startswith("fb_tv_") and token["scope"] == "tv_panels"


def test_unknown_client_is_rejected(auth):
    response = TestClient(app).post(
        "/auth/device/login",
        json={"client_id": "fiestaboard-web", "device_name": "x", "app_version": "1", "username": "admin",
              "password": PASSWORD},
    )  # fmt: skip
    assert response.status_code == 422


def test_device_code_flow_is_not_offered_to_phones_yet(auth):
    # The /activate page shows a TV prompt. Until it can show what a phone may do
    # (H10 PR 2 with H11 pairing), a code approval must not mint a control credential.
    for metadata in (IOS, ANDROID):
        response = TestClient(app).post("/auth/device/authorize", json=metadata)
        assert response.status_code == 400
        assert response.json()["error"] == "unsupported_client"
    assert TestClient(app).post("/auth/device/authorize", json=TV).status_code == 200


def test_exchange_never_turns_a_tv_challenge_into_a_phone(auth):
    service = DeviceService(auth)
    grant = service.authorize(DeviceMetadata(**TV), "127.0.0.1")
    with pytest.raises(AuthFlowError) as raised:
        service.exchange(grant.device_code, "fiestaboard-ios")
    assert raised.value.error == "invalid_grant"


def test_disabled_enrollment_blocks_phone_sign_in(auth):
    auth.sessions.set_enrollment(False)
    response = TestClient(app).post("/auth/device/login", json={**IOS, "username": "admin", "password": PASSWORD})
    assert response.status_code == 403


def test_auth_status_identifies_the_phone(phone):
    client, _ = phone
    status = client.get("/auth/status").json()
    assert status["authenticated"] is True and status["username"] == "admin" and status["auth_kind"] == "mobile"


def test_kinds_do_not_cross(auth):
    service = DeviceService(auth)
    mobile = service.login("admin", PASSWORD, DeviceMetadata(**IOS)).access_token
    tv = service.login("admin", PASSWORD, DeviceMetadata(**TV)).access_token
    assert service.authenticate_mobile(mobile) is not None and service.authenticate_tv(tv) is not None
    assert service.authenticate_tv(mobile) is None and service.authenticate_mobile(tv) is None
    # Swapping the prefix changes the digest, so it cannot re-badge a token.
    assert service.authenticate_tv("fb_tv_" + mobile.removeprefix("fb_mob_")) is None
    assert service.authenticate_mobile("fb_mob_" + tv.removeprefix("fb_tv_")) is None


# --- Scope: what a phone may reach ------------------------------------------

CONTROL_ALLOWED = [
    ("GET", "/v1/status", None),
    ("GET", "/v1/boards", None),
    ("GET", "/api/v1/status", None),
    ("GET", "/v1/health", None),
    ("GET", "/status", None),
    ("GET", "/api/status", None),
    ("GET", "/version", None),
    ("GET", "/silence-status", None),
    ("GET", "/settings/temporary-override", None),
    ("DELETE", "/settings/temporary-override", None),
    ("GET", "/settings/active-page", None),
    ("POST", "/templates/render/live", {}),
    ("GET", "/templates/variables", None),
    ("GET", "/outputs", None),
    ("GET", "/oauth/connections", None),
    ("POST", "/schedules/validate", {}),
    ("GET", "/schedules", None),
    ("GET", "/pages", None),
    ("GET", "/collections", None),
    ("GET", "/plugins", None),
    ("GET", "/plugins/registry", None),
    ("POST", "/pages/import/preview", {}),
    ("GET", "/panels", None),
    ("PATCH", "/panels/missing", {"name": "Renamed"}),
    ("GET", "/triggers", None),
    ("GET", "/system/update-check", None),
    ("GET", "/config/general", None),
    # H11: the phone approves a TV's code (an unknown code is 400, not 401/403).
    ("POST", "/auth/device/inspect", {"user_code": "BCDF-GHJK"}),
    ("POST", "/auth/device/approve", {"user_code": "BCDF-GHJK"}),
    ("POST", "/auth/device/deny", {"user_code": "BCDF-GHJK"}),
    # H10b: the phone lists and signs out TVs (an unknown id is 404, not 401/403).
    ("GET", "/auth/device/tvs", None),
    ("DELETE", "/auth/device/tvs/unknown", None),
]


@pytest.mark.parametrize(("method", "path", "body"), CONTROL_ALLOWED)
def test_control_reaches_the_mobile_surface(phone, method, path, body):
    client, _ = phone
    response = client.request(method, path, json=body)
    assert response.status_code not in (401, 403), (method, path, response.status_code, response.text)


CONTROL_DENIED = [
    # Account and credential management stays with a real browser session.
    ("GET", "/auth/sessions", None),
    ("GET", "/auth/sessions/context", None),
    ("POST", "/auth/sessions/revoke", {"include_current": True}),
    ("DELETE", "/auth/sessions/other", None),
    ("PUT", "/auth/device/settings", {"enabled": False}),
    # H11: a phone may approve a TV (/auth/device/inspect|approve|deny), but it never
    # creates pairing codes for other phones.
    ("POST", "/auth/pairing", {}),
    ("DELETE", "/auth/pairing", None),
    ("POST", "/auth/change-password", {}),
    ("POST", "/auth/change-username", {}),
    ("POST", "/auth/disable", {}),
    ("GET", "/auth/mcp-token", None),
    ("POST", "/auth/mcp-token", {}),
    ("POST", "/auth/login", {"username": "admin", "password": PASSWORD}),
    ("POST", "/auth/logout", None),
    ("POST", "/mcp", {}),
    ("POST", "/api/mcp", {}),
    # Whole-install and host operations.
    ("GET", "/backup/export", None),
    ("POST", "/backup/import", {}),
    ("POST", "/system/update", {}),
    ("POST", "/system/restart", None),
    ("POST", "/system/shutdown", None),
    ("POST", "/system/channel", {}),
    ("POST", "/network/wifi/connect", {}),
    ("GET", "/network/wifi/saved", None),
    ("GET", "/logs", None),
    # Installing code.
    ("POST", "/plugins/install", {}),
    ("POST", "/plugins/registry/x/install", None),
    ("DELETE", "/plugins/x/uninstall", None),
    ("POST", "/plugins/x/update", None),
    ("POST", "/plugins/updates/apply", {}),
    ("POST", "/pages/import", {}),
    ("POST", "/outputs/x/install", {}),
    # Stored secrets and integrations that hold credentials.
    ("GET", "/settings/ai", None),
    ("GET", "/api/settings/ai", None),
    ("GET", "/settings/mqtt", None),
    ("GET", "/settings/all", None),
    ("GET", "/config", None),
    ("GET", "/config/full", None),
    ("GET", "/config/board", None),
    ("PUT", "/config/general", {}),
    ("POST", "/generic-data/test-fetch", {}),
    ("POST", "/ai/operations", {}),
    ("POST", "/pages/ai/chat", {}),
    ("POST", "/debug/fill", {}),
    ("POST", "/debug/blank", {}),
    # Near-misses of allowed paths.
    ("GET", "/status/", None),
    ("GET", "/statusx", None),
    ("GET", "/v1x", None),
    ("GET", "/panels/a/b", None),
    ("POST", "/version", None),
]


@pytest.mark.parametrize(("method", "path", "body"), CONTROL_DENIED)
def test_control_denies_everything_else(phone, method, path, body):
    client, _ = phone
    response = client.request(method, path, json=body)
    assert response.status_code == 403, (method, path, response.status_code)
    assert response.json()["error"] == "forbidden"


@pytest.mark.parametrize("path", ["/v1/status", "/status", "/auth/status"])
def test_head_is_not_in_any_scope(phone, path):
    client, _ = phone
    assert client.head(path).status_code == 403


def test_network_bound_routes_answer_from_the_stubs(phone):
    client, _ = phone
    assert client.get("/system/update-check").json()["update_available"] is False
    assert client.get("/plugins/registry").json()["entries"] == []


def test_control_works_alongside_a_configured_api_token(phone, monkeypatch):
    client, _ = phone
    monkeypatch.setenv("FIESTABOARD_MCP_TOKEN", "operator-api-token")
    assert client.get("/v1/status").status_code not in (401, 403)
    assert client.post("/mcp", json={}).status_code == 403


def test_invalid_mobile_token_is_never_anonymous(auth):
    client = bearer_client("fb_mob_not-a-real-token")
    for path in ("/v1/status", "/status", "/v1/health", "/auth/status"):
        response = client.get(path)
        assert response.status_code == 401, path
        assert response.json()["error"] == "unauthorized"


# --- Scope: TV confinement is unchanged ------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [row for row in CONTROL_ALLOWED if not row[1].startswith(("/panels", "/panel/"))],
)
def test_tv_still_cannot_reach_control_routes(tv, method, path, body):
    client, _ = tv
    assert client.request(method, path, json=body).status_code == 403, (method, path)


def test_tv_patch_limits_survive(tv):
    client, _ = tv
    assert client.patch("/panels/missing", json={"name": "Renamed"}).status_code == 403
    assert client.patch("/panels/missing", json={"calibration_scale": 1.0}).status_code == 404


# --- Revocation ------------------------------------------------------------


def test_browser_revokes_a_phone(auth, browser, phone):
    client, token = phone
    assert client.get("/v1/status").status_code == 200
    assert browser.delete("/auth/sessions/" + token["session_id"]).status_code == 200
    assert client.get("/v1/status").status_code == 401
    assert client.get("/status").status_code == 401
    assert browser.get("/auth/status").json()["authenticated"] is True


def test_phone_signs_itself_out_only(auth, phone, tv):
    client, _ = phone
    tv_client, _ = tv
    assert client.delete("/auth/device/session").status_code == 200
    assert client.get("/v1/status").status_code == 401
    assert tv_client.get("/panels").status_code == 200


def test_sign_out_everywhere_revokes_phones(auth, browser, phone):
    client, _ = phone
    assert browser.post("/auth/sessions/revoke", json={"include_current": False}).status_code == 200
    assert client.get("/v1/status").status_code == 401


def test_account_rotation_revokes_phones(auth, phone):
    client, _ = phone
    auth.invalidate_all_sessions("admin")
    assert client.get("/v1/status").status_code == 401


def test_cookie_cannot_rescue_a_revoked_phone(auth, phone):
    client, token = phone
    client.cookies.set("fiestaboard_session", auth.authenticate("admin", PASSWORD))
    auth.sessions.revoke_session("admin", token["session_id"])
    assert client.get("/v1/status").status_code == 401
    assert client.get("/settings/temporary-override").status_code == 401


def test_phone_token_expires_after_a_year(auth, phone):
    client, _ = phone
    now = auth.sessions.clock_ms()
    auth.sessions.clock_ms = lambda: now + 366 * 24 * 3600 * 1000
    assert client.get("/v1/status").status_code == 401
    assert client.get("/auth/status").status_code == 401


def test_phone_sign_in_shares_the_password_lockout(auth):
    client = TestClient(app)
    wrong = {**IOS, "username": "admin", "password": "wrong-password"}
    for _ in range(10):
        assert client.post("/auth/device/login", json=wrong).status_code == 401
    locked = client.post("/auth/device/login", json={**IOS, "username": "admin", "password": PASSWORD})
    assert locked.status_code == 429 and locked.headers["retry-after"] == "60"
    # The bucket is the browser login's too.
    assert client.post("/auth/login", json={"username": "admin", "password": PASSWORD}).status_code == 429


def test_disabling_enrollment_keeps_existing_phones(auth, phone):
    client, _ = phone
    auth.sessions.set_enrollment(False)
    assert client.get("/v1/status").status_code == 200


# --- The policy table itself -----------------------------------------------


def _templates():
    schema = TestClient(app).get("/internal/openapi.json").json()
    for path, operations in schema["paths"].items():
        for method in operations:
            yield method.upper(), path


def _routes():
    for method, path in _templates():
        yield method, re.sub(r"\{[^}]+\}", "sample", path)


def test_every_control_rule_names_a_real_route():
    routes = list(_routes())
    for rule in scopes.CONTROL_RULES:
        assert any(rule.matches(m, p) for m, p in routes), f"dead control rule: {rule}"


def test_control_is_a_strict_subset_of_the_api():
    routes = list(_routes())
    allowed = {(m, p) for m, p in routes if scopes.permits(scopes.CONTROL, m, p)}
    denied = {(m, p) for m, p in routes if not scopes.permits(scopes.CONTROL, m, p)}
    assert allowed and denied
    # Nothing that manages credentials, the host or installed code is in the scope.
    for method, path in allowed:
        assert not path.startswith(("/auth/sessions", "/auth/mcp-token", "/backup", "/network", "/mcp")), path
        # ``/v1/install`` is the install's settings resource (schedule switch, default page), not an installer.
        if path == "/v1/install":
            continue
        assert not re.search(r"/(install|uninstall|update|restart|shutdown|rollback)$", path), (method, path)


def test_literal_routes_never_ride_a_wildcard():
    # A fixed path such as /plugins/registry must be allowed by its own rule, not
    # because it happens to fit /plugins/{}. /v1 is allowed whole by design.
    for method, template in _templates():
        if "{" in template or template.startswith("/v1") or not scopes.permits(scopes.CONTROL, method, template):
            continue
        assert any(rule.literal and rule.matches(method, template) for rule in scopes.CONTROL_RULES), (
            method,
            template,
        )


def test_tv_scope_is_unchanged():
    assert scopes.permits(scopes.TV_PANELS, "GET", "/panels")
    assert scopes.permits(scopes.TV_PANELS, "GET", "/panel/a/frame")
    assert scopes.permits(scopes.TV_PANELS, "PATCH", "/panels/a")
    assert scopes.permits(scopes.TV_PANELS, "DELETE", "/auth/device/session")
    assert not scopes.permits(scopes.TV_PANELS, "GET", "/v1/status")
    assert not scopes.permits(scopes.TV_PANELS, "GET", "/api/panels")


def test_client_scope_mapping():
    assert scopes.scope_for_client("fiestaboard-ios") == scopes.CONTROL
    assert scopes.scope_for_client("fiestaboard-android") == scopes.CONTROL
    assert scopes.scope_for_client("fiestaboard-tvos") == scopes.TV_PANELS
    assert scopes.scope_for_client("fiestaboard-androidtv") == scopes.TV_PANELS
