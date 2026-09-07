"""REST API server for FiestaBoard Display Service."""

import asyncio
import contextlib
import json
import logging
import logging.handlers
import os
import re
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from fastapi import BackgroundTasks, Body, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

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
from .board_client import board_client_from_board_dict  # noqa: E402

# Board lookup / send guards and the DisplayService accessor now live in
# neutral modules so the extracted routers can import them directly instead of
# reaching back into this one at call time (Phase 2 §2.3). They stay bound as
# `src.api_server.<name>` here: this module's own handlers use them, and the
# suite patches them at that path for those handlers.
from .board_guards import (  # noqa: E402
    _board_dims,
    _board_is_paused,
    _find_board,
    _require_board,
    _silence_active,
)
from .board_guards import validate_board_host as _validate_board_host  # noqa: E402
from .board_guards import (  # noqa: E402
    validate_board_host_is_local_network as _validate_board_host_is_local_network,
)
from .board_send_executor import run_board_preview, run_board_send  # noqa: E402
from .collections.models import is_collection_id  # noqa: E402
from .collections.service import (  # noqa: E402
    get_collection_service,
    resolve_active_page_id,
    resolve_next_check_seconds,
)
from .config import Config  # noqa: E402

# ``unmask_sensitive_values`` / ``reset_display_service`` /
# ``reset_template_engine`` used to be imported here purely as patch seams for
# the extracted plugins router (#1757). That router binds them from their
# canonical homes now (Phase 2 slice 4) and was their last consumer, so the
# three re-exports are gone rather than left as patch targets that steer
# nothing.
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
from .network.wifi import WiFiError, get_wifi_service  # noqa: E402
from .pages.service import (  # noqa: E402
    check_ref_board_compatibility,
    find_incompatible_board_references,
    get_page_service,
)
from .panels.models import PanelCreate, PanelUpdate  # noqa: E402
from .panels.service import get_panel_service  # noqa: E402
from .paths import get_data_dir  # noqa: E402, F401  (re-export: patch seam)

# Patch seam (issue #1756): no handler left in this module calls it, but the
# extracted routers resolve it through `src.api_server` at call time so
# tests that patch `src.api_server.get_schedule_service` keep working.
from .schedules.service import get_schedule_service  # noqa: E402, F401
from .settings.service import VALID_OUTPUT_TARGETS, VALID_STRATEGIES, get_settings_service  # noqa: E402
from .settings.service import temporary_override_payload as _temporary_override_payload  # noqa: E402
from .templates.engine import get_template_engine  # noqa: E402
from .templates.expressions import function_signatures  # noqa: E402
from .text_to_board import text_to_board_array  # noqa: E402
from .time_service import reset_time_service  # noqa: E402
from .virtual_board_client import release_virtual_board_state  # noqa: E402

logger = logging.getLogger(__name__)

# Cache state for /muni/stops endpoint
_muni_stops_cache: dict[str, Any] | None = None
_muni_stops_cache_time: float = 0.0
_muni_stops_cache_lock = threading.Lock()


def _validate_request_url(
    url: str,
    *,
    allow_http: bool = True,
    allow_https: bool = True,
) -> None:
    """Validate a user-supplied URL before using it in an HTTP request.

    Blocks credentialed URLs (``user:pass@host``), unsupported schemes and
    non-public destinations (loopback/private/link-local/etc.) to reduce SSRF
    risk. Raises :class:`HTTPException` (status 400) when the URL is rejected.
    """
    import ipaddress
    import socket
    from urllib.parse import urlparse

    if not isinstance(url, str) or not url:
        raise HTTPException(status_code=400, detail="URL is required")
    try:
        parsed = urlparse(url)
    except ValueError:
        raise HTTPException(status_code=400, detail="URL could not be parsed") from None
    allowed = []
    if allow_http:
        allowed.append("http")
    if allow_https:
        allowed.append("https")
    if parsed.scheme not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"URL scheme must be one of: {', '.join(allowed)}",
        )
    if not parsed.hostname:
        raise HTTPException(status_code=400, detail="URL is missing a host")
    if parsed.username is not None or parsed.password is not None:
        raise HTTPException(status_code=400, detail="URL must not contain credentials")
    # Block requests targeting private/loopback/link-local addresses to
    # prevent SSRF against internal services.
    _h = parsed.hostname.lower().rstrip(".")
    if _h in {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}:
        raise HTTPException(
            status_code=400,
            detail="URL must not target internal network resources",
        )
    try:
        _addr = ipaddress.ip_address(_h)
        if _addr.is_private or _addr.is_loopback or _addr.is_link_local or _addr.is_reserved or _addr.is_multicast:
            raise HTTPException(
                status_code=400,
                detail="URL must not target internal network resources",
            )
    except ValueError:
        pass  # Not an IP literal; hostname-based domains are permitted

    host = parsed.hostname.strip().lower()
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise HTTPException(status_code=400, detail="URL host is not allowed")

    def _is_non_public_ip(ip_str: str) -> bool:
        ip_obj = ipaddress.ip_address(ip_str)
        return (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_multicast
            or ip_obj.is_reserved
            or ip_obj.is_unspecified
        )

    try:
        if _is_non_public_ip(host):
            raise HTTPException(status_code=400, detail="URL host resolves to a non-public IP")
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
        except socket.gaierror:
            raise HTTPException(status_code=400, detail="URL host could not be resolved") from None

        for info in infos:
            resolved_ip = info[4][0]
            if _is_non_public_ip(resolved_ip):
                raise HTTPException(status_code=400, detail="URL host resolves to a non-public IP") from None


def _get_generic_data_allowed_hosts() -> list[str]:
    """Return normalized allowlisted hosts for generic-data test fetch.

    Reads comma-separated hostnames from ``GENERIC_DATA_ALLOWED_HOSTS``.
    Empty value means no hosts are allowed.
    """
    raw = os.getenv("GENERIC_DATA_ALLOWED_HOSTS", "")
    hosts = []
    for part in raw.split(","):
        h = part.strip().lower().rstrip(".")
        if h:
            hosts.append(h)
    return hosts


def _is_host_allowed(host: str, allowed_hosts: list[str]) -> bool:
    """Check whether host is exactly allowed or a subdomain of an allowed host."""
    h = (host or "").strip().lower().rstrip(".")
    for allowed in allowed_hosts:
        if h == allowed or h.endswith("." + allowed):
            return True
    return False


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

class MessageRequest(BaseModel):
    """Request model for sending a custom message."""

    text: str


class StatusResponse(BaseModel):
    """Response model for service status."""

    running: bool
    initialized: bool
    config_summary: dict[str, Any]
    # Per-board status keyed by board id (issue #1244). Additive: the
    # top-level fields keep their legacy single-board meaning.
    boards: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str
    service_running: bool
    version: str


# ── WiFi / NetworkManager models ─────────────────────────────────────────────
class WiFiCapabilityResponse(BaseModel):
    available: bool
    reason: str | None = None


class WiFiNetworkModel(BaseModel):
    ssid: str
    signal: int  # 0..100
    security: str
    in_use: bool


class SavedNetworkModel(BaseModel):
    name: str
    autoconnect: bool


class WiFiStatusModel(BaseModel):
    connected: bool
    ssid: str | None = None
    ip_address: str | None = None
    gateway: str | None = None
    signal: int | None = None
    internet_reachable: bool


class WiFiConnectRequest(BaseModel):
    ssid: str
    password: str | None = None
    hidden: bool = False


class WiFiConnectResponse(BaseModel):
    status: WiFiStatusModel
    connectivity_confirmed: bool
    message: str


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


@app.get("/", response_model=dict[str, str])
async def root():
    """Root endpoint with API information."""
    return {"name": "FiestaBoard Display API", "version": "1.0.0", "status": "running"}


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    service = get_service()
    return HealthResponse(status="ok", service_running=_service_running and service is not None, version=__version__)


@app.head("/health", response_model=HealthResponse)
async def health_head():
    """Health check endpoint (HEAD).

    Split from `health()` above into its own handler with a distinct name so
    each HTTP method gets its own APIRoute and its own OpenAPI operationId.
    A single @app.api_route(methods=["GET", "HEAD"]) produces one APIRoute
    whose unique_id is derived from `list(route.methods)[0]` — since
    route.methods is a set, that pick is non-deterministic, and FastAPI emits
    the same operationId for both the GET and HEAD operations (see #1572).
    """
    return await health()


@app.get("/mqtt/status")
async def get_mqtt_status():
    """Return the current MQTT connection status.

    Useful for UI display and for tests to determine whether the live MQTT
    client (not just the one-off discovery script) is connected and able to
    process commands.
    """
    try:
        from .mqtt import get_mqtt_client

        client = get_mqtt_client()
        if client is None:
            return {"enabled": False, "connected": False, "running": False}
        return {
            "enabled": True,
            "connected": client.is_connected(),
            "running": client.is_running(),
        }
    except Exception as e:
        # ``enabled: False`` is a real answer ("MQTT is switched off"), so it
        # must never double as "we could not tell" — the two were identical
        # before #1887 and an operator debugging a broken broker saw the
        # same body as one who had simply not enabled MQTT.
        logger.error(f"Failed to read MQTT status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to read MQTT status.") from e


@app.post("/mqtt/republish-discovery")
async def mqtt_republish_discovery():
    """Re-publish MQTT discovery messages for all entities.

    Useful when the page list changes after the MQTT client first connected,
    or to force HA to refresh entity options (e.g. Active Page select options).
    Returns 503 if MQTT is not connected.
    """
    try:
        from .mqtt import get_mqtt_client

        client = get_mqtt_client()
        if client is None or not client.is_connected():
            raise HTTPException(status_code=503, detail="MQTT client not connected")
        client._publish_discovery()
        return {"status": "ok", "message": "Discovery messages republished"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


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


# ── WiFi management (FiestaPi only) ──────────────────────────────────────────
def _wifi_unavailable(reason: str | None) -> HTTPException:
    return HTTPException(
        status_code=501,
        detail={
            "status": "unavailable",
            "reason": reason or "WiFi management is unavailable on this deployment.",
        },
    )


def _wifi_error(exc: WiFiError) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={"status": "error", "error": str(exc)},
    )


@app.get("/network/wifi/capability", response_model=WiFiCapabilityResponse)
async def wifi_capability():
    """Feature probe — does this deployment support WiFi management?

    The UI calls this once on load and hides the Network tab when the
    answer is False, so generic Docker users never see WiFi controls.
    """
    cap = get_wifi_service().capability()
    return WiFiCapabilityResponse(available=cap.available, reason=cap.reason)


@app.get("/network/wifi/status", response_model=WiFiStatusModel)
async def wifi_status():
    svc = get_wifi_service()
    cap = svc.capability()
    if not cap.available:
        raise _wifi_unavailable(cap.reason)
    try:
        status = await asyncio.to_thread(svc.status)
    except WiFiError as exc:
        raise _wifi_error(exc) from exc
    return WiFiStatusModel(**status.__dict__)


@app.post("/network/wifi/scan", response_model=list[WiFiNetworkModel])
async def wifi_scan():
    """Trigger a rescan and return de-duplicated networks (strongest signal)."""
    svc = get_wifi_service()
    cap = svc.capability()
    if not cap.available:
        raise _wifi_unavailable(cap.reason)
    try:
        networks = await asyncio.to_thread(svc.scan)
    except WiFiError as exc:
        raise _wifi_error(exc) from exc
    return [WiFiNetworkModel(**n.__dict__) for n in networks]


@app.get("/network/wifi/saved", response_model=list[SavedNetworkModel])
async def wifi_saved():
    svc = get_wifi_service()
    cap = svc.capability()
    if not cap.available:
        raise _wifi_unavailable(cap.reason)
    try:
        saved = await asyncio.to_thread(svc.saved_networks)
    except WiFiError as exc:
        raise _wifi_error(exc) from exc
    return [SavedNetworkModel(**s.__dict__) for s in saved]


@app.post("/network/wifi/connect", response_model=WiFiConnectResponse)
async def wifi_connect(payload: WiFiConnectRequest):
    """Create/replace a persistent profile and activate it.

    Returns the new status plus a `connectivity_confirmed` flag so the
    UI can warn the user when the AP associates but the internet probe
    fails (typical for wrong password / captive portal).
    """
    svc = get_wifi_service()
    cap = svc.capability()
    if not cap.available:
        raise _wifi_unavailable(cap.reason)
    try:
        result = await svc.connect(ssid=payload.ssid, password=payload.password, hidden=payload.hidden)
    except WiFiError as exc:
        raise _wifi_error(exc) from exc
    return WiFiConnectResponse(
        status=WiFiStatusModel(**result.status.__dict__),
        connectivity_confirmed=result.connectivity_confirmed,
        message=result.message,
    )


@app.post("/network/wifi/disconnect", response_model=WiFiStatusModel)
async def wifi_disconnect():
    svc = get_wifi_service()
    cap = svc.capability()
    if not cap.available:
        raise _wifi_unavailable(cap.reason)
    try:
        status = await svc.disconnect()
    except WiFiError as exc:
        raise _wifi_error(exc) from exc
    return WiFiStatusModel(**status.__dict__)


@app.delete("/network/wifi/saved/{con_name}", response_model=dict[str, str])
async def wifi_forget(con_name: str):
    svc = get_wifi_service()
    cap = svc.capability()
    if not cap.available:
        raise _wifi_unavailable(cap.reason)
    try:
        await svc.forget(con_name)
    except WiFiError as exc:
        raise _wifi_error(exc) from exc
    return {"status": "ok"}


@app.get("/status", response_model=StatusResponse)
async def get_status():
    """Get current service status."""
    service = get_service()
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    settings_service = get_settings_service()

    status = StatusResponse(
        running=_service_running, initialized=service is not None, config_summary=Config.get_summary()
    )
    # Add active page ID to config summary
    status.config_summary["active_page_id"] = settings_service.get_active_page_id()

    # Per-board status (issue #1244): configured/paused/active page for every
    # configured board, keyed by board id. Defensive throughout — a partial
    # boards list must never break the legacy top-level status fields.
    try:
        boards = settings_service.get_board_settings().boards or []
        # Why each board failed to get a client, when it failed (issue #1749).
        # A board skipped at startup is visible here instead of only in the log.
        init_errors = getattr(service, "board_init_errors", None)
        if not isinstance(init_errors, dict):
            init_errors = {}
        for board in boards:
            if not isinstance(board, dict) or not board.get("id"):
                continue
            bid = board["id"]
            try:
                configured = service.get_board_client(bid) is not None
            except Exception:
                configured = False
            active_page_id = settings_service.get_active_page_id(board_id=bid)
            if not isinstance(active_page_id, str):
                active_page_id = None
            init_error = init_errors.get(bid)
            if not isinstance(init_error, str):
                init_error = None
            status.boards[bid] = {
                "configured": configured,
                "paused": _board_is_paused(bid),
                "active_page_id": active_page_id,
                "error": init_error,
            }
    except Exception as e:
        logger.debug(f"Per-board status unavailable: {e}")
    return status


@app.post("/start")
async def start_service(background_tasks: BackgroundTasks):
    """Start the background service."""
    global _service_thread, _shutting_down

    if _service_running:
        return {"status": "already_running", "message": "Service is already running"}

    _shutting_down = False  # Re-enable auto-restart

    service = get_service()
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # Retry initialization if it failed before
    # This allows the service to start after configuration is fixed
    if not service.vb_client:
        logger.info("Retrying service initialization...")
        if not service.initialize():
            raise HTTPException(
                status_code=503,
                detail="Service initialization failed - check board configuration (API key, host, etc.)",
            )
        logger.info("Service initialization successful on retry")

    # Start service in background thread
    _service_thread = threading.Thread(target=run_service_background, daemon=True)
    _service_thread.start()

    # Give it a moment to start
    await asyncio.sleep(0.5)

    if _service_running:
        return {"status": "started", "message": "Service started successfully"}
    else:
        raise HTTPException(status_code=500, detail="Service failed to start - check logs for details")


@app.post("/stop")
async def stop_service():
    """Stop the background service."""
    global _service_running, _shutting_down

    if not _service_running:
        return {"status": "not_running", "message": "Service is not running"}

    _shutting_down = True  # Prevent auto-restart
    running_service = peek_service()
    if running_service:
        running_service.running = False
        _service_running = False

    return {"status": "stopped", "message": "Service stopped successfully"}


@app.post("/refresh")
async def refresh_display(board_id: str | None = None, payload: dict | None = Body(None)):
    """Manually trigger a display refresh.

    Args:
        board_id: Optional board to refresh (query param, or
            ``{"board_id": ...}`` in the JSON body). Omitted → legacy
            behavior: refresh every board, primary first (issue #1244).
    """
    if board_id is None and payload:
        board_id = payload.get("board_id")

    service = get_service()
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        if board_id is None:
            # Every board is driven here, so a failing secondary must surface
            # too — the wrapper aggregates across the whole pass (issue #1791).
            # The pass is board network I/O, so it runs in a worker thread to
            # keep the event loop free (#1826); _send_with_status moves as one
            # call because its failure reason lives in a thread-local that is
            # set and read inside the same sync call.
            sent, error = await run_board_send(
                _send_with_status, service, "check_and_send_active_page_with_status", "check_and_send_active_page"
            )
            if error:
                raise HTTPException(status_code=500, detail=f"Failed to refresh display: {error}")
            return {
                "status": "success",
                "message": "Display refreshed successfully",
                "board_id": None,
                "sent": sent,
            }

        board = _require_board(board_id)
        rt = service.get_runtime(board_id)
        if rt is None:
            raise HTTPException(status_code=503, detail=f"Board client not initialized: {board_id}")
        is_primary = board_id == get_settings_service().get_primary_board_id()
        # Board network I/O — off the event loop (#1826); _send_with_status
        # moves as one call (thread-local failure reason, see above).
        sent, error = await run_board_send(
            _send_with_status,
            service,
            "check_and_send_for_board_with_status",
            "check_and_send_for_board",
            board_id,
            rt,
            is_primary=is_primary,
            board=board,
        )
        if error:
            raise HTTPException(status_code=500, detail=f"Failed to refresh board {board_id}: {error}")
        return {
            "status": "success",
            "message": f"Board {board_id} refreshed successfully",
            "board_id": board_id,
            "sent": sent,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing display: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to refresh display: {str(e)}") from e


def _characters_to_message(characters: list) -> str:
    """Convert a character grid (list[list[int]]) to the message string format.

    Character codes map as follows (matching the Vestaboard spec):
      0       → space
      1–26    → A–Z
      27–35   → 1–9
      36      → 0
      37–62   → punctuation / special characters
      63–71   → color tiles, rendered as {63}…{71}

    Undefined codes (43, 45, 51, 57, 58, 61) are rendered as a space.
    """
    # Index-aligned lookup table for codes 0–62
    _LOOKUP = [
        " ",  # 0
        "A",
        "B",
        "C",
        "D",
        "E",
        "F",
        "G",
        "H",
        "I",
        "J",  # 1–10
        "K",
        "L",
        "M",
        "N",
        "O",
        "P",
        "Q",
        "R",
        "S",
        "T",  # 11–20
        "U",
        "V",
        "W",
        "X",
        "Y",
        "Z",  # 21–26
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "8",
        "9",
        "0",  # 27–36
        "!",
        "@",
        "#",
        "$",
        "(",
        ")",  # 37–42
        " ",  # 43 – undefined
        "-",  # 44
        " ",  # 45 – undefined
        "+",
        "&",
        "=",
        ";",
        ":",  # 46–50
        " ",  # 51 – undefined
        "'",
        '"',
        "%",
        ",",
        ".",  # 52–56
        " ",
        " ",  # 57–58 – undefined
        "/",
        "?",  # 59–60
        " ",  # 61 – undefined
        "°",  # 62
    ]

    lines = []
    for row in characters:
        chars = []
        for code in row:
            if 63 <= code <= 71:
                chars.append(f"{{{code}}}")
            elif 0 <= code < len(_LOOKUP):
                chars.append(_LOOKUP[code])
            else:
                chars.append(" ")
        lines.append("".join(chars))
    return "\n".join(lines)


@app.get("/board/current-message")
async def get_board_current_message(force: bool = False, board_id: str | None = None):
    """Return the current state of the physical board.

    Normally serves from the cached result of the background poll thread
    (updated every 30 s local / 3 min cloud) so callers don't hammer the
    Vestaboard API.  Pass ?force=true to trigger a live read instead.

    Args:
        force: Trigger a live board read instead of serving the poll cache.
            Only honored for the primary board.
        board_id: Optional board to read (issue #1247). Omitted or the
            primary board → legacy live-polled behavior. A secondary board is
            served from its runtime cache (last-sent/polled content) because
            board-state polling is primary-only by design; ``characters`` /
            ``message`` are null when nothing has been sent to it yet.

    Returns:
        characters:          Actual 2-D grid currently on the board
        message:             Formatted string suitable for BoardDisplay
        rows / cols:         Grid dimensions
        expected_characters: What FiestaBoard last sent (None until first send)
        cached_at:           ISO timestamp of last poll, or null on live read
        api_mode:            "local" or "cloud"
        board_id:            Echo of the requested board id (null = primary)
    """
    service = get_service()
    if not service or not service.vb_client:
        raise HTTPException(status_code=503, detail="Board client not initialized")

    if board_id is not None:
        board = _require_board(board_id)
        if board_id != get_settings_service().get_primary_board_id():
            # Secondary board: serve from its runtime cache. No live read —
            # the poll thread only tracks the primary board (issue #1243).
            rt = service.get_runtime(board_id)
            rt_client = rt.client if rt is not None else None
            last_sent = getattr(rt_client, "_last_characters", None) if rt_client is not None else None
            polled = rt.polled_characters if rt is not None else None
            characters = polled if polled is not None else last_sent
            cached_at = None
            if polled is not None and rt is not None and rt.polled_at is not None:
                cached_at = datetime.fromtimestamp(rt.polled_at, tz=UTC).isoformat()
            board_api_mode = "cloud" if getattr(rt_client, "use_cloud", False) else "local"
            if characters is None:
                # Nothing sent to this board yet — return its geometry so the
                # UI can degrade gracefully (render the active page instead).
                dims = _board_dims(board)
                return {
                    "characters": None,
                    "message": None,
                    "rows": dims.rows,
                    "cols": dims.cols,
                    "expected_characters": None,
                    "cached_at": None,
                    "api_mode": board_api_mode,
                    "board_id": board_id,
                }
            return {
                "characters": characters,
                "message": _characters_to_message(characters),
                "rows": len(characters),
                "cols": len(characters[0]) if characters else 0,
                "expected_characters": last_sent,
                "cached_at": cached_at,
                "api_mode": board_api_mode,
                "board_id": board_id,
            }

    api_mode = "cloud" if getattr(service.vb_client, "use_cloud", False) else "local"
    expected_characters = service.vb_client._last_characters

    if force or service._polled_characters is None:
        # No cached data yet (startup) or caller wants a live read — hit the board directly
        characters = await asyncio.to_thread(service.vb_client.read_current_message)
        if characters is None:
            raise HTTPException(status_code=503, detail="Failed to read current board message")
        # Prime the cache so subsequent requests are fast
        service._polled_characters = characters
        service._polled_at = time.time()
        cached_at = None
    else:
        characters = service._polled_characters
        cached_at = datetime.fromtimestamp(service._polled_at, tz=UTC).isoformat()

    message = _characters_to_message(characters)
    rows = len(characters)
    cols = len(characters[0]) if characters else 0

    return {
        "characters": characters,
        "message": message,
        "rows": rows,
        "cols": cols,
        "expected_characters": expected_characters,
        "cached_at": cached_at,
        "api_mode": api_mode,
        "board_id": board_id,
    }


def _throttled_send_response(board_client) -> JSONResponse | None:
    """A 429 for an out-of-band write dropped by the client-side send floor.

    #1868 review: cloud boards (and note arrays) enforce a minimum interval
    between sends (#1754); a send inside the window returns ``(True, False)``
    with ``last_send_throttled`` set — the content was DROPPED, not
    delivered, and unlike the engine tick (which retries next pass) the
    manual out-of-band endpoints (/send-message, /send-welcome-message)
    never retry. Answering "success/unchanged" would silently swallow the
    user's write, so they answer 429 with a Retry-After hint computed from
    the floor.

    The /debug/* senders used to share this helper; since their conventions
    pass they raise ``HTTPException(429, detail=...)`` from
    ``src/debug/routes.py`` instead, so the whole domain serves the one
    ``{"detail": ...}`` error contract. Same status, same Retry-After, same
    arithmetic — this stays until the remaining senders convert.

    Returns None when the last send was not throttled (the ``is True`` guard
    also keeps Mock clients in tests, whose attributes are truthy, on the
    legacy path unless they opt in).
    """
    if getattr(board_client, "last_send_throttled", False) is not True:
        return None
    try:
        floor_ms = int(getattr(board_client, "min_send_interval_ms", 0))
    except (TypeError, ValueError):
        floor_ms = 0
    retry_after = max(1, -(-floor_ms // 1000)) if floor_ms else 15
    return JSONResponse(
        status_code=429,
        content={
            "status": "throttled",
            "message": (
                f"Send skipped: the board accepts at most one message every {retry_after}s. Retry shortly."
            ),
            "retry_after_seconds": retry_after,
        },
        headers={"Retry-After": str(retry_after)},
    )


@app.post("/send-message")
async def send_message(request: MessageRequest):
    """Send a custom message to the board."""
    service = get_service()
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # CRITICAL: Block ALL manual sends during silence mode to prevent wake-ups.
    # This path drives the primary board's client, so it must resolve the
    # primary board's window (issue #1788).
    if _silence_active():
        logger.info("Silence mode is active - blocking manual message send to prevent wake-up")
        return {
            "status": "blocked",
            "message": "Manual sends blocked during silence mode to prevent wake-ups",
            "silence_mode": True,
        }

    # Block all sends when the target board is paused (issue #970).
    if _board_is_paused():
        logger.info("Board is paused - blocking manual message send")
        return _paused_response()

    if not service.vb_client:
        raise HTTPException(status_code=503, detail="Board client not initialized")

    try:
        settings_service = get_settings_service()
        transition = settings_service.get_transition_settings()
        # Size the grid to the active (first) board so a manual send to a note
        # array uses its real geometry instead of a default flagship 22×6.
        board_settings = settings_service.get_board_settings()
        device_type = "flagship"
        notes_wide = 1
        notes_tall = 1
        if board_settings.boards:
            primary_board = board_settings.boards[0]
            device_type = primary_board.get("device_type", "flagship")
            notes_wide = primary_board.get("notes_wide", 1)
            notes_tall = primary_board.get("notes_tall", 1)
        dims = resolve_dimensions(device_type, notes_wide, notes_tall)
        # Word-wrap/convert/render is the shared message core (#1765): the
        # MCP send_message executor calls the same function, so the two
        # surfaces cannot render a message differently. See
        # src/displays/messages.py for the #1793 newline/backslash notes.
        from .displays.messages import render_message

        success, was_sent = render_message(
            service.vb_client,
            request.text,
            rows=dims.rows,
            cols=dims.cols,
            strategy=transition.strategy,
            step_interval_ms=transition.step_interval_ms,
            step_size=transition.step_size,
        )
        if success:
            if was_sent:
                # Flag the out-of-band write and push fresh MQTT state so HA
                # reflects the update (issues #1794/#1831). The display
                # loop's dedupe cache is deliberately left alone:
                # invalidating it here made the message self-destruct on the
                # next engine tick (<=15s). Restoring the active page is a
                # pull — /force-refresh, MQTT Refresh Display, re-selecting
                # a page, or an actual content change (issue #1794).
                _note_out_of_band_write()
                service.request_board_refresh()
                return {"status": "success", "message": "Message sent successfully"}
            else:
                # A not-sent "success" can also mean the send floor dropped
                # the write entirely (#1868 review) — that is not "unchanged".
                throttled = _throttled_send_response(service.vb_client)
                if throttled is not None:
                    return throttled
                return {"status": "success", "message": "Message unchanged, no update needed", "skipped": True}
        else:
            raise HTTPException(status_code=500, detail="Failed to send message")
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send message: {str(e)}") from e


# Default welcome messages, sized to fit each device's center row.
# Flagship has 22 columns; Note has 15 columns.
_DEFAULT_WELCOME_FLAGSHIP = "HIYA FROM FIESTABOARD"
_DEFAULT_WELCOME_NOTE = "HIYA FIESTA!"

# Colorful welcome template for Flagship (6 rows x 22 cols).
# Matches the welcome page in pages.json.
_WELCOME_TEMPLATE_FLAGSHIP = [
    "{{red}}{{red}}{{orange}}{{yellow}}{{orange}}{{red}}{{violet}}{{red}}{{orange}}{{yellow}}{{red}}{{orange}}{{violet}}{{yellow}}{{red}}{{orange}}{{red}}{{yellow}}{{violet}}{{orange}}{{red}}{{yellow}}",
    "{{orange}}{{yellow}}{{red}}{{violet}}{{yellow}}{{orange}}{{red}}{{yellow}}{{violet}}{{orange}}{{yellow}}{{red}}{{orange}}{{violet}}{{yellow}}{{orange}}{{red}}{{violet}}{{yellow}}{{red}}{{orange}}{{red}}",
    "{center}",
    "{{violet}}{{orange}}{{yellow}}{{red}}{{orange}}{{violet}}{{yellow}}{{orange}}{{red}}{{yellow}}{{red}}{{violet}}{{orange}}{{yellow}}{{violet}}{{red}}{{orange}}{{yellow}}{{orange}}{{red}}{{violet}}{{orange}}",
    "{{red}}{{yellow}}{{orange}}{{violet}}{{red}}{{orange}}{{red}}{{violet}}{{yellow}}{{orange}}{{violet}}{{red}}{{yellow}}{{red}}{{orange}}{{violet}}{{yellow}}{{red}}{{violet}}{{orange}}{{yellow}}{{red}}",
    "{{orange}}{{violet}}{{red}}{{yellow}}{{violet}}{{red}}{{orange}}{{yellow}}{{red}}{{red}}{{orange}}{{yellow}}{{violet}}{{orange}}{{red}}{{yellow}}{{orange}}{{red}}{{yellow}}{{violet}}{{red}}{{orange}}",
]

# Colorful welcome template for Note (3 rows x 15 cols).
# Two colorful border rows surround a centered text row.
_WELCOME_TEMPLATE_NOTE = [
    "{{red}}{{orange}}{{yellow}}{{red}}{{violet}}{{orange}}{{yellow}}{{red}}{{violet}}{{orange}}{{yellow}}{{red}}{{violet}}{{orange}}{{yellow}}",
    "{center}",
    "{{yellow}}{{orange}}{{violet}}{{red}}{{yellow}}{{orange}}{{violet}}{{red}}{{yellow}}{{orange}}{{violet}}{{red}}{{yellow}}{{orange}}{{violet}}",
]


def _build_welcome_template(
    device_type: str,
    custom_msg: str,
    notes_wide: int = 1,
    notes_tall: int = 1,
) -> list:
    """Build the welcome message template for a given device type.

    Returns a list of template strings (one per row) sized appropriately
    for the device. The center row contains the welcome text, truncated to
    fit the device's column count.

    Args:
        device_type: "flagship", "note", or "note_array"
        custom_msg: Optional user-configured welcome message; when empty,
            a device-appropriate default is used.
        notes_wide: For note_array: number of notes side-by-side (default 1).
        notes_tall: For note_array: number of notes stacked (default 1).
    """
    try:
        dims = resolve_dimensions(device_type, notes_wide=notes_wide, notes_tall=notes_tall)
    except ValueError:
        dims = resolve_dimensions("flagship")

    cols = dims.cols

    if device_type == "note":
        default_msg = _DEFAULT_WELCOME_NOTE
        rows = list(_WELCOME_TEMPLATE_NOTE)
    elif device_type == "note_array":
        default_msg = _DEFAULT_WELCOME_NOTE
        # Generate a plain template: blank rows with center row carrying text
        center_idx = dims.rows // 2
        rows = [""] * dims.rows
        rows[center_idx] = "{center}"
    else:
        default_msg = _DEFAULT_WELCOME_FLAGSHIP
        rows = list(_WELCOME_TEMPLATE_FLAGSHIP)

    center_text = (custom_msg.upper() if custom_msg else default_msg)[:cols]
    if custom_msg and len(custom_msg) > cols:
        logger.debug(
            "Welcome message truncated from %d to %d characters for %s device",
            len(custom_msg),
            cols,
            device_type,
        )
    return [row.replace("{center}", center_text) for row in rows]


@app.post("/send-welcome-message")
async def send_welcome_message():
    """
    Send a colorful welcome message to the board.

    Used by the setup wizard to confirm the board is working.
    Sends "HIYA FROM FIESTABOARD" with colorful borders.

    Note: This creates a fresh board client from the settings boards store
    so any recent credential changes (setup wizard or Settings) are used.
    """
    # Check silence mode for the board this actually writes to (the primary
    # board — the wizard has no board picker).
    if _silence_active():
        logger.info("Silence mode is active - blocking welcome message to prevent wake-up")
        return {"status": "blocked", "message": "Welcome message blocked during silence mode", "silence_mode": True}

    # Block welcome message when the (first) board is paused (issue #970).
    if _board_is_paused():
        logger.info("Board is paused - blocking welcome message")
        return _paused_response()

    # Create a fresh board client from the primary settings board so recent
    # credential edits are always used. Board credentials are unified on
    # settings.json (issue #1760): the legacy config.json copy is never read.
    board = _primary_board_entry()
    try:
        board_client = board_client_from_board_dict(board) if board is not None else None
    except ValueError as e:
        logger.error(f"Failed to create board client: {e}")
        raise HTTPException(status_code=503, detail=f"Board not configured: {str(e)}") from e
    if board_client is None:
        raise HTTPException(status_code=503, detail="Board not configured: no board with a usable connection")
    board_client.skip_unchanged = False  # Always send the welcome message

    try:
        # Use custom welcome message if set, otherwise use the default
        config_manager = get_config_manager()
        general = config_manager.get_general()
        custom_msg = general.get("welcome_message", "").strip()

        settings_service = get_settings_service()
        transition = settings_service.get_transition_settings()

        # Determine device type and array dimensions from configured boards
        # (defaults to flagship 6×22). Note arrays use notes_wide/notes_tall
        # to compute the actual grid size.
        device_type = "flagship"
        nw, nt = 1, 1
        try:
            board_settings = settings_service.get_board_settings()
            boards = getattr(board_settings, "boards", None) or []
            if boards:
                first = boards[0]
                if isinstance(first, dict):
                    dt = first.get("device_type", "flagship")
                    nw = first.get("notes_wide", 1)
                    nt = first.get("notes_tall", 1)
                else:
                    dt = getattr(first, "device_type", "flagship")
                    nw = getattr(first, "notes_wide", 1)
                    nt = getattr(first, "notes_tall", 1)
                if dt in ("flagship", "note", "note_array"):
                    device_type = dt
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Could not determine device type for welcome message: %s", exc)

        welcome_template = _build_welcome_template(device_type, custom_msg, notes_wide=nw, notes_tall=nt)

        # Convert template to board array sized for the target device
        welcome_text = "\n".join(welcome_template)
        dims = resolve_dimensions(device_type, notes_wide=nw, notes_tall=nt)
        board_array = text_to_board_array(welcome_text, rows=dims.rows, cols=dims.cols)

        success, was_sent = board_client.render(
            board_array,
            strategy=transition.strategy,
            step_interval_ms=transition.step_interval_ms,
            step_size=transition.step_size,
            force=True,  # Force send even if cached
            device_type=device_type,
        )

        if success:
            if was_sent:
                logger.info("Welcome message sent to board")
                return {"status": "success", "message": "Welcome message sent to your board!"}
            else:
                # Dropped by the send floor, not unchanged (#1868 review).
                throttled = _throttled_send_response(board_client)
                if throttled is not None:
                    return throttled
                return {"status": "success", "message": "Welcome message unchanged", "skipped": True}
        else:
            raise HTTPException(status_code=500, detail="Failed to send welcome message")

    except Exception as e:
        logger.error(f"Error sending welcome message: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send welcome message: {str(e)}") from e


# =============================================================================
# Configuration Endpoints — moved to src/config_api/routes.py (Phase 2, Task 8)
# =============================================================================

from .config_api.routes import router as config_router  # noqa: E402

app.include_router(config_router)


@app.get("/silence-status")
async def get_silence_status(board_id: str | None = None):
    """
    Get current silence mode status with UTC times.

    Args:
        board_id: Optional board to read (query param). Omitted → the
            **primary** board (issue #1788), matching ``_silence_active`` and
            ``_board_is_paused``. This is a runtime status endpoint, not a
            config dump: "is silence on?" with no board means "on the board
            you drive by default". Returning the install-wide layer instead
            made the dashboard overlay, the silence-imminent banner and
            ``GET /silence-status`` all report the pre-save window on a
            single-board install, because the settings form writes the board
            layer. The install-wide layer is still readable as raw config via
            ``GET /settings/all``.

    Returns:
    - enabled: Whether silence schedule is enabled
    - active: Whether silence mode is currently active
    - start_time_utc: Start time in UTC ISO format
    - end_time_utc: End time in UTC ISO format
    - current_time_utc: Current UTC time
    - next_change_utc: Time of next status change
    - board_id: The board this status describes (the primary board when the
      query param was omitted; null only when no board is configured)
    """
    from .config import resolve_silence_schedule
    from .time_service import get_time_service

    time_service = get_time_service()
    config_manager = get_config_manager()

    if board_id is None:
        try:
            primary = get_settings_service().get_primary_board_id()
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("Could not resolve primary board for silence status: %s", e)
            primary = None
        # Coerce: an id that is not a string would land in the JSON response.
        board_id = str(primary) if isinstance(primary, str) and primary else None

    # No migration here: this is a read the UI polls on a timer, and the
    # migration is a config write.  It runs once at startup instead
    # (``_run_startup_migrations``) — see #1746.
    silence_config = resolve_silence_schedule(config_manager.get_feature("silence_schedule"), board_id)
    enabled = silence_config["enabled"]
    start_time = silence_config["start_time"]
    end_time = silence_config["end_time"]
    mode = silence_config["mode"]
    page_id = silence_config["page_id"]

    # Check if currently active
    active = False
    if enabled:
        active = time_service.is_time_in_window(start_time, end_time)

    # Get current UTC time
    current_utc = time_service.get_current_utc()
    current_time_utc = current_utc.strftime("%H:%M+00:00")

    # Determine next change time (simplified - just return start or end)
    next_change_utc = end_time if active else start_time

    # Wall-clock seconds until the next active/inactive transition. Lets the
    # frontend show a "silence starts in N min" warning without re-doing the
    # UTC + offset math the silence window uses (which has subtle edge cases
    # around midnight rollover and DST). None when silence is disabled.
    seconds_until_next_change: int | None = None
    if enabled:
        next_change_dt = time_service.parse_iso_time(next_change_utc)
        if next_change_dt is not None:
            delta_seconds = int((next_change_dt - current_utc).total_seconds())
            # next_change_dt is anchored to "today" in UTC, so a negative value
            # means the boundary already passed today and will recur tomorrow.
            if delta_seconds < 0:
                delta_seconds += 86_400
            seconds_until_next_change = delta_seconds

    return {
        "enabled": enabled,
        "active": active,
        "start_time_utc": start_time,
        "end_time_utc": end_time,
        "current_time_utc": current_time_utc,
        "next_change_utc": next_change_utc,
        "seconds_until_next_change": seconds_until_next_change,
        "mode": mode,
        "page_id": page_id,
        "indicator_text": silence_config["indicator_text"],
        "indicator_position": silence_config["indicator_position"],
        "board_id": board_id,
    }


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


@app.get("/baywheels/stations")
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


@app.get("/baywheels/stations/nearby")
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


@app.get("/baywheels/stations/search")
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


@app.get("/muni/stops")
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


@app.get("/muni/stops/nearby")
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


@app.get("/muni/stops/search")
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


@app.get("/transit/cache/status")
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


@app.get("/stocks/search")
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


@app.post("/stocks/validate")
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


@app.post("/traffic/routes/geocode")
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


@app.post("/traffic/routes/validate")
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


def _ensure_transition_plugins_beta() -> None:
    """Gate transition-plugin endpoints behind the beta flag.

    The SDK is experimental and its contract may change.  Until the
    operator opts in via Settings → Beta the endpoints respond 404 so
    the feature is fully hidden -- no plugin picker, no preview page,
    no surface area for users to start depending on something we may
    reshape.
    """
    settings_service = get_settings_service()
    beta = settings_service.get_beta_settings()
    if not beta.transition_plugins_enabled:
        raise HTTPException(
            status_code=404,
            detail=(
                "Transition plugins are an experimental beta. Enable them in Settings → Beta to use this endpoint."
            ),
        )


@app.get("/transitions/plugins")
async def list_transition_plugins():
    """List installed transition plugins available for selection.

    Each entry includes the plugin id, display name, manifest metadata,
    its ``settings_schema`` (so the UI can render a config form), and the
    plugin's ``transition_settings`` caps.  Every installed transition
    plugin is listed -- unlike data plugins, transitions don't need to be
    enabled in the Marketplace to be selectable; installing one is opting
    in.

    Gated behind ``beta.transition_plugins_enabled``.
    """
    _ensure_transition_plugins_beta()

    from .plugins.base import TransitionPluginBase
    from .plugins.registry import get_plugin_registry

    registry = get_plugin_registry()
    out = []
    # registry.plugins copies under the registry lock, so a concurrent
    # install/uninstall can't mutate the dict mid-iteration (#1828).
    for plugin_id, plugin in registry.plugins.items():
        if not isinstance(plugin, TransitionPluginBase):
            continue
        manifest = registry.get_manifest(plugin_id)
        if manifest is None:
            continue
        out.append(
            {
                "id": plugin_id,
                "name": manifest.name,
                "description": manifest.description,
                "icon": manifest.icon,
                "version": manifest.version,
                "author": manifest.author,
                "settings_schema": manifest.settings_schema,
                "transition_settings": plugin.transition_settings,
                "config": dict(plugin.config or {}),
                "strategy": f"plugin:{plugin_id}",
            }
        )
    out.sort(key=lambda e: e["name"].lower())
    return {"plugins": out}


@app.post("/transitions/preview")
async def preview_transition(request: dict):
    """Drive a transition plugin once and return its frame sequence.

    Gated behind ``beta.transition_plugins_enabled`` -- see
    ``_ensure_transition_plugins_beta``.
    """
    _ensure_transition_plugins_beta()
    return await _preview_transition_impl(request)


async def _preview_transition_impl(request: dict):
    """Run a transition plugin once and return the resulting frame sequence.

    Designed for the standalone /transitions test harness in the web UI.
    Frames are generated in-process and returned as JSON; nothing is sent
    to a real board.

    Request body:
      - plugin_id (str, required): the transition plugin to drive
      - from_text (str, optional): text to render into the from-grid
        (uses text_to_board_array).  Defaults to a blank grid.
      - to_text (str, required): text to render into the to-grid
      - config (dict, optional): per-run overrides for the plugin's
        settings_schema fields.  Merged on top of the plugin's
        currently-bound config.
      - device_type (str, optional): "flagship" (default), "note", or
        "note_array" (sized by notes_wide/notes_tall)
      - notes_wide, notes_tall (int, optional): note-array geometry
        (1-8 each; only used when device_type is "note_array")

    Response:
      ``{"frames": [{"grid": [[..]], "delay_ms": int}, ...],
         "total_delay_ms": int, "capped": bool, "plugin_id": str}``

    The runner's caps (max_frames, max_runtime_seconds, min_interval_ms)
    are honored.  If the plugin exceeds either max_frames or
    max_runtime_seconds the response is truncated and ``capped`` is set
    to true so the UI can display a hint.

    Iteration happens on a worker thread (``asyncio.to_thread``) so a
    slow / runaway plugin generator cannot block FastAPI's event loop.
    """
    import asyncio

    from .devices import MAX_NOTES_PER_AXIS, board_context_for
    from .plugins.registry import get_plugin_registry
    from .text_to_board import text_to_board_array

    plugin_id = request.get("plugin_id")
    if not plugin_id or not isinstance(plugin_id, str):
        raise HTTPException(status_code=400, detail="plugin_id is required")

    registry = get_plugin_registry()
    plugin = registry.get_transition_plugin(plugin_id)
    if plugin is None:
        raise HTTPException(
            status_code=404,
            detail=f"Transition plugin {plugin_id!r} not loaded or not enabled",
        )

    device_type = request.get("device_type", "flagship")
    if device_type not in ("flagship", "note", "note_array"):
        raise HTTPException(status_code=400, detail=f"Unknown device_type: {device_type}")
    try:
        notes_wide = int(request.get("notes_wide", 1))
        notes_tall = int(request.get("notes_tall", 1))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="notes_wide/notes_tall must be integers") from exc
    if not (1 <= notes_wide <= MAX_NOTES_PER_AXIS and 1 <= notes_tall <= MAX_NOTES_PER_AXIS):
        raise HTTPException(
            status_code=400,
            detail=f"notes_wide/notes_tall must be between 1 and {MAX_NOTES_PER_AXIS}",
        )
    device = board_context_for(device_type, notes_wide=notes_wide, notes_tall=notes_tall)

    from_text = request.get("from_text", "")
    to_text = request.get("to_text", "")
    from_grid = text_to_board_array(from_text, rows=device.rows, cols=device.cols)
    to_grid = text_to_board_array(to_text, rows=device.rows, cols=device.cols)

    # Merge override config on top of the plugin's currently-bound config.
    config = dict(plugin.config or {})
    overrides = request.get("config") or {}
    if isinstance(overrides, dict):
        config.update(overrides)

    caps = plugin.transition_settings
    max_frames = int(caps["max_frames"])
    min_interval_ms = int(caps["min_interval_ms"])
    max_runtime_s = int(caps["max_runtime_seconds"])

    def _collect_frames() -> tuple[list, int, bool, str | None]:
        """Run on a worker thread; returns (frames, total_delay, capped, error)."""
        import time

        frames: list = []
        total_delay = 0
        capped_flag = False
        started = time.monotonic()
        try:
            for raw_frame in plugin.generate_frames(from_grid, to_grid, device, config):
                if len(frames) >= max_frames:
                    capped_flag = True
                    break
                if (time.monotonic() - started) >= max_runtime_s:
                    capped_flag = True
                    break
                if isinstance(raw_frame, tuple) and len(raw_frame) == 2:
                    grid, delay = raw_frame
                else:
                    grid, delay = raw_frame, 0
                try:
                    delay = int(delay or 0)
                except (TypeError, ValueError):
                    delay = 0
                delay = max(delay, min_interval_ms)
                if not isinstance(grid, list) or not grid or not isinstance(grid[0], list):
                    continue
                frames.append({"grid": grid, "delay_ms": delay})
                total_delay += delay
        except Exception as exc:
            return frames, total_delay, capped_flag, str(exc)
        return frames, total_delay, capped_flag, None

    try:
        # Bound the thread itself: if iteration takes longer than the cap +
        # a small grace period, give up rather than letting a runaway
        # plugin tie up a worker thread indefinitely.
        frames, total_delay, capped, error = await asyncio.wait_for(
            asyncio.to_thread(_collect_frames),
            timeout=max_runtime_s + 5,
        )
    except TimeoutError as exc:
        logger.warning(
            "Transition preview for %s exceeded %ds; aborting",
            plugin_id,
            max_runtime_s,
        )
        raise HTTPException(
            status_code=504,
            detail=(f"Plugin {plugin_id!r} exceeded the {max_runtime_s}s runtime cap and was aborted."),
        ) from exc

    if error is not None:
        logger.warning("Transition preview failed for %s: %s", plugin_id, error)
        raise HTTPException(status_code=500, detail=f"Plugin error: {error}")

    return {
        "plugin_id": plugin_id,
        "device_type": device_type,
        "frames": frames,
        "frame_count": len(frames),
        "total_delay_ms": total_delay,
        "capped": capped,
        "from_grid": from_grid,
        "to_grid": to_grid,
    }


# Hold the from-page on the board briefly before starting a live-test
# transition so the starting state is actually visible (physical tile
# flips take a moment to settle).
LIVE_TEST_FROM_HOLD_SECONDS = 1.5


def _resolve_live_board_client(board_id: str | None) -> tuple[dict | None, Any]:
    """Resolve ``(board_entry, client)`` for a Transition Lab live send.

    Mirrors the routing used by ``/pages/{id}/send``: an explicit
    *board_id* targets that board's client; omitted keeps the legacy
    primary-client path.  Raises :class:`HTTPException` when the service
    or client isn't available.
    """
    service = get_service()
    if board_id is not None:
        if not service:
            raise HTTPException(status_code=503, detail="Service not initialized")
        board = _require_board(board_id)
        client = service.get_board_client(board_id)
        if client is None:
            raise HTTPException(status_code=503, detail=f"Board client not initialized: {board_id}")
        return board, client
    if not service or not service.vb_client:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return None, service.vb_client


def _render_live_page_grid(page_id: str, rows: int, cols: int) -> list[list[int]]:
    """Render *page_id* fresh and convert it to a rows×cols grid."""
    page_service = get_page_service()
    result = page_service.preview_page(page_id, force_refresh=True)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")
    if not result.available:
        raise HTTPException(status_code=503, detail=result.error or f"Page rendering failed: {page_id}")
    return text_to_board_array(result.formatted, rows=rows, cols=cols)


@app.post("/transitions/test-live")
async def run_live_transition_test(request: dict):
    """Run a transition plugin once on the real board (Transition Lab).

    Request body:
      - plugin_id (str, required): the transition plugin to drive
      - to_page_id (str, required): page the transition lands on
      - from_page_id (str, optional): page snapped to the board first so
        the transition visibly starts from it; omitted → the transition
        starts from whatever the board currently shows
      - config (dict, optional): per-run overrides merged on top of the
        plugin's currently-bound config
      - board_id (str, optional): target board; omitted → primary board

    Respects silence mode and board pause (409 so the UI can explain why
    nothing happened).  The board is left showing the to-page; use
    ``POST /transitions/restore`` — or just wait for the normal display
    loop — to return it to its active page.

    Gated behind ``beta.transition_plugins_enabled``.
    """
    _ensure_transition_plugins_beta()

    from .plugins.registry import get_plugin_registry

    plugin_id = request.get("plugin_id")
    if not plugin_id or not isinstance(plugin_id, str):
        raise HTTPException(status_code=400, detail="plugin_id is required")
    to_page_id = request.get("to_page_id")
    if not to_page_id or not isinstance(to_page_id, str):
        raise HTTPException(status_code=400, detail="to_page_id is required")
    from_page_id = request.get("from_page_id")
    board_id = request.get("board_id")

    registry = get_plugin_registry()
    plugin = registry.get_transition_plugin(plugin_id)
    if plugin is None:
        raise HTTPException(
            status_code=404,
            detail=f"Transition plugin {plugin_id!r} not loaded or not enabled",
        )

    board, board_client = _resolve_live_board_client(board_id)

    if _silence_active(board_id):
        raise HTTPException(status_code=409, detail="Silence mode is active - live test blocked")
    if _board_is_paused(board_id):
        raise HTTPException(status_code=409, detail="Board is paused - live test blocked")

    page_service = get_page_service()
    to_page = page_service.get_page(to_page_id)
    if not to_page:
        raise HTTPException(status_code=404, detail=f"Page not found: {to_page_id}")
    if from_page_id and not page_service.get_page(from_page_id):
        raise HTTPException(status_code=404, detail=f"Page not found: {from_page_id}")

    # Size grids to the explicit target board when given (issue #1244);
    # otherwise keep the to-page's own device type, matching /pages/{id}/send.
    if board is not None:
        dims = _board_dims(board)
        device_hint = board.get("device_type") or to_page.device_type
    else:
        dims = resolve_dimensions(to_page.device_type, to_page.notes_wide, to_page.notes_tall)
        device_hint = to_page.device_type

    to_grid = _render_live_page_grid(to_page_id, dims.rows, dims.cols)
    from_grid = _render_live_page_grid(from_page_id, dims.rows, dims.cols) if from_page_id else None

    # Merge override config on top of the plugin's currently-bound config,
    # mirroring /transitions/preview so live behavior matches the preview.
    config = dict(plugin.config or {})
    overrides = request.get("config") or {}
    if isinstance(overrides, dict):
        config.update(overrides)

    max_runtime_s = int(plugin.transition_settings["max_runtime_seconds"])

    def _run_live() -> tuple[bool, bool]:
        if from_grid is not None:
            board_client.send_characters(from_grid, strategy=None, force=True)
            time.sleep(LIVE_TEST_FROM_HOLD_SECONDS)
        return board_client.render(
            to_grid,
            strategy=f"plugin:{plugin_id}",
            force=True,
            device_type=device_hint,
            transition_config=config,
        )

    try:
        # The runner enforces the plugin's runtime cap itself; the outer
        # timeout only guards against a generator that blocks inside next()
        # (the abandoned thread still snaps the board to the target).
        success, was_sent = await asyncio.wait_for(
            asyncio.to_thread(_run_live),
            timeout=max_runtime_s + LIVE_TEST_FROM_HOLD_SECONDS + 15,
        )
    except TimeoutError as exc:
        logger.warning("Live transition test for %s exceeded %ds; abandoning", plugin_id, max_runtime_s)
        raise HTTPException(
            status_code=504,
            detail=f"Plugin {plugin_id!r} exceeded the {max_runtime_s}s runtime cap.",
        ) from exc

    if not success:
        raise HTTPException(status_code=502, detail="Board unreachable - live test failed")

    return {
        "status": "success",
        "sent": was_sent,
        "plugin_id": plugin_id,
        "from_page_id": from_page_id,
        "to_page_id": to_page_id,
        "board_id": board_id,
    }


@app.post("/transitions/restore")
async def restore_after_transition_test(request: dict | None = None):
    """Snap the board back to its active page after a live transition test.

    Request body (optional):
      - board_id (str, optional): target board; omitted → primary board

    Re-renders the board's active page and sends it plainly (no
    transition), cancelling any still-running plugin transition.  The
    normal display loop would eventually do the same; this endpoint just
    lets the Transition Lab do it on demand.

    Gated behind ``beta.transition_plugins_enabled``.
    """
    _ensure_transition_plugins_beta()

    body = request or {}
    board_id = body.get("board_id")

    board, board_client = _resolve_live_board_client(board_id)

    if _silence_active(board_id):
        raise HTTPException(status_code=409, detail="Silence mode is active - restore blocked")
    if _board_is_paused(board_id):
        raise HTTPException(status_code=409, detail="Board is paused - restore blocked")

    settings_service = get_settings_service()
    if board_id is not None:
        active_page_id = settings_service.get_active_page_id(board_id=board_id)
    else:
        active_page_id = settings_service.get_active_page_id()
    if not active_page_id:
        raise HTTPException(status_code=404, detail="No active page set")

    if is_collection_id(active_page_id):
        resolved = get_collection_service().resolve_page_id(active_page_id)
        if not resolved:
            raise HTTPException(status_code=404, detail="Collection could not be resolved")
        active_page_id = resolved

    page_service = get_page_service()
    page = page_service.get_page(active_page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Active page not found")

    if board is not None:
        dims = _board_dims(board)
    else:
        dims = resolve_dimensions(page.device_type, page.notes_wide, page.notes_tall)
    grid = _render_live_page_grid(active_page_id, dims.rows, dims.cols)

    success, was_sent = await run_board_send(board_client.render, grid, strategy=None, force=True)
    if not success:
        raise HTTPException(status_code=502, detail="Board unreachable - restore failed")

    return {"status": "success", "page_id": active_page_id, "sent": was_sent, "board_id": board_id}


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




def _paused_response(board_id: str | None = None) -> dict:
    """Standard payload returned by API endpoints that skip a send because
    the target board is paused."""
    return {
        "status": "blocked",
        "message": "Board is paused — sends are blocked until it is resumed.",
        "paused": True,
        "board_id": board_id,
    }


# =============================================================================
# Debug / diagnostics / logs Endpoints — moved to src/debug/routes.py
# (Phase 2 Task 8). Covers /debug/*, GET /cache-status, POST /clear-cache,
# POST /force-refresh and GET /logs.
# =============================================================================

from .debug.routes import router as debug_router  # noqa: E402

app.include_router(debug_router)


# =============================================================================
# FiestaPanel Endpoints
# =============================================================================
#
# Two surfaces with different auth:
#   /panels  (plural)  — CRUD for the app, authenticated like everything else.
#   /panel/  (singular) — read-only viewer endpoints for TVs, exempted from
#                         auth via AuthMiddleware(extra_public_paths).
# A panel's virtual board is co-created on POST and co-deleted on DELETE so
# "a FiestaPanel" stays one concept for the user.


def _panel_not_found_detail(ref: str) -> str:
    """404 detail for the public viewer: the reserved display ref gets
    actionable copy (the HDMI kiosk shows it before a panel is designated)."""
    if ref == "display":
        return "No display panel selected"
    return "Panel not found"


def _panel_board_fields(board: dict | None) -> dict:
    """Board-derived fields attached to panel payloads (orphan-aware)."""
    if board is None:
        return {"device_type": None, "board_missing": True, "rows": None, "cols": None}
    dims = _board_dims(board)
    return {
        "device_type": board.get("device_type"),
        "board_missing": False,
        "rows": dims.rows,
        "cols": dims.cols,
    }


@app.get("/panels")
async def list_panels():
    """List all panels with their virtual board's shape attached."""
    panel_service = get_panel_service()
    panels = []
    for panel in panel_service.list_panels():
        board = _find_board(panel.board_id)
        panels.append({**panel.model_dump(mode="json"), **_panel_board_fields(board)})
    return {"panels": panels, "total": len(panels)}


@app.post("/panels")
async def create_panel(data: PanelCreate):
    """Create a panel and its backing auto-fit virtual board.

    The board's grid (note-array blocks) is computed from the TV size so
    each flap renders at real-world scale while filling the screen. The
    virtual board is added first; if panel creation then fails the board
    is rolled back so no orphan is left behind.
    """
    from .panels.autofit import compute_autofit_grid

    settings_service = get_settings_service()
    board_id = str(uuid.uuid4())
    notes_wide, notes_tall = compute_autofit_grid(
        data.screen_diagonal_inches, data.screen_aspect_w, data.screen_aspect_h
    )
    settings_service.add_board(
        {
            "id": board_id,
            "device_type": "note_array",
            "api_mode": "virtual",
            "notes_wide": notes_wide,
            "notes_tall": notes_tall,
            "name": f"{data.name} (Panel)",
        }
    )
    _reinitialize_board_clients()
    panel_service = get_panel_service()
    try:
        panel = panel_service.create_panel(data, board_id=board_id)
    except Exception:
        with contextlib.suppress(Exception):
            settings_service.remove_board(board_id)
            _reinitialize_board_clients()
        raise
    board = _find_board(board_id)
    return {
        "status": "success",
        "panel": {**panel.model_dump(mode="json"), **_panel_board_fields(board)},
    }


@app.patch("/panels/{panel_id}")
async def update_panel(panel_id: str, data: PanelUpdate):
    """Update a panel's display configuration.

    A screen-size change re-fits the virtual board's grid: content keeps
    flowing at the new dimensions on the next send.
    """
    from .panels.autofit import compute_autofit_grid

    panel_service = get_panel_service()
    panel = panel_service.update_panel(panel_id, data)
    if panel is None:
        raise HTTPException(status_code=404, detail="Panel not found")

    incompatible_references: list[dict] | None = None
    updates = data.model_dump(exclude_unset=True)
    screen_changed = any(
        updates.get(field) is not None for field in ("screen_diagonal_inches", "screen_aspect_w", "screen_aspect_h")
    )
    if screen_changed:
        settings_service = get_settings_service()
        boards = [dict(b) for b in (settings_service.get_board_settings().boards or [])]
        target = next((b for b in boards if b.get("id") == panel.board_id), None)
        if target is not None and target.get("api_mode") == "virtual":
            notes_wide, notes_tall = compute_autofit_grid(
                panel.screen_diagonal_inches, panel.screen_aspect_w, panel.screen_aspect_h
            )
            if (target.get("notes_wide"), target.get("notes_tall")) != (notes_wide, notes_tall) or target.get(
                "device_type"
            ) != "note_array":
                target["device_type"] = "note_array"
                target["notes_wide"] = notes_wide
                target["notes_tall"] = notes_tall
                settings_service.set_boards(boards)
                # Drop the old-shape frame BEFORE rebuilding the client.
                # read_current_message already refuses to serve a frame whose
                # shape no longer matches the board, but `_last_characters` is
                # read unguarded by /board/current-message (both the secondary
                # branch and the primary's `expected_characters`), which would
                # keep rendering the old grid — the exact stale-shape bug this
                # reshape path exists to prevent. Releasing the shared state
                # clears `displayed_characters` and `last_characters` together.
                release_virtual_board_state(panel.board_id)
                _reinitialize_board_clients()
                # The grid changed shape: pages authored for the old grid stay
                # referenced but can no longer render here. Warn-only, exactly
                # like PUT /pages/{id} after a size retarget (issue #1250).
                incompatible_references = find_incompatible_board_references(target)

    board = _find_board(panel.board_id)
    response = {
        "status": "success",
        "panel": {**panel.model_dump(mode="json"), **_panel_board_fields(board)},
    }
    if incompatible_references is not None:
        response["incompatible_references"] = incompatible_references
    return response


@app.delete("/panels/{panel_id}")
async def delete_panel(panel_id: str):
    """Delete a panel and its virtual board (tolerating an already-gone board).

    When the virtual board is the ONLY board, the last-board rule forbids
    removing it outright — deleting the panel would otherwise strand an
    unremovable virtual board as the primary. A fresh default board is
    swapped in instead (the same state a data reset produces).
    """
    panel_service = get_panel_service()
    panel = panel_service.delete_panel(panel_id)
    if panel is None:
        raise HTTPException(status_code=404, detail="Panel not found")
    settings_service = get_settings_service()
    try:
        settings_service.remove_board(panel.board_id)
    except ValueError:
        # Either the board is already gone (fine) or it is the last board.
        boards = settings_service.get_board_settings().boards or []
        if len(boards) == 1 and boards[0].get("id") == panel.board_id:
            with contextlib.suppress(Exception):
                settings_service.set_boards([{"device_type": "flagship"}])
    release_virtual_board_state(panel.board_id)
    _reinitialize_board_clients()
    return {"status": "success"}


@app.get("/panel/{panel_id}")
async def get_panel_public(panel_id: str):
    """Public viewer config: panel settings + board geometry. No auth."""
    panel = get_panel_service().get_panel_by_ref(panel_id)
    if panel is None:
        raise HTTPException(status_code=404, detail=_panel_not_found_detail(panel_id))
    out = panel.model_dump(mode="json")
    board = _find_board(panel.board_id)
    if board is None:
        out.update(
            {
                "device_type": None,
                "board_missing": True,
                "rows": None,
                "cols": None,
                "board_color": None,
                "code62_glyph": None,
            }
        )
        return out
    from .devices import BoardInstance

    dims = _board_dims(board)
    instance = BoardInstance.from_dict(board)
    out.update(
        {
            "device_type": board.get("device_type"),
            "board_missing": False,
            "rows": dims.rows,
            "cols": dims.cols,
            "board_color": board.get("board_color") or "black",
            "code62_glyph": instance.effective_code62_glyph,
        }
    )
    return out


@app.get("/panel/{panel_id}/frame")
async def get_panel_frame(panel_id: str):
    """Public viewer frame: the virtual board's current content. No auth.

    Never triggers a live HTTP read — a panel misconfigured onto a physical
    board serves that board's last-sent cache instead of hammering it at the
    viewer's 2s poll cadence.
    """
    panel = get_panel_service().get_panel_by_ref(panel_id)
    if panel is None:
        raise HTTPException(status_code=404, detail=_panel_not_found_detail(panel_id))
    board = _find_board(panel.board_id)
    dims = _board_dims(board) if board is not None else resolve_dimensions("flagship")

    service = get_service()
    client = service.get_board_client(panel.board_id) if service is not None else None
    if client is None and service is not None:
        # Primary runtimes may be keyed under a legacy sentinel rather than
        # the settings board id; fall back to the primary client.
        with contextlib.suppress(Exception):
            if panel.board_id == get_settings_service().get_primary_board_id():
                client = service.vb_client

    characters = None
    updated_at = None
    if client is not None:
        if getattr(client, "is_virtual", False):
            characters = client.read_current_message()
        else:
            characters = getattr(client, "_last_characters", None)
        ts = getattr(client, "_last_sent_at", None)
        if ts:
            updated_at = datetime.fromtimestamp(ts, tz=UTC).isoformat()

    if characters is None:
        return {
            "characters": None,
            "message": None,
            "rows": dims.rows,
            "cols": dims.cols,
            "updated_at": updated_at,
        }
    return {
        "characters": characters,
        "message": _characters_to_message(characters),
        "rows": len(characters),
        "cols": len(characters[0]) if characters else 0,
        "updated_at": updated_at,
    }


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


@app.get("/home-assistant/entities")
async def get_home_assistant_entities():
    """
    Get all available entities from Home Assistant.

    Returns list of entities with their current state and all attributes.
    Used by the UI to populate entity picker dropdowns.
    """
    from .utils.home_assistant import get_home_assistant_source

    ha_source = get_home_assistant_source()
    if not ha_source:
        raise HTTPException(status_code=503, detail="Home Assistant not configured")

    try:
        # Call Home Assistant /api/states to get ALL entities
        response = await asyncio.to_thread(
            requests.get,
            f"{ha_source.base_url}/api/states",
            headers=ha_source.headers,
            timeout=ha_source.timeout,
        )
        response.raise_for_status()
        entities = response.json()

        # Transform to simpler format for UI (HA may omit or null attributes)
        result_entities = []
        for e in entities:
            attrs = e.get("attributes") or {}
            result_entities.append(
                {
                    "entity_id": e["entity_id"],
                    "state": e["state"],
                    "attributes": attrs,
                    "friendly_name": attrs.get("friendly_name", e["entity_id"]),
                }
            )
        return {"entities": result_entities}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to fetch entities: {str(e)}") from e


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
# Triggers — Event-based plugin messages
# =============================================================================


@app.get("/triggers")
async def list_triggers():
    """List all active triggers with their status."""
    from .triggers.service import get_trigger_service

    trigger_service = get_trigger_service()
    active = trigger_service.list_active_triggers()
    return {
        "triggers": [t.to_dict() for t in active],
        "count": len(active),
    }


@app.get("/triggers/active")
async def get_active_trigger():
    """Get the current highest-priority active trigger, if any."""
    from .triggers.service import get_trigger_service

    trigger_service = get_trigger_service()
    active = trigger_service.get_active_trigger()
    if active is None:
        return {"trigger": None}
    return {"trigger": active.to_dict()}


@app.post("/triggers/{trigger_id}/dismiss")
async def dismiss_trigger(trigger_id: str):
    """Dismiss (remove) a specific trigger by its id."""
    from .triggers.service import get_trigger_service

    trigger_service = get_trigger_service()
    dismissed = trigger_service.dismiss_trigger(trigger_id)
    if not dismissed:
        raise HTTPException(status_code=404, detail=f"Trigger not found: {trigger_id}")
    return {"status": "dismissed", "trigger_id": trigger_id}


@app.post("/triggers/clear")
async def clear_triggers():
    """Clear all active triggers."""
    from .triggers.service import get_trigger_service

    trigger_service = get_trigger_service()
    trigger_service.clear_all()
    return {"status": "cleared"}


@app.post("/triggers/check")
async def check_triggers():
    """Manually trigger a check of all trigger-capable plugins.

    This is normally done automatically by the display loop, but this
    endpoint allows the UI or external systems to force an immediate check.
    """
    if not PLUGIN_SYSTEM_AVAILABLE:
        raise HTTPException(status_code=503, detail="Plugin system is not available.")

    from .triggers.service import get_trigger_service

    registry = get_plugin_registry()
    trigger_service = get_trigger_service()

    checked = 0
    for _plugin_id, plugin in registry.trigger_plugins.items():
        trigger_service.check_plugin_triggers(plugin)
        checked += 1

    active = trigger_service.list_active_triggers()
    return {
        "plugins_checked": checked,
        "active_triggers": [t.to_dict() for t in active],
        "count": len(active),
    }


# =============================================================================
# Generic Data Plugin — Test Fetch
# =============================================================================


@app.post("/generic-data/test-fetch")
async def generic_data_test_fetch(request: dict):
    """Fetch a URL and return the parsed response structure for mapping preview.

    Reuses the same parsing logic as the generic_data plugin so the preview
    matches real behaviour.  Response body is capped at 1 MB.
    """
    import defusedxml.ElementTree as DefusedET
    import requests as req

    from .plugins.config_interpolation import get_builtin_variables, interpolate_string

    try:
        _tz = get_config_manager().get_general().get("timezone") or "America/Los_Angeles"
        _interp_vars = get_builtin_variables(timezone=_tz)
    except Exception:
        _interp_vars = get_builtin_variables()

    url = interpolate_string((request.get("url") or "").strip(), _interp_vars)
    fmt = request.get("format", "json")
    method = request.get("method", "GET")
    headers_list = request.get("headers", [])
    body = request.get("body")

    # Validate the URL: scheme must be http(s) and credentials are not allowed
    # (defence against SSRF/credential leaks).
    _SSRF_BLOCKED_DETAILS = {
        "URL must not target internal network resources",
        "URL host is not allowed",
        "URL host resolves to a non-public IP",
    }
    try:
        _validate_request_url(url)
    except HTTPException as _url_exc:
        if _url_exc.detail in _SSRF_BLOCKED_DETAILS:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Test & Preview can't reach local or private network addresses "
                    f"({urlparse(url).hostname}). This restriction only applies to the "
                    "preview feature — your plugin will still fetch this URL normally "
                    "when your page runs."
                ),
            ) from _url_exc
        raise
    # Re-derive url from a strict allowlist regex so the downstream HTTP call is not
    # tracked as tainted by static-analysis tools (py/full-ssrf).
    _safe_url_m = re.fullmatch(
        r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+",
        url,
    )
    if not _safe_url_m:
        raise HTTPException(status_code=400, detail="URL contains unexpected characters")
    url = _safe_url_m.group(0)

    # Resolve the URL host and confirm it is a public/global IP address.
    # CodeQL's ``py/full-ssrf`` IpAddressSanitizer recognises an
    # ``ipaddress`` object gated by a positive ``is_global`` check.
    import ipaddress as _ipaddress_mod
    import socket as _socket_mod

    _parsed_url = urlparse(url)
    _host_for_check = (_parsed_url.hostname or "").strip()
    try:
        _resolved_ip = _ipaddress_mod.ip_address(_host_for_check)
    except ValueError:
        try:
            _addrinfo = _socket_mod.getaddrinfo(
                _host_for_check,
                _parsed_url.port or (443 if _parsed_url.scheme == "https" else 80),
            )
        except _socket_mod.gaierror:
            raise HTTPException(status_code=400, detail="URL host could not be resolved") from None
        _resolved_ips = [info[4][0] for info in _addrinfo if info and len(info) >= 5 and info[4]]
        if not _resolved_ips:
            raise HTTPException(status_code=400, detail="URL host did not resolve") from None
        _resolved_ip = _ipaddress_mod.ip_address(_resolved_ips[0])
    # Positive ``is_global`` check — the CodeQL-recognised IpAddressSanitizer.
    if not _resolved_ip.is_global:
        raise HTTPException(status_code=400, detail="URL host resolves to a non-public IP")

    # After the IP barrier passes, rebuild ``url`` via ``urlunsplit`` from
    # the parsed components.  This routes the final URL string through
    # ``urllib.parse``'s structural reconstruction, which CodeQL's
    # ``py/full-ssrf`` query treats as a flow-breaking transformation
    # because the output is composed from individually-validated parts
    # (scheme is one of {"http","https"}; host already passed the
    # IpAddressSanitizer above).
    from urllib.parse import urlunsplit as _urlunsplit

    _safe_scheme = "https" if _parsed_url.scheme == "https" else "http"
    _safe_netloc = _host_for_check
    if _parsed_url.port:
        _safe_netloc = f"{_safe_netloc}:{int(_parsed_url.port)}"
    url = _urlunsplit((_safe_scheme, _safe_netloc, _parsed_url.path or "", _parsed_url.query or "", ""))

    host = _host_for_check
    allowed_hosts = _get_generic_data_allowed_hosts()
    # When GENERIC_DATA_ALLOWED_HOSTS is set, enforce the allowlist.
    # When it is unset, _validate_request_url above already blocks SSRF
    # (private IPs, loopback, .local) so we allow any public host.
    if allowed_hosts and not _is_host_allowed(host, allowed_hosts):
        raise HTTPException(
            status_code=400,
            detail="URL host is not in the allowlist",
        )

    headers: dict = {
        "Accept": "application/json" if fmt == "json" else "application/xml",
    }
    for h in headers_list:
        n = (h.get("name") or "").strip()
        v = (h.get("value") or "").strip()
        if n and v:
            headers[n] = interpolate_string(v, _interp_vars)

    try:
        kwargs: dict = {"headers": headers, "timeout": 15, "allow_redirects": False}
        if method == "POST" and body:
            kwargs["data"] = interpolate_string(body, _interp_vars) if isinstance(body, str) else body

        resp = req.request(method, url, **kwargs)
        resp.raise_for_status()

        if len(resp.content) > 1_048_576:
            raise HTTPException(status_code=400, detail="Response too large (exceeds 1 MB)")

        if fmt == "xml":
            from plugins.generic_data import _xml_to_dict

            # ``defusedxml`` disables external entity expansion, DTDs and
            # entity bombs by default, mitigating XXE attacks.
            root = DefusedET.fromstring(resp.text)
            parsed = _xml_to_dict(root)
        else:
            parsed = resp.json()

        return {"ok": True, "data": parsed}
    except HTTPException:
        raise
    except req.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Request timed out") from None
    except req.exceptions.ConnectionError:
        raise HTTPException(status_code=502, detail="Connection error — check the URL") from None
    except req.exceptions.HTTPError:
        # Don't echo the upstream exception (URL/headers/status) back to the
        # caller — generic message is enough for a "test fetch" feature.
        raise HTTPException(status_code=502, detail="HTTP error from remote service") from None
    except Exception:
        logger.exception("generic-data test-fetch failed")
        raise HTTPException(status_code=500, detail="Failed to fetch data") from None


# =============================================================================
# Backup & Restore — export and import all user data as a single JSON file
# =============================================================================


@app.get("/backup/export")
async def export_backup():
    """Download a JSON file containing all user data (config, settings,
    pages, collections, schedules, and metadata for installed external
    plugins).

    The file can be re-uploaded to ``/backup/import`` on a new instance
    to migrate or restore a configuration.
    """
    from .backup import get_backup_service

    payload = get_backup_service().export_to_json()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"fiestaboard-backup-{timestamp}.json"
    return Response(
        content=payload,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@app.post("/backup/import")
async def import_backup(
    payload: dict[str, Any] = Body(...),
    reinstall_plugins: bool = Query(True),
):
    """Restore a backup file produced by ``/backup/export``.

    Existing data files are preserved as ``<name>.json.pre-restore-<ts>``
    siblings before being overwritten so the operator can roll back
    manually if needed.  In-memory service singletons are reloaded so the
    change takes effect without restarting the container.
    """
    from .backup import BackupError, BackupRestoreAborted, get_backup_service

    try:
        result = get_backup_service().import_from_dict(payload, reinstall_plugins=reinstall_plugins)
    except BackupRestoreAborted as exc:
        # The environment failed, not the uploaded file — a 400 would blame
        # the operator's backup for a full disk (Phase 2 Task 10d).
        logger.error("Backup restore aborted: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except BackupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("Backup import failed")
        raise HTTPException(status_code=500, detail="Backup import failed") from None

    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
