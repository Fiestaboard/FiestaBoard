"""Tests for output target routing and settings service."""

import os
import tempfile
from unittest.mock import Mock, patch

import pytest

from src.settings.service import (
    VALID_OUTPUT_TARGETS,
    VALID_STRATEGIES,
    OutputSettings,
    SettingsService,
    TransitionSettings,
)


class TestTransitionSettings:
    """Tests for TransitionSettings dataclass."""

    def test_default_values(self):
        """Test default values are None."""
        settings = TransitionSettings()
        assert settings.strategy is None
        assert settings.step_interval_ms is None
        assert settings.step_size is None

    def test_to_dict(self):
        """Test conversion to dictionary."""
        settings = TransitionSettings(strategy="column", step_interval_ms=500, step_size=2)
        d = settings.to_dict()
        assert d["strategy"] == "column"
        assert d["step_interval_ms"] == 500
        assert d["step_size"] == 2

    def test_from_dict(self):
        """Test creation from dictionary."""
        d = {"strategy": "row", "step_interval_ms": 1000, "step_size": 3}
        settings = TransitionSettings.from_dict(d)
        assert settings.strategy == "row"
        assert settings.step_interval_ms == 1000
        assert settings.step_size == 3


class TestOutputSettings:
    """Tests for OutputSettings dataclass."""

    def test_default_target(self):
        """Test default target is 'board'."""
        settings = OutputSettings()
        assert settings.target == "board"

    def test_from_dict_valid_target(self):
        """Test creation from dict with valid target."""
        settings = OutputSettings.from_dict({"target": "both"})
        assert settings.target == "both"

    def test_from_dict_invalid_target_falls_back(self):
        """Test invalid target falls back to 'board'."""
        settings = OutputSettings.from_dict({"target": "invalid"})
        assert settings.target == "board"


class TestSettingsService:
    """Tests for SettingsService."""

    @pytest.fixture
    def temp_settings_file(self):
        """Create a temporary settings file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{}")
            yield f.name
        os.unlink(f.name)

    @pytest.fixture
    def service(self, temp_settings_file):
        """Create a settings service with temp file."""
        with patch.object(SettingsService, "_load_transition_settings", return_value=TransitionSettings()):
            with patch.object(SettingsService, "_load_output_settings", return_value=OutputSettings()):
                return SettingsService(settings_file=temp_settings_file)

    def test_get_transition_settings(self, service):
        """Test getting transition settings."""
        settings = service.get_transition_settings()
        assert isinstance(settings, TransitionSettings)

    def test_update_transition_strategy(self, service):
        """Test updating transition strategy."""
        result = service.update_transition_settings(strategy="column")
        assert result.strategy == "column"

    def test_update_transition_invalid_strategy_raises(self, service):
        """Test invalid strategy raises ValueError."""
        with pytest.raises(ValueError, match="Invalid strategy"):
            service.update_transition_settings(strategy="invalid")

    def test_update_transition_all_strategies(self, service):
        """Test all valid strategies can be set."""
        for strategy in VALID_STRATEGIES:
            result = service.update_transition_settings(strategy=strategy)
            assert result.strategy == strategy

    def test_update_transition_clear_with_none(self, service):
        """Test clearing strategy with None."""
        service.update_transition_settings(strategy="column")
        result = service.update_transition_settings(strategy=None)
        assert result.strategy is None

    def test_update_transition_interval_and_step(self, service):
        """Test updating interval and step size."""
        result = service.update_transition_settings(step_interval_ms=500, step_size=2)
        assert result.step_interval_ms == 500
        assert result.step_size == 2

    def test_get_output_settings(self, service):
        """Test getting output settings."""
        settings = service.get_output_settings()
        assert isinstance(settings, OutputSettings)

    def test_set_output_target(self, service):
        """Test setting output target."""
        result = service.set_output_target("both")
        assert result.target == "both"

    def test_set_output_invalid_target_raises(self, service):
        """Test invalid target raises ValueError."""
        with pytest.raises(ValueError, match="Invalid target"):
            service.set_output_target("invalid")

    def test_all_output_targets(self, service):
        """Test all valid output targets can be set."""
        for target in VALID_OUTPUT_TARGETS:
            result = service.set_output_target(target)
            assert result.target == target

    def test_should_send_to_board(self, service):
        """Test should_send_to_board based on output target."""
        service.set_output_target("board")
        assert service.should_send_to_board() is True

        service.set_output_target("both")
        assert service.should_send_to_board() is True

        service.set_output_target("ui")
        assert service.should_send_to_board() is False

    def test_settings_persistence(self, temp_settings_file):
        """Test that settings persist across service restarts."""
        # First service instance - use real loading which will use defaults
        with patch.object(SettingsService, "_load_transition_settings", return_value=TransitionSettings()):
            with patch.object(SettingsService, "_load_output_settings", return_value=OutputSettings()):
                service1 = SettingsService(settings_file=temp_settings_file)
                service1.update_transition_settings(strategy="diagonal", step_interval_ms=1000)
                service1.set_output_target("both")

        # Second service instance - load from file
        service2 = SettingsService(settings_file=temp_settings_file)

        # Should load persisted settings
        transition = service2.get_transition_settings()
        output = service2.get_output_settings()

        assert transition.strategy == "diagonal"
        assert transition.step_interval_ms == 1000
        assert output.target == "both"


class TestOutputAPIEndpoints:
    """Tests for output-related API endpoints."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        from fastapi.testclient import TestClient

        from src.api_server import app

        return TestClient(app)

    @pytest.fixture
    def mock_services(self):
        """Mock the services."""
        with (
            patch("src.api_server.get_display_service") as mock_display,
            patch("src.api_server.get_settings_service") as mock_settings,
            patch("src.api_server.get_service") as mock_main,
        ):
            # Setup display service mock
            mock_display_svc = Mock()
            mock_display.return_value = mock_display_svc

            # Setup settings service mock
            mock_settings_svc = Mock()
            mock_settings_svc.get_transition_settings.return_value = TransitionSettings(
                strategy="column", step_interval_ms=500, step_size=2
            )
            mock_settings_svc.get_output_settings.return_value = OutputSettings(target="board")
            mock_settings_svc.should_send_to_board.return_value = True
            mock_settings.return_value = mock_settings_svc

            # Setup main service mock
            mock_main_svc = Mock()
            mock_main_svc.vb_client = Mock()
            mock_main_svc.vb_client.send_text.return_value = (True, True)
            mock_main.return_value = mock_main_svc

            yield {"display": mock_display_svc, "settings": mock_settings_svc, "main": mock_main_svc}

    def test_get_transition_settings(self, client, mock_services):
        """Test GET /settings/transitions."""
        response = client.get("/settings/transitions")

        assert response.status_code == 200
        data = response.json()
        assert data["strategy"] == "column"
        assert data["step_interval_ms"] == 500
        assert data["step_size"] == 2

    def test_update_transition_settings(self, client, mock_services):
        """Test PUT /settings/transitions."""
        mock_services["settings"].update_transition_settings.return_value = TransitionSettings(
            strategy="row", step_interval_ms=1000, step_size=3
        )

        response = client.put("/settings/transitions", json={"strategy": "row", "step_interval_ms": 1000})

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_get_output_settings(self, client, mock_services):
        """Test GET /settings/output."""
        response = client.get("/settings/output")

        assert response.status_code == 200
        data = response.json()
        assert data["target"] == "board"
        assert "available_targets" in data

    def test_update_output_settings(self, client, mock_services):
        """Test PUT /settings/output."""
        mock_services["settings"].set_output_target.return_value = OutputSettings(target="both")

        response = client.put("/settings/output", json={"target": "both"})

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_update_output_missing_target(self, client, mock_services):
        """Test PUT /settings/output without target."""
        response = client.put("/settings/output", json={})

        assert response.status_code == 400
