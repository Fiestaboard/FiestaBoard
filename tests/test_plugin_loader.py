"""Tests for PluginLoader - discovers and loads plugin modules."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


from src.plugins.loader import PluginLoader


def _loader_for_tests(plugins_dir: Path) -> PluginLoader:
    """PluginLoader scoped to *plugins_dir* only (no merge with repo ``external_plugins/``)."""
    return PluginLoader(plugins_dir=plugins_dir, external_dirs=[])


# --- Minimal valid plugin for testing ---

VALID_MANIFEST = {
    "id": "test_plugin",
    "name": "Test Plugin",
    "version": "1.0.0",
    "description": "Test",
    "author": "Test",
    "variables": {"simple": ["var1"]},
    "max_lengths": {},
}


def create_valid_plugin_dir(tmp_path: Path, plugin_id: str = "test_plugin") -> Path:
    """Create a minimal valid plugin directory structure."""
    plugin_dir = tmp_path / plugin_id
    plugin_dir.mkdir()

    manifest = {**VALID_MANIFEST, "id": plugin_id}
    (plugin_dir / "manifest.json").write_text(
        '{"id":"' + plugin_id + '","name":"Test","version":"1.0.0","description":"","author":"","variables":{"simple":["var1"]},"max_lengths":{}}'
    )

    plugin_code = f'''
"""Test plugin for {plugin_id}."""
from src.plugins.base import PluginBase, PluginResult

class TestPlugin(PluginBase):
    @property
    def plugin_id(self) -> str:
        return "{plugin_id}"

    def fetch_data(self) -> PluginResult:
        return PluginResult(available=True, data={{"value": "test"}})
'''
    (plugin_dir / "__init__.py").write_text(plugin_code)
    return plugin_dir


# --- __init__ ---


def test_init_uses_default_plugins_dir_when_none():
    """__init__ uses default plugins dir when None."""
    with patch.object(Path, "parent") as mock_parent:
        mock_parent.parent.parent = Path("/project")
        loader = PluginLoader(plugins_dir=None)
        # When None, it resolves from __file__ - we can't easily test that
        # So just verify it doesn't crash and uses a Path
        assert loader.plugins_dir is not None
        assert isinstance(loader.plugins_dir, Path)


def test_init_uses_provided_plugins_dir():
    """__init__ uses provided plugins dir."""
    plugins_dir = Path("/custom/plugins")
    loader = PluginLoader(plugins_dir=plugins_dir)
    assert loader.plugins_dir == plugins_dir


# --- loaded_plugins and load_errors properties ---


def test_loaded_plugins_returns_copy():
    """loaded_plugins returns copy of loaded plugins."""
    loader = PluginLoader(plugins_dir=Path("/fake"))
    loaded = loader.loaded_plugins
    assert loaded == {}
    assert loaded is not loader._loaded_plugins


def test_load_errors_returns_copy():
    """load_errors returns copy of load errors."""
    loader = PluginLoader(plugins_dir=Path("/fake"))
    loader._load_errors["bad"] = ["error1"]
    errors = loader.load_errors
    assert errors == {"bad": ["error1"]}
    errors["bad"] = ["modified"]
    assert loader.load_errors["bad"] == ["error1"]


# --- discover_plugins ---


def test_discover_plugins_returns_sorted_dirs_with_manifest(tmp_path):
    """discover_plugins returns sorted list of dirs with manifest.json."""
    (tmp_path / "plugin_a").mkdir()
    (tmp_path / "plugin_a" / "manifest.json").write_text("{}")
    (tmp_path / "plugin_b").mkdir()
    (tmp_path / "plugin_b" / "manifest.json").write_text("{}")
    (tmp_path / "plugin_c").mkdir()
    # plugin_c has no manifest

    loader = _loader_for_tests(tmp_path)
    plugins = loader.discover_plugins()
    assert plugins == ["plugin_a", "plugin_b"]


def test_discover_plugins_skips_hidden_dirs(tmp_path):
    """discover_plugins skips hidden and _ prefixed dirs."""
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "manifest.json").write_text("{}")
    (tmp_path / "_template").mkdir()
    (tmp_path / "_template" / "manifest.json").write_text("{}")
    (tmp_path / "valid").mkdir()
    (tmp_path / "valid" / "manifest.json").write_text("{}")

    loader = _loader_for_tests(tmp_path)
    plugins = loader.discover_plugins()
    assert plugins == ["valid"]


def test_discover_plugins_handles_missing_dir(tmp_path):
    """discover_plugins handles missing directory."""
    missing = tmp_path / "nonexistent"
    loader = _loader_for_tests(missing)
    plugins = loader.discover_plugins()
    assert plugins == []


def test_discover_plugins_handles_non_dir_path(tmp_path):
    """discover_plugins handles path that is not a directory."""
    file_path = tmp_path / "file.txt"
    file_path.write_text("not a dir")
    loader = _loader_for_tests(file_path)
    plugins = loader.discover_plugins()
    assert plugins == []


# --- load_plugin ---


def test_load_plugin_loads_valid_plugin_successfully(tmp_path):
    """load_plugin loads valid plugin successfully."""
    create_valid_plugin_dir(tmp_path, "test_plugin")
    loader = _loader_for_tests(tmp_path)

    plugin = loader.load_plugin("test_plugin")
    assert plugin is not None
    assert plugin.plugin_id == "test_plugin"
    assert "test_plugin" in loader.loaded_plugins


def test_load_plugin_handles_missing_directory(tmp_path):
    """load_plugin handles missing directory."""
    loader = _loader_for_tests(tmp_path)
    plugin = loader.load_plugin("nonexistent")
    assert plugin is None
    assert "nonexistent" in loader.load_errors
    assert any("not found" in e for e in loader.load_errors["nonexistent"])


def test_load_plugin_handles_manifest_errors(tmp_path):
    """load_plugin handles manifest errors."""
    plugin_dir = tmp_path / "bad_manifest"
    plugin_dir.mkdir()
    (plugin_dir / "manifest.json").write_text("{ invalid json")
    (plugin_dir / "__init__.py").write_text("")

    loader = _loader_for_tests(tmp_path)
    plugin = loader.load_plugin("bad_manifest")
    assert plugin is None
    assert "bad_manifest" in loader.load_errors


def test_load_plugin_handles_manifest_id_mismatch(tmp_path):
    """load_plugin handles manifest ID mismatch with directory name."""
    plugin_dir = tmp_path / "dir_name"
    plugin_dir.mkdir()
    (plugin_dir / "manifest.json").write_text(
        '{"id":"different_id","name":"Test","version":"1.0.0","description":"","author":"","variables":{"simple":[]},"max_lengths":{}}'
    )
    (plugin_dir / "__init__.py").write_text(
        """
from src.plugins.base import PluginBase, PluginResult
class P(PluginBase):
    @property
    def plugin_id(self): return "different_id"
    def fetch_data(self): return PluginResult(available=True, data={})
"""
    )

    loader = _loader_for_tests(tmp_path)
    plugin = loader.load_plugin("dir_name")
    assert plugin is None
    assert "dir_name" in loader.load_errors
    assert any("does not match" in e for e in loader.load_errors["dir_name"])


def test_load_plugin_handles_missing_init(tmp_path):
    """load_plugin handles missing __init__.py."""
    plugin_dir = tmp_path / "no_init"
    plugin_dir.mkdir()
    (plugin_dir / "manifest.json").write_text(
        '{"id":"no_init","name":"Test","version":"1.0.0","description":"","author":"","variables":{"simple":[]},"max_lengths":{}}'
    )
    # No __init__.py

    loader = _loader_for_tests(tmp_path)
    plugin = loader.load_plugin("no_init")
    assert plugin is None
    assert any("__init__.py" in e for e in loader.load_errors["no_init"])


def test_load_plugin_loads_package_layout(tmp_path):
    """load_plugin finds __init__.py in plugins/<id>/ subdirectory (newer repo layout)."""
    plugin_id = "pkg_layout"
    plugin_dir = tmp_path / plugin_id
    plugin_dir.mkdir()
    (plugin_dir / "manifest.json").write_text(
        '{"id":"pkg_layout","name":"Test","version":"1.0.0","description":"","author":"","variables":{"simple":["var1"]},"max_lengths":{}}'
    )
    # Create package layout: plugins/pkg_layout/__init__.py (no root __init__.py)
    sub_pkg = plugin_dir / "plugins" / plugin_id
    sub_pkg.mkdir(parents=True)
    (plugin_dir / "plugins" / "__init__.py").write_text("")
    plugin_code = f'''
"""Test plugin with package layout."""
from src.plugins.base import PluginBase, PluginResult

class PkgLayoutPlugin(PluginBase):
    @property
    def plugin_id(self) -> str:
        return "{plugin_id}"

    def fetch_data(self) -> PluginResult:
        return PluginResult(available=True, data={{"value": "test"}})
'''
    (sub_pkg / "__init__.py").write_text(plugin_code)

    loader = _loader_for_tests(tmp_path)
    plugin = loader.load_plugin(plugin_id)
    assert plugin is not None
    assert plugin.plugin_id == plugin_id
    assert plugin_id in loader.loaded_plugins


def test_load_plugin_handles_import_errors(tmp_path):
    """load_plugin handles import errors in __init__.py."""
    plugin_dir = tmp_path / "import_error"
    plugin_dir.mkdir()
    (plugin_dir / "manifest.json").write_text(
        '{"id":"import_error","name":"Test","version":"1.0.0","description":"","author":"","variables":{"simple":[]},"max_lengths":{}}'
    )
    (plugin_dir / "__init__.py").write_text("raise ImportError('syntax error')")

    loader = _loader_for_tests(tmp_path)
    plugin = loader.load_plugin("import_error")
    assert plugin is None
    assert "import_error" in loader.load_errors
    assert any("import" in e.lower() or "syntax" in e.lower() for e in loader.load_errors["import_error"])


def test_load_plugin_handles_no_plugin_base_subclass(tmp_path):
    """load_plugin handles module with no PluginBase subclass."""
    plugin_dir = tmp_path / "no_plugin_class"
    plugin_dir.mkdir()
    (plugin_dir / "manifest.json").write_text(
        '{"id":"no_plugin_class","name":"Test","version":"1.0.0","description":"","author":"","variables":{"simple":[]},"max_lengths":{}}'
    )
    (plugin_dir / "__init__.py").write_text("x = 42")

    loader = _loader_for_tests(tmp_path)
    plugin = loader.load_plugin("no_plugin_class")
    assert plugin is None
    assert any("PluginBase" in e for e in loader.load_errors["no_plugin_class"])


def test_load_plugin_handles_instantiation_errors(tmp_path):
    """load_plugin handles plugin instantiation errors."""
    plugin_dir = tmp_path / "init_error"
    plugin_dir.mkdir()
    (plugin_dir / "manifest.json").write_text(
        '{"id":"init_error","name":"Test","version":"1.0.0","description":"","author":"","variables":{"simple":[]},"max_lengths":{}}'
    )
    (plugin_dir / "__init__.py").write_text(
        """
from src.plugins.base import PluginBase, PluginResult
class P(PluginBase):
    @property
    def plugin_id(self): return "init_error"
    def fetch_data(self): return PluginResult(available=True, data={})
    def __init__(self, m):
        super().__init__(m)
        raise RuntimeError("init failed")
"""
    )

    loader = _loader_for_tests(tmp_path)
    plugin = loader.load_plugin("init_error")
    assert plugin is None
    assert any("instantiate" in e.lower() or "init failed" in e for e in loader.load_errors["init_error"])


def test_load_plugin_handles_plugin_id_mismatch(tmp_path):
    """load_plugin handles plugin_id mismatch with manifest."""
    plugin_dir = tmp_path / "id_mismatch"
    plugin_dir.mkdir()
    (plugin_dir / "manifest.json").write_text(
        '{"id":"id_mismatch","name":"Test","version":"1.0.0","description":"","author":"","variables":{"simple":[]},"max_lengths":{}}'
    )
    (plugin_dir / "__init__.py").write_text(
        """
from src.plugins.base import PluginBase, PluginResult
class P(PluginBase):
    @property
    def plugin_id(self): return "wrong_id"
    def fetch_data(self): return PluginResult(available=True, data={})
"""
    )

    loader = _loader_for_tests(tmp_path)
    plugin = loader.load_plugin("id_mismatch")
    assert plugin is None
    assert any("does not match" in e for e in loader.load_errors["id_mismatch"])


def test_load_plugin_clears_previous_errors(tmp_path):
    """load_plugin clears previous errors for plugin."""
    create_valid_plugin_dir(tmp_path, "test_plugin")
    loader = _loader_for_tests(tmp_path)
    loader._load_errors["test_plugin"] = ["old error"]

    plugin = loader.load_plugin("test_plugin")
    assert plugin is not None
    assert "test_plugin" not in loader.load_errors


# --- _find_plugin_class ---


def test_find_plugin_class_finds_class():
    """_find_plugin_class finds PluginBase subclass in module."""
    import types

    from src.plugins.base import PluginBase, PluginResult

    class FoundPlugin(PluginBase):
        @property
        def plugin_id(self):
            return "found"

        def fetch_data(self):
            return PluginResult(available=True, data={})

    module = types.ModuleType("test_module")
    module.FoundPlugin = FoundPlugin

    loader = PluginLoader(plugins_dir=Path("/fake"))
    found = loader._find_plugin_class(module, "found")
    assert found is FoundPlugin


def test_find_plugin_class_skips_plugin_base():
    """_find_plugin_class skips PluginBase itself."""
    from src.plugins.base import PluginBase

    module = MagicMock()
    module.PluginBase = PluginBase

    loader = PluginLoader(plugins_dir=Path("/fake"))
    found = loader._find_plugin_class(module, "x")
    assert found is None


def test_find_plugin_class_returns_none_when_not_found():
    """_find_plugin_class returns None when not found."""
    module = MagicMock()
    module.SomeClass = str  # Not a PluginBase subclass

    loader = PluginLoader(plugins_dir=Path("/fake"))
    found = loader._find_plugin_class(module, "x")
    assert found is None


# --- load_all_plugins ---


def test_load_all_plugins_discovers_and_loads_all(tmp_path):
    """load_all_plugins discovers and loads all plugins."""
    create_valid_plugin_dir(tmp_path, "plugin_a")
    create_valid_plugin_dir(tmp_path, "plugin_b")
    loader = _loader_for_tests(tmp_path)

    loaded = loader.load_all_plugins()
    assert len(loaded) == 2
    assert "plugin_a" in loaded
    assert "plugin_b" in loaded


def test_load_all_plugins_logs_errors(tmp_path):
    """load_all_plugins logs errors for failed plugins."""
    create_valid_plugin_dir(tmp_path, "good")
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "manifest.json").write_text("{ invalid")
    loader = _loader_for_tests(tmp_path)

    loaded = loader.load_all_plugins()
    assert "good" in loaded
    assert "bad" in loader.load_errors


# --- reload_plugin ---


def test_reload_plugin_unloads_and_loads_again(tmp_path):
    """reload_plugin unloads old, removes from sys.modules, loads again."""
    create_valid_plugin_dir(tmp_path, "test_plugin")
    loader = _loader_for_tests(tmp_path)
    loader.load_plugin("test_plugin")

    module_name = "plugins.test_plugin"
    # Plugin was loaded so it may be in sys.modules
    reloaded = loader.reload_plugin("test_plugin")
    assert reloaded is not None
    assert reloaded.plugin_id == "test_plugin"


def test_reload_plugin_loads_if_not_loaded(tmp_path):
    """reload_plugin loads plugin if not previously loaded."""
    create_valid_plugin_dir(tmp_path, "test_plugin")
    loader = _loader_for_tests(tmp_path)

    plugin = loader.reload_plugin("test_plugin")
    assert plugin is not None
    assert plugin.plugin_id == "test_plugin"


# --- unload_plugin ---


def test_unload_plugin_cleans_up_and_removes_from_sys_modules(tmp_path):
    """unload_plugin cleans up, removes from sys.modules."""
    create_valid_plugin_dir(tmp_path, "test_plugin")
    loader = _loader_for_tests(tmp_path)
    loader.load_plugin("test_plugin")

    result = loader.unload_plugin("test_plugin")
    assert result is True
    assert "test_plugin" not in loader.loaded_plugins
    assert "plugins.test_plugin" not in sys.modules


def test_unload_plugin_returns_false_if_not_loaded():
    """unload_plugin returns False if not loaded."""
    loader = PluginLoader(plugins_dir=Path("/fake"))
    result = loader.unload_plugin("nonexistent")
    assert result is False


# --- get_manifest ---


def test_get_manifest_returns_manifest_for_loaded(tmp_path):
    """get_manifest returns manifest for loaded plugin."""
    create_valid_plugin_dir(tmp_path, "test_plugin")
    loader = _loader_for_tests(tmp_path)
    loader.load_plugin("test_plugin")

    manifest = loader.get_manifest("test_plugin")
    assert manifest is not None
    assert manifest.id == "test_plugin"
    assert manifest.name == "Test"


def test_get_manifest_returns_none_for_not_loaded():
    """get_manifest returns None for not loaded plugin."""
    loader = PluginLoader(plugins_dir=Path("/fake"))
    assert loader.get_manifest("unknown") is None


# --- spec/loader edge case ---


def test_load_plugin_handles_none_spec(tmp_path):
    """load_plugin handles None module spec."""
    plugin_dir = tmp_path / "spec_error"
    plugin_dir.mkdir()
    (plugin_dir / "manifest.json").write_text(
        '{"id":"spec_error","name":"Test","version":"1.0.0","description":"","author":"","variables":{"simple":[]},"max_lengths":{}}'
    )
    (plugin_dir / "__init__.py").write_text("x = 1")

    with patch("importlib.util.spec_from_file_location", return_value=None):
        loader = _loader_for_tests(tmp_path)
        plugin = loader.load_plugin("spec_error")
    assert plugin is None
    assert any("spec" in e.lower() for e in loader.load_errors["spec_error"])


# --- get_source ---


def test_get_source_returns_source_for_loaded_plugin(tmp_path):
    """get_source returns a PluginSource for a loaded plugin."""
    create_valid_plugin_dir(tmp_path, "test_plugin")
    loader = _loader_for_tests(tmp_path)
    loader.load_plugin("test_plugin")

    source = loader.get_source("test_plugin")
    assert source is not None
    assert source.source_type == "builtin"
    assert "test_plugin" in source.local_path


def test_get_source_returns_none_for_unknown():
    """get_source returns None for unknown plugin."""
    loader = PluginLoader(plugins_dir=Path("/fake"))
    assert loader.get_source("nonexistent") is None


# --- plugin_sources property ---


def test_plugin_sources_returns_loaded_sources(tmp_path):
    """plugin_sources property returns sources for all loaded plugins."""
    create_valid_plugin_dir(tmp_path, "test_plugin")
    loader = _loader_for_tests(tmp_path)
    loader.load_plugin("test_plugin")

    sources = loader.plugin_sources
    assert "test_plugin" in sources
    assert sources["test_plugin"].source_type == "builtin"


# --- _get_fiestaboard_version ---


def test_get_fiestaboard_version():
    """_get_fiestaboard_version reads version from package.json."""
    import src.plugins.loader as loader_mod

    old = loader_mod._FIESTABOARD_VERSION
    try:
        loader_mod._FIESTABOARD_VERSION = None
        version = loader_mod._get_fiestaboard_version()
        assert version != ""
        assert "." in version
    finally:
        loader_mod._FIESTABOARD_VERSION = old


def test_get_fiestaboard_version_caches():
    """_get_fiestaboard_version caches the result."""
    import src.plugins.loader as loader_mod

    old = loader_mod._FIESTABOARD_VERSION
    try:
        loader_mod._FIESTABOARD_VERSION = "1.2.3"
        assert loader_mod._get_fiestaboard_version() == "1.2.3"
    finally:
        loader_mod._FIESTABOARD_VERSION = old


def test_get_fiestaboard_version_fallback_on_error():
    """_get_fiestaboard_version returns 0.0.0 when file can't be read."""
    import src.plugins.loader as loader_mod

    old = loader_mod._FIESTABOARD_VERSION
    try:
        loader_mod._FIESTABOARD_VERSION = None
        with patch("builtins.open", side_effect=OSError("not found")):
            version = loader_mod._get_fiestaboard_version()
        assert version == "0.0.0"
    finally:
        loader_mod._FIESTABOARD_VERSION = old
