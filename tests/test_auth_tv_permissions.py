"""A TV credential cannot become an administrator through any public bypass."""

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.auth import service as auth_module
from src.auth.device_models import DeviceMetadata
from src.auth.device_service import DeviceService


@pytest.fixture
def tv(tmp_path, monkeypatch):
    auth = auth_module.AuthService(tmp_path / "auth.json")
    auth.create_initial_user("admin", "correct-password")
    auth.sessions.set_enrollment(True)
    monkeypatch.setattr(auth_module, "_service", auth)
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "true")
    token = DeviceService(auth).login(
        "admin", "correct-password", DeviceMetadata(client_id="fiestaboard-tvos", device_name="TV", app_version="1")
    )
    client = TestClient(app, headers={"Authorization": "Bearer " + token.access_token})
    return client, auth, token


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/auth/sessions", None),
        ("GET", "/auth/sessions/context", None),
        ("PUT", "/auth/device/settings", {"enabled": False}),
        ("POST", "/auth/change-password", {}),
        ("POST", "/auth/login", {"username": "admin", "password": "correct-password"}),
        ("GET", "/v1/health", None),
        ("POST", "/mcp", {}),
        ("POST", "/panels", {}),
        ("DELETE", "/panels/example", None),
        ("GET", "/settings", None),
        ("GET", "/plugins", None),
        ("PATCH", "/panels/example", {"name": "Renamed"}),
        ("PATCH", "/panels/example", {"calibration_scale": 1.0, "unknown_field": True}),
        ("PATCH", "/panels/example", {"calibration_scale": 1.0, "backdrop": "dark"}),
    ],
)
def test_scope_denies_unrelated_operations(tv, method, path, body):
    client, _, _ = tv
    assert client.request(method, path, json=body).status_code == 403


def test_cookie_cannot_rescue_revoked_tv_and_anonymous_frames_stay_public(tv):
    client, auth, token = tv
    client.cookies.set("fiestaboard_session", auth.authenticate("admin", "correct-password"))
    auth.sessions.revoke_session("admin", token.session_id)
    assert client.get("/panels").status_code == 401
    assert client.get("/panel/missing/frame").status_code == 401
    anonymous = TestClient(app)
    assert anonymous.get("/panel/missing/frame").status_code == 404


def test_scoped_patch_reaches_existing_validation(tv):
    client, _, _ = tv
    assert client.patch("/panels/missing", json={"calibration_scale": 1.0}).status_code == 404
    assert client.patch("/panels/missing", json={"calibration_scale": 99}).status_code == 422


def test_self_revoke_cannot_revoke_other_device(tv):
    client, auth, _token = tv
    browser = auth.authenticate("admin", "correct-password")
    assert client.delete("/auth/device/session").status_code == 200
    assert client.get("/panels").status_code == 401
    assert auth.verify_session(browser) == "admin"
