"""
Template Plugin for FiestaBoard.

This is a template/example plugin that demonstrates the plugin structure.
Copy this directory to create a new plugin.

Rename the directory to match your plugin ID (from manifest.json).
"""

import logging
import os
from typing import Any

from src.plugins.base import PluginBase, PluginResult

# Uncomment when adding event-based triggers (see check_triggers stub below):
# from src.plugins.base import TriggerResult

logger = logging.getLogger(__name__)


class MyPlugin(PluginBase):
    """Template plugin implementation.

    This class demonstrates how to create a FiestaBoard plugin.
    Rename this class to match your plugin.
    """

    @property
    def plugin_id(self) -> str:
        """Return the plugin ID matching manifest.json."""
        return "my_plugin"

    def fetch_data(self) -> PluginResult:
        """
        Fetch data from your data source.

        This method is called by the display service to get data for
        templates and displays.

        Returns:
            PluginResult with:
            - available: True if data was fetched successfully
            - data: Dictionary of template variables
            - formatted: Optional pre-formatted display string
            - error: Error message if fetch failed
        """
        # Get configuration
        api_key = self.get_config("api_key")

        # Can also check environment variable
        if not api_key:
            api_key = os.getenv("MY_PLUGIN_API_KEY")

        if not api_key:
            return PluginResult(
                available=False,
                error="API key not configured"
            )

        try:
            # TODO: Implement your data fetching logic here
            # Example:
            # response = requests.get("https://api.example.com/data", headers={"Authorization": api_key})
            # data = response.json()

            # For this template, return example data
            example_data = {
                "value": "123",
                "status": "OK",
                "formatted": "Value: 123",
                "item_count": 2,
                "items": [
                    {"name": "Item 1", "value": "100", "status": "Active"},
                    {"name": "Item 2", "value": "200", "status": "Pending"},
                ],
            }

            return PluginResult(
                available=True,
                data=example_data,
                formatted_lines=self._format_display(example_data)
            )

        except Exception as e:
            logger.error(f"Error fetching data: {e}", exc_info=True)
            return PluginResult(
                available=False,
                error=str(e)
            )

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        """
        Validate plugin configuration.

        This method is called when configuration is updated.
        Note: refresh_seconds validation is handled automatically by
        the base class using the manifest's settings_schema bounds.

        Args:
            config: The configuration dictionary to validate

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        # Example validation
        if not config.get("api_key"):
            # API key is required per settings_schema
            errors.append("API key is required")

        return errors

    def _format_display(self, data: dict[str, Any]) -> list[str]:
        """
        Format data for display on the board.

        Args:
            data: The fetched data

        Returns:
            List of display lines (max 22 chars per line, up to 6 lines)
        """
        lines: list[str] = []
        lines.append(f"Status: {data.get('status', 'N/A')}")
        lines.append(f"Value: {data.get('value', 'N/A')}")

        items = data.get("items", [])
        if items:
            lines.append(f"Items: {len(items)}")
            for item in items[:2]:
                lines.append(f"  {item['name']}: {item['value']}")

        while len(lines) < 6:
            lines.append("")

        return lines[:6]

    def cleanup(self) -> None:
        """
        Cleanup when plugin is disabled.

        Override this to clean up any resources (close connections, etc.)
        """
        logger.info(f"Plugin {self.plugin_id} cleanup")

    # ------------------------------------------------------------------
    # Optional: event-based triggers
    # ------------------------------------------------------------------
    # Uncomment and adapt the block below if your plugin needs to push a
    # specific page to the board in response to an event (doorbell ring,
    # weather alert, threshold crossed, etc.). You must also set
    # `"supports_triggers": true` in manifest.json — without that flag
    # this method is never called.
    #
    # Full docs: docs/development/PLUGIN_DEVELOPMENT.md
    # ("Triggering Pages from a Plugin")
    #
    # def check_triggers(self) -> list["TriggerResult"]:
    #     """Return a list of TriggerResult; entries with triggered=True activate."""
    #     event = self._pending_event()  # your own state
    #     if event is None:
    #         return []
    #     return [
    #         TriggerResult(
    #             triggered=True,
    #             trigger_id=f"my_plugin_event_{event.id}",  # stable per event
    #             priority=50,                                # higher = more important
    #             duration_seconds=30,                        # auto-expires after this
    #             data={"label": event.label},                # → {{my_plugin.label}}
    #             message="Event fired",                      # fallback when no
    #                                                         # trigger_page_id is set
    #         )
    #     ]

