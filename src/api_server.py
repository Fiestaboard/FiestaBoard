"""REST API server for FiestaBoard Display Service."""

import asyncio
import json
import logging
import logging.handlers
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

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
from .board_client import board_client_from_board_dict  # noqa: E402

# Board lookup / send guards and the DisplayService accessor now live in
# neutral modules so the extracted routers can import them directly instead of
# reaching back into this one at call time (Phase 2 §2.3). They stay bound as
# `src.api_server.<name>` here: this module's own handlers use them, and the
# suite patches them at that path for those handlers.
from .board_guards import (  # noqa: E402
    _board_dims,
    _board_is_paused,
    _require_board,
)
from .board_guards import validate_board_host as _validate_board_host  # noqa: E402
from .board_guards import (  # noqa: E402
    validate_board_host_is_local_network as _validate_board_host_is_local_network,
)
from .board_send_executor import run_board_send  # noqa: E402
from .collections.models import is_collection_id  # noqa: E402
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
from .devices import classify_dimensions, resolve_dimensions  # noqa: E402
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
from .pages.service import check_ref_board_compatibility, get_page_service  # noqa: E402
from .panels.service import get_panel_service  # noqa: E402
from .paths import get_data_dir  # noqa: E402, F401  (re-export: patch seam)
from .settings.service import VALID_OUTPUT_TARGETS, VALID_STRATEGIES, get_settings_service  # noqa: E402
from .settings.service import temporary_override_payload as _temporary_override_payload  # noqa: E402
from .text_to_board import text_to_board_array  # noqa: E402
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

    Also runs the MCP server's ``StreamableHTTPSessionManager`` for the
    duration of the API. FastAPI's ``app.mount(...)`` does NOT propagate
    a sub-app's lifespan, so without wiring this here the MCP session
    manager's ``_task_group`` is never created and every request to
    ``/api/mcp/*`` returns 404. The wrapping is best-effort: if the mcp
    package failed to load or the session manager init throws, the rest
    of the API still comes up — MCP just stays disabled.
    """
    global _service_thread, _shutting_down, _service_running

    # Resolve the MCP context manager (or fall back to a no-op) before we
    # decide which branch to take. The mount at the bottom of this module
    # already called ``streamable_http_app()`` (which lazily creates the
    # session manager), so it's safe to access ``session_manager`` here.
    _mcp_ctx = None
    try:
        from .mcp_server import mcp_server as _mcp_for_lifespan

        if _mcp_for_lifespan is not None:
            _mcp_ctx = _mcp_for_lifespan.session_manager.run()
    except Exception as _mcp_exc:  # pragma: no cover — defensive
        logger.warning(
            "MCP session manager could not be wired into lifespan: %s",
            _mcp_exc,
        )
        _mcp_ctx = None

    # --- Startup ---
    _shutting_down = False
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

    # Hold the MCP session manager open for the lifetime of the API, then
    # let it tear down on shutdown. ``_mcp_ctx`` is None when the mcp
    # package didn't load — fall through to a bare yield in that case so
    # the rest of the API still serves requests.
    if _mcp_ctx is not None:
        async with _mcp_ctx:
            logger.info("MCP session manager started")
            yield
    else:
        yield

    # --- Shutdown ---
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
app = FastAPI(
    title="FiestaBoard Display API",
    description="REST API for controlling and monitoring the FiestaBoard Display Service",
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

# Mount the MCP server at /mcp (accessible at /api/mcp via nginx).
# Gracefully skipped if the mcp package is not installed.
try:
    from .mcp_server import build_streamable_http_app as _build_mcp_app

    _mcp_app = _build_mcp_app()
    if _mcp_app is not None:
        app.mount("/mcp", _mcp_app)
        logger.info("FiestaBoard MCP server mounted at /mcp (public: /api/mcp)")
    else:
        logger.warning("MCP server disabled — mcp package not installed or failed to initialise")
except Exception as _mcp_mount_err:  # pragma: no cover
    logger.warning("Failed to mount MCP server: %s", _mcp_mount_err)

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


@app.get("/settings/mqtt")
async def get_mqtt_settings():
    """Return current MQTT integration settings (password masked)."""
    from .settings.service import get_settings_service

    s = get_settings_service().get_mqtt_settings()
    return s.to_dict(mask_secrets=True)


@app.put("/settings/mqtt")
async def update_mqtt_settings(request: Request):
    """Save MQTT settings and immediately apply them.

    Enables or disables the live MQTT client based on the *enabled* flag.
    Supply only the fields you want to change; omitted fields keep their current
    values.  Password is only updated when a non-empty, non-masked value is sent.
    """
    body = await request.json()
    from .settings.service import get_settings_service

    svc = get_settings_service()
    updated = svc.set_mqtt_settings(body)
    _apply_mqtt_config(updated)
    return updated.to_dict(mask_secrets=True)


# ---------------------------------------------------------------------------
# AI provider settings + page generation ("Gen AI" feature)
# ---------------------------------------------------------------------------

# Per-process throttle for /pages/ai/generate. The cap is intentionally
# low because each call costs the user money (BYO-LLM) and a stuck UI
# can otherwise loop. Two concurrent generations across the whole
# instance is plenty for interactive use.
_AI_GENERATE_SEMAPHORE = asyncio.Semaphore(2)
_AI_GENERATE_MIN_INTERVAL_SECONDS = 1.0
_ai_generate_last_call: float = 0.0
_ai_generate_lock = threading.Lock()


def _ai_generate_throttle_check() -> None:
    """Reject a call if it lands less than the min interval after the last.

    Cheap defence against runaway clients without adding a dependency.
    """
    global _ai_generate_last_call
    now = time.monotonic()
    with _ai_generate_lock:
        wait = (_ai_generate_last_call + _AI_GENERATE_MIN_INTERVAL_SECONDS) - now
        if wait > 0:
            raise HTTPException(
                status_code=429,
                detail=("AI generation is rate-limited. Please wait a moment and try again."),
            )
        _ai_generate_last_call = now


@app.get("/settings/ai")
async def get_ai_settings():
    """Return AI provider configuration with each provider's api_key masked."""
    cm = get_config_manager()
    return cm.get_ai_providers_masked()


@app.put("/settings/ai")
async def update_ai_settings(request: Request):
    """Update AI provider configuration.

    Body may include any of:
    - ``enabled`` (bool)
    - ``providers`` (list of provider objects: ``id``, ``name``,
      ``base_url``, ``api_key``, ``models``, ``default_model``,
      ``headers``)
    - ``default_provider_id``

    Providers whose ``api_key`` field is the mask placeholder (``"***"``)
    keep their existing key on update, matching the rest of FiestaBoard's
    masked-secret pattern.
    """
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object.")
    cm = get_config_manager()
    return cm.set_ai_providers(body)


@app.post("/settings/ai/test")
async def test_ai_provider(request: Request):
    """Send a tiny smoke-test request to a configured provider.

    Body: ``{provider_id?: str, model?: str, provider?: dict}``. When
    ``provider`` is supplied, its fields override the persisted config so
    unsaved drafts in the settings UI can be tested without saving first.
    A masked ``api_key`` (``"***"``) is resolved to the stored key by
    ``provider_id``. Otherwise the persisted provider is loaded by id.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    provider_id = body.get("provider_id") if isinstance(body, dict) else None
    model = body.get("model") if isinstance(body, dict) else None
    draft = body.get("provider") if isinstance(body, dict) else None

    cm = get_config_manager()

    if isinstance(draft, dict):
        provider = dict(draft)
        if provider.get("api_key") == "***":
            stored_id = provider.get("id") or provider_id
            stored = cm.get_ai_provider(stored_id) if stored_id else None
            provider["api_key"] = (stored or {}).get("api_key", "")
    else:
        block = cm.get_ai_providers()
        if not block.get("providers"):
            raise HTTPException(
                status_code=400,
                detail="No AI providers are configured.",
            )
        if provider_id:
            provider = cm.get_ai_provider(provider_id)
            if provider is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"AI provider {provider_id!r} not found.",
                )
        else:
            default_id = block.get("default_provider_id")
            provider = (cm.get_ai_provider(default_id) if default_id else None) or block["providers"][0]

    from .ai.generator import test_provider as ai_test_provider

    result = await ai_test_provider(provider, model=model)
    return result


# Server-side execution of chat operations (Phase 2 Task 11): the web
# drawer posts validated tool calls here so chat and MCP share one
# executor per op instead of the browser re-implementing each one.
from .ai.routes import router as ai_router  # noqa: E402

app.include_router(ai_router)


@app.get("/pages/ai/context")
async def get_ai_context(device_type: str = "flagship"):
    """Return the variable list + exemplars that would be sent to the model.

    Useful for debugging the prompt; never includes API keys.
    """
    if device_type not in ("flagship", "note"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid device_type: {device_type!r}",
        )

    from .ai.prompt_builder import build_prompt

    variables = _collect_ai_variables()
    demos = _collect_plugin_demos()

    context = build_prompt(
        user_prompt="(no prompt — debug context only)",
        device_type=device_type,  # type: ignore[arg-type]
        variables=variables,
        plugin_demos=demos,
    )
    return context.to_dict()


@app.post("/pages/ai/generate")
async def generate_ai_page(request: Request):
    """Ask the user's configured LLM for a draft template page.

    Body: ``{prompt, device_type, provider_id?, model?, current_page?}``.
    Returns ``{page, model_used, provider_id, warnings, usage}``.

    Does **not** persist anything: the editor inserts the returned page
    locally and the user must click Save to keep it.
    """
    _ai_generate_throttle_check()

    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object.")

    prompt = body.get("prompt")
    device_type = body.get("device_type", "flagship")
    provider_id = body.get("provider_id")
    model = body.get("model")
    current_page = body.get("current_page")

    if not isinstance(prompt, str) or not prompt.strip():
        raise HTTPException(status_code=400, detail="`prompt` is required.")
    if device_type not in ("flagship", "note"):
        raise HTTPException(status_code=400, detail=f"Invalid device_type: {device_type!r}")
    if current_page is not None and not isinstance(current_page, dict):
        raise HTTPException(status_code=400, detail="`current_page` must be an object.")

    cm = get_config_manager()
    providers_block = cm.get_ai_providers()
    variables = _collect_ai_variables()
    demos = _collect_plugin_demos()

    from .ai.generator import AIGenerationError, _user_safe_error_message
    from .ai.generator import generate_page as ai_generate_page

    try:
        async with _AI_GENERATE_SEMAPHORE:
            result = await ai_generate_page(
                user_prompt=prompt,
                device_type=device_type,
                providers_block=providers_block,
                variables=variables,
                plugin_demos=demos,
                current_page=current_page,
                provider_id=provider_id,
                model=model,
            )
    except AIGenerationError as exc:
        # Predictable, user-visible failures: 400 with the message in
        # the body so the UI can render it as a warning.  Funnel the message
        # through a sanitizer so static analysis (py/stack-trace-exposure)
        # sees a constant-character flow, not raw exception data.
        raise HTTPException(status_code=400, detail=_user_safe_error_message(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected error in /pages/ai/generate")
        raise HTTPException(
            status_code=500,
            detail=("Unexpected AI generation error. See server logs for details."),
        ) from None

    return result


@app.post("/pages/ai/chat")
async def chat_ai_page(request: Request):
    """Stream a multi-turn AI chat for refining/building a page.

    Body: ``{messages: [{role, content}], device_type, current_page?,
    provider_id?, model?}``.

    Returns a Server-Sent Events stream. Event types match what
    :func:`src.ai.chat.stream_chat` yields:

    - ``text``      — token-level prose deltas
    - ``tool_call`` — a validated structured operation
                       (see :mod:`src.ai.chat_ops`)
    - ``warning``   — recoverable issue (e.g. malformed tool block)
    - ``error``     — fatal issue, stream is about to close
    - ``done``      — terminal frame with usage + model_used

    Like ``/pages/ai/generate``, this never persists anything: the
    editor applies tool calls locally and the user must click Save.

    Note: we deliberately skip the per-second throttle here. Chat is
    conversational — the user may send several messages back-to-back
    (especially when iterating on a design), and a 429 mid-conversation
    is jarring. The semaphore below caps concurrent streams instead,
    which is the real protection against runaway clients.
    """

    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object.")

    messages = body.get("messages")
    device_type = body.get("device_type", "flagship")
    provider_id = body.get("provider_id")
    model = body.get("model")
    current_page = body.get("current_page")
    available_pages = body.get("available_pages")
    installed_plugins = body.get("installed_plugins")
    available_schedules = body.get("available_schedules")
    available_collections = body.get("available_collections")
    registry_plugins = body.get("registry_plugins")
    # Which chat panel is calling us — "editor" (inline panel inside the
    # page editor) vs "global" (global drawer). Steers the AI's choice
    # between in-place page edits and navigation. Defaults to "global"
    # for old clients that don't send it.
    surface = body.get("surface", "global")
    if surface not in ("editor", "global"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid surface: {surface!r} (expected 'editor' or 'global').",
        )

    if not isinstance(messages, list) or not messages:
        raise HTTPException(status_code=400, detail="`messages` must be a non-empty array.")
    if device_type not in ("flagship", "note"):
        raise HTTPException(status_code=400, detail=f"Invalid device_type: {device_type!r}")
    if current_page is not None and not isinstance(current_page, dict):
        raise HTTPException(status_code=400, detail="`current_page` must be an object.")
    if available_pages is not None and not isinstance(available_pages, list):
        raise HTTPException(status_code=400, detail="`available_pages` must be an array.")
    if installed_plugins is not None and not isinstance(installed_plugins, list):
        raise HTTPException(status_code=400, detail="`installed_plugins` must be an array.")
    if available_schedules is not None and not isinstance(available_schedules, list):
        raise HTTPException(status_code=400, detail="`available_schedules` must be an array.")
    if available_collections is not None and not isinstance(available_collections, list):
        raise HTTPException(status_code=400, detail="`available_collections` must be an array.")
    if registry_plugins is not None and not isinstance(registry_plugins, list):
        raise HTTPException(status_code=400, detail="`registry_plugins` must be an array.")

    cm = get_config_manager()
    providers_block = cm.get_ai_providers()
    variables = _collect_ai_variables()
    demos = _collect_plugin_demos()

    from .ai.chat import stream_chat as ai_stream_chat

    async def event_source():
        """Render the normalized event stream as SSE bytes.

        Holds the AI semaphore for the duration of the stream so a
        client that drops mid-response still releases the slot via
        ``finally`` when the generator is closed.
        """
        try:
            await _AI_GENERATE_SEMAPHORE.acquire()
        except Exception:
            yield _format_sse_event("error", {"message": "Could not acquire AI lock."})
            return
        try:
            try:
                async for evt in ai_stream_chat(
                    messages=messages,
                    device_type=device_type,
                    providers_block=providers_block,
                    variables=variables,
                    plugin_demos=demos,
                    current_page=current_page,
                    available_pages=available_pages,
                    installed_plugins=installed_plugins,
                    available_schedules=available_schedules,
                    available_collections=available_collections,
                    registry_plugins=registry_plugins,
                    surface=surface,
                    provider_id=provider_id,
                    model=model,
                ):
                    yield _format_sse_event(evt["event"], evt["data"])
            except Exception:
                logger.exception("Unexpected error in /pages/ai/chat")
                yield _format_sse_event(
                    "error",
                    {"message": ("Unexpected AI chat error. See server logs for details.")},
                )
        finally:
            _AI_GENERATE_SEMAPHORE.release()

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",  # disable nginx buffering for SSE
            "Connection": "keep-alive",
        },
    )


def _format_sse_event(event: str, data: dict[str, Any]) -> bytes:
    """Serialize a single Server-Sent Event frame.

    SSE requires ``event:``/``data:`` on separate lines and a blank
    line as the frame terminator. JSON-encode ``data`` so multi-line
    strings don't break the framing.
    """
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n".encode()


def _collect_ai_variables() -> dict[str, dict[str, dict[str, Any]]]:
    """Variable registry to pass to the AI prompt builder.

    Mirrors what ``GET /templates/variables`` exposes so the model and
    the UI's variable picker stay in sync.
    """
    try:
        from .plugins import get_plugin_registry as _get_registry
    except ImportError:
        return {}
    try:
        registry = _get_registry()
        return registry.get_all_variables_with_metadata()
    except Exception as exc:
        logger.warning("Could not collect AI variables: %s", exc)
        return {}


def _collect_plugin_demos() -> list[dict[str, Any]]:
    """Return plugin-supplied demo pages (from each manifest's ``demo`` block).

    Used as exemplars in the prompt. Only demos for *enabled* plugins are
    included so the model doesn't suggest variables the user can't use.
    """
    try:
        from .plugins import get_plugin_registry as _get_registry
    except ImportError:
        return []
    demos: list[dict[str, Any]] = []
    try:
        registry = _get_registry()
        manifests = getattr(registry, "_manifests", {})
        enabled = getattr(registry, "_enabled", {})
        for plugin_id, manifest in manifests.items():
            if not enabled.get(plugin_id, False):
                continue
            demo = getattr(manifest, "demo", None)
            if demo is None:
                continue
            demos.append(
                {
                    "name": getattr(demo, "name", plugin_id),
                    "device_type": getattr(demo, "device_type", "flagship"),
                    "template": list(getattr(demo, "template", []) or []),
                    "line_metadata": list(getattr(demo, "line_metadata", []) or []),
                    "duration_seconds": getattr(demo, "duration_seconds", 300),
                }
            )
    except Exception as exc:
        logger.warning("Could not collect plugin demos: %s", exc)
    return demos


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
    _fiestaboard_profile,
    _managed_externally,
    _resolve_snapshot_name,
    _updater_probe,
    _updater_token,
    _updater_url,
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


class SilenceScheduleRequest(BaseModel):
    """Request body for updating the silence schedule feature."""

    enabled: bool
    start_time: str
    end_time: str
    mode: str | None = None  # "freeze" (default), "indicator", or "page"
    page_id: str | None = None  # Page id to display when mode == "page"
    indicator_text: str | None = None  # Custom text to display when mode == "indicator"
    indicator_position: str | None = None  # Position: center, top-left, top-right, bottom-left, bottom-right
    # Board to target (issue #1788). Omitted → the install-wide schedule.
    # Deliberately in the BODY, not the URL, so the endpoint path is unchanged.
    board_id: str | None = None


@app.put("/settings/silence-schedule")
async def update_silence_schedule(request: SilenceScheduleRequest):
    """
    Update the silence schedule configuration.

    `silence_schedule` is a system feature (not a plugin). Times must be in
    UTC ISO format (e.g. "04:00+00:00"); the UI converts local time to UTC
    before calling this endpoint.

    `mode` selects what happens while silence is active:
      - "indicator" (default) - show a clean "SNOOZING" message sized to the device
      - "freeze" - leave whatever is on the board, stop sending updates
      - "page" - display the page identified by `page_id` and freeze it

    `board_id` (optional, issue #1788) targets one board: the write lands in
    `features.silence_schedule.by_board[board_id]` and the install-wide layer
    is left alone. Omitted → the install-wide layer is written, which is what
    every board without its own override resolves to.
    """
    config_manager = get_config_manager()

    board_id = request.board_id
    if board_id is not None:
        _require_board(board_id)

    # Validate mode and page_id together
    mode = request.mode if request.mode in ("indicator", "freeze", "page") else "freeze"
    page_id: str | None = None
    if mode == "page":
        if not request.page_id:
            raise HTTPException(
                status_code=400,
                detail="page_id is required when mode is 'page'",
            )
        page_id = request.page_id
    elif request.page_id:
        # Preserve a previously selected page even when mode is not "page",
        # so the user can toggle back without losing their choice.
        page_id = request.page_id

    # Normalize indicator_text: uppercase, strip, fallback to "SNOOZING"
    indicator_text_raw = request.indicator_text
    if isinstance(indicator_text_raw, str) and indicator_text_raw.strip():
        indicator_text = indicator_text_raw.strip().upper()
    else:
        indicator_text = "SNOOZING"

    # Normalize indicator_position
    _valid_positions = ("center", "top-left", "top-right", "bottom-left", "bottom-right")
    indicator_position = request.indicator_position if request.indicator_position in _valid_positions else "center"

    # Enforce page<->board size compatibility (issue #1788, mirroring #1245's
    # rule on PUT /settings/active-page). Without this a 22x6 Flagship page
    # could be selected as the silence page of a 15x3 Note board. There is no
    # board to validate against on an install-wide write.
    if board_id is not None and page_id:
        compat = check_ref_board_compatibility(page_id, board_id)
        if not compat.ok:
            raise HTTPException(status_code=400, detail=compat.error)

    updated = {
        "enabled": request.enabled,
        "start_time": request.start_time,
        "end_time": request.end_time,
        "mode": mode,
        "page_id": page_id,
        "indicator_text": indicator_text,
        "indicator_position": indicator_position,
    }

    if board_id is not None:
        success = config_manager.set_silence_schedule_for_board(board_id, updated)
    else:
        success = config_manager.set_feature("silence_schedule", updated)
        # The engine resolves silence per board on every install
        # (``check_and_send_for_board(primary_id, ...)``), so an install-wide
        # write that leaves a board-scoped copy in place is shadowed key by
        # key: the user turns silence off, the API says 200, and the board
        # keeps snoozing at the old time. On a single-board install there is
        # no meaningful difference between "the install default" and "this
        # board", so drop the override rather than let it win (issue #1788
        # review). Multi-board installs are untouched — there the overrides
        # are the whole point.
        if success:
            try:
                boards = get_settings_service().get_board_settings().boards or []
            except Exception:  # pragma: no cover - defensive: never fail the save
                boards = []
            if len(boards) == 1 and isinstance(boards[0], dict) and boards[0].get("id"):
                config_manager.prune_silence_schedule_for_board(str(boards[0]["id"]))
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to persist silence schedule configuration",
        )

    logger.info(
        "Silence schedule updated for board=%s: enabled=%s, start=%s, end=%s, mode=%s, page_id=%s, "
        "indicator_text=%s, indicator_position=%s",
        board_id or "(install-wide)",
        request.enabled,
        request.start_time,
        request.end_time,
        mode,
        page_id,
        indicator_text,
        indicator_position,
    )

    if board_id is not None:
        from .config import resolve_silence_schedule

        config = resolve_silence_schedule(config_manager.get_feature("silence_schedule"), board_id)
    else:
        config = config_manager.get_feature("silence_schedule") or updated

    return {
        "status": "success",
        "config": config,
        "board_id": board_id,
    }


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


@app.get("/settings/transitions")
async def get_transition_settings():
    """Get current transition animation settings."""
    settings_service = get_settings_service()
    transition = settings_service.get_transition_settings()
    return {
        "strategy": transition.strategy,
        "step_interval_ms": transition.step_interval_ms,
        "step_size": transition.step_size,
        "available_strategies": VALID_STRATEGIES,
    }


# =============================================================================
# Transition plugins (beta) — moved to src/transitions/routes.py (slice 8)
# =============================================================================

from .transitions.routes import router as transitions_router  # noqa: E402

app.include_router(transitions_router)


@app.put("/settings/transitions")
async def update_transition_settings(request: dict):
    """
    Update transition animation settings.

    Body can include:
    - strategy: One of column, reverse-column, edges-to-center, row, diagonal, random,
                "plugin:<id>" to drive a transition plugin, or null to disable.
    - step_interval_ms: Delay between animation steps (ms), or null for default
    - step_size: How many columns/rows animate at once, or null for default
    """
    settings_service = get_settings_service()

    try:
        # Use ... as sentinel for "not provided"
        strategy = request.get("strategy", ...)
        step_interval_ms = request.get("step_interval_ms", ...)
        step_size = request.get("step_size", ...)

        transition = settings_service.update_transition_settings(
            strategy=strategy, step_interval_ms=step_interval_ms, step_size=step_size
        )

        return {"status": "success", "settings": transition.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/settings/output")
async def get_output_settings():
    """Get current output target settings."""
    settings_service = get_settings_service()
    output = settings_service.get_output_settings()
    return {"target": output.target, "effective_target": output.target, "available_targets": VALID_OUTPUT_TARGETS}


@app.put("/settings/output")
async def update_output_settings(request: dict):
    """
    Update output target settings.

    Body should include:
    - target: One of "ui", "board", or "both"
    """
    if "target" not in request:
        raise HTTPException(status_code=400, detail="target parameter required")

    settings_service = get_settings_service()

    try:
        output = settings_service.set_output_target(request["target"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # Switching away from "ui" must resync the hardware (issue #1748). While
    # target was "ui" the display loop short-circuited before rendering, so
    # every board's content cache still holds whatever was last actually sent.
    # Without this the next poll sees "content unchanged, skipping send" and
    # the board stays stale until the content happens to change. The target is
    # a global setting, so every board is invalidated, not just the primary.
    svc = get_service()
    runtimes = getattr(svc, "runtimes", None) if svc else None
    # Only a real mapping is iterated (a Mock from an older fixture is not).
    if isinstance(runtimes, dict):
        for board_id in list(runtimes):
            try:
                svc.invalidate_board_content(board_id)
            except Exception as e:  # never fail the settings write on a cache reset
                logger.debug("Could not invalidate board %s after output-target change: %s", board_id, e)

    return {"status": "success", "settings": output.to_dict()}


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


@app.get("/settings/active-page")
async def get_active_page(board_id: str | None = None):
    """Get the currently active page ID.

    Args:
        board_id: Optional board to read (query param). Omitted → primary
            board, legacy behavior (issue #1244).
    """
    settings_service = get_settings_service()
    if board_id is not None:
        page_id = settings_service.get_active_page_id(board_id=board_id)
    else:
        page_id = settings_service.get_active_page_id()
    return {
        "page_id": page_id,
        "resolved_page_id": _resolve_active_page_id(page_id),
        "resolved_next_check_seconds": _resolve_next_check_seconds(page_id),
        "board_id": board_id,
    }


@app.put("/settings/active-page")
async def set_active_page(request: dict):
    """
    Set the active page ID.

    Body should include:
    - page_id: Page ID to set as active, or null to clear
    - board_id: Optional board to target. Omitted → primary board,
      legacy behavior (issue #1244).

    When a page is set, it will be immediately rendered and sent to the board.

    Response: ``sent_to_board`` reports whether content actually reached the
    board, and ``error`` carries the render/send failure reason (null when the
    send succeeded or was skipped benignly — paused board, UI-only output,
    unchanged content). The page selection itself is persisted either way.
    """
    settings_service = get_settings_service()
    page_service = get_page_service()
    service = get_service()

    page_id = request.get("page_id")
    board_id = request.get("board_id")
    board = None
    if board_id is not None:
        board = _require_board(board_id)
    collection_service = get_collection_service()

    # Validate page or collection exists if not clearing
    page = None
    render_page_id = page_id
    if page_id is not None:
        if is_collection_id(page_id):
            collection = collection_service.get_collection(page_id)
            if not collection:
                raise HTTPException(status_code=404, detail=f"Collection not found: {page_id}")
            render_page_id = collection_service.resolve_page_id(page_id)
            if render_page_id:
                page = page_service.get_page(render_page_id)
        else:
            page = page_service.get_page(page_id)
            if not page:
                raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")

    # Enforce page<->board size compatibility (issue #1245). Collections are
    # allowed when at least one member fits (non-fitting members become
    # warnings); plain pages must match the board size exactly.
    compat_warnings: list[str] = []
    if page_id is not None:
        compat = check_ref_board_compatibility(page_id, request.get("board_id"))
        if not compat.ok:
            raise HTTPException(status_code=400, detail=compat.error)
        compat_warnings = compat.warnings

    # Everything from the trigger dismissal through the board send blocks:
    # disk writes, a plugin-fan-out render, then the board network call plus
    # an up-to-seconds transition animation. It runs as one worker-thread
    # unit so the event loop keeps serving requests (#1826). The settings
    # write itself is not internally locked yet — per-store locking is
    # Track A2's job (#1848).
    def _work() -> tuple[bool, bool, str | None]:
        # Dismiss any active plugin triggers so the user's explicit page change
        # actually sticks. Without this, a plugin re-emitting the same trigger
        # every display loop tick (e.g. calendar_sub during a countdown window)
        # would silently overwrite the user's selection. See issue #856.
        if PLUGIN_SYSTEM_AVAILABLE:
            from .triggers.service import get_trigger_service

            get_trigger_service().dismiss_active_for_user_override()

        # Set the active page (stores the collection ID or page ID as-is).
        # An explicit board_id targets that board's slot; omitted keeps the
        # legacy primary-board call (issue #1244).
        if board_id is not None:
            settings_service.set_active_page_id(page_id, board_id=board_id)
        else:
            settings_service.set_active_page_id(page_id)

        # Resolve the client for the immediate send: explicit board_id routes to
        # that board's client, omitted keeps the legacy primary-client path.
        send_client = None
        if service:
            send_client = service.get_board_client(board_id) if board_id is not None else service.vb_client

        # Immediately send to board if a page is set. The page selection is
        # persisted either way; a failed render/send is a partial failure that
        # must be reported, not silently swallowed (issue #1791).
        sent_to_board = False
        paused = False
        send_error: str | None = None
        if render_page_id and page and send_client and settings_service.should_send_to_board():
            # Skip immediate send when the board is paused (issue #970). The
            # active-page selection is still persisted so it takes effect when
            # the user later resumes the board.
            if _board_is_paused(board_id):
                logger.info("Board is paused - skipping immediate active-page send")
                paused = True
            else:
                result = page_service.preview_page(render_page_id, force_refresh=True)
                if result and result.available:
                    system_transition = settings_service.get_transition_settings()
                    strategy = page.transition_strategy if page.transition_strategy else system_transition.strategy
                    interval_ms = (
                        page.transition_interval_ms
                        if page.transition_interval_ms is not None
                        else system_transition.step_interval_ms
                    )
                    step_size = (
                        page.transition_step_size
                        if page.transition_step_size is not None
                        else system_transition.step_size
                    )

                    # Size the grid to the explicit target board when given
                    # (issue #1244); otherwise keep the page's device type.
                    if board is not None:
                        dims = _board_dims(board)
                    else:
                        dims = resolve_dimensions(page.device_type, page.notes_wide, page.notes_tall)
                    board_array = text_to_board_array(result.formatted, rows=dims.rows, cols=dims.cols)
                    # render() serializes concurrent senders via the client's
                    # per-board _send_lock, so worker threads can't interleave.
                    success, was_sent = send_client.render(
                        board_array,
                        strategy=strategy,
                        step_interval_ms=interval_ms,
                        step_size=step_size,
                        device_type=(board.get("device_type") if board is not None else page.device_type),
                    )
                    sent_to_board = was_sent
                    if not success:
                        send_error = f"Failed to send page to board: {page_id}"
                        logger.warning(f"Failed to send active page to board: {page_id}")
                    elif was_sent and (board_id is None or board_id == settings_service.get_primary_board_id()):
                        # Adaptive post-send refresh polls the primary board only.
                        service.request_board_refresh()
                else:
                    # A network/plugin failure surfaces here as an unavailable
                    # render — report it instead of skipping silently (#1791).
                    render_error = getattr(result, "error", None) if result else None
                    send_error = render_error or f"Failed to render page: {render_page_id}"
                    logger.warning(f"Active page set but render unavailable, not sent: {render_page_id}")
        return sent_to_board, paused, send_error

    sent_to_board, paused, send_error = await run_board_send(_work)

    # status stays "success" (the page selection itself was persisted); a
    # render/send problem is reported via error + sent_to_board=False, the
    # same partial-failure contract page-builder already consumes.
    response = {
        "status": "success",
        "page_id": page_id,
        "sent_to_board": sent_to_board,
        "paused": paused,
        "board_id": board_id,
        "error": send_error,
    }
    if compat_warnings:
        response["warnings"] = compat_warnings
    return response


@app.get("/settings/temporary-override")
async def get_temporary_override():
    """Get the current temporary override status."""
    settings_service = get_settings_service()
    return _temporary_override_payload(settings_service.get_temporary_override())


@app.post("/settings/temporary-override")
async def set_temporary_override(request: dict):
    """
    Activate a temporary override, from a saved page or from inline content.

    Exactly one of ``page_id`` or ``template`` must be supplied.

    Body:
      - page_id (str): Page (or collection) to show during the override
      - template (list[str]): Inline one-off board content, never persisted as
        a Page (issue #1787)
      - line_metadata (list[dict], optional): Per-line alignment/wrap for the
        inline form
      - device_type (str, optional): Geometry the inline content was composed
        for ("flagship" | "note" | "note_array"); defaults to flagship
      - notes_wide / notes_tall (int, optional): note_array geometry
      - duration_minutes (int, optional): How long to show it (1–480). Omit for
        an indefinite override that lasts until the user cancels it.
      - revert_mode (str, optional): "schedule" | "blank" | "page" (default: "schedule")
      - revert_page_id (str, optional): Required when revert_mode is "page"

    Deliberately not guarded by silence or pause: a user-initiated override is
    meant to beat the silence schedule (issue #949).
    """
    from datetime import datetime, timedelta

    from .devices import DEFAULT_DEVICE_TYPE, DEVICE_TYPES, MAX_NOTES_PER_AXIS
    from .settings.service import (
        TEMPORARY_OVERRIDE_DURATION_MAX,
        TEMPORARY_OVERRIDE_DURATION_MIN,
        VALID_REVERT_MODES,
        TemporaryOverride,
    )

    settings_service = get_settings_service()
    page_service = get_page_service()

    page_id = request.get("page_id")
    template = request.get("template")

    if page_id and template is not None:
        raise HTTPException(status_code=422, detail="Supply either page_id or template, not both")
    if not page_id and template is None:
        raise HTTPException(status_code=422, detail="Either page_id or template is required")

    device_type = None
    line_metadata = None
    notes_wide = None
    notes_tall = None

    if template is not None:
        # --- Inline (one-off) form ---
        if not isinstance(template, list) or not template:
            raise HTTPException(status_code=422, detail="template must be a non-empty list of strings")
        if not all(isinstance(line, str) for line in template):
            raise HTTPException(status_code=422, detail="template must contain only strings")

        device_type = request.get("device_type") or DEFAULT_DEVICE_TYPE
        if device_type not in DEVICE_TYPES:
            raise HTTPException(status_code=422, detail=f"device_type must be one of {list(DEVICE_TYPES)}")

        line_metadata = request.get("line_metadata")
        if line_metadata is not None and (
            not isinstance(line_metadata, list) or not all(isinstance(m, dict) for m in line_metadata)
        ):
            raise HTTPException(status_code=422, detail="line_metadata must be a list of objects")

        for key, raw in (("notes_wide", request.get("notes_wide")), ("notes_tall", request.get("notes_tall"))):
            if raw is None:
                continue
            try:
                value = int(raw)
            except (TypeError, ValueError):
                raise HTTPException(status_code=422, detail=f"{key} must be an integer") from None
            if not (1 <= value <= MAX_NOTES_PER_AXIS):
                raise HTTPException(status_code=422, detail=f"{key} must be between 1 and {MAX_NOTES_PER_AXIS}")
            if key == "notes_wide":
                notes_wide = value
            else:
                notes_tall = value

        dims = resolve_dimensions(device_type, notes_wide or 1, notes_tall or 1)
        if len(template) > dims.rows:
            raise HTTPException(
                status_code=422,
                detail=f"template has {len(template)} lines but this board fits {dims.rows}",
            )
    else:
        # --- Saved page form (unchanged; collections are also valid) ---
        if not is_collection_id(page_id):
            if not page_service.get_page(page_id):
                raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")
        else:
            collection_service = get_collection_service()
            if not collection_service.get_collection(page_id):
                raise HTTPException(status_code=404, detail=f"Collection not found: {page_id}")

    duration_minutes = request.get("duration_minutes")
    expires_at = None
    if duration_minutes is not None:
        try:
            duration_minutes = int(duration_minutes)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="duration_minutes must be an integer") from None
        if not (TEMPORARY_OVERRIDE_DURATION_MIN <= duration_minutes <= TEMPORARY_OVERRIDE_DURATION_MAX):
            raise HTTPException(
                status_code=422,
                detail=f"duration_minutes must be between {TEMPORARY_OVERRIDE_DURATION_MIN} and {TEMPORARY_OVERRIDE_DURATION_MAX}",
            )
        expires_at = (datetime.now(UTC) + timedelta(minutes=duration_minutes)).isoformat()

    revert_mode = request.get("revert_mode", "schedule")
    if revert_mode not in VALID_REVERT_MODES:
        raise HTTPException(status_code=422, detail=f"revert_mode must be one of {VALID_REVERT_MODES}")

    revert_page_id = request.get("revert_page_id")
    if revert_mode == "page":
        if not revert_page_id:
            raise HTTPException(status_code=422, detail="revert_page_id is required when revert_mode is 'page'")
        if not is_collection_id(revert_page_id):
            if not page_service.get_page(revert_page_id):
                raise HTTPException(status_code=404, detail=f"Revert page not found: {revert_page_id}")

    override = TemporaryOverride(
        page_id=page_id or None,
        expires_at=expires_at,
        revert_mode=revert_mode,
        revert_page_id=revert_page_id,
        template=template,
        line_metadata=line_metadata,
        device_type=device_type,
        notes_wide=notes_wide,
        notes_tall=notes_tall,
    )
    settings_service.set_temporary_override(override)

    # Clear the display cache so the next poll sends the override immediately
    svc = get_service()
    if svc:
        svc._last_active_page_content = None

    return _temporary_override_payload(override)


@app.delete("/settings/temporary-override")
async def clear_temporary_override():
    """Cancel the active temporary override and trigger an immediate board refresh."""
    settings_service = get_settings_service()
    override = settings_service.get_temporary_override()
    revert_mode = override.revert_mode if override else None
    settings_service.clear_temporary_override()

    # Apply revert side-effects server-side (same logic as expiry in the display loop)
    if override and override.revert_mode == "page" and override.revert_page_id:
        settings_service.set_active_page_id(override.revert_page_id)

    # Force an immediate re-render so the board shows the reverted state
    svc = get_service()
    if svc:
        svc._last_active_page_content = None

    return {"status": "cleared", "revert_mode": revert_mode}


@app.get("/settings/polling")
async def get_polling_settings():
    """Get current polling interval settings."""
    settings_service = get_settings_service()
    polling = settings_service.get_polling_settings()
    return polling.to_dict()


@app.put("/settings/polling")
async def update_polling_settings(request: dict):
    """
    Update polling interval settings.

    Accepted body fields:
    - interval_seconds: How often FiestaBoard checks active page (min 10, requires restart)
    - board_read_interval_local: How often to read board state in local mode (min 20)
    - board_read_interval_cloud: How often to read board state in cloud mode (min 20)
    """
    settings_service = get_settings_service()
    requires_restart = False

    try:
        if "interval_seconds" in request:
            interval_seconds = int(request["interval_seconds"])
            settings_service.set_polling_interval(interval_seconds)
            requires_restart = True

        if "board_read_interval_local" in request or "board_read_interval_cloud" in request:
            local = int(request["board_read_interval_local"]) if "board_read_interval_local" in request else None
            cloud = int(request["board_read_interval_cloud"]) if "board_read_interval_cloud" in request else None
            settings_service.set_board_read_intervals(local_seconds=local, cloud_seconds=cloud)

        polling = settings_service.get_polling_settings()
        return {
            "status": "success",
            "settings": polling.to_dict(),
            "requires_restart": requires_restart,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/settings/board")
async def get_board_settings():
    """Get current board settings (display type, boards array, devices)."""
    settings_service = get_settings_service()
    board = settings_service.get_board_settings()
    return board.to_dict()


@app.put("/settings/board")
async def update_board_settings(request: dict):
    """
    Update board settings.

    Body may include:
    - board_type: "black", "white", or null for default
    - devices: list of device types (e.g. ["flagship", "note"]) for backward compatibility
    - boards: full list of board instance dicts
    """
    settings_service = get_settings_service()

    try:
        if "devices" in request:
            devices = request["devices"]
            if not isinstance(devices, list):
                raise HTTPException(status_code=400, detail="devices must be a list")
            board = settings_service.set_devices(devices)
            _reinitialize_board_clients()
            return {"status": "success", "settings": board.to_dict()}
        if "boards" in request:
            boards = request["boards"]
            if not isinstance(boards, list):
                raise HTTPException(status_code=400, detail="boards must be a list")
            board = settings_service.set_boards(boards)
            _reinitialize_board_clients()
            return {"status": "success", "settings": board.to_dict()}
        if "board_type" in request:
            board_type = request["board_type"]
            board = settings_service.set_board_type(board_type)
            return {"status": "success", "settings": board.to_dict()}
        raise HTTPException(
            status_code=400,
            detail="One of board_type, devices, or boards is required",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _reinitialize_board_clients() -> None:
    """Rebuild board clients after a boards-list mutation.

    Kept as a name here because unconverted domains patch
    ``src.api_server._reinitialize_board_clients``; the implementation moved to
    ``src/display_runtime.py`` so routers can reach it without importing this
    module.
    """
    reinitialize_board_clients()


@app.post("/settings/board/add")
async def add_board_instance(request: dict):
    """Add a new board instance. Body: device_type, optional name and other board fields."""
    if "device_type" not in request:
        raise HTTPException(status_code=400, detail="device_type is required")
    settings_service = get_settings_service()
    try:
        board = settings_service.add_board(request)
        _reinitialize_board_clients()
        return {"status": "success", "settings": board.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.delete("/settings/board/{board_id}")
async def remove_board_instance(board_id: str):
    """Remove a board instance by ID.

    A board still referenced by a FiestaPanel is removed by deleting the
    panel — pulling it out from under a live panel blanks the TV and
    orphans the panel, so that request is refused with a 409.
    """
    referencing_panel = next(
        (p for p in get_panel_service().list_panels() if p.board_id == board_id),
        None,
    )
    if referencing_panel is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Board is in use by FiestaPanel '{referencing_panel.name}'. "
                "Delete the panel in Settings → FiestaPanel instead."
            ),
        )
    settings_service = get_settings_service()
    try:
        board = settings_service.remove_board(board_id)
        _reinitialize_board_clients()
        return {"status": "success", "settings": board.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/settings/board/{board_id}/pause")
async def set_board_paused(board_id: str, request: dict):
    """Pause or resume a board (issue #970).

    Body: ``{"paused": bool}``. When paused, FiestaBoard will not push
    anything to this board from any code path (polling loop, schedule,
    manual sends, plugin triggers, MQTT, debug, welcome, etc) until the
    board is resumed.
    """
    if "paused" not in request:
        raise HTTPException(status_code=400, detail="paused is required")
    if not isinstance(request["paused"], bool):
        raise HTTPException(status_code=400, detail="paused must be a boolean")
    _require_board(board_id)
    settings_service = get_settings_service()
    paused = settings_service.set_paused(request["paused"], board_id=board_id)
    return {
        "status": "success",
        "board_id": board_id,
        "paused": paused,
        "settings": settings_service.get_board_settings().to_dict(),
    }


@app.post("/settings/board/{board_id}/detect-size")
async def detect_board_size(board_id: str):
    """Auto-detect a board's device type and dimensions from its live layout.

    Reads the board's current message over its own transport (local / cloud /
    note-array, via ``board_client_from_board_dict``) and classifies the grid
    shape with :func:`classify_dimensions`.

    Returns ``device_type``, ``rows``, ``cols`` and — for note arrays —
    ``notes_wide``, ``notes_tall`` and ``matched_preset``.

    Errors: 404 (unknown board), 400 (board not configured), 422 (board
    returned no layout, or an unclassifiable grid).
    """
    settings_service = get_settings_service()
    boards = settings_service.get_board_settings().boards or []

    board_dict = next((b for b in boards if b.get("id") == board_id), None)
    if board_dict is None:
        raise HTTPException(status_code=404, detail=f"Board {board_id} not found")

    from .devices import BoardInstance

    # A local-mode array's shape is DEFINED by its tile assignments — a local
    # read can only re-stitch the configured W×H (or fail on a partial array),
    # so "detection" would be a tautology. Only the Cloud API knows an array's
    # real shape; reject clearly instead of echoing the configuration back.
    if BoardInstance.from_dict(board_dict).uses_local_tiles:
        raise HTTPException(
            status_code=400,
            detail="Auto-detect is not available for local-mode note arrays — "
            "the array's size is defined by its tile assignments",
        )

    client = board_client_from_board_dict(board_dict)
    if client is None:
        raise HTTPException(
            status_code=400,
            detail=f"Board {board_id} is not configured (missing credentials)",
        )

    grid = client.read_current_message()
    if grid is None:
        raise HTTPException(
            status_code=422,
            detail=f"Board {board_id} returned no layout — board may be blank or unreachable",
        )

    rows = len(grid)
    cols = len(grid[0]) if rows > 0 else 0
    try:
        return classify_dimensions(rows, cols)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Board {board_id} returned an unclassifiable grid ({rows}×{cols}): {exc}",
        ) from exc


class BoardIdentifyRequest(BaseModel):
    """Request body for the local note-array identify flash.

    ``target: "tile"`` identifies one slot (``row``/``col`` required unless
    the credential override is supplied); ``target: "all"`` flashes every
    configured tile at once. The optional ``host``/``port``/``local_api_key``
    override lets the assign dialog identify a board BEFORE its tile is
    saved — in that case ``row``/``col`` name the slot being assigned.
    """

    target: str = "tile"
    row: int | None = None
    col: int | None = None
    host: str | None = None
    port: int | None = None
    local_api_key: str | None = None


@app.post("/settings/board/{board_id}/identify")
async def identify_board_tiles(board_id: str, request: BoardIdentifyRequest):
    """Flash slot positions onto local note-array tiles (monitor-arrangement style).

    Sends each targeted tile a 3×15 pattern labeling its slot so the user
    can see which physical board answers for which grid position. The real
    frame is restored automatically on the next display-loop cycle (the
    board's content dedupe and client caches are invalidated here); on a
    paused board the pattern persists until the board is resumed.

    Errors: 404 (unknown board), 400 (not a note array in local mode, bad
    target, or missing/unknown tile).
    """
    from .devices import BoardInstance, identify_pattern, is_note_array

    settings_service = get_settings_service()
    boards = settings_service.get_board_settings().boards or []
    board_dict = next((b for b in boards if b.get("id") == board_id), None)
    if board_dict is None:
        raise HTTPException(status_code=404, detail=f"Board {board_id} not found")

    instance = BoardInstance.from_dict(board_dict)
    if not is_note_array(instance.device_type) or instance.api_mode != "local":
        raise HTTPException(
            status_code=400,
            detail="Identify is only available for note arrays in local API mode",
        )

    if request.target not in ("tile", "all"):
        raise HTTPException(status_code=400, detail='target must be "tile" or "all"')

    # Resolve the set of (row, col, host, port, key) endpoints to flash
    targets: list[dict] = []
    if request.host is not None or request.local_api_key is not None:
        # Unsaved-tile override from the assign dialog
        if request.target != "tile" or request.row is None or request.col is None:
            raise HTTPException(
                status_code=400,
                detail="Credential override requires target='tile' with row and col",
            )
        if not request.host or not request.local_api_key:
            raise HTTPException(status_code=400, detail="host and local_api_key are both required")
        _validate_board_host(request.host)
        _validate_board_host_is_local_network(request.host)
        targets.append(
            {
                "row": request.row,
                "col": request.col,
                "host": request.host,
                "port": request.port or 7000,
                "local_api_key": request.local_api_key,
            }
        )
    else:
        configured = instance.configured_tiles()
        if request.target == "all":
            targets = configured
        else:
            if request.row is None or request.col is None:
                raise HTTPException(status_code=400, detail="row and col are required for target='tile'")
            tile = next(
                (t for t in configured if t["row"] == request.row and t["col"] == request.col),
                None,
            )
            if tile is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"No configured tile at row={request.row}, col={request.col}",
                )
            targets = [tile]
        if not targets:
            raise HTTPException(status_code=400, detail="Board has no configured tiles to identify")

    def flash_tile(tile: dict) -> dict:
        from .board_client import BoardClient

        pattern = identify_pattern(tile["row"], tile["col"], instance.notes_wide)
        try:
            client = BoardClient(
                api_key=tile["local_api_key"],
                host=tile["host"],
                use_cloud=False,
                skip_unchanged=False,
                port=tile.get("port") or None,
            )
            success, _ = client.send_characters(pattern, force=True)
        except Exception as exc:  # noqa: BLE001 — per-tile failure must not abort the rest
            logger.error(f"Identify failed for tile ({tile['row']},{tile['col']}): {exc}")
            success = False
        return {"row": tile["row"], "col": tile["col"], "success": success}

    results = await asyncio.gather(*(asyncio.to_thread(flash_tile, t) for t in targets))

    # Restore: invalidate the display loop's dedupe + client caches so the
    # next cycle re-sends the real frame over the identify pattern.
    service = get_service()
    if service is not None:
        service.invalidate_board_content(board_id)

    return {"status": "success", "board_id": board_id, "results": list(results)}


@app.get("/settings/display")
async def get_display_settings():
    """Get current web UI display settings."""
    settings_service = get_settings_service()
    return settings_service.get_display_settings().to_dict()


@app.put("/settings/display")
async def update_display_settings(request: dict):
    """
    Update web UI display settings.

    Body may include:
    - reduce_motion: bool — force reduced-motion CSS behaviour in the UI
    - board_animations: "on" | "desktop" | "off" — control split-flap board
      animation. "desktop" disables it on mobile screens only.
    - site_animations: "on" | "off" — control general UI transitions/hovers.
    - board_flap_speed: "hardware" | "quick" | "standard" | "relaxed", or a
      raw millisecond count clamped to [8, 2000] — how fast a tile flips one
      character in the ON-SCREEN board preview. Default "standard" (80ms).
      This is not the physical board: pacing for the hardware lives in
      /settings/transitions (step_interval_ms / step_size).
    """
    settings_service = get_settings_service()
    display = settings_service.update_display_settings(request)
    return {"status": "success", "settings": display.to_dict()}


@app.get("/settings/location")
async def get_location_settings():
    """Get current location settings for sun-based schedules (sunrise/sunset)."""
    settings_service = get_settings_service()
    return settings_service.get_location_settings().to_dict()


@app.put("/settings/location")
async def update_location_settings(request: dict):
    """
    Update location settings for sun-based schedules.

    Body may include:
    - latitude: float | null — Location latitude (-90 to 90)
    - longitude: float | null — Location longitude (-180 to 180)
    """
    settings_service = get_settings_service()
    location = settings_service.update_location_settings(request)
    return {"status": "success", "settings": location.to_dict()}


@app.get("/settings/location/sun-times")
async def get_location_sun_times(date: str | None = None):
    """
    Get sunrise and sunset times for the configured location on a given date.

    Query params:
    - date: ISO date string (YYYY-MM-DD); defaults to today in the configured timezone.

    Returns sunrise and sunset as HH:MM strings, or null values if location is not
    configured or sun times cannot be computed (e.g. polar day/night).
    """
    from datetime import date as date_cls

    from .schedules.sun_times import (
        get_effective_timezone,
        get_sun_times,
        get_today_in_timezone,
    )

    settings_service = get_settings_service()
    location = settings_service.get_location_settings()

    if location.latitude is None or location.longitude is None:
        return {"sunrise": None, "sunset": None, "location_configured": False}

    timezone_str = get_effective_timezone()

    if date:
        try:
            target_date = date_cls.fromisoformat(date)
        except ValueError:
            from fastapi import HTTPException

            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.") from None
    else:
        target_date = get_today_in_timezone(timezone_str)

    times = get_sun_times(location.latitude, location.longitude, target_date, timezone_str)
    if times is None:
        return {"sunrise": None, "sunset": None, "location_configured": True}

    return {
        "sunrise": times["sunrise"].strftime("%H:%M"),
        "sunset": times["sunset"].strftime("%H:%M"),
        "location_configured": True,
    }


@app.get("/settings/location/sun-times-week")
async def get_location_sun_times_week(week_start: str):
    """
    Get sunrise and sunset times for each day of a 7-day week.

    Query params:
    - week_start: ISO date string (YYYY-MM-DD) for the first day of the week.

    Returns a map of date strings to { sunrise, sunset } HH:MM values.
    """
    from datetime import date as date_cls
    from datetime import timedelta

    from .schedules.sun_times import get_effective_timezone, get_sun_times

    settings_service = get_settings_service()
    location = settings_service.get_location_settings()

    if location.latitude is None or location.longitude is None:
        return {"location_configured": False, "dates": {}}

    timezone_str = get_effective_timezone()

    try:
        start = date_cls.fromisoformat(week_start)
    except ValueError:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="Invalid week_start format. Use YYYY-MM-DD.") from None

    result: dict = {}
    for i in range(7):
        day = start + timedelta(days=i)
        times = get_sun_times(location.latitude, location.longitude, day, timezone_str)
        if times:
            result[day.isoformat()] = {
                "sunrise": times["sunrise"].strftime("%H:%M"),
                "sunset": times["sunset"].strftime("%H:%M"),
            }

    return {"location_configured": True, "dates": result}


# ==================== Beta Settings (HTTPS, etc.) ====================


def _beta_https_status() -> dict[str, Any]:
    """Return the runtime status of the HTTPS beta feature.

    Reports whether the cert files currently exist on disk and whether
    the fiestaupdater sidecar is reachable for one-click restarts.
    """
    from .system import https_certs

    cert_path, key_path = https_certs.cert_paths()
    return {
        "cert_present": https_certs.cert_exists(),
        "cert_path": str(cert_path),
        "key_path": str(key_path),
        "updater_available": bool(_updater_token()) and _updater_probe(),
    }


@app.get("/settings/beta")
async def get_beta_settings():
    """Get opt-in beta-feature settings + runtime status."""
    settings_service = get_settings_service()
    settings = settings_service.get_beta_settings()
    status = await asyncio.to_thread(_beta_https_status)
    return {
        "settings": settings.to_dict(),
        "https": status,
    }


@app.put("/settings/beta")
async def update_beta_settings(request: dict):
    """Update beta-feature settings.

    Body may include:
    - https_enabled: bool — enable/disable the HTTPS (Beta) feature.
    - transition_plugins_enabled: bool — enable/disable the experimental
      transition-plugin system (frame-by-frame board animations). Takes
      effect immediately; no restart required.

    Side effects:
    - When https_enabled flips to ``true``, a self-signed certificate is
      generated under ``data/certs/`` (if not already present). nginx
      will switch to HTTPS the next time the container starts.
    - When https_enabled flips to ``false``, the cert files are removed
      so the next container start reverts to HTTP.

    Returns the updated settings, the cert status, and a hint about
    whether a restart is required for the change to take effect.
    """
    from .system import https_certs

    settings_service = get_settings_service()
    previous = settings_service.get_beta_settings().https_enabled
    requested = request.get("https_enabled", previous) if isinstance(request, dict) else previous

    cert_error: str | None = None
    if "https_enabled" in (request or {}):
        if requested and not previous:
            # User just turned HTTPS on -> generate cert eagerly so nginx
            # finds it on the next restart. Failure here shouldn't block
            # persisting the user's preference, but we surface the error.
            try:
                await asyncio.to_thread(https_certs.generate_cert)
            except Exception:  # noqa: BLE001 - report to caller
                # Full detail stays in the server log; the raw exception can
                # carry paths/config internals (CodeQL py/stack-trace-exposure).
                logger.exception("Failed to generate HTTPS certificate")
                cert_error = "Certificate generation failed — check the server logs for details."
        elif previous and not requested:
            # User just turned HTTPS off -> remove the cert so nginx
            # falls back to HTTP on next restart.
            try:
                await asyncio.to_thread(https_certs.remove_cert)
            except Exception as e:  # noqa: BLE001
                logger.warning("Failed to remove HTTPS certificate: %s", e)

    updated = settings_service.update_beta_settings(request or {})
    status = await asyncio.to_thread(_beta_https_status)

    # A restart is required whenever the on/off state changed, since
    # nginx only re-reads its config on container start.
    restart_required = updated.https_enabled != previous

    response: dict[str, Any] = {
        "status": "success",
        "settings": updated.to_dict(),
        "https": status,
        "restart_required": restart_required,
    }
    if cert_error:
        response["status"] = "warning"
        response["cert_error"] = cert_error
    return response


@app.get("/settings/plugins")
async def get_plugin_settings():
    """Get plugin system settings."""
    settings_service = get_settings_service()
    return {"settings": settings_service.get_plugin_settings().to_dict()}


@app.put("/settings/plugins")
async def update_plugin_settings(request: dict):
    """Update plugin system settings.

    Body may include:
    - auto_update: bool — when true, plugins are updated automatically in the background.
    """
    settings_service = get_settings_service()
    updated = settings_service.update_plugin_settings(request or {})
    return {"status": "success", "settings": updated.to_dict()}


@app.get("/settings/all")
async def get_all_settings():
    """
    Get all settings in a single request.

    Returns consolidated settings for the settings page including:
    - general config (timezone, etc.)
    - silence_schedule plugin config
    - polling interval settings
    - transitions settings
    - output settings
    - board settings
    - mqtt integration settings
    - display settings
    - service status (running)
    """
    settings_service = get_settings_service()
    config_manager = get_config_manager()

    # Get silence schedule config (stored under features, not plugins)
    silence_feature = config_manager.get_feature("silence_schedule") or {}

    # Get all other settings
    general = config_manager.get_general()
    polling = settings_service.get_polling_settings()
    transitions = settings_service.get_transition_settings()
    output = settings_service.get_output_settings()
    board = settings_service.get_board_settings()
    mqtt = settings_service.get_mqtt_settings()
    display = settings_service.get_display_settings()
    location = settings_service.get_location_settings()
    beta = settings_service.get_beta_settings()
    plugins = settings_service.get_plugin_settings()

    return {
        "general": general,
        "silence_schedule": {"config": silence_feature},
        "polling": polling.to_dict(),
        "transitions": {**transitions.to_dict(), "available_strategies": VALID_STRATEGIES},
        "output": output.to_dict(),
        "board": board.to_dict(),
        "mqtt": mqtt.to_dict(mask_secrets=True),
        "display": display.to_dict(),
        "location": location.to_dict(),
        "beta": beta.to_dict(),
        "plugins": plugins.to_dict(),
        "status": {
            "running": _service_running,
        },
    }




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


def _hdmi_kiosk_supported() -> bool:
    """The in-app HDMI kiosk controls exist only on FiestaPi installs with a
    reachable fiestaupdater sidecar — the sidecar is the sole component that
    can mutate the host OS (via its Docker socket)."""
    return _fiestaboard_profile() == "pi" and _updater_probe()


@app.get("/settings/hdmi-kiosk")
async def get_hdmi_kiosk_status():
    """Status of the FiestaPi HDMI kiosk (Settings → FiestaPanel UI)."""
    if not _hdmi_kiosk_supported():
        return {"supported": False, "status": "unsupported"}
    status: dict = {"status": "unknown"}
    try:
        resp = requests.get(f"{_updater_url()}/hdmi/status", timeout=3)
        if resp.status_code == 200:
            body = resp.json()
            if isinstance(body, dict):
                status = body
    except Exception as e:
        logger.debug("fiestaupdater /hdmi/status fetch failed: %s", e)
    return {"supported": True, **status}


@app.post("/settings/hdmi-kiosk")
async def set_hdmi_kiosk(request: dict):
    """Enable or disable the HDMI kiosk on this FiestaPi.

    Proxies to the sidecar's fixed /hdmi/enable | /hdmi/disable verbs; the
    sidecar performs the host-side install through its Docker socket. Body:
    ``{"enabled": bool}``.
    """
    if "enabled" not in request or not isinstance(request["enabled"], bool):
        raise HTTPException(status_code=400, detail="enabled (boolean) is required")
    if not _hdmi_kiosk_supported():
        raise HTTPException(
            status_code=400,
            detail="HDMI kiosk controls are only available on FiestaPi installs with the updater sidecar",
        )
    verb = "enable" if request["enabled"] else "disable"
    try:
        resp = requests.post(
            f"{_updater_url()}/hdmi/{verb}",
            headers={"Authorization": f"Bearer {_updater_token()}"},
            timeout=10,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not reach the updater sidecar: {e}") from e
    if resp.status_code == 404:
        # Fleet sidecar predates the hdmi verbs. The Pi's boot service pulls
        # the newest sidecar image on every boot, so a reboot upgrades it.
        raise HTTPException(
            status_code=409,
            detail="The updater sidecar on this Pi is too old for HDMI controls — reboot the Pi to update it, then try again",
        )
    if resp.status_code not in (200, 202):
        raise HTTPException(status_code=502, detail=f"Updater sidecar error: {resp.status_code}")
    try:
        return resp.json()
    except Exception:
        return {"status": "queued", "action": f"hdmi_{verb}"}


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
