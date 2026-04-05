"""Tests for display service and API endpoints."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

from src.displays.service import DisplayService, DisplayResult, get_display_service


class TestDisplayService:
    """Tests for DisplayService class."""
    
    @pytest.fixture
    def mock_plugin_registry(self):
        """Create a mock plugin registry."""
        mock_registry = Mock()
        mock_registry.list_plugins.return_value = [
            {"id": "weather", "name": "Weather", "description": "Current weather conditions"},
            {"id": "datetime", "name": "DateTime", "description": "Current date and time"},
            {"id": "stocks", "name": "Stocks", "description": "Stock prices"},
        ]
        mock_registry.is_enabled.return_value = True
        mock_registry.get_plugin.return_value = Mock()
        return mock_registry
    
    @pytest.fixture
    def service(self, mock_plugin_registry):
        """Create a display service with mocked plugin registry."""
        with patch('src.displays.service.PLUGIN_SYSTEM_AVAILABLE', True), \
             patch('src.displays.service.get_plugin_registry') as mock_get_registry:
            mock_get_registry.return_value = mock_plugin_registry
            service = DisplayService()
            yield service
    
    def test_get_available_displays(self, service, mock_plugin_registry):
        """Test listing available displays."""
        displays = service.get_available_displays()
        
        assert len(displays) == 3
        display_types = [d["type"] for d in displays]
        assert "weather" in display_types
        assert "datetime" in display_types
        assert "stocks" in display_types
    
    def test_get_available_displays_includes_availability(self, service, mock_plugin_registry):
        """Test that availability is correctly reported."""
        displays = service.get_available_displays()
        
        weather = next(d for d in displays if d["type"] == "weather")
        assert "available" in weather
        assert "description" in weather
        assert weather["source"] == "plugin"
    
    def test_get_display_invalid_type(self, service, mock_plugin_registry):
        """Test that invalid display type returns error."""
        mock_plugin_registry.get_plugin.return_value = None
        
        result = service.get_display("invalid_type")
        
        assert result.available is False
        assert "Unknown display type" in result.error
    
    def test_get_display_success(self, service, mock_plugin_registry):
        """Test successful display fetch via plugin system."""
        from src.plugins.base import PluginResult
        
        mock_plugin_result = PluginResult(
            available=True,
            data={"temperature": 72, "condition": "Sunny"},
            formatted_lines=["Sunny, 72F"]
        )
        mock_plugin_registry.fetch_plugin_data.return_value = mock_plugin_result
        
        result = service.get_display("weather")
        
        assert result.display_type == "weather"
        assert result.available is True
        assert result.error is None
        assert "Sunny, 72F" in result.formatted
    
    def test_get_display_plugin_disabled(self, service, mock_plugin_registry):
        """Test display fetch when plugin is disabled."""
        from src.plugins.base import PluginResult
        
        mock_plugin_result = PluginResult(
            available=False,
            error="Plugin not enabled: weather"
        )
        mock_plugin_registry.fetch_plugin_data.return_value = mock_plugin_result
        
        result = service.get_display("weather")
        
        assert result.display_type == "weather"
        assert result.available is False
        assert "not enabled" in result.error


class TestDisplayResult:
    """Tests for DisplayResult dataclass."""
    
    def test_display_result_creation(self):
        """Test creating a DisplayResult."""
        result = DisplayResult(
            display_type="weather",
            formatted="Sunny, 72F",
            raw={"temp": 72},
            available=True
        )
        
        assert result.display_type == "weather"
        assert result.formatted == "Sunny, 72F"
        assert result.raw == {"temp": 72}
        assert result.available is True
        assert result.error is None
    
    def test_display_result_with_error(self):
        """Test DisplayResult with error."""
        result = DisplayResult(
            display_type="weather",
            formatted="",
            raw={},
            available=False,
            error="Source not configured"
        )
        
        assert result.available is False
        assert result.error == "Source not configured"


class TestDisplayAPIEndpoints:
    """Tests for display API endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create a test client."""
        from src.api_server import app
        return TestClient(app)
    
    @pytest.fixture
    def mock_display_service(self):
        """Mock the display service."""
        with patch('src.api_server.get_display_service') as mock:
            mock_service = Mock()
            mock.return_value = mock_service
            yield mock_service
    
    def test_list_displays(self, client, mock_display_service):
        """Test GET /displays endpoint."""
        mock_display_service.get_available_displays.return_value = [
            {"type": "weather", "available": True, "description": "Weather", "source": "plugin"},
            {"type": "date_time", "available": True, "description": "DateTime", "source": "plugin"},
        ]
        
        response = client.get("/displays")
        
        assert response.status_code == 200
        data = response.json()
        assert "displays" in data
        assert data["total"] == 2
        assert data["available_count"] == 2
    
    def test_get_display_success(self, client, mock_display_service):
        """Test GET /displays/{type} endpoint."""
        mock_display_service.get_display.return_value = DisplayResult(
            display_type="weather",
            formatted="Sunny, 72F\nSan Francisco",
            raw={"temp": 72},
            available=True
        )
        
        response = client.get("/displays/weather")
        
        assert response.status_code == 200
        data = response.json()
        assert data["display_type"] == "weather"
        assert data["message"] == "Sunny, 72F\nSan Francisco"
        assert len(data["lines"]) == 2
    
    def test_get_display_invalid_type(self, client, mock_display_service):
        """Test GET /displays/{type} with invalid type."""
        mock_display_service.get_display.return_value = DisplayResult(
            display_type="invalid_type",
            formatted="",
            raw={},
            available=False,
            error="Unknown display type: invalid_type. Valid types: ['weather', 'datetime']"
        )
        
        response = client.get("/displays/invalid_type")
        
        assert response.status_code == 400
        assert "Unknown display type" in response.json()["detail"]
    
    def test_get_display_unavailable(self, client, mock_display_service):
        """Test GET /displays/{type} when source unavailable."""
        mock_display_service.get_display.return_value = DisplayResult(
            display_type="home_assistant",
            formatted="",
            raw={},
            available=False,
            error="Home Assistant not configured"
        )
        
        response = client.get("/displays/home_assistant")
        
        assert response.status_code == 503
        assert "not configured" in response.json()["detail"]
    
    def test_get_display_raw(self, client, mock_display_service):
        """Test GET /displays/{type}/raw endpoint."""
        mock_display_service.get_display.return_value = DisplayResult(
            display_type="weather",
            formatted="Sunny",
            raw={"temperature": 72, "condition": "Sunny", "humidity": 45},
            available=True
        )
        
        response = client.get("/displays/weather/raw")
        
        assert response.status_code == 200
        data = response.json()
        assert data["display_type"] == "weather"
        assert data["data"]["temperature"] == 72
        assert data["available"] is True
    
    def test_get_display_raw_invalid_type(self, client, mock_display_service):
        """Test GET /displays/{type}/raw with invalid type returns 503."""
        mock_display_service.get_display.return_value = DisplayResult(
            display_type="invalid_type",
            formatted="",
            raw={},
            available=False,
            error="Unknown display type: invalid_type"
        )
        
        response = client.get("/displays/invalid_type/raw")
        
        # Raw endpoint returns 503 for any unavailable display
        assert response.status_code == 503


class TestDisplayServiceEdgeCases:
    """Tests for edge cases and error paths in DisplayService."""

    def test_import_error_handling(self):
        """Test module-level ImportError handling for plugin system (lines 17-20)."""
        import importlib
        import sys
        import src.displays.service as svc

        orig_plugins_module = sys.modules.get('src.plugins')

        try:
            # Setting a module to None in sys.modules causes ImportError on import
            sys.modules['src.plugins'] = None
            importlib.reload(svc)

            assert svc.PLUGIN_SYSTEM_AVAILABLE is False
            assert svc.get_plugin_registry is None
            assert svc.PluginRegistry is None
        finally:
            # Restore the plugins module and reload to reset state
            if orig_plugins_module is not None:
                sys.modules['src.plugins'] = orig_plugins_module
            else:
                sys.modules.pop('src.plugins', None)
            importlib.reload(svc)

    def test_init_plugin_registry_init_exception(self):
        """Test __init__ when plugin registry raises during initialization (lines 56-58)."""
        with patch('src.displays.service.PLUGIN_SYSTEM_AVAILABLE', True), \
             patch('src.displays.service.get_plugin_registry') as mock_get:
            mock_get.side_effect = Exception("Registry init failed")
            service = DisplayService()
            assert service._plugin_registry is None

    def test_init_plugin_system_unavailable(self):
        """Test __init__ when plugin system is not available (lines 59-60)."""
        with patch('src.displays.service.PLUGIN_SYSTEM_AVAILABLE', False):
            service = DisplayService()
            assert service._plugin_registry is None

    def test_get_plugin_registry_returns_registry(self):
        """Test get_plugin_registry returns the registry when set (line 66)."""
        mock_registry = Mock()
        with patch('src.displays.service.PLUGIN_SYSTEM_AVAILABLE', True), \
             patch('src.displays.service.get_plugin_registry') as mock_get:
            mock_get.return_value = mock_registry
            service = DisplayService()
            assert service.get_plugin_registry() is mock_registry

    def test_get_plugin_registry_returns_none_when_unavailable(self):
        """Test get_plugin_registry returns None when no registry (line 66)."""
        with patch('src.displays.service.PLUGIN_SYSTEM_AVAILABLE', False):
            service = DisplayService()
            assert service.get_plugin_registry() is None

    def test_get_available_displays_no_registry(self):
        """Test get_available_displays returns empty list when no registry (line 79)."""
        with patch('src.displays.service.PLUGIN_SYSTEM_AVAILABLE', False):
            service = DisplayService()
            assert service.get_available_displays() == []

    def test_get_display_no_registry(self):
        """Test get_display returns error result when no registry (lines 102-108)."""
        with patch('src.displays.service.PLUGIN_SYSTEM_AVAILABLE', False):
            service = DisplayService()
            result = service.get_display("weather")
            assert result.available is False
            assert result.error == "Plugin system not initialized."
            assert result.display_type == "weather"
            assert result.formatted == ""
            assert result.raw == {}

    def test_get_display_fetch_exception(self):
        """Test get_display handles exception during plugin data fetch (lines 147-149)."""
        mock_registry = Mock()
        mock_registry.get_plugin.return_value = Mock()
        mock_registry.fetch_plugin_data.side_effect = RuntimeError("Connection timeout")

        with patch('src.displays.service.PLUGIN_SYSTEM_AVAILABLE', True), \
             patch('src.displays.service.get_plugin_registry') as mock_get:
            mock_get.return_value = mock_registry
            service = DisplayService()
            result = service.get_display("weather")

            assert result.available is False
            assert "Error fetching data" in result.error
            assert "Connection timeout" in result.error
            assert result.display_type == "weather"


class TestResetDisplayService:
    """Tests for reset_display_service singleton management."""

    def test_reset_when_no_instance(self):
        """Test reset_display_service when no instance exists (lines 177-178)."""
        from src.displays.service import reset_display_service
        import src.displays.service as svc

        original = svc._display_service
        try:
            svc._display_service = None
            # Should not raise even when already None
            reset_display_service()
            assert svc._display_service is None
        finally:
            svc._display_service = original
