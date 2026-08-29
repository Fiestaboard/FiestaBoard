"""Tests for the in-app HDMI kiosk controls (FiestaPi only).

The app proxies to the fiestaupdater sidecar's fixed /hdmi verbs; these
endpoints are what the FiestaPanel settings UI drives so nobody has to SSH.
"""

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from src.api_server import app

    return TestClient(app)


class TestHdmiKioskStatus:
    def test_unsupported_off_pi(self, client):
        with (
            patch("src.api_server._fiestaboard_profile", return_value="docker"),
            patch("src.api_server._updater_probe", return_value=True),
        ):
            response = client.get("/settings/hdmi-kiosk")
        assert response.status_code == 200
        assert response.json() == {"supported": False, "status": "unsupported"}

    def test_unsupported_without_sidecar(self, client):
        with (
            patch("src.api_server._fiestaboard_profile", return_value="pi"),
            patch("src.api_server._updater_probe", return_value=False),
        ):
            response = client.get("/settings/hdmi-kiosk")
        assert response.status_code == 200
        assert response.json() == {"supported": False, "status": "unsupported"}

    def test_supported_merges_sidecar_status(self, client):
        sidecar = Mock(status_code=200)
        sidecar.json.return_value = {"status": "enabled", "action": "enable"}
        with (
            patch("src.api_server._fiestaboard_profile", return_value="pi"),
            patch("src.api_server._updater_probe", return_value=True),
            patch("src.api_server.requests.get", return_value=sidecar) as get,
        ):
            response = client.get("/settings/hdmi-kiosk")
        assert response.status_code == 200
        data = response.json()
        assert data["supported"] is True
        assert data["status"] == "enabled"
        assert get.call_args[0][0].endswith("/hdmi/status")

    def test_sidecar_without_hdmi_verbs_reports_unknown(self, client):
        """Fleet sidecars older than the hdmi verbs 404 the status route."""
        sidecar = Mock(status_code=404)
        with (
            patch("src.api_server._fiestaboard_profile", return_value="pi"),
            patch("src.api_server._updater_probe", return_value=True),
            patch("src.api_server.requests.get", return_value=sidecar),
        ):
            response = client.get("/settings/hdmi-kiosk")
        assert response.status_code == 200
        data = response.json()
        assert data["supported"] is True
        assert data["status"] == "unknown"


class TestHdmiKioskToggle:
    def test_enable_proxies_to_sidecar_with_token(self, client):
        sidecar = Mock(status_code=202)
        sidecar.json.return_value = {"status": "queued", "action": "hdmi_enable"}
        with (
            patch("src.api_server._fiestaboard_profile", return_value="pi"),
            patch("src.api_server._updater_probe", return_value=True),
            patch("src.api_server._updater_token", return_value="tok-123"),
            patch("src.api_server.requests.post", return_value=sidecar) as post,
        ):
            response = client.post("/settings/hdmi-kiosk", json={"enabled": True})
        assert response.status_code == 200
        assert response.json()["status"] == "queued"
        assert post.call_args[0][0].endswith("/hdmi/enable")
        assert post.call_args[1]["headers"]["Authorization"] == "Bearer tok-123"

    def test_disable_hits_disable_verb(self, client):
        sidecar = Mock(status_code=202)
        sidecar.json.return_value = {"status": "queued", "action": "hdmi_disable"}
        with (
            patch("src.api_server._fiestaboard_profile", return_value="pi"),
            patch("src.api_server._updater_probe", return_value=True),
            patch("src.api_server._updater_token", return_value="tok-123"),
            patch("src.api_server.requests.post", return_value=sidecar) as post,
        ):
            response = client.post("/settings/hdmi-kiosk", json={"enabled": False})
        assert response.status_code == 200
        assert post.call_args[0][0].endswith("/hdmi/disable")

    def test_toggle_rejected_off_pi(self, client):
        with patch("src.api_server._fiestaboard_profile", return_value="docker"):
            response = client.post("/settings/hdmi-kiosk", json={"enabled": True})
        assert response.status_code == 400

    def test_stale_sidecar_maps_404_to_actionable_error(self, client):
        """An old sidecar without the hdmi verbs → tell the user to reboot
        (the boot service pulls the newest sidecar image on every boot)."""
        sidecar = Mock(status_code=404)
        with (
            patch("src.api_server._fiestaboard_profile", return_value="pi"),
            patch("src.api_server._updater_probe", return_value=True),
            patch("src.api_server._updater_token", return_value="tok-123"),
            patch("src.api_server.requests.post", return_value=sidecar),
        ):
            response = client.post("/settings/hdmi-kiosk", json={"enabled": True})
        assert response.status_code == 409
        assert "reboot" in response.json()["detail"].lower()

    def test_missing_enabled_field_is_rejected(self, client):
        with patch("src.api_server._fiestaboard_profile", return_value="pi"):
            response = client.post("/settings/hdmi-kiosk", json={})
        assert response.status_code == 400
