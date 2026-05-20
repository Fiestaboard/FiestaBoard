"""Tests for multi-instance plugin support.

Validates that plugins can be instantiated multiple times with
independent configurations, enabled states, and data.
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.plugins.base import PluginBase, PluginResult
from src.plugins.manifest import PluginManifest
from src.plugins.registry import (
    PluginRegistry,
    _INSTANCE_LABEL_RE,
)


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_loader():
    """Create a mock PluginLoader."""
    loader = MagicMock()
    loader.load_all_plugins.return_value = {}
    loader.load_errors = {}
    loader.get_manifest.return_value = None
    loader.reload_plugin.return_value = None
    loader.get_source.return_value = None
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


@pytest.fixture
def registry_with_plugin(registry, mock_plugin, mock_manifest, mock_loader):
    """Registry with one plugin already loaded."""
    registry._plugins["test_plugin"] = mock_plugin
    registry._manifests["test_plugin"] = mock_manifest
    registry._enabled["test_plugin"] = True

    # Allow creating instances
    new_plugin = MagicMock(spec=PluginBase)
    new_plugin.plugin_id = "test_plugin"
    new_plugin.validate_config.return_value = []
    new_plugin._validate_refresh_seconds.return_value = []
    new_plugin.get_data.return_value = PluginResult(available=True, data={"instance": True})
    new_plugin.enabled = False
    new_plugin.config = {}
    mock_loader.create_instance.return_value = new_plugin

    return registry


# ── static helpers ──────────────────────────────────────────────────────────


class TestInstanceKeyHelpers:
    """Tests for make_instance_key / parse_instance_key / is_instance_key."""

    def test_make_instance_key(self):
        assert PluginRegistry.make_instance_key("weather", "sf") == "weather:sf"

    def test_make_instance_key_with_underscores(self):
        assert PluginRegistry.make_instance_key("generic_data", "my_api") == "generic_data:my_api"

    def test_parse_instance_key_compound(self):
        base, label = PluginRegistry.parse_instance_key("weather:sf")
        assert base == "weather"
        assert label == "sf"

    def test_parse_instance_key_simple(self):
        base, label = PluginRegistry.parse_instance_key("weather")
        assert base == "weather"
        assert label is None

    def test_parse_instance_key_multiple_separators(self):
        """Only the first separator is split."""
        base, label = PluginRegistry.parse_instance_key("weather:sf:extra")
        assert base == "weather"
        assert label == "sf:extra"

    def test_is_instance_key_true(self):
        assert PluginRegistry.is_instance_key("weather:sf") is True

    def test_is_instance_key_false(self):
        assert PluginRegistry.is_instance_key("weather") is False

    def test_roundtrip(self):
        key = PluginRegistry.make_instance_key("stocks", "nasdaq")
        base, label = PluginRegistry.parse_instance_key(key)
        assert base == "stocks"
        assert label == "nasdaq"


class TestInstanceLabelRegex:
    """Tests for valid/invalid instance labels."""

    @pytest.mark.parametrize("label", ["sf", "my_api", "prod-1", "A", "abc123", "a" * 40])
    def test_valid_labels(self, label):
        assert _INSTANCE_LABEL_RE.match(label)

    @pytest.mark.parametrize("label", ["", " ", "a b", "sf!", "a:b", "a" * 41, "hello world"])
    def test_invalid_labels(self, label):
        assert not _INSTANCE_LABEL_RE.match(label)


# ── create_instance ─────────────────────────────────────────────────────────


class TestCreateInstance:
    """Tests for PluginRegistry.create_instance()."""

    def test_create_instance_success(self, registry_with_plugin):
        errors = registry_with_plugin.create_instance("test_plugin", "my_inst")
        assert errors == []
        assert "test_plugin:my_inst" in registry_with_plugin._plugins
        assert registry_with_plugin._enabled["test_plugin:my_inst"] is False
        assert registry_with_plugin._configs["test_plugin:my_inst"] == {}

    def test_create_instance_uses_base_manifest(self, registry_with_plugin, mock_manifest):
        registry_with_plugin.create_instance("test_plugin", "inst1")
        assert registry_with_plugin._manifests["test_plugin:inst1"] is mock_manifest

    def test_create_instance_invalid_label_empty(self, registry_with_plugin):
        errors = registry_with_plugin.create_instance("test_plugin", "")
        assert len(errors) == 1
        assert "Invalid instance label" in errors[0]

    def test_create_instance_invalid_label_spaces(self, registry_with_plugin):
        errors = registry_with_plugin.create_instance("test_plugin", "a b")
        assert len(errors) == 1
        assert "Invalid instance label" in errors[0]

    def test_create_instance_invalid_label_too_long(self, registry_with_plugin):
        errors = registry_with_plugin.create_instance("test_plugin", "a" * 41)
        assert len(errors) == 1
        assert "Invalid instance label" in errors[0]

    def test_create_instance_unknown_plugin(self, registry_with_plugin):
        errors = registry_with_plugin.create_instance("nonexistent", "inst1")
        assert len(errors) == 1
        assert "Plugin not found" in errors[0]

    def test_create_instance_duplicate(self, registry_with_plugin):
        errors1 = registry_with_plugin.create_instance("test_plugin", "dup")
        assert errors1 == []
        errors2 = registry_with_plugin.create_instance("test_plugin", "dup")
        assert len(errors2) == 1
        assert "already exists" in errors2[0]

    def test_create_instance_loader_failure(self, registry_with_plugin, mock_loader):
        mock_loader.create_instance.return_value = None
        errors = registry_with_plugin.create_instance("test_plugin", "fail")
        assert len(errors) == 1
        assert "Failed to create instance" in errors[0]

    def test_create_multiple_instances(self, registry_with_plugin, mock_loader):
        """Create multiple instances of the same plugin."""
        # Each call to create_instance returns a fresh mock
        mock_loader.create_instance.side_effect = [
            MagicMock(spec=PluginBase),
            MagicMock(spec=PluginBase),
            MagicMock(spec=PluginBase),
        ]
        assert registry_with_plugin.create_instance("test_plugin", "a") == []
        assert registry_with_plugin.create_instance("test_plugin", "b") == []
        assert registry_with_plugin.create_instance("test_plugin", "c") == []
        assert "test_plugin:a" in registry_with_plugin._plugins
        assert "test_plugin:b" in registry_with_plugin._plugins
        assert "test_plugin:c" in registry_with_plugin._plugins

    def test_create_instance_normalizes_mixed_case_label(self, registry_with_plugin):
        """Mixed-case labels are stored lowercase so the template engine's
        case-insensitive variable lookup matches the compound key (#774)."""
        errors = registry_with_plugin.create_instance("test_plugin", "FijiAustralia")
        assert errors == []
        assert "test_plugin:fijiaustralia" in registry_with_plugin._plugins
        assert "test_plugin:FijiAustralia" not in registry_with_plugin._plugins

    def test_create_instance_duplicate_differs_only_in_case(self, registry_with_plugin):
        """Two labels that differ only in case should collide (both normalize)."""
        assert registry_with_plugin.create_instance("test_plugin", "Wedding") == []
        errors = registry_with_plugin.create_instance("test_plugin", "WEDDING")
        assert len(errors) == 1
        assert "already exists" in errors[0]


# ── delete_instance ─────────────────────────────────────────────────────────


class TestDeleteInstance:
    """Tests for PluginRegistry.delete_instance()."""

    def test_delete_instance_success(self, registry_with_plugin):
        registry_with_plugin.create_instance("test_plugin", "del_me")
        assert "test_plugin:del_me" in registry_with_plugin._plugins

        errors = registry_with_plugin.delete_instance("test_plugin", "del_me")
        assert errors == []
        assert "test_plugin:del_me" not in registry_with_plugin._plugins
        assert "test_plugin:del_me" not in registry_with_plugin._manifests
        assert "test_plugin:del_me" not in registry_with_plugin._enabled
        assert "test_plugin:del_me" not in registry_with_plugin._configs

    def test_delete_instance_calls_cleanup(self, registry_with_plugin):
        registry_with_plugin.create_instance("test_plugin", "cleanup_test")
        instance_plugin = registry_with_plugin._plugins["test_plugin:cleanup_test"]
        registry_with_plugin.delete_instance("test_plugin", "cleanup_test")
        instance_plugin.cleanup.assert_called_once()

    def test_delete_nonexistent_instance(self, registry_with_plugin):
        errors = registry_with_plugin.delete_instance("test_plugin", "nope")
        assert len(errors) == 1
        assert "not found" in errors[0]

    def test_delete_instance_clears_discovered_vars(self, registry_with_plugin):
        registry_with_plugin.create_instance("test_plugin", "dv")
        registry_with_plugin._discovered_vars["test_plugin:dv"] = ["a", "b"]
        registry_with_plugin.delete_instance("test_plugin", "dv")
        assert "test_plugin:dv" not in registry_with_plugin._discovered_vars


# ── list_instances ──────────────────────────────────────────────────────────


class TestListInstances:
    """Tests for PluginRegistry.list_instances()."""

    def test_list_instances_empty(self, registry_with_plugin):
        instances = registry_with_plugin.list_instances("test_plugin")
        assert instances == []

    def test_list_instances_single(self, registry_with_plugin):
        registry_with_plugin.create_instance("test_plugin", "alpha")
        instances = registry_with_plugin.list_instances("test_plugin")
        assert len(instances) == 1
        assert instances[0]["label"] == "alpha"
        assert instances[0]["key"] == "test_plugin:alpha"
        assert instances[0]["enabled"] is False

    def test_list_instances_multiple_sorted(self, registry_with_plugin, mock_loader):
        mock_loader.create_instance.side_effect = [
            MagicMock(spec=PluginBase),
            MagicMock(spec=PluginBase),
        ]
        registry_with_plugin.create_instance("test_plugin", "beta")
        registry_with_plugin.create_instance("test_plugin", "alpha")
        instances = registry_with_plugin.list_instances("test_plugin")
        assert len(instances) == 2
        assert instances[0]["label"] == "alpha"
        assert instances[1]["label"] == "beta"

    def test_list_instances_for_unknown_plugin(self, registry_with_plugin):
        """Returns empty list for unknown plugin."""
        instances = registry_with_plugin.list_instances("nonexistent")
        assert instances == []


# ── integration: instances in list_plugins ──────────────────────────────────


class TestListPluginsWithInstances:
    """Verify that list_plugins includes instance metadata."""

    def test_base_plugin_has_null_instance_label(self, registry_with_plugin):
        plugins = registry_with_plugin.list_plugins()
        base = next(p for p in plugins if p["id"] == "test_plugin")
        assert base["instance_label"] is None
        assert base["base_plugin_id"] == "test_plugin"

    def test_instance_has_label_and_base_id(self, registry_with_plugin):
        registry_with_plugin.create_instance("test_plugin", "inst1")
        plugins = registry_with_plugin.list_plugins()
        instance = next(p for p in plugins if p["id"] == "test_plugin:inst1")
        assert instance["instance_label"] == "inst1"
        assert instance["base_plugin_id"] == "test_plugin"

    def test_instance_name_includes_label(self, registry_with_plugin):
        registry_with_plugin.create_instance("test_plugin", "inst1")
        plugins = registry_with_plugin.list_plugins()
        instance = next(p for p in plugins if p["id"] == "test_plugin:inst1")
        assert "(inst1)" in instance["name"]


# ── integration: instances with config / enable / disable ───────────────────


class TestInstanceConfigAndState:
    """Verify that instances have independent config and enabled state."""

    def test_instance_config_independent_from_base(self, registry_with_plugin):
        registry_with_plugin.create_instance("test_plugin", "cfg_test")
        registry_with_plugin.set_plugin_config("test_plugin", {"api_key": "base_key"})
        registry_with_plugin.set_plugin_config("test_plugin:cfg_test", {"api_key": "inst_key"})

        assert registry_with_plugin.get_plugin_config("test_plugin")["api_key"] == "base_key"
        assert registry_with_plugin.get_plugin_config("test_plugin:cfg_test")["api_key"] == "inst_key"

    def test_instance_enabled_independent_from_base(self, registry_with_plugin):
        registry_with_plugin.create_instance("test_plugin", "state_test")
        registry_with_plugin.enable_plugin("test_plugin:state_test")

        assert registry_with_plugin.is_enabled("test_plugin") is True
        assert registry_with_plugin.is_enabled("test_plugin:state_test") is True

        registry_with_plugin.disable_plugin("test_plugin")
        assert registry_with_plugin.is_enabled("test_plugin") is False
        assert registry_with_plugin.is_enabled("test_plugin:state_test") is True

    def test_fetch_data_from_instance(self, registry_with_plugin):
        registry_with_plugin.create_instance("test_plugin", "data_test")
        registry_with_plugin.enable_plugin("test_plugin:data_test")
        result = registry_with_plugin.fetch_plugin_data("test_plugin:data_test")
        assert result.available is True

    def test_fetch_data_from_disabled_instance(self, registry_with_plugin):
        registry_with_plugin.create_instance("test_plugin", "disabled")
        # Instance starts disabled
        result = registry_with_plugin.fetch_plugin_data("test_plugin:disabled")
        assert result.available is False


# ── integration: instances in build_template_context ────────────────────────


class TestBuildTemplateContextWithInstances:
    """Verify instances contribute to the template context."""

    def test_enabled_instance_in_context(self, registry_with_plugin):
        registry_with_plugin.create_instance("test_plugin", "ctx")
        registry_with_plugin.enable_plugin("test_plugin:ctx")
        context = registry_with_plugin.build_template_context()
        # Both base and instance should be in context
        assert "test_plugin" in context
        assert "test_plugin:ctx" in context

    def test_disabled_instance_not_in_context(self, registry_with_plugin):
        registry_with_plugin.create_instance("test_plugin", "off")
        # Instance is disabled by default
        context = registry_with_plugin.build_template_context()
        assert "test_plugin" in context  # base is enabled
        assert "test_plugin:off" not in context


# ── restore instances from config ───────────────────────────────────────────


class TestRestoreInstances:
    """Test _restore_instances() for boot-time restoration."""

    def test_restore_instances_from_stored_configs(self, registry_with_plugin, mock_loader):
        """Instances stored in config are restored via the proper enable pipeline."""
        stored_configs = {
            "test_plugin": {"enabled": True},
            "test_plugin:restored": {"enabled": True, "api_key": "saved_key"},
        }
        new_plugin = MagicMock(spec=PluginBase)
        new_plugin.validate_config.return_value = []
        new_plugin._validate_refresh_seconds.return_value = []
        new_plugin.enabled = False
        new_plugin.config = {}
        mock_loader.create_instance.return_value = new_plugin

        registry_with_plugin._restore_instances(stored_configs)

        assert "test_plugin:restored" in registry_with_plugin._plugins
        # Enabled via enable_plugin() which sets _enabled dict
        assert registry_with_plugin._enabled["test_plugin:restored"] is True
        # Config stored via set_plugin_config()
        assert registry_with_plugin._configs["test_plugin:restored"]["api_key"] == "saved_key"

    def test_restore_uses_enable_plugin_pipeline(self, registry_with_plugin, mock_loader):
        """_restore_instances uses enable_plugin() not direct attribute assignment."""
        stored_configs = {
            "test_plugin:inst": {"enabled": True, "setting": "value"},
        }
        new_plugin = MagicMock(spec=PluginBase)
        new_plugin.validate_config.return_value = []
        new_plugin._validate_refresh_seconds.return_value = []
        new_plugin.enabled = False
        new_plugin.config = {}
        mock_loader.create_instance.return_value = new_plugin

        registry_with_plugin._restore_instances(stored_configs)

        # enable_plugin() sets plugin.enabled = True
        assert new_plugin.enabled is True

    def test_restore_disabled_instance_not_enabled(self, registry_with_plugin, mock_loader):
        """Instances stored as disabled should remain disabled after restore."""
        stored_configs = {
            "test_plugin:inst": {"enabled": False, "setting": "value"},
        }
        new_plugin = MagicMock(spec=PluginBase)
        new_plugin.validate_config.return_value = []
        new_plugin._validate_refresh_seconds.return_value = []
        new_plugin.enabled = False
        new_plugin.config = {}
        mock_loader.create_instance.return_value = new_plugin

        registry_with_plugin._restore_instances(stored_configs)

        assert registry_with_plugin._enabled.get("test_plugin:inst") is False

    def test_restore_skips_non_instance_keys(self, registry_with_plugin):
        stored_configs = {"test_plugin": {"enabled": True}}
        registry_with_plugin._restore_instances(stored_configs)
        # No instances should be created
        instances = registry_with_plugin.list_instances("test_plugin")
        assert instances == []

    def test_restore_skips_missing_base_plugin(self, registry_with_plugin):
        stored_configs = {"unknown_plugin:inst1": {"enabled": True}}
        registry_with_plugin._restore_instances(stored_configs)
        assert "unknown_plugin:inst1" not in registry_with_plugin._plugins

    def test_restore_migrates_mixed_case_key_to_lowercase(self, registry_with_plugin, mock_loader):
        """Pre-existing mixed-case instance keys are migrated to lowercase on
        restore so subsequent template renders resolve correctly (#774).

        The on-disk config is rewritten under the lowercase key and the old
        mixed-case entry is removed so we don't carry a stale duplicate.
        """
        stored_configs = {
            "test_plugin:FijiAustralia": {"enabled": True, "setting": "v"},
        }
        new_plugin = MagicMock(spec=PluginBase)
        new_plugin.validate_config.return_value = []
        new_plugin._validate_refresh_seconds.return_value = []
        new_plugin.enabled = False
        new_plugin.config = {}
        mock_loader.create_instance.return_value = new_plugin

        mock_config_manager = MagicMock()
        with patch("src.config_manager.get_config_manager", return_value=mock_config_manager):
            registry_with_plugin._restore_instances(stored_configs)

        # Instance is registered under the lowercase compound key
        assert "test_plugin:fijiaustralia" in registry_with_plugin._plugins
        assert "test_plugin:FijiAustralia" not in registry_with_plugin._plugins
        assert registry_with_plugin._enabled["test_plugin:fijiaustralia"] is True
        assert registry_with_plugin._configs["test_plugin:fijiaustralia"]["setting"] == "v"

        # On-disk config is migrated: new key written, old key deleted
        mock_config_manager.set_plugin_config.assert_called_with(
            "test_plugin:fijiaustralia", {"enabled": True, "setting": "v"}
        )
        mock_config_manager.delete_plugin_config.assert_called_with(
            "test_plugin:FijiAustralia"
        )

    def test_restore_lowercase_key_does_not_trigger_migration(self, registry_with_plugin, mock_loader):
        """Already-lowercase keys should not re-save or delete config."""
        stored_configs = {
            "test_plugin:wedding": {"enabled": True},
        }
        new_plugin = MagicMock(spec=PluginBase)
        new_plugin.validate_config.return_value = []
        new_plugin._validate_refresh_seconds.return_value = []
        new_plugin.enabled = False
        new_plugin.config = {}
        mock_loader.create_instance.return_value = new_plugin

        mock_config_manager = MagicMock()
        with patch("src.config_manager.get_config_manager", return_value=mock_config_manager):
            registry_with_plugin._restore_instances(stored_configs)

        mock_config_manager.set_plugin_config.assert_not_called()
        mock_config_manager.delete_plugin_config.assert_not_called()


# ── edge cases ──────────────────────────────────────────────────────────────


class TestInstanceEdgeCases:
    """Edge cases for instance management."""

    def test_instance_label_with_hyphens_and_underscores(self, registry_with_plugin):
        errors = registry_with_plugin.create_instance("test_plugin", "my-api_v2")
        assert errors == []
        assert "test_plugin:my-api_v2" in registry_with_plugin._plugins

    def test_instance_label_single_char(self, registry_with_plugin):
        errors = registry_with_plugin.create_instance("test_plugin", "x")
        assert errors == []

    def test_instance_label_max_length(self, registry_with_plugin):
        errors = registry_with_plugin.create_instance("test_plugin", "a" * 40)
        assert errors == []

    def test_instance_label_over_max_length(self, registry_with_plugin):
        errors = registry_with_plugin.create_instance("test_plugin", "a" * 41)
        assert len(errors) == 1


# ── API endpoint tests ───────────────────────────────────────────────────────


class TestPluginInstanceEndpoints:
    """Integration-style tests for the three instance REST endpoints via TestClient."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from src.api_server import app
        return TestClient(app)

    @pytest.fixture
    def mock_registry(self):
        registry = Mock()
        registry.parse_instance_key.side_effect = lambda k: (k.split(":", 1)[0], k.split(":", 1)[1] if ":" in k else None)
        registry.make_instance_key.side_effect = lambda base, label: f"{base}:{label}"
        registry.is_instance_key.side_effect = lambda k: ":" in k
        return registry

    # ── list instances ──────────────────────────────────────────────────────

    def test_list_instances_success(self, client, mock_registry):
        mock_registry.get_plugin.return_value = Mock()
        mock_registry.list_instances.return_value = [
            {"id": "weather:sf", "instance_label": "sf", "enabled": False},
        ]
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_plugin_registry", return_value=mock_registry):
            resp = client.get("/plugins/weather/instances")
        assert resp.status_code == 200
        data = resp.json()
        assert data["plugin_id"] == "weather"
        assert len(data["instances"]) == 1
        assert data["instances"][0]["instance_label"] == "sf"

    def test_list_instances_plugin_not_found(self, client, mock_registry):
        mock_registry.get_plugin.return_value = None
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_plugin_registry", return_value=mock_registry):
            resp = client.get("/plugins/nonexistent/instances")
        assert resp.status_code == 404

    def test_list_instances_system_unavailable(self, client):
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", False):
            resp = client.get("/plugins/weather/instances")
        assert resp.status_code == 503

    # ── create instance ─────────────────────────────────────────────────────

    def test_create_instance_success(self, client, mock_registry):
        mock_registry.get_plugin.return_value = Mock()
        mock_registry.create_instance.return_value = []  # no errors
        mock_cm = Mock()
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_plugin_registry", return_value=mock_registry), \
             patch("src.api_server.get_config_manager", return_value=mock_cm), \
             patch("src.api_server.reset_display_service"), \
             patch("src.api_server.reset_template_engine"):
            resp = client.post("/plugins/weather/instances", json={"label": "sf"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["instance_label"] == "sf"
        assert data["instance_key"] == "weather:sf"
        # Persists config
        mock_cm.set_plugin_config.assert_called_once_with("weather:sf", {"enabled": False})

    def test_create_instance_resets_services(self, client, mock_registry):
        """Creating an instance should reset display and template services."""
        mock_registry.get_plugin.return_value = Mock()
        mock_registry.create_instance.return_value = []
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_plugin_registry", return_value=mock_registry), \
             patch("src.api_server.get_config_manager", return_value=Mock()), \
             patch("src.api_server.reset_display_service") as mock_rds, \
             patch("src.api_server.reset_template_engine") as mock_rte:
            client.post("/plugins/weather/instances", json={"label": "nyc"})
        mock_rds.assert_called_once()
        mock_rte.assert_called_once()

    def test_create_instance_validation_error(self, client, mock_registry):
        mock_registry.get_plugin.return_value = Mock()
        mock_registry.create_instance.return_value = ["Label already exists"]
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_plugin_registry", return_value=mock_registry):
            resp = client.post("/plugins/weather/instances", json={"label": "sf"})
        assert resp.status_code == 400
        assert "Label already exists" in resp.json()["detail"]

    def test_create_instance_plugin_not_found(self, client, mock_registry):
        mock_registry.get_plugin.return_value = None
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_plugin_registry", return_value=mock_registry):
            resp = client.post("/plugins/nonexistent/instances", json={"label": "sf"})
        assert resp.status_code == 404

    def test_create_instance_system_unavailable(self, client):
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", False):
            resp = client.post("/plugins/weather/instances", json={"label": "sf"})
        assert resp.status_code == 503

    # ── delete instance ─────────────────────────────────────────────────────

    def test_delete_instance_success(self, client, mock_registry):
        mock_registry.delete_instance.return_value = []  # no errors
        mock_cm = Mock()
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_plugin_registry", return_value=mock_registry), \
             patch("src.api_server.get_config_manager", return_value=mock_cm), \
             patch("src.api_server.reset_display_service"), \
             patch("src.api_server.reset_template_engine"):
            resp = client.delete("/plugins/weather/instances/sf")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["instance_key"] == "weather:sf"
        # Uses public delete_plugin_config() (not private internals)
        mock_cm.delete_plugin_config.assert_called_once_with("weather:sf")

    def test_delete_instance_resets_services(self, client, mock_registry):
        """Deleting an instance should reset display and template services."""
        mock_registry.delete_instance.return_value = []
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_plugin_registry", return_value=mock_registry), \
             patch("src.api_server.get_config_manager", return_value=Mock()), \
             patch("src.api_server.reset_display_service") as mock_rds, \
             patch("src.api_server.reset_template_engine") as mock_rte:
            client.delete("/plugins/weather/instances/sf")
        mock_rds.assert_called_once()
        mock_rte.assert_called_once()

    def test_delete_instance_not_found(self, client, mock_registry):
        mock_registry.delete_instance.return_value = ["Instance not found"]
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True), \
             patch("src.api_server.get_plugin_registry", return_value=mock_registry):
            resp = client.delete("/plugins/weather/instances/nonexistent")
        assert resp.status_code == 400

    def test_delete_instance_system_unavailable(self, client):
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", False):
            resp = client.delete("/plugins/weather/instances/sf")
        assert resp.status_code == 503
