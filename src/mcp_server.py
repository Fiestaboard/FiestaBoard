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

See ``docs/internal/setup/MCP_CLIENTS.md`` for the full setup walkthrough,
including why claude.ai web Connectors can't reach a LAN host.

Tool annotations
----------------
Every tool carries standard MCP ``ToolAnnotations`` (``readOnlyHint``,
``destructiveHint``, ``idempotentHint``, ``openWorldHint``, ``title``), set
through the ``_tool`` decorator's keyword flags. They are the server's
statement of what a tool does to the world, and two consumers rely on
them: external clients decide whether to confirm a call, and the in-app
chat runs ``readOnlyHint`` tools freely mid-turn while pausing only on
``destructiveHint`` ones. ``tests/test_mcp_annotations.py`` pins the sets,
so a new tool has to declare its flags rather than inherit a default.
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
from .ops.results import rest_detail as _rest_detail
from .ops.results import serialize as _serialize

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy imports — the MCP package is optional; we log a warning if missing
# rather than crashing the whole API server on import.
# ---------------------------------------------------------------------------

try:
    from mcp.server import MCPServer  # type: ignore[import-untyped]
    from mcp.server.mcpserver.exceptions import ToolError  # type: ignore[import-untyped]
    from mcp.types import ToolAnnotations  # type: ignore[import-untyped]

    _MCP_AVAILABLE = True
except ImportError:  # pragma: no cover
    _MCP_AVAILABLE = False
    MCPServer = None  # type: ignore[assignment,misc]
    ToolError = None  # type: ignore[assignment,misc]
    ToolAnnotations = None  # type: ignore[assignment,misc]
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
                # The credential-free projection every board tool returns
                # (id, name, device_type, colour, glyph, api_mode, flags,
                # has_host / has_credentials) plus the summary-only fields.
                **ops_executors.board_public_view(board),
                "rows": rows,
                "cols": cols,
                "primary": bid == primary_id,
                "active_page_id": active_page_id,
                "error": error if isinstance(error, str) else None,
            }
        )
    return boards_out


def _mask_settings_block(cm: Any, block: Any) -> Any:
    """Mask credential fields in a config block on the way out.

    ``ConfigManager._mask_sensitive`` is the same projection the REST
    settings endpoints apply; it replaces a set value with ``"***"`` and
    leaves an unset one empty, so a model can tell "configured" from "not"
    without ever seeing the secret.
    """
    return cm._mask_sensitive(_serialize(block))


def _rest_error(exc: Any) -> Exception:
    """Map a REST handler's HTTPException onto the MCP error contract."""
    return ToolError(_rest_detail(exc))


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
            "  7. Optionally schedule pages with create_schedule()\n"
            "  8. Adjust display, location, polling or quiet hours with\n"
            "     update_setting() — read them first via get_settings_summary()\n\n"
            "PAGE EDITOR\n"
            "  Everything the web page editor saves is reachable here:\n"
            "  • update_page() takes device_type, notes_wide/notes_tall (note_array\n"
            "    geometry), line_metadata (per-line alignment + wrap), duration_seconds\n"
            "    and a per-page transition override (transition_strategy,\n"
            "    transition_interval_ms, transition_step_size; clear_transition_override\n"
            "    removes it). A device/size retarget answers incompatible_references —\n"
            "    the boards, schedules and silence pages the page no longer fits.\n"
            "    Relay them to the user; nothing is changed automatically.\n"
            "  • export_page(page_id) → a portable share string; import_page(share_string)\n"
            "    creates a new page from one (the editor's Share / Import buttons).\n"
            "  • list_staff_picks() + import_staff_pick(pick_id) — the curated gallery.\n"
            "  • get_current_display() — the raw template + line_metadata of the page\n"
            "    a board is showing, to start a new page from.\n"
            "  • list_formula_functions() — every function usable inside {{= ...}}.\n"
            "  • Transition Lab (beta, Settings → Beta): list_transition_plugins(),\n"
            "    test_transition_live(plugin_id, to_page_id) runs one on the real board,\n"
            "    restore_board() snaps it back to its active page afterwards.\n\n"
            "PLUGIN MANAGEMENT (everything the Integrations page can do)\n"
            "  • install_plugin(plugin_id) installs from the registry;\n"
            "    install_plugin(repository=<https git URL>, branch=...) is the\n"
            "    'Add from Git' dialog — confirm the URL with the user first.\n"
            "  • Multi-instance plugins (one weather plugin per city): \n"
            "    list_plugin_instances() / create_plugin_instance() /\n"
            "    delete_plugin_instance(). Instances are addressed as 'base:label'\n"
            "    in configure_plugin(), enable_plugin() and {{base:label.var}}.\n"
            "  • Demo pages: get_plugin_demo_page() tells whether a plugin bundles\n"
            "    one and whether it exists; create_plugin_demo_page() builds it\n"
            "    (requires the plugin's required settings to be configured).\n"
            "  • Updates: list_pending_plugin_updates() reads the cached check;\n"
            "    check_plugin_updates() scans the git remotes now;\n"
            "    update_all_plugins() applies every pending update at once.\n"
            "  • Configuring: get_plugin_manifest() has the full settings_schema,\n"
            "    color_rules_schema and demo templates; list_plugin_options()\n"
            "    browses a remote-options picker (Home Assistant entities, transit\n"
            "    stops…) for a valid value; configure_plugin() also takes\n"
            "    color_rules (see its description) to colour a variable by value.\n"
            "  • list_plugin_errors() explains plugins that failed to load or\n"
            "    were quarantined by the fetch circuit breaker.\n\n"
            "SCHEDULES (everything the Schedules page can do)\n"
            "  • list_schedules(board_id) is the page's view: entries with today's\n"
            "    resolved sunrise/sunset times, plus default_page_id and\n"
            "    schedule_enabled for that board.\n"
            "  • create_schedule()/update_schedule() take every entry-form field:\n"
            "    custom_days, recurrence_type ('weekly' | 'annual_date' |\n"
            "    'one_off_date') with its dates, start_type/end_type ('fixed' |\n"
            "    'sunrise' | 'sunset') with minute offsets, and board_id.\n"
            "  • validate_schedules(board_id) reports overlaps and gaps — run it\n"
            "    after editing. set_default_page(page_id) picks what shows in gaps;\n"
            "    update_setting('schedule_behavior', {defer_on_reenable}) sets the\n"
            "    global re-enable behavior.\n"
            "  • Collections rotate on 'time', pick by 'variable' rules, or shuffle\n"
            "    on 'random'; update_collection() merges mode config, so a single\n"
            "    field (poll_seconds, rules, interval_seconds) can change alone.\n\n"
            "BOARD STATE (the Home page's controls)\n"
            "  • set_temporary_override(page_id | template_lines, duration_minutes)\n"
            "    shows something for a while on the primary board and reverts on\n"
            "    its own; get_temporary_override() reads it; cancel_temporary_override()\n"
            "    ends it early. get_active_page() also reports it.\n"
            "  • force_refresh() resends the active content to every board\n"
            "    ('Resend to board'). get_silence_status(board_id) says whether\n"
            "    quiet hours are suppressing sends right now.\n"
            "  • pause_board(board_id)/resume_board(board_id) stop and restart\n"
            "    every write to a board; a paused board reports 'blocked' on sends.\n\n"
            "SETTINGS, HARDWARE AND SYSTEM (everything the Settings page can change,\n"
            "except secrets)\n"
            "  • update_setting(category, values) — general (instance_name renames\n"
            "    the install, timezone, time/date format), display, transitions,\n"
            "    output, polling, location, silence_schedule, active_page, beta,\n"
            "    plugins (auto_update), mqtt (no username/password), ai (no\n"
            "    api_key), release_channel, auto_update, hdmi_kiosk\n"
            "  • Boards: update_board() renames/retypes/resizes a board, sets its\n"
            "    colour, code-62 glyph, API mode or host; add_board(),\n"
            "    remove_board(), detect_board_size(), identify_tile()\n"
            "  • FiestaPanels (TV viewers): list_panels(), create_panel(),\n"
            "    update_panel() (incl. is_display), delete_panel()\n"
            "  • Network (FiestaPi): disconnect_wifi(), forget_wifi_network()\n"
            "  • System: get_system_status(), check_for_update(),\n"
            "    trigger_system_update(), restart_system(), shutdown_system(),\n"
            "    export_backup(), test_ai_provider()\n"
            "  • Advanced/debug: blank_board(), fill_board(),\n"
            "    show_board_debug_info(), run_network_diagnostics(),\n"
            "    clear_board_cache()\n"
            "  Secrets never travel over MCP: board API keys, Wi-Fi passphrases,\n"
            "  MQTT/AI credentials, MCP tokens and login settings are entered by\n"
            "  the user in the web UI. Tell them where, don't ask them to paste.\n\n"
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
            "  • Destructive tools (uninstall_plugin, delete_plugin_instance,\n"
            "    delete_page, delete_schedule, delete_collection, remove_board,\n"
            "    delete_panel, forget_wifi_network,\n"
            "    disconnect_wifi, trigger_system_update, restart_system,\n"
            "    shutdown_system) cannot be undone — confirm intent with the user\n"
            "    before calling them unless they explicitly requested the action.\n"
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
    def _tool(
        fn: Any = None,
        *,
        read_only: bool = False,
        destructive: bool | None = None,
        idempotent: bool | None = None,
        open_world: bool = False,
        title: str | None = None,
    ) -> Any:
        """Register ``fn`` as a tool with the error contract and its annotations.

        The keyword flags become standard MCP ``ToolAnnotations``, which are
        how a client (and the in-app chat) learns what a tool does to the
        world without keeping its own list:

        - ``read_only``: observes only. Implies ``destructive=False`` and
          ``idempotent=True``; the chat runs these without pausing.
        - ``destructive``: cannot be undone by another tool call (deletes,
          uninstalls). Clients ask the user first. Defaults to
          ``not read_only`` so an unclassified writer errs on the side of
          asking — the spec's own default for a missing hint is *true*.
        - ``idempotent``: the same call twice leaves the same state as once.
        - ``open_world``: reaches outside this install (registry over the
          network, a git remote, a plugin's upstream API).

        ``tests/test_mcp_annotations.py`` pins the resulting sets, so adding
        a tool means deciding its flags; there is no silent default path.
        """

        def decorate(fn: Any) -> Any:
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

            is_destructive = (not read_only) if destructive is None else destructive
            is_idempotent = read_only if idempotent is None else idempotent
            # Wire names, not attribute names: the SDK renamed the Python
            # attributes between 2.1 (readOnlyHint) and 2.2 (read_only_hint);
            # the camelCase aliases are the stable contract on both.
            annotations = ToolAnnotations.model_validate(
                {
                    "title": title or fn.__name__.replace("_", " ").capitalize(),
                    "readOnlyHint": read_only,
                    "destructiveHint": is_destructive,
                    "idempotentHint": is_idempotent,
                    "openWorldHint": open_world,
                }
            )
            return mcp.tool(annotations=annotations)(wrapper)

        return decorate(fn) if fn is not None else decorate

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

    @_tool(read_only=True)
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

    @_tool(read_only=True, open_world=True)
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

    @_tool(destructive=False, open_world=True)
    async def install_plugin(
        plugin_id: str | None = None,
        auto_enable: bool = True,
        repository: str | None = None,
        branch: str = "",
        initial_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Install a plugin from the FiestaBoard registry or from a public git URL.

        Two sources, like the Integrations page:
        - Registry (default): pass only plugin_id from list_registry_plugins().
        - "Add from Git": pass repository (an https git URL) and optionally
          branch; plugin_id is then an optional override of the id derived
          from the repository name. Anyone can publish a plugin repo, so
          confirm the URL with the user before installing from git.

        Args:
            plugin_id: Registry plugin id (e.g. 'openweather'); or, with
                       repository, the id to install the clone under.
            auto_enable: Whether to enable the plugin after installation (default: True).
            repository: Public https git URL to clone instead of using the registry.
            branch: Branch or tag to check out when installing from repository
                    (default: the repository's default branch).
            initial_config: Settings to apply right after install (same shape
                            as configure_plugin's config). Never guess API keys.

        Returns {plugin_id, enabled, source: 'registry'|'git'}. After
        installing, use configure_plugin() to set API keys and other settings
        and get_template_variables() to discover the variables it exposes.
        """
        return await ops_executors.install_plugin(
            plugin_id,
            auto_enable=auto_enable,
            initial_config=initial_config,
            repository=repository,
            branch=branch,
        )

    @_tool(destructive=False, idempotent=True)
    async def enable_plugin(plugin_id: str) -> dict[str, Any]:
        """Enable an installed but currently-disabled plugin.

        The plugin must already be installed — use install_plugin() first for
        anything from list_registry_plugins().

        Args:
            plugin_id: The plugin identifier (from list_installed_plugins()).
        """
        return ops_executors.enable_plugin(plugin_id)

    @_tool(destructive=False, idempotent=True)
    async def disable_plugin(plugin_id: str) -> dict[str, Any]:
        """Disable an installed plugin without uninstalling it.

        The plugin can be re-enabled later with enable_plugin().

        Args:
            plugin_id: The plugin identifier (from list_installed_plugins()).
        """
        return ops_executors.disable_plugin(plugin_id)

    @_tool(destructive=True)
    async def uninstall_plugin(plugin_id: str) -> dict[str, Any]:
        """Permanently remove an installed plugin.

        WARNING: This is irreversible. The plugin and all its configuration
        will be deleted. Only external/registry plugins can be uninstalled;
        built-in plugins cannot be removed.

        Args:
            plugin_id: The plugin identifier (from list_installed_plugins()).
        """
        return ops_executors.uninstall_plugin(plugin_id)

    @_tool(destructive=False, idempotent=True)
    async def configure_plugin(plugin_id: str, config: dict[str, Any]) -> dict[str, Any]:
        """Update configuration settings for an installed plugin.

        Use list_installed_plugins() to see the settings_schema for a plugin,
        which shows all valid config keys, their types, and which are required.

        Settings are merged into the plugin's existing configuration and saved
        to disk, so they survive a restart. A config the plugin rejects is
        reported as an error and nothing is saved.

        IMPORTANT: Never guess API keys — only set values the user has provided.
        Sensitive fields (api_key, password, etc.) must be provided explicitly.

        Plugin instances: a multi-instance plugin's named instances are
        configured by their compound id 'base:label' (e.g. 'weather:sf') —
        see list_plugin_instances() / create_plugin_instance(). Fields with
        a remote-options picker ("ui:widget": "remote-options" in the
        settings_schema) take a value from list_plugin_options().

        Color rules: to colour a variable automatically, set the special
        'color_rules' key — {field_name: [rule, ...]} where each rule is
        {"condition": "==" | "!=" | ">" | "<" | ">=" | "<=", "value": <number
        or string>, "color": "red" | "orange" | "yellow" | "green" | "blue" |
        "violet" | "white" | "black"}. Rules are checked in order and the
        FIRST match wins; a colour tile is then placed before the value
        wherever {{plugin.field}} is rendered. get_plugin_manifest() lists
        the eligible fields under color_rules_schema. Example:
        {"color_rules": {"temp_f": [{"condition": ">=", "value": 90,
        "color": "red"}, {"condition": "<", "value": 50, "color": "blue"}]}}.
        'color_rules' replaces the whole map for that plugin (it is not
        merged per field), so send every field's rules together.

        Args:
            plugin_id: The plugin identifier, or an instance id 'base:label'.
            config: Dictionary of configuration key-value pairs to update.
                    Only include keys you want to change.
        """
        return ops_executors.configure_plugin(plugin_id, config)

    @_tool(destructive=False, idempotent=True, open_world=True)
    async def update_plugin(plugin_id: str) -> dict[str, Any]:
        """Update an installed plugin to its latest version from its git remote.

        Built-in plugins cannot be updated this way.

        Args:
            plugin_id: The plugin identifier (from list_installed_plugins()).
        """
        # #1741 lives on in the executor: updates go through
        # PluginService.apply_update — the shared, guarded path.
        return await ops_executors.update_plugin(plugin_id)

    # -- updates (the Integrations page's "Check for updates" / "Update all") --

    @_tool(read_only=True)
    def list_pending_plugin_updates() -> dict[str, Any]:
        """Which installed external plugins have an update waiting, per the last check.

        Reads the cached result of the periodic (6-hourly) check or of
        check_plugin_updates(); it never touches the network itself.

        Returns {updates: {plugin_id: true|false}, blocked: {plugin_id:
        reason}} — 'blocked' explains updates held back because the new
        version needs a newer FiestaBoard core.
        """
        from .plugins import get_plugin_registry

        registry = get_plugin_registry()
        return {
            "updates": _serialize(registry.get_update_status()),
            "blocked": _serialize(registry.get_update_blocked_reasons()),
        }

    @_tool(destructive=False, idempotent=True, open_world=True)
    async def check_plugin_updates() -> dict[str, Any]:
        """Check every enabled external plugin's git remote for a newer version now.

        Refreshes the cache list_pending_plugin_updates() reads. Apply what
        it finds with update_plugin() (one) or update_all_plugins() (all).

        Returns {checked, updates_available: [plugin_id, ...], blocked:
        {plugin_id: reason}}.
        """
        return await ops_executors.check_plugin_updates()

    @_tool(destructive=False, idempotent=True, open_world=True)
    async def update_all_plugins() -> dict[str, Any]:
        """Fetch and reload every external plugin with a pending update.

        Uses the cached status from the last check — call
        check_plugin_updates() first for a fresh scan. A plugin that fails
        does not abort the rest: the result is still a success carrying
        {updated: [plugin_id, ...], failed: {plugin_id: reason}}.
        """
        return await ops_executors.update_all_plugins()

    # -- instances (multi-instance plugins, e.g. one weather plugin per city) --

    @_tool(read_only=True)
    def list_plugin_instances(plugin_id: str) -> dict[str, Any]:
        """List the named instances of a multi-instance plugin (the base is not included).

        Args:
            plugin_id: The base plugin identifier (an instance id 'base:label'
                       is accepted and resolved to its base).

        Returns {plugin_id, instances: [{label, key, enabled, has_config}],
        total}. 'key' is the compound id ('base:label') to pass to
        configure_plugin(), enable_plugin(), disable_plugin() and
        get_plugin_data(); templates reference it as {{base:label.variable}}.
        """
        from .plugins import get_plugin_registry

        registry = get_plugin_registry()
        base_id, _ = registry.parse_instance_key(plugin_id)
        if registry.get_plugin(base_id) is None:
            raise ToolError(f"Plugin not found: {base_id}")
        instances = registry.list_instances(base_id)
        return {"plugin_id": base_id, "instances": _serialize(instances), "total": len(instances)}

    @_tool(destructive=False)
    async def create_plugin_instance(plugin_id: str, label: str) -> dict[str, Any]:
        """Create a named instance of an installed plugin (e.g. a second weather city).

        The new instance starts DISABLED with an empty configuration; configure
        it with configure_plugin() and enable it with enable_plugin() using
        the returned instance_key ('base:label'). Labels are 1-40 letters,
        digits, underscores or hyphens and are normalised to lowercase.

        Args:
            plugin_id: The base plugin identifier (from list_installed_plugins()).
            label: Short label for the instance (e.g. 'sf', 'kitchen').

        Returns {plugin_id, instance_label, instance_key}.
        """
        return ops_executors.create_plugin_instance(plugin_id, label)

    @_tool(destructive=True)
    async def delete_plugin_instance(plugin_id: str, label: str) -> dict[str, Any]:
        """Permanently remove a plugin instance and its saved configuration.

        WARNING: irreversible. Pages that reference {{base:label.variable}}
        will render '???' afterwards. The base plugin itself is untouched —
        use uninstall_plugin() for that.

        Args:
            plugin_id: The base plugin identifier.
            label: The instance label (from list_plugin_instances()).
        """
        return ops_executors.delete_plugin_instance(plugin_id, label)

    # -- demo pages (the Integrations page's "Create Demo Page") --------------

    @_tool(read_only=True)
    def get_plugin_demo_page(plugin_id: str, device_type: str = "flagship") -> dict[str, Any]:
        """Whether a plugin ships a demo page template and whether one has been created.

        Args:
            plugin_id: The plugin identifier (from list_installed_plugins()).
            device_type: Board shape to check for ('flagship' or 'note';
                         default 'flagship').

        Returns {plugin_id, device_type, has_demo_template, exists, page_id}.
        'has_demo_template' is whether the plugin bundles a demo for that
        shape; 'exists'/'page_id' whether create_plugin_demo_page() has
        already built it.
        """
        from .plugins.errors import PluginError
        from .plugins.service import PluginService

        try:
            status = PluginService().demo_page_status(plugin_id, device_type)
        except PluginError as exc:
            raise ToolError(str(exc)) from exc
        return {"plugin_id": plugin_id, "device_type": device_type, **status}

    @_tool(destructive=False)
    async def create_plugin_demo_page(
        plugin_id: str,
        device_type: str | None = None,
        recreate: bool = False,
    ) -> dict[str, Any]:
        """Create the demo page a plugin bundles — a ready-made page showing its variables.

        The plugin's required settings must be configured first (the tool says
        which are missing). The demo page is a singleton per plugin and device
        type: if one already exists it is left alone and reported back, unless
        recreate=True, which deletes it and rebuilds from the plugin's template
        (losing any edits the user made to it).

        Args:
            plugin_id: The plugin identifier (from list_installed_plugins()).
            device_type: 'flagship' or 'note'. Omitted = whichever the user's
                         configured boards need (first board with a matching
                         demo template).
            recreate: Rebuild an existing demo page instead of keeping it
                      (default: False).

        Returns {page_id, name, device_type, created, recreated}. Show it
        with set_active_page() or preview it with preview_saved_page().
        """
        return ops_executors.create_plugin_demo_page(plugin_id, device_type, recreate=recreate)

    # -- discovery reads the configure flow needs ------------------------------

    @_tool(read_only=True, open_world=True)
    async def list_plugin_options(
        plugin_id: str,
        options_id: str,
        parent: dict[str, Any] | None = None,
        query: str = "",
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Browse a plugin's upstream catalog to find a valid value for a settings field.

        Some settings fields are pickers over a remote catalog (Home Assistant
        entities, transit stops, stock symbols…): in the settings_schema they
        carry "ui:widget": "remote-options" and "ui:options": {"options_id":
        ...}. This tool asks the plugin for that catalog so you can put a real
        value into configure_plugin(). The plugin's stored config is used, so
        set credentials first. Uses the plugin's upstream API.

        Args:
            plugin_id: The plugin identifier, or an instance id 'base:label'.
            options_id: The catalog to browse — the field's ui:options.options_id.
            parent: Values of the fields this one depends on (ui:options.depends_on),
                    e.g. {"agency": "SF"} to scope a stop list to an agency.
            query: Free-text search for catalogs that support it.
            limit: Maximum options to return, 1-1000 (default 50).
            cursor: Continuation token from a previous result's 'cursor'.

        Returns {plugin_id, options_id, options: [{value, label, description,
        group, preview, disabled}], has_more, cursor, total, error}. 'value'
        is what goes into the config. A non-null 'error' with no options is a
        hint (e.g. no API key yet), not a failure.
        """
        from .plugins.errors import PluginError
        from .plugins.service import PluginService

        try:
            result = await PluginService().browse_options(
                plugin_id,
                options_id,
                parent=parent,
                query=query,
                limit=limit,
                cursor=cursor,
            )
        except PluginError as exc:
            raise ToolError(str(exc)) from exc
        return _serialize(result)

    @_tool(read_only=True)
    def get_plugin_manifest(plugin_id: str) -> dict[str, Any]:
        """The full raw manifest of an installed plugin.

        Everything the plugin declares in one read: settings_schema (with any
        ui:widget / ui:options picker hints), variables and their groups,
        max_lengths, color_rules_schema (which fields configure_plugin()'s
        color_rules can target, with their default rules), demo templates,
        env_vars, screenshots. list_installed_plugins() carries only the
        summary; use this when configuring a plugin in detail.

        Args:
            plugin_id: The plugin identifier, or an instance id 'base:label'.
        """
        from .plugins import get_plugin_registry

        manifest = get_plugin_registry().get_manifest(plugin_id)
        if manifest is None:
            raise ToolError(f"Plugin not found: {plugin_id}")
        return _serialize(manifest.raw)

    @_tool(read_only=True)
    def list_plugin_errors() -> dict[str, Any]:
        """Why installed plugins are not contributing data — load errors and tripped breakers.

        Two independent failure modes in one payload: 'errors' maps plugin ids
        to import-time error messages (the plugin never loaded, so it is
        missing from list_installed_plugins()); 'fetch_breakers' maps plugin
        ids to {consecutive_timeouts, quarantined, cooldown_remaining_seconds}
        for plugins that loaded fine but keep timing out, so the circuit
        breaker has stopped polling them. Empty maps mean all is well. Check
        this when a page shows '???' or stale values and get_plugin_data()
        does not explain it.
        """
        from .plugins import get_plugin_registry

        registry = get_plugin_registry()
        return {
            "errors": _serialize(registry.get_load_errors()),
            "fetch_breakers": _serialize(registry.get_fetch_breaker_status()),
        }

    @_tool(read_only=True)
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

    @_tool(read_only=True, open_world=True)
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

    @_tool(read_only=True)
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

    @_tool(read_only=True)
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

    @_tool(destructive=False)
    def create_page(
        name: str,
        template_lines: list[str],
        device_type: str = "flagship",
        duration_seconds: int = 300,
        line_metadata: list[dict[str, Any]] | None = None,
        notes_wide: int | None = None,
        notes_tall: int | None = None,
        transition_strategy: str | None = None,
        transition_interval_ms: int | None = None,
        transition_step_size: int | None = None,
    ) -> dict[str, Any]:
        """Create a new template page on FiestaBoard.

        Template lines use {{plugin.variable}} syntax for dynamic data and
        {{color}} tokens ({{red}}, {{green}}, {{white}}, etc.) for styling.

        Flagship display is 22 columns × 6 rows.
        Note display is 15 columns × 3 rows.
        A note_array is notes_wide × notes_tall Notes: 15·notes_wide columns
        × 3·notes_tall rows.

        Args:
            name: Display name for the page.
            template_lines: List of template strings, one per row. Must match
                            the number of rows for the device_type
                            (6 for flagship, 3 for note, 3·notes_tall for
                            note_array).
            device_type: 'flagship' (default), 'note', or 'note_array'.
            duration_seconds: How long to show this page in a time-mode collection (default: 300).
            line_metadata: Optional per-line dicts with "alignment"
                           ('left'/'center'/'right') and "wrap" (bool), one
                           per template line — the editor's alignment and
                           wrap toggles. Omitted = left-aligned, no wrap.
            notes_wide: For note_array only — Notes across (1–8). Omitted = 1.
            notes_tall: For note_array only — Notes down (1–8). Omitted = 1.
            transition_strategy: Optional per-page transition override —
                                 'column', 'reverse-column', 'edges-to-center',
                                 'row', 'diagonal', 'random', or the
                                 'plugin:<id>' string from
                                 list_transition_plugins(). Omitted = the
                                 system transition from get_settings_summary().
            transition_interval_ms: Optional per-page step interval (0–5000 ms).
            transition_step_size: Optional per-page step size (≥ 1).

        Example template_lines for a weather page:
            ["{{white}}{{= UPPER(weather.city)}}", "{{yellow}}{{weather.temperature}}°F",
             "{{weather.condition}}", "", "{{date_time.time_12h}}", "{{date_time.date_short}}"]
        """
        return ops_executors.create_page(
            name=name,
            template_lines=template_lines,
            device_type=device_type,
            duration_seconds=duration_seconds,
            line_metadata=line_metadata,
            notes_wide=notes_wide,
            notes_tall=notes_tall,
            transition_strategy=transition_strategy,
            transition_interval_ms=transition_interval_ms,
            transition_step_size=transition_step_size,
        )

    @_tool(destructive=False, idempotent=True)
    def update_page(
        page_id: str,
        name: str | None = None,
        template_lines: list[str] | None = None,
        duration_seconds: int | None = None,
        device_type: str | None = None,
        notes_wide: int | None = None,
        notes_tall: int | None = None,
        line_metadata: list[dict[str, Any]] | None = None,
        transition_strategy: str | None = None,
        transition_interval_ms: int | None = None,
        transition_step_size: int | None = None,
        clear_transition_override: bool = False,
    ) -> dict[str, Any]:
        """Update any field of an existing page. Only the fields you pass change.

        Covers everything the web page editor saves. Changing device_type,
        notes_wide or notes_tall RETARGETS the page to a new size: content
        that no longer fits is truncated at render time, and the response's
        incompatible_references lists every board reference (a schedule
        entry, a board's active page, a silence page) that now points this
        page at a board it no longer fits. Nothing is changed automatically
        — relay the list to the user so they can fix the references.

        Args:
            page_id: The page identifier (from list_pages()).
            name: New display name (optional).
            template_lines: New template content (optional). Replaces all lines;
                            must match the row count of the (new) device size.
            duration_seconds: New time-mode duration in seconds (optional).
            device_type: Retarget to 'flagship', 'note', or 'note_array' (optional).
            notes_wide: New note_array width in Notes, 1–8 (optional).
            notes_tall: New note_array height in Notes, 1–8 (optional).
            line_metadata: New per-line alignment/wrap list (optional). Replaces
                           the whole list; one {"alignment", "wrap"} dict per line.
            transition_strategy: New per-page transition override (optional) —
                                 a built-in strategy name or a 'plugin:<id>'
                                 from list_transition_plugins().
            transition_interval_ms: New per-page step interval, 0–5000 (optional).
            transition_step_size: New per-page step size, ≥ 1 (optional).
            clear_transition_override: Set True to remove the per-page
                transition override so the page follows the system
                transition again. Needed because omitting the transition
                fields means "unchanged".

        Returns: {status, message, page_id, name, device_type,
        incompatible_references: [{board_id, board_name, surface, schedule_id}]}.
        """
        return ops_executors.update_page(
            page_id,
            name=name,
            template_lines=template_lines,
            duration_seconds=duration_seconds,
            device_type=device_type,
            notes_wide=notes_wide,
            notes_tall=notes_tall,
            line_metadata=line_metadata,
            transition_strategy=transition_strategy,
            transition_interval_ms=transition_interval_ms,
            transition_step_size=transition_step_size,
            clear_transition_override=clear_transition_override,
        )

    @_tool(destructive=True)
    def delete_page(page_id: str) -> dict[str, Any]:
        """Delete a page permanently.

        WARNING: This cannot be undone. If this is the last page, a default
        welcome page will be created automatically.

        Args:
            page_id: The page identifier (from list_pages()).
        """
        return ops_executors.delete_page(page_id)

    @_tool(read_only=True)
    def render_page_preview(
        template_lines: list[str],
        device_type: str = "flagship",
        line_metadata: list[dict[str, Any]] | None = None,
        notes_wide: int = 1,
        notes_tall: int = 1,
    ) -> dict[str, Any]:
        """Render a template to see how it will look BEFORE saving it as a page.

        Use this to iterate on a design without creating (and then having to
        delete) throwaway pages. Substitutes live plugin values into the
        template just like the real renderer would, then returns the resulting
        grid with newlines between rows.

        Args:
            template_lines: Template strings to render (one per row). Extra
                            rows are dropped; missing rows are filled with blanks.
            device_type: 'flagship' (22×6), 'note' (15×3), or 'note_array'
                         (15·notes_wide × 3·notes_tall).
            line_metadata: Optional per-line dicts with "alignment"
                           ('left'/'center'/'right') and "wrap" (bool) — the
                           same metadata saved pages carry. Include it to
                           preview alignment and wrap faithfully.
            notes_wide: For note_array — Notes across (1–8). Ignored otherwise.
            notes_tall: For note_array — Notes down (1–8). Ignored otherwise.

        Returns:
            {
              "rendered": "<grid string with \\n between rows>",
              "device_type": "flagship",
              "rows": 6, "cols": 22,
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
        # render_lines' own never-crash fallback. A note_array is sized from
        # notes_wide × notes_tall, exactly as a saved page's geometry is.
        render_device_type = device_type or DEFAULT_DEVICE_TYPE
        try:
            dims = resolve_dimensions(render_device_type, notes_wide, notes_tall)
        except ValueError:
            render_device_type = DEFAULT_DEVICE_TYPE
            dims = resolve_dimensions(render_device_type)
        context = engine._build_context(BoardContext(render_device_type, rows=dims.rows, cols=dims.cols))
        rendered = engine.render_lines(
            template_lines,
            context=context,
            line_metadata=line_metadata,
            device_type=device_type,
            notes_wide=notes_wide,
            notes_tall=notes_tall,
        )
        return {
            "rendered": rendered,
            "device_type": device_type,
            "rows": dims.rows,
            "cols": dims.cols,
            "context_plugins": sorted(context.keys()),
        }

    @_tool(read_only=True)
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

    @_tool(read_only=True)
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

    @_tool(read_only=True)
    def list_formula_functions() -> dict[str, Any]:
        """List every function usable inside a {{= ...}} template expression.

        The reference behind the editor's function picker: conditionals,
        arithmetic, text and date helpers, each with its signature and a
        one-line summary. Use it when writing formulas for a page template
        or a variable-mode collection rule, before validate_template().

        Returns: {functions: {NAME: {category, signature, summary}}}.
        """
        from .templates.expressions import function_signatures

        return {"functions": _serialize(function_signatures())}

    # -----------------------------------------------------------------------
    # Page sharing — the editor's Share / Import buttons and the staff-picks
    # gallery. Share strings are the portable base64url envelope
    # src.pages.share produces; a string from another install imports here.
    # -----------------------------------------------------------------------

    @_tool(read_only=True)
    def export_page(page_id: str) -> dict[str, Any]:
        """Export a page as a portable share string (the editor's Share button).

        The string encodes the page's content — name, template, line_metadata,
        duration and transition override — but never its id or timestamps.
        Give it to another FiestaBoard user; import_page() recreates the page.
        Read-only: nothing changes on this install.

        Args:
            page_id: The page identifier (from list_pages()).

        Returns: {page_id, name, device_type, share_string}.
        """
        from .pages.service import get_page_service
        from .pages.share import encode_page

        page = get_page_service().get_page(page_id)
        if page is None:
            raise ToolError(f"Page '{page_id}' not found.")
        return {
            "page_id": page.id,
            "name": page.name,
            "device_type": page.device_type,
            "share_string": encode_page(page),
        }

    @_tool(destructive=False)
    def import_page(share_string: str) -> dict[str, Any]:
        """Create a NEW page from a share string (the editor's Import button).

        Every call creates another page — importing the same string twice
        gives two pages. The imported page is not shown on any board until
        you set_active_page() or schedule it.

        Args:
            share_string: A share string from export_page() or another
                          FiestaBoard user. Malformed strings are reported
                          as errors and nothing is created.

        Returns: {status, message, page_id, name, device_type}.
        """
        return ops_executors.import_page(share_string)

    @_tool(read_only=True)
    def list_staff_picks() -> list[dict[str, Any]] | dict[str, Any]:
        """List the curated staff-pick pages that ship with FiestaBoard.

        Each entry has id (use it with import_staff_pick()), name,
        description, device_type, tags, and required_plugins — the plugins
        its template references, which must be installed and enabled
        (list_installed_plugins()) for the page to render without '???'.
        Share strings are deliberately not included here.
        """
        from .staff_picks.routes import _load_staff_picks

        picks = _load_staff_picks()
        return _serialize([{k: v for k, v in pick.items() if k != "share_string"} for pick in picks])

    @_tool(destructive=False)
    def import_staff_pick(pick_id: str) -> dict[str, Any]:
        """Create a NEW page from a staff pick (the gallery's Add button).

        Every call creates another page. Check the pick's required_plugins
        from list_staff_picks() and install/enable them first, or the page
        will render '???' where their variables are.

        Args:
            pick_id: The staff pick identifier (from list_staff_picks()).

        Returns: {status, message, page_id, name, device_type, pick_id,
        required_plugins}.
        """
        return ops_executors.import_staff_pick(pick_id)

    @_tool(read_only=True)
    def get_current_display(board_id: str | None = None) -> dict[str, Any]:
        """The page a board is showing right now, with its raw template content.

        Resolves schedule mode and collections to the concrete page, like
        get_active_page(), but returns the CONTENT: for a template page the
        raw template ({{variables}} intact) plus its line_metadata, so you can
        start a new page from it; for other page types the rendered rows and
        line_metadata null. Read-only.

        Args:
            board_id: Board to inspect on a multi-board install (from the boards
                      list in get_settings_summary()). Omitted = the primary board.

        Returns: {board_id, page_id, page_name, page_type, device_type,
        notes_wide, notes_tall, template: [rows], line_metadata}.
        """
        from .collections.models import is_collection_id
        from .pages.service import get_page_service
        from .settings.service import get_settings_service

        svc = get_settings_service()
        if board_id is not None:
            boards = svc.get_board_settings().boards or []
            if not any(isinstance(b, dict) and b.get("id") == board_id for b in boards):
                raise ToolError(f"Board not found: {board_id}")

        # Mirrors GET /pages/current-display, with a board_id so a secondary
        # board's content is reachable too (the REST route is primary-only).
        if svc.is_schedule_enabled(board_id):
            from .schedules.service import get_schedule_service
            from .time_service import get_time_service

            now = get_time_service().get_current_time()
            active_ref = get_schedule_service().get_active_page_id(
                now.time(), now.strftime("%A").lower(), board_id=board_id
            )
        else:
            active_ref = svc.get_active_page_id(board_id)
        if not active_ref:
            where = f" for board '{board_id}'" if board_id is not None else ""
            raise ToolError(f"No active page set{where}.")

        if is_collection_id(active_ref):
            from .collections.service import get_collection_service

            active_ref = get_collection_service().resolve_page_id(active_ref)
            if not active_ref:
                raise ToolError("Collection could not be resolved to a page.")

        page_service = get_page_service()
        page = page_service.get_page(active_ref)
        if page is None:
            raise ToolError(f"Active page '{active_ref}' not found.")

        if page.type == "template" and page.template:
            template = list(page.template)
            line_metadata = [m.model_dump() for m in page.line_metadata] if page.line_metadata else None
        else:
            result = page_service.preview_page(page.id, force_refresh=True)
            template = result.formatted.split("\n") if result is not None and result.available else []
            line_metadata = None

        return {
            "board_id": board_id,
            "page_id": page.id,
            "page_name": page.name,
            "page_type": page.type,
            "device_type": page.device_type,
            "notes_wide": page.notes_wide,
            "notes_tall": page.notes_tall,
            "template": template,
            "line_metadata": line_metadata,
        }

    # -----------------------------------------------------------------------
    # Transition Lab (beta) — the /transitions endpoints. Gated behind
    # Settings → Beta → transition plugins, exactly like the REST routes.
    # -----------------------------------------------------------------------

    @_tool(read_only=True)
    def list_transition_plugins() -> dict[str, Any]:
        """List installed transition plugins (frame-by-frame board animations).

        Each entry has id, name, description, settings_schema (its config
        form), transition_settings (its frame/runtime caps), config (its
        current bound config) and strategy — the 'plugin:<id>' string to
        store as a page's transition_strategy via update_page(), or as the
        system transition via update_setting('transitions', ...).

        Transition plugins are a beta: while Settings → Beta has them off
        this reports an error, the same way the web UI hides the picker.
        """
        from .transitions import service as transitions

        refusal = ops_executors._transition_beta_refusal()
        if refusal is not None:
            return refusal
        return {"plugins": _serialize(transitions.list_installed_transition_plugins())}

    @_tool(destructive=False)
    async def test_transition_live(
        plugin_id: str,
        to_page_id: str,
        from_page_id: str | None = None,
        config: dict[str, Any] | None = None,
        board_id: str | None = None,
    ) -> dict[str, Any]:
        """Run a transition plugin ONCE on the real board (the Transition Lab).

        Snaps from_page_id onto the board (when given), then animates to
        to_page_id with the plugin. The board is LEFT showing to_page_id —
        call restore_board() afterwards, or wait for the display loop to put
        the active page back. Does not change which page is active.

        A paused board or an active silence window returns status "blocked"
        (deliberate policy — relay it to the user, don't retry). Beta-gated
        like list_transition_plugins().

        Args:
            plugin_id: The transition plugin (from list_transition_plugins()).
            to_page_id: The page the transition lands on (from list_pages()).
            from_page_id: Optional page shown first so the animation visibly
                          starts from it. Omitted = whatever the board shows now.
            config: Optional per-run overrides merged over the plugin's
                    current config (keys from its settings_schema).
            board_id: Board to target on a multi-board install (from the boards
                      list in get_settings_summary()). Omitted = the primary board.

        Returns: {status, message, sent, plugin_id, from_page_id, to_page_id, board_id}.
        """
        return await ops_executors.test_transition_live(
            plugin_id,
            to_page_id,
            from_page_id=from_page_id,
            config=config,
            board_id=board_id,
        )

    @_tool(destructive=False, idempotent=True)
    async def restore_board(board_id: str | None = None) -> dict[str, Any]:
        """Snap a board back to its active page after test_transition_live().

        Re-renders the board's active page and sends it plainly (no
        transition), cancelling any still-running plugin transition. Safe to
        repeat. A paused board or an active silence window returns status
        "blocked". Beta-gated like list_transition_plugins().

        Args:
            board_id: Board to restore on a multi-board install (from the boards
                      list in get_settings_summary()). Omitted = the primary board.

        Returns: {status, message, page_id, sent, board_id}.
        """
        return await ops_executors.restore_board(board_id=board_id)

    # -----------------------------------------------------------------------
    # Schedule tools
    # -----------------------------------------------------------------------

    @_tool(read_only=True)
    def list_schedules(board_id: str | None = None) -> dict[str, Any]:
        """List a board's schedule entries, with today's resolved times, exactly as the Schedules page shows them.

        Mirrors GET /v1/schedules. Each entry carries the stored fields
        (id, page_id, start_time/end_time in HH:MM, day_pattern, custom_days,
        recurrence_type with annual_date/annual_end_date or
        one_off_date/one_off_end_date, start_type/end_type with the sun
        offsets, enabled, board_id) plus resolved_start_time /
        resolved_end_time — the actual HH:MM for today, which differs from the
        stored value only for sunrise/sunset entries. end_time null means the
        entry runs until the next one starts.

        Args:
            board_id: Board to list (from the boards list in
                      get_settings_summary()). Omitted = the primary board.
                      Pass "*" for every board's entries at once — then
                      default_page_id and schedule_enabled are null, since
                      they are per-board.

        Returns: {schedules: [...], total, board_id, default_page_id (the page
        shown in schedule gaps — change it with set_default_page()),
        schedule_enabled (whether schedule mode drives this board — change it
        with set_schedule_mode())}.
        """
        from .schedules.routes import _enrich_schedule_with_sun_times
        from .schedules.service import get_schedule_service
        from .settings.service import get_settings_service

        svc = get_schedule_service()
        if board_id == "*":
            entries = [_enrich_schedule_with_sun_times(s.model_dump()) for s in svc.list_schedules(board_id="*")]
            return {
                "schedules": _serialize(entries),
                "total": len(entries),
                "board_id": "*",
                "default_page_id": None,
                "schedule_enabled": None,
            }

        settings = get_settings_service()
        if board_id is not None and not any(
            isinstance(b, dict) and b.get("id") == board_id for b in (settings.get_board_settings().boards or [])
        ):
            raise ToolError(f"Board not found: {board_id}")
        target = ops_executors.resolve_board_id(board_id)
        entries = [_enrich_schedule_with_sun_times(s.model_dump()) for s in svc.list_schedules(board_id=target)]
        return {
            "schedules": _serialize(entries),
            "total": len(entries),
            "board_id": target,
            "default_page_id": svc.get_default_page(board_id=target),
            "schedule_enabled": bool(settings.is_schedule_enabled(board_id=target)),
        }

    @_tool(read_only=True)
    def validate_schedules(board_id: str | None = None) -> dict[str, Any]:
        """Check a board's schedule for overlapping entries and uncovered gaps.

        The same check the Schedules page runs (POST /schedules/validate).
        Only enabled weekly entries take part; annual and one-off dates are
        intentional overrides and never count as conflicts. Sunrise/sunset
        entries are resolved to today's times first. Read-only.

        Args:
            board_id: Board to validate (from the boards list in
                      get_settings_summary()). Omitted = the primary board.

        Returns: {valid (false when any overlap exists), overlaps:
        [{schedule1_id, schedule2_id, conflict_description}], gaps:
        [{start_time, end_time, days}]}. Gaps are informational — the
        board shows default_page_id (see list_schedules()) during them.
        """
        from .schedules.service import get_schedule_service

        target = ops_executors.resolve_board_id(board_id)
        return _serialize(get_schedule_service().validate_schedules(board_id=target))

    @_tool(destructive=False)
    def create_schedule(
        page_id: str,
        start_time: str,
        day_pattern: str = "all",
        end_time: str | None = None,
        enabled: bool = True,
        custom_days: list[str] | None = None,
        board_id: str | None = None,
        recurrence_type: str | None = None,
        annual_date: str | None = None,
        annual_end_date: str | None = None,
        one_off_date: str | None = None,
        one_off_end_date: str | None = None,
        start_type: str | None = None,
        start_sun_offset: int | None = None,
        end_type: str | None = None,
        end_sun_offset: int | None = None,
    ) -> dict[str, Any]:
        """Create a new schedule entry to show a specific page at a specific time.

        Accepts every field the Schedules page's entry form saves. The
        simplest call is page_id + start_time: a weekly entry, every day,
        fixed times, on the primary board.

        Args:
            page_id: Which page (or collection) to display. Use IDs from list_pages()
                     or list_collections().
            start_time: When to start showing this page in HH:MM format (24h), e.g. "07:00".
                        For start_type 'sunrise'/'sunset' this is the fallback used
                        when no location is configured.
            day_pattern: When this applies — 'all' (every day), 'weekdays', 'weekends',
                         or 'custom' (then pass custom_days). Default: 'all'.
                         Only meaningful for weekly recurrence.
            end_time: When to stop in HH:MM format. Null means open-ended
                      (runs until the next schedule or end of day). Default: None.
            enabled: Whether this schedule is active. Default: True.
            custom_days: For day_pattern 'custom' — lowercase day names, e.g.
                         ["monday", "wednesday", "friday"].
            board_id: Board this entry belongs to (from the boards list in
                      get_settings_summary()). Omitted = the primary board.
            recurrence_type: 'weekly' (default; uses day_pattern), 'annual_date'
                             (repeats every year on annual_date) or 'one_off_date'
                             (a single calendar date). Date entries override
                             weekly ones while their date is active.
            annual_date: For 'annual_date' — "MM-DD", e.g. "12-25".
            annual_end_date: Optional "MM-DD" end of a multi-day annual window
                             (may wrap the year, e.g. "12-30" to "01-02").
            one_off_date: For 'one_off_date' — "YYYY-MM-DD".
            one_off_end_date: Optional "YYYY-MM-DD" end of a multi-day one-off window.
            start_type: 'fixed' (default, uses start_time), 'sunrise' or 'sunset'
                        (computed daily from the location setting).
            start_sun_offset: Minutes relative to the sun event for start_type
                              'sunrise'/'sunset' — positive = after, negative = before.
            end_type: 'fixed' (default, uses end_time), 'sunrise' or 'sunset'.
            end_sun_offset: Minutes relative to the sun event for end_type.
        """
        return ops_executors.create_schedule(
            page_id=page_id,
            start_time=start_time,
            day_pattern=day_pattern,
            end_time=end_time,
            enabled=enabled,
            custom_days=custom_days,
            board_id=board_id,
            recurrence_type=recurrence_type,
            annual_date=annual_date,
            annual_end_date=annual_end_date,
            one_off_date=one_off_date,
            one_off_end_date=one_off_end_date,
            start_type=start_type,
            start_sun_offset=start_sun_offset,
            end_type=end_type,
            end_sun_offset=end_sun_offset,
        )

    @_tool(destructive=False, idempotent=True)
    def update_schedule(
        schedule_id: str,
        page_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        day_pattern: str | None = None,
        enabled: bool | None = None,
        clear_end_time: bool = False,
        clear_custom_days: bool = False,
        custom_days: list[str] | None = None,
        board_id: str | None = None,
        recurrence_type: str | None = None,
        annual_date: str | None = None,
        annual_end_date: str | None = None,
        one_off_date: str | None = None,
        one_off_end_date: str | None = None,
        start_type: str | None = None,
        start_sun_offset: int | None = None,
        end_type: str | None = None,
        end_sun_offset: int | None = None,
        clear_annual_end_date: bool = False,
        clear_one_off_end_date: bool = False,
    ) -> dict[str, Any]:
        """Update an existing schedule entry.

        Only the fields you provide will be changed. Every field
        create_schedule() accepts can be changed here; the clear_* flags
        exist because omitting a field means "unchanged", so an explicit
        null cannot express a clear.

        Args:
            schedule_id: The schedule identifier (from list_schedules()).
            page_id: New page or collection to display (optional).
            start_time: New start time in HH:MM format (optional).
            end_time: New end time in HH:MM format (optional; omitted = unchanged).
            day_pattern: New day pattern: 'all', 'weekdays', 'weekends', 'custom' (optional).
            enabled: Enable or disable this schedule entry (optional).
            clear_end_time: Set True to remove the end time, making the entry
                open-ended.
            clear_custom_days: Set True to drop a stored custom day list
                (e.g. when changing day_pattern away from 'custom').
            custom_days: New day list for day_pattern 'custom' (lowercase names).
            board_id: Move the entry to another board (from the boards list in
                      get_settings_summary()).
            recurrence_type: 'weekly', 'annual_date' or 'one_off_date'.
            annual_date: New "MM-DD" for annual recurrence.
            annual_end_date: New "MM-DD" end of the annual window.
            one_off_date: New "YYYY-MM-DD" for a one-off entry.
            one_off_end_date: New "YYYY-MM-DD" end of the one-off window.
            start_type: 'fixed', 'sunrise' or 'sunset'.
            start_sun_offset: Minutes relative to the start sun event (+after/-before).
            end_type: 'fixed', 'sunrise' or 'sunset'.
            end_sun_offset: Minutes relative to the end sun event (+after/-before).
            clear_annual_end_date: Set True to make an annual entry a single day again.
            clear_one_off_end_date: Set True to make a one-off entry a single day again.
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
            custom_days=custom_days,
            board_id=board_id,
            recurrence_type=recurrence_type,
            annual_date=annual_date,
            annual_end_date=annual_end_date,
            one_off_date=one_off_date,
            one_off_end_date=one_off_end_date,
            start_type=start_type,
            start_sun_offset=start_sun_offset,
            end_type=end_type,
            end_sun_offset=end_sun_offset,
            clear_annual_end_date=clear_annual_end_date,
            clear_one_off_end_date=clear_one_off_end_date,
        )

    @_tool(destructive=False, idempotent=True)
    def set_default_page(page_id: str | None, board_id: str | None = None) -> dict[str, Any]:
        """Set (or clear) the page a board falls back to when no schedule entry is active.

        This is the Schedules page's "default page" — what shows during the
        gaps validate_schedules() reports. Read it back from
        list_schedules() as default_page_id.

        Args:
            page_id: A page or collection ID (from list_pages() or
                     list_collections()), or null to clear the default so
                     gaps leave the board on whatever it last showed.
            board_id: Board to target (from the boards list in
                      get_settings_summary()). Omitted = the primary board.
        """
        return ops_executors.set_default_page(page_id, board_id=board_id)

    @_tool(destructive=True)
    def delete_schedule(schedule_id: str) -> dict[str, Any]:
        """Delete a schedule entry permanently.

        Args:
            schedule_id: The schedule identifier (from list_schedules()).
        """
        return ops_executors.delete_schedule(schedule_id)

    # -----------------------------------------------------------------------
    # Collection tools
    # -----------------------------------------------------------------------

    @_tool(read_only=True)
    def list_collections() -> list[dict[str, Any]] | dict[str, Any]:
        """List all collections (ordered page groups with a selection mode).

        Returns a list with:
        - id: use for update_collection(), delete_collection(), or as page_id in schedules
        - name, page_ids
        - selection_mode: "time" (rotate on interval), "variable" (pick by
          rule) or "random" (shuffle, never the same page twice in a row)
        - time / variable / random: mode-specific config block
        """
        from .collections.service import get_collection_service

        svc = get_collection_service()
        return _serialize(svc.list_collections())

    @_tool(destructive=False)
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
                live plugin data; "random" shows a random page per interval,
                never the same page twice in a row.
            interval_seconds: For time and random mode — how long to show
                each page (default 30). Range: 5–86400 (5 seconds to 24 hours).
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

    @_tool(destructive=False, idempotent=True)
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

        Pass only the fields you want to change. Mode-specific fields merge
        with what is stored, so a variable-mode collection can have just its
        poll_seconds or rules changed. To switch modes, send the new
        selection_mode (plus default_page_id when switching TO variable mode
        for the first time); interval_seconds is optional when switching to
        random — the current interval carries over.

        Args:
            collection_id: The collection identifier (from list_collections()).
            name: New name (optional).
            page_ids: New ordered list of page IDs (optional). Replaces entire list.
            selection_mode: New mode ("time", "variable" or "random").
            interval_seconds: New page duration (time and random mode).
            rules: New rule list (variable mode). Replaces the whole list.
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

    @_tool(destructive=True)
    def delete_collection(collection_id: str) -> dict[str, Any]:
        """Delete a collection permanently.

        Args:
            collection_id: The collection identifier (from list_collections()).
        """
        return ops_executors.delete_collection(collection_id)

    # -----------------------------------------------------------------------
    # System tools
    # -----------------------------------------------------------------------

    @_tool(read_only=True)
    async def get_system_status() -> dict[str, Any]:
        """Get the current status of the FiestaBoard system.

        Returns version, whether the display service is running, plugin system
        status, the number of installed/enabled plugins, plus:
        - running_version, release_channel ("stable" | "beta")
        - update: {auto_update_interval ("daily" | "weekly" | "monthly" |
          "manual"), updater_available (sidecar reachable — needed for
          trigger_system_update(), restart_system(), shutdown_system() and
          channel switches), managed_externally, last_check, last_update}.
          For whether a newer release exists, call check_for_update().
        - mqtt: {enabled, connected, running} — the live Home Assistant bridge
        - hdmi_kiosk: {supported, status, enabled} — the FiestaPi TV kiosk

        Blocks that cannot be read are reported as null rather than failing
        the whole status.
        """
        from .api_server import __version__, _service_running, get_service
        from .plugins import get_plugin_registry

        registry = get_plugin_registry()
        plugins = registry.list_plugins()
        service = get_service()
        status: dict[str, Any] = {
            "version": __version__,
            "service_running": _service_running and service is not None,
            "plugin_system_available": True,
            "plugins_installed": len(plugins),
            "plugins_enabled": sum(1 for p in plugins if p.get("enabled")),
            "running_version": None,
            "release_channel": None,
            "update": None,
            "mqtt": None,
            "hdmi_kiosk": None,
        }
        try:
            from .system import update_service

            state = update_service._system_update_state_load()
            has_token = bool(update_service._updater_token())
            status["running_version"] = update_service.running_version()
            status["release_channel"] = update_service.current_channel()
            status["update"] = {
                "auto_update_interval": update_service._resolve_auto_update_interval(state),
                "updater_available": bool(update_service._updater_probe()) if has_token else False,
                "managed_externally": bool(update_service._managed_externally()),
                "last_check": state.get("last_check"),
                "last_update": state.get("last_update"),
            }
        except Exception as exc:
            logger.debug("get_system_status: could not read update state: %s", exc)
        try:
            from .mqtt import get_mqtt_client
            from .settings.service import get_settings_service

            client = get_mqtt_client()
            status["mqtt"] = {
                "enabled": bool(get_settings_service().get_mqtt_settings().enabled),
                "connected": bool(client.is_connected()) if client else False,
                "running": bool(client.is_running()) if client else False,
            }
        except Exception as exc:
            logger.debug("get_system_status: could not read MQTT state: %s", exc)
        try:
            from .settings.routes import get_hdmi_kiosk_status

            status["hdmi_kiosk"] = _serialize(await get_hdmi_kiosk_status())
        except Exception as exc:
            logger.debug("get_system_status: could not read HDMI kiosk state: %s", exc)
        return status

    @_tool(read_only=True)
    def get_settings_summary() -> dict[str, Any]:
        """Get a summary of current FiestaBoard settings (non-sensitive fields only).

        Every block is keyed by the update_setting() category that changes it:
        - general: instance_name (the install's name), timezone, time_format,
          date_format, welcome_message
        - display, transitions, output, polling, location: as documented on
          update_setting()
        - silence_schedule: the install-wide quiet-hours config, plus
          by_board overrides keyed by board id
        - beta: https_enabled, transition_plugins_enabled
        - plugins: auto_update
        - mqtt: enabled, broker_host, broker_port, external_url, username and
          password masked as "***" when set
        - ai: enabled, default_provider_id, providers (id, name, protocol,
          base_url, models, default_model; api_key masked as "***" when set)
        - schedule: {enabled} — whether schedule mode drives the primary board
        - active_page_id: the primary board's manually-selected page (or null)
        - boards: one entry per configured board with id, name, device_type,
          rows/cols, notes_wide/notes_tall, board_color, code62_glyph,
          api_mode, has_host, has_credentials, primary, enabled, paused,
          schedule_enabled, active_page_id, and error (why the board failed to
          initialize, or null). Use a board's id as the board_id argument to
          board-targeting tools, and its rows/cols to size templates for it.

        Release channel, auto-update interval, MQTT connection and HDMI kiosk
        state are on get_system_status(). Credentials (board API keys, Wi-Fi,
        MQTT password, AI api_key, MCP token, login) are never returned.
        """
        from .config_manager import get_config_manager
        from .settings.service import get_settings_service

        svc = get_settings_service()
        summary: dict[str, Any] = {}
        for key, fetch in (
            ("display", svc.get_display_settings),
            ("location", svc.get_location_settings),
            ("output", svc.get_output_settings),
            ("transitions", svc.get_transition_settings),
            ("polling", svc.get_polling_settings),
            ("beta", svc.get_beta_settings),
            ("plugins", svc.get_plugin_settings),
        ):
            try:
                summary[key] = _serialize(fetch())
            except Exception as exc:
                logger.debug(
                    "get_settings_summary: could not fetch %s settings: %s",
                    key,
                    exc,
                )

        # Blocks that carry credentials go through the config manager's
        # masking so a set secret reads as "***" and an unset one as "".
        try:
            cm = get_config_manager()
            general = cm.get_general() or {}
            summary["general"] = {key: general.get(key) for key in ops_executors.GENERAL_SETTING_KEYS}
            summary["silence_schedule"] = _serialize(cm.get_feature("silence_schedule") or {})
            ai = _mask_settings_block(cm, cm.get_ai_providers())
            for provider in ai.get("providers", []) or []:
                if isinstance(provider, dict):
                    provider.pop("headers", None)  # may carry an Authorization header
            # The chat's approval policy is the user's, not the assistant's
            # to read back and act on (update_setting refuses it); the loop's
            # system prompt already says how destructive tools behave.
            ai.pop("approval_mode", None)
            summary["ai"] = ai
            mqtt = _mask_settings_block(cm, svc.get_mqtt_settings())
            if mqtt.get("username"):
                mqtt["username"] = "***"
            summary["mqtt"] = mqtt
        except Exception as exc:
            logger.debug("get_settings_summary: could not fetch config-manager blocks: %s", exc)

        # Schedule mode + active page (#1765): the troubleshoot prompt
        # walks both, and until now no tool returned them.
        try:
            summary["schedule"] = {"enabled": bool(svc.is_schedule_enabled())}
            summary["active_page_id"] = svc.get_active_page_id()
        except Exception as exc:
            logger.debug("get_settings_summary: could not fetch schedule/active page: %s", exc)

        summary["boards"] = _boards_summary(svc)
        return summary

    @_tool(destructive=False, idempotent=True)
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

    @_tool(destructive=False, idempotent=True)
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

    @_tool(destructive=False, idempotent=True)
    async def update_setting(category: str, values: dict[str, Any]) -> dict[str, Any]:
        """Change one category of non-credential settings.

        Only the keys you pass change; everything else in the category is
        left as it is. Read the current values first with
        get_settings_summary() (and get_system_status() for the system
        categories). Unknown keys are refused, not ignored.

        Args:
            category: Which settings group to change. One of 'general',
                'display', 'transitions', 'output', 'polling', 'location',
                'silence_schedule', 'schedule_behavior', 'active_page', 'beta',
                'plugins', 'mqtt', 'ai', 'release_channel', 'auto_update', or
                'hdmi_kiosk'.
            values: The keys to change within that category — see "Keys
                per category" below.

        Keys per category:
                - general: instance_name (string — the install's name, shown
                  in the UI and on the network; this is how you rename the
                  board/instance), timezone (IANA name, e.g.
                  "America/New_York"), time_format ("12h" | "24h"),
                  date_format ("MM/DD/YYYY" | "DD/MM/YYYY" | "YYYY-MM-DD"),
                  welcome_message (string, "" = default).
                - display (the on-screen board preview, not the physical
                  board): reduce_motion (bool), board_animations
                  ("on" | "desktop" | "off"), site_animations ("on" | "off"),
                  board_flap_speed ("hardware" | "quick" | "standard" |
                  "relaxed", or a millisecond count).
                - transitions (how the physical board animates between
                  pages): strategy (string), step_interval_ms (int),
                  step_size (int).
                - output: target ("ui" | "board" | "both").
                - polling: interval_seconds (int) — how often plugins
                  refresh; board_read_interval_local / _cloud (int seconds).
                - location: latitude (float), longitude (float) — used by
                  sunrise/sunset schedules and location-aware plugins.
                - silence_schedule: enabled (bool), start_time and end_time
                  ("HH:MM"), mode ("freeze" | "page" | "indicator"), page_id,
                  indicator_text, indicator_position, board_id (optional —
                  writes that board's own override instead of the
                  install-wide schedule; boards without an override follow
                  the install-wide one).
                - schedule_behavior: defer_on_reenable (bool) — the
                  Schedules page's global toggle: when true, turning schedule
                  mode back on waits for the next entry's start instead of
                  switching the board immediately.
                - active_page: page_id (string), board_id (optional) — the
                  same selection set_active_page() makes.
                - beta: https_enabled (bool — needs a restart_system() to
                  take effect), transition_plugins_enabled (bool).
                - plugins: auto_update (bool — update installed plugins in
                  the background).
                - mqtt (Home Assistant bridge): enabled (bool), broker_host
                  (string), broker_port (int), external_url (string).
                  username and password are set by the user in the web UI.
                - ai (the in-app assistant): enabled (bool),
                  default_provider_id (string), providers (list replacing the
                  provider list; each entry: id, name, protocol
                  ("openai" | "anthropic"), base_url, models (list),
                  default_model). Existing providers keep their stored
                  api_key; a new provider is saved without one until the
                  user adds it in the web UI. Never pass api_key or headers.
                - release_channel: channel ("stable" | "beta") — switches the
                  install's update channel via the updater sidecar; the
                  container restarts on the new image.
                - auto_update: interval ("daily" | "weekly" | "monthly" |
                  "manual") — how often FiestaBoard updates itself.
                - hdmi_kiosk: enabled (bool) — the FiestaPi's HDMI TV kiosk
                  (FiestaPi with the updater sidecar only).

        Secrets are refused by name: api_key, password, username, headers,
        token, local_api_key, cloud_key, note_array_token. Ask the user to
        enter those in the web UI's Settings page.
        """
        return await ops_executors.update_setting(category, values)

    @_tool(read_only=True)
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
        collection resolution), page (summary of the resolved page, or null),
        temporary_override (the same status get_temporary_override() returns;
        when active it wins over source/active_ref on the primary board)}.
        """
        from .collections.models import is_collection_id
        from .settings.service import get_settings_service, temporary_override_payload

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
            "temporary_override": temporary_override_payload(svc.get_temporary_override()),
        }

    @_tool(read_only=True)
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

    @_tool(destructive=False)
    def send_message(text: str, board_id: str | None = None) -> dict[str, Any]:
        """Send a one-off text message directly to a board.

        The text is word-wrapped to the board's width; real newlines are
        honored; single-brace color markers like {red} or {63} render as one
        colored tile each. This bypasses pages entirely — the message stays
        up until the active page next changes or the display refreshes.

        A paused board or active silence mode returns status "blocked"
        (deliberate policy — relay it to the user, don't retry). A message
        sent inside the board's minimum send interval is DROPPED by the
        board, not queued: that is an error whose text names the window
        (e.g. "at most one message every 15s") — wait it out, then retry.

        Args:
            text: The message text to display.
            board_id: Board to target on a multi-board install (from the boards
                      list in get_settings_summary()). Omitted = the primary board.
        """
        return ops_executors.send_message(text, board_id=board_id)

    # -----------------------------------------------------------------------
    # Board state tools — the Home page's controls
    #
    # The temporary override and the forced resend are install-wide: one
    # override store, applied by the display loop to the primary board only;
    # one refresh pass over every board. They take no board_id because the
    # REST routes behind them take none, and a parameter the store cannot
    # honor would be a lie in the schema.
    # -----------------------------------------------------------------------

    @_tool(read_only=True)
    def get_temporary_override() -> dict[str, Any]:
        """Whether a temporary override is showing on the primary board, and what it is.

        Mirrors GET /settings/temporary-override. An override is a saved
        page or a one-off message put up by set_temporary_override(); while
        active it wins over the schedule and the manually selected page.

        Returns: {active, page_id (saved-page form), template (one-off form),
        line_metadata, device_type, notes_wide, notes_tall, expires_at (ISO
        UTC, or null for an indefinite override), remaining_seconds (null when
        indefinite or inactive), revert_mode, revert_page_id}. Every field but
        active is null when nothing is active.
        """
        from .settings.service import get_settings_service, temporary_override_payload

        return temporary_override_payload(get_settings_service().get_temporary_override())

    @_tool(destructive=False, idempotent=False)
    async def set_temporary_override(
        page_id: str | None = None,
        template_lines: list[str] | None = None,
        line_metadata: list[dict[str, Any]] | None = None,
        device_type: str | None = None,
        notes_wide: int | None = None,
        notes_tall: int | None = None,
        duration_minutes: int | None = None,
        revert_mode: str = "schedule",
        revert_page_id: str | None = None,
    ) -> dict[str, Any]:
        """Temporarily show a saved page or a composed one-off on the primary board.

        The Home page's "force set" and "compose" actions (POST
        /settings/temporary-override). Supply EITHER page_id OR
        template_lines, never both. Unlike send_message(), the override
        survives display refreshes and reverts on its own when it expires;
        it also deliberately beats silence mode and pause. Check
        get_temporary_override() to read it back; cancel_temporary_override()
        ends it early.

        Args:
            page_id: Saved page or collection to show (from list_pages() or
                     list_collections()).
            template_lines: One-off board content instead of a saved page —
                            template strings, one per row, never persisted as
                            a page. Use render_page_preview() to iterate first.
            line_metadata: Optional per-line {"alignment", "wrap"} dicts for
                           the one-off form (same shape as saved pages).
            device_type: Geometry the one-off content was composed for:
                         'flagship' (default), 'note' or 'note_array'.
            notes_wide: note_array only — notes across (1–8).
            notes_tall: note_array only — notes down (1–8).
            duration_minutes: How long to show it, 1–480. Omit for an
                              indefinite override that stays until cancelled.
            revert_mode: What happens when a timed override expires:
                         'schedule' (default — resume schedule/manual page),
                         'blank' (clear the board) or 'page' (switch the
                         active page to revert_page_id).
            revert_page_id: Required when revert_mode is 'page'.
        """
        return await ops_executors.set_temporary_override(
            page_id=page_id,
            template_lines=template_lines,
            line_metadata=line_metadata,
            device_type=device_type,
            notes_wide=notes_wide,
            notes_tall=notes_tall,
            duration_minutes=duration_minutes,
            revert_mode=revert_mode,
            revert_page_id=revert_page_id,
        )

    @_tool(destructive=False, idempotent=True)
    async def cancel_temporary_override() -> dict[str, Any]:
        """End the active temporary override now and let the primary board revert.

        Mirrors DELETE /settings/temporary-override. A 'page' revert mode is
        applied immediately; the board re-renders on the next tick. Calling
        this when nothing is active is a harmless no-op (was_active: false).

        Returns: {status, message, was_active, revert_mode}.
        """
        return await ops_executors.cancel_temporary_override()

    @_tool(destructive=False, idempotent=True)
    async def force_refresh() -> dict[str, Any]:
        """Resend the active content to every board even if it looks unchanged.

        The Home page's "Resend to board" (POST /force-refresh): clears the
        unchanged-content caches and drives one send pass. Use it when the
        flaps disagree with what get_active_page() says should be showing.
        Respects pause and a UI-only output target — then sent is false.

        Returns: {status, message, sent}.
        """
        return await ops_executors.force_refresh()

    @_tool(read_only=True)
    async def get_silence_status(board_id: str | None = None) -> dict[str, Any]:
        """Whether a board is inside its silence (quiet hours) window right now.

        Mirrors GET /silence-status. Silence mode suppresses sends so the
        board does not clack at night; send_message() comes back "blocked"
        while it is active. The window itself is changed with
        update_setting('silence_schedule', ...).

        Args:
            board_id: Board to read (from the boards list in
                      get_settings_summary()). Omitted = the primary board.

        Returns: {enabled, active, start_time_utc, end_time_utc,
        current_time_utc, next_change_utc, seconds_until_next_change (null
        when disabled), mode ('freeze' | 'page' | 'indicator'), page_id,
        indicator_text, indicator_position, board_id}.
        """
        from .service_api.routes import get_silence_status as _rest_silence_status

        return _serialize(await _rest_silence_status(board_id))

    @_tool(destructive=False, idempotent=True)
    def pause_board(board_id: str | None = None) -> dict[str, Any]:
        """Pause a board: nothing is written to it until resume_board().

        The Home page's pause toggle (PATCH /v1/boards/{id} paused=true).
        Every code path stops — the display loop, schedules, plugin
        triggers, MQTT, send_message(). The board keeps showing whatever is
        on it. Reversible with resume_board(); read the state back from the
        boards list in get_settings_summary().

        Args:
            board_id: Board to pause (from the boards list in
                      get_settings_summary()). Omitted = the primary board.
        """
        return ops_executors.pause_board(board_id=board_id)

    @_tool(destructive=False, idempotent=True)
    def resume_board(board_id: str | None = None) -> dict[str, Any]:
        """Resume a paused board so it receives writes again.

        The Home page's pause toggle (PATCH /v1/boards/{id} paused=false).
        The next display tick re-sends the active content.

        Args:
            board_id: Board to resume (from the boards list in
                      get_settings_summary()). Omitted = the primary board.
        """
        return ops_executors.resume_board(board_id=board_id)

    # Board hardware tools (Settings → Boards). Non-secret fields only; board
    # API keys and note-array tokens are entered by the user in the web UI.
    # -----------------------------------------------------------------------

    @_tool(destructive=False, idempotent=True)
    async def update_board(
        board_id: str,
        name: str | None = None,
        device_type: str | None = None,
        notes_wide: int | None = None,
        notes_tall: int | None = None,
        board_color: str | None = None,
        code62_glyph: str | None = None,
        api_mode: str | None = None,
        host: str | None = None,
    ) -> dict[str, Any]:
        """Rename, retype, resize or reconfigure one board's non-secret hardware fields.

        Only the fields you pass change. Read the roster first with
        get_settings_summary() (the boards list). Changing device_type or the
        note-array grid changes the board's rows/cols, so pages sized for the
        old shape stop fitting — check with preview_saved_page() afterwards.

        Args:
            board_id: The board to change (from the boards list in get_settings_summary()).
            name: New display name (trimmed; empty restores the default "My Board").
            device_type: 'flagship' (22×6), 'note' (15×3) or 'note_array'
                (a grid of Notes; set notes_wide/notes_tall too).
            notes_wide: Note-array width in Notes (1–8).
            notes_tall: Note-array height in Notes (1–8).
            board_color: 'black' or 'white' — the physical board's colour,
                used by previews and FiestaPanels.
            code62_glyph: 'degree' or 'heart' — which glyph this Flagship's
                character-62 flap carries (display only; Flagship only).
            api_mode: 'local' (LAN API) or 'cloud' (Vestaboard cloud API).
                The matching credential must be entered by the user in the
                web UI.
            host: IP address or hostname of the board on the LAN (local API
                mode). Write-only: the summary reports has_host, never the
                address.
        """
        return await ops_executors.update_board(
            board_id,
            name=name,
            device_type=device_type,
            notes_wide=notes_wide,
            notes_tall=notes_tall,
            board_color=board_color,
            code62_glyph=code62_glyph,
            api_mode=api_mode,
            host=host,
        )

    @_tool(destructive=False)
    async def add_board(
        device_type: str,
        name: str | None = None,
        api_mode: str | None = None,
        notes_wide: int | None = None,
        notes_tall: int | None = None,
        board_color: str | None = None,
        host: str | None = None,
    ) -> dict[str, Any]:
        """Add another board to this install (multi-board driving).

        The board is added without credentials: tell the user to open
        Settings → Boards and enter its API key (or enable the local API)
        — until then it fails to initialize and the boards summary says so.

        Args:
            device_type: 'flagship', 'note' or 'note_array'.
            name: Display name (default: "My Board", "My Board 2", ...).
            api_mode: 'local' or 'cloud' (default 'local'; note arrays are
                usually 'cloud').
            notes_wide: Note-array width in Notes (1–8, note_array only).
            notes_tall: Note-array height in Notes (1–8, note_array only).
            board_color: 'black' or 'white'.
            host: IP address or hostname on the LAN (local API mode).
        """
        return await ops_executors.add_board(
            device_type,
            name=name,
            api_mode=api_mode,
            notes_wide=notes_wide,
            notes_tall=notes_tall,
            board_color=board_color,
            host=host,
        )

    @_tool(destructive=True)
    async def remove_board(board_id: str) -> dict[str, Any]:
        """Remove a board from this install permanently.

        WARNING: cannot be undone — the board's credentials go with it and
        the user has to re-enter them to add it back. The last board cannot be
        removed, and a board driven by a FiestaPanel must be removed via
        delete_panel() instead.

        Args:
            board_id: The board to remove (from the boards list in get_settings_summary()).
        """
        return await ops_executors.remove_board(board_id)

    @_tool(read_only=True)
    async def detect_board_size(board_id: str) -> dict[str, Any]:
        """Read a board's live layout to find its real device type and grid size.

        Use it when a board renders truncated or padded content — the stored
        device_type may not match the hardware. Nothing is written; apply the
        answer with update_board(). Not available for local-mode note arrays
        (their size is defined by their tile assignments).

        Args:
            board_id: The board to probe (from the boards list in get_settings_summary()).

        Returns: {board_id, device_type, rows, cols, notes_wide, notes_tall,
        matched_preset}.
        """
        return await ops_executors.detect_board_size(board_id)

    @_tool(destructive=False, idempotent=True)
    async def identify_tile(
        board_id: str,
        row: int | None = None,
        col: int | None = None,
        target: str = "tile",
    ) -> dict[str, Any]:
        """Flash a slot label onto a local note array's tiles so the user can see which Note sits where.

        Only for note arrays in local API mode with tiles already assigned in
        the web UI. The real frame comes back on the next display cycle.

        Args:
            board_id: The note-array board (from the boards list in get_settings_summary()).
            row: Tile row (0-based) when target is 'tile'.
            col: Tile column (0-based) when target is 'tile'.
            target: 'tile' (one slot, needs row and col) or 'all' (every
                configured tile at once).
        """
        return await ops_executors.identify_tile(board_id, row=row, col=col, target=target)

    # -----------------------------------------------------------------------
    # FiestaPanel tools (Settings → FiestaPanel): TV viewers backed by a
    # virtual board that is auto-fit to the screen.
    # -----------------------------------------------------------------------

    @_tool(read_only=True)
    async def list_panels() -> dict[str, Any]:
        """List the FiestaPanels (TV viewers) and the virtual board behind each.

        Each entry has id (use it for update_panel() / delete_panel()), name,
        board_id (the virtual board — appears in the boards list too and can
        be targeted like any board), screen_diagonal_inches, screen_aspect_w /
        _h, calibration_scale, animations_enabled, is_display (the panel the
        FiestaPi HDMI kiosk shows at /p/display), backdrop, auto_dim, and the
        board's device_type / rows / cols. short_code is the number the TV
        types into /p/<code>.
        """
        from .panels.routes import list_panels as _rest_list_panels

        return _serialize(await _rest_list_panels())

    @_tool(destructive=False)
    async def create_panel(
        name: str,
        screen_diagonal_inches: float = 55.0,
        screen_aspect_w: float = 16.0,
        screen_aspect_h: float = 9.0,
    ) -> dict[str, Any]:
        """Create a FiestaPanel — a browser viewer for a TV — with its own virtual board.

        The virtual board's grid is auto-fit from the screen size so every
        flap renders at real-world scale; no shape is chosen by hand. The new
        board appears in the boards list and can be targeted like any board.

        Args:
            name: Display name for the panel (the board is named "<name> (Panel)").
            screen_diagonal_inches: TV size in inches (3–200, default 55).
            screen_aspect_w: Aspect ratio width (default 16).
            screen_aspect_h: Aspect ratio height (default 9).
        """
        return await ops_executors.create_panel(
            name,
            screen_diagonal_inches=screen_diagonal_inches,
            screen_aspect_w=screen_aspect_w,
            screen_aspect_h=screen_aspect_h,
        )

    @_tool(destructive=False, idempotent=True)
    async def update_panel(
        panel_id: str,
        name: str | None = None,
        screen_diagonal_inches: float | None = None,
        screen_aspect_w: float | None = None,
        screen_aspect_h: float | None = None,
        calibration_scale: float | None = None,
        animations_enabled: bool | None = None,
        is_display: bool | None = None,
        backdrop: str | None = None,
        auto_dim: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Change a FiestaPanel's display settings. Only the fields you pass change.

        A screen-size change re-fits the virtual board's grid; pages authored
        for the old grid are reported back as incompatible_references.

        Args:
            panel_id: The panel (from list_panels()).
            name: New display name.
            screen_diagonal_inches: TV size in inches (3–200).
            screen_aspect_w: Aspect ratio width (1–100).
            screen_aspect_h: Aspect ratio height (1–100).
            calibration_scale: Fine size nudge, 0.85–1.15 (1.0 = true scale).
            animations_enabled: Whether tiles flip mechanically on the TV.
            is_display: True makes this THE local display panel served at
                /p/display (the FiestaPi HDMI kiosk); the previous holder is
                demoted automatically.
            backdrop: 'wall', 'dark' or 'none'.
            auto_dim: Night dimming window as {"enabled": bool,
                "start": "HH:MM", "end": "HH:MM"} on the TV's local clock.
        """
        return await ops_executors.update_panel(
            panel_id,
            name=name,
            screen_diagonal_inches=screen_diagonal_inches,
            screen_aspect_w=screen_aspect_w,
            screen_aspect_h=screen_aspect_h,
            calibration_scale=calibration_scale,
            animations_enabled=animations_enabled,
            is_display=is_display,
            backdrop=backdrop,
            auto_dim=auto_dim,
        )

    @_tool(destructive=True)
    async def delete_panel(panel_id: str) -> dict[str, Any]:
        """Delete a FiestaPanel and the virtual board behind it permanently.

        WARNING: cannot be undone. Pages and schedules that referenced the
        panel's board keep their references but no longer render anywhere.

        Args:
            panel_id: The panel (from list_panels()).
        """
        return await ops_executors.delete_panel(panel_id)

    # -----------------------------------------------------------------------
    # Network tools (Settings → Network, FiestaPi only). No scan/connect —
    # joining a network needs a passphrase, which the user enters in the UI.
    # -----------------------------------------------------------------------

    @_tool(destructive=True)
    async def disconnect_wifi() -> dict[str, Any]:
        """Drop the FiestaPi's active Wi-Fi connection.

        WARNING: if the user reaches FiestaBoard over that Wi-Fi, this cuts
        them off until the Pi reconnects (the saved profile is kept, so it
        usually auto-joins again) or they plug in Ethernet. FiestaPi only;
        other installs report that Wi-Fi management is unavailable.
        """
        return await ops_executors.disconnect_wifi()

    @_tool(destructive=True)
    async def forget_wifi_network(name: str) -> dict[str, Any]:
        """Delete a saved Wi-Fi profile so the FiestaPi stops auto-joining it.

        WARNING: cannot be undone here — re-joining needs the passphrase,
        which the user enters in Settings → Network. Forgetting the network
        currently in use disconnects the Pi. FiestaPi only.

        Args:
            name: The saved profile's name (usually the SSID) as listed in
                Settings → Network.
        """
        return await ops_executors.forget_wifi_network(name)

    # -----------------------------------------------------------------------
    # System tools (Settings → System / About / Backup / AI)
    # -----------------------------------------------------------------------

    @_tool(read_only=True, open_world=True)
    async def check_for_update() -> dict[str, Any]:
        """Check Docker Hub / GitHub for a newer FiestaBoard release on this install's channel.

        Returns {current_version, latest_version, update_available,
        package_url, error, is_production}. An unreachable registry comes
        back as error text, not a failure. Apply with trigger_system_update().
        """
        from .system.routes import system_update_check

        return _serialize(await system_update_check())

    @_tool(destructive=True, open_world=True)
    async def trigger_system_update() -> dict[str, Any]:
        """Pull the latest FiestaBoard release and restart onto it.

        WARNING: the container restarts and the web UI (and this connection)
        drop for a minute. A settings snapshot is taken first so the update
        can be rolled back from Settings → System. Needs the updater sidecar
        (get_system_status() → update.updater_available); otherwise the error
        carries the manual-update instructions to relay. Only call this when
        the user explicitly asks to update.
        """
        return await ops_executors.trigger_system_update()

    @_tool(destructive=True)
    async def restart_system() -> dict[str, Any]:
        """Restart the FiestaBoard container via the updater sidecar.

        WARNING: the web UI and this connection drop for ~5 seconds. Needed
        after enabling HTTPS (beta) or changing the polling interval. Needs
        the updater sidecar (get_system_status() → update.updater_available).
        """
        return await ops_executors.restart_system()

    @_tool(destructive=True)
    async def shutdown_system() -> dict[str, Any]:
        """Power off the host machine (FiestaPi) via the updater sidecar.

        WARNING: the host stays off until someone switches it on again by
        hand — there is no remote power-on. Only call this when the user
        explicitly asks to shut the device down.
        """
        return await ops_executors.shutdown_system()

    @_tool(read_only=True)
    def export_backup() -> dict[str, Any]:
        """Return the full backup document (config, settings, pages, collections, schedules, panels).

        The same document Settings → Backup downloads, with every credential
        masked as "***" — so it is a complete picture of the install for
        review or diffing, but a masked document cannot be restored as-is.
        For a restorable file the user downloads it from Settings → Backup.
        """
        from .backup import get_backup_service
        from .config_manager import get_config_manager

        return _mask_settings_block(get_config_manager(), get_backup_service().build_backup())

    @_tool(read_only=True, open_world=True)
    async def test_ai_provider(provider_id: str | None = None, model: str | None = None) -> dict[str, Any]:
        """Send a tiny smoke-test request to a configured AI provider to verify it works.

        Reports the provider's own verdict ({ok, message, model_used}) —
        "your key was rejected" is a result, not a failure. Provider ids are
        in get_settings_summary() → ai.providers.

        Args:
            provider_id: Which configured provider to test. Omitted = the
                default provider (or the first one).
            model: Model name to try instead of the provider's default_model.
        """
        from fastapi import HTTPException

        from .settings.models import AiTestRequest
        from .settings.routes import test_ai_provider as _rest_test_ai_provider

        try:
            result = await _rest_test_ai_provider(AiTestRequest(provider_id=provider_id, model=model))
        except HTTPException as exc:
            raise _rest_error(exc) from exc
        return _serialize(result)

    # -----------------------------------------------------------------------
    # Advanced / debug tools (Settings → Advanced). Out-of-band writes to a
    # board: same silence/pause gates as send_message, forced past the
    # unchanged-content dedupe.
    # -----------------------------------------------------------------------

    @_tool(destructive=False, idempotent=True)
    def blank_board(board_id: str | None = None) -> dict[str, Any]:
        """Clear a board — every tile to blank.

        The board stays blank until the active page next changes or the
        display refreshes. A paused board or active silence mode returns
        status "blocked" (deliberate policy — relay it, don't retry).

        Args:
            board_id: Board to target on a multi-board install (from the boards
                      list in get_settings_summary()). Omitted = the primary board.
        """
        return ops_executors.blank_board(board_id)

    @_tool(destructive=False, idempotent=True)
    def fill_board(character_code: int, board_id: str | None = None) -> dict[str, Any]:
        """Fill every tile of a board with one flap code — a quick hardware test.

        A paused board or active silence mode returns status "blocked".

        Args:
            character_code: Flap code 0–71: 0 blank, 1–26 A–Z, 27–36 digits
                0–9, 63–71 colour tiles (63 red, 64 orange, 65 yellow,
                66 green, 67 blue, 68 violet, 69 white, 70 black, 71 filled).
            board_id: Board to target on a multi-board install (from the boards
                      list in get_settings_summary()). Omitted = the primary board.
        """
        return ops_executors.fill_board(character_code, board_id)

    @_tool(destructive=False, idempotent=True)
    def show_board_debug_info(board_id: str | None = None) -> dict[str, Any]:
        """Show the support card (board IP, server IP, uptime, API mode, version, time) ON the board.

        Use it when the user is at the board and wants to check connectivity
        without the web UI. A paused board or active silence mode returns
        status "blocked".

        Args:
            board_id: Board to target on a multi-board install (from the boards
                      list in get_settings_summary()). Omitted = the primary board.
        """
        return ops_executors.show_board_debug_info(board_id)

    @_tool(read_only=True, open_world=True)
    async def run_network_diagnostics() -> dict[str, Any]:
        """Check DNS, internet reachability and the primary board's API from the FiestaBoard host.

        Use it when the board is unreachable or plugins report network
        errors. Returns per-step results and recommendations; nothing is
        changed.
        """
        from fastapi import HTTPException

        from .debug.routes import debug_network_diagnostics

        try:
            result = await debug_network_diagnostics()
        except HTTPException as exc:
            raise _rest_error(exc) from exc
        return _serialize(result)

    @_tool(destructive=False, idempotent=True)
    def clear_board_cache(board_id: str | None = None) -> dict[str, Any]:
        """Forget what was last sent to a board so the next send goes out even if unchanged.

        Use it when the board shows something different from what FiestaBoard
        believes it sent (a power cycle, a manual change on the board) and a
        refresh is being skipped as "unchanged".

        Args:
            board_id: Board to target on a multi-board install (from the boards
                      list in get_settings_summary()). Omitted = the primary board.
        """
        return ops_executors.clear_board_cache(board_id)

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
