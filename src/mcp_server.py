"""FiestaBoard MCP Server.

Exposes all FiestaBoard management operations as MCP (Model Context Protocol)
tools, enabling external LLMs such as Claude Desktop or Claude Code to control
FiestaBoard via conversation.

Mount point: ``/mcp``  (accessed as ``/api/mcp`` via nginx)

Authentication
--------------
When ``FIESTABOARD_AUTH_ENABLED`` is on, ``/mcp`` accepts either the
session cookie (used by the FiestaBoard web UI) or a pre-shared bearer
token configured via ``FIESTABOARD_MCP_TOKEN`` — set the env var and pass
the value as ``Authorization: Bearer <token>``. A 401 from ``/mcp``
includes ``WWW-Authenticate: Bearer realm="FiestaBoard MCP"`` so MCP
clients send a token rather than attempting OAuth registration.

Connection example for Claude Desktop (``claude_desktop_config.json``).
Desktop only supports stdio servers, so we proxy through ``mcp-remote``.
The trailing slash on the URL avoids a 307 from FastAPI that drops the port::

    {
        "mcpServers": {
            "fiestaboard": {
                "command": "npx",
                "args": [
                    "-y",
                    "mcp-remote",
                    "http://fiestaboard.local:4420/api/mcp/",
                    "--allow-http",
                    "--header",
                    "Authorization: Bearer <FIESTABOARD_MCP_TOKEN>"
                ]
            }
        }
    }

Connection example for Claude Code (talks HTTP directly, no proxy)::

    claude mcp add fiestaboard --transport http \\
        --url http://localhost:4420/api/mcp/ \\
        --header "Authorization: Bearer <FIESTABOARD_MCP_TOKEN>"

See ``docs/setup/MCP_CLIENTS.md`` for the full setup walkthrough,
including why claude.ai web Connectors can't reach a LAN host.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response helpers — every tool returns structured data (dict/list) rather
# than a json.dumps()'d string. FastMCP serializes the return value into
# tool output automatically, so clients get real JSON instead of a JSON
# string that has to be parsed again.
# ---------------------------------------------------------------------------

def _ok(message: str, **fields: Any) -> dict[str, Any]:
    """Standard success envelope for mutation tools."""
    return {"status": "success", "message": message, **fields}


def _err(error: str) -> dict[str, Any]:
    """Standard error envelope. Tools never raise — they return this instead."""
    return {"status": "error", "error": error}


def _serialize(obj: Any) -> Any:
    """Convert Pydantic models / dataclasses / datetimes to JSON-compatible primitives.

    Used when a tool returns Pydantic models (pages, schedules, carousels)
    or dataclasses (settings objects). Plain dicts/lists pass through.
    Falls back to ``__dict__`` for other ad-hoc objects (e.g. SimpleNamespace).
    """
    import dataclasses
    from datetime import date, datetime, time
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _serialize(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, list):
        return [_serialize(x) for x in obj]
    if isinstance(obj, tuple):
        return [_serialize(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (datetime, date, time)):
        return obj.isoformat()
    if hasattr(obj, "__dict__"):
        return {k: _serialize(v) for k, v in vars(obj).items() if not k.startswith("_")}
    return str(obj)

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

    # FastMCP's default transport_security enables DNS-rebinding protection
    # and only allows Host headers matching ``127.0.0.1:*``/``localhost:*``/
    # ``[::1]:*``. FiestaBoard is reached over the LAN by IP, hostname, or
    # ``fiestaboard.local`` — none of which match — so the default would
    # 421 every legitimate request. We opt out and rely on the auth layer
    # (``FIESTABOARD_AUTH_ENABLED``) for access control instead.
    from mcp.server.transport_security import TransportSecuritySettings  # type: ignore[import-untyped]

    mcp = FastMCP(
        "FiestaBoard",
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        ),
        instructions=(
            "FiestaBoard is a smart LED matrix display controller. You can:\n"
            "  • Manage plugins/integrations (weather, stocks, transit, etc.)\n"
            "  • Create and edit display pages using template variables from plugins\n"
            "  • Schedule which page shows at which time of day\n"
            "  • Create carousels that rotate through multiple pages\n\n"
            "TYPICAL WORKFLOW\n"
            "  1. list_installed_plugins() — see what's installed & enabled\n"
            "  2. list_pages() — see current pages\n"
            "  3. get_template_variables() — see what variables plugins expose\n"
            "  4. install/configure plugins as needed\n"
            "  5. render_page_preview() — iterate on a template until it looks right\n"
            "  6. create_page() with template_lines using {{plugin_id.variable_name}} syntax\n"
            "  7. Optionally schedule pages with create_schedule()\n\n"
            "DEBUGGING TOOLS\n"
            "  • render_page_preview(template_lines, device_type) — see how a\n"
            "    template will look WITHOUT creating a page. Use this to iterate.\n"
            "  • get_plugin_data(plugin_id) — see the LIVE values a plugin is\n"
            "    currently exposing. Use this when a page renders '???' or wrong\n"
            "    values; it tells you whether the plugin or the template is at fault.\n\n"
            "DEVICE DIMENSIONS (template_lines length must match exactly)\n"
            "  • flagship: 22 columns × 6 rows\n"
            "  • note:     15 columns × 3 rows\n"
            "  Content longer than the board width is TRUNCATED at render time —\n"
            "  prefer concise variable names, the |wrap filter, or {{= LEFT(...)}}\n"
            "  over letting the engine silently cut text off.\n\n"
            "TEMPLATE SYNTAX\n"
            "  • Variables:  {{plugin_id.variable_name}}  e.g. {{weather.temperature}}\n"
            "  • Colors:     {{red}} {{orange}} {{yellow}} {{green}} {{blue}}\n"
            "                {{violet}} {{purple}} {{white}} {{black}}\n"
            "                Numeric equivalents 63–71 also work ({{63}} = red).\n"
            "                Each color token renders as ONE solid tile (not a\n"
            "                style for following text). Place the token where you\n"
            "                want the dot/indicator to appear.\n"
            "  • Filters:    {{var|upper}} {{var|lower}} {{var|pad:5}} {{var|wrap}}\n"
            "                |wrap lets a long value flow into the empty lines\n"
            "                immediately below it — leave blank lines beneath a\n"
            "                wrapped line for overflow.\n"
            "  • Formulas:   {{= EXPRESSION }} for Excel-like logic.\n"
            "                Functions include: IF, AND, OR, NOT, UPPER, LOWER,\n"
            "                LEFT, RIGHT, LEN, ROUND, FLOOR, CEIL, MIN, MAX, COLOR.\n"
            "                Example: {{= IF(weather.temp_f > 80, \"HOT\", \"OK\")}}\n\n"
            "SAFETY RULES (please follow strictly)\n"
            "  • NEVER guess API keys, tokens, or credentials. If a plugin needs\n"
            "    one, ask the user to provide it before calling configure_plugin().\n"
            "  • Destructive tools (uninstall_plugin, delete_page, delete_schedule,\n"
            "    delete_carousel) cannot be undone — confirm intent with the user\n"
            "    before calling them unless they explicitly requested the deletion.\n"
            "  • Sensitive config values are MASKED as '***' when read back; that\n"
            "    is intentional — do not try to 'restore' or re-send the mask.\n\n"
            "DESIGN TIPS\n"
            "  • Color sparingly. A single {{yellow}} or {{green}} tile as a\n"
            "    status indicator reads better than walls of color.\n"
            "  • Reserve row 1 for a title/label and the last row for time or\n"
            "    context. Use \"\" (empty string) for breathing room and as\n"
            "    overflow space for |wrap.\n\n"
            "Available user-invokable PROMPTS: setup_fiestaboard,\n"
            "create_display_page, schedule_my_day, build_a_carousel,\n"
            "troubleshoot_display."
        ),
    )

    # -----------------------------------------------------------------------
    # Plugin tools
    # -----------------------------------------------------------------------

    @mcp.tool()
    def list_installed_plugins() -> list[dict[str, Any]] | dict[str, Any]:
        """List all installed FiestaBoard plugins with their status and config schema.

        Returns a list of plugin objects. Each includes:
        - id: plugin identifier (use this for other plugin tools)
        - name: display name
        - enabled: whether the plugin is active
        - configured: whether required settings have been filled in
        - description: what the plugin does
        - settings_schema: JSON Schema describing configurable fields
        - config: current configuration (sensitive values masked as '***')
        """
        try:
            from .config_manager import get_config_manager
            from .plugins import get_plugin_registry
            registry = get_plugin_registry()
            cm = get_config_manager()
            plugins = registry.list_plugins()
            for p in plugins:
                cfg = cm.get_plugin_config(p["id"])
                p["config"] = cm._mask_sensitive(cfg) if cfg else {}
                p["configured"] = bool(cfg)
            return _serialize(plugins)
        except Exception as exc:
            return _err(str(exc))

    @mcp.tool()
    def list_registry_plugins() -> list[dict[str, Any]] | dict[str, Any]:
        """List all plugins available to install from the FiestaBoard registry.

        Returns a list. Each entry includes:
        - id: use this as plugin_id when calling install_plugin()
        - name, description, category
        - installed: true if already installed
        """
        try:
            from .plugins import get_plugin_registry
            registry = get_plugin_registry()
            return _serialize(registry.get_registry_entries())
        except Exception as exc:
            return _err(str(exc))

    @mcp.tool()
    def install_plugin(plugin_id: str, auto_enable: bool = True) -> dict[str, Any]:
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
            state = "installed and enabled" if auto_enable else "installed (disabled)"
            return _ok(f"Plugin '{plugin_id}' {state} successfully.",
                       plugin_id=plugin_id, enabled=auto_enable)
        except Exception as exc:
            return _err(f"Error installing plugin '{plugin_id}': {exc}")

    @mcp.tool()
    def enable_plugin(plugin_id: str) -> dict[str, Any]:
        """Enable an installed but currently-disabled plugin.

        Args:
            plugin_id: The plugin identifier (from list_installed_plugins()).
        """
        try:
            from .plugins import get_plugin_registry
            registry = get_plugin_registry()
            registry.enable_plugin(plugin_id)
            return _ok(f"Plugin '{plugin_id}' enabled successfully.", plugin_id=plugin_id)
        except Exception as exc:
            return _err(f"Error enabling plugin '{plugin_id}': {exc}")

    @mcp.tool()
    def disable_plugin(plugin_id: str) -> dict[str, Any]:
        """Disable an installed plugin without uninstalling it.

        The plugin can be re-enabled later with enable_plugin().

        Args:
            plugin_id: The plugin identifier (from list_installed_plugins()).
        """
        try:
            from .plugins import get_plugin_registry
            registry = get_plugin_registry()
            registry.disable_plugin(plugin_id)
            return _ok(f"Plugin '{plugin_id}' disabled successfully.", plugin_id=plugin_id)
        except Exception as exc:
            return _err(f"Error disabling plugin '{plugin_id}': {exc}")

    @mcp.tool()
    def uninstall_plugin(plugin_id: str) -> dict[str, Any]:
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
            return _ok(f"Plugin '{plugin_id}' uninstalled successfully.", plugin_id=plugin_id)
        except Exception as exc:
            return _err(f"Error uninstalling plugin '{plugin_id}': {exc}")

    @mcp.tool()
    def configure_plugin(plugin_id: str, config: dict[str, Any]) -> dict[str, Any]:
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
            from .config_manager import get_config_manager
            from .plugins import get_plugin_registry
            registry = get_plugin_registry()
            cm = get_config_manager()
            existing = cm.get_plugin_config(plugin_id) or {}
            merged = {**existing, **config}
            registry.set_plugin_config(plugin_id, merged)
            updated = cm.get_plugin_config(plugin_id) or {}
            return _ok(
                f"Configuration updated for '{plugin_id}'.",
                plugin_id=plugin_id,
                config=_serialize(cm._mask_sensitive(updated)),
            )
        except Exception as exc:
            return _err(f"Error configuring plugin '{plugin_id}': {exc}")

    @mcp.tool()
    def update_plugin(plugin_id: str) -> dict[str, Any]:
        """Update an installed plugin to its latest registry version.

        Args:
            plugin_id: The plugin identifier (from list_installed_plugins()).
        """
        try:
            from .plugins import get_plugin_registry
            registry = get_plugin_registry()
            registry.reload_plugin(plugin_id)
            return _ok(f"Plugin '{plugin_id}' updated successfully.", plugin_id=plugin_id)
        except Exception as exc:
            return _err(f"Error updating plugin '{plugin_id}': {exc}")

    @mcp.tool()
    def get_template_variables() -> dict[str, Any]:
        """Get all template variables available from enabled plugins.

        Returns a nested object: {plugin_id: {variable_name: {description, example, max_length}}}.
        Use these variables in page templates as {{plugin_id.variable_name}}.

        Example: {{weather.temperature}}, {{stocks.price}}, {{date_time.time_12h}}
        """
        try:
            from .plugins import get_plugin_registry
            registry = get_plugin_registry()
            return _serialize(registry.get_all_variables())
        except Exception as exc:
            return _err(str(exc))

    @mcp.tool()
    def get_plugin_data(plugin_id: str) -> dict[str, Any]:
        """Fetch the CURRENT live values a plugin is exposing to template variables.

        Use this when debugging a page that renders unexpectedly — e.g. a value
        shows as '???' or the wrong number. The returned dict is exactly what
        the template engine sees when substituting {{plugin_id.variable_name}}.

        Args:
            plugin_id: The plugin identifier (from list_installed_plugins()).

        Returns: {"available": bool, "data": {...}, "error": "..."}
        If the plugin is disabled or not configured, 'available' is false and
        'error' explains why; no exception is raised. Cached values may be
        returned if the plugin's refresh interval hasn't elapsed.
        """
        try:
            from .plugins import get_plugin_registry
            registry = get_plugin_registry()
            result = registry.fetch_plugin_data(plugin_id)
            return {
                "available": result.available,
                "data": _serialize(result.data),
                "error": result.error,
            }
        except Exception as exc:
            return _err(str(exc))

    # -----------------------------------------------------------------------
    # Page tools
    # -----------------------------------------------------------------------

    @mcp.tool()
    def list_pages() -> list[dict[str, Any]] | dict[str, Any]:
        """List all display pages on this FiestaBoard.

        Returns a list of page objects with:
        - id: use this for get_page(), update_page(), delete_page(), schedules
        - name: display name
        - type: 'template' (dynamic content), 'single', or 'composite'
        - device_type: 'flagship' or 'note'
        - duration_seconds: how long to show the page in carousels
        """
        try:
            from .pages.service import get_page_service
            svc = get_page_service()
            return _serialize(svc.list_pages())
        except Exception as exc:
            return _err(str(exc))

    @mcp.tool()
    def get_page(page_id: str) -> dict[str, Any]:
        """Get full details of a specific page including its template content.

        Args:
            page_id: The page identifier (from list_pages()).

        Returns all page fields including the template array. Each template
        line can contain {{plugin.variable}} references and {{color}} tokens
        like {{red}}, {{green}}, {{white}} etc.
        """
        try:
            from .pages.service import get_page_service
            svc = get_page_service()
            page = svc.get_page(page_id)
            if page is None:
                return _err(f"Page '{page_id}' not found.")
            return _serialize(page)
        except Exception as exc:
            return _err(str(exc))

    @mcp.tool()
    def create_page(
        name: str,
        template_lines: list[str],
        device_type: str = "flagship",
        duration_seconds: int = 300,
    ) -> dict[str, Any]:
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
            from .pages.models import PageCreate
            from .pages.service import get_page_service
            svc = get_page_service()
            data = PageCreate(
                name=name,
                type="template",
                device_type=device_type,  # type: ignore[arg-type]
                template=template_lines,
                duration_seconds=duration_seconds,
            )
            page = svc.create_page(data)
            return _ok(
                f"Page '{name}' created with id '{page.id}'.",
                page_id=page.id,
                name=page.name,
            )
        except Exception as exc:
            return _err(f"Error creating page: {exc}")

    @mcp.tool()
    def update_page(
        page_id: str,
        name: str | None = None,
        template_lines: list[str] | None = None,
        duration_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Update an existing page's name, template content, or duration.

        Args:
            page_id: The page identifier (from list_pages()).
            name: New display name (optional).
            template_lines: New template content (optional). Replaces all lines.
            duration_seconds: New carousel duration in seconds (optional).
        """
        try:
            from .pages.models import PageUpdate
            from .pages.service import get_page_service
            svc = get_page_service()
            data = PageUpdate(
                name=name,
                template=template_lines,
                duration_seconds=duration_seconds,
            )
            page = svc.update_page(page_id, data)
            if page is None:
                return _err(f"Page '{page_id}' not found.")
            return _ok(f"Page '{page_id}' updated.", page_id=page.id, name=page.name)
        except Exception as exc:
            return _err(f"Error updating page '{page_id}': {exc}")

    @mcp.tool()
    def delete_page(page_id: str) -> dict[str, Any]:
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
                return _err(f"Error deleting page: {result.message}")
            return _ok(f"Page '{page_id}' deleted successfully.", page_id=page_id)
        except Exception as exc:
            return _err(f"Error deleting page '{page_id}': {exc}")

    @mcp.tool()
    def render_page_preview(
        template_lines: list[str],
        device_type: str = "flagship",
    ) -> dict[str, Any]:
        """Render a template to see how it will look BEFORE saving it as a page.

        Use this to iterate on a design without creating (and then having to
        delete) throwaway pages. Substitutes live plugin values into the
        template just like the real renderer would, then returns the resulting
        grid with newlines between rows.

        Args:
            template_lines: Template strings to render (one per row). Extra
                            rows are dropped; missing rows are filled with blanks.
            device_type: 'flagship' (22×6) or 'note' (15×3).

        Returns:
            {
              "rendered": "<grid string with \\n between rows>",
              "device_type": "flagship",
              "context_plugins": ["weather", "date_time", ...]
            }
        Unresolved variables render as "???" — that's a sign of a typo or a
        plugin that's disabled/unconfigured. Lines longer than the board width
        will appear truncated in the output, matching real-device behavior.
        """
        try:
            from .templates.engine import get_template_engine
            engine = get_template_engine()
            context = engine._build_context()
            rendered = engine.render_lines(
                template_lines,
                context=context,
                device_type=device_type,
            )
            return {
                "rendered": rendered,
                "device_type": device_type,
                "context_plugins": sorted(context.keys()),
            }
        except Exception as exc:
            return _err(str(exc))

    # -----------------------------------------------------------------------
    # Schedule tools
    # -----------------------------------------------------------------------

    @mcp.tool()
    def list_schedules() -> list[dict[str, Any]] | dict[str, Any]:
        """List all scheduled time slots for page display.

        Returns a list of schedule entries with:
        - id: use this for update_schedule(), delete_schedule()
        - page_id: which page to show
        - start_time / end_time: HH:MM format (24h). end_time null = runs until next schedule.
        - day_pattern: 'all', 'weekdays', 'weekends', or 'custom'
        - enabled: whether the schedule entry is active
        """
        try:
            from .schedules.service import get_schedule_service
            svc = get_schedule_service()
            return _serialize(svc.list_schedules())
        except Exception as exc:
            return _err(str(exc))

    @mcp.tool()
    def create_schedule(
        page_id: str,
        start_time: str,
        day_pattern: str = "all",
        end_time: str | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
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
            from .schedules.models import ScheduleCreate
            from .schedules.service import get_schedule_service
            svc = get_schedule_service()
            data = ScheduleCreate(
                page_id=page_id,
                start_time=start_time,
                end_time=end_time,
                day_pattern=day_pattern,  # type: ignore[arg-type]
                enabled=enabled,
            )
            entry = svc.create_schedule(data)
            return _ok(
                f"Schedule created: page '{page_id}' from {start_time} on {day_pattern} days.",
                schedule_id=entry.id,
            )
        except Exception as exc:
            return _err(f"Error creating schedule: {exc}")

    @mcp.tool()
    def update_schedule(
        schedule_id: str,
        page_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        day_pattern: str | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any]:
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
            from .schedules.models import ScheduleUpdate
            from .schedules.service import get_schedule_service
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
                return _err(f"Schedule '{schedule_id}' not found.")
            return _ok(f"Schedule '{schedule_id}' updated.", schedule_id=entry.id)
        except Exception as exc:
            return _err(f"Error updating schedule '{schedule_id}': {exc}")

    @mcp.tool()
    def delete_schedule(schedule_id: str) -> dict[str, Any]:
        """Delete a schedule entry permanently.

        Args:
            schedule_id: The schedule identifier (from list_schedules()).
        """
        try:
            from .schedules.service import get_schedule_service
            svc = get_schedule_service()
            svc.delete_schedule(schedule_id)
            return _ok(f"Schedule '{schedule_id}' deleted successfully.", schedule_id=schedule_id)
        except Exception as exc:
            return _err(f"Error deleting schedule '{schedule_id}': {exc}")

    # -----------------------------------------------------------------------
    # Carousel tools
    # -----------------------------------------------------------------------

    @mcp.tool()
    def list_carousels() -> list[dict[str, Any]] | dict[str, Any]:
        """List all carousels (playlists that rotate between multiple pages).

        Returns a list with:
        - id: use this for update_carousel(), delete_carousel(), or as page_id in schedules
        - name, page_ids, interval_seconds
        """
        try:
            from .carousels.service import get_carousel_service
            svc = get_carousel_service()
            return _serialize(svc.list_carousels())
        except Exception as exc:
            return _err(str(exc))

    @mcp.tool()
    def create_carousel(
        name: str,
        page_ids: list[str],
        interval_seconds: int = 30,
    ) -> dict[str, Any]:
        """Create a carousel that rotates through multiple pages.

        The carousel ID can be used as the page_id in create_schedule() to
        schedule the whole playlist at a specific time of day.

        Args:
            name: Display name for the carousel.
            page_ids: Ordered list of page IDs to rotate through.
            interval_seconds: How long to show each page (default: 30). Range: 5–3600.
        """
        try:
            from .carousels.models import CarouselCreate
            from .carousels.service import get_carousel_service
            svc = get_carousel_service()
            data = CarouselCreate(
                name=name,
                page_ids=page_ids,
                interval_seconds=interval_seconds,
            )
            carousel = svc.create_carousel(data)
            return _ok(
                f"Carousel '{name}' created with {len(page_ids)} pages.",
                carousel_id=carousel.id,
                name=carousel.name,
            )
        except Exception as exc:
            return _err(f"Error creating carousel: {exc}")

    @mcp.tool()
    def update_carousel(
        carousel_id: str,
        name: str | None = None,
        page_ids: list[str] | None = None,
        interval_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Update an existing carousel's name, page list, or rotation interval.

        Args:
            carousel_id: The carousel identifier (from list_carousels()).
            name: New name (optional).
            page_ids: New ordered list of page IDs (optional). Replaces entire list.
            interval_seconds: New rotation interval in seconds (optional).
        """
        try:
            from .carousels.models import CarouselUpdate
            from .carousels.service import get_carousel_service
            svc = get_carousel_service()
            data = CarouselUpdate(
                name=name,
                page_ids=page_ids,
                interval_seconds=interval_seconds,
            )
            carousel = svc.update_carousel(carousel_id, data)
            if carousel is None:
                return _err(f"Carousel '{carousel_id}' not found.")
            return _ok(f"Carousel '{carousel_id}' updated.", carousel_id=carousel.id)
        except Exception as exc:
            return _err(f"Error updating carousel '{carousel_id}': {exc}")

    @mcp.tool()
    def delete_carousel(carousel_id: str) -> dict[str, Any]:
        """Delete a carousel permanently.

        Args:
            carousel_id: The carousel identifier (from list_carousels()).
        """
        try:
            from .carousels.service import get_carousel_service
            svc = get_carousel_service()
            svc.delete_carousel(carousel_id)
            return _ok(f"Carousel '{carousel_id}' deleted successfully.", carousel_id=carousel_id)
        except Exception as exc:
            return _err(f"Error deleting carousel '{carousel_id}': {exc}")

    # -----------------------------------------------------------------------
    # System tools
    # -----------------------------------------------------------------------

    @mcp.tool()
    def get_system_status() -> dict[str, Any]:
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
            return {
                "version": __version__,
                "service_running": _service_running and service is not None,
                "plugin_system_available": True,
                "plugins_installed": len(plugins),
                "plugins_enabled": sum(1 for p in plugins if p.get("enabled")),
            }
        except Exception as exc:
            return _err(str(exc))

    @mcp.tool()
    def get_settings_summary() -> dict[str, Any]:
        """Get a summary of current FiestaBoard settings (non-sensitive fields only).

        Returns display, output, location, and schedule settings.
        AI provider credentials and board API keys are intentionally excluded.
        """
        try:
            from .settings.service import get_settings_service
            svc = get_settings_service()
            summary: dict[str, Any] = {}
            for key, fetch in (
                ("display", svc.get_display_settings),
                ("location", svc.get_location_settings),
                ("output", svc.get_output_settings),
            ):
                try:
                    summary[key] = _serialize(fetch())
                except Exception as exc:
                    logger.debug(
                        "get_settings_summary: could not fetch %s settings: %s",
                        key, exc,
                    )
            return summary
        except Exception as exc:
            return _err(str(exc))

    @mcp.tool()
    def set_active_page(page_id: str) -> dict[str, Any]:
        """Set which page is currently shown on the FiestaBoard display.

        This immediately changes what's visible on the board.

        Args:
            page_id: The page or carousel ID to display (from list_pages() or list_carousels()).
        """
        try:
            from .config_manager import get_config_manager
            cm = get_config_manager()
            cm.set_active_page(page_id)
            return _ok(f"Active page set to '{page_id}'.", page_id=page_id)
        except Exception as exc:
            return _err(f"Error setting active page: {exc}")

    @mcp.tool()
    def set_schedule_mode(enabled: bool) -> dict[str, Any]:
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
            return _ok(f"Schedule mode {state}.", enabled=enabled)
        except Exception as exc:
            return _err(f"Error setting schedule mode: {exc}")

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

    @mcp.resource("fiestaboard://page/{page_id}/preview.html", mime_type="text/html")
    def get_page_preview_html(page_id: str) -> str:
        """Self-contained HTML preview of a page rendered as a board.

        Useful for MCP-UI clients that want to fetch a board preview by
        page id without going through the page tools.
        """
        try:
            from .board_html_renderer import render_page_preview_html
            from .pages.service import get_page_service
            svc = get_page_service()
            page = svc.get_page(page_id)
            if page is None:
                return (
                    "<!DOCTYPE html><html><body><p>Page "
                    f"<code>{page_id}</code> not found.</p></body></html>"
                )
            return render_page_preview_html(page)
        except Exception as exc:
            return f"<!DOCTYPE html><html><body><p>Error: {exc}</p></body></html>"

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

    @mcp.resource("fiestaboard://schedules")
    def get_schedules_resource() -> str:
        """Live list of all scheduled time slots."""
        try:
            from .schedules.service import get_schedule_service
            svc = get_schedule_service()
            schedules = svc.list_schedules()
            lines = [f"# Schedules ({len(schedules)} total)\n"]
            for s in schedules:
                status = "✓ enabled" if getattr(s, "enabled", True) else "✗ disabled"
                end = getattr(s, "end_time", None) or "open"
                lines.append(
                    f"- **{s.start_time}–{end}** on {s.day_pattern} "
                    f"→ page `{s.page_id}` ({status}) [`{s.id}`]"
                )
            return "\n".join(lines)
        except Exception as exc:
            return f"Error: {exc}"

    @mcp.resource("fiestaboard://carousels")
    def get_carousels_resource() -> str:
        """Live list of all carousels (page playlists)."""
        try:
            from .carousels.service import get_carousel_service
            svc = get_carousel_service()
            carousels = svc.list_carousels()
            lines = [f"# Carousels ({len(carousels)} total)\n"]
            for c in carousels:
                page_count = len(getattr(c, "page_ids", []) or [])
                interval = getattr(c, "interval_seconds", "?")
                lines.append(
                    f"- **{c.name}** (`{c.id}`) — {page_count} pages, "
                    f"{interval}s per page"
                )
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

    @mcp.prompt()
    def schedule_my_day() -> str:
        """Build a time-of-day schedule that rotates pages through the day."""
        return (
            "Help me set up a daily display schedule on FiestaBoard. Please:\n"
            "1. Call list_pages() and list_carousels() so we know what content exists\n"
            "2. Ask me about the rhythm of my day — morning routine, work hours,\n"
            "   evening, overnight — and what I'd want to see at each\n"
            "3. If a useful page is missing, offer to create it before scheduling\n"
            "4. Call list_schedules() to see what's already configured so we don't\n"
            "   clobber existing entries\n"
            "5. Use create_schedule() for each time slot (HH:MM, 24-hour). Remember:\n"
            "   end_time=None means 'runs until the next schedule', which is usually\n"
            "   what you want for a chain of slots covering the day\n"
            "6. After creating, call set_schedule_mode(enabled=True) so the schedule\n"
            "   actually takes effect\n"
            "7. Summarise the final schedule back to me\n\n"
            "Day patterns available: 'all', 'weekdays', 'weekends', 'custom'."
        )

    @mcp.prompt()
    def build_a_carousel() -> str:
        """Build a carousel (playlist) that rotates between multiple pages."""
        return (
            "Help me build a FiestaBoard carousel — a playlist that cycles through\n"
            "several pages on a timer. Please:\n"
            "1. Call list_pages() and show me the candidates with their device_type\n"
            "2. Ask which pages I want in the rotation and in what order\n"
            "   (all pages in one carousel must share the same device_type)\n"
            "3. Ask how long each page should stay up — typical values are\n"
            "   15–60 seconds; the allowed range is 5–3600\n"
            "4. Call create_carousel() with the ordered page_ids\n"
            "5. Offer to either:\n"
            "     a) set the carousel as the active page now via set_active_page(),\n"
            "        OR\n"
            "     b) schedule it for specific time slots via create_schedule()\n"
            "        (a carousel id can be used anywhere a page id is accepted)\n"
            "6. Confirm what's now showing and what's scheduled."
        )

    @mcp.prompt()
    def troubleshoot_display() -> str:
        """Diagnose a blank, frozen, or visually broken FiestaBoard display."""
        return (
            "Help me figure out why my FiestaBoard isn't showing what I expect.\n"
            "Please walk through diagnosis in this order and SHOW your findings\n"
            "at each step before moving on:\n\n"
            "1. get_system_status() — is the display service actually running?\n"
            "   If service_running is false, that's the headline issue.\n"
            "2. Ask the user: what do you currently see? (blank, wrong page,\n"
            "   garbled text, frozen, all one color, etc.) Use that to narrow down.\n"
            "3. list_schedules() + get_settings_summary() — if schedule mode is on,\n"
            "   work out which schedule entry SHOULD be active right now given the\n"
            "   current time and day pattern. A common gotcha: schedule mode is off\n"
            "   so the board is stuck on a fixed active page.\n"
            "4. For the page that *should* be showing, call get_page(page_id) and\n"
            "   inspect the template lines for:\n"
            "     • Wrong device_type vs what's actually plugged in\n"
            "     • Lines longer than the board width (will be truncated)\n"
            "     • Variables referencing plugins that aren't enabled — cross-check\n"
            "       against list_installed_plugins() and get_template_variables()\n"
            "     • Typos like {{weather.temp}} when the variable is {{weather.temperature}}\n"
            "     • Plugins that are enabled but not configured (configured: false)\n"
            "5. If everything looks right but the board still misbehaves, suggest\n"
            "   the user try /restart on the container.\n\n"
            "Report findings as: 'Likely cause: X. Evidence: Y. Suggested fix: Z.'"
        )

    return mcp


# ---------------------------------------------------------------------------
# Module-level singleton — imported by api_server.py
# ---------------------------------------------------------------------------

mcp_server = _build_mcp_server()
