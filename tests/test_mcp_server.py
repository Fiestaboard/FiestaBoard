"""Tests for the FiestaBoard MCP server (src/mcp_server.py).

Tools are exercised directly by calling the inner functions returned by
_build_mcp_server(), bypassing the MCP JSON-RPC layer. Services are mocked
so no real filesystem/network IO is needed.

Strategy
--------
- Import mcp_server._build_mcp_server and call it; the returned FastMCP
  object exposes the tool functions via its internal registry so we can
  introspect what tools were registered.
- For execution testing we call the registered tool functions directly
  through the FastMCP tool manager.
- Service singletons are patched at the module level so the lazy-import
  paths inside the tools resolve to our mocks.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Skip entire module if the mcp package isn't installed
# ---------------------------------------------------------------------------

pytest.importorskip("mcp", reason="mcp package not installed")

from src.mcp_server import _build_mcp_server, mcp_server, _MCP_AVAILABLE  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call_tool(mcp_instance: Any, tool_name: str, **kwargs: Any) -> Any:
    """Synchronously call a registered MCP tool by name.

    FastMCP registers tools in ``_tool_manager``. Each tool's ``fn`` is the
    original decorated function.  We call it directly, bypassing JSON-RPC.

    Page tools that emit an MCP-UI HTML preview return a list of content
    blocks (``[TextContent, EmbeddedResource]``). For backward-compat with
    existing assertions that ``json.loads(result)``, this helper unwraps
    the first ``TextContent`` block to its raw ``.text`` string. Callers
    that need the embedded HTML resource should use ``_call_tool_blocks``.
    """
    import asyncio
    mgr = mcp_instance._tool_manager
    tool = mgr._tools.get(tool_name)
    if tool is None:
        raise KeyError(f"Tool '{tool_name}' not registered. Available: {list(mgr._tools)}")
    result = tool.fn(**kwargs)
    if asyncio.iscoroutine(result):
        result = asyncio.get_event_loop().run_until_complete(result)
    if isinstance(result, list) and result:
        first = result[0]
        if hasattr(first, "text"):
            return first.text
    return result


def _call_tool_blocks(mcp_instance: Any, tool_name: str, **kwargs: Any) -> Any:
    """Like ``_call_tool`` but returns the raw tool return value (list of
    content blocks for page tools, or a string otherwise)."""
    import asyncio
    mgr = mcp_instance._tool_manager
    tool = mgr._tools.get(tool_name)
    if tool is None:
        raise KeyError(f"Tool '{tool_name}' not registered. Available: {list(mgr._tools)}")
    result = tool.fn(**kwargs)
    if asyncio.iscoroutine(result):
        result = asyncio.get_event_loop().run_until_complete(result)
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def mcp():
    """Build a fresh MCP server instance for the test module."""
    instance = _build_mcp_server()
    assert instance is not None, "MCP package is installed but _build_mcp_server() returned None"
    return instance


@pytest.fixture
def mock_registry():
    """Minimal mock plugin registry."""
    registry = MagicMock()
    registry.list_plugins.return_value = [
        {
            "id": "openweather",
            "name": "OpenWeather",
            "enabled": True,
            "description": "Weather data",
            "settings_schema": {"type": "object", "properties": {"api_key": {"type": "string"}}},
        }
    ]
    registry.get_registry_entries.return_value = [
        {"id": "openweather", "name": "OpenWeather", "description": "Weather data", "installed": True},
        {"id": "stocks", "name": "Stocks", "description": "Stock prices", "installed": False},
    ]
    registry.get_all_variables.return_value = {
        "openweather": {
            "temperature": {"description": "Current temperature", "example": "72°F"},
            "condition": {"description": "Weather condition", "example": "Sunny"},
        }
    }
    return registry


@pytest.fixture
def mock_config_manager():
    """Minimal mock config manager."""
    cm = MagicMock()
    cm.get_plugin_config.return_value = {"api_key": "secret123", "units": "imperial"}
    cm._mask_sensitive.return_value = {"api_key": "***", "units": "imperial"}
    return cm


@pytest.fixture
def mock_page_service():
    """Minimal mock page service."""
    svc = MagicMock()
    page = MagicMock()
    page.id = "page-001"
    page.name = "Weather"
    page.type = "template"
    page.device_type = "flagship"
    page.duration_seconds = 300
    page.template = ["{{weather.temperature}}", "{{weather.condition}}"]
    page.model_dump.return_value = {
        "id": "page-001",
        "name": "Weather",
        "type": "template",
        "device_type": "flagship",
        "duration_seconds": 300,
        "template": ["{{weather.temperature}}", "{{weather.condition}}"],
    }
    svc.list_pages.return_value = [page]
    svc.get_page.return_value = page
    result = MagicMock()
    result.id = "page-new"
    result.name = "New Page"
    svc.create_page.return_value = result
    svc.update_page.return_value = page
    delete_result = MagicMock()
    delete_result.success = True
    delete_result.message = "Deleted"
    svc.delete_page.return_value = delete_result
    return svc


@pytest.fixture
def mock_schedule_service():
    """Minimal mock schedule service."""
    svc = MagicMock()
    entry = MagicMock()
    entry.id = "sched-001"
    entry.page_id = "page-001"
    entry.start_time = "08:00"
    entry.end_time = None
    entry.day_pattern = "all"
    entry.enabled = True
    entry.model_dump.return_value = {
        "id": "sched-001",
        "page_id": "page-001",
        "start_time": "08:00",
        "end_time": None,
        "day_pattern": "all",
        "enabled": True,
    }
    svc.list_schedules.return_value = [entry]
    svc.create_schedule.return_value = entry
    svc.update_schedule.return_value = entry
    return svc


@pytest.fixture
def mock_carousel_service():
    """Minimal mock carousel service."""
    svc = MagicMock()
    c = MagicMock()
    c.id = "carousel-001"
    c.name = "Daily"
    c.page_ids = ["page-001", "page-002"]
    c.interval_seconds = 30
    c.model_dump.return_value = {
        "id": "carousel-001",
        "name": "Daily",
        "page_ids": ["page-001", "page-002"],
        "interval_seconds": 30,
    }
    svc.list_carousels.return_value = [c]
    svc.create_carousel.return_value = c
    svc.update_carousel.return_value = c
    return svc


@pytest.fixture
def mock_settings_service():
    """Minimal mock settings service.

    Uses SimpleNamespace for return values so Python 3.14's stricter
    MagicMock.__dict__ handling doesn't interfere.
    """
    from types import SimpleNamespace
    svc = MagicMock()
    svc.get_display_settings.return_value = SimpleNamespace(brightness=80, refresh_rate=30)
    svc.get_location_settings.return_value = SimpleNamespace(
        latitude=40.7128, longitude=-74.0060, timezone="America/New_York"
    )
    svc.get_output_settings.return_value = SimpleNamespace(target="board")
    return svc


# ---------------------------------------------------------------------------
# Module-level guards
# ---------------------------------------------------------------------------

def test_mcp_available():
    """_MCP_AVAILABLE is True when the mcp package is installed."""
    assert _MCP_AVAILABLE is True


def test_mcp_server_singleton_not_none():
    """Module-level mcp_server singleton is not None."""
    assert mcp_server is not None


def test_build_mcp_server_returns_fastmcp(mcp):
    """_build_mcp_server() returns a FastMCP instance."""
    from mcp.server.fastmcp import FastMCP
    assert isinstance(mcp, FastMCP)


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

EXPECTED_TOOLS = {
    # Plugin tools
    "list_installed_plugins",
    "list_registry_plugins",
    "install_plugin",
    "enable_plugin",
    "disable_plugin",
    "uninstall_plugin",
    "configure_plugin",
    "update_plugin",
    "get_template_variables",
    # Page tools
    "list_pages",
    "get_page",
    "create_page",
    "update_page",
    "delete_page",
    # Schedule tools
    "list_schedules",
    "create_schedule",
    "update_schedule",
    "delete_schedule",
    # Carousel tools
    "list_carousels",
    "create_carousel",
    "update_carousel",
    "delete_carousel",
    # System tools
    "get_system_status",
    "get_settings_summary",
    "set_active_page",
    "set_schedule_mode",
}


def test_all_expected_tools_registered(mcp):
    """All expected tools are registered in the MCP server."""
    registered = set(mcp._tool_manager._tools.keys())
    missing = EXPECTED_TOOLS - registered
    assert not missing, f"Missing tools: {missing}"


def test_tool_count(mcp):
    """MCP server has at least 26 tools registered."""
    count = len(mcp._tool_manager._tools)
    assert count >= 26, f"Expected ≥26 tools, found {count}"


# ---------------------------------------------------------------------------
# Plugin tools
# ---------------------------------------------------------------------------

class TestListInstalledPlugins:
    def test_returns_json_array(self, mcp, mock_registry, mock_config_manager):
        # The tool uses lazy imports (`from .plugins import get_plugin_registry`)
        # so we patch the canonical module locations, not src.mcp_server.
        with (
            patch("src.plugins.get_plugin_registry", return_value=mock_registry),
            patch("src.config_manager.get_config_manager", return_value=mock_config_manager),
        ):
            result = _call_tool(mcp, "list_installed_plugins")
        data = json.loads(result)
        assert isinstance(data, list)
        assert data[0]["id"] == "openweather"

    def test_includes_config(self, mcp, mock_registry, mock_config_manager):
        with (
            patch("src.plugins.get_plugin_registry", return_value=mock_registry),
            patch("src.config_manager.get_config_manager", return_value=mock_config_manager),
        ):
            result = _call_tool(mcp, "list_installed_plugins")
        data = json.loads(result)
        assert "config" in data[0]

    def test_error_handling(self, mcp):
        """Returns JSON error object when service call fails."""
        with patch("src.plugins.get_plugin_registry", side_effect=RuntimeError("db unavailable")):
            result = _call_tool(mcp, "list_installed_plugins")
        data = json.loads(result)
        assert "error" in data


class TestListRegistryPlugins:
    def test_returns_registry_entries(self, mcp, mock_registry):
        with patch("src.plugins.get_plugin_registry", return_value=mock_registry):
            result = _call_tool(mcp, "list_registry_plugins")
        data = json.loads(result)
        assert len(data) == 2
        ids = {d["id"] for d in data}
        assert "openweather" in ids
        assert "stocks" in ids


class TestInstallPlugin:
    def test_install_and_enable(self, mcp, mock_registry):
        with patch("src.plugins.get_plugin_registry", return_value=mock_registry):
            result = _call_tool(mcp, "install_plugin", plugin_id="stocks")
        assert "installed and enabled" in result
        mock_registry.install_from_registry.assert_called_once_with("stocks")
        mock_registry.enable_plugin.assert_called_once_with("stocks")

    def test_install_without_enable(self, mcp, mock_registry):
        with patch("src.plugins.get_plugin_registry", return_value=mock_registry):
            result = _call_tool(mcp, "install_plugin", plugin_id="stocks", auto_enable=False)
        assert "installed (disabled)" in result
        mock_registry.enable_plugin.assert_not_called()

    def test_install_error(self, mcp):
        mock_reg = MagicMock()
        mock_reg.install_from_registry.side_effect = ValueError("Not in registry")
        with patch("src.plugins.get_plugin_registry", return_value=mock_reg):
            result = _call_tool(mcp, "install_plugin", plugin_id="unknown")
        assert "Error" in result
        assert "Not in registry" in result


class TestEnablePlugin:
    def test_enable_success(self, mcp, mock_registry):
        with patch("src.plugins.get_plugin_registry", return_value=mock_registry):
            result = _call_tool(mcp, "enable_plugin", plugin_id="openweather")
        assert "enabled successfully" in result

    def test_enable_error(self, mcp):
        mock_reg = MagicMock()
        mock_reg.enable_plugin.side_effect = KeyError("openweather not found")
        with patch("src.plugins.get_plugin_registry", return_value=mock_reg):
            result = _call_tool(mcp, "enable_plugin", plugin_id="openweather")
        assert "Error" in result


class TestDisablePlugin:
    def test_disable_success(self, mcp, mock_registry):
        with patch("src.plugins.get_plugin_registry", return_value=mock_registry):
            result = _call_tool(mcp, "disable_plugin", plugin_id="openweather")
        assert "disabled successfully" in result


class TestUninstallPlugin:
    def test_uninstall_success(self, mcp, mock_registry):
        with patch("src.plugins.get_plugin_registry", return_value=mock_registry):
            result = _call_tool(mcp, "uninstall_plugin", plugin_id="openweather")
        assert "uninstalled successfully" in result
        mock_registry.uninstall_external_plugin.assert_called_once_with("openweather")


class TestConfigurePlugin:
    def test_merges_with_existing_config(self, mcp, mock_registry, mock_config_manager):
        with (
            patch("src.plugins.get_plugin_registry", return_value=mock_registry),
            patch("src.config_manager.get_config_manager", return_value=mock_config_manager),
        ):
            result = _call_tool(
                mcp,
                "configure_plugin",
                plugin_id="openweather",
                config={"api_key": "new-key"},
            )
        data = json.loads(result)
        assert data["status"] == "success"
        assert data["plugin_id"] == "openweather"
        # Should have called set_plugin_config with merged dict
        mock_registry.set_plugin_config.assert_called_once()
        call_args = mock_registry.set_plugin_config.call_args[0]
        assert call_args[0] == "openweather"
        # The merged config should include both existing "units" and new "api_key"
        merged = call_args[1]
        assert "api_key" in merged

    def test_returns_masked_config(self, mcp, mock_registry, mock_config_manager):
        with (
            patch("src.plugins.get_plugin_registry", return_value=mock_registry),
            patch("src.config_manager.get_config_manager", return_value=mock_config_manager),
        ):
            result = _call_tool(
                mcp,
                "configure_plugin",
                plugin_id="openweather",
                config={"api_key": "new-key"},
            )
        data = json.loads(result)
        # Sensitive value should be masked
        assert data["config"]["api_key"] == "***"

    def test_configure_error(self, mcp):
        mock_reg = MagicMock()
        mock_cm = MagicMock()
        mock_cm.get_plugin_config.side_effect = KeyError("plugin not found")
        with (
            patch("src.plugins.get_plugin_registry", return_value=mock_reg),
            patch("src.config_manager.get_config_manager", return_value=mock_cm),
        ):
            result = _call_tool(
                mcp,
                "configure_plugin",
                plugin_id="nonexistent",
                config={"api_key": "x"},
            )
        assert "Error" in result


class TestGetTemplateVariables:
    def test_returns_nested_dict(self, mcp, mock_registry):
        with patch("src.plugins.get_plugin_registry", return_value=mock_registry):
            result = _call_tool(mcp, "get_template_variables")
        data = json.loads(result)
        assert "openweather" in data
        assert "temperature" in data["openweather"]


# ---------------------------------------------------------------------------
# Page tools
# ---------------------------------------------------------------------------

class TestListPages:
    def test_returns_page_list(self, mcp, mock_page_service):
        with patch("src.pages.service.get_page_service", return_value=mock_page_service):
            result = _call_tool(mcp, "list_pages")
        data = json.loads(result)
        assert isinstance(data, list)
        assert data[0]["id"] == "page-001"

    def test_error_returns_json_error(self, mcp):
        mock_svc = MagicMock()
        mock_svc.list_pages.side_effect = RuntimeError("service down")
        with patch("src.pages.service.get_page_service", return_value=mock_svc):
            result = _call_tool(mcp, "list_pages")
        data = json.loads(result)
        assert "error" in data


class TestGetPage:
    def test_returns_page_details(self, mcp, mock_page_service):
        with patch("src.pages.service.get_page_service", return_value=mock_page_service):
            result = _call_tool(mcp, "get_page", page_id="page-001")
        data = json.loads(result)
        assert data["id"] == "page-001"
        assert "template" in data

    def test_not_found(self, mcp):
        mock_svc = MagicMock()
        mock_svc.get_page.return_value = None
        with patch("src.pages.service.get_page_service", return_value=mock_svc):
            result = _call_tool(mcp, "get_page", page_id="missing")
        data = json.loads(result)
        assert "error" in data
        assert "not found" in data["error"]


class TestCreatePage:
    def test_creates_page_returns_id(self, mcp, mock_page_service):
        with patch("src.pages.service.get_page_service", return_value=mock_page_service):
            result = _call_tool(
                mcp,
                "create_page",
                name="My Page",
                template_lines=["Line 1", "Line 2", "Line 3", "Line 4", "Line 5", "Line 6"],
            )
        data = json.loads(result)
        assert data["status"] == "success"
        assert "page_id" in data

    def test_create_page_error(self, mcp):
        mock_svc = MagicMock()
        mock_svc.create_page.side_effect = ValueError("invalid template")
        with patch("src.pages.service.get_page_service", return_value=mock_svc):
            result = _call_tool(
                mcp,
                "create_page",
                name="Bad Page",
                template_lines=["only one line"],
            )
        assert "Error" in result


class TestUpdatePage:
    def test_update_name(self, mcp, mock_page_service):
        with patch("src.pages.service.get_page_service", return_value=mock_page_service):
            result = _call_tool(mcp, "update_page", page_id="page-001", name="New Name")
        data = json.loads(result)
        assert data["status"] == "success"

    def test_not_found(self, mcp):
        mock_svc = MagicMock()
        mock_svc.update_page.return_value = None
        with patch("src.pages.service.get_page_service", return_value=mock_svc):
            result = _call_tool(mcp, "update_page", page_id="missing")
        data = json.loads(result)
        assert "error" in data


class TestPageToolsEmbedHtmlPreview:
    """Page tools attach a ``ui://`` text/html EmbeddedResource as the
    second content block so MCP-UI clients can render a board preview."""

    @staticmethod
    def _assert_html_block(blocks):
        from mcp.types import EmbeddedResource, TextContent
        assert isinstance(blocks, list), f"expected list, got {type(blocks).__name__}"
        assert len(blocks) >= 2, "expected text + html resource blocks"
        assert isinstance(blocks[0], TextContent)
        embedded = blocks[1]
        assert isinstance(embedded, EmbeddedResource)
        assert embedded.resource.mimeType == "text/html"
        assert str(embedded.resource.uri).startswith("ui://fiestaboard/page/")
        html_text = embedded.resource.text
        assert "<!DOCTYPE html>" in html_text
        return html_text

    def test_get_page_embeds_html_preview(self, mcp, mock_page_service):
        # preview_page returns None -> renderer falls back to template lines
        mock_page_service.preview_page.return_value = None
        with patch("src.pages.service.get_page_service", return_value=mock_page_service):
            blocks = _call_tool_blocks(mcp, "get_page", page_id="page-001")
        self._assert_html_block(blocks)

    def test_create_page_embeds_html_preview(self, mcp, mock_page_service):
        mock_page_service.preview_page.return_value = None
        # create_page returns a result MagicMock; give it the attrs the renderer reads.
        result = mock_page_service.create_page.return_value
        result.device_type = "flagship"
        result.template = ["{{red}}HELLO", "WORLD"]
        with patch("src.pages.service.get_page_service", return_value=mock_page_service):
            blocks = _call_tool_blocks(
                mcp,
                "create_page",
                name="My Page",
                template_lines=["Line 1", "Line 2", "Line 3", "Line 4", "Line 5", "Line 6"],
            )
        html_text = self._assert_html_block(blocks)
        # Fallback path uses template lines verbatim, so the red swatch appears.
        assert "#eb4034" in html_text

    def test_update_page_embeds_html_preview(self, mcp, mock_page_service):
        mock_page_service.preview_page.return_value = None
        with patch("src.pages.service.get_page_service", return_value=mock_page_service):
            blocks = _call_tool_blocks(mcp, "update_page", page_id="page-001", name="New Name")
        self._assert_html_block(blocks)


class TestDeletePage:
    def test_delete_success(self, mcp, mock_page_service):
        with patch("src.pages.service.get_page_service", return_value=mock_page_service):
            result = _call_tool(mcp, "delete_page", page_id="page-001")
        assert "deleted successfully" in result

    def test_delete_failure(self, mcp):
        mock_svc = MagicMock()
        fail = MagicMock()
        fail.success = False
        fail.message = "Page is in use"
        mock_svc.delete_page.return_value = fail
        with patch("src.pages.service.get_page_service", return_value=mock_svc):
            result = _call_tool(mcp, "delete_page", page_id="page-001")
        assert "Error" in result or "Page is in use" in result


# ---------------------------------------------------------------------------
# Schedule tools
# ---------------------------------------------------------------------------

class TestListSchedules:
    def test_returns_schedule_list(self, mcp, mock_schedule_service):
        with patch("src.schedules.service.get_schedule_service", return_value=mock_schedule_service):
            result = _call_tool(mcp, "list_schedules")
        data = json.loads(result)
        assert isinstance(data, list)
        assert data[0]["id"] == "sched-001"


class TestCreateSchedule:
    def test_create_schedule_success(self, mcp, mock_schedule_service):
        with patch("src.schedules.service.get_schedule_service", return_value=mock_schedule_service):
            result = _call_tool(
                mcp,
                "create_schedule",
                page_id="page-001",
                start_time="08:00",
                day_pattern="weekdays",
            )
        data = json.loads(result)
        assert data["status"] == "success"
        assert "schedule_id" in data

    def test_create_schedule_error(self, mcp):
        mock_svc = MagicMock()
        mock_svc.create_schedule.side_effect = ValueError("invalid time format")
        with patch("src.schedules.service.get_schedule_service", return_value=mock_svc):
            result = _call_tool(
                mcp,
                "create_schedule",
                page_id="page-001",
                start_time="not-a-time",
            )
        assert "Error" in result


class TestUpdateSchedule:
    def test_update_success(self, mcp, mock_schedule_service):
        with patch("src.schedules.service.get_schedule_service", return_value=mock_schedule_service):
            result = _call_tool(mcp, "update_schedule", schedule_id="sched-001", enabled=False)
        data = json.loads(result)
        assert data["status"] == "success"

    def test_not_found(self, mcp):
        mock_svc = MagicMock()
        mock_svc.update_schedule.return_value = None
        with patch("src.schedules.service.get_schedule_service", return_value=mock_svc):
            result = _call_tool(mcp, "update_schedule", schedule_id="missing")
        assert "not found" in result


class TestDeleteSchedule:
    def test_delete_success(self, mcp, mock_schedule_service):
        with patch("src.schedules.service.get_schedule_service", return_value=mock_schedule_service):
            result = _call_tool(mcp, "delete_schedule", schedule_id="sched-001")
        assert "deleted successfully" in result


# ---------------------------------------------------------------------------
# Carousel tools
# ---------------------------------------------------------------------------

class TestListCarousels:
    def test_returns_carousel_list(self, mcp, mock_carousel_service):
        with patch("src.carousels.service.get_carousel_service", return_value=mock_carousel_service):
            result = _call_tool(mcp, "list_carousels")
        data = json.loads(result)
        assert data[0]["id"] == "carousel-001"
        assert len(data[0]["page_ids"]) == 2


class TestCreateCarousel:
    def test_create_success(self, mcp, mock_carousel_service):
        with patch("src.carousels.service.get_carousel_service", return_value=mock_carousel_service):
            result = _call_tool(
                mcp,
                "create_carousel",
                name="Morning Show",
                page_ids=["page-001", "page-002"],
                interval_seconds=60,
            )
        data = json.loads(result)
        assert data["status"] == "success"
        assert "carousel_id" in data


class TestUpdateCarousel:
    def test_update_success(self, mcp, mock_carousel_service):
        with patch("src.carousels.service.get_carousel_service", return_value=mock_carousel_service):
            result = _call_tool(mcp, "update_carousel", carousel_id="carousel-001", name="Renamed")
        data = json.loads(result)
        assert data["status"] == "success"

    def test_not_found(self, mcp):
        mock_svc = MagicMock()
        mock_svc.update_carousel.return_value = None
        with patch("src.carousels.service.get_carousel_service", return_value=mock_svc):
            result = _call_tool(mcp, "update_carousel", carousel_id="missing")
        assert "not found" in result


class TestDeleteCarousel:
    def test_delete_success(self, mcp, mock_carousel_service):
        with patch("src.carousels.service.get_carousel_service", return_value=mock_carousel_service):
            result = _call_tool(mcp, "delete_carousel", carousel_id="carousel-001")
        assert "deleted successfully" in result


# ---------------------------------------------------------------------------
# System tools
# ---------------------------------------------------------------------------

class TestGetSystemStatus:
    def test_returns_version_and_status(self, mcp, mock_registry):
        with (
            patch("src.mcp_server._service_running", False, create=True),
            patch("src.plugins.get_plugin_registry", return_value=mock_registry),
        ):
            # Patch the import inside the tool function
            import src.api_server as api_mod
            orig_running = getattr(api_mod, "_service_running", False)
            try:
                api_mod._service_running = True
                with patch("src.api_server.get_service", return_value=MagicMock()):
                    result = _call_tool(mcp, "get_system_status")
            finally:
                api_mod._service_running = orig_running
        data = json.loads(result)
        assert "version" in data
        assert "plugins_installed" in data

    def test_returns_plugin_counts(self, mcp, mock_registry):
        import src.api_server as api_mod
        with patch("src.api_server.get_service", return_value=None):
            result = _call_tool(mcp, "get_system_status")
        data = json.loads(result)
        assert isinstance(data.get("plugins_installed"), int)


class TestGetSettingsSummary:
    def test_returns_settings_sections(self, mcp, mock_settings_service):
        with patch("src.settings.service.get_settings_service", return_value=mock_settings_service):
            result = _call_tool(mcp, "get_settings_summary")
        data = json.loads(result)
        # Should have at least one section
        assert len(data) > 0


class TestSetActivePage:
    def test_set_active_page(self, mcp):
        mock_cm = MagicMock()
        with patch("src.config_manager.get_config_manager", return_value=mock_cm):
            result = _call_tool(mcp, "set_active_page", page_id="page-001")
        assert "page-001" in result
        mock_cm.set_active_page.assert_called_once_with("page-001")

    def test_error_handling(self, mcp):
        mock_cm = MagicMock()
        mock_cm.set_active_page.side_effect = ValueError("page not found")
        with patch("src.config_manager.get_config_manager", return_value=mock_cm):
            result = _call_tool(mcp, "set_active_page", page_id="bad-id")
        assert "Error" in result


class TestSetScheduleMode:
    def test_enable(self, mcp, mock_schedule_service):
        with patch("src.schedules.service.get_schedule_service", return_value=mock_schedule_service):
            result = _call_tool(mcp, "set_schedule_mode", enabled=True)
        assert "enabled" in result

    def test_disable(self, mcp, mock_schedule_service):
        with patch("src.schedules.service.get_schedule_service", return_value=mock_schedule_service):
            result = _call_tool(mcp, "set_schedule_mode", enabled=False)
        assert "disabled" in result


# ---------------------------------------------------------------------------
# MCP Resources
# ---------------------------------------------------------------------------

def _call_resource(mcp_instance: Any, uri: str) -> str:
    """Call a resource handler directly."""
    import asyncio
    mgr = mcp_instance._resource_manager
    # Resources are keyed by URI template
    for key, resource in mgr._resources.items():
        if key == uri or str(key) == uri:
            result = resource.fn()
            if asyncio.iscoroutine(result):
                result = asyncio.get_event_loop().run_until_complete(result)
            return result
    raise KeyError(f"Resource '{uri}' not found. Available: {list(mgr._resources.keys())}")


class TestMCPResources:
    def test_plugins_resource(self, mcp, mock_registry):
        with patch("src.plugins.get_plugin_registry", return_value=mock_registry):
            result = _call_resource(mcp, "fiestaboard://plugins")
        assert "OpenWeather" in result
        assert "openweather" in result

    def test_pages_resource(self, mcp, mock_page_service):
        with patch("src.pages.service.get_page_service", return_value=mock_page_service):
            result = _call_resource(mcp, "fiestaboard://pages")
        assert "Weather" in result
        assert "page-001" in result

    def test_variables_resource(self, mcp, mock_registry):
        with patch("src.plugins.get_plugin_registry", return_value=mock_registry):
            result = _call_resource(mcp, "fiestaboard://variables")
        assert "temperature" in result
        assert "openweather" in result


# ---------------------------------------------------------------------------
# MCP Prompts
# ---------------------------------------------------------------------------

def _call_prompt(mcp_instance: Any, prompt_name: str, **kwargs: Any) -> str:
    """Call a prompt handler directly."""
    import asyncio
    mgr = mcp_instance._prompt_manager
    prompt = mgr._prompts.get(prompt_name)
    if prompt is None:
        raise KeyError(f"Prompt '{prompt_name}' not found. Available: {list(mgr._prompts.keys())}")
    result = prompt.fn(**kwargs)
    if asyncio.iscoroutine(result):
        result = asyncio.get_event_loop().run_until_complete(result)
    return result


class TestMCPPrompts:
    def test_setup_fiestaboard_prompt(self, mcp):
        result = _call_prompt(mcp, "setup_fiestaboard")
        assert "list_installed_plugins" in result
        assert "list_pages" in result

    def test_create_display_page_prompt_default_topic(self, mcp):
        result = _call_prompt(mcp, "create_display_page")
        assert "weather" in result.lower()
        assert "get_template_variables" in result

    def test_create_display_page_prompt_custom_topic(self, mcp):
        result = _call_prompt(mcp, "create_display_page", topic="stocks")
        assert "stocks" in result


# ---------------------------------------------------------------------------
# Error resilience: ensure no tool raises an unhandled exception
# ---------------------------------------------------------------------------

class TestToolErrorResilience:
    """All tools should catch exceptions and return an error string / JSON."""

    @pytest.mark.parametrize("tool_name,kwargs", [
        ("list_installed_plugins", {}),
        ("list_registry_plugins", {}),
        ("install_plugin", {"plugin_id": "x"}),
        ("enable_plugin", {"plugin_id": "x"}),
        ("disable_plugin", {"plugin_id": "x"}),
        ("uninstall_plugin", {"plugin_id": "x"}),
        ("configure_plugin", {"plugin_id": "x", "config": {}}),
        ("update_plugin", {"plugin_id": "x"}),
        ("get_template_variables", {}),
        ("list_pages", {}),
        ("get_page", {"page_id": "x"}),
        ("create_page", {"name": "x", "template_lines": []}),
        ("update_page", {"page_id": "x"}),
        ("delete_page", {"page_id": "x"}),
        ("list_schedules", {}),
        ("create_schedule", {"page_id": "x", "start_time": "08:00"}),
        ("update_schedule", {"schedule_id": "x"}),
        ("delete_schedule", {"schedule_id": "x"}),
        ("list_carousels", {}),
        ("create_carousel", {"name": "x", "page_ids": []}),
        ("update_carousel", {"carousel_id": "x"}),
        ("delete_carousel", {"carousel_id": "x"}),
        ("get_system_status", {}),
        ("get_settings_summary", {}),
        ("set_active_page", {"page_id": "x"}),
        ("set_schedule_mode", {"enabled": True}),
    ])
    def test_tool_does_not_raise(self, mcp, tool_name: str, kwargs: dict):
        """Each tool returns a string (not raises) even when all services fail."""
        with (
            patch("src.plugins.get_plugin_registry", side_effect=RuntimeError("boom")),
            patch("src.pages.service.get_page_service", side_effect=RuntimeError("boom")),
            patch("src.schedules.service.get_schedule_service", side_effect=RuntimeError("boom")),
            patch("src.carousels.service.get_carousel_service", side_effect=RuntimeError("boom")),
            patch("src.settings.service.get_settings_service", side_effect=RuntimeError("boom")),
            patch("src.config_manager.get_config_manager", side_effect=RuntimeError("boom")),
            patch("src.api_server.get_service", side_effect=RuntimeError("boom")),
        ):
            result = _call_tool(mcp, tool_name, **kwargs)
        assert result is not None
        assert isinstance(result, str)
        # Must not be empty
        assert len(result) > 0
