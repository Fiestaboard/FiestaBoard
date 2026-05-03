"""Plugin discovery and loading.

The PluginLoader discovers plugins from the built-in ``plugins/`` directory
as well as external plugin directories (registry and custom git sources).
"""

import importlib.util
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type

from .base import PluginBase
from .manifest import PluginManifest, load_manifest
from .sources import (
    EXTERNAL_PLUGINS_DIR,
    PluginSource,
)

logger = logging.getLogger(__name__)

# Default plugins directory (relative to project root)
DEFAULT_PLUGINS_DIR = "plugins"

# ---------------------------------------------------------------------------
# FiestaBoard version compatibility helpers
# ---------------------------------------------------------------------------

_FIESTABOARD_VERSION: Optional[str] = None


def _get_fiestaboard_version() -> str:
    """Return the running FiestaBoard version from package.json."""
    global _FIESTABOARD_VERSION
    if _FIESTABOARD_VERSION is not None:
        return _FIESTABOARD_VERSION

    project_root = Path(__file__).parent.parent.parent
    pkg_path = project_root / "package.json"
    try:
        with open(pkg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        _FIESTABOARD_VERSION = data.get("version", "0.0.0")
    except Exception:
        _FIESTABOARD_VERSION = "0.0.0"

    return _FIESTABOARD_VERSION


def _parse_version(version_str: str) -> Tuple[int, int, int]:
    """Parse a semver string into a (major, minor, patch) tuple."""
    match = re.match(r"(\d+)\.(\d+)\.(\d+)", version_str)
    if not match:
        return (0, 0, 0)
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _check_version_constraint(constraint: str, running_version: str) -> Tuple[bool, str]:
    """Check whether *running_version* satisfies *constraint*.

    Supports simple single-operator constraints: ``>=``, ``>``, ``<=``, ``<``,
    ``==``, ``!=``.  Returns ``(satisfied, reason)``.
    """
    if not constraint:
        return True, ""

    match = re.match(r"^(>=|>|<=|<|==|!=)\s*(\d+\.\d+\.\d+)$", constraint.strip())
    if not match:
        return True, f"Unrecognised version constraint '{constraint}', skipping check"

    op, required_str = match.group(1), match.group(2)
    required = _parse_version(required_str)
    running = _parse_version(running_version)

    satisfied = {
        ">=": running >= required,
        ">":  running > required,
        "<=": running <= required,
        "<":  running < required,
        "==": running == required,
        "!=": running != required,
    }[op]

    if not satisfied:
        return False, (
            f"Plugin requires FiestaBoard {constraint}, "
            f"but running version is {running_version}"
        )
    return True, ""


class PluginLoadError(Exception):
    """Raised when a plugin fails to load."""
    pass


class PluginLoader:
    """Discovers and loads plugins from multiple directories.

    The loader supports three plugin sources:

    1. **Built-in** – plugins shipped in the repository's ``plugins/``
       directory.
    2. **Registry / Git** – external plugins cloned into the
       ``external_plugins/`` directory (managed by :mod:`sources`).

    Both directories are scanned during discovery.  The built-in directory
    always takes precedence when a plugin id exists in both locations.
    """

    def __init__(
        self,
        plugins_dir: Optional[Path] = None,
        external_dirs: Optional[List[Path]] = None,
    ):
        """Initialize the plugin loader.

        Args:
            plugins_dir: Path to the built-in plugins directory.  When
                *None* the default ``plugins/`` relative to the project
                root is used.
            external_dirs: Additional directories to scan for plugins
                (e.g. ``external_plugins/``).  When *None* the default
                external directory is included automatically.
        """
        if plugins_dir is None:
            project_root = Path(__file__).parent.parent.parent
            plugins_dir = project_root / DEFAULT_PLUGINS_DIR

        self.plugins_dir = Path(plugins_dir)

        if external_dirs is None:
            project_root = Path(__file__).parent.parent.parent
            ext_dir = project_root / EXTERNAL_PLUGINS_DIR
            self._external_dirs: List[Path] = [ext_dir] if ext_dir.is_dir() else []
        else:
            self._external_dirs = list(external_dirs)

        self._loaded_plugins: Dict[str, Tuple[PluginBase, PluginManifest]] = {}
        self._plugin_classes: Dict[str, Type[PluginBase]] = {}
        self._load_errors: Dict[str, List[str]] = {}
        self._plugin_sources: Dict[str, PluginSource] = {}

        logger.info(
            "PluginLoader initialized – built-in: %s, external dirs: %s",
            self.plugins_dir,
            [str(d) for d in self._external_dirs],
        )
    
    @property
    def loaded_plugins(self) -> Dict[str, Tuple[PluginBase, PluginManifest]]:
        """Return all successfully loaded plugins."""
        return self._loaded_plugins.copy()

    @property
    def load_errors(self) -> Dict[str, List[str]]:
        """Return load errors by plugin directory name."""
        return self._load_errors.copy()

    @property
    def plugin_sources(self) -> Dict[str, PluginSource]:
        """Return source information for every loaded plugin."""
        return self._plugin_sources.copy()

    # ── discovery ────────────────────────────────────────────────────────

    def _discover_from_dir(self, directory: Path) -> List[str]:
        """Discover valid plugin directories inside *directory*."""
        if not directory.exists() or not directory.is_dir():
            return []

        found: List[str] = []
        for item in directory.iterdir():
            if item.name.startswith(".") or item.name.startswith("_"):
                continue
            if item.is_dir() and (item / "manifest.json").exists():
                found.append(item.name)
                logger.debug("Discovered plugin directory: %s", item.name)
        return found

    def discover_plugins(self) -> List[str]:
        """Discover available plugin directories.

        Scans the built-in ``plugins/`` directory first, then any
        external directories.  Built-in plugins take precedence –
        if the same directory name appears in both locations only the
        built-in copy is returned.

        Returns:
            Sorted list of unique plugin directory names.
        """
        seen: Dict[str, Path] = {}

        # Built-in directory first (takes precedence)
        for name in self._discover_from_dir(self.plugins_dir):
            seen[name] = self.plugins_dir / name

        # External directories
        for ext_dir in self._external_dirs:
            for name in self._discover_from_dir(ext_dir):
                if name not in seen:
                    seen[name] = ext_dir / name

        return sorted(seen.keys())
    
    # ── resolution ──────────────────────────────────────────────────────

    def _resolve_plugin_dir(self, plugin_name: str) -> Optional[Path]:
        """Find the on-disk directory for *plugin_name*.

        Checks built-in first, then external directories.
        """
        # Built-in takes precedence
        candidate = self.plugins_dir / plugin_name
        if candidate.is_dir():
            return candidate

        for ext_dir in self._external_dirs:
            candidate = ext_dir / plugin_name
            if candidate.is_dir():
                return candidate

        return None

    def _source_for_dir(self, plugin_dir: Path) -> PluginSource:
        """Determine the :class:`PluginSource` for a plugin directory."""
        for ext_dir in self._external_dirs:
            try:
                plugin_dir.relative_to(ext_dir)
                return PluginSource(
                    source_type="external",
                    local_path=str(plugin_dir),
                )
            except ValueError:
                continue
        return PluginSource(source_type="builtin", local_path=str(plugin_dir))

    # ── loading ──────────────────────────────────────────────────────────

    def load_plugin(self, plugin_name: str) -> Optional[PluginBase]:
        """Load a single plugin by directory name.
        
        Args:
            plugin_name: Name of the plugin directory
            
        Returns:
            Loaded plugin instance, or None if loading failed
        """
        plugin_dir = self._resolve_plugin_dir(plugin_name)
        errors: List[str] = []
        
        # Clear previous errors
        self._load_errors.pop(plugin_name, None)
        
        # Check directory exists
        if plugin_dir is None or not plugin_dir.exists():
            errors.append(f"Plugin directory not found: {plugin_name}")
            self._load_errors[plugin_name] = errors
            return None
        
        # Load and validate manifest
        manifest_path = plugin_dir / "manifest.json"
        manifest, manifest_errors = load_manifest(manifest_path)
        
        if manifest_errors:
            errors.extend(manifest_errors)
            self._load_errors[plugin_name] = errors
            logger.error(f"Failed to load manifest for {plugin_name}: {manifest_errors}")
            return None
        
        assert manifest is not None
        
        # Verify manifest id matches directory name
        if manifest.id != plugin_name:
            errors.append(f"Manifest id '{manifest.id}' does not match directory name '{plugin_name}'")
            self._load_errors[plugin_name] = errors
            return None

        # Check FiestaBoard version compatibility (soft failure -- warn but still load)
        if manifest.fiestaboard_version:
            running = _get_fiestaboard_version()
            ok, reason = _check_version_constraint(manifest.fiestaboard_version, running)
            if not ok:
                logger.warning(
                    "Plugin '%s' version incompatibility: %s", plugin_name, reason
                )
                self._load_errors.setdefault(plugin_name, []).append(
                    f"Version incompatibility: {reason}"
                )

        # Load Python module
        # Support two repo layouts:
        #   1. Root layout:    <plugin_dir>/__init__.py                     (older repos)
        #   2. Package layout: <plugin_dir>/plugins/<id>/__init__.py        (newer repos)
        init_path = plugin_dir / "__init__.py"
        if not init_path.exists():
            subdir_path = plugin_dir / "plugins" / plugin_name / "__init__.py"
            if subdir_path.exists():
                init_path = subdir_path
                logger.debug("Using package layout for plugin %s: %s", plugin_name, init_path)
            else:
                errors.append(f"Plugin __init__.py not found: {init_path}")
                self._load_errors[plugin_name] = errors
                return None
        
        try:
            # Import the plugin module dynamically
            module_name = f"plugins.{plugin_name}"
            spec = importlib.util.spec_from_file_location(module_name, init_path)
            
            if spec is None or spec.loader is None:
                errors.append(f"Failed to create module spec for {plugin_name}")
                self._load_errors[plugin_name] = errors
                return None
            
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            
        except Exception as e:
            errors.append(f"Failed to import plugin module: {e}")
            self._load_errors[plugin_name] = errors
            logger.exception(f"Error importing plugin {plugin_name}")
            return None
        
        # Find PluginBase subclass
        plugin_class = self._find_plugin_class(module, manifest.id)
        if plugin_class is None:
            errors.append(f"No PluginBase subclass found in {plugin_name}")
            self._load_errors[plugin_name] = errors
            return None
        
        # Instantiate plugin
        try:
            plugin_instance = plugin_class(manifest.raw)
            
            # Verify plugin_id property
            if plugin_instance.plugin_id != manifest.id:
                errors.append(
                    f"Plugin class plugin_id '{plugin_instance.plugin_id}' "
                    f"does not match manifest id '{manifest.id}'"
                )
                self._load_errors[plugin_name] = errors
                return None
            
            # Store loaded plugin and class
            self._loaded_plugins[manifest.id] = (plugin_instance, manifest)
            self._plugin_classes[manifest.id] = plugin_class
            self._plugin_sources[manifest.id] = self._source_for_dir(plugin_dir)
            logger.info(f"Successfully loaded plugin: {manifest.id} v{manifest.version}")
            
            return plugin_instance
            
        except Exception as e:
            errors.append(f"Failed to instantiate plugin: {e}")
            self._load_errors[plugin_name] = errors
            logger.exception(f"Error instantiating plugin {plugin_name}")
            return None
    
    def _find_plugin_class(self, module: Any, expected_id: str) -> Optional[Type[PluginBase]]:
        """Find the PluginBase subclass in a module.
        
        Args:
            module: Loaded Python module
            expected_id: Expected plugin_id for validation
            
        Returns:
            PluginBase subclass, or None if not found
        """
        # Look for exported Plugin class
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            
            # Skip non-classes
            if not isinstance(attr, type):
                continue
            
            # Skip PluginBase itself
            if attr is PluginBase:
                continue
            
            # Check if it's a PluginBase subclass
            if issubclass(attr, PluginBase):
                logger.debug(f"Found plugin class: {attr_name}")
                return attr
        
        return None
    
    def load_all_plugins(self) -> Dict[str, PluginBase]:
        """Discover and load all available plugins.
        
        Returns:
            Dictionary mapping plugin IDs to loaded instances
        """
        plugin_dirs = self.discover_plugins()
        loaded = {}
        
        for plugin_name in plugin_dirs:
            plugin = self.load_plugin(plugin_name)
            if plugin:
                loaded[plugin.plugin_id] = plugin
        
        logger.info(f"Loaded {len(loaded)}/{len(plugin_dirs)} plugins")
        
        if self._load_errors:
            for name, errors in self._load_errors.items():
                logger.warning(f"Plugin {name} had errors: {errors}")
        
        return loaded
    
    def reload_plugin(self, plugin_id: str) -> Optional[PluginBase]:
        """Reload a plugin (unload and load again).
        
        Args:
            plugin_id: ID of plugin to reload
            
        Returns:
            Reloaded plugin instance, or None if failed
        """
        # Unload if loaded
        if plugin_id in self._loaded_plugins:
            old_plugin, _ = self._loaded_plugins[plugin_id]
            old_plugin.cleanup()
            del self._loaded_plugins[plugin_id]
            
            # Remove from sys.modules to force reimport
            module_name = f"plugins.{plugin_id}"
            if module_name in sys.modules:
                del sys.modules[module_name]
        
        # Load again
        return self.load_plugin(plugin_id)
    
    def unload_plugin(self, plugin_id: str) -> bool:
        """Unload a plugin.
        
        Args:
            plugin_id: ID of plugin to unload
            
        Returns:
            True if unloaded, False if not loaded
        """
        if plugin_id not in self._loaded_plugins:
            return False
        
        plugin, _ = self._loaded_plugins[plugin_id]
        plugin.cleanup()
        del self._loaded_plugins[plugin_id]
        
        # Remove from sys.modules
        module_name = f"plugins.{plugin_id}"
        if module_name in sys.modules:
            del sys.modules[module_name]
        
        logger.info(f"Unloaded plugin: {plugin_id}")
        return True
    
    def get_manifest(self, plugin_id: str) -> Optional[PluginManifest]:
        """Get the manifest for a loaded plugin.
        
        Args:
            plugin_id: Plugin ID
            
        Returns:
            PluginManifest or None if not loaded
        """
        if plugin_id in self._loaded_plugins:
            _, manifest = self._loaded_plugins[plugin_id]
            return manifest
        return None

    def get_source(self, plugin_id: str) -> Optional[PluginSource]:
        """Get the source information for a loaded plugin.

        Args:
            plugin_id: Plugin ID

        Returns:
            :class:`PluginSource` or *None* if not loaded.
        """
        return self._plugin_sources.get(plugin_id)

    def get_plugin_class(self, plugin_id: str) -> Optional[Type[PluginBase]]:
        """Get the plugin class for a loaded plugin.

        This is used to create additional instances of the same plugin type.

        Args:
            plugin_id: Plugin ID

        Returns:
            The PluginBase subclass or None if not loaded.
        """
        return self._plugin_classes.get(plugin_id)

    def create_instance(self, plugin_id: str) -> Optional[PluginBase]:
        """Create a new instance of a loaded plugin.

        Returns a fresh PluginBase instance using the stored class and
        manifest for *plugin_id*.  The caller is responsible for
        configuring and enabling the returned instance.

        Args:
            plugin_id: Base plugin ID (must already be loaded).

        Returns:
            A new PluginBase instance, or None if the plugin is not loaded.
        """
        plugin_class = self._plugin_classes.get(plugin_id)
        if plugin_class is None:
            logger.warning("Cannot create instance: plugin class not found for %s", plugin_id)
            return None

        if plugin_id not in self._loaded_plugins:
            logger.warning("Cannot create instance: plugin not loaded: %s", plugin_id)
            return None

        _, manifest = self._loaded_plugins[plugin_id]

        try:
            return plugin_class(manifest.raw)
        except Exception as e:
            logger.exception("Failed to create instance of %s: %s", plugin_id, e)
            return None

