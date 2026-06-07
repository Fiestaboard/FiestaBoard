"""Base classes for FiestaBoard plugins.

All plugins must inherit from PluginBase and implement the required methods.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

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
    data: dict[str, Any] | None = None
    error: str | None = None
    formatted_lines: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "available": self.available,
            "data": self.data,
            "error": self.error,
            "formatted_lines": self.formatted_lines,
        }


@dataclass
class TriggerResult:
    """Result from a plugin trigger check.

    Plugins that support event-based triggers return a list of these
    from ``check_triggers()``.  Only results with ``triggered=True``
    cause the board to display the associated message.

    Attributes:
        triggered: Whether this trigger has fired.
        trigger_id: Stable identifier for this trigger (used for dedup/dismiss).
        message: Simple text message to display on the board.
        formatted_lines: Pre-formatted display lines (6 lines for board).
        priority: Higher values take precedence when multiple triggers fire.
        duration_seconds: How long the triggered message should be shown.
        data: Raw data dict available for template rendering.
    """

    triggered: bool
    trigger_id: str = ""
    message: str | None = None
    formatted_lines: list[str] | None = None
    priority: int = 0
    duration_seconds: int = 30
    data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "triggered": self.triggered,
            "trigger_id": self.trigger_id,
            "message": self.message,
            "formatted_lines": self.formatted_lines,
            "priority": self.priority,
            "duration_seconds": self.duration_seconds,
            "data": self.data,
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

    def __init__(self, manifest: dict[str, Any]):
        """Initialize plugin with its manifest.

        Args:
            manifest: Parsed manifest.json dictionary
        """
        self._manifest = manifest
        self._config: dict[str, Any] = {}
        self._enabled = False
        self._cached_result: PluginResult | None = None
        self._last_fetch_time: datetime | None = None
        logger.debug(f"Plugin initialized: {self.plugin_id}")

    @property
    @abstractmethod
    def plugin_id(self) -> str:
        """Return unique plugin identifier.

        Must match the 'id' field in manifest.json.
        """

    @property
    def manifest(self) -> dict[str, Any]:
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
    def config(self) -> dict[str, Any]:
        """Return current plugin configuration."""
        return self._config

    @config.setter
    def config(self, value: dict[str, Any]) -> None:
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

    def _get_refresh_schema(self) -> dict[str, Any] | None:
        """Get refresh_seconds property schema from the manifest, if defined."""
        schema = self._manifest.get("settings_schema", {})
        properties = schema.get("properties", {})
        return properties.get("refresh_seconds")

    @property
    def min_refresh_seconds(self) -> int | None:
        """Get the hard rate-limit floor from the manifest.

        This is the absolute minimum refresh interval enforced at runtime,
        regardless of user configuration.  Plugin developers set this via
        the top-level ``min_refresh_seconds`` field in manifest.json.
        Falls back to settings_schema ``minimum`` if the explicit field
        is absent.  Returns None when the plugin has no refresh_seconds.
        """
        refresh_schema = self._get_refresh_schema()
        if refresh_schema is None:
            return None
        explicit = self._manifest.get("min_refresh_seconds")
        if explicit is not None:
            return int(explicit)
        return refresh_schema.get("minimum", MIN_REFRESH_SECONDS)

    @property
    def live_data(self) -> bool:
        """Whether this plugin opts out of caching and serves fresh data every tick.

        Plugins that genuinely need fresh data on every render (clocks,
        animations, anything driven by ``now()``) set ``live_data: true``
        at the top level of ``manifest.json``.  When true, :meth:`get_data`
        skips the cache entirely and calls :meth:`fetch_data` on every call.

        Defaults to ``False`` -- the safer behavior -- so plugins that
        don't declare a refresh interval get a sensible default cache
        instead of hammering their data source on every poll tick.
        """
        return bool(self._manifest.get("live_data", False))

    @property
    def refresh_seconds(self) -> int | None:
        """Get the effective refresh interval in seconds.

        Resolution order:

        1. If the plugin's manifest declares ``live_data: true``, return
           ``None`` to signal "no cache" to :meth:`get_data`.
        2. If the manifest declares ``refresh_seconds`` in its
           ``settings_schema``, return the configured/default value
           (clamped to ``min_refresh_seconds``).
        3. Otherwise fall back to :data:`DEFAULT_REFRESH_SECONDS` so a
           plugin that forgot to declare a refresh interval still gets a
           reasonable cache instead of fetching fresh data on every tick.
        """
        if self.live_data:
            return None
        refresh_schema = self._get_refresh_schema()
        if refresh_schema is None:
            return DEFAULT_REFRESH_SECONDS
        default = refresh_schema.get("default", DEFAULT_REFRESH_SECONDS)
        value = self._config.get("refresh_seconds", default)
        floor = self.min_refresh_seconds
        if floor is not None and isinstance(value, int | float) and value < floor:
            logger.warning(f"Plugin {self.plugin_id}: refresh_seconds {value} is below hard minimum {floor}, clamping")
            return floor
        return value

    def get_data(self) -> PluginResult:
        """Get plugin data with automatic caching based on refresh_seconds.

        Behavior is controlled by the manifest:

        * ``live_data: true`` -- bypass the cache entirely (every call
          invokes :meth:`fetch_data`).  Use this for clocks/animations
          where stale data is wrong by definition.
        * ``settings_schema.properties.refresh_seconds`` declared -- cache
          results for the configured interval.
        * Neither declared -- cache results for
          :data:`DEFAULT_REFRESH_SECONDS` (5 minutes).  This is the safer
          default for random/static-ish data sources.

        Returns:
            PluginResult with data or error
        """
        if self.live_data:
            logger.debug(f"Live data plugin {self.plugin_id}: skipping cache")
            return self.fetch_data()

        interval = self.refresh_seconds

        if interval is None:
            return self.fetch_data()

        if self._cached_result is not None and self._last_fetch_time is not None:
            age = (datetime.now() - self._last_fetch_time).total_seconds()
            if age < interval:
                logger.debug(f"Using cached data for {self.plugin_id} (age: {age:.0f}s < {interval}s)")
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

    def _validate_refresh_seconds(self, config: dict[str, Any]) -> list[str]:
        """Validate refresh_seconds against the manifest schema bounds.

        Uses the hard floor from ``min_refresh_seconds`` (which considers
        the top-level manifest field first, then the schema minimum).
        """
        errors: list[str] = []
        refresh_schema = self._get_refresh_schema()

        if refresh_schema is None or "refresh_seconds" not in config:
            return errors

        value = config["refresh_seconds"]
        floor = self.min_refresh_seconds or MIN_REFRESH_SECONDS
        maximum = refresh_schema.get("maximum", MAX_REFRESH_SECONDS)

        if not isinstance(value, int | float):
            errors.append("Refresh interval must be a number")
        elif value < floor:
            errors.append(f"Refresh interval must be at least {floor} seconds")
        elif value > maximum:
            errors.append(f"Refresh interval must not exceed {maximum} seconds")

        return errors

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        """Validate configuration before use.

        Override this method to add custom validation logic.

        Args:
            config: Configuration dictionary to validate

        Returns:
            List of error messages (empty if valid)
        """
        return []

    def get_formatted_display(self) -> list[str] | None:
        """Return pre-formatted 6-line display.

        Override this method to provide a default formatted display.
        This is used when showing the plugin as a "single" page type.

        Returns:
            List of 6 strings for board display, or None to use
            the template system for formatting.
        """
        return None

    def on_config_change(self, old_config: dict[str, Any], new_config: dict[str, Any]) -> None:
        """Called when configuration is updated.

        Override this method to handle configuration changes,
        e.g., to reset caches or reconnect to services.

        Args:
            old_config: Previous configuration
            new_config: New configuration
        """
        logger.debug(f"Config changed for {self.plugin_id}")

    def cleanup(self) -> None:  # noqa: B027 — optional override hook, intentionally empty
        """Called when plugin is disabled or unloaded.

        Override this method to clean up resources, close connections, etc.
        """

    def resolve_config_variables(
        self,
        extra_variables: dict[str, str] | None = None,
        timezone: str | None = None,
    ) -> dict[str, Any]:
        """Return a copy of the plugin config with ``{{variable}}`` patterns resolved.

        Built-in system variables (date, year, month, day, hour, minute,
        timestamp, etc.) are always available.  Additional variables can be
        supplied via *extra_variables* (e.g. cross-plugin references).

        The original ``self.config`` is **never** mutated.

        Args:
            extra_variables: Optional mapping of additional variable names
                to string values.  These take precedence over built-in
                variables when names collide.
            timezone: Optional IANA timezone name for date/time variables.

        Returns:
            A new configuration dictionary with variables resolved.
        """
        from .config_interpolation import get_builtin_variables, interpolate_config

        variables = get_builtin_variables(timezone=timezone)
        if extra_variables:
            variables.update(extra_variables)

        return interpolate_config(self._config, variables)

    def get_resolved_config_value(
        self,
        key: str,
        default: Any = None,
        extra_variables: dict[str, str] | None = None,
        timezone: str | None = None,
    ) -> Any:
        """Return a single config value from a resolved copy (see ``resolve_config_variables``)."""
        resolved = self.resolve_config_variables(extra_variables=extra_variables, timezone=timezone)
        return resolved.get(key, default)

    def get_url(
        self,
        key: str = "url",
        default: str = "",
        extra_variables: dict[str, str] | None = None,
        timezone: str | None = None,
    ) -> str:
        """Return a string setting with ``{{variable}}`` patterns resolved.

        Intended for HTTP endpoint fields (e.g. Generic Data ``url``). Non-string
        values fall back to *default*.
        """
        raw = self.get_resolved_config_value(
            key,
            default=default,
            extra_variables=extra_variables,
            timezone=timezone,
        )
        if raw is None:
            return default
        if isinstance(raw, str):
            return raw
        return default

    def get_variables_schema(self) -> dict[str, Any]:
        """Return the variables schema from manifest.

        Returns:
            Variables schema dictionary for the template engine.
        """
        return self._manifest.get("variables", {})

    def get_max_lengths(self) -> dict[str, int]:
        """Return the max lengths from manifest.

        Returns:
            Dictionary mapping variable names to max character lengths.
        """
        return self._manifest.get("max_lengths", {})

    def get_settings_schema(self) -> dict[str, Any]:
        """Return the settings JSON schema from manifest.

        Returns:
            JSON Schema for the plugin's settings form.
        """
        return self._manifest.get("settings_schema", {})

    @property
    def supports_triggers(self) -> bool:
        """Whether this plugin supports event-based triggers.

        Determined by the ``supports_triggers`` flag in the plugin manifest.
        """
        return bool(self._manifest.get("supports_triggers", False))

    def receive_payload(self, payload: dict[str, Any], headers: dict[str, str], raw_body: bytes = b"") -> None:
        """Handle an incoming webhook payload pushed to this plugin.

        Override this in plugins that accept push data from external systems.
        Raise ``PermissionError`` for signature validation failures (→ HTTP 403),
        ``ValueError`` for bad request data (→ HTTP 400).
        The default implementation raises ``NotImplementedError`` (→ HTTP 405).
        """
        raise NotImplementedError(f"Plugin {self.plugin_id} does not support receive")

    def check_triggers(self) -> list["TriggerResult"]:
        """Check whether any event-based triggers should fire.

        Plugins that support triggers override this method to evaluate
        conditions and return one or more :class:`TriggerResult` objects.
        Only results where ``triggered`` is ``True`` will be activated.

        The method is called periodically by the trigger service.

        Returns:
            List of TriggerResult objects (empty by default).
        """
        return []

    def fire_trigger(self, trigger: "TriggerResult") -> None:
        """Immediately submit a trigger to the active :class:`TriggerService`.

        Intended for **push-driven** plugins -- typically those overriding
        :meth:`receive_payload` -- that need to surface an event as soon as
        a webhook arrives instead of waiting for the next polling tick or
        re-implementing ``check_triggers``.

        The method is a no-op when:

        * the plugin's manifest does not declare ``supports_triggers: true``
          (the trigger system is intentionally opt-in), or
        * the supplied :class:`TriggerResult` has ``triggered=False`` (matches
          the behaviour of :meth:`TriggerService.check_plugin_triggers`).

        Triggers that the user has dismissed are still suppressed by the
        :class:`TriggerService`; ``fire_trigger`` simply delegates and does
        not bypass user overrides.

        Args:
            trigger: The :class:`TriggerResult` to enqueue.  When ``trigger_id``
                is omitted the plugin id is used as a fallback so simple
                webhook handlers can fire-and-forget.
        """
        if not self.supports_triggers:
            logger.debug(
                "fire_trigger called on plugin %s which does not declare supports_triggers; ignoring",
                self.plugin_id,
            )
            return

        if not getattr(trigger, "triggered", False):
            logger.debug(
                "fire_trigger received a non-fired TriggerResult from %s; ignoring",
                self.plugin_id,
            )
            return

        # Default trigger_id to the plugin id so naive callers
        # (``self.fire_trigger(TriggerResult(triggered=True, message="..."))``)
        # don't end up colliding on an empty string in the service dict.
        if not trigger.trigger_id:
            trigger.trigger_id = self.plugin_id

        try:
            # Local import keeps the plugin base independent of the triggers
            # subpackage at import time (avoids a circular import — the
            # service module imports PluginBase).
            from src.triggers.service import get_trigger_service
        except Exception:
            logger.exception(
                "fire_trigger could not import TriggerService for plugin %s",
                self.plugin_id,
            )
            return

        service = get_trigger_service()
        service.activate_trigger(self.plugin_id, trigger)

    def get_env_vars(self) -> list[dict[str, Any]]:
        """Return required/optional environment variables from manifest.

        Returns:
            List of env var definitions with name, required, description.
        """
        return self._manifest.get("env_vars", [])
