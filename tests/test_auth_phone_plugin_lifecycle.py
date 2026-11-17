"""H21c: a phone installs, updates and removes registry plugins, behind step-up.

* ``POST /plugins/updates/check`` is tier 1: it only asks whether updates exist.
* Registry install, update, update-all and uninstall are tier 2: ``403
  step_up_required`` until the phone re-enters the password, then the handler runs.
* Install from a Git URL stays browser-only, stepped up or not.
* A TV reaches none of it; a browser session is unchanged.
"""

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.auth import routes as routes_module
from src.auth import scopes
from src.auth import service as auth_module
from src.plugins import routes as plugin_routes

PASSWORD = "correct-password"
IOS = {"client_id": "fiestaboard-ios", "device_name": "Maya's iPhone", "app_version": "1.0"}
TV = {"client_id": "fiestaboard-tvos", "device_name": "Living room", "app_version": "1.0"}

TIER2 = [
    ("POST", "/plugins/registry/weather_x/install", "install_from_registry"),
    ("POST", "/plugins/weather_x/update", "apply_update"),
    ("POST", "/plugins/updates/apply", "apply_all_updates"),
    ("DELETE", "/plugins/weather_x/uninstall", "uninstall"),
]

GIT_INSTALL = ("POST", "/plugins/install", {"repository": "https://example.com/x/fiestaboard-plugin--x.git"})


class FakeService:
    """Records which lifecycle call ran, instead of cloning anything."""

    def __init__(self):
        self.calls = []

    async def install_from_registry(self, plugin_id):
        self.calls.append(("install_from_registry", plugin_id))

    async def install_from_git(self, repository, plugin_id=None, branch=None):
        self.calls.append(("install_from_git", repository))
        return "x"

    async def apply_update(self, plugin_id):
        self.calls.append(("apply_update", plugin_id))

    async def apply_all_updates(self):
        self.calls.append(("apply_all_updates", None))
        return {"updated": [], "failed": {}, "message": "Nothing to update."}

    def uninstall(self, plugin_id):
        self.calls.append(("uninstall", plugin_id))


class FakeRegistry:
    def check_for_updates(self):
        return {"weather_x": True}


@pytest.fixture
def service(monkeypatch):
    fake = FakeService()
    monkeypatch.setattr(plugin_routes, "_require_plugin_system", lambda: None)
    monkeypatch.setattr(plugin_routes, "_plugin_service", lambda: fake)
    monkeypatch.setattr(plugin_routes, "get_plugin_registry", lambda: FakeRegistry())
    return fake


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


def bearer(metadata):
    response = TestClient(app).post("/auth/device/login", json={**metadata, "username": "admin", "password": PASSWORD})
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return TestClient(app, headers={"Authorization": "Bearer " + token}, raise_server_exceptions=False)


@pytest.fixture
def phone(auth):
    return bearer(IOS)


def step_up(client):
    assert client.post("/auth/device/elevate", json={"password": PASSWORD}).status_code == 200


def test_update_check_is_tier_one(phone, service):
    response = phone.post("/plugins/updates/check")
    assert response.status_code == 200, response.text
    assert response.json() == {"checked": 1, "updates_available": ["weather_x"]}


@pytest.mark.parametrize(("method", "path", "call"), TIER2)
def test_lifecycle_needs_a_step_up(phone, service, method, path, call):
    refused = phone.request(method, path)
    assert refused.status_code == 403
    assert refused.json()["error"] == "step_up_required"
    assert service.calls == []


@pytest.mark.parametrize(("method", "path", "call"), TIER2)
def test_lifecycle_runs_after_step_up(phone, service, method, path, call):
    step_up(phone)
    response = phone.request(method, path)
    assert response.status_code in (200, 201), response.text
    assert [name for name, _ in service.calls] == [call]


@pytest.mark.parametrize(("method", "path", "call"), TIER2)
def test_lifecycle_closes_when_the_step_up_lapses(auth, phone, service, method, path, call):
    now = auth.sessions.clock_ms()
    auth.sessions.clock_ms = lambda: now
    step_up(phone)
    auth.sessions.clock_ms = lambda: now + 600_000
    assert phone.request(method, path).json()["error"] == "step_up_required"
    assert service.calls == []


@pytest.mark.parametrize("elevated", [False, True])
def test_git_install_stays_browser_only(phone, service, elevated):
    if elevated:
        step_up(phone)
    method, path, body = GIT_INSTALL
    response = phone.request(method, path, json=body)
    assert response.status_code == 403 and response.json()["error"] == "forbidden"
    assert service.calls == []


def test_a_tv_reaches_no_lifecycle_route(auth, service):
    tv = bearer(TV)
    for method, path, _ in [*TIER2, ("POST", "/plugins/updates/check", None)]:
        response = tv.request(method, path)
        assert response.status_code == 403 and response.json()["error"] == "forbidden", path
    assert service.calls == []


def test_browser_is_unchanged(auth, service):
    browser = TestClient(app, raise_server_exceptions=False)
    assert browser.post("/auth/login", json={"username": "admin", "password": PASSWORD}).status_code == 200
    method, path, body = GIT_INSTALL
    assert browser.request(method, path, json=body).status_code == 201
    for method, path, _ in TIER2:
        assert browser.request(method, path).status_code in (200, 201), path


def test_the_tier_table():
    for method, path, _ in TIER2:
        assert scopes.requires_step_up(scopes.CONTROL, method, path), path
    assert not scopes.requires_step_up(scopes.CONTROL, "POST", "/plugins/updates/check")
    assert scopes.permits(scopes.CONTROL, "POST", "/plugins/updates/check")
    assert not scopes.permits(scopes.CONTROL, "POST", "/plugins/install")
