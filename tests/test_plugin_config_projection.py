"""Plugin configuration response and access regression tests; fake credentials only."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.auth import routes as auth_routes
from src.auth import service as auth_module
from src.config_manager import ConfigManager
from src.plugins import routes as pr

FIELDS = ["purpleair_read_key", "statestream_broker_password", "api_access_code", "secret", "token", "refresh_token"]
FAKE = {k: "cx-FAKE-" + k for k in FIELDS}
PASSWORD = "cx-fake-admin-password"


@pytest.fixture
def env(tmp_path, monkeypatch):
    svc = auth_module.AuthService(tmp_path / "auth.json")
    svc.create_initial_user("admin", PASSWORD)
    svc.sessions.set_enrollment(True)
    monkeypatch.setattr(auth_module, "_service", svc)
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "true")
    monkeypatch.delenv("FIESTABOARD_MCP_TOKEN", raising=False)
    auth_routes._FAILED_ATTEMPTS.clear()
    cm = ConfigManager(config_path=str(tmp_path / "config.json"))
    cm.set_plugin_config("cx_probe", {**FAKE, "api_key": "cx-FAKE-control-key", "enabled": False})
    cm.set_plugin_config("cx_probe:office", {**FAKE, "enabled": False})
    manifest = SimpleNamespace(
        name="CX Probe",
        version="1.0",
        description="fake only",
        author="CX",
        icon="puzzle",
        category="utility",
        plugin_type="data",
        settings_schema={
            "type": "object",
            "properties": {k: {"type": "string", "ui:widget": "password"} for k in FIELDS},
        },
        raw={"variables": {}},
        max_lengths={},
        env_vars=[],
        documentation="",
        demo=None,
    )
    reg = Mock()
    reg.get_manifest.return_value = manifest
    reg.get_plugin.return_value = Mock()
    reg.is_enabled.return_value = False
    reg.parse_instance_key.side_effect = lambda k: (k.split(":")[0], k.split(":")[1] if ":" in k else None)
    reg.list_instances.return_value = []
    reg.list_plugins.side_effect = lambda: [{"id": "cx_probe", "name": "CX Probe"}]
    reg.set_plugin_config.return_value = []
    # Alpha separates preflight validation from live application.
    reg.validate_plugin_config.return_value = []
    reg.apply_stored_config.return_value = []
    monkeypatch.setattr(pr, "get_plugin_registry", lambda: reg)
    monkeypatch.setattr(pr, "PLUGIN_SYSTEM_AVAILABLE", True)
    monkeypatch.setattr(pr, "reset_display_service", lambda: None)
    monkeypatch.setattr(pr, "reset_template_engine", lambda: None)
    import src.plugins

    monkeypatch.setattr(src.plugins, "get_plugin_registry", lambda: reg)
    import src.plugins.registry

    monkeypatch.setattr(src.plugins.registry, "_registry", reg)
    return cm


def client_for(role, monkeypatch):
    c = TestClient(app, raise_server_exceptions=False)
    if role == "off":
        monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "false")
    elif role == "admin":
        r = c.post("/auth/login", json={"username": "admin", "password": PASSWORD})
        assert r.status_code == 200, r.text
        context = c.get("/auth/sessions/context").json()
        c.headers.update({"Origin": "http://testserver", "X-CSRF-Token": context["csrf_token"]})
    elif role in ("phone", "tv"):
        r = c.post(
            "/auth/device/login",
            json={
                "username": "admin",
                "password": PASSWORD,
                "client_id": "fiestaboard-ios" if role == "phone" else "fiestaboard-tvos",
                "device_name": "CX Fake",
                "app_version": "1",
            },
        )
        if role == "phone" and r.status_code == 422:
            pytest.skip("10.x has no phone control enrollment")
        assert r.status_code == 200, r.text
        c.headers["Authorization"] = "Bearer " + r.json()["access_token"]
    elif role == "api":
        monkeypatch.setenv("FIESTABOARD_MCP_TOKEN", "cx-fake-mcp-token")
        c.headers["Authorization"] = "Bearer cx-fake-mcp-token"
    return c


PATHS = ["/plugins", "/plugins/cx_probe", "/plugins/cx_probe:office", "/v1/plugins/cx_probe", "/config/full"]


@pytest.mark.parametrize("role", ["admin", "phone", "tv", "off", "guest", "api"])
@pytest.mark.parametrize("path", PATHS)
def test_read_matrix(env, monkeypatch, role, path):
    c = client_for(role, monkeypatch)
    r = c.get(path)
    allowed = (
        role in ("admin", "off")
        or (role == "phone" and path != "/config/full")
        or (role == "api" and path.startswith("/v1/"))
    )
    expected = 200 if allowed else 403 if role in ("tv", "phone") else 401
    assert r.status_code == expected, (role, path, r.status_code, r.text)
    if allowed:
        for value in FAKE.values():
            assert value not in r.text, (path, value, r.text)
        assert "cx-FAKE-control-key" not in r.text


@pytest.mark.parametrize("role", ["admin", "phone", "off"])
@pytest.mark.parametrize(
    "method,path,body",
    [("put", "/plugins/cx_probe/config", {"config": FAKE}), ("patch", "/v1/plugins/cx_probe", {"enabled": False})],
)
def test_write_response(env, monkeypatch, role, method, path, body):
    r = getattr(client_for(role, monkeypatch), method)(path, json=body)
    assert r.status_code == 200, r.text
    for value in FAKE.values():
        assert value not in r.text, r.text


def test_v1_catalog_omits_config(env, monkeypatch):
    r = client_for("admin", monkeypatch).get("/v1/plugins")
    assert r.status_code == 200
    assert not any(v in r.text for v in FAKE.values())


def test_mcp_list(env):
    from src.mcp_server import _build_mcp_server
    from tests.test_mcp_server import _call_tool

    result = _call_tool(_build_mcp_server(), "list_installed_plugins")
    for v in FAKE.values():
        assert v not in json.dumps(result), result


def test_output_schema_masking(env):
    from src.outputs.output_config import mask_output_config

    schema = {"properties": {k: {"secret": True} for k in FIELDS}}
    assert mask_output_config(FAKE, schema) == dict.fromkeys(FIELDS, "***")
    assert mask_output_config(FAKE, None) == "***"


@pytest.mark.parametrize("plugin_id", ["cx_probe", "cx_probe:office"])
def test_all_declared_passwords_roundtrip_through_rest(env, monkeypatch, plugin_id):
    client = client_for("admin", monkeypatch)
    config = client.get("/plugins/" + plugin_id).json()["config"]
    assert all(config[key] == "***" for key in FIELDS)
    response = client.put("/plugins/" + plugin_id + "/config", json={"config": config})
    assert response.status_code == 200, response.text
    assert all(value not in response.text for value in FAKE.values())
    assert all(
        env.get_plugin_config(plugin_id, include_env_overrides=False)[key] == value for key, value in FAKE.items()
    )


def test_mcp_configure_roundtrip(env):
    from src.mcp_server import _build_mcp_server
    from tests.test_mcp_server import _call_tool

    server = _build_mcp_server()
    result = _call_tool(server, "configure_plugin", plugin_id="cx_probe", config=dict.fromkeys(FIELDS, "***"))
    assert "error" not in result, result
    assert all(value not in json.dumps(result) for value in FAKE.values())
    assert all(
        env.get_plugin_config("cx_probe", include_env_overrides=False)[key] == value for key, value in FAKE.items()
    )
