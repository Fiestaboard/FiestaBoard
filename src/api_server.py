"""REST API server for FiestaBoard Display Service."""

import asyncio
import json
import logging
import logging.handlers
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

# Load environment variables from .env file before importing modules that may
# read them at import time. The intra-package imports below intentionally come
# after this call; noqa: E402 suppresses ruff's import-order check.
load_dotenv()

# The display-service runtime and the log store live in their own modules
# (Phase 2 Task 8) so a router can reach them without importing this one.
# Imported under their pre-move identities: ~130 test patch targets, plus the
# handlers still declared here, resolve them as ``src.api_server.<name>``.
from . import (  # noqa: E402,F401  (re-export)
    __version__,  # noqa: E402
    display_runtime,
    log_store,
)
from .auth import is_auth_enabled  # noqa: E402
from .auth.middleware import AuthMiddleware  # noqa: E402
from .auth.routes import router as auth_router  # noqa: E402

# Re-export: src/mcp_server.py imports this name from here, and
# tests/test_api_extended.py exercises the helper through it.
from .board_chars import characters_to_message as _characters_to_message  # noqa: E402,F401

# Patch seams (Phase 2, Task 8): api_server has no handler of its own left that
# calls these, but src/settings/routes.py resolves them through
# `src.api_server` at call time so the ~200 tests that patch them at that path
# keep steering the moved /settings handlers.
from .board_client import board_client_from_board_dict  # noqa: E402, F401  (patch seam)

# Board lookup / send guards and the DisplayService accessor now live in
# neutral modules so the extracted routers can import them directly instead of
# reaching back into this one at call time (Phase 2 §2.3). They stay bound as
# `src.api_server.<name>` here: this module's own handlers use them, and the
# suite patches them at that path for those handlers.
from .board_guards import (  # noqa: E402, F401  (patch seams, see above)
    _board_dims,
    _board_is_paused,
    _require_board,
)
from .collections.models import is_collection_id  # noqa: E402, F401  (patch seam)
from .collections.service import (  # noqa: E402
    get_collection_service,
    resolve_active_page_id,
    resolve_next_check_seconds,
)

# ``unmask_sensitive_values`` / ``reset_display_service`` /
# ``reset_template_engine`` used to be imported here purely as patch seams for
# the extracted plugins router (#1757). That router binds them from their
# canonical homes now (Phase 2 slice 4) and was their last consumer, so the
# three re-exports are gone rather than left as patch targets that steer
# nothing.
from .config import Config  # noqa: E402,F401  (41 tests patch src.api_server.Config.*)
from .config_manager import get_config_manager  # noqa: E402
from .devices import resolve_dimensions  # noqa: E402, F401  (patch seam)
from .display_runtime import (  # noqa: E402
    _format_uptime,  # noqa: F401  (re-export: pre-move patch target)
    _get_board_client,  # noqa: F401  (re-export: pre-move patch target)
    _get_first_board_dims,  # noqa: F401  (re-export: pre-move patch target)
    _get_server_ip,  # noqa: F401  (re-export: pre-move patch target)
    _get_service_uptime,  # noqa: F401  (re-export: pre-move patch target)
    _note_out_of_band_write,  # noqa: F401  (re-export: pre-move patch target)
    _primary_board_entry,  # noqa: F401  (re-export: pre-move patch target)
    _primary_connection_info,  # noqa: F401  (re-export: pre-move patch target)
    _publish_mqtt_state_update,  # noqa: F401  (re-export: pre-move patch target)
    _send_with_status,  # noqa: F401  (re-export: pre-move patch target)
    get_service,  # noqa: F401  (re-export: pre-move patch target)
    mark_service_started,  # noqa: F401  (re-export: pre-move patch target)
    peek_service,  # noqa: F401  (re-export: pre-move patch target)
    reinitialize_board_clients,  # noqa: F401  (re-export: pre-move patch target)
)
from .displays.service import get_display_service, reset_display_service  # noqa: E402, F401
from .log_store import (  # noqa: E402
    LOG_BACKUP_COUNT,  # noqa: F401  (re-export: pre-move patch target)
    LOG_MAX_BYTES,  # noqa: F401  (re-export: pre-move patch target)
    JSONFileHandler,  # noqa: F401  (re-export: pre-move patch target)
    LogBufferHandler,  # noqa: F401  (re-export: pre-move patch target)
    _create_log_entry,  # noqa: F401  (re-export: pre-move patch target)
    _log_buffer,  # noqa: F401  (re-export: pre-move patch target)
    _log_dir,  # noqa: F401  (re-export: pre-move patch target)
    _log_file,  # noqa: F401  (re-export: pre-move patch target)
    _log_lock,  # noqa: F401  (re-export: pre-move patch target)
    _read_logs_from_files,  # noqa: F401  (re-export: pre-move patch target)
    _setup_file_logging,  # noqa: F401  (re-export: pre-move patch target)
)
from .pages.service import (  # noqa: E402, F401  (patch seam)
    check_ref_board_compatibility,
    get_page_service,
)
from .panels.service import get_panel_service  # noqa: E402, F401  (patch seam, see above)
from .paths import get_data_dir  # noqa: E402, F401  (re-export: patch seam)
from .settings.service import get_settings_service  # noqa: E402, F401  (patch seam)
from .text_to_board import text_to_board_array  # noqa: E402, F401  (patch seam)
from .time_service import reset_time_service  # noqa: E402

logger = logging.getLogger(__name__)

# Cache state for /muni/stops endpoint
_muni_stops_cache: dict[str, Any] | None = None
_muni_stops_cache_time: float = 0.0
_muni_stops_cache_lock = threading.Lock()


# The URL guard and the generic-data host allowlist moved to
# src/plugin_support/url_guard.py with their one caller (Phase 2, Task 8).


# Global service instance
# The DisplayService singleton itself lives in src/display_runtime.py so the
# extracted routers can reach it without importing this module (Phase 2 §2.3).
# The background-thread lifecycle below is server lifecycle and stays here.
_service_thread: threading.Thread | None = None
_service_running = False
_shutting_down = False  # Set during app shutdown to suppress auto-restart

# ``_service_running`` is written by the start/stop lifecycle below and read at
# 22 sites here; src/display_runtime.py reads it through this probe so a
# converted router can answer "is the display loop running" without importing
# this module. One flag, one owner, two readers.
display_runtime.set_running_probe(lambda: _service_running)

# MessageRequest, StatusResponse and HealthResponse moved with their routes
# to src/board_api/models.py and src/service_api/models.py (Phase 2, Task 8).
# Nothing here imports them any more, and leaving a binding behind would
# advertise a patch target that no longer steers anything.


def _run_startup_migrations() -> None:
    """Run the one-shot config migrations that used to fire from read paths.

    ``migrate_silence_schedule_to_per_board`` seeds each configured board's
    silence override from the install-wide window, and
    ``migrate_silence_schedule_to_utc`` converts pre-UTC ``HH:MM`` silence
    times.  Seeding runs first so the UTC pass converts the per-board windows
    in the same boot.  Both are idempotent, so running them once per boot is
    enough; doing it here keeps ``GET /silence-status`` a pure read (#1746).
    Failures are logged, never fatal — a migration must not stop the API from
    booting.
    """
    try:
        get_config_manager().migrate_silence_schedule_to_per_board()
    except Exception:
        logger.warning("Silence-schedule per-board migration failed on startup", exc_info=True)
    try:
        get_config_manager().migrate_silence_schedule_to_utc()
    except Exception:
        logger.warning("Silence-schedule UTC migration failed on startup", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events.

    Startup does **not** touch MCP: the ``mcp`` package is imported by the
    lazy mount (``_LazyMCPMount``) on the first request to ``/api/mcp``,
    and that mount also owns the session manager's lifecycle. Shutdown
    closes it if it was ever activated.
    """
    global _service_thread, _shutting_down, _service_running, _mcp_serving

    # --- Startup ---
    _shutting_down = False
    _mcp_serving = True
    logger.info("API server starting up...")

    # Set up file-based logging
    _setup_file_logging()

    # Auto-heal config dropped on an upgrade boot (#1102/#948) BEFORE the
    # service + plugin registry read it. No-op unless this is a version-change
    # boot with a snapshot that still holds the lost data.
    try:
        _restored = _auto_restore_post_upgrade_regression()
        if _restored:
            logger.warning("Post-upgrade auto-restore applied from snapshot: %s", _restored)
    except Exception:  # pragma: no cover - safety net must never block boot
        logger.debug("Post-upgrade auto-restore failed", exc_info=True)
    _log_config_boot_snapshot("post-restore")

    # One-shot config migrations, before anything reads the migrated values.
    _run_startup_migrations()

    # If the most recent settings snapshot looks materially richer than the
    # live config (more enabled plugins, etc.), tell the user loudly on
    # startup so they don't have to discover the recovery path on their own.
    # See issue #948.
    try:
        _regression_hint = _detect_post_upgrade_regression()
        if _regression_hint:
            logger.warning(
                "Post-upgrade regression suspected: snapshot '%s' has %d enabled "
                "plugin(s) but live config has %d. Missing: %s. "
                "Roll back with POST /system/update/rollback (snapshot=%s, restore_settings=true).",
                _regression_hint["snapshot_name"],
                _regression_hint["snapshot_enabled_count"],
                _regression_hint["current_enabled_count"],
                _regression_hint["missing_plugin_ids"],
                _regression_hint["snapshot_name"],
            )
    except Exception:  # pragma: no cover - defensive
        logger.debug("Post-upgrade regression check failed", exc_info=True)

    # Initialize and auto-start the service
    service = get_service()
    if service:
        # Try to auto-start, but don't fail if it doesn't work
        # The service can be started manually later via the /start endpoint
        try:
            logger.info("Auto-starting background service...")
            _service_thread = threading.Thread(target=run_service_background, daemon=True)
            _service_thread.start()
            time.sleep(0.5)  # Give it a moment to start

            # Check if it actually started
            if _service_running:
                logger.info("Background service auto-started successfully")
            else:
                logger.warning(
                    "Background service failed to start - likely due to configuration issues. Use the /start endpoint or UI to start it manually after fixing configuration."
                )
        except Exception as e:
            logger.error(f"Failed to auto-start background service: {e}", exc_info=True)
            logger.warning("Service can be started manually via /start endpoint after configuration is fixed")
    else:
        logger.warning("Service instance could not be created - check logs for initialization errors")
    _log_config_boot_snapshot("post-service-init")

    # Start mDNS/Bonjour advertisement (fiestaboard.local)
    try:
        from .system.mdns import start_mdns

        if start_mdns():
            from .system.mdns import get_mdns_service

            logger.info("Access FiestaBoard at %s", get_mdns_service().local_url)
    except Exception as e:
        logger.warning(f"mDNS service could not be started: {e}")

    # Start MQTT client for Home Assistant discovery/control (optional)
    try:
        from .settings.service import get_settings_service

        mqtt_cfg = get_settings_service().get_mqtt_settings()
        if mqtt_cfg.enabled:
            _apply_mqtt_config(mqtt_cfg)
            logger.info("MQTT client started for Home Assistant")
    except Exception as e:
        logger.warning(f"MQTT client could not be started: {e}")

    # Start plugin update checker background task (every 6 hours)
    update_check_task = None
    try:
        import asyncio as _asyncio

        async def _plugin_update_check_loop():
            interval = 3600  # 1 hour
            # Initial delay of 5 minutes so startup isn't burdened
            await _asyncio.sleep(300)
            while True:
                try:
                    if PLUGIN_SYSTEM_AVAILABLE:
                        registry = get_plugin_registry()
                        results = await _asyncio.get_event_loop().run_in_executor(None, registry.check_for_updates)
                        updates = [p for p, v in results.items() if v]
                        if updates:
                            auto_update = get_settings_service().get_plugin_settings().auto_update
                            if auto_update:
                                await _auto_apply_plugin_updates(registry, updates)
                            else:
                                logger.info(
                                    "Plugin updates available (auto-update off): %s",
                                    ", ".join(updates),
                                )
                        else:
                            logger.debug("Plugin update check: all plugins up to date")
                except Exception as exc:
                    logger.warning("Plugin update check error: %s", exc)
                await _asyncio.sleep(interval)

        update_check_task = _asyncio.create_task(_plugin_update_check_loop())
        logger.info("Plugin update checker scheduled (every 6 hours)")
    except Exception as e:
        logger.warning(f"Could not start plugin update checker: {e}")

    # Start FiestaBoard system update checker.  Wakes up periodically and, if
    # the user-configured interval has elapsed since the last check, refreshes
    # ``last_check`` so the in-app banner can show "Update Available" without
    # the user having to open Settings and click Refresh.
    system_update_task = None
    if _managed_externally():
        # An external supervisor (HA add-on) owns updates — polling Docker Hub
        # here serves no purpose and would only feed a duplicate notification
        # the UI already suppresses.  Skip the checker entirely.
        logger.info("System update checker disabled: updates are managed externally (e.g. Home Assistant add-on)")
    else:
        try:

            async def _system_update_check_loop():
                # Tick once an hour.  Even on the longest interval (monthly) this
                # is plenty granular and keeps the work the loop does tiny.
                # The tick body lives in src/system/update_service.py
                # (issue #1758); only the loop shell stays in the lifespan.
                tick_seconds = 3600
                # Initial delay so we don't pile onto startup work.
                await _asyncio.sleep(60)
                while True:
                    try:
                        await run_system_update_check_if_due()
                    except Exception as exc:
                        logger.warning("System update check error: %s", exc)
                    await _asyncio.sleep(tick_seconds)

            system_update_task = _asyncio.create_task(_system_update_check_loop())
            logger.info("System update checker scheduled (interval read from state on each tick)")
        except Exception as e:
            logger.warning(f"Could not start system update checker: {e}")

    yield

    # --- Shutdown ---
    # Release the MCP session manager if a request ever activated it. No-op
    # on the (overwhelmingly common) boot where nobody spoke MCP.
    _mcp_serving = False
    await _mcp_mount.aclose()

    if update_check_task is not None:
        update_check_task.cancel()
    if system_update_task is not None:
        system_update_task.cancel()
    logger.info("API server shutting down...")
    _shutting_down = True
    _service_running = False
    running_service = peek_service()
    if running_service:
        running_service.running = False

    # Stop MQTT client
    try:
        from .mqtt import get_mqtt_client, set_mqtt_client_instance

        mqtt_client = get_mqtt_client()
        if mqtt_client:
            mqtt_client.stop()
            set_mqtt_client_instance(None)
            logger.info("MQTT client stopped")
    except Exception:
        logger.debug("Failed to stop MQTT client during shutdown", exc_info=True)

    # Stop mDNS advertisement
    try:
        from .system.mdns import stop_mdns

        stop_mdns()
    except Exception:
        logger.debug("Failed to stop mDNS during shutdown", exc_info=True)

    # Stop the shared plugin-fetch pool (issue #1751). wait=False: a wedged
    # plugin fetch must not stall process shutdown.
    try:
        from .plugins.registry import shutdown_plugin_fetch_executor

        shutdown_plugin_fetch_executor()
    except Exception:
        logger.debug("Failed to stop plugin-fetch executor during shutdown", exc_info=True)

    # Stop the dedicated board-send and live-preview pools (issue #1878).
    # wait=False for the same reason: a wedged board must not stall process
    # shutdown.
    try:
        from .board_send_executor import shutdown_board_preview_executor, shutdown_board_send_executor

        shutdown_board_send_executor()
        shutdown_board_preview_executor()
    except Exception:
        logger.debug("Failed to stop board-send executor during shutdown", exc_info=True)


# Create FastAPI app
# The front page of /api/docs. Swagger renders this as markdown, so it is the
# one place a newcomer can be told what the nouns are and be handed a request
# that works. Keep it short and keep it true — no endpoint that does not exist.
API_DESCRIPTION = """\
FiestaBoard drives one or more split-flap displays from templated pages.

### Hello world

Put text on the board right now:

```bash
curl -X POST http://fiestaboard.local:4420/api/send-message \\
  -H 'Content-Type: application/json' \\
  -d '{"text": "HELLO WORLD"}'
```

### How the pieces fit

* A **page** is a template: literal text plus `{{plugin_id.variable}}`
  placeholders that **plugins** fill with live data.
* A **schedule** or a **collection** decides which page a board shows at a
  given moment. `POST /send-message` bypasses both for a one-off write.
* `/settings/*` and `/config/*` are the install's configuration;
  `/system/*`, `/network/*` and `/auth/*` administer the appliance itself.

### Base URL

nginx fronts the API under `/api`, so every path below is reached as
`/api/<path>` — `GET /status` is `http://fiestaboard.local:4420/api/status`.
These docs live at `/api/docs`, the schema at `/api/openapi.json`.

### Authentication

Off by default: a fresh install answers every request. With
`FIESTABOARD_AUTH_ENABLED=true`, requests carry the session cookie that
`POST /auth/login` sets. MCP clients may instead send
`Authorization: Bearer <token>` to `/api/mcp` (see `POST /auth/mcp-token`).
"""

# Deliberate order — Swagger lists tags in this order, and anything not listed
# here falls in after them. Boards and the content on them come first; the
# appliance-administration surfaces a newcomer does not need on day one
# (settings, updates, Wi-Fi, diagnostics) come last. The previous default was
# first-appearance-in-the-paths-object order, which opened on MQTT and put
# `pages` fourteenth, below `debug`.
OPENAPI_TAGS = [
    {"name": "service", "description": "The display loop itself: health, status, start/stop/refresh."},
    {"name": "board", "description": "Write to a board out of band, and read back what is physically on it."},
    {"name": "pages", "description": "Pages — the unit of content. CRUD, preview, send, import/export."},
    {"name": "templates", "description": "Render and validate template text; list the variables and formula functions it can use."},
    {"name": "displays", "description": "Device shapes and raw character-code grids."},
    {"name": "schedules", "description": "Time-of-day rules choosing which page a board shows."},
    {"name": "collections", "description": "Ordered groups of pages that rotate as one."},
    {"name": "triggers", "description": "Event-driven page interrupts, and the ones currently firing."},
    {"name": "transitions", "description": "Transition plugins (beta): preview, test and restore board animations."},
    {"name": "plugins", "description": "Install, configure, enable and inspect the data-source plugins that fill template variables."},
    {"name": "plugin-support", "description": "Platform helpers that back a plugin's configuration form."},
    {"name": "staff-picks", "description": "Curated example pages shipped with the app."},
    {"name": "panels", "description": "FiestaPanel — the read-only browser view of a board."},
    {"name": "ai", "description": "AI page generation, chat editing and the operation grammar shared with MCP."},
    {"name": "settings", "description": "Install settings: boards, display, location, polling, output, MQTT, AI, beta flags."},
    {"name": "config", "description": "Board connection configuration and its validation/discovery helpers."},
    {"name": "backup", "description": "Export and import the whole install as one file."},
    {"name": "mqtt", "description": "MQTT / Home Assistant discovery status and republish."},
    {"name": "auth", "description": "Optional login, password/username management and MCP bearer tokens."},
    {"name": "network", "description": "Wi-Fi configuration for the appliance."},
    {"name": "system", "description": "Version, update checks, updates and rollback, restart and shutdown."},
    {"name": "debug", "description": "Diagnostics: logs, caches, connection tests and board fill/blank probes."},
]

app = FastAPI(
    title="FiestaBoard Display API",
    description=API_DESCRIPTION,
    openapi_tags=OPENAPI_TAGS,
    version=__version__,
    lifespan=lifespan,
    # The API is served behind nginx under the /api/* prefix (which nginx
    # strips before proxying to FastAPI). Setting root_path tells Swagger UI
    # / ReDoc to reference /api/openapi.json so the docs page at /api/docs
    # can load its API definition through the proxy.
    root_path="/api",
)

CORS_ORIGINS_ENV = "FIESTABOARD_CORS_ORIGINS"


def cors_settings() -> dict:
    """Resolve the CORS policy from the environment.

    The UI is served from the same origin as the API (nginx fronts both),
    so CORS only ever matters for third-party callers. Two regimes:

    * ``FIESTABOARD_CORS_ORIGINS`` unset (the default) — allow any origin
      but **without** credentials. Anonymous cross-origin reads keep
      working exactly as before; what stops working is a browser sending
      the session cookie (or any other credential) on behalf of a page
      the operator never allow-listed.
    * ``FIESTABOARD_CORS_ORIGINS`` set to a comma-separated list of
      origins — only those origins are allowed, and they may send
      credentials.

    ``allow_origins=["*"]`` together with ``allow_credentials=True`` is
    never emitted: browsers reject that pairing, and Starlette "helpfully"
    works around it by echoing back whatever ``Origin`` the caller sent —
    which is how every site on the internet ended up holding a
    credentialed grant to a LAN board (#1744).
    """
    raw = os.environ.get(CORS_ORIGINS_ENV, "")
    origins = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]

    if not origins:
        return {
            "allow_origins": ["*"],
            "allow_credentials": False,
            "allow_methods": ["*"],
            "allow_headers": ["*"],
        }

    if "*" in origins:
        logger.warning(
            "%s contains '*'; credentials disabled for CORS because a wildcard "
            "origin cannot be combined with credentials. List explicit origins "
            "to allow credentialed cross-origin requests.",
            CORS_ORIGINS_ENV,
        )
        return {
            "allow_origins": ["*"],
            "allow_credentials": False,
            "allow_methods": ["*"],
            "allow_headers": ["*"],
        }

    return {
        "allow_origins": origins,
        "allow_credentials": True,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }


# Add CORS middleware
app.add_middleware(CORSMiddleware, **cors_settings())


# ---------------------------------------------------------------------------
# MCP server mount
# ---------------------------------------------------------------------------


class _MCPActivation:
    """One activation of the MCP sub-app, bound to one event loop.

    Holds the streamable-HTTP session manager open in a dedicated task for as
    long as the API is serving. ``StreamableHTTPSessionManager.run()`` is
    once-per-instance, but ``build_streamable_http_app()`` mints a fresh
    manager on every call, so re-activating (after ``aclose()``, or on a new
    event loop) is safe.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.app: Any = None
        self.error: str | None = None
        self._stop = asyncio.Event()
        self._ready: asyncio.Future[None] = loop.create_future()
        self._runner: asyncio.Task[None] | None = None

    def _mark_ready(self) -> None:
        if not self._ready.done():
            self._ready.set_result(None)

    async def _hold(self) -> None:
        """Build the sub-app and keep its lifespan open until ``aclose()``."""
        try:
            from .mcp_server import build_streamable_http_app

            sub_app = build_streamable_http_app()
            if sub_app is None:
                self.error = "mcp package not installed or failed to initialise"
                logger.warning("MCP server disabled — %s", self.error)
                return
            # The sub-app's own lifespan *is* ``session_manager.run()``, and
            # FastAPI's ``app.mount()`` does not propagate a sub-app lifespan.
            # Without running it here the session manager has no task group
            # and every request to ``/api/mcp/*`` fails.
            async with sub_app.router.lifespan_context(sub_app):
                self.app = sub_app
                logger.info("FiestaBoard MCP server activated at /mcp (public: /api/mcp)")
                self._mark_ready()
                await self._stop.wait()
        except Exception as exc:  # pragma: no cover — defensive
            self.error = str(exc)
            logger.warning("Failed to activate MCP server: %s", exc, exc_info=True)
        finally:
            self._mark_ready()

    async def wait_ready(self) -> None:
        """Start the holder task on first call; every caller awaits the same result."""
        if self._runner is None:
            self._runner = asyncio.create_task(self._hold(), name="fiestaboard-mcp-session-manager")
        await self._ready

    async def aclose(self) -> None:
        self._stop.set()
        if self._runner is not None:
            await self._runner


class _LazyMCPMount:
    """ASGI app mounted at ``/mcp`` that imports ``mcp`` on first request.

    Building the MCP app at module scope pulled the whole ``mcp`` package —
    240 modules — into every boot whether or not anyone speaks MCP: measured
    at +434 ms of import time and +34.7 MB RSS, a third of the process. On a
    Raspberry Pi that is seconds of "did it survive the power cut?".

    The mount itself is still registered eagerly, so the route table is
    unchanged; only the import and the session manager are deferred.
    """

    def __init__(self) -> None:
        self._state: _MCPActivation | None = None

    async def _activation(self) -> _MCPActivation:
        loop = asyncio.get_running_loop()
        state = self._state
        if state is None or state.loop is not loop:
            # A previous activation's task group belongs to an event loop that
            # is gone (each bare TestClient request gets its own). Build a
            # fresh activation rather than dispatch into a dead task group.
            state = self._state = _MCPActivation(loop)
        await state.wait_ready()
        return state

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if not _mcp_serving:
            # The session manager's lifetime is the app's lifetime: activating
            # it outside a running lifespan would leave a task group nothing
            # ever closes. Matches the pre-lazy behaviour, where the manager
            # was only ever started from the lifespan.
            response = PlainTextResponse("MCP server is not running", status_code=503)
            await response(scope, receive, send)
            return
        state = await self._activation()
        if state.app is None:
            response = PlainTextResponse(
                f"MCP server unavailable: {state.error or 'not initialised'}",
                status_code=503,
            )
            await response(scope, receive, send)
            return
        await state.app(scope, receive, send)

    async def aclose(self) -> None:
        state, self._state = self._state, None
        if state is not None:
            await state.aclose()


# Mount the MCP server at /mcp (accessible at /api/mcp via nginx).
#
# ``_mcp_serving`` is True only while the app lifespan is running. The mount
# refuses to activate outside it, because the session manager it starts has to
# be closed by that same lifespan.
_mcp_serving = False
_mcp_mount = _LazyMCPMount()
app.mount("/mcp", _mcp_mount)

# Optional authentication layer (opt-in via FIESTABOARD_AUTH_ENABLED env var).
# Mounted unconditionally so /auth/* endpoints are always reachable; the
# middleware itself short-circuits when auth is disabled so existing
# local-only installs are unaffected.
# /panel/ (singular) is the FiestaPanel viewer surface: read-only endpoints a
# TV browser must reach with no session cookie. The /panels CRUD surface
# (plural) stays behind auth like everything else.
app.add_middleware(AuthMiddleware, extra_public_paths=("/panel/",))
app.include_router(auth_router)
if is_auth_enabled():
    logger.info("Authentication is ENABLED (FIESTABOARD_AUTH_ENABLED=true)")
else:
    logger.info("Authentication is disabled (set FIESTABOARD_AUTH_ENABLED=true to require login)")


# Set up log buffer handler
log_buffer_handler = LogBufferHandler()
log_buffer_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
logging.getLogger().addHandler(log_buffer_handler)


def run_service_background():
    """Run the service in a background thread with auto-restart on failure."""
    global _service_running
    restart_delay = 2
    max_restart_delay = 60

    while not _shutting_down:
        service = get_service()
        if not service:
            logger.warning("Service instance unavailable, retrying in %ds...", restart_delay)
            time.sleep(restart_delay)
            restart_delay = min(restart_delay * 2, max_restart_delay)
            continue

        if not service.vb_client:
            logger.info("Service not fully initialized, attempting initialization...")
            if not service.initialize():
                logger.error("Service initialization failed - retrying in %ds...", restart_delay)
                time.sleep(restart_delay)
                restart_delay = min(restart_delay * 2, max_restart_delay)
                continue

        service.running = True
        _service_running = True
        mark_service_started()
        restart_delay = 2  # Reset backoff on successful start
        try:
            logger.info("Starting background display service...")
            service.run()
        except BaseException as e:
            logger.error(f"Service error: {e}", exc_info=True)
        finally:
            _service_running = False

        if _shutting_down:
            logger.info("Background display service stopped (app shutting down)")
            break

        logger.warning("Background display service stopped unexpectedly, restarting in %ds...", restart_delay)
        time.sleep(restart_delay)
        restart_delay = min(restart_delay * 2, max_restart_delay)


def start_display_service_sync() -> bool:
    """Start the display service (sync). Used by MQTT command handler. Returns True if started."""
    global _service_thread, _shutting_down
    if _service_running:
        return True
    _shutting_down = False
    service = get_service()
    if not service:
        return False
    if not service.vb_client and not service.initialize():
        return False
    _service_thread = threading.Thread(target=run_service_background, daemon=True)
    _service_thread.start()
    time.sleep(0.5)
    return _service_running


def stop_display_service_sync() -> bool:
    """Stop the display service (sync). Used by MQTT command handler. Returns True if stopped."""
    global _service_running, _shutting_down
    if not _service_running:
        return True
    _shutting_down = True
    running_service = peek_service()
    if running_service:
        running_service.running = False
    _service_running = False
    return True


# ── Display-loop controls for the extracted service router ──────────────────
#
# The background-thread state above stays in this module (see the
# src/display_runtime.py docstring: ~30 test sites patch
# ``src.api_server._service_running``, and a module global cannot be relocated
# without breaking every one of them). What moves is the *decision* — which of
# "already running" / "not initialized" / "failed to start" the caller gets —
# which now lives in src/service_api/routes.py. These two primitives are the
# only writes it needs, and they are registered here, next to the state they
# mutate, exactly as ``set_running_probe`` already registers the read.


def _spawn_display_loop() -> None:
    """Clear the shutdown flag and start the background loop thread."""
    global _service_thread, _shutting_down
    _shutting_down = False
    _service_thread = threading.Thread(target=run_service_background, daemon=True)
    _service_thread.start()


def _halt_display_loop() -> None:
    """Suppress auto-restart, tell a running service to stop, clear the flag."""
    global _service_running, _shutting_down
    _shutting_down = True
    running_service = peek_service()
    if running_service:
        running_service.running = False
    _service_running = False


display_runtime.set_loop_controls(_spawn_display_loop, _halt_display_loop)


# ── MQTT status and discovery — moved to src/mqtt/routes.py (Phase 2,
# Task 8). ``_apply_mqtt_config`` below stays: it is boot/settings wiring,
# not an endpoint.
from .mqtt.routes import router as mqtt_router  # noqa: E402

app.include_router(mqtt_router)


def _apply_mqtt_config(mqtt_cfg) -> None:
    """Start or stop the MQTT client to match *mqtt_cfg.enabled*.

    Safe to call at any time: stops the old client first when one is running.
    """
    from .mqtt import MQTTClient, get_mqtt_client, set_mqtt_client_instance
    from .mqtt.commands import CommandHandler
    from .mqtt.state import StatePublisher

    old = get_mqtt_client()
    if old:
        old.stop()
        set_mqtt_client_instance(None)

    if not mqtt_cfg.enabled:
        return

    from .mqtt.config import MQTTConfig

    config = MQTTConfig(
        enabled=mqtt_cfg.enabled,
        broker_host=mqtt_cfg.broker_host,
        broker_port=mqtt_cfg.broker_port,
        username=mqtt_cfg.username or None,
        password=mqtt_cfg.password or None,
        external_url=mqtt_cfg.external_url or None,
    )
    errors = config.validate()
    if errors:
        logger.warning("MQTT config invalid: %s", errors)
        return

    client = MQTTClient(config)
    state_publisher = StatePublisher(
        client,
        get_display_running=lambda: _service_running,
        get_current_message=lambda: "—",
    )
    command_handler = CommandHandler(
        client,
        start_display_service=start_display_service_sync,
        stop_display_service=stop_display_service_sync,
    )
    client.set_state_publisher(state_publisher)
    client.set_command_handler(command_handler)
    client.start()
    set_mqtt_client_instance(client)
    logger.info("MQTT client (re)started")


# ---------------------------------------------------------------------------
# AI provider settings + page generation ("Gen AI" feature)
# ---------------------------------------------------------------------------

# Server-side execution of chat operations (Phase 2 Task 11): the web
# drawer posts validated tool calls here so chat and MCP share one
# executor per op instead of the browser re-implementing each one.
#
# The /pages/ai routes (context, generate, chat) live in the sibling
# src/ai/page_routes.py — a different URL prefix, the same `ai` domain.
from .ai.page_routes import router as ai_page_router  # noqa: E402
from .ai.routes import router as ai_router  # noqa: E402

app.include_router(ai_router)
app.include_router(ai_page_router)


# =============================================================================
# System Management Endpoints — moved to src/system/ (issue #1758)
# =============================================================================
#
# The system-update subsystem (Docker Hub / GitHub version comparison, the
# fiestaupdater sidecar client, pre-update settings snapshots, and the
# .system-update.json state machine) lives in src/system/update_service.py;
# its route handlers (/version, /system/update-check, /system/update/*,
# /system/restart, /system/shutdown) live in src/system/routes.py and are
# included below.
#
# Nothing is re-exported for the test suite any more: the Phase 2 system slice
# retired that seam. src/system/ imports nothing from this module, the two path
# overrides (SYSTEM_UPDATE_STATE_FILE / SETTINGS_SNAPSHOT_DIR) now live on the
# service, and tests patch src.system.update_service.<name> directly. What is
# imported below is only what api_server's own lifespan / restore paths call.
from .system.update_service import (  # noqa: E402
    _detect_post_upgrade_regression,
    _managed_externally,
    _resolve_snapshot_name,
    run_system_update_check_if_due,
)


async def _auto_apply_plugin_updates(registry: Any, plugin_ids: list) -> None:
    """Silently apply pending plugin updates in the background update loop.

    Runs unattended from ``_plugin_update_check_loop`` once an hour, so the git
    fetch and the module reimport go to worker threads: inline they would seize
    the event loop for up to 120 s per plugin with nobody having asked for
    anything, and the board would simply stop updating (#1750).
    """
    import os as _os
    from pathlib import Path as _Path

    from .plugins.sources import clone_or_update_repo, get_external_plugins_dir

    _ext_dir = get_external_plugins_dir()
    _ext_root = _os.path.realpath(str(_ext_dir))
    updated = []
    failed = []

    for plugin_id in plugin_ids:
        source = registry.get_plugin_source(plugin_id)
        if source is None or not source.local_path:
            failed.append(plugin_id)
            continue

        _real_local = _os.path.realpath(str(_Path(source.local_path)))
        try:
            _common = _os.path.commonpath([_ext_root, _real_local])
        except ValueError:
            failed.append(plugin_id)
            continue
        if _common != _ext_root or _real_local == _ext_root:
            failed.append(plugin_id)
            continue
        if not (_Path(_real_local) / ".git").is_dir():
            failed.append(plugin_id)
            continue

        ok, err = await asyncio.to_thread(clone_or_update_repo, "", plugin_id, external_dir=_ext_dir)
        if not ok:
            logger.warning("Auto-update: git fetch failed for %s: %s", plugin_id, err)
            failed.append(plugin_id)
            continue

        reloaded = await asyncio.to_thread(registry.reload_plugin, plugin_id)
        if reloaded is None:
            logger.warning("Auto-update: reload failed for %s", plugin_id)
            failed.append(plugin_id)
            continue

        registry.clear_update_status(plugin_id)
        updated.append(plugin_id)

    if updated:
        logger.info("Auto-updated plugins: %s", ", ".join(updated))
    if failed:
        logger.warning("Auto-update failed for plugins: %s", ", ".join(failed))


# ── Post-upgrade regression detection / auto-restore (boot-time) ───────────
# These stay in api_server: they run from the lifespan (before services read
# config) and the suite drives them as ``api_server.<name>`` while
# monkeypatching ``api_server._resolve_snapshot_name`` /
# ``api_server.get_config_manager`` — module-local references keep those
# patches live. They call the snapshot helpers through this module's
# re-imported bindings.

# Config fields we know are user-set and safe to auto-restore from a snapshot.
_RESTORABLE_GENERAL_FIELDS = ("timezone", "instance_name")


def _build_post_upgrade_restore_set(snap_config: dict[str, Any], live_config: dict[str, Any]) -> dict[str, Any]:
    """Compute which config.json keys regressed vs a pre-update snapshot.

    Returns ``{"general": {...}, "plugins": {...}}`` with only the keys worth
    restoring; an empty dict means nothing regressed. See plan Task 2 for rules.
    """
    from src.config_manager import DEFAULT_CONFIG, SENSITIVE_FIELDS

    result: dict[str, Any] = {}

    snap_general = snap_config.get("general") or {}
    live_general = live_config.get("general") or {}
    default_general = DEFAULT_CONFIG.get("general", {})
    general: dict[str, Any] = {}
    for field in _RESTORABLE_GENERAL_FIELDS:
        snap_val = snap_general.get(field)
        if not isinstance(snap_val, str) or not snap_val:
            continue
        live_val = live_general.get(field)
        if live_val == snap_val:
            continue
        if live_val in ("", None, default_general.get(field)):
            general[field] = snap_val
    if general:
        result["general"] = general

    snap_plugins = snap_config.get("plugins") or {}
    live_plugins = live_config.get("plugins") or {}
    # Deliberate-removal tombstones (#1394): a plugin the user uninstalled is
    # absent from the live config *on purpose* — never restore it from the
    # snapshot. A base-plugin tombstone also covers its instances ("stocks:sf").
    raw_removed = live_config.get("removed_plugins")
    removed = {pid for pid in raw_removed if isinstance(pid, str)} if isinstance(raw_removed, list) else set()
    plugins: dict[str, Any] = {}
    for pid, snap_cfg in snap_plugins.items():
        if pid in removed or pid.split(":", 1)[0] in removed:
            continue  # deliberately uninstalled — do not resurrect (#1394)
        if not (isinstance(snap_cfg, dict) and snap_cfg.get("enabled") is True):
            continue  # only auto-restore plugins the user had ENABLED (#937 invariant)
        live_cfg = live_plugins.get(pid)
        lost_enable = not (isinstance(live_cfg, dict) and live_cfg.get("enabled") is True)
        lost_secret = isinstance(live_cfg, dict) and any(
            key in SENSITIVE_FIELDS and snap_cfg.get(key) and not live_cfg.get(key) for key in snap_cfg
        )
        if lost_enable or lost_secret:
            plugins[pid] = snap_cfg
    if plugins:
        result["plugins"] = plugins

    return result


def _auto_restore_post_upgrade_regression() -> dict[str, Any]:
    """Restore config keys lost on an upgrade boot from the newest pre-update
    snapshot, before the service/registry reads config. Returns a summary of
    what was restored (empty when it did nothing). See issue #1102 / #948.
    """
    if os.environ.get("FIESTABOARD_AUTO_RESTORE", "1").strip().lower() in ("0", "false", "no"):
        return {}

    cm = get_config_manager()
    if not getattr(cm, "version_changed_on_load", False):
        return {}

    newest = _resolve_snapshot_name(None)
    if newest is None:
        return {}
    try:
        snap_doc = json.loads(newest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    snap_config = (snap_doc.get("data") or {}).get("config") or {}
    if not snap_config:
        return {}

    restore_set = _build_post_upgrade_restore_set(snap_config, cm.get_all())
    if not restore_set:
        return {}

    summary: dict[str, Any] = {}
    general = restore_set.get("general")
    if general:
        cm.set_general(general)
        summary["general"] = sorted(general)
    plugins = restore_set.get("plugins")
    if plugins:
        for pid, cfg in plugins.items():
            cm.set_plugin_config(pid, cfg)
        summary["plugins"] = sorted(plugins)

    # Restored timezone won't take effect until the cached TimeService is rebuilt.
    reset_time_service()
    return summary


def _log_config_boot_snapshot(stage: str) -> None:
    """Log a one-line config fingerprint at a boot stage (issue #1102 forensics)."""
    try:
        cm = get_config_manager()
        general = cm.get_general()
        plugins = cm.get_all_plugin_configs()
        enabled = sum(1 for c in plugins.values() if isinstance(c, dict) and c.get("enabled"))
        logger.info(
            "config boot snapshot [%s]: %d plugin(s), %d enabled, timezone=%r, instance_name=%r",
            stage,
            len(plugins),
            enabled,
            general.get("timezone"),
            general.get("instance_name"),
        )
    except Exception:  # pragma: no cover - diagnostics must never block boot
        logger.debug("config boot snapshot [%s] failed", stage, exc_info=True)


from .system.routes import router as system_router  # noqa: E402

app.include_router(system_router)


# ── WiFi management (FiestaPi only) — moved to src/network/routes.py
# (Phase 2, Task 8). Covers the seven /network/wifi/* routes.
from .network.routes import router as network_router  # noqa: E402

app.include_router(network_router)


# ── The out-of-band board surface — moved to src/board_api/routes.py
# (Phase 2, Task 8). Covers GET /board/current-message, POST /send-message
# and POST /send-welcome-message; the welcome-card builder moved beside
# them into src/board_api/welcome.py.
from .board_api.routes import router as board_router  # noqa: E402

app.include_router(board_router)


# =============================================================================
# Configuration Endpoints — moved to src/config_api/routes.py (Phase 2, Task 8)
# =============================================================================

from .config_api.routes import router as config_router  # noqa: E402

app.include_router(config_router)


# ── The app's own service surface — moved to src/service_api/routes.py
# (Phase 2, Task 8). Covers GET /, GET|HEAD /health, GET /status,
# POST /start, POST /stop, POST /refresh and GET /silence-status.
from .service_api.routes import router as service_router  # noqa: E402

app.include_router(service_router)


# =============================================================================
# Display Source Endpoints — moved to src/displays/routes.py (Phase 2 slice 8)
# =============================================================================

from .displays.routes import router as displays_router  # noqa: E402

app.include_router(displays_router)


# =============================================================================
# Bay Wheels Station Search Endpoints
# =============================================================================


# =============================================================================
# Deprecated plugin-specific platform routes (Phase 2, Task 8)
# =============================================================================
#
# Eleven routes that serve one plugin each — the shape CLAUDE.md says must not
# live in src/. The pickers that called them were replaced by the generic
# remote-options mechanism (GET /plugins/{id}/options/{options_id}); this slice
# grepped web/src, web/tests, the bundled plugins and every sibling plugin repo
# and found no live consumer for any of them.
#
# They are marked deprecated rather than deleted because two of them
# (/muni/stops*, /stocks/*) are documented as public API in shipped plugin
# SETUP guides, so a third-party integration this repo cannot see may call
# them. "Deprecation, never deletion" — see
# docs/internal/reference/API_CONVENTIONS.md. Removal is tracked in the issue
# named on each decorator (#1915); until then they keep their exact current contract
# and stay outside the conventions ratchet, because re-shaping a body we
# intend to delete buys a lockstep web change and nothing else.

@app.get("/baywheels/stations", deprecated=True)  # removal tracked in #1915
async def list_all_baywheels_stations():
    """
    List all Bay Wheels stations with current status.

    Returns all stations from the GBFS feed with their current bike availability.
    """
    import requests

    from src.utils.baywheels import STATION_STATUS_URL, BayWheelsSource

    try:
        # Get station information and current status concurrently (both make HTTP calls)
        station_info, response = await asyncio.gather(
            asyncio.to_thread(BayWheelsSource._get_station_information),
            asyncio.to_thread(requests.get, STATION_STATUS_URL, timeout=10),
        )
        response.raise_for_status()
        status_data = response.json()
        stations_status = {s.get("station_id"): s for s in status_data.get("data", {}).get("stations", [])}

        # Combine information and status
        result = []
        for station_id, info in (station_info or {}).items():
            status = stations_status.get(station_id, {})

            # Count bike types
            electric = 0
            classic = 0
            for vt in status.get("vehicle_types_available", []):
                vt_id = vt.get("vehicle_type_id", "").lower()
                count = vt.get("count", 0)
                if "electric" in vt_id or "boost" in vt_id:
                    electric += count
                elif "classic" in vt_id:
                    classic += count
                else:
                    classic += count

            result.append(
                {
                    "station_id": station_id,
                    "name": info.get("name", station_id),
                    "lat": info.get("lat"),
                    "lon": info.get("lon"),
                    "address": info.get("address", ""),
                    "capacity": info.get("capacity", 0),
                    "num_bikes_available": status.get("num_bikes_available", 0),
                    "electric_bikes": electric,
                    "classic_bikes": classic,
                    "num_docks_available": status.get("num_docks_available", 0),
                    "is_renting": status.get("is_renting", 1) == 1,
                }
            )

        return {"stations": result, "total": len(result)}
    except Exception as e:
        logger.error(f"Error listing Bay Wheels stations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/baywheels/stations/nearby", deprecated=True)  # removal tracked in #1915
async def find_nearby_baywheels_stations(
    lat: float = Query(..., description="Latitude"),
    lng: float = Query(..., description="Longitude"),
    radius: float = Query(2.0, description="Search radius in kilometers"),
    limit: int = Query(10, description="Maximum number of results"),
):
    """
    Find Bay Wheels stations near a location.

    Args:
        lat: Latitude
        lng: Longitude
        radius: Search radius in kilometers (default 2.0)
        limit: Maximum number of results (default 10)

    Returns:
        List of nearby stations sorted by distance
    """
    import requests

    from src.utils.baywheels import STATION_STATUS_URL, BayWheelsSource

    try:
        stations, response = await asyncio.gather(
            asyncio.to_thread(BayWheelsSource.find_stations_near_location, lat, lng, radius, limit),
            asyncio.to_thread(requests.get, STATION_STATUS_URL, timeout=10),
        )

        # Get current status for these stations
        response.raise_for_status()
        status_data = response.json()
        stations_status = {s.get("station_id"): s for s in status_data.get("data", {}).get("stations", [])}

        # Add status information to each station
        for station in stations:
            station_id = station["station_id"]
            status = stations_status.get(station_id, {})

            # Count bike types
            electric = 0
            classic = 0
            for vt in status.get("vehicle_types_available", []):
                vt_id = vt.get("vehicle_type_id", "").lower()
                count = vt.get("count", 0)
                if "electric" in vt_id or "boost" in vt_id:
                    electric += count
                elif "classic" in vt_id:
                    classic += count
                else:
                    classic += count

            station["num_bikes_available"] = status.get("num_bikes_available", 0)
            station["electric_bikes"] = electric
            station["classic_bikes"] = classic
            station["num_docks_available"] = status.get("num_docks_available", 0)
            station["is_renting"] = status.get("is_renting", 1) == 1

        return {
            "stations": stations,
            "count": len(stations),
            "search_location": {"lat": lat, "lng": lng},
            "radius_km": radius,
        }
    except Exception as e:
        logger.error(f"Error finding nearby Bay Wheels stations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/baywheels/stations/search", deprecated=True)  # removal tracked in #1915
async def search_baywheels_stations_by_address(
    address: str = Query(..., description="Address to search near"),
    radius: float = Query(2.0, description="Search radius in kilometers"),
    limit: int = Query(10, description="Maximum number of results"),
):
    """
    Find Bay Wheels stations near an address.

    Uses OpenStreetMap Nominatim for geocoding (free, no API key required).

    Args:
        address: Address string (e.g., "123 Main St, San Francisco, CA")
        radius: Search radius in kilometers (default 2.0)
        limit: Maximum number of results (default 10)

    Returns:
        List of nearby stations sorted by distance
    """
    import requests

    from src.utils.baywheels import STATION_STATUS_URL, BayWheelsSource

    try:
        # Geocode address using Nominatim
        geocode_url = "https://nominatim.openstreetmap.org/search"
        geocode_params = {"q": address, "format": "json", "limit": 1}
        geocode_headers = {"User-Agent": "FiestaBoard-Service/1.0"}

        geocode_response = await asyncio.to_thread(
            requests.get, geocode_url, params=geocode_params, headers=geocode_headers, timeout=10
        )
        geocode_response.raise_for_status()
        geocode_data = geocode_response.json()

        if not geocode_data:
            raise HTTPException(status_code=404, detail=f"Address not found: {address}")

        location = geocode_data[0]
        lat = float(location["lat"])
        lng = float(location["lon"])

        # Find nearby stations and get current status concurrently
        stations, response = await asyncio.gather(
            asyncio.to_thread(BayWheelsSource.find_stations_near_location, lat, lng, radius, limit),
            asyncio.to_thread(requests.get, STATION_STATUS_URL, timeout=10),
        )

        # Get current status for these stations
        response.raise_for_status()
        status_data = response.json()
        stations_status = {s.get("station_id"): s for s in status_data.get("data", {}).get("stations", [])}

        # Add status information to each station
        for station in stations:
            station_id = station["station_id"]
            status = stations_status.get(station_id, {})

            # Count bike types
            electric = 0
            classic = 0
            for vt in status.get("vehicle_types_available", []):
                vt_id = vt.get("vehicle_type_id", "").lower()
                count = vt.get("count", 0)
                if "electric" in vt_id or "boost" in vt_id:
                    electric += count
                elif "classic" in vt_id:
                    classic += count
                else:
                    classic += count

            station["num_bikes_available"] = status.get("num_bikes_available", 0)
            station["electric_bikes"] = electric
            station["classic_bikes"] = classic
            station["num_docks_available"] = status.get("num_docks_available", 0)
            station["is_renting"] = status.get("is_renting", 1) == 1

        return {
            "stations": stations,
            "count": len(stations),
            "search_address": address,
            "geocoded_location": {"lat": lat, "lng": lng, "display_name": location.get("display_name", "")},
            "radius_km": radius,
        }
    except HTTPException:
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"Error geocoding address: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail=f"Geocoding service unavailable: {str(e)}") from e
    except Exception as e:
        logger.error(f"Error searching Bay Wheels stations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


# =============================================================================
# MUNI Endpoints
# =============================================================================


@app.get("/muni/stops", deprecated=True)  # removal tracked in #1915
async def list_all_muni_stops():
    """
    List all SF Muni stops with metadata.

    Returns all stops from the 511.org transit API with cached data (24hr TTL).
    """
    import time

    import requests

    # Cache for stop information (24 hour TTL)
    CACHE_TTL = 24 * 60 * 60  # 24 hours

    global _muni_stops_cache, _muni_stops_cache_time
    current_time = time.time()

    # Return cached data if still valid
    with _muni_stops_cache_lock:
        if _muni_stops_cache and (current_time - _muni_stops_cache_time) < CACHE_TTL:
            return _muni_stops_cache

    try:
        # Fetch stops from 511.org
        # Note: 511.org requires an API key for most endpoints
        # We'll use the API key configured on the muni plugin
        muni_config = get_config_manager().get_plugin_config("muni") or {}
        api_key = muni_config.get("api_key", "")

        if not api_key:
            raise HTTPException(status_code=400, detail="MUNI API key not configured")

        url = "http://api.511.org/transit/stops"
        params = {"api_key": api_key, "operator_id": "SF", "format": "json"}

        response = await asyncio.to_thread(requests.get, url, params=params, timeout=15)
        response.raise_for_status()

        # Handle BOM if present
        content = response.text
        if content.startswith("\ufeff"):
            content = content[1:]

        import json

        data = json.loads(content)

        # Parse stops from the Contents.dataObjects.ScheduledStopPoint array
        stops = []
        stop_points = data.get("Contents", {}).get("dataObjects", {}).get("ScheduledStopPoint", [])

        for stop in stop_points:
            stop_id = stop.get("id", "")
            # Extract numeric stop code from ID (format: "SF_####")
            stop_code = stop_id.split("_")[-1] if "_" in stop_id else stop_id

            location = stop.get("Location", {})
            lat = location.get("Latitude")
            lon = location.get("Longitude")

            # Get stop name
            name = stop.get("Name", stop_code)

            stops.append(
                {
                    "stop_code": stop_code,
                    "stop_id": stop_id,
                    "name": name,
                    "lat": float(lat) if lat else None,
                    "lon": float(lon) if lon else None,
                }
            )

        result = {"stops": stops, "total": len(stops)}

        # Update cache
        with _muni_stops_cache_lock:
            _muni_stops_cache = result
            _muni_stops_cache_time = current_time

        return result

    except Exception as e:
        logger.error(f"Error listing Muni stops: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/muni/stops/nearby", deprecated=True)  # removal tracked in #1915
async def find_nearby_muni_stops(
    lat: float = Query(..., description="Latitude"),
    lng: float = Query(..., description="Longitude"),
    radius: float = Query(0.5, description="Search radius in kilometers"),
    limit: int = Query(10, description="Maximum number of results"),
):
    """
    Find Muni stops near a location.

    Args:
        lat: Latitude
        lng: Longitude
        radius: Search radius in kilometers (default 0.5)
        limit: Maximum number of results (default 10)

    Returns:
        List of nearby stops sorted by distance with live arrival data
    """
    import math

    try:
        # Get all stops (from cache if available)
        stops_data = await list_all_muni_stops()
        all_stops = stops_data["stops"]

        # Calculate distance to each stop using haversine formula
        def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
            """Calculate distance in kilometers between two points."""
            R = 6371.0  # Earth radius in km

            lat1_rad = math.radians(lat1)
            lon1_rad = math.radians(lon1)
            lat2_rad = math.radians(lat2)
            lon2_rad = math.radians(lon2)

            dlat = lat2_rad - lat1_rad
            dlon = lon2_rad - lon1_rad

            a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

            return R * c

        # Filter stops within radius and calculate distances
        nearby_stops = []
        for stop in all_stops:
            if stop["lat"] is None or stop["lon"] is None:
                continue

            distance = haversine_distance(lat, lng, stop["lat"], stop["lon"])

            if distance <= radius:
                stop_with_distance = stop.copy()
                stop_with_distance["distance_km"] = round(distance, 2)
                nearby_stops.append(stop_with_distance)

        # Sort by distance and limit
        nearby_stops.sort(key=lambda x: x["distance_km"])
        nearby_stops = nearby_stops[:limit]

        # Try to get routes serving each stop from regional transit cache
        try:
            from src.utils.transit_cache import get_transit_cache

            cache = get_transit_cache()

            if cache.is_ready():
                # Get all cached stop codes for SF agency
                all_sf_stops = cache.get_all_stops_for_agency("SF")

                for stop in nearby_stops:
                    try:
                        # Get cached visits for this stop
                        visits = all_sf_stops.get(stop["stop_code"], [])

                        # Extract unique route names from cached visits
                        routes = set()
                        for visit in visits:
                            journey = visit.get("MonitoredVehicleJourney", {})
                            published_line = journey.get("PublishedLineName", "")
                            if isinstance(published_line, list):
                                published_line = published_line[0] if published_line else ""
                            if published_line:
                                routes.add(published_line.upper())

                        stop["routes"] = sorted(routes)
                    except Exception:
                        # If we can't get routes, just skip
                        stop["routes"] = []
            else:
                logger.warning("Regional transit cache not ready, routes unavailable")
                for stop in nearby_stops:
                    stop["routes"] = []
        except Exception as e:
            logger.error(f"Error accessing regional transit cache: {e}")
            for stop in nearby_stops:
                stop["routes"] = []

        return {
            "stops": nearby_stops,
            "count": len(nearby_stops),
            "search_location": {"lat": lat, "lng": lng},
            "radius_km": radius,
        }

    except Exception as e:
        logger.error(f"Error finding nearby Muni stops: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/muni/stops/search", deprecated=True)  # removal tracked in #1915
async def search_muni_stops_by_address(
    address: str = Query(..., description="Address to search near"),
    radius: float = Query(0.5, description="Search radius in kilometers"),
    limit: int = Query(10, description="Maximum number of results"),
):
    """
    Find Muni stops near an address.

    Uses OpenStreetMap Nominatim for geocoding (free, no API key required).

    Args:
        address: Address string (e.g., "123 Main St, San Francisco, CA")
        radius: Search radius in kilometers (default 0.5)
        limit: Maximum number of results (default 10)

    Returns:
        List of nearby stops sorted by distance
    """
    import requests

    try:
        # Geocode address using Nominatim
        geocode_url = "https://nominatim.openstreetmap.org/search"
        geocode_params = {"q": address, "format": "json", "limit": 1}
        geocode_headers = {"User-Agent": "FiestaBoard-Service/1.0"}

        geocode_response = await asyncio.to_thread(
            requests.get, geocode_url, params=geocode_params, headers=geocode_headers, timeout=10
        )
        geocode_response.raise_for_status()
        geocode_data = geocode_response.json()

        if not geocode_data:
            raise HTTPException(status_code=404, detail=f"Address not found: {address}")

        location = geocode_data[0]
        lat = float(location["lat"])
        lng = float(location["lon"])

        # Find nearby stops
        stops_data = await find_nearby_muni_stops(lat=lat, lng=lng, radius=radius, limit=limit)

        return {
            "stops": stops_data["stops"],
            "count": stops_data["count"],
            "search_address": address,
            "geocoded_location": {"lat": lat, "lng": lng, "display_name": location.get("display_name", "")},
            "radius_km": radius,
        }

    except HTTPException:
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"Error geocoding address: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail=f"Geocoding service unavailable: {str(e)}") from e
    except Exception as e:
        logger.error(f"Error searching Muni stops: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/transit/cache/status", deprecated=True)  # removal tracked in #1915
async def get_transit_cache_status():
    """
    Get status and health information about the regional transit cache.

    Returns cache statistics including:
    - Last refresh time and age
    - Number of agencies and stops cached
    - Refresh count and error count
    - Whether cache is stale
    """
    try:
        from src.utils.transit_cache import get_transit_cache

        cache = get_transit_cache()
        status = cache.get_status()

        # Add human-readable timestamps
        if status["last_refresh"] > 0:
            status["last_refresh_iso"] = datetime.fromtimestamp(status["last_refresh"]).isoformat()
        else:
            status["last_refresh_iso"] = None

        if status["last_success"] > 0:
            status["last_success_iso"] = datetime.fromtimestamp(status["last_success"]).isoformat()
        else:
            status["last_success_iso"] = None

        return status
    except Exception as e:
        logger.error(f"Error getting transit cache status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


# =============================================================================
# Stocks Endpoints
# =============================================================================


@app.get("/stocks/search", deprecated=True)  # removal tracked in #1915
async def search_stock_symbols(
    query: str = Query(..., description="Search query (symbol or company name)"),
    limit: int = Query(10, ge=1, le=50, description="Maximum number of results"),
):
    """
    Search for stock symbols by symbol or company name.

    Uses Finnhub API if configured, otherwise searches curated list of popular stocks.

    Args:
        query: Search query (symbol or company name)
        limit: Maximum number of results (default 10, max 50)

    Returns:
        List of matching symbols with company names:
        [{"symbol": "GOOG", "name": "Alphabet Inc."}, ...]
    """
    try:
        from src.utils.stocks import StocksSource

        # Get Finnhub API key if configured on the stocks plugin
        stocks_config = get_config_manager().get_plugin_config("stocks") or {}
        finnhub_api_key = stocks_config.get("finnhub_api_key") or None

        results = StocksSource.search_symbols(query=query, limit=limit, finnhub_api_key=finnhub_api_key)

        return {"symbols": results, "count": len(results), "query": query}
    except Exception as e:
        logger.error(f"Error searching stock symbols: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/stocks/validate", deprecated=True)  # removal tracked in #1915
async def validate_stock_symbol(request: dict):
    """
    Validate if a stock symbol is valid.

    Uses yfinance to check if the symbol exists and has price data.

    Body:
        symbol: Stock symbol to validate (e.g., "GOOG")

    Returns:
        Validation result:
        {
            "valid": bool,
            "symbol": str,
            "name": str (if valid),
            "error": str (if invalid)
        }
    """
    symbol = request.get("symbol")
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol parameter required")

    try:
        from src.utils.stocks import StocksSource

        result = StocksSource.validate_symbol(symbol)
        return result
    except Exception as e:
        logger.error(f"Error validating stock symbol: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to validate stock symbol") from e


# =============================================================================
# Traffic Endpoints
# =============================================================================


@app.post("/traffic/routes/geocode", deprecated=True)  # removal tracked in #1915
async def geocode_address(request: dict):
    """
    Geocode an address to coordinates.

    Body:
        address: Address string

    Returns:
        lat, lng, and formatted_address
    """
    import requests

    address = request.get("address")
    if not address:
        raise HTTPException(status_code=400, detail="address parameter required")

    try:
        # Try Nominatim (free, no key needed)
        geocode_url = "https://nominatim.openstreetmap.org/search"
        geocode_params = {"q": address, "format": "json", "limit": 1}
        geocode_headers = {"User-Agent": "FiestaBoard-Service/1.0"}

        response = await asyncio.to_thread(
            requests.get, geocode_url, params=geocode_params, headers=geocode_headers, timeout=10
        )
        response.raise_for_status()
        data = response.json()

        if not data:
            raise HTTPException(status_code=404, detail=f"Address not found: {address}")

        location = data[0]
        return {
            "lat": float(location["lat"]),
            "lng": float(location["lon"]),
            "formatted_address": location.get("display_name", address),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error geocoding address: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/traffic/routes/validate", deprecated=True)  # removal tracked in #1915
async def validate_traffic_route(request: dict):
    """
    Validate a traffic route and get basic info.

    Body:
        origin: Origin address or lat,lng
        destination: Destination address or lat,lng
        destination_name: Display name for destination

    Returns:
        Validation result with distance and duration estimates
    """
    from src.utils.traffic import TrafficSource

    origin = request.get("origin")
    destination = request.get("destination")
    destination_name = request.get("destination_name", "DESTINATION")

    if not origin or not destination:
        raise HTTPException(status_code=400, detail="origin and destination required")

    # Get API key from the traffic plugin config
    traffic_config = get_config_manager().get_plugin_config("traffic") or {}
    api_key = traffic_config.get("api_key") or None
    if not api_key:
        raise HTTPException(status_code=400, detail="Google Routes API key not configured")

    try:
        # Create a temporary TrafficSource to test the route
        # Pass as a list of routes (expected format)
        routes = [
            {
                "origin": origin,
                "destination": destination,
                "destination_name": destination_name,
                "travel_mode": request.get("travel_mode", "DRIVE"),
            }
        ]

        traffic_source = TrafficSource(api_key=api_key, routes=routes)

        # Fetch traffic data to validate (blocking HTTP call - run in thread pool)
        data = await asyncio.to_thread(traffic_source.fetch_traffic_data)

        if not data:
            # No verdict was produced: the upstream Routes API returned
            # nothing, which is not the same as "this route is invalid".
            # Reporting it as ``valid: false`` at 200 hid every outage,
            # quota block and disabled-API misconfiguration (#1887).
            raise HTTPException(
                status_code=502,
                detail=(
                    "Could not validate the route: the Google Routes API returned no data. "
                    "This is usually an invalid address, the Routes API not being enabled, "
                    "or an API key problem."
                ),
            )

        # Extract coordinates if available
        origin_coords = None
        destination_coords = None

        return {
            "valid": True,
            "distance_km": round(data.get("static_duration", 0) / 60 * 0.8, 1),  # Rough estimate
            "static_duration_minutes": data.get("static_duration_minutes", 0),
            "origin": origin,
            "destination": destination,
            "destination_name": destination_name,
            "origin_coords": origin_coords,
            "destination_coords": destination_coords,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating traffic route: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to validate route.") from e


# =============================================================================
# Settings Endpoints
# =============================================================================


# =============================================================================
# Transition plugins (beta) — moved to src/transitions/routes.py (slice 8)
# =============================================================================

from .transitions.routes import router as transitions_router  # noqa: E402

app.include_router(transitions_router)


def _resolve_active_page_id(page_id: str | None) -> str | None:
    """This module's binding of :func:`src.collections.service.resolve_active_page_id`.

    Passes *this* module's ``get_collection_service``, so the resolution goes on
    resolving through the name the suite stubs when it exercises the handlers
    that still live here.
    """
    return resolve_active_page_id(page_id, get_collection_service)


def _resolve_next_check_seconds(page_id: str | None) -> int | None:
    """This module's binding of :func:`src.collections.service.resolve_next_check_seconds`."""
    return resolve_next_check_seconds(page_id, get_collection_service)


def _reinitialize_board_clients() -> None:
    """Rebuild board clients after a boards-list mutation.

    Kept as a name here because unconverted domains patch
    ``src.api_server._reinitialize_board_clients``; the implementation moved to
    ``src/display_runtime.py`` so routers can reach it without importing this
    module.
    """
    reinitialize_board_clients()


# ==================== Beta Settings (HTTPS, etc.) ====================


# =============================================================================
# Debug / diagnostics / logs Endpoints — moved to src/debug/routes.py
# (Phase 2 Task 8). Covers /debug/*, GET /cache-status, POST /clear-cache,
# POST /force-refresh and GET /logs.
# =============================================================================

from .debug.routes import router as debug_router  # noqa: E402

app.include_router(debug_router)


# =============================================================================
# FiestaPanel Endpoints — moved to src/panels/routes.py (Phase 2 slice 8)
# =============================================================================

from .panels.routes import router as panels_router  # noqa: E402

app.include_router(panels_router)


# =============================================================================
# Pages Endpoints — moved to src/pages/routes.py (issue #1756)
# =============================================================================

from .pages.routes import router as pages_router  # noqa: E402

app.include_router(pages_router)

# Staff picks share the pages surface but are their own domain (Phase 2 slice 8).
from .staff_picks.routes import router as staff_picks_router  # noqa: E402

app.include_router(staff_picks_router)

# =============================================================================
# Schedule Endpoints — moved to src/schedules/routes.py (issue #1756)
# =============================================================================

from .schedules.routes import router as schedules_router  # noqa: E402

app.include_router(schedules_router)


# =============================================================================
# Collection Endpoints — moved to src/collections/routes.py (issue #1756)
# =============================================================================

from .collections.routes import router as collections_router  # noqa: E402

app.include_router(collections_router)


# =============================================================================
# Settings Endpoints — moved to src/settings/routes.py (Phase 2, Task 8)
# =============================================================================

from .settings.routes import router as settings_router  # noqa: E402

app.include_router(settings_router)

# =============================================================================
# Template Endpoints — moved to src/templates/routes.py (Phase 2 slice 8)
# =============================================================================

from .templates.routes import router as templates_router  # noqa: E402

app.include_router(templates_router)


# =============================================================================
# Home Assistant Endpoints
# =============================================================================


# Legacy endpoints /preview and /publish-preview have been removed.
# Use /pages/{page_id}/preview and /pages/{page_id}/send instead.
# Set the active page with PUT /settings/active-page for automatic board updates.


# =============================================================================
# Plugin API Endpoints
# =============================================================================

# The plugin router, the availability flag, and the whole remote-options
# runtime (13 names, ~260 lines) moved into ``src/plugins/`` in Phase 2
# slice 4. They are deliberately NOT re-exported here: nothing in this module
# uses them any more, and leaving a binding behind would advertise a patch
# target that no longer steers anything. Patch
# ``src.plugins.routes.<name>`` / ``src.plugins.options_runtime.<name>``.
#
# ``PLUGIN_SYSTEM_AVAILABLE`` is the exception — this module's own handlers
# still branch on it, so the name stays bound here and is patched here for
# them.
from .plugins.routes import PLUGIN_SYSTEM_AVAILABLE  # noqa: E402

if PLUGIN_SYSTEM_AVAILABLE:  # pragma: no branch - False needs a broken install
    from .plugins import get_plugin_registry
else:  # pragma: no cover
    get_plugin_registry = None


# =============================================================================
# Plugin Endpoints — moved to src/plugins/routes.py (issue #1757)
# =============================================================================

from .plugins.routes import router as plugins_router  # noqa: E402

app.include_router(plugins_router)

# =============================================================================
# Triggers — moved to src/triggers/routes.py (Phase 2 slice 8)
# =============================================================================

from .triggers.routes import router as triggers_router  # noqa: E402

app.include_router(triggers_router)


# =============================================================================
# Generic Data Plugin — Test Fetch
# =============================================================================


# ── Platform helpers that back a plugin's configuration form — moved to
# src/plugin_support/routes.py (Phase 2, Task 8). Covers
# GET /home-assistant/entities and POST /generic-data/test-fetch, the only
# two of the thirteen plugin-specific platform routes with a live web
# consumer; the other eleven are deprecated in place below.
from .plugin_support.routes import router as plugin_support_router  # noqa: E402

app.include_router(plugin_support_router)


from .backup.routes import router as backup_router  # noqa: E402

app.include_router(backup_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
