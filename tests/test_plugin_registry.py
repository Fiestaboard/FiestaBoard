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
from src.plugins.sources import PluginSource, RegistryEntry


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
    manifest.fiestaboard_version = ""
    manifest.supports_triggers = False
    manifest.settings_schema = {}
    manifest.variables = MagicMock()
    manifest.variables.auto_discover = False
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
    mock_loader.get_manifest.side_effect = (
        lambda pid: mock_manifest
        if pid == "test_plugin"
        else MagicMock(
            id=pid,
            name=pid,
            version="1.0.0",
            description="",
            author="",
            icon="puzzle",
            category="utility",
            variables=MagicMock(get_all_variable_names=lambda _: []),
            max_lengths={},
            raw={},
        )
    )

    # Patch config manager so the migration doesn't pull in configs from the
    # developer's real data/config.json and auto-install external plugins.
    with patch("src.config_manager.get_config_manager") as mock_cm:
        mock_cm.return_value.get_all_plugin_configs.return_value = {}
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


def test_reload_plugin_preserves_config_when_new_version_fails_validation(
    registry, mock_loader, mock_plugin, mock_manifest
):
    """Regression test for GitHub issue #733.

    When a plugin update ships a stricter settings_schema, the stored user
    config may fail the new validate_config.  For a DISABLED plugin, the only
    code path that sets plugin.config is set_plugin_config — which silently
    returns without applying the config when validation fails.  This leaves
    plugin.config empty so the plugin produces no output when later enabled.

    For an enabled plugin, enable_plugin() applies the config directly (no
    validation) before set_plugin_config is called, which masks the problem.
    The bug is most visible for disabled-but-configured plugins.

    After the fix, reload_plugin falls back to raw config assignment so the
    user's existing settings survive the update even if they no longer pass
    the new validation.
    """
    stored_config = {"api_key": "user-key", "city": "New York"}
    mock_plugin.validate_config.return_value = []
    mock_plugin._validate_refresh_seconds.return_value = []
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: mock_manifest if pid == "test_plugin" else None
    with patch("src.config_manager.get_config_manager") as mock_cm:
        # Plugin is DISABLED but has stored config — the path where the bug bites.
        mock_cm.return_value.get_all_plugin_configs.return_value = {"test_plugin": {"enabled": False, **stored_config}}
        registry.initialize()

    # Verify the stored config was applied during initialization.
    assert mock_plugin.config.get("api_key") == "user-key"

    # Simulate an updated plugin whose validate_config rejects the old config
    # (e.g. a new required field was added that the stored config doesn't have).
    new_plugin = MagicMock(spec=PluginBase)
    new_plugin.plugin_id = "test_plugin"
    new_plugin.validate_config.return_value = ["Missing required field: new_field"]
    new_plugin._validate_refresh_seconds.return_value = []
    new_plugin.config = {}

    mock_loader.reload_plugin.return_value = new_plugin
    mock_loader.get_manifest.side_effect = lambda pid: mock_manifest if pid == "test_plugin" else None

    result = registry.reload_plugin("test_plugin")

    assert result is new_plugin
    # The stored config must survive even though the new plugin rejects it.
    assert new_plugin.config.get("api_key") == "user-key", (
        "plugin.config was empty after reload — stored config was silently discarded"
    )
    assert registry.get_plugin_config("test_plugin").get("api_key") == "user-key"


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


# --- auto-discovery ---


def _make_autodiscover_manifest(auto_discover=True, simple=None):
    """Helper to build a mock manifest with auto_discover settings."""
    from src.plugins.manifest import VariablesSchema

    manifest = MagicMock(spec=PluginManifest)
    manifest.id = "test_plugin"
    manifest.name = "Test Plugin"
    manifest.version = "1.0.0"
    manifest.description = ""
    manifest.author = ""
    manifest.icon = "puzzle"
    manifest.category = "utility"
    manifest.fiestaboard_version = ""
    manifest.max_lengths = {}
    manifest.raw = {}

    vs = VariablesSchema(
        simple=simple or [],
        auto_discover=auto_discover,
    )
    manifest.variables = vs
    return manifest


def test_auto_discover_introspects_data_keys(registry, mock_loader, mock_plugin):
    """When auto_discover is True, live data keys are added to the variable list."""
    manifest = _make_autodiscover_manifest(auto_discover=True, simple=[])
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: manifest if pid == "test_plugin" else None
    mock_plugin.get_data.return_value = PluginResult(available=True, data={"discovered_a": "hello", "discovered_b": 42})
    with patch("src.config_manager.get_config_manager") as mock_cm:
        mock_cm.return_value.get_all_plugin_configs.return_value = {"test_plugin": {"enabled": True}}
        registry.initialize()

    variables = registry.get_all_variables()
    assert "test_plugin" in variables
    assert "discovered_a" in variables["test_plugin"]
    assert "discovered_b" in variables["test_plugin"]


def test_auto_discover_merges_with_manifest(registry, mock_loader, mock_plugin):
    """Auto-discovered keys are merged with manifest-declared variables."""
    manifest = _make_autodiscover_manifest(auto_discover=True, simple=["declared"])
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: manifest if pid == "test_plugin" else None
    mock_plugin.get_data.return_value = PluginResult(available=True, data={"declared": "val", "extra": "bonus"})
    with patch("src.config_manager.get_config_manager") as mock_cm:
        mock_cm.return_value.get_all_plugin_configs.return_value = {"test_plugin": {"enabled": True}}
        registry.initialize()

    variables = registry.get_all_variables()
    assert "declared" in variables["test_plugin"]
    assert "extra" in variables["test_plugin"]


def test_auto_discover_off_hides_undeclared_keys(registry, mock_loader, mock_plugin):
    """When auto_discover is False, only manifest-declared variables appear."""
    manifest = _make_autodiscover_manifest(auto_discover=False, simple=["declared"])
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: manifest if pid == "test_plugin" else None
    mock_plugin.get_data.return_value = PluginResult(available=True, data={"declared": "val", "hidden": "secret"})
    with patch("src.config_manager.get_config_manager") as mock_cm:
        mock_cm.return_value.get_all_plugin_configs.return_value = {"test_plugin": {"enabled": True}}
        registry.initialize()

    variables = registry.get_all_variables()
    assert "declared" in variables["test_plugin"]
    assert "hidden" not in variables["test_plugin"]


def test_auto_discover_on_when_no_variables_section(registry, mock_loader, mock_plugin):
    """Plugins without a variables section get auto_discover=True by default."""
    manifest = _make_autodiscover_manifest(auto_discover=True, simple=[])
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: manifest if pid == "test_plugin" else None
    mock_plugin.get_data.return_value = PluginResult(available=True, data={"auto_field": "value"})
    with patch("src.config_manager.get_config_manager") as mock_cm:
        mock_cm.return_value.get_all_plugin_configs.return_value = {"test_plugin": {"enabled": True}}
        registry.initialize()

    variables = registry.get_all_variables()
    assert "auto_field" in variables["test_plugin"]


def test_get_all_variables_with_metadata(registry, mock_loader, mock_plugin):
    """get_all_variables_with_metadata returns metadata and preview values."""
    from src.plugins.manifest import VariableMetadata, VariablesSchema

    manifest = MagicMock(spec=PluginManifest)
    manifest.id = "test_plugin"
    manifest.name = "Test"
    manifest.version = "1.0.0"
    manifest.description = ""
    manifest.author = ""
    manifest.icon = "puzzle"
    manifest.category = "utility"
    manifest.fiestaboard_version = ""
    manifest.max_lengths = {}
    manifest.raw = {}

    vs = VariablesSchema(
        simple=["temp"],
        auto_discover=False,
        metadata={"temp": VariableMetadata(description="Temperature", type="number")},
    )
    manifest.variables = vs

    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: manifest if pid == "test_plugin" else None
    mock_plugin.get_data.return_value = PluginResult(available=True, data={"temp": "72"})
    with patch("src.config_manager.get_config_manager") as mock_cm:
        mock_cm.return_value.get_all_plugin_configs.return_value = {"test_plugin": {"enabled": True}}
        registry.initialize()

    meta = registry.get_all_variables_with_metadata()
    assert "test_plugin" in meta
    assert "temp" in meta["test_plugin"]
    assert meta["test_plugin"]["temp"]["description"] == "Temperature"
    assert meta["test_plugin"]["temp"]["type"] == "number"
    assert meta["test_plugin"]["temp"]["preview"] == "72"


def test_clear_discovered_cache(registry, mock_loader, mock_plugin):
    """clear_discovered_cache resets the auto-discovery cache."""
    manifest = _make_autodiscover_manifest(auto_discover=True, simple=[])
    mock_loader.load_all_plugins.return_value = {"test_plugin": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: manifest if pid == "test_plugin" else None
    mock_plugin.get_data.return_value = PluginResult(available=True, data={"field": "val"})
    with patch("src.config_manager.get_config_manager") as mock_cm:
        mock_cm.return_value.get_all_plugin_configs.return_value = {"test_plugin": {"enabled": True}}
        registry.initialize()

    registry.get_all_variables()
    assert "test_plugin" in registry._discovered_vars
    registry.clear_discovered_cache("test_plugin")
    assert "test_plugin" not in registry._discovered_vars


# --- check_for_updates / get_update_status ---


def test_check_for_updates_skips_builtin(registry, mock_loader):
    """check_for_updates skips built-in plugins."""
    mock_loader.plugin_sources = {
        "builtin_plugin": PluginSource(source_type="builtin", local_path="/plugins/builtin_plugin"),
    }
    results = registry.check_for_updates()
    assert results == {}


@patch("src.plugins.registry.check_plugin_update_available", return_value=True)
def test_check_for_updates_detects_external(mock_check, registry, mock_loader):
    """check_for_updates checks external plugins and caches results."""
    mock_loader.plugin_sources = {
        "ext_plugin": PluginSource(source_type="external", local_path="/ext/ext_plugin"),
    }
    results = registry.check_for_updates()
    assert results == {"ext_plugin": True}
    assert registry.get_update_status() == {"ext_plugin": True}
    mock_check.assert_called_once()


@patch("src.plugins.registry.check_plugin_update_available", return_value=False)
def test_check_for_updates_no_update(mock_check, registry, mock_loader):
    """check_for_updates returns False when up to date."""
    mock_loader.plugin_sources = {
        "ext_plugin": PluginSource(source_type="external", local_path="/ext/ext_plugin"),
    }
    results = registry.check_for_updates()
    assert results == {"ext_plugin": False}


def test_get_update_status_returns_copy(registry):
    """get_update_status returns a copy of the cached status."""
    registry._update_status = {"p": True}
    status = registry.get_update_status()
    assert status == {"p": True}
    status["p"] = False
    assert registry._update_status["p"] is True


# --- get_plugin_source ---


def test_get_plugin_source_delegates_to_loader(registry, mock_loader):
    """get_plugin_source calls through to the loader."""
    expected = PluginSource(source_type="builtin", local_path="/plugins/test")
    mock_loader.get_source.return_value = expected
    result = registry.get_plugin_source("test_plugin")
    assert result is expected
    mock_loader.get_source.assert_called_once_with("test_plugin")


def test_get_plugin_source_returns_none_for_unknown(registry, mock_loader):
    """get_plugin_source returns None for unknown plugin."""
    mock_loader.get_source.return_value = None
    assert registry.get_plugin_source("unknown") is None


# --- get_registry_entries ---


@patch("src.plugins.registry.load_registry")
def test_get_registry_entries(mock_load, registry):
    """get_registry_entries returns formatted entry list."""
    mock_load.return_value = [
        RegistryEntry(
            plugin_id="weather",
            name="Weather",
            description="Weather data",
            repository="https://github.com/Org/fiestaboard-plugin--weather",
            icon="cloud-sun",
            category="weather",
        ),
    ]
    entries = registry.get_registry_entries()
    assert len(entries) == 1
    assert entries[0]["id"] == "weather"
    assert entries[0]["name"] == "Weather"
    assert entries[0]["installed"] is False


@patch("src.plugins.registry.load_registry")
def test_get_registry_entries_marks_installed(mock_load, registry, mock_loader, mock_plugin, mock_manifest):
    """get_registry_entries marks plugins as installed when loaded."""
    mock_loader.load_all_plugins.return_value = {"weather": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: mock_manifest if pid == "weather" else None
    mock_manifest.id = "weather"
    registry.initialize()

    mock_load.return_value = [
        RegistryEntry(
            plugin_id="weather",
            name="Weather",
            repository="https://github.com/Org/fiestaboard-plugin--weather",
        ),
    ]
    entries = registry.get_registry_entries()
    assert entries[0]["installed"] is True


# --- install_from_registry ---


@patch("src.plugins.registry.get_external_plugins_dir")
@patch("src.plugins.registry.install_registry_plugin", return_value=(True, ""))
@patch("src.plugins.registry.load_registry")
def test_install_from_registry_success(
    mock_load, mock_install, mock_dir, registry, mock_loader, mock_plugin, mock_manifest
):
    """install_from_registry installs and loads the plugin."""
    mock_load.return_value = [
        RegistryEntry(
            plugin_id="weather", name="Weather", repository="https://github.com/Org/fiestaboard-plugin--weather"
        ),
    ]
    mock_loader.load_plugin.return_value = mock_plugin
    mock_loader.get_manifest.return_value = mock_manifest

    errors = registry.install_from_registry("weather")
    assert errors == []
    mock_install.assert_called_once()


@patch("src.plugins.registry.load_registry")
def test_install_from_registry_not_found(mock_load, registry):
    """install_from_registry returns error when plugin not in registry."""
    mock_load.return_value = []
    errors = registry.install_from_registry("nonexistent")
    assert len(errors) == 1
    assert "not found" in errors[0]


@patch("src.plugins.registry.install_registry_plugin", return_value=(False, "clone failed"))
@patch("src.plugins.registry.load_registry")
def test_install_from_registry_clone_failure(mock_load, mock_install, registry):
    """install_from_registry returns error when clone fails."""
    mock_load.return_value = [
        RegistryEntry(
            plugin_id="weather", name="Weather", repository="https://github.com/Org/fiestaboard-plugin--weather"
        ),
    ]
    errors = registry.install_from_registry("weather")
    assert errors == ["clone failed"]


# --- install_from_git ---


@patch("src.plugins.registry.get_external_plugins_dir")
@patch("src.plugins.registry.install_git_plugin", return_value=(True, ""))
def test_install_from_git_success(mock_install, mock_dir, registry, mock_loader, mock_plugin, mock_manifest):
    """install_from_git clones and loads the plugin."""
    mock_loader.load_plugin.return_value = mock_plugin
    mock_loader.get_manifest.return_value = mock_manifest

    errors = registry.install_from_git("https://github.com/someone/my-plugin", plugin_id="my_plugin")
    assert errors == []
    mock_install.assert_called_once()


@patch("src.plugins.registry.install_git_plugin", return_value=(False, "clone failed"))
def test_install_from_git_failure(mock_install, registry):
    """install_from_git returns error when clone fails."""
    errors = registry.install_from_git("https://github.com/someone/my-plugin")
    assert errors == ["clone failed"]


@patch("src.plugins.registry.get_external_plugins_dir")
@patch("src.plugins.registry.install_git_plugin", return_value=(True, ""))
def test_install_from_git_derives_plugin_id(mock_install, mock_dir, registry, mock_loader, mock_plugin, mock_manifest):
    """install_from_git derives plugin_id from URL when not provided."""
    mock_loader.load_plugin.return_value = mock_plugin
    mock_loader.get_manifest.return_value = mock_manifest

    errors = registry.install_from_git("https://github.com/Org/fiestaboard-plugin--surf")
    assert errors == []
    mock_loader.load_plugin.assert_called_with("surf")


# --- _auto_migrate_v2_plugins ---


def test_auto_migrate_noop_when_all_configs_are_loaded(registry, mock_loader, mock_plugin, mock_manifest):
    """_auto_migrate_v2_plugins does nothing when every configured plugin is already loaded."""
    mock_loader.load_all_plugins.return_value = {"weather": mock_plugin}
    mock_loader.get_manifest.side_effect = lambda pid: mock_manifest if pid == "weather" else None
    mock_manifest.id = "weather"

    with (
        patch("src.plugins.registry.load_registry") as mock_load_reg,
        patch("src.config_manager.get_config_manager") as mock_cm,
    ):
        mock_cm.return_value.get_all_plugin_configs.return_value = {"weather": {"enabled": True, "api_key": "key"}}
        registry.initialize()

    # No orphans → load_registry should never be called
    mock_load_reg.assert_not_called()


def test_auto_migrate_noop_when_stored_configs_empty(registry, mock_loader):
    """_auto_migrate_v2_plugins does nothing when there are no stored plugin configs."""
    mock_loader.load_all_plugins.return_value = {}

    with (
        patch("src.plugins.registry.load_registry") as mock_load_reg,
        patch("src.config_manager.get_config_manager") as mock_cm,
    ):
        mock_cm.return_value.get_all_plugin_configs.return_value = {}
        registry.initialize()

    mock_load_reg.assert_not_called()


@patch("src.plugins.registry.get_external_plugins_dir")
@patch("src.plugins.registry.install_registry_plugin", return_value=(True, ""))
@patch("src.plugins.registry.load_registry")
def test_auto_migrate_installs_orphaned_enabled_plugin(
    mock_load_reg, mock_install, mock_ext_dir, registry, mock_loader, mock_plugin, mock_manifest
):
    """_auto_migrate_v2_plugins installs an orphaned plugin and restores its enabled=True state."""
    mock_loader.load_all_plugins.return_value = {}
    mock_manifest.id = "weather"
    mock_load_reg.return_value = [
        RegistryEntry(
            plugin_id="weather",
            name="Weather",
            repository="https://github.com/Org/fiestaboard-plugin--weather",
        )
    ]
    mock_loader.load_plugin.return_value = mock_plugin
    mock_loader.get_manifest.return_value = mock_manifest

    stored_cfg = {"enabled": True, "api_key": "secret_key", "location": "Seattle"}

    with patch("src.config_manager.get_config_manager") as mock_cm:
        mock_cm.return_value.get_all_plugin_configs.return_value = {"weather": stored_cfg}
        registry.initialize()

    assert "weather" in registry._plugins
    assert registry._enabled["weather"] is True
    assert registry._configs["weather"] == stored_cfg
    assert mock_plugin.enabled is True
    assert mock_plugin.config == stored_cfg


@patch("src.plugins.registry.get_external_plugins_dir")
@patch("src.plugins.registry.install_registry_plugin", return_value=(True, ""))
@patch("src.plugins.registry.load_registry")
def test_auto_migrate_installs_orphaned_disabled_plugin(
    mock_load_reg, mock_install, mock_ext_dir, registry, mock_loader, mock_plugin, mock_manifest
):
    """_auto_migrate_v2_plugins installs an orphaned plugin and preserves its enabled=False state."""
    mock_loader.load_all_plugins.return_value = {}
    mock_manifest.id = "muni"
    mock_load_reg.return_value = [
        RegistryEntry(
            plugin_id="muni",
            name="SF Muni",
            repository="https://github.com/Org/fiestaboard-plugin--muni",
        )
    ]
    mock_loader.load_plugin.return_value = mock_plugin
    mock_loader.get_manifest.return_value = mock_manifest

    stored_cfg = {"enabled": False, "api_key": "transit_key", "stop_code": "15726"}

    with patch("src.config_manager.get_config_manager") as mock_cm:
        mock_cm.return_value.get_all_plugin_configs.return_value = {"muni": stored_cfg}
        registry.initialize()

    assert "muni" in registry._plugins
    assert registry._enabled["muni"] is False
    assert mock_plugin.enabled is False


@patch("src.plugins.registry.load_registry")
def test_auto_migrate_skips_plugin_not_in_registry(mock_load_reg, registry, mock_loader):
    """_auto_migrate_v2_plugins logs a warning and skips plugins absent from the registry."""
    mock_loader.load_all_plugins.return_value = {}
    mock_load_reg.return_value = []  # registry is empty

    with patch("src.config_manager.get_config_manager") as mock_cm:
        mock_cm.return_value.get_all_plugin_configs.return_value = {"custom_builtin": {"enabled": True}}
        registry.initialize()

    assert "custom_builtin" not in registry._plugins


@patch("src.plugins.registry.load_registry", side_effect=Exception("DNS failure"))
def test_auto_migrate_handles_registry_load_error_gracefully(mock_load_reg, registry, mock_loader):
    """_auto_migrate_v2_plugins catches registry-load exceptions and does not raise."""
    mock_loader.load_all_plugins.return_value = {}

    with patch("src.config_manager.get_config_manager") as mock_cm:
        mock_cm.return_value.get_all_plugin_configs.return_value = {"weather": {"enabled": True, "api_key": "key"}}
        # Should not raise despite registry failure
        registry.initialize()

    assert "weather" not in registry._plugins


@patch("src.plugins.registry.install_registry_plugin", return_value=(False, "git clone failed"))
@patch("src.plugins.registry.load_registry")
def test_auto_migrate_handles_install_failure_gracefully(mock_load_reg, mock_install, registry, mock_loader):
    """_auto_migrate_v2_plugins logs an error and continues when install fails."""
    mock_loader.load_all_plugins.return_value = {}
    mock_load_reg.return_value = [
        RegistryEntry(
            plugin_id="stocks",
            name="Stocks",
            repository="https://github.com/Org/fiestaboard-plugin--stocks",
        )
    ]

    with patch("src.config_manager.get_config_manager") as mock_cm:
        mock_cm.return_value.get_all_plugin_configs.return_value = {"stocks": {"enabled": True, "symbols": ["AAPL"]}}
        registry.initialize()

    assert "stocks" not in registry._plugins


@patch("src.plugins.registry.get_external_plugins_dir")
@patch("src.plugins.registry.install_registry_plugin", return_value=(True, ""))
@patch("src.plugins.registry.load_registry")
def test_auto_migrate_processes_multiple_orphaned_plugins(
    mock_load_reg, mock_install, mock_ext_dir, registry, mock_loader, mock_manifest
):
    """_auto_migrate_v2_plugins installs all orphaned plugins in one pass."""
    weather_plugin = MagicMock(spec=PluginBase)
    weather_plugin.plugin_id = "weather"
    weather_manifest = MagicMock(spec=PluginManifest)
    weather_manifest.id = "weather"

    muni_plugin = MagicMock(spec=PluginBase)
    muni_plugin.plugin_id = "muni"
    muni_manifest = MagicMock(spec=PluginManifest)
    muni_manifest.id = "muni"

    mock_loader.load_all_plugins.return_value = {}
    mock_load_reg.return_value = [
        RegistryEntry(
            plugin_id="weather",
            name="Weather",
            repository="https://github.com/Org/fiestaboard-plugin--weather",
        ),
        RegistryEntry(
            plugin_id="muni",
            name="SF Muni",
            repository="https://github.com/Org/fiestaboard-plugin--muni",
        ),
    ]

    def _load_plugin(pid):
        return weather_plugin if pid == "weather" else muni_plugin

    def _get_manifest(pid):
        return weather_manifest if pid == "weather" else muni_manifest

    mock_loader.load_plugin.side_effect = _load_plugin
    mock_loader.get_manifest.side_effect = _get_manifest

    with patch("src.config_manager.get_config_manager") as mock_cm:
        mock_cm.return_value.get_all_plugin_configs.return_value = {
            "weather": {"enabled": True, "api_key": "w_key"},
            "muni": {"enabled": True, "api_key": "m_key"},
        }
        registry.initialize()

    assert "weather" in registry._plugins
    assert "muni" in registry._plugins
    assert registry._enabled["weather"] is True
    assert registry._enabled["muni"] is True


@patch("src.plugins.registry.get_external_plugins_dir")
@patch("src.plugins.registry.install_registry_plugin", return_value=(True, ""))
@patch("src.plugins.registry.load_registry")
def test_auto_migrate_skips_already_installed_on_subsequent_boots(
    mock_load_reg, mock_install, mock_ext_dir, registry, mock_loader, mock_plugin, mock_manifest
):
    """_auto_migrate_v2_plugins is idempotent: plugins already in _plugins are skipped."""
    mock_manifest.id = "weather"
    # Simulate "already installed" — weather appears in load_all_plugins output
    mock_loader.load_all_plugins.return_value = {"weather": mock_plugin}
    mock_loader.get_manifest.return_value = mock_manifest

    with patch("src.config_manager.get_config_manager") as mock_cm:
        mock_cm.return_value.get_all_plugin_configs.return_value = {"weather": {"enabled": True, "api_key": "key"}}
        registry.initialize()

    # load_registry should never be called (no orphans to process)
    mock_load_reg.assert_not_called()
    # install_registry_plugin should never be called
    mock_install.assert_not_called()


# --- uninstall_external_plugin ---


@patch("src.plugins.registry.remove_external_plugin")
def test_uninstall_external_plugin_success(mock_remove, registry, mock_loader, mock_plugin, mock_manifest):
    """uninstall_external_plugin removes external plugin."""
    registry._plugins["ext"] = mock_plugin
    registry._manifests["ext"] = mock_manifest
    registry._enabled["ext"] = True
    registry._configs["ext"] = {"key": "val"}

    mock_loader.get_source.return_value = PluginSource(source_type="external", local_path="/ext/ext")

    errors = registry.uninstall_external_plugin("ext")
    assert errors == []
    assert "ext" not in registry._plugins
    assert "ext" not in registry._manifests
    assert "ext" not in registry._enabled
    mock_plugin.cleanup.assert_called_once()
    mock_loader.unload_plugin.assert_called_once_with("ext")
    mock_remove.assert_called_once()


def test_uninstall_external_plugin_not_found(registry, mock_loader):
    """uninstall_external_plugin returns error for unknown plugin."""
    mock_loader.get_source.return_value = None
    errors = registry.uninstall_external_plugin("unknown")
    assert "not found" in errors[0]


def test_uninstall_external_plugin_rejects_builtin(registry, mock_loader):
    """uninstall_external_plugin refuses to remove built-in plugins."""
    mock_loader.get_source.return_value = PluginSource(source_type="builtin", local_path="/plugins/test")
    errors = registry.uninstall_external_plugin("test")
    assert "Cannot uninstall" in errors[0]
