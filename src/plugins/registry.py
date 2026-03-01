"""Plugin registry - singleton for managing all loaded plugins.

The PluginRegistry is the central point for:
- Loading and unloading plugins
- Getting plugin instances by ID
- Managing plugin configurations
- Providing plugin data to other services
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import PluginBase, PluginResult
from .loader import PluginLoader
from .manifest import PluginManifest

logger = logging.getLogger(__name__)

# Singleton instance
_registry: Optional["PluginRegistry"] = None


class PluginRegistry:
    """Central registry for all loaded plugins.
    
    The registry manages:
    - Plugin loading via PluginLoader
    - Plugin enable/disable state
    - Plugin configuration
    - Aggregated variable schemas for templates
    """
    
    def __init__(self, plugins_dir: Optional[Path] = None):
        """Initialize the registry.
        
        Args:
            plugins_dir: Path to plugins directory
        """
        self._loader = PluginLoader(plugins_dir)
        self._plugins: Dict[str, PluginBase] = {}
        self._manifests: Dict[str, PluginManifest] = {}
        self._configs: Dict[str, Dict[str, Any]] = {}
        self._enabled: Dict[str, bool] = {}
        
        logger.info("PluginRegistry initialized")
    
    @property
    def plugins(self) -> Dict[str, PluginBase]:
        """Return all loaded plugins."""
        return self._plugins.copy()
    
    @property
    def enabled_plugins(self) -> Dict[str, PluginBase]:
        """Return only enabled plugins."""
        return {
            pid: plugin 
            for pid, plugin in self._plugins.items() 
            if self._enabled.get(pid, False)
        }
    
    def initialize(self) -> None:
        """Load all discovered plugins.
        
        This should be called once at startup. It will:
        1. Load all plugin modules from the plugins directory
        2. Read stored configurations from config manager
        3. Enable plugins that have enabled=true in their config
        """
        loaded = self._loader.load_all_plugins()
        
        # Try to get stored configs from config manager
        stored_configs: Dict[str, Dict[str, Any]] = {}
        try:
            from ..config_manager import get_config_manager
            config_manager = get_config_manager()
            # Get all plugin configs
            stored_configs = config_manager.get_all_plugin_configs()
        except Exception as e:
            logger.warning(f"Could not load stored plugin configs: {e}")
        
        for plugin_id, plugin in loaded.items():
            manifest = self._loader.get_manifest(plugin_id)
            if manifest:
                self._plugins[plugin_id] = plugin
                self._manifests[plugin_id] = manifest
                
                # Check if plugin has stored config with enabled=true
                plugin_config = stored_configs.get(plugin_id, {})
                is_enabled = plugin_config.get("enabled", False)
                
                self._enabled[plugin_id] = is_enabled
                
                # Apply stored config to the plugin
                if plugin_config:
                    self._configs[plugin_id] = plugin_config
                    plugin.config = plugin_config
                    plugin.enabled = is_enabled
                    
                if is_enabled:
                    logger.info(f"Loaded and enabled plugin: {plugin_id}")
                else:
                    logger.debug(f"Loaded plugin (disabled): {plugin_id}")
        
        enabled_count = sum(1 for e in self._enabled.values() if e)
        logger.info(f"Initialized {len(self._plugins)} plugins ({enabled_count} enabled)")
    
    def get_plugin(self, plugin_id: str) -> Optional[PluginBase]:
        """Get a plugin by ID.
        
        Args:
            plugin_id: Plugin identifier
            
        Returns:
            Plugin instance or None if not loaded
        """
        return self._plugins.get(plugin_id)
    
    def get_manifest(self, plugin_id: str) -> Optional[PluginManifest]:
        """Get a plugin's manifest.
        
        Args:
            plugin_id: Plugin identifier
            
        Returns:
            PluginManifest or None if not loaded
        """
        return self._manifests.get(plugin_id)
    
    def is_enabled(self, plugin_id: str) -> bool:
        """Check if a plugin is enabled.
        
        Args:
            plugin_id: Plugin identifier
            
        Returns:
            True if enabled, False otherwise
        """
        return self._enabled.get(plugin_id, False)
    
    def enable_plugin(self, plugin_id: str) -> bool:
        """Enable a plugin.
        
        Args:
            plugin_id: Plugin identifier
            
        Returns:
            True if enabled successfully, False if plugin not found
        """
        if plugin_id not in self._plugins:
            logger.warning(f"Cannot enable unknown plugin: {plugin_id}")
            return False
        
        plugin = self._plugins[plugin_id]
        plugin.enabled = True
        self._enabled[plugin_id] = True
        
        # Apply stored config
        if plugin_id in self._configs:
            plugin.config = self._configs[plugin_id]
        
        logger.info(f"Enabled plugin: {plugin_id}")
        return True
    
    def disable_plugin(self, plugin_id: str) -> bool:
        """Disable a plugin.
        
        Args:
            plugin_id: Plugin identifier
            
        Returns:
            True if disabled successfully, False if plugin not found
        """
        if plugin_id not in self._plugins:
            return False
        
        plugin = self._plugins[plugin_id]
        plugin.enabled = False
        self._enabled[plugin_id] = False
        
        logger.info(f"Disabled plugin: {plugin_id}")
        return True
    
    def set_plugin_config(self, plugin_id: str, config: Dict[str, Any]) -> List[str]:
        """Set configuration for a plugin.
        
        Args:
            plugin_id: Plugin identifier
            config: Configuration dictionary
            
        Returns:
            List of validation errors (empty if valid)
        """
        if plugin_id not in self._plugins:
            return [f"Plugin not found: {plugin_id}"]
        
        plugin = self._plugins[plugin_id]
        
        # Validate config (base refresh_seconds + plugin-specific)
        errors = plugin._validate_refresh_seconds(config)
        errors.extend(plugin.validate_config(config))
        if errors:
            return errors
        
        # Store and apply config
        self._configs[plugin_id] = config
        plugin.config = config
        
        logger.debug(f"Updated config for {plugin_id}")
        return []
    
    def get_plugin_config(self, plugin_id: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a plugin.
        
        Args:
            plugin_id: Plugin identifier
            
        Returns:
            Configuration dictionary or None if not found
        """
        return self._configs.get(plugin_id)
    
    def fetch_plugin_data(self, plugin_id: str) -> PluginResult:
        """Fetch data from a plugin.
        
        Args:
            plugin_id: Plugin identifier
            
        Returns:
            PluginResult with data or error
        """
        if plugin_id not in self._plugins:
            return PluginResult(
                available=False,
                error=f"Plugin not found: {plugin_id}"
            )
        
        if not self._enabled.get(plugin_id, False):
            return PluginResult(
                available=False,
                error=f"Plugin not enabled: {plugin_id}"
            )
        
        plugin = self._plugins[plugin_id]
        
        try:
            return plugin.get_data()
        except Exception as e:
            logger.exception(f"Error fetching data from {plugin_id}")
            return PluginResult(
                available=False,
                error=str(e)
            )
    
    def get_all_variables(self) -> Dict[str, List[str]]:
        """Get all template variables from enabled plugins.
        
        Returns:
            Dictionary mapping plugin_id to list of variable names
        """
        variables: Dict[str, List[str]] = {}
        
        for plugin_id, plugin in self._plugins.items():
            if not self._enabled.get(plugin_id, False):
                continue
            
            manifest = self._manifests.get(plugin_id)
            if not manifest:
                continue
            
            # Get variable names from manifest
            var_names = manifest.variables.get_all_variable_names(plugin_id)
            if var_names:
                variables[plugin_id] = var_names
        
        return variables
    
    def get_all_max_lengths(self) -> Dict[str, int]:
        """Get all max lengths from enabled plugins.
        
        Returns:
            Dictionary mapping "plugin_id.variable" to max length
        """
        max_lengths: Dict[str, int] = {}
        
        for plugin_id in self._plugins:
            if not self._enabled.get(plugin_id, False):
                continue
            
            manifest = self._manifests.get(plugin_id)
            if not manifest:
                continue
            
            # Prefix variable names with plugin_id
            for var_name, max_len in manifest.max_lengths.items():
                full_name = f"{plugin_id}.{var_name}"
                max_lengths[full_name] = max_len
        
        return max_lengths
    
    def get_variables_schema(self, plugin_id: str) -> Optional[Dict[str, Any]]:
        """Get the variables schema for a plugin.
        
        Args:
            plugin_id: Plugin identifier
            
        Returns:
            Variables schema dictionary or None
        """
        manifest = self._manifests.get(plugin_id)
        if manifest:
            return manifest.raw.get("variables", {})
        return None
    
    def list_plugins(self) -> List[Dict[str, Any]]:
        """List all plugins with their status.
        
        Returns:
            List of plugin info dictionaries
        """
        plugins = []
        
        for plugin_id, plugin in self._plugins.items():
            manifest = self._manifests.get(plugin_id)
            info = {
                "id": plugin_id,
                "name": manifest.name if manifest else plugin_id,
                "version": manifest.version if manifest else "unknown",
                "description": manifest.description if manifest else "",
                "author": manifest.author if manifest else "Unknown",
                "enabled": self._enabled.get(plugin_id, False),
                "icon": manifest.icon if manifest else "puzzle",
                "category": manifest.category if manifest else "utility",
            }
            plugins.append(info)
        
        # Sort by name
        plugins.sort(key=lambda p: p["name"].lower())
        
        return plugins
    
    def reload_plugin(self, plugin_id: str) -> Optional[PluginBase]:
        """Reload a plugin.
        
        Args:
            plugin_id: Plugin identifier
            
        Returns:
            Reloaded plugin instance or None if failed
        """
        # Remember enabled state and config
        was_enabled = self._enabled.get(plugin_id, False)
        config = self._configs.get(plugin_id, {})
        
        # Unload
        if plugin_id in self._plugins:
            self._plugins[plugin_id].cleanup()
            del self._plugins[plugin_id]
        if plugin_id in self._manifests:
            del self._manifests[plugin_id]
        
        # Reload
        plugin = self._loader.reload_plugin(plugin_id)
        if plugin:
            manifest = self._loader.get_manifest(plugin_id)
            if manifest:
                self._plugins[plugin_id] = plugin
                self._manifests[plugin_id] = manifest
                
                # Restore state
                if was_enabled:
                    self.enable_plugin(plugin_id)
                if config:
                    self.set_plugin_config(plugin_id, config)
                
                return plugin
        
        return None
    
    def get_load_errors(self) -> Dict[str, List[str]]:
        """Get plugin load errors.
        
        Returns:
            Dictionary mapping plugin directory names to error lists
        """
        return self._loader.load_errors
    
    def build_template_context(self) -> Dict[str, Any]:
        """Build context dictionary for template rendering.
        
        Fetches data from all enabled plugins.
        
        Returns:
            Dictionary mapping plugin_id to plugin data
        """
        context: Dict[str, Any] = {}
        
        for plugin_id in self.enabled_plugins:
            result = self.fetch_plugin_data(plugin_id)
            if result.available and result.data:
                context[plugin_id] = result.data
        
        return context


def get_plugin_registry() -> PluginRegistry:
    """Get or create the global plugin registry singleton.
    
    Returns:
        The global PluginRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
        _registry.initialize()  # Load all plugins on first access
    return _registry


def reset_plugin_registry() -> None:
    """Reset the global plugin registry.
    
    Use this when you need to reinitialize the registry,
    e.g., in tests or after configuration changes.
    """
    global _registry
    _registry = None
    logger.info("Plugin registry reset")

