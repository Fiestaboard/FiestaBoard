"""Tests for /settings/beta API endpoints (HTTPS Beta toggle)."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from src.api_server import app
from src.settings.service import get_settings_service

client = TestClient(app)


def _reset_beta_state():
    """Force the beta setting back to disabled between tests."""
    svc = get_settings_service()
    svc.update_beta_settings({"https_enabled": False})


def test_get_beta_settings_returns_defaults():
    _reset_beta_state()
    with (
        patch("src.api_server._updater_token", return_value=""),
        patch("src.api_server._updater_probe", return_value=False),
    ):
        response = client.get("/settings/beta")
    assert response.status_code == 200
    body = response.json()
    assert body["settings"]["https_enabled"] is False
    assert "https" in body
    assert "cert_present" in body["https"]
    assert "updater_available" in body["https"]
    assert body["https"]["updater_available"] is False


def test_put_beta_enable_https_generates_cert_and_requests_restart(tmp_path, monkeypatch):
    _reset_beta_state()
    monkeypatch.setenv("FIESTABOARD_CERT_DIR", str(tmp_path))

    fake_cert = tmp_path / "fiestaboard.crt"
    fake_key = tmp_path / "fiestaboard.key"

    def fake_generate(*args, **kwargs):
        fake_cert.write_text("CERT")
        fake_key.write_text("KEY")
        return fake_cert, fake_key

    with (
        patch("src.system.https_certs.generate_cert", side_effect=fake_generate) as gen,
        patch("src.api_server._updater_token", return_value=""),
        patch("src.api_server._updater_probe", return_value=False),
    ):
        response = client.put("/settings/beta", json={"https_enabled": True})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["settings"]["https_enabled"] is True
    assert body["restart_required"] is True
    gen.assert_called_once()


def test_put_beta_disable_https_removes_cert(tmp_path, monkeypatch):
    """Toggling off after on should call remove_cert and request restart."""
    _reset_beta_state()
    monkeypatch.setenv("FIESTABOARD_CERT_DIR", str(tmp_path))

    # Pre-enable without invoking openssl.
    with (
        patch("src.system.https_certs.generate_cert", return_value=(tmp_path / "c", tmp_path / "k")),
        patch("src.api_server._updater_token", return_value=""),
        patch("src.api_server._updater_probe", return_value=False),
    ):
        client.put("/settings/beta", json={"https_enabled": True})

    with (
        patch("src.system.https_certs.remove_cert", return_value=True) as rm,
        patch("src.api_server._updater_token", return_value=""),
        patch("src.api_server._updater_probe", return_value=False),
    ):
        response = client.put("/settings/beta", json={"https_enabled": False})

    assert response.status_code == 200
    body = response.json()
    assert body["settings"]["https_enabled"] is False
    assert body["restart_required"] is True
    rm.assert_called_once()


def test_put_beta_no_change_does_not_request_restart(tmp_path, monkeypatch):
    _reset_beta_state()
    monkeypatch.setenv("FIESTABOARD_CERT_DIR", str(tmp_path))

    with (
        patch("src.api_server._updater_token", return_value=""),
        patch("src.api_server._updater_probe", return_value=False),
    ):
        # Setting to current value should not request a restart and
        # should not invoke cert generation.
        with patch("src.system.https_certs.generate_cert") as gen, patch("src.system.https_certs.remove_cert") as rm:
            response = client.put("/settings/beta", json={"https_enabled": False})

    assert response.status_code == 200
    body = response.json()
    assert body["restart_required"] is False
    gen.assert_not_called()
    rm.assert_not_called()


def test_put_beta_cert_generation_failure_returns_warning(tmp_path, monkeypatch):
    _reset_beta_state()
    monkeypatch.setenv("FIESTABOARD_CERT_DIR", str(tmp_path))

    with (
        patch(
            "src.system.https_certs.generate_cert",
            side_effect=RuntimeError("openssl exploded"),
        ),
        patch("src.api_server._updater_token", return_value=""),
        patch("src.api_server._updater_probe", return_value=False),
    ):
        response = client.put("/settings/beta", json={"https_enabled": True})

    assert response.status_code == 200
    body = response.json()
    # The setting still toggles (we don't hide the user's intent), but
    # we surface the cert error so the UI can show it.
    assert body["status"] == "warning"
    assert body["settings"]["https_enabled"] is True
    assert "openssl exploded" in body["cert_error"]
    _reset_beta_state()


def test_put_beta_reports_updater_availability():
    _reset_beta_state()
    with (
        patch("src.api_server._updater_token", return_value="tok"),
        patch("src.api_server._updater_probe", return_value=True),
    ):
        response = client.put("/settings/beta", json={})
    body = response.json()
    assert body["https"]["updater_available"] is True


def test_settings_all_includes_beta_section():
    """beta should appear in the consolidated /settings/all payload."""
    response = client.get("/settings/all")
    assert response.status_code == 200
    data = response.json()
    assert "beta" in data
    assert "https_enabled" in data["beta"]
