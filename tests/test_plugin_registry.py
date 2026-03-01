"""Tests for PluginRegistry - manages loaded plugins."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.plugins.base import PluginBase, PluginResult
from src.plugins.manifest import PluginManifest
from src.plugins.registry import (
    PluginRegistry,
    get_plugin_registry,
    reset_plugin_registry,
)


@pytest.fixture
def mock_loader():
    """Create a mock PluginLoader."""
    loader = MagicMock()
    loader.load_all_plugins.return_value = {}
    loader.load_errors = {}
    loader.get_manifest.return_value = None
    loader.reload_plugin.return_value = None
    return loader


@pytest.fixture
def mock_plugin():
    """Create a mock PluginBase instance."""
    plugin = MagicMock(spec=PluginBase)
    plugin.plugin_id = "test_plugin"
    plugin.validate_config.return_value = []
    plugin._validate_refresh_seconds.return_value = []
    plugin.fetch_data.return_value = PluginResult(available=True, data={"key": "value"})
    plugin.get_data.return_value = PluginResult(available=True, data={"key": "value"})
    plugin.enabled = False
    plugin.config = {}
    return plugin


@pytest.fixture
def mock_manifest():
    """Create a mock PluginManifest."""
    manifest = MagicMock(spec=PluginManifest)
    manifest.id = "test_plugin"
    manifest.name = "Test Plugin"
    manifest.version = "1.0.0"
    manifest.description = "A test plugin"
    manifest.author = "Test Author"
    manifest.icon = "puzzle"
    manifest.category = "utility"
    manifest.variables = MagicMock()
    manifest.variables.get_all_variable_names.return_value = ["var1", "var2"]
    manifest.max_lengths = {"var1": 10, "var2": 20}
    manifest.raw = {"variables": {"simple": ["var1", "var2"]}}
    return manifest


@pytest.fixture
def registry(mock_loader):
    """Create PluginRegistry with mocked loader."""
    with patch("src.plugins.registry.PluginLoader", return_value=mock_loader):
        return PluginRegistry(plugins_dir=Path("/fake/plugins"))


# --- __init__ ---


def test_init_creates_empty_dicts(registry):
    """__init__ creates empty dicts for plugins, manifests, configs, enabled."""
    assert registry.plugins == {}
    assert registry.enabled_plugins == {}
    assert registry.get_plugin("any") is None
    assert registry.get_plugin_config("any") is None
    assert not registry.is_enabled("any")


# --- plugins property ---


def test_plugins_property_returns_copy(registry, mock_loader, mock_plugin, mock_manifest):
    """plugins property returns copy of loaded plugins."""
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: mock_manifest if pid == "test_plugin" else None
    registry.initialize()

    plugins = registry.plugins
    assert plugins == {"test_plugin": mock_plugin}
    plugins["test_plugin"] = "modified"
    assert registry.plugins["test_plugin"] is mock_plugin


# --- enabled_plugins property ---


def test_enabled_plugins_returns_only_enabled(registry, mock_loader, mock_plugin, mock_manifest):
    """enabled_plugins returns only enabled ones."""
    plugin2 = MagicMock(spec=PluginBase)
    plugin2.plugin_id = "plugin2"
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin, "plugin2": plugin2}
    mock_loader.get_manifest.side_effect = lambda pid: mock_manifest if pid == "test_plugin" else MagicMock(id=pid, name=pid, version="1.0.0", description="", author="", icon="puzzle", category="utility", variables=MagicMock(get_all_variable_names=lambda _: []), max_lengths={}, raw={})
    registry.initialize()

    assert registry.enabled_plugins == {}
    registry.enable_plugin("test_plugin")
    enabled = registry.enabled_plugins
    assert "test_plugin" in enabled
    assert "plugin2" not in enabled


# --- initialize ---


def test_initialize_loads_plugins_applies_config(registry, mock_loader, mock_plugin, mock_manifest):
    """initialize() loads all plugins, applies stored configs, enables those with enabled=True."""
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: mock_manifest if pid == "test_plugin" else None

    stored_configs = {"test_plugin": {"enabled": True, "api_key": "secret"}}
    with patch("src.config_manager.get_config_manager") as mock_cm:
        mock_cm.return_value.get_all_plugin_configs.return_value = stored_configs
        registry.initialize()

    assert "test_plugin" in registry.plugins
    assert registry.is_enabled("test_plugin")
    assert mock_plugin.config == stored_configs["test_plugin"]
    assert mock_plugin.enabled is True


def test_initialize_handles_config_manager_exception(registry, mock_loader, mock_plugin, mock_manifest):
    """initialize() handles config manager exception gracefully."""
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: mock_manifest if pid == "test_plugin" else None

    with patch("src.config_manager.get_config_manager", side_effect=Exception("config error")):
        registry.initialize()

    assert "test_plugin" in registry.plugins
    assert not registry.is_enabled("test_plugin")


def test_initialize_disabled_plugin_stays_disabled(registry, mock_loader, mock_plugin, mock_manifest):
    """initialize() keeps plugins disabled when enabled=False in config."""
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: mock_manifest if pid == "test_plugin" else None

    with patch("src.config_manager.get_config_manager") as mock_cm:
        mock_cm.return_value.get_all_plugin_configs.return_value = {"test_plugin": {"enabled": False}}
        registry.initialize()

    assert not registry.is_enabled("test_plugin")


# --- get_plugin ---


def test_get_plugin_returns_plugin(registry, mock_loader, mock_plugin, mock_manifest):
    """get_plugin returns plugin when loaded."""
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: mock_manifest if pid == "test_plugin" else None
    registry.initialize()
    assert registry.get_plugin("test_plugin") is mock_plugin


def test_get_plugin_returns_none_for_unknown(registry):
    """get_plugin returns None for unknown plugin."""
    assert registry.get_plugin("unknown") is None


# --- get_manifest ---


def test_get_manifest_returns_manifest(registry, mock_loader, mock_plugin, mock_manifest):
    """get_manifest returns manifest when loaded."""
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: mock_manifest if pid == "test_plugin" else None
    registry.initialize()
    assert registry.get_manifest("test_plugin") is mock_manifest


def test_get_manifest_returns_none_for_unknown(registry):
    """get_manifest returns None for unknown plugin."""
    assert registry.get_manifest("unknown") is None


# --- is_enabled ---


def test_is_enabled_returns_true_when_enabled(registry, mock_loader, mock_plugin, mock_manifest):
    """is_enabled returns True when plugin is enabled."""
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: mock_manifest if pid == "test_plugin" else None
    with patch("src.config_manager.get_config_manager") as mock_cm:
        mock_cm.return_value.get_all_plugin_configs.return_value = {"test_plugin": {"enabled": True}}
        registry.initialize()
    assert registry.is_enabled("test_plugin") is True


def test_is_enabled_returns_false_when_disabled(registry, mock_loader, mock_plugin, mock_manifest):
    """is_enabled returns False when plugin is disabled."""
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: mock_manifest if pid == "test_plugin" else None
    registry.initialize()
    assert registry.is_enabled("test_plugin") is False


# --- enable_plugin ---


def test_enable_plugin_enables_and_applies_config(registry, mock_loader, mock_plugin, mock_manifest):
    """enable_plugin enables plugin and applies stored config."""
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: mock_manifest if pid == "test_plugin" else None
    registry.initialize()
    registry.set_plugin_config("test_plugin", {"api_key": "key123"})

    result = registry.enable_plugin("test_plugin")
    assert result is True
    assert registry.is_enabled("test_plugin")
    assert mock_plugin.enabled is True
    assert mock_plugin.config == {"api_key": "key123"}


def test_enable_plugin_returns_false_for_unknown(registry):
    """enable_plugin returns False for unknown plugin."""
    assert registry.enable_plugin("unknown") is False


# --- disable_plugin ---


def test_disable_plugin_disables_plugin(registry, mock_loader, mock_plugin, mock_manifest):
    """disable_plugin disables plugin."""
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: mock_manifest if pid == "test_plugin" else None
    with patch("src.config_manager.get_config_manager") as mock_cm:
        mock_cm.return_value.get_all_plugin_configs.return_value = {"test_plugin": {"enabled": True}}
        registry.initialize()

    result = registry.disable_plugin("test_plugin")
    assert result is True
    assert not registry.is_enabled("test_plugin")


def test_disable_plugin_returns_false_for_unknown(registry):
    """disable_plugin returns False for unknown plugin."""
    assert registry.disable_plugin("unknown") is False


# --- set_plugin_config ---


def test_set_plugin_config_validates_stores_applies(registry, mock_loader, mock_plugin, mock_manifest):
    """set_plugin_config validates config, stores and applies when valid."""
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: mock_manifest if pid == "test_plugin" else None
    registry.initialize()

    config = {"api_key": "valid"}
    errors = registry.set_plugin_config("test_plugin", config)
    assert errors == []
    assert registry.get_plugin_config("test_plugin") == config
    assert mock_plugin.config == config


def test_set_plugin_config_returns_errors_for_invalid(registry, mock_loader, mock_plugin, mock_manifest):
    """set_plugin_config returns validation errors for invalid config."""
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: mock_manifest if pid == "test_plugin" else None
    mock_plugin.validate_config.return_value = ["API key required"]
    registry.initialize()

    errors = registry.set_plugin_config("test_plugin", {})
    assert errors == ["API key required"]


def test_set_plugin_config_returns_error_for_unknown_plugin(registry):
    """set_plugin_config returns errors for unknown plugin."""
    errors = registry.set_plugin_config("unknown", {"key": "value"})
    assert errors == ["Plugin not found: unknown"]


# --- get_plugin_config ---


def test_get_plugin_config_returns_config(registry, mock_loader, mock_plugin, mock_manifest):
    """get_plugin_config returns config when set."""
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: mock_manifest if pid == "test_plugin" else None
    registry.initialize()
    registry.set_plugin_config("test_plugin", {"key": "value"})
    assert registry.get_plugin_config("test_plugin") == {"key": "value"}


def test_get_plugin_config_returns_none_for_unknown(registry):
    """get_plugin_config returns None for unknown plugin."""
    assert registry.get_plugin_config("unknown") is None


# --- fetch_plugin_data ---


def test_fetch_plugin_data_returns_data_for_enabled(registry, mock_loader, mock_plugin, mock_manifest):
    """fetch_plugin_data returns data for enabled plugin."""
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: mock_manifest if pid == "test_plugin" else None
    with patch("src.config_manager.get_config_manager") as mock_cm:
        mock_cm.return_value.get_all_plugin_configs.return_value = {"test_plugin": {"enabled": True}}
        registry.initialize()

    result = registry.fetch_plugin_data("test_plugin")
    assert result.available is True
    assert result.data == {"key": "value"}


def test_fetch_plugin_data_error_for_disabled(registry, mock_loader, mock_plugin, mock_manifest):
    """fetch_plugin_data returns error for disabled plugin."""
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: mock_manifest if pid == "test_plugin" else None
    registry.initialize()

    result = registry.fetch_plugin_data("test_plugin")
    assert result.available is False
    assert "not enabled" in result.error


def test_fetch_plugin_data_error_for_unknown(registry):
    """fetch_plugin_data returns error for unknown plugin."""
    result = registry.fetch_plugin_data("unknown")
    assert result.available is False
    assert "not found" in result.error


def test_fetch_plugin_data_handles_exception(registry, mock_loader, mock_plugin, mock_manifest):
    """fetch_plugin_data handles plugin fetch exceptions."""
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: mock_manifest if pid == "test_plugin" else None
    mock_plugin.get_data.side_effect = ValueError("fetch failed")
    with patch("src.config_manager.get_config_manager") as mock_cm:
        mock_cm.return_value.get_all_plugin_configs.return_value = {"test_plugin": {"enabled": True}}
        registry.initialize()

    result = registry.fetch_plugin_data("test_plugin")
    assert result.available is False
    assert "fetch failed" in result.error


# --- get_all_variables ---


def test_get_all_variables_from_enabled_only(registry, mock_loader, mock_plugin, mock_manifest):
    """get_all_variables returns variable names from enabled plugins only."""
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: mock_manifest if pid == "test_plugin" else None
    with patch("src.config_manager.get_config_manager") as mock_cm:
        mock_cm.return_value.get_all_plugin_configs.return_value = {"test_plugin": {"enabled": True}}
        registry.initialize()

    variables = registry.get_all_variables()
    assert "test_plugin" in variables
    assert variables["test_plugin"] == ["var1", "var2"]


def test_get_all_variables_excludes_disabled(registry, mock_loader, mock_plugin, mock_manifest):
    """get_all_variables excludes disabled plugins."""
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: mock_manifest if pid == "test_plugin" else None
    registry.initialize()
    variables = registry.get_all_variables()
    assert variables == {}


# --- get_all_max_lengths ---


def test_get_all_max_lengths_from_enabled_only(registry, mock_loader, mock_plugin, mock_manifest):
    """get_all_max_lengths returns max lengths from enabled plugins only."""
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: mock_manifest if pid == "test_plugin" else None
    with patch("src.config_manager.get_config_manager") as mock_cm:
        mock_cm.return_value.get_all_plugin_configs.return_value = {"test_plugin": {"enabled": True}}
        registry.initialize()

    max_lengths = registry.get_all_max_lengths()
    assert "test_plugin.var1" in max_lengths
    assert max_lengths["test_plugin.var1"] == 10
    assert "test_plugin.var2" in max_lengths
    assert max_lengths["test_plugin.var2"] == 20


# --- get_variables_schema ---


def test_get_variables_schema_returns_schema(registry, mock_loader, mock_plugin, mock_manifest):
    """get_variables_schema returns variables schema from manifest."""
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: mock_manifest if pid == "test_plugin" else None
    registry.initialize()

    schema = registry.get_variables_schema("test_plugin")
    assert schema == {"simple": ["var1", "var2"]}


def test_get_variables_schema_returns_none_for_unknown(registry):
    """get_variables_schema returns None for unknown plugin."""
    assert registry.get_variables_schema("unknown") is None


# --- list_plugins ---


def test_list_plugins_returns_sorted_info(registry, mock_loader, mock_plugin, mock_manifest):
    """list_plugins returns sorted list of plugin info dicts."""
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: mock_manifest if pid == "test_plugin" else None
    registry.initialize()

    plugins = registry.list_plugins()
    assert len(plugins) == 1
    info = plugins[0]
    assert info["id"] == "test_plugin"
    assert info["name"] == "Test Plugin"
    assert info["version"] == "1.0.0"
    assert info["enabled"] is False
    assert info["icon"] == "puzzle"
    assert info["category"] == "utility"


def test_list_plugins_sorted_by_name(registry, mock_loader, mock_plugin, mock_manifest):
    """list_plugins sorts by name."""
    plugin_a = MagicMock(spec=PluginBase)
    plugin_a.plugin_id = "plugin_a"
    manifest_a = MagicMock()
    manifest_a.id = "plugin_a"
    manifest_a.name = "Alpha"
    manifest_a.version = "1.0.0"
    manifest_a.description = ""
    manifest_a.author = ""
    manifest_a.icon = "puzzle"
    manifest_a.category = "utility"
    manifest_a.variables = MagicMock(get_all_variable_names=lambda _: [])
    manifest_a.max_lengths = {}
    manifest_a.raw = {}
    plugin_b = MagicMock(spec=PluginBase)
    plugin_b.plugin_id = "plugin_b"
    manifest_b = MagicMock()
    manifest_b.id = "plugin_b"
    manifest_b.name = "Beta"
    manifest_b.version = "1.0.0"
    manifest_b.description = ""
    manifest_b.author = ""
    manifest_b.icon = "puzzle"
    manifest_b.category = "utility"
    manifest_b.variables = MagicMock(get_all_variable_names=lambda _: [])
    manifest_b.max_lengths = {}
    manifest_b.raw = {}

    mock_loader.load_all_plugins.return_value = {"plugin_a": plugin_a, "plugin_b": plugin_b}
    mock_loader.get_manifest.side_effect = lambda pid: manifest_a if pid == "plugin_a" else manifest_b
    registry.initialize()

    plugins = registry.list_plugins()
    assert plugins[0]["name"] == "Alpha"
    assert plugins[1]["name"] == "Beta"


# --- reload_plugin ---


def test_reload_plugin_unloads_reloads_restores(registry, mock_loader, mock_plugin, mock_manifest):
    """reload_plugin unloads, reloads, restores state."""
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: mock_manifest if pid == "test_plugin" else None
    with patch("src.config_manager.get_config_manager") as mock_cm:
        mock_cm.return_value.get_all_plugin_configs.return_value = {"test_plugin": {"enabled": True, "api_key": "key"}}
        registry.initialize()

    new_plugin = MagicMock(spec=PluginBase)
    new_plugin.plugin_id = "test_plugin"
    mock_loader.reload_plugin.return_value = new_plugin

    result = registry.reload_plugin("test_plugin")
    assert result is new_plugin
    mock_plugin.cleanup.assert_called_once()
    mock_loader.reload_plugin.assert_called_once_with("test_plugin")


def test_reload_plugin_returns_none_on_failure(registry, mock_loader, mock_plugin, mock_manifest):
    """reload_plugin returns None if reload fails."""
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: mock_manifest if pid == "test_plugin" else None
    registry.initialize()

    mock_loader.reload_plugin.return_value = None
    result = registry.reload_plugin("test_plugin")
    assert result is None


# --- get_load_errors ---


def test_get_load_errors_returns_loader_errors(registry, mock_loader):
    """get_load_errors returns loader's errors."""
    mock_loader.load_errors = {"bad_plugin": ["manifest error"]}
    errors = registry.get_load_errors()
    assert errors == {"bad_plugin": ["manifest error"]}


# --- build_template_context ---


def test_build_template_context_fetches_from_enabled(registry, mock_loader, mock_plugin, mock_manifest):
    """build_template_context fetches data from all enabled plugins."""
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: mock_manifest if pid == "test_plugin" else None
    with patch("src.config_manager.get_config_manager") as mock_cm:
        mock_cm.return_value.get_all_plugin_configs.return_value = {"test_plugin": {"enabled": True}}
        registry.initialize()

    context = registry.build_template_context()
    assert "test_plugin" in context
    assert context["test_plugin"] == {"key": "value"}


def test_build_template_context_skips_unavailable(registry, mock_loader, mock_plugin, mock_manifest):
    """build_template_context skips plugins that return unavailable."""
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: mock_manifest if pid == "test_plugin" else None
    mock_plugin.get_data.return_value = PluginResult(available=False, error="failed")
    with patch("src.config_manager.get_config_manager") as mock_cm:
        mock_cm.return_value.get_all_plugin_configs.return_value = {"test_plugin": {"enabled": True}}
        registry.initialize()

    context = registry.build_template_context()
    assert "test_plugin" not in context


# --- get_plugin_registry / reset_plugin_registry ---


def test_get_plugin_registry_creates_singleton():
    """get_plugin_registry creates and returns singleton."""
    reset_plugin_registry()
    with patch("src.plugins.registry.PluginRegistry") as MockRegistry:
        mock_instance = MagicMock()
        MockRegistry.return_value = mock_instance
        reg = get_plugin_registry()
        assert reg is mock_instance
        mock_instance.initialize.assert_called_once()
    reset_plugin_registry()


def test_get_plugin_registry_returns_same_instance():
    """get_plugin_registry returns same instance on multiple calls."""
    reset_plugin_registry()
    with patch("src.plugins.registry.PluginRegistry") as MockRegistry:
        mock_instance = MagicMock()
        MockRegistry.return_value = mock_instance
        reg1 = get_plugin_registry()
        reg2 = get_plugin_registry()
        assert reg1 is reg2
        MockRegistry.assert_called_once()
    reset_plugin_registry()


def test_reset_plugin_registry_clears_singleton():
    """reset_plugin_registry clears the singleton."""
    reset_plugin_registry()
    with patch("src.plugins.registry.PluginRegistry") as MockRegistry:
        mock_instance = MagicMock()
        MockRegistry.return_value = mock_instance
        get_plugin_registry()
        reset_plugin_registry()
        get_plugin_registry()
        assert MockRegistry.call_count == 2
    reset_plugin_registry()
