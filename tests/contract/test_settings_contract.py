"""Contract tests for the /settings API endpoints.

Validates that the Python backend returns responses that conform to the
schema the Next.js frontend expects.

Issue: #502
"""

import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.api_server import app
from tests.contract.schemas import (
    HealthResponse,
    VersionResponse,
    TransitionSettingsResponse,
    OutputSettingsResponse,
    BoardSettingsResponse,
)


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


class TestHealthContract:
    def test_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_response_has_status_field(self, client):
        resp = client.get("/health")
        data = resp.json()
        assert "status" in data

    def test_status_is_ok(self, client):
        resp = client.get("/health")
        assert resp.json()["status"] == "ok"

    def test_validates_against_schema(self, client):
        resp = client.get("/health")
        parsed = HealthResponse(**resp.json())
        assert parsed.status == "ok"


# ---------------------------------------------------------------------------
# GET /version
# ---------------------------------------------------------------------------


class TestVersionContract:
    def test_returns_200(self, client):
        resp = client.get("/version")
        assert resp.status_code == 200

    def test_response_has_package_version_field(self, client):
        resp = client.get("/version")
        assert "package_version" in resp.json()

    def test_package_version_is_string(self, client):
        resp = client.get("/version")
        assert isinstance(resp.json()["package_version"], str)

    def test_package_version_is_semver_like(self, client):
        """Version should look like X.Y.Z."""
        resp = client.get("/version")
        version = resp.json()["package_version"]
        parts = version.split(".")
        assert len(parts) >= 2, f"Version '{version}' doesn't look like semver"

    def test_response_has_build_version_field(self, client):
        resp = client.get("/version")
        assert "build_version" in resp.json()

    def test_response_has_is_dev_field(self, client):
        resp = client.get("/version")
        assert "is_dev" in resp.json()
        assert isinstance(resp.json()["is_dev"], bool)

    def test_validates_against_schema(self, client):
        resp = client.get("/version")
        parsed = VersionResponse(**resp.json())
        assert len(parsed.package_version) > 0


# ---------------------------------------------------------------------------
# GET /settings/transitions
# ---------------------------------------------------------------------------


class TestTransitionSettingsContract:
    def _make_transition_mock(self, strategy="column", step_interval_ms=50, step_size=1):
        """Create a transition settings mock with concrete attribute values."""
        from types import SimpleNamespace
        return SimpleNamespace(
            strategy=strategy,
            step_interval_ms=step_interval_ms,
            step_size=step_size,
        )

    def test_returns_200(self, client):
        with patch("src.api_server.get_settings_service") as mock_svc:
            ss = Mock()
            ss.get_transition_settings.return_value = self._make_transition_mock()
            mock_svc.return_value = ss

            resp = client.get("/settings/transitions")

        assert resp.status_code == 200

    def test_response_has_strategy(self, client):
        with patch("src.api_server.get_settings_service") as mock_svc:
            ss = Mock()
            ss.get_transition_settings.return_value = self._make_transition_mock()
            mock_svc.return_value = ss

            resp = client.get("/settings/transitions")

        assert "strategy" in resp.json()

    def test_validates_against_schema(self, client):
        with patch("src.api_server.get_settings_service") as mock_svc:
            ss = Mock()
            ss.get_transition_settings.return_value = self._make_transition_mock(
                strategy="column", step_interval_ms=100
            )
            mock_svc.return_value = ss

            resp = client.get("/settings/transitions")

        parsed = TransitionSettingsResponse(**resp.json())
        assert parsed.strategy == "column"

    def test_strategy_is_string(self, client):
        with patch("src.api_server.get_settings_service") as mock_svc:
            ss = Mock()
            ss.get_transition_settings.return_value = self._make_transition_mock(strategy="instant")
            mock_svc.return_value = ss

            resp = client.get("/settings/transitions")

        assert isinstance(resp.json()["strategy"], str)


# ---------------------------------------------------------------------------
# GET /settings/output
# ---------------------------------------------------------------------------


class TestOutputSettingsContract:
    def _make_output_mock(self, target="ui"):
        from types import SimpleNamespace
        return SimpleNamespace(target=target)

    def test_returns_200(self, client):
        with patch("src.api_server.get_settings_service") as mock_svc:
            ss = Mock()
            ss.get_output_settings.return_value = self._make_output_mock("ui")
            mock_svc.return_value = ss

            resp = client.get("/settings/output")

        assert resp.status_code == 200

    def test_response_has_target_field(self, client):
        with patch("src.api_server.get_settings_service") as mock_svc:
            ss = Mock()
            ss.get_output_settings.return_value = self._make_output_mock("ui")
            mock_svc.return_value = ss

            resp = client.get("/settings/output")

        assert "target" in resp.json()

    def test_validates_against_schema(self, client):
        with patch("src.api_server.get_settings_service") as mock_svc:
            ss = Mock()
            ss.get_output_settings.return_value = self._make_output_mock("board")
            mock_svc.return_value = ss

            resp = client.get("/settings/output")

        parsed = OutputSettingsResponse(**resp.json())
        assert parsed.target == "board"

    def test_target_is_string(self, client):
        with patch("src.api_server.get_settings_service") as mock_svc:
            ss = Mock()
            ss.get_output_settings.return_value = self._make_output_mock("ui")
            mock_svc.return_value = ss

            resp = client.get("/settings/output")

        assert isinstance(resp.json()["target"], str)


# ---------------------------------------------------------------------------
# GET /settings/board
# ---------------------------------------------------------------------------


class TestBoardSettingsContract:
    def _make_board_settings_mock(self, boards=None):
        """Create a board settings mock with a concrete to_dict()."""
        if boards is None:
            boards = []
        board_dict = {
            "board_type": "black",
            "boards": boards,
            "devices": ["flagship"],
        }
        m = Mock()
        m.to_dict.return_value = board_dict
        return m

    def test_returns_200(self, client):
        with patch("src.api_server.get_settings_service") as mock_svc:
            ss = Mock()
            ss.get_board_settings.return_value = self._make_board_settings_mock()
            mock_svc.return_value = ss

            resp = client.get("/settings/board")

        assert resp.status_code == 200

    def test_response_has_boards_field(self, client):
        with patch("src.api_server.get_settings_service") as mock_svc:
            ss = Mock()
            ss.get_board_settings.return_value = self._make_board_settings_mock()
            mock_svc.return_value = ss

            resp = client.get("/settings/board")

        assert "boards" in resp.json()

    def test_boards_is_list(self, client):
        with patch("src.api_server.get_settings_service") as mock_svc:
            ss = Mock()
            ss.get_board_settings.return_value = self._make_board_settings_mock()
            mock_svc.return_value = ss

            resp = client.get("/settings/board")

        assert isinstance(resp.json()["boards"], list)

    def test_validates_against_schema(self, client):
        with patch("src.api_server.get_settings_service") as mock_svc:
            ss = Mock()
            ss.get_board_settings.return_value = self._make_board_settings_mock()
            mock_svc.return_value = ss

            resp = client.get("/settings/board")

        parsed = BoardSettingsResponse(**resp.json())
        assert isinstance(parsed.boards, list)

    def test_response_has_board_type_field(self, client):
        with patch("src.api_server.get_settings_service") as mock_svc:
            ss = Mock()
            ss.get_board_settings.return_value = self._make_board_settings_mock()
            mock_svc.return_value = ss

            resp = client.get("/settings/board")

        assert "board_type" in resp.json()


# ---------------------------------------------------------------------------
# GET /settings/active-page
# ---------------------------------------------------------------------------


class TestActivePageSettingsContract:
    def test_returns_200(self, client):
        with patch("src.api_server.get_settings_service") as mock_svc:
            ss = Mock()
            ss.get_active_page_id.return_value = None
            mock_svc.return_value = ss

            resp = client.get("/settings/active-page")

        assert resp.status_code == 200

    def test_response_has_page_id_field(self, client):
        with patch("src.api_server.get_settings_service") as mock_svc:
            ss = Mock()
            ss.get_active_page_id.return_value = None
            mock_svc.return_value = ss

            resp = client.get("/settings/active-page")

        data = resp.json()
        assert "page_id" in data

    def test_page_id_can_be_null(self, client):
        with patch("src.api_server.get_settings_service") as mock_svc:
            ss = Mock()
            ss.get_active_page_id.return_value = None
            mock_svc.return_value = ss

            resp = client.get("/settings/active-page")

        assert resp.json()["page_id"] is None

    def test_page_id_can_be_string(self, client):
        with patch("src.api_server.get_settings_service") as mock_svc:
            ss = Mock()
            ss.get_active_page_id.return_value = "some-page-id"
            mock_svc.return_value = ss

            resp = client.get("/settings/active-page")

        assert resp.json()["page_id"] == "some-page-id"
