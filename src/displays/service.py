"""Display service for managing individual display sources.

This module provides a clean interface to fetch formatted and raw data
from each display source via the plugin system.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from src.devices import BoardContext

# Import plugin system
try:
    from src.plugins import PluginRegistry, get_plugin_registry

    PLUGIN_SYSTEM_AVAILABLE = True
except ImportError:
    PLUGIN_SYSTEM_AVAILABLE = False
    get_plugin_registry = None
    PluginRegistry = None

logger = logging.getLogger(__name__)


@dataclass
class DisplayResult:
    """Result from fetching a display."""

    display_type: str
    formatted: str
    raw: dict[str, Any]
    available: bool
    error: str | None = None


class DisplayService:
    """Service for fetching individual display sources.

    Provides methods to:
    - List available display types
    - Get formatted output for a specific type
    - Get raw data from a source

    Uses the plugin system exclusively for all data sources.
    """

    def __init__(self):
        """Initialize display service with plugin registry."""
        self._plugin_registry: PluginRegistry | None = None

        if PLUGIN_SYSTEM_AVAILABLE:
            try:
                self._plugin_registry = get_plugin_registry()
                self._plugin_registry.initialize()
                logger.info("DisplayService initialized with plugin system")
            except Exception as e:
                logger.error(f"Failed to initialize plugin registry: {e}")
                self._plugin_registry = None
        else:
            logger.error("Plugin system is not available. DisplayService cannot function.")

        logger.info(f"DisplayService initialized (plugins={'enabled' if self._plugin_registry else 'disabled'})")

    def get_plugin_registry(self) -> PluginRegistry | None:
        """Get the plugin registry if available."""
        return self._plugin_registry

    def get_available_displays(self) -> list[dict[str, Any]]:
        """Get list of available display types with their status.

        Returns:
            List of display info dictionaries with:
            - type: Display type name (plugin ID)
            - available: Whether the plugin is configured/available
            - description: Human-readable description
            - source: "plugin"
        """
        if not self._plugin_registry:
            return []

        displays = []
        for plugin_data in self._plugin_registry.list_plugins():
            plugin_id = plugin_data["id"]
            displays.append(
                {
                    "type": plugin_id,
                    "available": self._plugin_registry.is_enabled(plugin_id),
                    "description": plugin_data.get("description", ""),
                    "source": "plugin",
                }
            )
        return displays

    def get_display(self, display_type: str, board: BoardContext | None = None) -> DisplayResult:
        """Get formatted and raw data for a specific display type (plugin).

        Args:
            display_type: Plugin ID
            board: Board being rendered on, forwarded to the plugin so it can
                adapt content (e.g. its pre-formatted display) to the board's
                size. ``None`` keeps the board-agnostic behavior.

        Returns:
            DisplayResult with formatted text and raw data
        """
        if not self._plugin_registry:
            return DisplayResult(
                display_type=display_type, formatted="", raw={}, available=False, error="Plugin system not initialized."
            )

        # Validate the display type exists as a plugin
        if not self._plugin_registry.get_plugin(display_type):
            # Get list of valid plugin IDs
            valid_types = [p["id"] for p in self._plugin_registry.list_plugins()]
            return DisplayResult(
                display_type=display_type,
                formatted="",
                raw={},
                available=False,
                error=f"Unknown display type: {display_type}. Valid types: {valid_types}",
            )

        try:
            plugin_result = self._plugin_registry.fetch_plugin_data(display_type, board=board)

            if plugin_result.available:
                # Convert PluginResult to DisplayResult
                formatted_lines = plugin_result.formatted_lines
                if formatted_lines:
                    formatted = "\n".join(formatted_lines)
                else:
                    formatted = str(plugin_result.data.get("formatted", "")) if plugin_result.data else ""

                return DisplayResult(
                    display_type=display_type, formatted=formatted, raw=plugin_result.data or {}, available=True
                )
            return DisplayResult(
                display_type=display_type, formatted="", raw={}, available=False, error=plugin_result.error
            )
        except Exception as e:
            logger.error(f"Error fetching data for plugin {display_type}: {e}", exc_info=True)
            return DisplayResult(
                display_type=display_type, formatted="", raw={}, available=False, error=f"Error fetching data: {e}"
            )


# Singleton instance
_display_service: DisplayService | None = None


def get_display_service() -> DisplayService:
    """Get or create the display service singleton."""
    global _display_service
    if _display_service is None:
        _display_service = DisplayService()
    return _display_service


def reset_display_service() -> None:
    """Reset the display service singleton to force reinitialization.

    This should be called when configuration changes to ensure
    data sources are recreated with updated settings.
    """
    global _display_service
    _display_service = None
    logger.info("Display service singleton reset")
