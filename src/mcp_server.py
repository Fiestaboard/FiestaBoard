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

import functools
import inspect
import logging
from typing import Annotated, Any

from pydantic import Field

# Mutating tools dispatch into the shared operation layer (#1764); the
# result envelopes live there too, so executors and the read-only tools
# that remain here return identical shapes. Every tool returns structured
# data (dict/list) rather than a json.dumps()'d string — FastMCP
# serializes the return value into tool output automatically, so clients
# get real JSON instead of a JSON string that has to be parsed again.
from .ops import executors as ops_executors
from .ops import teaching as ops_teaching
from .ops.results import serialize as _serialize

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy imports — the MCP package is optional; we log a warning if missing
# rather than crashing the whole API server on import.
# ---------------------------------------------------------------------------

try:
    from mcp.server import MCPServer  # type: ignore[import-untyped]
    from mcp.server.mcpserver.exceptions import ToolError  # type: ignore[import-untyped]

    _MCP_AVAILABLE = True
except ImportError:  # pragma: no cover
    _MCP_AVAILABLE = False
    MCPServer = None  # type: ignore[assignment,misc]
    ToolError = None  # type: ignore[assignment,misc]
    logger.warning(
        "mcp package not installed — FiestaBoard MCP server is disabled. "
        "Add `mcp>=2.0.0` to requirements.txt and rebuild the container."
    )


def _boards_summary(settings_service: Any) -> list[dict[str, Any]]:
    """Per-board roster for ``get_settings_summary`` (#1765).

    An explicit field projection, never the raw board dicts — those carry
    credentials (host, API keys, note-array tokens) that must not cross the
    MCP boundary even masked. ``error`` is the #1813 per-board init failure,
    read defensively off the engine service when one exists.
    """
    from .devices import resolve_dimensions

    init_errors: dict[str, str] = {}
    try:
        # peek, never create: a read-only summary must not boot the engine.
        from .api_server import peek_service

        engine = peek_service()
        maybe = getattr(engine, "board_init_errors", None)
        if isinstance(maybe, dict):
            init_errors = maybe
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("get_settings_summary: could not read board init errors: %s", exc)

    boards_out: list[dict[str, Any]] = []
    try:
        boards = settings_service.get_board_settings().boards or []
        primary_id = settings_service.get_primary_board_id()
    except Exception as exc:
        logger.debug("get_settings_summary: could not read boards list: %s", exc)
        return boards_out

    for board in boards:
        if not isinstance(board, dict) or not board.get("id"):
            continue
        bid = board["id"]
        rows = cols = None
        try:
            dims = resolve_dimensions(
                board.get("device_type") or "flagship",
                board.get("notes_wide") or 1,
                board.get("notes_tall") or 1,
            )
            rows, cols = dims.rows, dims.cols
        except Exception as exc:
            logger.debug("get_settings_summary: could not resolve dims for board %s: %s", bid, exc)
        try:
            active_page_id = settings_service.get_active_page_id(board_id=bid)
        except Exception:
            active_page_id = None
        if not isinstance(active_page_id, str):
            active_page_id = None
        error = init_errors.get(bid)
        boards_out.append(
            {
                "id": bid,
                "name": board.get("name", ""),
                "device_type": board.get("device_type", "flagship"),
                "rows": rows,
                "cols": cols,
                "notes_wide": board.get("notes_wide", 1),
                "notes_tall": board.get("notes_tall", 1),
                "primary": bid == primary_id,
                "enabled": bool(board.get("enabled", True)),
                "paused": bool(board.get("paused", False)),
                "schedule_enabled": bool(board.get("schedule_enabled", False)),
                "active_page_id": active_page_id,
                "error": error if isinstance(error, str) else None,
            }
        )
    return boards_out


def _tool_failure(tool_name: str, exc: Exception) -> Exception:
    """Map an unexpected exception to a concise protocol error (#1765).

    The full traceback goes to the server log; the wire gets a one-line
    message naming the tool and the exception class but no internal detail
    — raw exception text routinely carries paths, config values, and other
    things an MCP client has no business seeing.
    """
    logger.exception("MCP tool %s failed", tool_name)
    return ToolError(f"{tool_name} failed unexpectedly ({type(exc).__name__}); details are in the server log.")


def _raise_error_envelope(result: Any) -> Any:
    """Turn an executor ``{"status": "error"}`` envelope into a ToolError.

    The ops executors never raise (their envelope contract predates #1765
    and the chat grammar still consumes it); at the MCP boundary the
    envelope becomes a raised ToolError so the framework answers with
    ``CallToolResult(isError=True)`` carrying the executor's own
    domain-worded message. Success and policy-"blocked" payloads pass
    through unchanged.
    """
    if isinstance(result, dict) and result.get("status") == "error":
        message = str(result.get("error") or "The operation failed.")
        logger.info("MCP tool error: %s", message)
        raise ToolError(message)
    return result


def _build_mcp_server() -> Any:
    """Construct and return the MCPServer instance.

    Returns ``None`` if the ``mcp`` package is not installed.  Transport
    configuration (stateless HTTP, JSON responses, security) lives in
    :func:`build_streamable_http_app` — mcp 2.0 moved it off the server
    constructor onto the app builders.
    """
    if not _MCP_AVAILABLE:
        return None

    mcp = MCPServer(
        "FiestaBoard",
        instructions=(
            "FiestaBoard is a smart LED matrix display controller. You can:\n"
            "  • Manage plugins/integrations (weather, stocks, transit, etc.)\n"
            "  • Create and edit display pages using template variables from plugins\n"
            "  • Schedule which page shows at which time of day\n"
            "  • Create collections that group pages and decide which one shows\n\n"
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
            "MULTI-BOARD\n"
            "  An install can drive several boards. get_settings_summary() returns\n"
            "  a boards list (id, name, device_type, rows/cols, active page, error).\n"
            "  Board-targeting tools take an optional board_id — omitted always\n"
            "  means the primary board. When working against a specific board, use\n"
            "  ITS device_type and dimensions, not the primary's.\n\n"
            # Board-dimensions and template-syntax teaching is GENERATED from
            # the defining modules (#1764) — the previous hardcoded copy had
            # rotted (nonexistent |upper/|lower filters, a 63–71 color range,
            # a frozen 15-function formula roster).
            + ops_teaching.device_dimensions_block()
            + "\n\n"
            + ops_teaching.template_syntax_block()
            + "\n\n"
            "SAFETY RULES (please follow strictly)\n"
            "  • NEVER guess API keys, tokens, or credentials. If a plugin needs\n"
            "    one, ask the user to provide it before calling configure_plugin().\n"
            "  • Destructive tools (uninstall_plugin, delete_page, delete_schedule,\n"
            "    delete_collection) cannot be undone — confirm intent with the user\n"
            "    before calling them unless they explicitly requested the deletion.\n"
            "  • Sensitive config values are MASKED as '***' when read back; that\n"
            "    is intentional — do not try to 'restore' or re-send the mask.\n\n"
            "DESIGN TIPS\n"
            "  • Color sparingly. A single {{yellow}} or {{green}} tile as a\n"
            "    status indicator reads better than walls of color.\n"
            "  • Reserve row 1 for a title/label and the last row for time or\n"
            '    context. Use "" (empty string) for breathing room and as\n'
            "    overflow space for |wrap.\n\n"
            "Available user-invokable PROMPTS: setup_fiestaboard,\n"
            "create_display_page, schedule_my_day, build_a_collection,\n"
            "troubleshoot_display."
        ),
    )

    # Every tool registers through this wrapper: the #1765 error contract in
    # one place. Executor error envelopes become raised ToolErrors (protocol
    # isError=True with the domain message); unexpected exceptions are logged
    # server-side with their traceback and mapped to a concise message. A
    # ToolError raised by a tool body passes through untouched.
    def _tool(fn: Any) -> Any:
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    result = await fn(*args, **kwargs)
                except ToolError:
                    raise
                except Exception as exc:
                    raise _tool_failure(fn.__name__, exc) from exc
                return _raise_error_envelope(result)

        else:

            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    result = fn(*args, **kwargs)
                except ToolError:
                    raise
                except Exception as exc:
                    raise _tool_failure(fn.__name__, exc) from exc
                return _raise_error_envelope(result)

        return mcp.tool()(wrapper)

    # -----------------------------------------------------------------------
    # Plugin tools
    #
    # The mutating ones dispatch into the operation layer (#1764) —
    # ``src.ops.executors`` — which delegates to ``PluginService`` (#1757),
    # the same orchestration the REST handlers use, rather than driving
    # ``PluginRegistry`` directly. Enabling or configuring a plugin is two
    # writes, not one: the registry holds the live state, ConfigManager holds
    # ``config.json``. #1588 is what going straight to the registry costs —
    # every setting made over MCP looked fine until the container was
    # recreated, then came back gone, because nothing had ever been written
    # to disk. Going through the service (not ``api_server``'s handlers) is
    # what keeps mcp_server importable without api_server.
    # -----------------------------------------------------------------------

    @_tool
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

    @_tool
    def list_registry_plugins(
        page: int = 1,
        page_size: int = 20,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """List plugins available to install from the FiestaBoard registry (paginated).

        Each entry includes id (use it as plugin_id for install_plugin()),
        name, description, category, plugin_type, and installed. The
        board-preview fields (teaser, previews) are omitted by default —
        they are large literal board grids; opt in via fields when you
        actually need to show what a plugin looks like on a board.

        Args:
            page: 1-based page number (default 1).
            page_size: Entries per page, 1-100 (default 20).
            fields: Optional exact projection — each entry then carries only
                    these fields plus id (e.g. ["name", "previews"]).

        Returns: {plugins: [...], total, page, page_size, total_pages}.
        """
        from .plugins import get_plugin_registry

        if page < 1:
            raise ToolError("page must be >= 1")
        if not 1 <= page_size <= 100:
            raise ToolError("page_size must be between 1 and 100")

        entries = _serialize(get_plugin_registry().get_registry_entries())

        if fields is not None:
            known = {key for entry in entries for key in entry}
            unknown = sorted(set(fields) - known)
            if entries and unknown:
                raise ToolError(f"Unknown fields: {', '.join(unknown)}. Valid fields: {', '.join(sorted(known))}")
            keep = set(fields) | {"id"}

            def project(entry: dict[str, Any]) -> dict[str, Any]:
                return {k: v for k, v in entry.items() if k in keep}

        else:
            # Default projection: everything except the fat preview grids
            # (#1765 audit finding 4 — they made this response ~33KB).
            def project(entry: dict[str, Any]) -> dict[str, Any]:
                return {k: v for k, v in entry.items() if k not in ("teaser", "previews")}

        total = len(entries)
        start = (page - 1) * page_size
        return {
            "plugins": [project(e) for e in entries[start : start + page_size]],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, -(-total // page_size)),
        }

    @_tool
    async def install_plugin(plugin_id: str, auto_enable: bool = True) -> dict[str, Any]:
        """Install a plugin from the official FiestaBoard registry and optionally enable it.

        Args:
            plugin_id: The plugin identifier from list_registry_plugins() (e.g. 'openweather').
            auto_enable: Whether to enable the plugin after installation (default: True).

        After installing, use configure_plugin() to set API keys and other settings.
        Use get_template_variables() to discover the variables the plugin exposes.
        """
        return await ops_executors.install_plugin(plugin_id, auto_enable=auto_enable)

    @_tool
    async def enable_plugin(plugin_id: str) -> dict[str, Any]:
        """Enable an installed but currently-disabled plugin.

        The plugin must already be installed — use install_plugin() first for
        anything from list_registry_plugins().

        Args:
            plugin_id: The plugin identifier (from list_installed_plugins()).
        """
        return ops_executors.enable_plugin(plugin_id)

    @_tool
    async def disable_plugin(plugin_id: str) -> dict[str, Any]:
        """Disable an installed plugin without uninstalling it.

        The plugin can be re-enabled later with enable_plugin().

        Args:
            plugin_id: The plugin identifier (from list_installed_plugins()).
        """
        return ops_executors.disable_plugin(plugin_id)

    @_tool
    async def uninstall_plugin(plugin_id: str) -> dict[str, Any]:
        """Permanently remove an installed plugin.

        WARNING: This is irreversible. The plugin and all its configuration
        will be deleted. Only external/registry plugins can be uninstalled;
        built-in plugins cannot be removed.

        Args:
            plugin_id: The plugin identifier (from list_installed_plugins()).
        """
        return ops_executors.uninstall_plugin(plugin_id)

    @_tool
    async def configure_plugin(plugin_id: str, config: dict[str, Any]) -> dict[str, Any]:
        """Update configuration settings for an installed plugin.

        Use list_installed_plugins() to see the settings_schema for a plugin,
        which shows all valid config keys, their types, and which are required.

        Settings are merged into the plugin's existing configuration and saved
        to disk, so they survive a restart. A config the plugin rejects is
        reported as an error and nothing is saved.

        IMPORTANT: Never guess API keys — only set values the user has provided.
        Sensitive fields (api_key, password, etc.) must be provided explicitly.

        Args:
            plugin_id: The plugin identifier.
            config: Dictionary of configuration key-value pairs to update.
                    Only include keys you want to change.
        """
        return ops_executors.configure_plugin(plugin_id, config)

    @_tool
    async def update_plugin(plugin_id: str) -> dict[str, Any]:
        """Update an installed plugin to its latest version from its git remote.

        Built-in plugins cannot be updated this way.

        Args:
            plugin_id: The plugin identifier (from list_installed_plugins()).
        """
        # #1741 lives on in the executor: updates go through
        # PluginService.apply_update — the shared, guarded path.
        return await ops_executors.update_plugin(plugin_id)

    @_tool
    def get_template_variables() -> dict[str, Any]:
        """Get all template variables available from enabled plugins.

        Returns a nested object: {plugin_id: {variable_name: {description, example, max_length}}}.
        Use these variables in page templates as {{plugin_id.variable_name}}.

        Example: {{weather.temperature}}, {{stocks.price}}, {{date_time.time_12h}}
        """
        from .plugins import get_plugin_registry

        registry = get_plugin_registry()
        # #1739: get_all_variables() returns {plugin: [name, ...]}, not the
        # nested metadata this tool documents. GET /templates/variables
        # already uses the *_with_metadata variant; this call site drifted.
        return _serialize(registry.get_all_variables_with_metadata())

    @_tool
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
        from .plugins import get_plugin_registry

        registry = get_plugin_registry()
        result = registry.fetch_plugin_data(plugin_id)
        return {
            "available": result.available,
            "data": _serialize(result.data),
            "error": result.error,
        }

    # -----------------------------------------------------------------------
    # Page tools
    # -----------------------------------------------------------------------

    @_tool
    def list_pages() -> list[dict[str, Any]] | dict[str, Any]:
        """List all display pages on this FiestaBoard.

        Returns a list of page objects with:
        - id: use this for get_page(), update_page(), delete_page(), schedules
        - name: display name
        - type: 'template' (dynamic content), 'single', or 'composite'
        - device_type: 'flagship' or 'note'
        - duration_seconds: how long to show the page in time-mode collections
        """
        from .pages.service import get_page_service

        svc = get_page_service()
        return _serialize(svc.list_pages())

    @_tool
    def get_page(page_id: str) -> dict[str, Any]:
        """Get full details of a specific page including its template content.

        Args:
            page_id: The page identifier (from list_pages()).

        Returns all page fields including the template array. Each template
        line can contain {{plugin.variable}} references and {{color}} tokens
        like {{red}}, {{green}}, {{white}} etc.
        """
        from .pages.service import get_page_service

        svc = get_page_service()
        page = svc.get_page(page_id)
        if page is None:
            raise ToolError(f"Page '{page_id}' not found.")
        return _serialize(page)

    @_tool
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
            duration_seconds: How long to show this page in a time-mode collection (default: 300).

        Example template_lines for a weather page:
            ["{{white}}{{= UPPER(weather.city)}}", "{{yellow}}{{weather.temperature}}°F",
             "{{weather.condition}}", "", "{{date_time.time_12h}}", "{{date_time.date_short}}"]
        """
        return ops_executors.create_page(
            name=name,
            template_lines=template_lines,
            device_type=device_type,
            duration_seconds=duration_seconds,
        )

    @_tool
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
            duration_seconds: New time-mode duration in seconds (optional).
        """
        return ops_executors.update_page(
            page_id,
            name=name,
            template_lines=template_lines,
            duration_seconds=duration_seconds,
        )

    @_tool
    def delete_page(page_id: str) -> dict[str, Any]:
        """Delete a page permanently.

        WARNING: This cannot be undone. If this is the last page, a default
        welcome page will be created automatically.

        Args:
            page_id: The page identifier (from list_pages()).
        """
        return ops_executors.delete_page(page_id)

    @_tool
    def render_page_preview(
        template_lines: list[str],
        device_type: str = "flagship",
        line_metadata: list[dict[str, Any]] | None = None,
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
            line_metadata: Optional per-line dicts with "alignment"
                           ('left'/'center'/'right') and "wrap" (bool) — the
                           same metadata saved pages carry. Include it to
                           preview alignment and wrap faithfully.

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
        from .devices import DEFAULT_DEVICE_TYPE, BoardContext, resolve_dimensions
        from .templates.engine import get_template_engine

        engine = get_template_engine()
        # Build the plugin context around the real BoardContext — the same
        # construction render_lines performs internally and the saved-page
        # render path (PageService._render_template) relies on — so
        # board-aware plugins see the true geometry. The pre-#1765 call
        # passed no board at all, and every plugin previewed board-blind.
        # Unknown device types fall back to the default, matching
        # render_lines' own never-crash fallback.
        render_device_type = device_type or DEFAULT_DEVICE_TYPE
        try:
            dims = resolve_dimensions(render_device_type)
        except ValueError:
            render_device_type = DEFAULT_DEVICE_TYPE
            dims = resolve_dimensions(render_device_type)
        context = engine._build_context(BoardContext(render_device_type, rows=dims.rows, cols=dims.cols))
        rendered = engine.render_lines(
            template_lines,
            context=context,
            line_metadata=line_metadata,
            device_type=device_type,
        )
        return {
            "rendered": rendered,
            "device_type": device_type,
            "context_plugins": sorted(context.keys()),
        }

    @_tool
    def preview_saved_page(page_id: str, board_id: str | None = None) -> dict[str, Any]:
        """Render a SAVED page exactly as the display engine would send it.

        Complements render_page_preview(), which renders unsaved template
        lines: use this one to verify an existing page — with its stored
        line_metadata (alignment, wrap) applied — before set_active_page().
        Read-only; nothing is sent to the board.

        Args:
            page_id: The page identifier (from list_pages()).
            board_id: Optional board to check the page against (from the boards
                      list in get_settings_summary()). Adds fits_board and
                      board_warnings to the response; rendering itself always
                      uses the page's own device geometry.

        Returns: {page_id, name, device_type, rendered, rows, line_metadata,
        and — when board_id is given — fits_board, board_warnings}.
        """
        from .pages.service import check_ref_board_compatibility, get_page_service

        svc = get_page_service()
        page = svc.get_page(page_id)
        if page is None:
            raise ToolError(f"Page '{page_id}' not found.")
        result = svc.preview_page(page_id, force_refresh=True)
        if result is None:
            raise ToolError(f"Page '{page_id}' not found.")
        if not result.available:
            raise ToolError(result.error or "Page rendering failed.")

        out: dict[str, Any] = {
            "page_id": page_id,
            "name": page.name,
            "device_type": page.device_type,
            "rendered": result.formatted,
            "rows": result.formatted.split("\n"),
            "line_metadata": ([m.model_dump() for m in page.line_metadata] if page.line_metadata else None),
        }
        if board_id is not None:
            # Same roster existence check as the sibling board tools:
            # compatibility against a board that does not exist would come
            # back fits_board: true (unresolvable boards pass, by design of
            # the compat helper) — an answer about nothing (#1874 review).
            from .settings.service import get_settings_service

            known = get_settings_service().get_board_settings().boards or []
            if not any(isinstance(b, dict) and b.get("id") == board_id for b in known):
                raise ToolError(f"Board not found: {board_id}")
            compat = check_ref_board_compatibility(page_id, board_id)
            out["board_id"] = board_id
            out["fits_board"] = compat.ok
            out["board_warnings"] = compat.warnings
            if not compat.ok:
                out["board_error"] = compat.error
        return out

    @_tool
    def validate_template(template: list[str] | str, device_type: str = "flagship") -> dict[str, Any]:
        """Check template syntax without rendering, saving, or touching the board.

        Catches malformed {{...}} references, unknown plugins/variables,
        formula errors ({{= ... }}), and unknown filters — cheaper than
        render_page_preview() when you only need a syntax verdict.

        Args:
            template: Template string or list of template lines.
            device_type: Which board type's width to validate against —
                         'flagship' (22 cols), 'note' (15 cols).

        Returns: {valid: bool, errors: [{line, column, message}], device_type}.
        """
        from .devices import resolve_dimensions
        from .templates.engine import get_template_engine

        try:
            cols = resolve_dimensions(device_type).cols
        except Exception as exc:
            raise ToolError(f"Unknown device_type: {device_type}") from exc

        text = "\n".join(template) if isinstance(template, list) else template
        errors = get_template_engine().validate_template(text, cols=cols)
        return {
            "valid": len(errors) == 0,
            "errors": [{"line": e.line, "column": e.column, "message": e.message} for e in errors],
            "device_type": device_type,
        }

    # -----------------------------------------------------------------------
    # Schedule tools
    # -----------------------------------------------------------------------

    @_tool
    def list_schedules() -> list[dict[str, Any]] | dict[str, Any]:
        """List all scheduled time slots for page display.

        Returns a list of schedule entries with:
        - id: use this for update_schedule(), delete_schedule()
        - page_id: which page to show
        - start_time / end_time: HH:MM format (24h). end_time null = runs until next schedule.
        - day_pattern: 'all', 'weekdays', 'weekends', or 'custom'
        - enabled: whether the schedule entry is active
        """
        from .schedules.service import get_schedule_service

        svc = get_schedule_service()
        return _serialize(svc.list_schedules())

    @_tool
    def create_schedule(
        page_id: str,
        start_time: str,
        day_pattern: str = "all",
        end_time: str | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        """Create a new schedule entry to show a specific page at a specific time.

        Args:
            page_id: Which page (or collection) to display. Use IDs from list_pages()
                     or list_collections().
            start_time: When to start showing this page in HH:MM format (24h), e.g. "07:00".
            day_pattern: When this applies — 'all' (every day), 'weekdays', 'weekends',
                         or 'custom'. Default: 'all'.
            end_time: When to stop in HH:MM format. Null means open-ended
                      (runs until the next schedule or end of day). Default: None.
            enabled: Whether this schedule is active. Default: True.
        """
        return ops_executors.create_schedule(
            page_id=page_id,
            start_time=start_time,
            day_pattern=day_pattern,
            end_time=end_time,
            enabled=enabled,
        )

    @_tool
    def update_schedule(
        schedule_id: str,
        page_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        day_pattern: str | None = None,
        enabled: bool | None = None,
        clear_end_time: bool = False,
        clear_custom_days: bool = False,
    ) -> dict[str, Any]:
        """Update an existing schedule entry.

        Only the fields you provide will be changed.

        Args:
            schedule_id: The schedule identifier (from list_schedules()).
            page_id: New page to display (optional).
            start_time: New start time in HH:MM format (optional).
            end_time: New end time in HH:MM format (optional; omitted = unchanged).
            day_pattern: New day pattern: 'all', 'weekdays', 'weekends', 'custom' (optional).
            enabled: Enable or disable this schedule entry (optional).
            clear_end_time: Set True to remove the end time, making the entry
                open-ended. Needed because omitting end_time means
                "unchanged" — an explicit null cannot express the clear.
            clear_custom_days: Set True to drop a stored custom day list
                (e.g. when changing day_pattern away from 'custom').
        """
        return ops_executors.update_schedule(
            schedule_id,
            page_id=page_id,
            start_time=start_time,
            end_time=end_time,
            day_pattern=day_pattern,
            enabled=enabled,
            clear_end_time=clear_end_time,
            clear_custom_days=clear_custom_days,
        )

    @_tool
    def delete_schedule(schedule_id: str) -> dict[str, Any]:
        """Delete a schedule entry permanently.

        Args:
            schedule_id: The schedule identifier (from list_schedules()).
        """
        return ops_executors.delete_schedule(schedule_id)

    # -----------------------------------------------------------------------
    # Collection tools
    # -----------------------------------------------------------------------

    @_tool
    def list_collections() -> list[dict[str, Any]] | dict[str, Any]:
        """List all collections (ordered page groups with a selection mode).

        Returns a list with:
        - id: use for update_collection(), delete_collection(), or as page_id in schedules
        - name, page_ids
        - selection_mode: "time" (rotate on interval) or "variable" (pick by rule)
        - time / variable: mode-specific config block
        """
        from .collections.service import get_collection_service

        svc = get_collection_service()
        return _serialize(svc.list_collections())

    @_tool
    def create_collection(
        name: str,
        page_ids: list[str],
        selection_mode: str = "time",
        interval_seconds: int = 30,
        rules: list[dict[str, str]] | None = None,
        default_page_id: str | None = None,
        poll_seconds: int = 10,
    ) -> dict[str, Any]:
        """Create a collection that decides which page to show.

        The collection ID can be used as the page_id in create_schedule() to
        schedule the whole group at a specific time of day.

        Args:
            name: Display name for the collection.
            page_ids: Ordered list of page IDs that belong to the collection.
            selection_mode: "time" (default) rotates pages on a fixed interval;
                "variable" picks a page by evaluating expression rules against
                live plugin data.
            interval_seconds: For time mode — how long to show each page
                (default 30). Range: 5–86400 (5 seconds to 24 hours).
            rules: For variable mode — ordered list of
                {"expression": ..., "page_id": ...} entries. First truthy
                expression wins.
            default_page_id: For variable mode — fallback page when no rule
                matches. Must be in page_ids.
            poll_seconds: For variable mode — how often to re-evaluate rules
                (default 10). Range: 2–600.
        """
        return ops_executors.create_collection(
            name=name,
            page_ids=page_ids,
            selection_mode=selection_mode,
            interval_seconds=interval_seconds,
            rules=rules,
            default_page_id=default_page_id,
            poll_seconds=poll_seconds,
        )

    @_tool
    def update_collection(
        collection_id: str,
        name: str | None = None,
        page_ids: list[str] | None = None,
        selection_mode: str | None = None,
        interval_seconds: int | None = None,
        rules: list[dict[str, str]] | None = None,
        default_page_id: str | None = None,
        poll_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Update an existing collection's name, page list, or selection config.

        Pass only the fields you want to change. To switch modes, send the new
        selection_mode together with its config (interval_seconds for time,
        or rules + default_page_id for variable).

        Args:
            collection_id: The collection identifier (from list_collections()).
            name: New name (optional).
            page_ids: New ordered list of page IDs (optional). Replaces entire list.
            selection_mode: New mode ("time" or "variable").
            interval_seconds: New rotation interval (time mode).
            rules: New rule list (variable mode).
            default_page_id: New fallback page (variable mode).
            poll_seconds: New re-evaluation cadence (variable mode).
        """
        return ops_executors.update_collection(
            collection_id,
            name=name,
            page_ids=page_ids,
            selection_mode=selection_mode,
            interval_seconds=interval_seconds,
            rules=rules,
            default_page_id=default_page_id,
            poll_seconds=poll_seconds,
        )

    @_tool
    def delete_collection(collection_id: str) -> dict[str, Any]:
        """Delete a collection permanently.

        Args:
            collection_id: The collection identifier (from list_collections()).
        """
        return ops_executors.delete_collection(collection_id)

    # -----------------------------------------------------------------------
    # System tools
    # -----------------------------------------------------------------------

    @_tool
    def get_system_status() -> dict[str, Any]:
        """Get the current status of the FiestaBoard system.

        Returns version, whether the display service is running, plugin system
        status, and the number of installed/enabled plugins.
        """
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

    @_tool
    def get_settings_summary() -> dict[str, Any]:
        """Get a summary of current FiestaBoard settings (non-sensitive fields only).

        Returns display, location, and output settings, plus:
        - schedule: {enabled} — whether schedule mode drives the primary board
        - active_page_id: the primary board's manually-selected page (or null)
        - boards: one entry per configured board with id, name, device_type,
          rows/cols, notes_wide/notes_tall, primary, enabled, paused,
          schedule_enabled, active_page_id, and error (why the board failed to
          initialize, or null). Use a board's id as the board_id argument to
          board-targeting tools, and its rows/cols to size templates for it.

        AI provider credentials and board API keys are intentionally excluded.
        """
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
                    key,
                    exc,
                )

        # Schedule mode + active page (#1765): the troubleshoot prompt
        # walks both, and until now no tool returned them.
        try:
            summary["schedule"] = {"enabled": bool(svc.is_schedule_enabled())}
            summary["active_page_id"] = svc.get_active_page_id()
        except Exception as exc:
            logger.debug("get_settings_summary: could not fetch schedule/active page: %s", exc)

        summary["boards"] = _boards_summary(svc)
        return summary

    @_tool
    async def set_active_page(page_id: str, board_id: str | None = None) -> dict[str, Any]:
        """Set which page is currently shown on the FiestaBoard display.

        This immediately changes what's visible on the board.

        Args:
            page_id: The page or collection ID to display (from list_pages() or list_collections()).
            board_id: Board to target on a multi-board install (from the boards
                      list in get_settings_summary()). Omitted = the primary board.
        """
        # The executor delegates to the REST handler rather than
        # reimplementing it (#1559): selecting a page validates the ref,
        # enforces page<->board size compatibility, dismisses active plugin
        # triggers (#856), and renders to the board.
        return await ops_executors.set_active_page(page_id, board_id=board_id)

    @_tool
    def set_schedule_mode(enabled: bool, board_id: str | None = None) -> dict[str, Any]:
        """Enable or disable schedule mode.

        When enabled, FiestaBoard automatically switches pages according to
        the schedule you've configured. When disabled, it shows a fixed page.
        Schedule mode is per-board on a multi-board install.

        Args:
            enabled: True to enable schedule-based display, False to disable.
            board_id: Board to target on a multi-board install (from the boards
                      list in get_settings_summary()). Omitted = the primary board.
        """
        return ops_executors.set_schedule_mode(enabled, board_id=board_id)

    @_tool
    def get_active_page(board_id: str | None = None) -> dict[str, Any]:
        """What a board is CONFIGURED to show right now, fully resolved.

        Resolves schedule mode (when enabled for the board) and collections
        down to the concrete page. Distinct from get_board_content(), which
        reports what was last physically sent to the flaps.

        Args:
            board_id: Board to inspect on a multi-board install (from the boards
                      list in get_settings_summary()). Omitted = the primary board.

        Returns: {board_id, schedule_enabled, source ('schedule' or 'manual'),
        active_ref (the stored page/collection id), resolved_page_id (after
        collection resolution), page (summary of the resolved page, or null)}.
        """
        from .collections.models import is_collection_id
        from .settings.service import get_settings_service

        svc = get_settings_service()
        if board_id is not None:
            boards = svc.get_board_settings().boards or []
            if not any(isinstance(b, dict) and b.get("id") == board_id for b in boards):
                raise ToolError(f"Board not found: {board_id}")

        # Mirrors GET /pages/current-display: schedule mode owns the
        # answer when enabled; otherwise the manual per-board selection.
        schedule_enabled = bool(svc.is_schedule_enabled(board_id))
        if schedule_enabled:
            from .schedules.service import get_schedule_service
            from .time_service import get_time_service

            now = get_time_service().get_current_time()
            active_ref = get_schedule_service().get_active_page_id(
                now.time(), now.strftime("%A").lower(), board_id=board_id
            )
            source = "schedule"
        else:
            active_ref = svc.get_active_page_id(board_id)
            source = "manual"

        resolved_page_id = active_ref
        if active_ref and is_collection_id(active_ref):
            from .collections.service import get_collection_service

            resolved_page_id = get_collection_service().resolve_page_id(active_ref)

        page_summary = None
        if resolved_page_id:
            from .pages.service import get_page_service

            page = get_page_service().get_page(resolved_page_id)
            if page is not None:
                page_summary = {
                    "id": page.id,
                    "name": page.name,
                    "type": page.type,
                    "device_type": page.device_type,
                }
        return {
            "board_id": board_id,
            "schedule_enabled": schedule_enabled,
            "source": source,
            "active_ref": active_ref,
            "resolved_page_id": resolved_page_id,
            "page": page_summary,
        }

    @_tool
    def get_board_content(board_id: str | None = None) -> dict[str, Any]:
        """What is currently ON a board — the last known flap content. Read-only.

        Served from FiestaBoard's own caches (background poll / last-sent
        content); never writes to the board and never triggers a live read.
        Use it to check whether the board matches what get_active_page() says
        it should be showing. characters and message are null when nothing
        has been observed or sent yet.

        Args:
            board_id: Board to read on a multi-board install (from the boards
                      list in get_settings_summary()). Omitted = the primary
                      board. Secondary boards are served from their runtime
                      cache — board-state polling is primary-only.

        Returns: {characters (2-D grid of flap codes or null), message
        (formatted string or null), rows, cols, source ('polled' or
        'last_sent' or null), board_id}.
        """
        # get_service is the DisplayService singleton accessor — the same
        # seam get_system_status uses; no REST handler is called.
        from .api_server import _characters_to_message, get_service

        service = get_service()
        if not service:
            raise ToolError("Display service not initialized.")

        characters = None
        source = None
        if board_id is None:
            characters = service._polled_characters
            source = "polled" if characters is not None else None
            if characters is None and service.vb_client is not None:
                characters = getattr(service.vb_client, "_last_characters", None)
                source = "last_sent" if characters is not None else None
        else:
            from .settings.service import get_settings_service

            settings = get_settings_service()
            boards = settings.get_board_settings().boards or []
            if not any(isinstance(b, dict) and b.get("id") == board_id for b in boards):
                raise ToolError(f"Board not found: {board_id}")
            rt = service.get_runtime(board_id)
            if rt is None:
                # Legacy installs may key the primary runtime under the
                # fallback sentinel rather than its settings board id — route
                # the primary's own id to the primary caches (mirrors
                # DisplayService.mark_showing_out_of_band, #1874 review).
                try:
                    primary_id = settings.get_primary_board_id()
                except Exception:
                    primary_id = None
                if board_id == primary_id:
                    characters = service._polled_characters
                    source = "polled" if characters is not None else None
                    if characters is None and service.vb_client is not None:
                        characters = getattr(service.vb_client, "_last_characters", None)
                        source = "last_sent" if characters is not None else None
            if rt is not None:
                characters = rt.polled_characters
                source = "polled" if characters is not None else None
                if characters is None and rt.client is not None:
                    characters = getattr(rt.client, "_last_characters", None)
                    source = "last_sent" if characters is not None else None

        if characters is None:
            return {"characters": None, "message": None, "rows": 0, "cols": 0, "source": None, "board_id": board_id}
        return {
            "characters": _serialize(characters),
            "message": _characters_to_message(characters),
            "rows": len(characters),
            "cols": len(characters[0]) if characters else 0,
            "source": source,
            "board_id": board_id,
        }

    @_tool
    def send_message(text: str, board_id: str | None = None) -> dict[str, Any]:
        """Send a one-off text message directly to a board.

        The text is word-wrapped to the board's width; real newlines are
        honored; single-brace color markers like {red} or {63} render as one
        colored tile each. This bypasses pages entirely — the message stays
        up until the active page next changes or the display refreshes.

        A paused board or active silence mode returns status "blocked"
        (deliberate policy — relay it to the user, don't retry).

        Args:
            text: The message text to display.
            board_id: Board to target on a multi-board install (from the boards
                      list in get_settings_summary()). Omitted = the primary board.
        """
        return ops_executors.send_message(text, board_id=board_id)

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
                return f"<!DOCTYPE html><html><body><p>Page <code>{page_id}</code> not found.</p></body></html>"
            return render_page_preview_html(page)
        except Exception as exc:
            return f"<!DOCTYPE html><html><body><p>Error: {exc}</p></body></html>"

    @mcp.resource("fiestaboard://variables")
    def get_variables_resource() -> str:
        """All template variables from enabled plugins."""
        try:
            from .plugins import get_plugin_registry

            registry = get_plugin_registry()
            # #1739: the loop below reads `meta.get("description")`, so it needs
            # the metadata mapping. Against get_all_variables()'s list payload
            # `.items()` raised AttributeError, and this handler returned that
            # as the resource body on every install with an enabled plugin.
            variables = registry.get_all_variables_with_metadata()
            lines = ["# Available Template Variables\n", "Use these in page templates as `{{plugin.variable}}`.\n"]
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
                    f"- **{s.start_time}–{end}** on {s.day_pattern} → page `{s.page_id}` ({status}) [`{s.id}`]"
                )
            return "\n".join(lines)
        except Exception as exc:
            return f"Error: {exc}"

    @mcp.resource("fiestaboard://collections")
    def get_collections_resource() -> str:
        """Live list of all collections (page playlists)."""
        try:
            from .collections.service import get_collection_service

            svc = get_collection_service()
            collections = svc.list_collections()
            lines = [f"# Collections ({len(collections)} total)\n"]
            for c in collections:
                page_count = len(getattr(c, "page_ids", []) or [])
                mode = getattr(c, "selection_mode", "time")
                if mode == "time":
                    interval = getattr(getattr(c, "time", None), "interval_seconds", "?")
                    tail = f"time mode, {interval}s per page"
                else:
                    poll = getattr(getattr(c, "variable", None), "poll_seconds", "?")
                    tail = f"variable mode, polls every {poll}s"
                lines.append(f"- **{c.name}** (`{c.id}`) — {page_count} pages, {tail}")
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
            "7. Optionally set up a schedule or collection\n\n"
            "Be conversational and explain what each step does."
        )

    @mcp.prompt()
    def create_display_page(
        topic: Annotated[
            str,
            Field(description="What the page should show, e.g. 'weather', 'my commute', 'stock prices'."),
        ] = "weather",
    ) -> str:
        """Create a new display page for a specific topic.

        Args:
            topic: What the page should show, e.g. "weather", "my commute".
        """
        return (
            f"Help me create a FiestaBoard display page for: {topic}\n\n"
            "Please:\n"
            "1. Check list_installed_plugins() for relevant plugins\n"
            "2. If needed, suggest installing a plugin and guide me through configuration\n"
            "3. Call get_template_variables() to find the right variable references\n"
            "4. Create a well-designed page with create_page() using those variables\n"
            "5. Offer to schedule the page if appropriate\n\n"
            f"{ops_teaching.dimensions_summary_sentence()} Use colour tokens like "
            "{{yellow}}, {{white}}, {{green}} to make it visually clear."
        )

    @mcp.prompt()
    def schedule_my_day() -> str:
        """Build a time-of-day schedule that rotates pages through the day."""
        return (
            "Help me set up a daily display schedule on FiestaBoard. Please:\n"
            "1. Call list_pages() and list_collections() so we know what content exists\n"
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
    def build_a_collection() -> str:
        """Build a collection (playlist) that rotates between multiple pages."""
        return (
            "Help me build a FiestaBoard collection — a playlist that cycles through\n"
            "several pages on a timer. Please:\n"
            "1. Call list_pages() and show me the candidates with their device_type\n"
            "2. Ask which pages I want in the rotation and in what order\n"
            "   (all pages in one collection must share the same device_type)\n"
            "3. Ask how long each page should stay up — typical values are\n"
            "   15–60 seconds; the allowed range is 5–86400 (up to 24 hours)\n"
            "4. Call create_collection() with the ordered page_ids\n"
            "5. Offer to either:\n"
            "     a) set the collection as the active page now via set_active_page(),\n"
            "        OR\n"
            "     b) schedule it for specific time slots via create_schedule()\n"
            "        (a collection id can be used anywhere a page id is accepted)\n"
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


def build_streamable_http_app() -> Any:
    """Return the ASGI app for the MCP server, or ``None`` if unavailable.

    The default transport_security enables DNS-rebinding protection and only
    allows Host headers matching ``127.0.0.1:*``/``localhost:*``/``[::1]:*``.
    FiestaBoard is reached over the LAN by IP, hostname, or
    ``fiestaboard.local`` — none of which match — so the default would 421
    every legitimate request. We opt out and rely on the auth layer
    (``FIESTABOARD_AUTH_ENABLED``) for access control instead.
    """
    if mcp_server is None:
        return None

    from mcp.server.transport_security import TransportSecuritySettings  # type: ignore[import-untyped]

    return mcp_server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        ),
    )
