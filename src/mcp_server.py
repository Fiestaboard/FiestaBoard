"""FiestaBoard MCP Server.

Exposes all FiestaBoard management operations as MCP (Model Context Protocol)
tools, enabling external LLMs such as Claude Desktop or Claude Code to control
FiestaBoard via conversation.

Mount point: ``/mcp``  (accessed as ``/api/mcp`` via nginx)

No authentication is required — this server is intended for local / LAN use.
When FiestaBoard gains a login system, Bearer-token auth should be added here.

Connection example for Claude Desktop (``claude_desktop_config.json``):
    {
        "mcpServers": {
            "fiestaboard": {
                "type": "http",
                "url": "http://fiestaboard.local:4420/api/mcp"
            }
        }
    }

Connection example for Claude Code:
    Add via: /mcp add fiestaboard --transport http --url http://localhost:4420/api/mcp
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports — the MCP package is optional; we log a warning if missing
# rather than crashing the whole API server on import.
# ---------------------------------------------------------------------------

try:
    from mcp.server.fastmcp import FastMCP  # type: ignore[import-untyped]
    _MCP_AVAILABLE = True
except ImportError:  # pragma: no cover
    _MCP_AVAILABLE = False
    FastMCP = None  # type: ignore[assignment,misc]
    logger.warning(
        "mcp package not installed — FiestaBoard MCP server is disabled. "
        "Add `mcp>=1.8.0` to requirements.txt and rebuild the container."
    )


def _build_mcp_server() -> Any:  # noqa: PLR0915 — large but tabular
    """Construct and return the FastMCP server instance.

    Returns ``None`` if the ``mcp`` package is not installed.
    """
    if not _MCP_AVAILABLE:
        return None

    mcp = FastMCP(
        "FiestaBoard",
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
        instructions=(
            "FiestaBoard is a smart LED matrix display controller. You can:\n"
            "  • Manage plugins/integrations (weather, stocks, transit, etc.)\n"
            "  • Create and edit display pages using template variables from plugins\n"
            "  • Schedule which page shows at which time of day\n"
            "  • Create carousels that rotate through multiple pages\n\n"
            "Typical workflow:\n"
            "  1. list_installed_plugins() — see what's installed & enabled\n"
            "  2. list_pages() — see current pages\n"
            "  3. get_template_variables() — see what variables plugins expose\n"
            "  4. install/configure plugins as needed\n"
            "  5. create_page() with template_lines using {{plugin_id.variable_name}} syntax\n"
            "  6. Optionally schedule pages with create_schedule()\n\n"
            "Template syntax: variables use double-braces like {{weather.temperature}}. "
            "Color tokens like {{red}}, {{green}} etc. style text inline."
        ),
    )

    # -----------------------------------------------------------------------
    # Plugin tools
    # -----------------------------------------------------------------------

    @mcp.tool()
    def list_installed_plugins() -> str:
        """List all installed FiestaBoard plugins with their status and config schema.

        Returns a JSON array of plugin objects. Each includes:
        - id: plugin identifier (use this for other plugin tools)
        - name: display name
        - enabled: whether the plugin is active
        - configured: whether required settings have been filled in
        - description: what the plugin does
        - settings_schema: JSON Schema describing configurable fields
        - config: current configuration (sensitive values masked as '***')
        """
        try:
            from .plugins import get_plugin_registry
            from .config_manager import get_config_manager
            registry = get_plugin_registry()
            cm = get_config_manager()
            plugins = registry.list_plugins()
            for p in plugins:
                cfg = cm.get_plugin_config(p["id"])
                p["config"] = cm._mask_sensitive(cfg) if cfg else {}
                p["configured"] = bool(cfg)
            return json.dumps(plugins, default=str)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    @mcp.tool()
    def list_registry_plugins() -> str:
        """List all plugins available to install from the FiestaBoard registry.

        Returns a JSON array. Each entry includes:
        - id: use this as plugin_id when calling install_plugin()
        - name, description, category
        - installed: true if already installed
        """
        try:
            from .plugins import get_plugin_registry
            registry = get_plugin_registry()
            return json.dumps(registry.get_registry_entries(), default=str)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    @mcp.tool()
    def install_plugin(plugin_id: str, auto_enable: bool = True) -> str:
        """Install a plugin from the official FiestaBoard registry and optionally enable it.

        Args:
            plugin_id: The plugin identifier from list_registry_plugins() (e.g. 'openweather').
            auto_enable: Whether to enable the plugin after installation (default: True).

        After installing, use configure_plugin() to set API keys and other settings.
        Use get_template_variables() to discover the variables the plugin exposes.
        """
        try:
            from .plugins import get_plugin_registry
            registry = get_plugin_registry()
            registry.install_from_registry(plugin_id)
            if auto_enable:
                registry.enable_plugin(plugin_id)
            status = "installed and enabled" if auto_enable else "installed (disabled)"
            return f"Plugin '{plugin_id}' {status} successfully."
        except Exception as exc:
            return f"Error installing plugin '{plugin_id}': {exc}"

    @mcp.tool()
    def enable_plugin(plugin_id: str) -> str:
        """Enable an installed but currently-disabled plugin.

        Args:
            plugin_id: The plugin identifier (from list_installed_plugins()).
        """
        try:
            from .plugins import get_plugin_registry
            registry = get_plugin_registry()
            registry.enable_plugin(plugin_id)
            return f"Plugin '{plugin_id}' enabled successfully."
        except Exception as exc:
            return f"Error enabling plugin '{plugin_id}': {exc}"

    @mcp.tool()
    def disable_plugin(plugin_id: str) -> str:
        """Disable an installed plugin without uninstalling it.

        The plugin can be re-enabled later with enable_plugin().

        Args:
            plugin_id: The plugin identifier (from list_installed_plugins()).
        """
        try:
            from .plugins import get_plugin_registry
            registry = get_plugin_registry()
            registry.disable_plugin(plugin_id)
            return f"Plugin '{plugin_id}' disabled successfully."
        except Exception as exc:
            return f"Error disabling plugin '{plugin_id}': {exc}"

    @mcp.tool()
    def uninstall_plugin(plugin_id: str) -> str:
        """Permanently remove an installed plugin.

        WARNING: This is irreversible. The plugin and all its configuration
        will be deleted. Only external/registry plugins can be uninstalled;
        built-in plugins cannot be removed.

        Args:
            plugin_id: The plugin identifier (from list_installed_plugins()).
        """
        try:
            from .plugins import get_plugin_registry
            registry = get_plugin_registry()
            registry.uninstall_external_plugin(plugin_id)
            return f"Plugin '{plugin_id}' uninstalled successfully."
        except Exception as exc:
            return f"Error uninstalling plugin '{plugin_id}': {exc}"

    @mcp.tool()
    def configure_plugin(plugin_id: str, config: Dict[str, Any]) -> str:
        """Update configuration settings for an installed plugin.

        Use list_installed_plugins() to see the settings_schema for a plugin,
        which shows all valid config keys, their types, and which are required.

        IMPORTANT: Never guess API keys — only set values the user has provided.
        Sensitive fields (api_key, password, etc.) must be provided explicitly.

        Args:
            plugin_id: The plugin identifier.
            config: Dictionary of configuration key-value pairs to update.
                    Only include keys you want to change.
        """
        try:
            from .plugins import get_plugin_registry
            from .config_manager import get_config_manager
            registry = get_plugin_registry()
            cm = get_config_manager()
            # Merge with existing config to avoid wiping unchanged fields
            existing = cm.get_plugin_config(plugin_id) or {}
            merged = {**existing, **config}
            registry.set_plugin_config(plugin_id, merged)
            # Return masked config so sensitive values aren't echoed back
            updated = cm.get_plugin_config(plugin_id) or {}
            return json.dumps({
                "status": "success",
                "plugin_id": plugin_id,
                "config": cm._mask_sensitive(updated),
            }, default=str)
        except Exception as exc:
            return f"Error configuring plugin '{plugin_id}': {exc}"

    @mcp.tool()
    def update_plugin(plugin_id: str) -> str:
        """Update an installed plugin to its latest registry version.

        Args:
            plugin_id: The plugin identifier (from list_installed_plugins()).
        """
        try:
            from .plugins import get_plugin_registry
            registry = get_plugin_registry()
            registry.reload_plugin(plugin_id)
            return f"Plugin '{plugin_id}' updated successfully."
        except Exception as exc:
            return f"Error updating plugin '{plugin_id}': {exc}"

    @mcp.tool()
    def get_template_variables() -> str:
        """Get all template variables available from enabled plugins.

        Returns a nested JSON object: {plugin_id: {variable_name: {description, example, max_length}}}.
        Use these variables in page templates as {{plugin_id.variable_name}}.

        Example: {{weather.temperature}}, {{stocks.price}}, {{date_time.time_12h}}
        """
        try:
            from .plugins import get_plugin_registry
            registry = get_plugin_registry()
            variables = registry.get_all_variables()
            return json.dumps(variables, default=str)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    # -----------------------------------------------------------------------
    # Page tools
    # -----------------------------------------------------------------------

    @mcp.tool()
    def list_pages() -> str:
        """List all display pages on this FiestaBoard.

        Returns a JSON array of page objects with:
        - id: use this for get_page(), update_page(), delete_page(), schedules
        - name: display name
        - type: 'template' (dynamic content), 'single', or 'composite'
        - device_type: 'flagship' or 'note'
        - duration_seconds: how long to show the page in carousels
        """
        try:
            from .pages.service import get_page_service
            svc = get_page_service()
            pages = svc.list_pages()
            return json.dumps([p.model_dump() for p in pages], default=str)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    @mcp.tool()
    def get_page(page_id: str) -> str:
        """Get full details of a specific page including its template content.

        Args:
            page_id: The page identifier (from list_pages()).

        Returns a JSON object with all page fields including the template array.
        Each template line can contain {{plugin.variable}} references and
        {{color}} tokens like {{red}}, {{green}}, {{white}} etc.
        """
        try:
            from .pages.service import get_page_service
            svc = get_page_service()
            page = svc.get_page(page_id)
            if page is None:
                return json.dumps({"error": f"Page '{page_id}' not found."})
            return json.dumps(page.model_dump(), default=str)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    @mcp.tool()
    def create_page(
        name: str,
        template_lines: List[str],
        device_type: str = "flagship",
        duration_seconds: int = 300,
    ) -> str:
        """Create a new template page on FiestaBoard.

        Template lines use {{plugin.variable}} syntax for dynamic data and
        {{color}} tokens ({{red}}, {{green}}, {{white}}, etc.) for styling.

        Flagship display is 22 columns × 6 rows.
        Note display is 15 columns × 3 rows.

        Args:
            name: Display name for the page.
            template_lines: List of template strings, one per row. Must match
                            the number of rows for the device_type
                            (6 for flagship, 3 for note).
            device_type: 'flagship' (default) or 'note'.
            duration_seconds: How long to show this page in a carousel (default: 300).

        Example template_lines for a weather page:
            ["{{white}}{{= UPPER(weather.city)}}", "{{yellow}}{{weather.temperature}}°F",
             "{{weather.condition}}", "", "{{date_time.time_12h}}", "{{date_time.date_short}}"]
        """
        try:
            from .pages.service import get_page_service
            from .pages.models import PageCreate
            svc = get_page_service()
            data = PageCreate(
                name=name,
                type="template",
                device_type=device_type,  # type: ignore[arg-type]
                template=template_lines,
                duration_seconds=duration_seconds,
            )
            page = svc.create_page(data)
            return json.dumps({
                "status": "success",
                "page_id": page.id,
                "name": page.name,
                "message": f"Page '{name}' created with id '{page.id}'.",
            }, default=str)
        except Exception as exc:
            return f"Error creating page: {exc}"

    @mcp.tool()
    def update_page(
        page_id: str,
        name: Optional[str] = None,
        template_lines: Optional[List[str]] = None,
        duration_seconds: Optional[int] = None,
    ) -> str:
        """Update an existing page's name, template content, or duration.

        Args:
            page_id: The page identifier (from list_pages()).
            name: New display name (optional).
            template_lines: New template content (optional). Replaces all lines.
            duration_seconds: New carousel duration in seconds (optional).
        """
        try:
            from .pages.service import get_page_service
            from .pages.models import PageUpdate
            svc = get_page_service()
            data = PageUpdate(
                name=name,
                template=template_lines,
                duration_seconds=duration_seconds,
            )
            page = svc.update_page(page_id, data)
            if page is None:
                return json.dumps({"error": f"Page '{page_id}' not found."})
            return json.dumps({"status": "success", "page_id": page.id, "name": page.name}, default=str)
        except Exception as exc:
            return f"Error updating page '{page_id}': {exc}"

    @mcp.tool()
    def delete_page(page_id: str) -> str:
        """Delete a page permanently.

        WARNING: This cannot be undone. If this is the last page, a default
        welcome page will be created automatically.

        Args:
            page_id: The page identifier (from list_pages()).
        """
        try:
            from .pages.service import get_page_service
            svc = get_page_service()
            result = svc.delete_page(page_id)
            if not result.success:
                return f"Error deleting page: {result.message}"
            return f"Page '{page_id}' deleted successfully."
        except Exception as exc:
            return f"Error deleting page '{page_id}': {exc}"

    # -----------------------------------------------------------------------
    # Schedule tools
    # -----------------------------------------------------------------------

    @mcp.tool()
    def list_schedules() -> str:
        """List all scheduled time slots for page display.

        Returns a JSON array of schedule entries with:
        - id: use this for update_schedule(), delete_schedule()
        - page_id: which page to show
        - start_time / end_time: HH:MM format (24h). end_time null = runs until next schedule.
        - day_pattern: 'all', 'weekdays', 'weekends', or 'custom'
        - enabled: whether the schedule entry is active
        """
        try:
            from .schedules.service import get_schedule_service
            svc = get_schedule_service()
            schedules = svc.list_schedules()
            return json.dumps([s.model_dump() for s in schedules], default=str)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    @mcp.tool()
    def create_schedule(
        page_id: str,
        start_time: str,
        day_pattern: str = "all",
        end_time: Optional[str] = None,
        enabled: bool = True,
    ) -> str:
        """Create a new schedule entry to show a specific page at a specific time.

        Args:
            page_id: Which page (or carousel) to display. Use IDs from list_pages()
                     or list_carousels().
            start_time: When to start showing this page in HH:MM format (24h), e.g. "07:00".
            day_pattern: When this applies — 'all' (every day), 'weekdays', 'weekends',
                         or 'custom'. Default: 'all'.
            end_time: When to stop in HH:MM format. Null means open-ended
                      (runs until the next schedule or end of day). Default: None.
            enabled: Whether this schedule is active. Default: True.
        """
        try:
            from .schedules.service import get_schedule_service
            from .schedules.models import ScheduleCreate
            svc = get_schedule_service()
            data = ScheduleCreate(
                page_id=page_id,
                start_time=start_time,
                end_time=end_time,
                day_pattern=day_pattern,  # type: ignore[arg-type]
                enabled=enabled,
            )
            entry = svc.create_schedule(data)
            return json.dumps({
                "status": "success",
                "schedule_id": entry.id,
                "message": f"Schedule created: page '{page_id}' from {start_time} on {day_pattern} days.",
            }, default=str)
        except Exception as exc:
            return f"Error creating schedule: {exc}"

    @mcp.tool()
    def update_schedule(
        schedule_id: str,
        page_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        day_pattern: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> str:
        """Update an existing schedule entry.

        Only the fields you provide will be changed.

        Args:
            schedule_id: The schedule identifier (from list_schedules()).
            page_id: New page to display (optional).
            start_time: New start time in HH:MM format (optional).
            end_time: New end time in HH:MM format, or None to make open-ended (optional).
            day_pattern: New day pattern: 'all', 'weekdays', 'weekends', 'custom' (optional).
            enabled: Enable or disable this schedule entry (optional).
        """
        try:
            from .schedules.service import get_schedule_service
            from .schedules.models import ScheduleUpdate
            svc = get_schedule_service()
            data = ScheduleUpdate(
                page_id=page_id,
                start_time=start_time,
                end_time=end_time,
                day_pattern=day_pattern,  # type: ignore[arg-type]
                enabled=enabled,
            )
            entry = svc.update_schedule(schedule_id, data)
            if entry is None:
                return f"Schedule '{schedule_id}' not found."
            return json.dumps({"status": "success", "schedule_id": entry.id}, default=str)
        except Exception as exc:
            return f"Error updating schedule '{schedule_id}': {exc}"

    @mcp.tool()
    def delete_schedule(schedule_id: str) -> str:
        """Delete a schedule entry permanently.

        Args:
            schedule_id: The schedule identifier (from list_schedules()).
        """
        try:
            from .schedules.service import get_schedule_service
            svc = get_schedule_service()
            svc.delete_schedule(schedule_id)
            return f"Schedule '{schedule_id}' deleted successfully."
        except Exception as exc:
            return f"Error deleting schedule '{schedule_id}': {exc}"

    # -----------------------------------------------------------------------
    # Carousel tools
    # -----------------------------------------------------------------------

    @mcp.tool()
    def list_carousels() -> str:
        """List all carousels (playlists that rotate between multiple pages).

        Returns a JSON array with:
        - id: use this for update_carousel(), delete_carousel(), or as page_id in schedules
        - name, page_ids, interval_seconds
        """
        try:
            from .carousels.service import get_carousel_service
            svc = get_carousel_service()
            carousels = svc.list_carousels()
            return json.dumps([c.model_dump() for c in carousels], default=str)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    @mcp.tool()
    def create_carousel(
        name: str,
        page_ids: List[str],
        interval_seconds: int = 30,
    ) -> str:
        """Create a carousel that rotates through multiple pages.

        The carousel ID can be used as the page_id in create_schedule() to
        schedule the whole playlist at a specific time of day.

        Args:
            name: Display name for the carousel.
            page_ids: Ordered list of page IDs to rotate through.
            interval_seconds: How long to show each page (default: 30). Range: 5–3600.
        """
        try:
            from .carousels.service import get_carousel_service
            from .carousels.models import CarouselCreate
            svc = get_carousel_service()
            data = CarouselCreate(
                name=name,
                page_ids=page_ids,
                interval_seconds=interval_seconds,
            )
            carousel = svc.create_carousel(data)
            return json.dumps({
                "status": "success",
                "carousel_id": carousel.id,
                "name": carousel.name,
                "message": f"Carousel '{name}' created with {len(page_ids)} pages.",
            }, default=str)
        except Exception as exc:
            return f"Error creating carousel: {exc}"

    @mcp.tool()
    def update_carousel(
        carousel_id: str,
        name: Optional[str] = None,
        page_ids: Optional[List[str]] = None,
        interval_seconds: Optional[int] = None,
    ) -> str:
        """Update an existing carousel's name, page list, or rotation interval.

        Args:
            carousel_id: The carousel identifier (from list_carousels()).
            name: New name (optional).
            page_ids: New ordered list of page IDs (optional). Replaces entire list.
            interval_seconds: New rotation interval in seconds (optional).
        """
        try:
            from .carousels.service import get_carousel_service
            from .carousels.models import CarouselUpdate
            svc = get_carousel_service()
            data = CarouselUpdate(
                name=name,
                page_ids=page_ids,
                interval_seconds=interval_seconds,
            )
            carousel = svc.update_carousel(carousel_id, data)
            if carousel is None:
                return f"Carousel '{carousel_id}' not found."
            return json.dumps({"status": "success", "carousel_id": carousel.id}, default=str)
        except Exception as exc:
            return f"Error updating carousel '{carousel_id}': {exc}"

    @mcp.tool()
    def delete_carousel(carousel_id: str) -> str:
        """Delete a carousel permanently.

        Args:
            carousel_id: The carousel identifier (from list_carousels()).
        """
        try:
            from .carousels.service import get_carousel_service
            svc = get_carousel_service()
            svc.delete_carousel(carousel_id)
            return f"Carousel '{carousel_id}' deleted successfully."
        except Exception as exc:
            return f"Error deleting carousel '{carousel_id}': {exc}"

    # -----------------------------------------------------------------------
    # System tools
    # -----------------------------------------------------------------------

    @mcp.tool()
    def get_system_status() -> str:
        """Get the current status of the FiestaBoard system.

        Returns version, whether the display service is running, plugin system
        status, and the number of installed/enabled plugins.
        """
        try:
            from .api_server import __version__, _service_running, get_service
            from .plugins import get_plugin_registry
            registry = get_plugin_registry()
            plugins = registry.list_plugins()
            service = get_service()
            return json.dumps({
                "version": __version__,
                "service_running": _service_running and service is not None,
                "plugin_system_available": True,
                "plugins_installed": len(plugins),
                "plugins_enabled": sum(1 for p in plugins if p.get("enabled")),
            }, default=str)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    @mcp.tool()
    def get_settings_summary() -> str:
        """Get a summary of current FiestaBoard settings (non-sensitive fields only).

        Returns display, output, location, and schedule settings.
        AI provider credentials and board API keys are intentionally excluded.
        """
        try:
            from .settings.service import get_settings_service
            svc = get_settings_service()
            summary: Dict[str, Any] = {}
            try:
                display = svc.get_display_settings()
                summary["display"] = display.__dict__ if hasattr(display, "__dict__") else str(display)
            except Exception:
                pass
            try:
                location = svc.get_location_settings()
                summary["location"] = location.__dict__ if hasattr(location, "__dict__") else str(location)
            except Exception:
                pass
            try:
                output = svc.get_output_settings()
                summary["output"] = output.__dict__ if hasattr(output, "__dict__") else str(output)
            except Exception:
                pass
            return json.dumps(summary, default=str)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    @mcp.tool()
    def set_active_page(page_id: str) -> str:
        """Set which page is currently shown on the FiestaBoard display.

        This immediately changes what's visible on the board.

        Args:
            page_id: The page or carousel ID to display (from list_pages() or list_carousels()).
        """
        try:
            from .config_manager import get_config_manager
            cm = get_config_manager()
            cm.set_active_page(page_id)
            return f"Active page set to '{page_id}'."
        except Exception as exc:
            return f"Error setting active page: {exc}"

    @mcp.tool()
    def set_schedule_mode(enabled: bool) -> str:
        """Enable or disable schedule mode.

        When enabled, FiestaBoard automatically switches pages according to
        the schedule you've configured. When disabled, it shows a fixed page.

        Args:
            enabled: True to enable schedule-based display, False to disable.
        """
        try:
            from .schedules.service import get_schedule_service
            svc = get_schedule_service()
            svc.set_schedule_enabled(enabled)
            state = "enabled" if enabled else "disabled"
            return f"Schedule mode {state}."
        except Exception as exc:
            return f"Error setting schedule mode: {exc}"

    # -----------------------------------------------------------------------
    # MCP Resources
    # -----------------------------------------------------------------------

    @mcp.resource("fiestaboard://plugins")
    def get_plugins_resource() -> str:
        """Live list of all installed plugins with status."""
        try:
            from .plugins import get_plugin_registry
            registry = get_plugin_registry()
            plugins = registry.list_plugins()
            lines = [f"# Installed Plugins ({len(plugins)} total)\n"]
            for p in plugins:
                status = "✓ enabled" if p.get("enabled") else "✗ disabled"
                lines.append(f"- **{p['name']}** (`{p['id']}`) — {status}")
                if p.get("description"):
                    lines.append(f"  {p['description']}")
            return "\n".join(lines)
        except Exception as exc:
            return f"Error: {exc}"

    @mcp.resource("fiestaboard://pages")
    def get_pages_resource() -> str:
        """Live list of all pages."""
        try:
            from .pages.service import get_page_service
            svc = get_page_service()
            pages = svc.list_pages()
            lines = [f"# Pages ({len(pages)} total)\n"]
            for p in pages:
                lines.append(f"- **{p.name}** (`{p.id}`) — {p.type}, {p.device_type}")
            return "\n".join(lines)
        except Exception as exc:
            return f"Error: {exc}"

    @mcp.resource("fiestaboard://variables")
    def get_variables_resource() -> str:
        """All template variables from enabled plugins."""
        try:
            from .plugins import get_plugin_registry
            registry = get_plugin_registry()
            variables = registry.get_all_variables()
            lines = ["# Available Template Variables\n",
                     "Use these in page templates as `{{plugin.variable}}`.\n"]
            for plugin_id, vars_dict in variables.items():
                lines.append(f"\n## {plugin_id}")
                for var_name, meta in vars_dict.items():
                    desc = meta.get("description", "")
                    example = meta.get("example", "")
                    example_str = f" (e.g. `{example}`)" if example else ""
                    lines.append(f"- `{{{{{plugin_id}.{var_name}}}}}` — {desc}{example_str}")
            return "\n".join(lines)
        except Exception as exc:
            return f"Error: {exc}"

    # -----------------------------------------------------------------------
    # MCP Prompts
    # -----------------------------------------------------------------------

    @mcp.prompt()
    def setup_fiestaboard() -> str:
        """Guide for setting up FiestaBoard from scratch."""
        return (
            "Help me set up FiestaBoard from scratch. Please:\n"
            "1. Start by calling list_installed_plugins() to see what's already installed\n"
            "2. Call list_pages() to see current pages\n"
            "3. Ask me what kind of information I want to display\n"
            "4. Suggest and install appropriate plugins\n"
            "5. Guide me through configuring each plugin with the right API keys / settings\n"
            "6. Create pages using the plugin variables\n"
            "7. Optionally set up a schedule or carousel\n\n"
            "Be conversational and explain what each step does."
        )

    @mcp.prompt()
    def create_display_page(topic: str = "weather") -> str:
        """Create a new display page for a specific topic."""
        return (
            f"Help me create a FiestaBoard display page for: {topic}\n\n"
            "Please:\n"
            "1. Check list_installed_plugins() for relevant plugins\n"
            "2. If needed, suggest installing a plugin and guide me through configuration\n"
            "3. Call get_template_variables() to find the right variable references\n"
            "4. Create a well-designed page with create_page() using those variables\n"
            "5. Offer to schedule the page if appropriate\n\n"
            "Flagship display is 22×6 characters. Use colour tokens like {{yellow}}, "
            "{{white}}, {{green}} to make it visually clear."
        )

    return mcp


# ---------------------------------------------------------------------------
# Module-level singleton — imported by api_server.py
# ---------------------------------------------------------------------------

mcp_server = _build_mcp_server()
