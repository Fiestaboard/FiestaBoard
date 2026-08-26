"""Auth-boundary tests for panel endpoints.

The /panel/ prefix (viewer reads) must work with no session cookie —
FiestaPanel TVs never log in. The /panels CRUD surface stays protected.

The suite-wide autouse fixture disables auth for this file (its name does
not contain "test_auth_"), so each test explicitly re-enables it.
"""

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from src.api_server import app

    return TestClient(app)


@pytest.fixture
def auth_enabled(monkeypatch):
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "true")


class TestPanelAuthBoundary:
    def test_public_panel_read_reaches_route_without_cookie(self, client, auth_enabled):
        """Unknown panel gives 404 (the route ran) — not 401/409 from auth."""
        with patch("src.api_server.get_panel_service") as mock:
            mock.return_value = Mock(get_panel=Mock(return_value=None))
            response = client.get("/panel/doesnotexist")
        assert response.status_code == 404

    def test_public_frame_read_reaches_route_without_cookie(self, client, auth_enabled):
        with patch("src.api_server.get_panel_service") as mock:
            mock.return_value = Mock(get_panel=Mock(return_value=None))
            response = client.get("/panel/doesnotexist/frame")
        assert response.status_code == 404

    def test_panels_list_requires_auth(self, client, auth_enabled):
        response = client.get("/panels")
        assert response.status_code in (401, 409)

    def test_panels_create_requires_auth(self, client, auth_enabled):
        response = client.post("/panels", json={"name": "TV", "device_type": "note"})
        assert response.status_code in (401, 409)
