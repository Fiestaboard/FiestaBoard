"""A phone never points an installed plugin's stored key at a new address.

The display rule (H21a) applied to plugin settings: a phone that changes where a
plugin's key is sent (its address, protocol or sign-in fields) while the key
comes back masked, or is left out of a merged update, is refused with
``400 key_required``. Through every door a phone has: ``PUT /plugins/{id}/config``,
``PATCH /v1/plugins/{id}``, FiestaBot's ``configure_plugin`` and
``POST /ai/operations``. Other edits, and a browser, are unchanged.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from src.ai.mcp_bridge import ToolOutcome
from src.ai.phone_tools import PhoneToolBackend, needs_key
from src.api_server import app
from src.auth import phone_policy
from src.auth import routes as routes_module
from src.auth import service as auth_module
from src.config_manager import ConfigManager
from src.plugins import routes as plugin_routes

PASSWORD = "correct-password"
IOS = {"client_id": "fiestaboard-ios", "device_name": "Maya's iPhone", "app_version": "1.0"}
PLUGIN = "home_x"
KEY = "test_plugin_token_stored"
STORED = {"enabled": True, "base_url": "http://192.168.1.30:8123", "access_token": KEY, "entity": "sensor.porch"}


class FakeService:
    def __init__(self):
        self.saved = []

    def update_plugin_config(self, plugin_id, config):
        self.saved.append((plugin_id, config))
        return config


@pytest.fixture
def config(tmp_path, monkeypatch):
    cm = ConfigManager(config_path=str(tmp_path / "config.json"))
    cm.set_plugin_config(PLUGIN, dict(STORED))
    monkeypatch.setattr("src.config_manager.get_config_manager", lambda: cm)
    return cm


@pytest.fixture
def service(monkeypatch, config):
    fake = FakeService()
    monkeypatch.setattr(plugin_routes, "_require_plugin_system", lambda: None)
    monkeypatch.setattr(plugin_routes, "_plugin_service", lambda: fake)

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


@pytest.fixture
def phone(auth, service):
    response = TestClient(app).post("/auth/device/login", json={**IOS, "username": "admin", "password": PASSWORD})
    token = response.json()["access_token"]
    return TestClient(app, headers={"Authorization": "Bearer " + token}, raise_server_exceptions=False)


@pytest.fixture
def browser(auth, service):
    client = TestClient(app, raise_server_exceptions=False)
    assert client.post("/auth/login", json={"username": "admin", "password": PASSWORD}).status_code == 200
    return client


def echoed(**changes):
    return {**STORED, "access_token": "***", **changes}


MOVES = [
    {"base_url": "https://attacker.example.net"},
    {"base_url": "http://192.168.1.31:8123"},
    {"ssl": True},
    {"entity": "203.0.113.7:443"},  # a field holding an address, whatever its name
    {"entity": "https://attacker.example.net"},
]


# --- PUT /plugins/{id}/config -----------------------------------------------------------


@pytest.mark.parametrize("changes", MOVES)
def test_moving_a_plugin_with_its_key_masked_is_refused(phone, service, changes):
    response = phone.put(f"/plugins/{PLUGIN}/config", json={"config": echoed(**changes)})
    assert response.status_code == 400, response.text
    assert response.json()["error"] == "key_required"
    assert service.saved == []


def test_moving_a_plugin_with_its_key_typed_again_is_allowed(phone, service):
    body = {"config": echoed(base_url="http://192.168.1.31:8123", access_token="test_retyped_token")}
    assert phone.put(f"/plugins/{PLUGIN}/config", json=body).status_code == 200
    assert len(service.saved) == 1


def test_moving_a_plugin_with_its_key_left_out_is_allowed(phone, service):
    # Replacing the config without the key keeps no stored key to send.
    config = {k: v for k, v in echoed(base_url="https://attacker.example.net").items() if k != "access_token"}
    assert phone.put(f"/plugins/{PLUGIN}/config", json={"config": config}).status_code == 200


@pytest.mark.parametrize("changes", [{}, {"entity": "sensor.garage"}, {"enabled": False}])
def test_other_plugin_edits_keep_the_masked_key(phone, service, changes):
    assert phone.put(f"/plugins/{PLUGIN}/config", json={"config": echoed(**changes)}).status_code == 200
    assert len(service.saved) == 1


def test_browser_is_not_held_to_key_re_entry(browser, service):
    body = {"config": echoed(base_url="https://other.example.org")}
    assert browser.put(f"/plugins/{PLUGIN}/config", json=body).status_code == 200


# --- PATCH /v1/plugins/{id} --------------------------------------------------------------


def test_v1_patch_is_held_to_the_same_rule(phone, service):
    response = phone.patch(f"/v1/plugins/{PLUGIN}", json={"config": echoed(base_url="https://attacker.example.net")})
    assert response.status_code == 400 and response.json()["error"] == "key_required", response.text
    assert service.saved == []
    # An edit that keeps the key's address is saved (the fake detail read answers no model).
    phone.patch(f"/v1/plugins/{PLUGIN}", json={"config": echoed(entity="sensor.garage")})
    assert [plugin_id for plugin_id, _config in service.saved] == [PLUGIN]


# --- FiestaBot: configure_plugin merges into the stored config ----------------------------


def test_configure_plugin_with_only_a_new_address_needs_the_key(config):
    assert needs_key("configure_plugin", {"plugin_id": PLUGIN, "config": {"base_url": "https://attacker.example.net"}})
    assert needs_key("install_plugin", {"plugin_id": PLUGIN, "initial_config": {"base_url": "https://x.example.net"}})
    assert not needs_key(
        "configure_plugin",
        {"plugin_id": PLUGIN, "config": {"base_url": "https://x.example.net", "access_token": "test_typed"}},
    )
    assert not needs_key("configure_plugin", {"plugin_id": PLUGIN, "config": {"entity": "sensor.garage"}})
    assert not needs_key("configure_plugin", {"plugin_id": "not_configured", "config": {"base_url": "https://x"}})


class Inner:
    def __init__(self):
        self.calls = []

    async def list_tools(self):
        return []

    async def call_tool(self, name, args):
        self.calls.append(name)
        return ToolOutcome(status="ok", result={"status": "ok"})


def test_the_phone_tool_backend_refuses_a_key_move(config):
    inner = Inner()
    backend = PhoneToolBackend(inner, lambda: False)
    moved = asyncio.run(
        backend.call_tool("configure_plugin", {"plugin_id": PLUGIN, "config": {"base_url": "https://a.example.net"}})
    )
    assert moved.status == "blocked" and moved.result["code"] == "key_required"
    assert inner.calls == []
    kept = asyncio.run(backend.call_tool("configure_plugin", {"plugin_id": PLUGIN, "config": {"entity": "sensor.x"}}))
    assert kept.status == "ok" and inner.calls == ["configure_plugin"]


def test_the_step_up_check_runs_off_the_event_loop(config):
    import threading

    loop_thread = []
    checked_on = []

    def is_elevated():
        checked_on.append(threading.get_ident())
        return False

    async def run():
        loop_thread.append(threading.get_ident())
        return await PhoneToolBackend(Inner(), is_elevated).call_tool("restart_system", {})

    outcome = asyncio.run(run())
    assert outcome.result["code"] == "step_up_required"
    assert checked_on and checked_on[0] != loop_thread[0]


def test_ai_operations_refuses_a_key_move(phone, config, monkeypatch):
    ran = []

    async def dispatch(op, args):
        ran.append(op)
        return {"status": "ok"}

    monkeypatch.setattr("src.ai.routes._dispatch", dispatch)
    body = {
        "op": "update_plugin_config",
        "args": {"plugin_id": PLUGIN, "config": {"base_url": "https://a.example.net"}},
    }
    response = phone.post("/ai/operations", json=body)
    assert response.status_code == 400 and response.json()["error"] == "key_required", response.text
    assert ran == []


def test_environment_supplied_keys_count_as_stored(config, monkeypatch):
    monkeypatch.setattr(
        config,
        "get_plugin_config",
        lambda pid, include_env_overrides=True: (
            {**STORED, "access_token": ""} if not include_env_overrides else dict(STORED)
        ),
    )
    assert phone_policy.plugin_config_needs_key(PLUGIN, {"base_url": "https://a.example.net"}, merge=True)


# --- Options lookups on draft settings ---------------------------------------------------


def test_an_options_lookup_on_a_moved_draft_needs_the_key(phone, service):
    body = {"draft_config": {"base_url": "https://attacker.example.net", "access_token": "***"}}
    response = phone.post(f"/plugins/{PLUGIN}/options/entities", json=body)
    assert response.status_code == 400 and response.json()["error"] == "key_required", response.text


def test_an_options_lookup_on_other_draft_fields_is_not_refused(phone, service):
    body = {"draft_config": {"entity": "sensor.garage", "access_token": "***"}}
    response = phone.post(f"/plugins/{PLUGIN}/options/entities", json=body)
    assert response.json().get("error") != "key_required", response.text


# --- Edges of the rule -----------------------------------------------------------------


def test_an_address_pinned_by_the_environment_still_needs_the_key(config, monkeypatch):
    # The environment supplies base_url now; once it is removed, the saved one is used.
    live = {**STORED, "base_url": "http://192.168.1.40:8123"}
    monkeypatch.setattr(
        config,
        "get_plugin_config",
        lambda pid, include_env_overrides=True: dict(live if include_env_overrides else STORED),
    )
    moved = {"base_url": "https://attacker.example.net", "access_token": "***"}
    assert phone_policy.plugin_config_needs_key(PLUGIN, moved, merge=True)
    assert phone_policy.plugin_config_needs_key(PLUGIN, {**STORED, **moved}, merge=False)


@pytest.mark.parametrize("field", ["subdomain", "region", "tenant", "workspace_id", "account", "cluster"])
def test_account_and_region_fields_count_as_connection(config, field):
    config.set_plugin_config(PLUGIN, {**STORED, field: "home"})
    assert phone_policy.plugin_config_needs_key(PLUGIN, {field: "attacker"}, merge=True)
