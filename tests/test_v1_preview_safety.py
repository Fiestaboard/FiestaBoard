"""A rejected update or paused preview must leave stored state unchanged."""

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def install():
    from src.api_server import app
    from src.settings.service import get_settings_service

    settings = get_settings_service()
    settings.set_boards([{"device_type": "flagship", "name": "Kitchen"}])
    return TestClient(app), settings


def test_invalid_install_patch_preserves_schedule_enabled(install):
    client, settings = install
    settings.set_schedule_enabled(True)

    response = client.patch("/v1/install", json={"schedule_enabled": False, "default_page_id": "missing"})

    assert response.status_code == 404
    assert settings.is_schedule_enabled() is True
    assert client.get("/v1/install").json()["schedule_enabled"] is True


def test_paused_ui_preview_does_not_arm_a_temporary_override(install):
    client, settings = install
    settings.set_output_target("ui")
    settings.set_paused(True)
    assert settings.get_temporary_override() is None
    service = Mock()

    with (
        patch("src.display_runtime.get_service", return_value=service),
        patch("src.api_server.get_service", return_value=service),
    ):
        response = client.post(
            "/v1/boards/primary/message",
            json={"text": "Preview only", "if_paused": "preview", "duration_minutes": 5},
        )

    assert response.status_code == 200, response.text
    assert settings.get_temporary_override() is None
    assert response.json()["sent"] is False
    assert response.json()["expires_at"] is None
    assert "paused" in response.json()["reason"]
