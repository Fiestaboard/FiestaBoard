"""Base classes for FiestaBoard plugins.

All plugins must inherit from PluginBase and implement the required methods.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

DEFAULT_REFRESH_SECONDS = 300
MIN_REFRESH_SECONDS = 10
MAX_REFRESH_SECONDS = 86400


@dataclass
class PluginResult:
    """Result from a plugin data fetch operation.
    
    Attributes:
        available: Whether the plugin is available and configured
        data: The fetched data dictionary (raw data for template variables)
        error: Error message if fetch failed
        formatted_lines: Optional pre-formatted display lines (6 lines for board)
    """
    available: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    formatted_lines: Optional[List[str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "available": self.available,
            "data": self.data,
            "error": self.error,
            "formatted_lines": self.formatted_lines,
        }


@dataclass
class PluginInfo:
    """Plugin metadata from manifest.
    
    Attributes:
        id: Unique plugin identifier
        name: Human-readable name
        version: Semantic version string
        description: Short description
        author: Plugin author/maintainer
        repository: Source repository URL
        documentation: Path to README or docs
    """
    id: str
    name: str
    version: str
    description: str
    author: str = "Unknown"
    repository: str = ""
    documentation: str = "README.md"


class PluginBase(ABC):
    """Abstract base class for all FiestaBoard plugins.
    
    Plugins must implement:
    - plugin_id property: Returns unique identifier matching manifest
    - fetch_data(): Returns PluginResult with data
    
    Plugins may optionally implement:
    - validate_config(): Validate configuration before use
    - get_formatted_display(): Return pre-formatted 6-line display
    - on_config_change(): Called when configuration is updated
    - cleanup(): Called when plugin is disabled/unloaded
    """
    
    def __init__(self, manifest: Dict[str, Any]):
        """Initialize plugin with its manifest.
        
        Args:
            manifest: Parsed manifest.json dictionary
        """
        self._manifest = manifest
        self._config: Dict[str, Any] = {}
        self._enabled = False
        self._cached_result: Optional["PluginResult"] = None
        self._last_fetch_time: Optional[datetime] = None
        logger.debug(f"Plugin initialized: {self.plugin_id}")
    
    @property
    @abstractmethod
    def plugin_id(self) -> str:
        """Return unique plugin identifier.
        
        Must match the 'id' field in manifest.json.
        """
        pass
    
    @property
    def manifest(self) -> Dict[str, Any]:
        """Return the plugin's manifest."""
        return self._manifest
    
    @property
    def info(self) -> PluginInfo:
        """Return plugin metadata from manifest."""
        return PluginInfo(
            id=self._manifest.get("id", self.plugin_id),
            name=self._manifest.get("name", self.plugin_id),
            version=self._manifest.get("version", "0.0.0"),
            description=self._manifest.get("description", ""),
            author=self._manifest.get("author", "Unknown"),
            repository=self._manifest.get("repository", ""),
            documentation=self._manifest.get("documentation", "README.md"),
        )
    
    @property
    def config(self) -> Dict[str, Any]:
        """Return current plugin configuration."""
        return self._config
    
    @config.setter
    def config(self, value: Dict[str, Any]) -> None:
        """Set plugin configuration."""
        old_config = self._config
        self._config = value
        if old_config != value:
            self.clear_cache()
            self.on_config_change(old_config, value)
    
    @property
    def enabled(self) -> bool:
        """Return whether plugin is enabled."""
        return self._enabled
    
    @enabled.setter
    def enabled(self, value: bool) -> None:
        """Set plugin enabled state."""
        if self._enabled != value:
            self._enabled = value
            if value:
                logger.info(f"Plugin enabled: {self.plugin_id}")
            else:
                logger.info(f"Plugin disabled: {self.plugin_id}")
                self.clear_cache()
                self.cleanup()
    
    @abstractmethod
    def fetch_data(self) -> PluginResult:
        """Fetch and return plugin data.
        
        This is the main method that plugins must implement.
        It should fetch data from external sources and return
        a PluginResult with the raw data for template variables.
        
        Returns:
            PluginResult with available=True and data if successful,
            or available=False and error message if failed.
        """
        pass
    
    def _get_refresh_schema(self) -> Optional[Dict[str, Any]]:
        """Get refresh_seconds property schema from the manifest, if defined."""
        schema = self._manifest.get("settings_schema", {})
        properties = schema.get("properties", {})
        return properties.get("refresh_seconds")

    @property
    def refresh_seconds(self) -> Optional[int]:
        """Get the effective refresh interval in seconds.
        
        Returns the configured value, falling back to the manifest default.
        Returns None if the plugin's manifest does not define refresh_seconds.
        """
        refresh_schema = self._get_refresh_schema()
        if refresh_schema is None:
            return None
        default = refresh_schema.get("default", DEFAULT_REFRESH_SECONDS)
        return self._config.get("refresh_seconds", default)

    def get_data(self) -> PluginResult:
        """Get plugin data with automatic caching based on refresh_seconds.
        
        If the plugin's manifest defines refresh_seconds in settings_schema,
        results are cached and reused until the refresh interval expires.
        Plugins without refresh_seconds in their manifest always fetch fresh.
        
        Returns:
            PluginResult with data or error
        """
        interval = self.refresh_seconds

        if interval is None:
            return self.fetch_data()

        if self._cached_result is not None and self._last_fetch_time is not None:
            age = (datetime.now() - self._last_fetch_time).total_seconds()
            if age < interval:
                logger.debug(
                    f"Using cached data for {self.plugin_id} "
                    f"(age: {age:.0f}s < {interval}s)"
                )
                return self._cached_result

        result = self.fetch_data()

        if result.available:
            self._cached_result = result
            self._last_fetch_time = datetime.now()

        return result

    def clear_cache(self) -> None:
        """Clear cached data, forcing a fresh fetch on the next get_data() call."""
        self._cached_result = None
        self._last_fetch_time = None

    def _validate_refresh_seconds(self, config: Dict[str, Any]) -> List[str]:
        """Validate refresh_seconds against the manifest schema bounds."""
        errors: List[str] = []
        refresh_schema = self._get_refresh_schema()

        if refresh_schema is None or "refresh_seconds" not in config:
            return errors

        value = config["refresh_seconds"]
        minimum = refresh_schema.get("minimum", MIN_REFRESH_SECONDS)
        maximum = refresh_schema.get("maximum", MAX_REFRESH_SECONDS)

        if not isinstance(value, (int, float)):
            errors.append("Refresh interval must be a number")
        elif value < minimum:
            errors.append(
                f"Refresh interval must be at least {minimum} seconds"
            )
        elif value > maximum:
            errors.append(
                f"Refresh interval must not exceed {maximum} seconds"
            )

        return errors

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate configuration before use.
        
        Override this method to add custom validation logic.
        
        Args:
            config: Configuration dictionary to validate
            
        Returns:
            List of error messages (empty if valid)
        """
        return []
    
    def get_formatted_display(self) -> Optional[List[str]]:
        """Return pre-formatted 6-line display.
        
        Override this method to provide a default formatted display.
        This is used when showing the plugin as a "single" page type.
        
        Returns:
            List of 6 strings for board display, or None to use
            the template system for formatting.
        """
        return None
    
    def on_config_change(self, old_config: Dict[str, Any], new_config: Dict[str, Any]) -> None:
        """Called when configuration is updated.
        
        Override this method to handle configuration changes,
        e.g., to reset caches or reconnect to services.
        
        Args:
            old_config: Previous configuration
            new_config: New configuration
        """
        logger.debug(f"Config changed for {self.plugin_id}")
    
    def cleanup(self) -> None:
        """Called when plugin is disabled or unloaded.
        
        Override this method to clean up resources, close connections, etc.
        """
        pass
    
    def get_variables_schema(self) -> Dict[str, Any]:
        """Return the variables schema from manifest.
        
        Returns:
            Variables schema dictionary for the template engine.
        """
        return self._manifest.get("variables", {})
    
    def get_max_lengths(self) -> Dict[str, int]:
        """Return the max lengths from manifest.
        
        Returns:
            Dictionary mapping variable names to max character lengths.
        """
        return self._manifest.get("max_lengths", {})
    
    def get_settings_schema(self) -> Dict[str, Any]:
        """Return the settings JSON schema from manifest.
        
        Returns:
            JSON Schema for the plugin's settings form.
        """
        return self._manifest.get("settings_schema", {})
    
    def get_env_vars(self) -> List[Dict[str, Any]]:
        """Return required/optional environment variables from manifest.
        
        Returns:
            List of env var definitions with name, required, description.
        """
        return self._manifest.get("env_vars", [])

