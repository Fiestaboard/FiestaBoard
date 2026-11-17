"""H21d: the phone's hub settings: general config, Wi-Fi, AI provider, update, backups.

Tier 1 (no step-up): ``PUT /config/general``; Wi-Fi status, saved, capability and
scan; the AI settings read (keys and header values masked) and the provider test.

Tier 2 (step-up): Wi-Fi join, disconnect and forget; ``PUT /settings/ai``; system
update, restart and shutdown; backup export (redacted for a phone) and import
(never re-cloning plugins from a phone).

Secrets: a phone never reads one, and never sends a stored one somewhere new:
moving an AI provider to another endpoint needs its key typed again.
"""

import json

import pytest
from fastapi.testclient import TestClient

import src.backup as backup_pkg
from src.api_server import app
from src.auth import phone_policy, scopes
from src.auth import routes as routes_module
from src.auth import service as auth_module
from src.backup.service import BackupService
from src.config_manager import ConfigManager
from src.network import routes as network_routes
from src.system import update_service

PASSWORD = "correct-password"
IOS = {"client_id": "fiestaboard-ios", "device_name": "Maya's iPhone", "app_version": "1.0"}
TV = {"client_id": "fiestaboard-tvos", "device_name": "Living room", "app_version": "1.0"}

SECRET_KEY = "test_sk_stored_secret_value"
SECRET_HEADER = "Bearer test_header_secret"
PROVIDER = {
    "id": "acme",
    "name": "Acme",
    "base_url": "https://llm.example.com/v1",
    "protocol": "openai",
    "api_key": SECRET_KEY,
    "headers": {"X-Org": SECRET_HEADER},
    "models": ["m1"],
    "default_model": "m1",
}

TIER1 = [
    ("PUT", "/config/general", {"instance_name": "Kitchen hub"}),
    ("GET", "/network/wifi/capability", None),
    ("GET", "/network/wifi/status", None),
    ("GET", "/network/wifi/saved", None),
    ("POST", "/network/wifi/scan", None),
    ("GET", "/settings/ai", None),
    ("GET", "/settings/ai/providers/acme/models", None),
    ("POST", "/settings/ai/test", {"provider_id": "acme"}),
]

TIER2 = [
    ("POST", "/network/wifi/connect", {"ssid": "Home", "password": "example-wifi-pass"}),
    ("POST", "/network/wifi/disconnect", None),
    ("DELETE", "/network/wifi/saved/Home", None),
    ("PUT", "/settings/ai", {"enabled": True}),
    ("POST", "/system/update", None),
    ("POST", "/system/restart", None),
    ("POST", "/system/shutdown", None),
    ("GET", "/backup/export", None),
    ("POST", "/backup/import?reinstall_plugins=false", None),
]

STILL_DENIED = [
    ("POST", "/system/channel", {"channel": "beta"}),
    ("POST", "/system/update/rollback", {}),
    ("POST", "/system/update/auto", {"interval": "daily"}),
    ("GET", "/settings/mqtt", None),
    ("GET", "/config/board", None),
    ("GET", "/config", None),
]


class Recorder:
    def __init__(self):
        self.calls = []


@pytest.fixture
def calls(monkeypatch):
    """Stub the host: nothing may really join Wi-Fi, update or restart."""
    record = Recorder()

    class Capability:
        available = True
        reason = None

    class Wifi:
        def capability(self):
            return Capability()

        def __getattr__(self, name):
            def call(*args, **kwargs):
                record.calls.append(name)
                raise network_routes.WiFiError("stubbed")

            if name in ("connect", "disconnect", "forget"):

                async def acall(*args, **kwargs):
                    return call()

                return acall
            return call

    async def sidecar(*args, **kwargs):
        record.calls.append(("sidecar", args))
        raise update_service.SidecarError(503, "stubbed")

    monkeypatch.setattr(network_routes, "get_wifi_service", lambda: Wifi())
    monkeypatch.setattr(update_service, "apply_update", sidecar)
    monkeypatch.setattr(update_service, "perform_sidecar_action", sidecar)
    return record


@pytest.fixture
def config(tmp_path, monkeypatch):
    cm = ConfigManager(config_path=str(tmp_path / "config.json"))
    cm.set_ai_providers({"enabled": True, "providers": [dict(PROVIDER)], "default_provider_id": "acme"})
    monkeypatch.setattr("src.api_server.get_config_manager", lambda: cm)
    return cm


@pytest.fixture
def backups(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    (data / "config.json").write_text(
        json.dumps(
            {
                "board": {"api_key": "test_board_key", "host": "192.0.2.10"},
                "features": {"weather": {"enabled": True, "openweathermap_api_key": "test_owm", "city": "Paris"}},
                "ai_providers": {"providers": [PROVIDER]},
            }
        )
    )
    (data / "settings.json").write_text(json.dumps({"mqtt": {"password": "test_mqtt", "host": "mqtt.local"}}))
    service = BackupService(data_dir=data)
    monkeypatch.setattr(backup_pkg, "get_backup_service", lambda: service)
    return service


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
def phone(auth, calls, config, backups):
    return bearer(IOS)


@pytest.fixture
def browser(auth, calls, config, backups):
    client = TestClient(app, raise_server_exceptions=False)
    assert client.post("/auth/login", json={"username": "admin", "password": PASSWORD}).status_code == 200
    return client


def step_up(client):
    assert client.post("/auth/device/elevate", json={"password": PASSWORD}).status_code == 200


def minimal_backup():
    return {"fiestaboard_backup": True, "schema_version": 1, "data": {}, "installed_plugins": []}


# --- The tier table ----------------------------------------------------------------


@pytest.mark.parametrize(("method", "path", "body"), TIER1)
def test_tier_one_needs_no_step_up(phone, method, path, body):
    response = phone.request(method, path, json=body)
    assert response.status_code not in (401, 403), (path, response.status_code, response.text)


@pytest.mark.parametrize(("method", "path", "body"), TIER2)
def test_tier_two_needs_a_step_up(phone, calls, method, path, body):
    if path.startswith("/backup/import"):
        body = minimal_backup()
    response = phone.request(method, path, json=body)
    assert response.status_code == 403, (path, response.text)
    assert response.json()["error"] == "step_up_required"
    assert calls.calls == []


@pytest.mark.parametrize(("method", "path", "body"), TIER2)
def test_tier_two_runs_after_step_up(phone, calls, method, path, body):
    if path.startswith("/backup/import"):
        body = minimal_backup()
    step_up(phone)
    response = phone.request(method, path, json=body)
    assert response.status_code not in (401, 403), (path, response.status_code, response.text)


@pytest.mark.parametrize("operation", ["connect", "disconnect", "forget"])
def test_wifi_changes_reach_the_service_only_after_step_up(phone, calls, operation):
    method, path, body = {
        "connect": TIER2[0],
        "disconnect": TIER2[1],
        "forget": TIER2[2],
    }[operation]
    phone.request(method, path, json=body)
    assert calls.calls == []
    step_up(phone)
    phone.request(method, path, json=body)
    assert calls.calls == [operation]


@pytest.mark.parametrize("path", ["/system/update", "/system/restart", "/system/shutdown"])
def test_host_actions_reach_the_sidecar_only_after_step_up(phone, calls, path):
    assert phone.post(path).json()["error"] == "step_up_required"
    assert calls.calls == []
    step_up(phone)
    assert phone.post(path).status_code == 503
    assert len(calls.calls) == 1


@pytest.mark.parametrize(("method", "path", "body"), STILL_DENIED)
def test_update_channel_rollback_and_raw_secrets_stay_browser_only(phone, method, path, body):
    step_up(phone)
    response = phone.request(method, path, json=body)
    assert response.status_code == 403 and response.json()["error"] == "forbidden", path


def test_a_tv_reaches_none_of_it(auth, calls, config, backups):
    tv = bearer(TV)
    for method, path, body in [*TIER1, *TIER2]:
        response = tv.request(method, path, json=body)
        assert response.status_code == 403 and response.json()["error"] == "forbidden", path


def test_general_config_is_saved_from_the_phone(phone):
    assert phone.put("/config/general", json={"instance_name": "Kitchen hub"}).status_code == 200
    assert phone.get("/config/general").json()["instance_name"] == "Kitchen hub"


# --- AI provider: no secret is read, none is sent somewhere new ------------------------


def test_phone_reads_ai_settings_masked(phone):
    body = phone.get("/settings/ai").json()
    provider = body["providers"][0]
    assert provider["api_key"] == "***"
    assert provider["headers"] == {"X-Org": "***"}
    assert SECRET_KEY not in json.dumps(body) and SECRET_HEADER not in json.dumps(body)


def test_browser_still_reads_headers(browser):
    assert browser.get("/settings/ai").json()["providers"][0]["headers"] == {"X-Org": SECRET_HEADER}


def provider_update(**changes):
    return {"providers": [{**PROVIDER, "api_key": "***", "headers": {"X-Org": "***"}, **changes}]}


@pytest.mark.parametrize(
    "changes",
    [
        {"base_url": "https://attacker.example.net/v1"},
        {"base_url": "http://llm.example.com/v1"},
        {"protocol": "anthropic"},
        {"base_url": "https://attacker.example.net/v1", "api_key": ""},
        {"base_url": "https://attacker.example.net/v1", "api_key": "test_new_key"},  # header still masked
    ],
)
def test_moving_a_provider_with_a_masked_secret_is_refused(phone, config, changes):
    step_up(phone)
    response = phone.put("/settings/ai", json=provider_update(**changes))
    assert response.status_code == 400, response.text
    assert response.json()["error"] == "key_required"
    stored = config.get_ai_provider("acme")
    assert stored["base_url"] == PROVIDER["base_url"] and stored["api_key"] == SECRET_KEY


def test_moving_a_provider_with_its_key_typed_again_is_allowed(phone, config):
    step_up(phone)
    update = provider_update(base_url="https://other.example.org/v1", api_key="test_new_key", headers={})
    assert phone.put("/settings/ai", json=update).status_code == 200
    stored = config.get_ai_provider("acme")
    assert stored["base_url"] == "https://other.example.org/v1" and stored["api_key"] == "test_new_key"


def test_editing_in_place_keeps_masked_secrets(phone, config):
    step_up(phone)
    assert phone.put("/settings/ai", json=provider_update(name="Acme 2", base_url=PROVIDER["base_url"] + "/")).status_code == 200
    stored = config.get_ai_provider("acme")
    assert stored["name"] == "Acme 2"
    assert stored["api_key"] == SECRET_KEY and stored["headers"] == {"X-Org": SECRET_HEADER}


def test_browser_is_not_held_to_key_re_entry(browser, config):
    update = provider_update(base_url="https://other.example.org/v1", headers={"X-Org": SECRET_HEADER})
    assert browser.put("/settings/ai", json=update).status_code == 200


@pytest.mark.parametrize(
    "draft",
    [
        {**PROVIDER, "api_key": "***", "base_url": "https://attacker.example.net/v1"},
        {**PROVIDER, "api_key": "", "base_url": "https://attacker.example.net/v1"},
        {**PROVIDER, "api_key": "test_typed", "headers": {"X-Org": "***"}},
    ],
)
def test_phone_cannot_test_a_draft_with_stored_secrets(phone, monkeypatch, draft):
    sent = []

    async def fake_test(provider, model=None):
        sent.append(provider)
        return {"ok": True, "message": "ok"}

    monkeypatch.setattr("src.ai.generator.test_provider", fake_test)
    response = phone.post("/settings/ai/test", json={"provider": draft})
    assert response.status_code == 400 and response.json()["error"] == "key_required"
    assert sent == []


def test_phone_tests_a_saved_provider_by_id(phone, monkeypatch):
    sent = []

    async def fake_test(provider, model=None):
        sent.append(provider["base_url"])
        return {"ok": True, "message": "ok"}

    monkeypatch.setattr("src.ai.generator.test_provider", fake_test)
    response = phone.post("/settings/ai/test", json={"provider_id": "acme"})
    assert response.status_code == 200, response.text
    assert sent == [PROVIDER["base_url"]]


# --- Backups ------------------------------------------------------------------------


def test_phone_export_is_redacted(phone):
    step_up(phone)
    response = phone.get("/backup/export")
    assert response.status_code == 200
    assert "redacted" in response.headers["content-disposition"]
    text = response.text
    for secret in ("test_board_key", "test_owm", "test_mqtt", SECRET_KEY, SECRET_HEADER):
        assert secret not in text, secret
    document = json.loads(text)
    assert document["redacted"] is True and "***" in document["redacted_note"]
    # Non-secret settings survive, so the file is still useful.
    assert document["data"]["config"]["features"]["weather"]["city"] == "Paris"
    assert document["data"]["settings"]["mqtt"]["host"] == "mqtt.local"


def test_browser_export_is_complete(browser):
    text = browser.get("/backup/export").text
    assert "test_board_key" in text and "redacted" not in json.loads(text)


def test_phone_import_never_reinstalls_plugins(phone, backups, monkeypatch):
    seen = []
    monkeypatch.setattr(backups, "import_from_dict", lambda doc, reinstall_plugins: seen.append(reinstall_plugins))
    step_up(phone)
    refused = phone.post("/backup/import", json=minimal_backup())  # reinstall_plugins defaults to true
    assert refused.status_code == 400 and "web app" in refused.json()["detail"]
    refused = phone.post("/backup/import?reinstall_plugins=true", json=minimal_backup())
    assert refused.status_code == 400
    assert seen == []


def test_redaction_masks_nested_secrets():
    redacted = phone_policy.redact(
        {
            "a": {"refresh_token": "x", "nested": {"client_secret": "y", "Authorization": "z"}},
            "headers": {"X-Anything": "w"},
            "list": [{"password": "v"}],
            "count": 3,
            "api_key_set": True,
        }
    )
    assert redacted == {
        "a": {"refresh_token": "***", "nested": {"client_secret": "***", "Authorization": "***"}},
        "headers": {"X-Anything": "***"},
        "list": [{"password": "***"}],
        "count": 3,
        "api_key_set": True,
    }


def test_table_rows():
    for method, path, _ in TIER2:
        assert scopes.requires_step_up(scopes.CONTROL, method, path.split("?")[0]), path
    for method, path, _ in TIER1:
        assert scopes.permits(scopes.CONTROL, method, path)
        assert not scopes.requires_step_up(scopes.CONTROL, method, path), path
