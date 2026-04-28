"""REST API server for FiestaBoard Display Service."""

import asyncio
import logging
import logging.handlers
import threading
import time
import os
import json
import re
import requests
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, Body, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Load environment variables from .env file
load_dotenv()

from . import __version__
from .main import DisplayService
from .config import Config
from .config_manager import get_config_manager
from .displays.service import get_display_service, reset_display_service
from .settings.service import get_settings_service, VALID_STRATEGIES, VALID_OUTPUT_TARGETS
from .pages.service import get_page_service
from .pages.models import PageCreate, PageUpdate
from .schedules.service import get_schedule_service
from .schedules.models import ScheduleCreate, ScheduleUpdate
from .carousels.service import get_carousel_service
from .carousels.models import CarouselCreate, CarouselUpdate, is_carousel_id
from .templates.engine import get_template_engine, reset_template_engine
from .text_to_board import text_to_board_array
from .devices import get_dimensions
from .board_client import board_client_from_board_dict

logger = logging.getLogger(__name__)

# Log file configuration
LOG_DIR = Path("/app/data/logs")
LOG_FILE = LOG_DIR / "app.log"
LOG_MAX_BYTES = 5 * 1024 * 1024  # 5MB per file
LOG_BACKUP_COUNT = 5  # Keep 5 backup files (25MB total max)

# Cache state for /muni/stops endpoint
_muni_stops_cache: Optional[Dict[str, Any]] = None
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
    from urllib.parse import urlparse
    import ipaddress
    import socket

    if not isinstance(url, str) or not url:
        raise HTTPException(status_code=400, detail="URL is required")
    try:
        parsed = urlparse(url)
    except ValueError:
        raise HTTPException(status_code=400, detail="URL could not be parsed")
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
        raise HTTPException(
            status_code=400, detail="URL must not contain credentials"
        )
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
        if (
            _addr.is_private
            or _addr.is_loopback
            or _addr.is_link_local
            or _addr.is_reserved
            or _addr.is_multicast
        ):
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
            raise HTTPException(status_code=400, detail="URL host could not be resolved")

        for info in infos:
            resolved_ip = info[4][0]
            if _is_non_public_ip(resolved_ip):
                raise HTTPException(status_code=400, detail="URL host resolves to a non-public IP")


def _get_generic_data_allowed_hosts() -> List[str]:
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


def _is_host_allowed(host: str, allowed_hosts: List[str]) -> bool:
    """Check whether host is exactly allowed or a subdomain of an allowed host."""
    h = (host or "").strip().lower().rstrip(".")
    for allowed in allowed_hosts:
        if h == allowed or h.endswith("." + allowed):
            return True
    return False


# Hostnames are restricted to RFC 1123 labels (letters, digits, hyphens) and
# IPv4 dotted-quad notation.  This rejects exotic forms (URL-encoded chars,
# ``user:pass@host``, schemes embedded in the host, etc.) before we ever try
# to connect to a board over HTTP.
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)"
    r"(?:(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)\.)*"
    r"(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)$"
)


def _validate_board_host(host: str) -> None:
    """Validate that ``host`` is a plain IP/hostname (no scheme, port, path).

    Used before constructing URLs that target a Vestaboard on the local
    network.  Raises :class:`HTTPException` (status 400) when invalid.
    """
    if not isinstance(host, str) or not host:
        raise HTTPException(status_code=400, detail="host is required")
    # Reject anything that looks like a full URL or contains delimiters that
    # could redirect the request elsewhere (``@``, ``/``, ``:``, ``?``,
    # ``#`` or whitespace).
    if any(c in host for c in "@/:?# \t\r\n\\"):
        raise HTTPException(
            status_code=400,
            detail="host must be a bare IP address or hostname",
        )
    # Try IPv4 first, then a hostname pattern.
    import ipaddress

    try:
        ipaddress.IPv4Address(host)
        return
    except ValueError:
        pass
    if not _HOSTNAME_RE.match(host):
        raise HTTPException(
            status_code=400,
            detail="host must be a valid IPv4 address or hostname",
        )


def _validate_board_host_is_local_network(host: str) -> None:
    """Ensure ``host`` resolves only to private/local IPv4 addresses.

    Prevents SSRF to arbitrary internet hosts while still allowing local
    network boards.
    """
    import ipaddress
    import socket

    def _is_allowed_ipv4(addr: ipaddress.IPv4Address) -> bool:
        return (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
        )

    try:
        ip = ipaddress.IPv4Address(host)
        if not _is_allowed_ipv4(ip):
            raise HTTPException(
                status_code=400,
                detail="host must resolve to a local/private IPv4 address",
            )
        return
    except ValueError:
        pass

    try:
        addrinfo = socket.getaddrinfo(host, None, family=socket.AF_INET, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise HTTPException(status_code=400, detail="host could not be resolved")

    resolved_ips = {
        ipaddress.IPv4Address(info[4][0])
        for info in addrinfo
        if info and len(info) >= 5 and info[4]
    }
    if not resolved_ips:
        raise HTTPException(status_code=400, detail="host did not resolve to an IPv4 address")

    if not all(_is_allowed_ipv4(ip) for ip in resolved_ips):
        raise HTTPException(
            status_code=400,
            detail="host must resolve only to local/private IPv4 addresses",
        )


# Global service instance
_service: Optional[DisplayService] = None
_service_lock = threading.Lock()
_service_thread: Optional[threading.Thread] = None
_service_running = False
_service_start_time: Optional[float] = None  # Track when service started
_shutting_down = False  # Set during app shutdown to suppress auto-restart

# In-memory log buffer (last 500 log entries for quick access)
_log_buffer: deque = deque(maxlen=500)
_log_lock = threading.Lock()

def _create_log_entry(record: logging.LogRecord, formatted_message: str) -> Dict[str, Any]:
    """Create a structured log entry from a log record with UTC timestamp."""
    from .time_service import get_time_service
    time_service = get_time_service()
    
    return {
        "timestamp": time_service.create_utc_timestamp(),
        "level": record.levelname,
        "logger": record.name,
        "message": formatted_message
    }


class LogBufferHandler(logging.Handler):
    """Custom logging handler that stores logs in memory for API access."""
    
    def emit(self, record):
        try:
            log_entry = _create_log_entry(record, self.format(record))
            with _log_lock:
                _log_buffer.append(log_entry)
        except Exception:
            self.handleError(record)


class JSONFileHandler(logging.handlers.RotatingFileHandler):
    """Rotating file handler that writes logs as JSON lines."""
    
    def emit(self, record):
        try:
            log_entry = _create_log_entry(record, self.format(record))
            # Write as JSON line
            msg = json.dumps(log_entry) + '\n'
            stream = self.stream
            stream.write(msg)
            self.flush()
            # Handle rotation
            if self.shouldRollover(record):
                self.doRollover()
        except Exception:
            self.handleError(record)
    
    def shouldRollover(self, record):
        """Check if we should rollover based on file size."""
        if self.stream is None:
            self.stream = self._open()
        if self.maxBytes > 0:
            self.stream.seek(0, 2)  # Seek to end
            if self.stream.tell() >= self.maxBytes:
                return True
        return False


def _setup_file_logging():
    """Set up file-based logging with rotation."""
    try:
        # Create logs directory if it doesn't exist
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        
        # Create JSON file handler with rotation
        file_handler = JSONFileHandler(
            str(LOG_FILE),
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding='utf-8'
        )
        file_handler.setFormatter(logging.Formatter('%(message)s'))
        file_handler.setLevel(logging.INFO)
        
        # Add to root logger
        logging.getLogger().addHandler(file_handler)
        logger.info(f"File logging initialized: {LOG_FILE}")
    except Exception as e:
        logger.warning(f"Failed to set up file logging: {e}")


def _read_logs_from_files(
    limit: int = 100,
    offset: int = 0,
    level: Optional[str] = None,
    search: Optional[str] = None
) -> tuple[List[Dict[str, Any]], int, bool]:
    """
    Read logs from log files with filtering and pagination.
    
    Returns: (logs, total_matching, has_more)
    """
    all_logs = []
    
    # Read from current log file and backups
    log_files = [LOG_FILE]
    for i in range(1, LOG_BACKUP_COUNT + 1):
        backup_file = Path(f"{LOG_FILE}.{i}")
        if backup_file.exists():
            log_files.append(backup_file)
    
    # Read all log entries from files (newest first)
    for log_file in log_files:
        if not log_file.exists():
            continue
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                for line in reversed(lines):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        all_logs.append(entry)
                    except json.JSONDecodeError:
                        continue
        except Exception:
            continue
    
    # Also include in-memory buffer (most recent)
    with _log_lock:
        memory_logs = list(_log_buffer)
    
    # Merge: memory logs are most recent, then file logs
    # Deduplicate by timestamp + message
    seen = set()
    merged_logs = []
    
    for log in reversed(memory_logs):
        key = (log.get('timestamp'), log.get('message'))
        if key not in seen:
            seen.add(key)
            merged_logs.append(log)
    
    for log in all_logs:
        key = (log.get('timestamp'), log.get('message'))
        if key not in seen:
            seen.add(key)
            merged_logs.append(log)
    
    # Apply filters
    filtered_logs = merged_logs
    
    if level:
        level_upper = level.upper()
        filtered_logs = [log for log in filtered_logs if log.get('level') == level_upper]
    
    if search:
        search_lower = search.lower()
        filtered_logs = [
            log for log in filtered_logs
            if search_lower in log.get('message', '').lower() or
               search_lower in log.get('logger', '').lower()
        ]
    
    total_matching = len(filtered_logs)
    
    # Apply pagination
    start = offset
    end = offset + limit
    paginated = filtered_logs[start:end]
    has_more = end < total_matching
    
    return paginated, total_matching, has_more


class MessageRequest(BaseModel):
    """Request model for sending a custom message."""
    text: str


class StatusResponse(BaseModel):
    """Response model for service status."""
    running: bool
    initialized: bool
    config_summary: Dict[str, Any]


class HealthResponse(BaseModel):
    """Response model for health check."""
    status: str
    service_running: bool
    version: str


class VersionResponse(BaseModel):
    """Response model for version information."""
    package_version: str
    build_version: str
    is_dev: bool


class UpdateCheckResponse(BaseModel):
    """Response model for update check."""
    current_version: str
    latest_version: str | None
    update_available: bool
    package_url: str
    error: str | None = None
    is_production: bool


class UpdateStatusResponse(BaseModel):
    """Response model for system update status (sidecar availability + auto-update flag)."""
    updater_available: bool
    auto_update_enabled: bool
    profile: str  # "docker" | "pi"  (where this install is running)
    sidecar_url: str
    last_check: str | None = None
    last_update: str | None = None


class UpdateApplyResponse(BaseModel):
    """Response model for triggering an update."""
    status: str  # "queued" | "manual"
    mode: str  # "sidecar" | "manual"
    previous_digest: str | None = None
    hint: str | None = None


class AutoUpdateRequest(BaseModel):
    """Request model for setting the auto-update toggle."""
    enabled: bool


class AutoUpdateResponse(BaseModel):
    """Response model for auto-update toggle."""
    enabled: bool


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    global _service_thread, _shutting_down, _service_running
    # --- Startup ---
    _shutting_down = False
    logger.info("API server starting up...")
    
    # Set up file-based logging
    _setup_file_logging()
    
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
                logger.warning("Background service failed to start - likely due to configuration issues. Use the /start endpoint or UI to start it manually after fixing configuration.")
        except Exception as e:
            logger.error(f"Failed to auto-start background service: {e}", exc_info=True)
            logger.warning("Service can be started manually via /start endpoint after configuration is fixed")
    else:
        logger.warning("Service instance could not be created - check logs for initialization errors")

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
            interval = 6 * 3600  # 6 hours
            # Initial delay of 5 minutes so startup isn't burdened
            await _asyncio.sleep(300)
            while True:
                try:
                    if PLUGIN_SYSTEM_AVAILABLE:
                        registry = get_plugin_registry()
                        results = registry.check_for_updates()
                        updates = [p for p, v in results.items() if v]
                        if updates:
                            logger.info(
                                "Plugin updates available: %s", ", ".join(updates)
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

    yield

    # --- Shutdown ---
    if update_check_task is not None:
        update_check_task.cancel()
    logger.info("API server shutting down...")
    _shutting_down = True
    _service_running = False
    if _service:
        _service.running = False

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


# Create FastAPI app
app = FastAPI(
    title="FiestaBoard Display API",
    description="REST API for controlling and monitoring the FiestaBoard Display Service",
    version=__version__,
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to your UI domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Set up log buffer handler
log_buffer_handler = LogBufferHandler()
log_buffer_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(log_buffer_handler)


def get_service() -> Optional[DisplayService]:
    """Get or create the service instance."""
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                try:
                    _service = DisplayService()
                    if not _service.initialize():
                        logger.warning("Service initialization failed - service can be started later when configuration is fixed")
                        # Keep the service instance but mark it as uninitialized
                        # This allows the /start endpoint to retry initialization
                        return _service
                except Exception as e:
                    logger.error(f"Failed to create service: {e}", exc_info=True)
                    return None
    return _service


def run_service_background():
    """Run the service in a background thread with auto-restart on failure."""
    global _service_running, _service_start_time
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
        _service_start_time = time.time()
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
    if _service:
        _service.running = False
    _service_running = False
    return True


@app.get("/", response_model=Dict[str, str])
async def root():
    """Root endpoint with API information."""
    return {
        "name": "FiestaBoard Display API",
        "version": "1.0.0",
        "status": "running"
    }


@app.api_route("/health", methods=["GET", "HEAD"], response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    service = get_service()
    return HealthResponse(
        status="ok",
        service_running=_service_running and service is not None,
        version=__version__
    )


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
    except Exception:
        return {"enabled": False, "connected": False, "running": False}


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
        raise HTTPException(status_code=500, detail=str(e))


def _apply_mqtt_config(mqtt_cfg) -> None:
    """Start or stop the MQTT client to match *mqtt_cfg.enabled*.

    Safe to call at any time: stops the old client first when one is running.
    """
    from .mqtt import MQTTClient, get_mqtt_client, set_mqtt_client_instance
    from .mqtt.state import StatePublisher
    from .mqtt.commands import CommandHandler

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


@app.get("/version", response_model=VersionResponse)
async def version():
    """Get version information.
    
    Returns both the package version (from __version__) and the build version
    (from VERSION environment variable). In production builds, these should match.
    """
    build_version = os.getenv("VERSION", "dev")
    production = os.getenv("PRODUCTION", "false").lower() == "true"
    return VersionResponse(
        package_version=__version__,
        build_version=build_version,
        is_dev=build_version == "dev" and not production
    )


# =============================================================================
# System Management Endpoints
# =============================================================================

GITHUB_PACKAGE_URL = "https://github.com/Fiestaboard/FiestaBoard/releases/latest"
GITHUB_RELEASES_API = "https://api.github.com/repos/Fiestaboard/FiestaBoard/releases/latest"
DOCKERHUB_TAGS_URL = "https://hub.docker.com/v2/repositories/fiestaboard/fiestaboard/tags"


def _check_dockerhub_for_latest() -> Optional[str]:
    """Check Docker Hub for the latest version tag.
    
    Queries the Docker Hub API for available tags. No authentication required
    for public repositories. Filters tags to find the highest semver version.
    
    Returns the latest version string, or None if the check fails.
    """
    try:
        # Query Docker Hub tags endpoint
        resp = requests.get(DOCKERHUB_TAGS_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        # Extract tag names from results
        results = data.get("results", [])
        tags = [result.get("name") for result in results if result.get("name")]
        
        # Filter to semver-style tags and find the highest version
        version_tags = []
        for tag in tags:
            parts = tag.split(".")
            if len(parts) >= 2 and all(p.isdigit() for p in parts):
                version_tags.append(tuple(int(p) for p in parts))
        
        if not version_tags:
            return None
        
        best = max(version_tags)
        return ".".join(str(p) for p in best)
    except Exception as e:
        logger.debug(f"Docker Hub version check failed: {e}")
        return None


def _check_github_releases_for_latest() -> Optional[str]:
    """Check GitHub Releases API for the latest version.
    
    Returns the latest version string, or None if the check fails.
    """
    try:
        resp = requests.get(
            GITHUB_RELEASES_API,
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=10,
        )
        resp.raise_for_status()
        tag_name = resp.json().get("tag_name", "")
        return tag_name.lstrip("v") if tag_name else None
    except Exception as e:
        logger.debug(f"GitHub releases check failed: {e}")
        return None


@app.get("/system/update-check", response_model=UpdateCheckResponse)
async def system_update_check():
    """Check if a newer version of FiestaBoard is available.
    
    Checks Docker Hub for the latest container image tag, with a fallback to
    the GitHub Releases API. No authentication is required because the package
    and repository are public.
    
    Returns the current version, latest version, and whether an update is available.
    """
    is_production = os.getenv("PRODUCTION", "false").lower() == "true"
    
    try:
        # Try Docker Hub first (checks actual container registry), fall back to GitHub Releases
        # Run in a thread so the blocking HTTP call doesn't stall the event loop
        latest_version = await asyncio.to_thread(_check_dockerhub_for_latest)
        
        if not latest_version:
            latest_version = await asyncio.to_thread(_check_github_releases_for_latest)
        
        if latest_version:
            update_available = _is_newer_version(latest_version, __version__)
            # Record this check so the UI can show "last checked".  Best-effort.
            try:
                _state = _system_update_state_load()
                _state["last_check"] = datetime.now(timezone.utc).isoformat()
                _system_update_state_save(_state)
            except Exception as e:
                logger.debug("Could not persist update-check timestamp (non-fatal): %s", e, exc_info=True)
            return UpdateCheckResponse(
                current_version=__version__,
                latest_version=latest_version,
                update_available=update_available,
                package_url=GITHUB_PACKAGE_URL,
                is_production=is_production,
            )
        
        raise RuntimeError("Both Docker Hub and GitHub Releases checks failed")
    except Exception as e:
        logger.warning(f"Failed to check for updates: {e}")
        return UpdateCheckResponse(
            current_version=__version__,
            latest_version=None,
            update_available=False,
            package_url=GITHUB_PACKAGE_URL,
            error=f"Could not check for updates: {e}",
            is_production=is_production,
        )


def _is_newer_version(latest: str, current: str) -> bool:
    """Compare two semver-style version strings.
    
    Returns True if latest is strictly newer than current.
    Handles version strings with varying component counts (e.g. "2.0" vs "2.0.1").
    """
    try:
        def parse_version(v: str):
            parts = v.split(".")
            if not parts or not all(p.isdigit() for p in parts):
                raise ValueError(f"Invalid version: {v}")
            return tuple(int(x) for x in parts)
        return parse_version(latest) > parse_version(current)
    except (ValueError, AttributeError):
        return False


# =============================================================================
# In-place self-update via the FiestaUpdater sidecar
# =============================================================================
#
# The companion `fiestaupdater` container exposes a tiny authenticated HTTP API
# on the internal compose network.  We never talk to the Docker socket from
# this process; we only proxy a single user-initiated request through.  See
# fiestaupdater/README.md for the security model.
# =============================================================================

# Path to the small JSON file that persists the auto-update toggle and
# bookkeeping (last check, last update).  Kept separate from settings.json
# because this state is system-level, not display-level.
SYSTEM_UPDATE_STATE_FILE = Path("data/.system-update.json")


def _system_update_state_load() -> Dict[str, Any]:
    """Read the system-update state file.  Returns a fresh dict on any error."""
    try:
        if SYSTEM_UPDATE_STATE_FILE.exists():
            with SYSTEM_UPDATE_STATE_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except Exception as e:
        logger.debug(f"Failed to read {SYSTEM_UPDATE_STATE_FILE}: {e}")
    return {}


def _system_update_state_save(state: Dict[str, Any]) -> None:
    """Persist the system-update state file."""
    try:
        SYSTEM_UPDATE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with SYSTEM_UPDATE_STATE_FILE.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to write {SYSTEM_UPDATE_STATE_FILE}: {e}")


def _fiestaboard_profile() -> str:
    """Return the install profile: "pi" if running on the FiestaPi flashable
    image, else "docker".  Determined by a build-time env var baked in by the
    pi-gen recipe.
    """
    return os.getenv("FIESTABOARD_PROFILE", "docker").strip().lower() or "docker"


def _auto_update_default() -> bool:
    """Default for the auto-update toggle when the user hasn't set one.
    OFF on regular Docker installs, ON on the Pi flashable image."""
    return _fiestaboard_profile() == "pi"


def _updater_url() -> str:
    """Base URL of the fiestaupdater sidecar on the compose network."""
    return os.getenv("FIESTAUPDATER_URL", "http://fiestaupdater:8765").rstrip("/")


def _updater_token() -> str:
    """Shared bearer token for the sidecar."""
    return os.getenv("FIESTAUPDATER_TOKEN", "")


def _updater_probe() -> bool:
    """Return True when the sidecar's /healthz responds 200.  Short timeout
    because this is called on every status query from the UI."""
    try:
        resp = requests.get(f"{_updater_url()}/healthz", timeout=2)
        return resp.status_code == 200
    except Exception:
        return False


@app.get("/system/update/status", response_model=UpdateStatusResponse)
async def system_update_status():
    """Report whether the FiestaUpdater sidecar is reachable and whether the
    user has opted in to scheduled auto-updates.
    
    The UI uses this to decide between showing the in-app "Update Now" button
    or fallback "manual update" instructions.
    """
    state = _system_update_state_load()
    available = await asyncio.to_thread(_updater_probe) if _updater_token() else False
    return UpdateStatusResponse(
        updater_available=available,
        auto_update_enabled=bool(state.get("auto_update_enabled", _auto_update_default())),
        profile=_fiestaboard_profile(),
        sidecar_url=_updater_url(),
        last_check=state.get("last_check"),
        last_update=state.get("last_update"),
    )


@app.post("/system/update", response_model=UpdateApplyResponse)
async def system_update_apply():
    """Trigger an in-place update via the fiestaupdater sidecar.
    
    The request returns 202 from the sidecar almost immediately; the actual
    container recreation happens shortly after, which will kill this process.
    Clients should expect their HTTP connection to drop and should poll
    `/health` to detect when the new version is up.
    
    If the sidecar is not running (user hasn't opted in), returns 503 with a
    `manual` mode response so the UI can fall back to instructions.
    """
    if not _updater_token():
        raise HTTPException(
            status_code=503,
            detail={
                "status": "manual",
                "mode": "manual",
                "hint": "FIESTAUPDATER_TOKEN is not set. Add COMPOSE_PROFILES=fiestaupdater to your .env and run 'docker compose up -d' to enable in-app updates.",
            },
        )

    url = f"{_updater_url()}/update"
    headers = {"Authorization": f"Bearer {_updater_token()}"}

    def _post():
        return requests.post(url, headers=headers, timeout=(5, 30))

    try:
        resp = await asyncio.to_thread(_post)
    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "manual",
                "mode": "manual",
                "hint": "Could not reach the fiestaupdater sidecar. Run 'docker compose pull && docker compose up -d' from your install directory to update manually.",
            },
        )
    except Exception as e:
        logger.warning(f"fiestaupdater update call failed: {e}")
        raise HTTPException(status_code=502, detail={"status": "error", "error": str(e)})

    if resp.status_code == 401:
        raise HTTPException(
            status_code=500,
            detail={"status": "error", "error": "fiestaupdater rejected our token; check FIESTAUPDATER_TOKEN matches in both services"},
        )
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={"status": "error", "error": f"fiestaupdater returned {resp.status_code}: {resp.text[:200]}"},
        )

    # Record bookkeeping so the UI can show "last update".
    body = {}
    try:
        body = resp.json()
    except ValueError as e:
        # fiestaupdater may return a non-JSON body (e.g. plain-text on error); fall back to empty dict.
        logger.debug("fiestaupdater response is not JSON, using empty body (non-fatal): %s", e)
    state = _system_update_state_load()
    state["last_update"] = datetime.now(timezone.utc).isoformat()
    _system_update_state_save(state)

    return UpdateApplyResponse(
        status="queued",
        mode="sidecar",
        previous_digest=body.get("previous_digest"),
    )


@app.post("/system/update/auto", response_model=AutoUpdateResponse)
async def system_update_set_auto(req: AutoUpdateRequest):
    """Enable or disable scheduled auto-updates.
    
    When enabled, the API process periodically checks for updates and, if a
    newer version is available, calls the sidecar to apply it.  The actual
    polling loop lives in the lifespan startup; this endpoint just persists
    the user's preference.
    """
    state = _system_update_state_load()
    state["auto_update_enabled"] = bool(req.enabled)
    _system_update_state_save(state)
    return AutoUpdateResponse(enabled=bool(req.enabled))


@app.get("/logs")
async def get_logs(
    limit: int = Query(default=50, ge=1, le=500, description="Number of log entries to return"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    level: Optional[str] = Query(default=None, description="Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"),
    search: Optional[str] = Query(default=None, description="Search in log message or logger name")
):
    """Get application logs with pagination, filtering, and search.
    
    Args:
        limit: Maximum number of log entries to return (default 50, max 500)
        offset: Number of entries to skip for pagination
        level: Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        search: Search text in log message or logger name
    
    Returns:
        List of log entries with pagination info
    """
    # Validate level if provided
    valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    if level and level.upper() not in valid_levels:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid log level: {level}. Valid levels: {valid_levels}"
        )
    
    logs, total, has_more = _read_logs_from_files(
        limit=limit,
        offset=offset,
        level=level,
        search=search
    )
    
    return {
        "logs": logs,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
        "filters": {
            "level": level.upper() if level else None,
            "search": search
        }
    }


@app.get("/status", response_model=StatusResponse)
async def get_status():
    """Get current service status."""
    service = get_service()
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    settings_service = get_settings_service()
    
    status = StatusResponse(
        running=_service_running,
        initialized=service is not None,
        config_summary=Config.get_summary()
    )
    # Add active page ID to config summary
    status.config_summary["active_page_id"] = settings_service.get_active_page_id()
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
                detail="Service initialization failed - check board configuration (API key, host, etc.)"
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
    if _service:
        _service.running = False
        _service_running = False
    
    return {"status": "stopped", "message": "Service stopped successfully"}


@app.post("/refresh")
async def refresh_display():
    """Manually trigger a display refresh."""
    service = get_service()
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        service.fetch_and_display()
        return {"status": "success", "message": "Display refreshed successfully"}
    except Exception as e:
        logger.error(f"Error refreshing display: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to refresh display: {str(e)}")


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
        ' ',  # 0
        'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J',  # 1–10
        'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T',  # 11–20
        'U', 'V', 'W', 'X', 'Y', 'Z',                        # 21–26
        '1', '2', '3', '4', '5', '6', '7', '8', '9', '0',   # 27–36
        '!', '@', '#', '$', '(', ')',                         # 37–42
        ' ',                                                   # 43 – undefined
        '-',                                                   # 44
        ' ',                                                   # 45 – undefined
        '+', '&', '=', ';', ':',                              # 46–50
        ' ',                                                   # 51 – undefined
        "'", '"', '%', ',', '.',                              # 52–56
        ' ', ' ',                                              # 57–58 – undefined
        '/', '?',                                              # 59–60
        ' ',                                                   # 61 – undefined
        '°',                                                   # 62
    ]

    lines = []
    for row in characters:
        chars = []
        for code in row:
            if 63 <= code <= 71:
                chars.append(f'{{{code}}}')
            elif 0 <= code < len(_LOOKUP):
                chars.append(_LOOKUP[code])
            else:
                chars.append(' ')
        lines.append(''.join(chars))
    return '\n'.join(lines)


@app.get("/board/current-message")
async def get_board_current_message():
    """Read the message currently displayed on the physical board.

    Calls the board API (Local or Cloud) to retrieve the live character grid
    and converts it to the standard message string format used by the UI.

    Returns:
        characters: Raw 2-D character code grid (list of lists of ints)
        message:    Message string suitable for rendering in BoardDisplay
        rows:       Number of rows in the grid
        cols:       Number of columns in the grid
    """
    service = get_service()
    if not service or not service.vb_client:
        raise HTTPException(status_code=503, detail="Board client not initialized")

    characters = await asyncio.to_thread(service.vb_client.read_current_message)

    if characters is None:
        raise HTTPException(status_code=503, detail="Failed to read current board message")

    message = _characters_to_message(characters)
    rows = len(characters)
    cols = len(characters[0]) if characters else 0

    return {
        "characters": characters,
        "message": message,
        "rows": rows,
        "cols": cols,
    }


@app.post("/send-message")
async def send_message(request: MessageRequest):
    """Send a custom message to the board."""
    service = get_service()
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    # CRITICAL: Block ALL manual sends during silence mode to prevent wake-ups
    if Config.is_silence_mode_active():
        logger.info("Silence mode is active - blocking manual message send to prevent wake-up")
        return {
            "status": "blocked",
            "message": "Manual sends blocked during silence mode to prevent wake-ups",
            "silence_mode": True
        }
    
    if not service.vb_client:
        raise HTTPException(status_code=503, detail="Board client not initialized")
    
    try:
        # Convert text to board array for proper character/color support
        board_array = text_to_board_array(request.text)
        settings_service = get_settings_service()
        transition = settings_service.get_transition_settings()
        
        success, was_sent = service.vb_client.send_characters(
            board_array,
            strategy=transition.strategy,
            step_interval_ms=transition.step_interval_ms,
            step_size=transition.step_size
        )
        if success:
            if was_sent:
                return {"status": "success", "message": "Message sent successfully"}
            else:
                return {"status": "success", "message": "Message unchanged, no update needed", "skipped": True}
        else:
            raise HTTPException(status_code=500, detail="Failed to send message")
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send message: {str(e)}")


@app.get("/config")
async def get_config():
    """Get current configuration summary (without sensitive keys)."""
    return Config.get_summary()


@app.post("/send-welcome-message")
async def send_welcome_message():
    """
    Send a colorful welcome message to the board.
    
    Used by the setup wizard to confirm the board is working.
    Sends "HIYA FROM FIESTABOARD" with colorful borders.
    
    Note: This creates a fresh BoardClient with current config values
    to ensure any recent config changes (e.g., from the setup wizard) are used.
    """
    from .board_client import BoardClient
    
    # Check silence mode
    if Config.is_silence_mode_active():
        logger.info("Silence mode is active - blocking welcome message to prevent wake-up")
        return {
            "status": "blocked",
            "message": "Welcome message blocked during silence mode",
            "silence_mode": True
        }
    
    # Create a fresh board client with current config values
    # This ensures any config changes from the setup wizard are used
    try:
        use_cloud = Config.BOARD_API_MODE.lower() == "cloud"
        board_client = BoardClient(
            api_key=Config.get_board_api_key(),
            host=Config.BOARD_HOST if not use_cloud else None,
            use_cloud=use_cloud,
            skip_unchanged=False  # Always send the welcome message
        )
    except ValueError as e:
        logger.error(f"Failed to create board client: {e}")
        raise HTTPException(status_code=503, detail=f"Board not configured: {str(e)}")
    
    try:
        # Use custom welcome message if set, otherwise use the default
        config_manager = get_config_manager()
        general = config_manager.get_general()
        custom_msg = general.get("welcome_message", "").strip()
        center_line = custom_msg.upper() if custom_msg else "HIYA FROM FIESTABOARD"

        # Colorful welcome template (matches pages.json welcome page)
        welcome_template = [
            "{{red}}{{red}}{{orange}}{{yellow}}{{orange}}{{red}}{{violet}}{{red}}{{orange}}{{yellow}}{{red}}{{orange}}{{violet}}{{yellow}}{{red}}{{orange}}{{red}}{{yellow}}{{violet}}{{orange}}{{red}}{{yellow}}",
            "{{orange}}{{yellow}}{{red}}{{violet}}{{yellow}}{{orange}}{{red}}{{yellow}}{{violet}}{{orange}}{{yellow}}{{red}}{{orange}}{{violet}}{{yellow}}{{orange}}{{red}}{{violet}}{{yellow}}{{red}}{{orange}}{{red}}",
            center_line,
            "{{violet}}{{orange}}{{yellow}}{{red}}{{orange}}{{violet}}{{yellow}}{{orange}}{{red}}{{yellow}}{{red}}{{violet}}{{orange}}{{yellow}}{{violet}}{{red}}{{orange}}{{yellow}}{{orange}}{{red}}{{violet}}{{orange}}",
            "{{red}}{{yellow}}{{orange}}{{violet}}{{red}}{{orange}}{{red}}{{violet}}{{yellow}}{{orange}}{{violet}}{{red}}{{yellow}}{{red}}{{orange}}{{violet}}{{yellow}}{{red}}{{violet}}{{orange}}{{yellow}}{{red}}",
            "{{orange}}{{violet}}{{red}}{{yellow}}{{violet}}{{red}}{{orange}}{{yellow}}{{red}}{{red}}{{orange}}{{yellow}}{{violet}}{{orange}}{{red}}{{yellow}}{{orange}}{{red}}{{yellow}}{{violet}}{{red}}{{orange}}"
        ]
        
        # Convert template to board array
        welcome_text = "\n".join(welcome_template)
        board_array = text_to_board_array(welcome_text)
        
        settings_service = get_settings_service()
        transition = settings_service.get_transition_settings()
        
        success, was_sent = board_client.send_characters(
            board_array,
            strategy=transition.strategy,
            step_interval_ms=transition.step_interval_ms,
            step_size=transition.step_size,
            force=True  # Force send even if cached
        )
        
        if success:
            if was_sent:
                logger.info("Welcome message sent to board")
                return {"status": "success", "message": "Welcome message sent to your board!"}
            else:
                return {"status": "success", "message": "Welcome message unchanged", "skipped": True}
        else:
            raise HTTPException(status_code=500, detail="Failed to send welcome message")
            
    except Exception as e:
        logger.error(f"Error sending welcome message: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send welcome message: {str(e)}")


# =============================================================================
# Configuration Management Endpoints
# =============================================================================

@app.get("/config/full")
async def get_full_config():
    """
    Get the full configuration with sensitive fields masked.
    
    Returns the complete config structure including all features and settings.
    API keys and passwords are masked with '***'.
    """
    config_manager = get_config_manager()
    return config_manager.get_all_masked()


@app.get("/config/board")
async def get_board_config():
    """Get board connection configuration (keys masked)."""
    config_manager = get_config_manager()
    board_config = config_manager.get_board()
    masked = config_manager._mask_sensitive(board_config)
    
    return {
        "config": masked,
        "api_modes": ["local", "cloud"]
    }


# Deprecated backward compatibility endpoint - redirects to /config/board
async def get_board_config_compat(response: Response):
    """Deprecated: Use /config/board instead."""
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</config/board>; rel="successor-version"'
    return await get_board_config()


@app.put("/config/board")
async def update_board_config(request: dict):
    """
    Update board configuration.
    
    Example body:
    {
        "api_mode": "local",
        "local_api_key": "your-key",
        "host": "192.168.1.100"
    }
    """
    config_manager = get_config_manager()
    
    # Update board config
    config_manager.set_board(request)
    
    # Reload config in the Config class
    Config.reload()
    
    # Reinitialize the board client with new config
    service = get_service()
    if service:
        service.reinitialize_board_client()
    
    # Get updated config (masked)
    updated = config_manager.get_board()
    masked = config_manager._mask_sensitive(updated)
    
    return {
        "status": "success",
        "config": masked
    }


# Deprecated backward compatibility endpoint - redirects to /config/board
async def update_board_config_compat(request: dict, response: Response):
    """Deprecated: Use /config/board instead."""
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</config/board>; rel="successor-version"'
    return await update_board_config(request)


@app.delete("/config/board")
async def reset_board_config():
    """
    Reset board configuration to defaults (first-run / wizard mode).

    Clears all board credentials and connection settings without re-applying
    environment-variable defaults.  This puts the backend into first-run mode
    so that ``GET /config/validate`` returns ``is_first_run: true`` even when
    ``BOARD_HOST`` / ``BOARD_LOCAL_API_KEY`` env vars are present.

    Also resets the multi-board settings service boards to a single default
    unconfigured board so that both the legacy config path and the new settings
    service path agree that no board is configured.

    Primarily used by integration-test helpers to set up wizard test scenarios.
    """
    config_manager = get_config_manager()
    config_manager.reset_board_config()

    # Also reset the multi-board settings so that validate_config() correctly
    # detects first-run mode regardless of which storage path is checked.
    try:
        from .devices import BoardInstance
        settings_svc = get_settings_service()
        settings_svc.set_boards([BoardInstance(
            name="My Board",
            device_type="flagship",
            board_color="black",
            enabled=True,
            api_mode="local",
            host="",
            local_api_key="",
            cloud_key="",
        ).to_dict()])
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to reset multi-board settings during board config reset")

    # Reinitialize the board client (will be unconfigured)
    service = get_service()
    if service:
        service.reinitialize_board_client()

    return {"status": "reset", "message": "Board config cleared; backend is in first-run mode"}


@app.get("/config/validate")
async def validate_config():
    """
    Validate the current configuration.

    Returns validation status, first-run detection, and any errors found.
    Used by the setup wizard to determine if onboarding is needed.

    A board is considered configured when either the legacy single-board
    config has the required credentials, or any board instance configured
    via the multi-board settings service has connection credentials. This
    ensures users who set up a board through Settings (rather than the
    wizard) are not treated as first-run.
    """
    config_manager = get_config_manager()
    is_valid, errors = config_manager.validate()

    # Get board config to check first-run state
    board_config = config_manager.get_board()
    api_mode = board_config.get("api_mode", "local")

    # Detect first-run: no API key configured for the selected mode
    is_first_run = False
    missing_fields = []

    if api_mode == "cloud":
        if not board_config.get("cloud_key"):
            is_first_run = True
            missing_fields.append("board.cloud_key")
    else:  # local mode
        if not board_config.get("local_api_key"):
            is_first_run = True
            missing_fields.append("board.local_api_key")
        if not board_config.get("host"):
            is_first_run = True
            missing_fields.append("board.host")

    # Also consider boards configured via the multi-board settings service.
    # If any configured board instance has connection credentials, the user
    # has completed setup (e.g. via Settings) and should not be treated as
    # first-run. Board-related validation errors/missing_fields from the
    # legacy config are dropped in that case.
    has_configured_board_instance = False
    try:
        from .devices import BoardInstance
        board_settings = get_settings_service().get_board_settings()
        for b in board_settings.boards or []:
            try:
                instance = BoardInstance.from_dict(b)
            except Exception:  # pragma: no cover - defensive
                continue
            if instance.is_connection_configured:
                has_configured_board_instance = True
                break
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to inspect multi-board settings during validate_config")

    if has_configured_board_instance:
        is_first_run = False
        missing_fields = [f for f in missing_fields if not f.startswith("board.")]
        board_error_prefixes = ("Board cloud_key", "Board local_api_key", "Board host")
        errors = [e for e in errors if not e.startswith(board_error_prefixes)]
        is_valid = len(errors) == 0

    return {
        "valid": is_valid,
        "is_first_run": is_first_run,
        "errors": errors,
        "missing_fields": missing_fields
    }


class BoardTestRequest(BaseModel):
    """Request model for testing board connection."""
    api_mode: str = "local"
    local_api_key: Optional[str] = None
    cloud_key: Optional[str] = None
    host: Optional[str] = None


@app.post("/config/board/test")
async def test_board_connection(request: BoardTestRequest):
    """
    Test board connection with provided credentials without saving.
    
    Used by the setup wizard to validate credentials before saving.
    
    Example body for Local API:
    {
        "api_mode": "local",
        "local_api_key": "your-local-api-key",
        "host": "192.168.1.100"
    }
    
    Example body for Cloud API:
    {
        "api_mode": "cloud",
        "cloud_key": "your-read-write-key"
    }
    
    Returns:
        success: Whether the connection test passed
        message: Human-readable status message
        error: Detailed error message if failed
    """
    from .board_client import BoardClient, is_successful_board_read_response

    api_mode = request.api_mode.lower()
    
    # Validate required fields based on mode
    if api_mode == "cloud":
        if not request.cloud_key:
            return {
                "success": False,
                "message": "Cloud API key is required",
                "error": "Missing cloud_key parameter"
            }
        api_key = request.cloud_key
        use_cloud = True
        host = None
    else:  # local mode
        if not request.local_api_key:
            return {
                "success": False,
                "message": "Local API key is required",
                "error": "Missing local_api_key parameter"
            }
        if not request.host:
            return {
                "success": False,
                "message": "Board host/IP is required for Local API",
                "error": "Missing host parameter"
            }
        api_key = request.local_api_key
        use_cloud = False
        host = request.host
        try:
            _validate_board_host(host)
        except HTTPException as _exc:
            return {
                "success": False,
                "message": "Invalid board host",
                "error": _exc.detail,
            }

    try:
        # Create temporary client with provided credentials
        client = BoardClient(
            api_key=api_key,
            host=host,
            use_cloud=use_cloud,
            skip_unchanged=False
        )
        
        # Test the connection directly so we can inspect HTTP status codes
        # (read_current_message() swallows errors and returns None, losing details)
        response = await asyncio.to_thread(
            requests.get, client.base_url, headers=client.headers, timeout=10
        )
        
        if response.status_code == 200:
            # Parse the response to verify it's valid board data
            try:
                data = response.json()
                if is_successful_board_read_response(data):
                    logger.info(f"Board connection test successful ({api_mode} mode)")
                    return {
                        "success": True,
                        "message": "Successfully connected to your board!",
                        "api_mode": api_mode,
                    }
                detail = (
                    f"JSON keys: {', '.join(sorted(data))}"
                    if isinstance(data, dict)
                    else f"body type: {type(data).__name__}"
                )
                logger.warning(
                    f"Board connection test: HTTP 200 but unrecognized response ({api_mode} mode): {detail}"
                )
                return {
                    "success": False,
                    "message": "Connected to Vestaboard but the response shape was not recognized.",
                    "error": f"Unrecognized read response ({detail}).",
                    "troubleshooting": [
                        "Update FiestaBoard to the latest version.",
                        "If this persists, file an issue with the response keys shown above (no API keys).",
                    ],
                }
            except ValueError:
                logger.warning(f"Board connection test: HTTP 200 but invalid JSON ({api_mode} mode)")
                return {
                    "success": False,
                    "message": "Connected to the board but the response could not be read. The board may be starting up.",
                    "error": "Invalid JSON response",
                    "troubleshooting": [
                        "Wait 30 seconds and try again — the board may still be starting up.",
                        "Try unplugging the board for 10 seconds and plugging it back in.",
                    ]
                }
        
        elif response.status_code == 401 or response.status_code == 403:
            logger.warning(f"Board connection test: auth rejected HTTP {response.status_code} ({api_mode} mode)")
            if use_cloud:
                return {
                    "success": False,
                    "message": f"Your API key was rejected by the Vestaboard cloud service (HTTP {response.status_code}).",
                    "error": f"HTTP {response.status_code}",
                    "troubleshooting": [
                        "Go to https://web.vestaboard.com and sign in to your account.",
                        "Make sure you are copying the Read/Write API key (not the subscription key or installable key).",
                        "Paste the key into the Cloud API Key field and try again.",
                    ]
                }
            else:
                return {
                    "success": False,
                    "message": f"Your API key was rejected by the board (HTTP {response.status_code}).",
                    "error": f"HTTP {response.status_code}",
                    "troubleshooting": [
                        "Verify your Local API key is correct — it was provided when you enabled the Local API with your enablement token.",
                        "If you need a new key, request an enablement token at https://www.vestaboard.com/local-api",
                        "Paste the correct key into the Local API Key field and try again.",
                        "If the key was recently regenerated, the old key will no longer work.",
                    ]
                }
        
        elif response.status_code >= 500:
            logger.warning(f"Board connection test: server error HTTP {response.status_code} ({api_mode} mode)")
            return {
                "success": False,
                "message": f"The board returned an error (HTTP {response.status_code}). It may be temporarily unavailable.",
                "error": f"HTTP {response.status_code}",
                "troubleshooting": [
                    "Try unplugging the Vestaboard for 10 seconds and plugging it back in.",
                    "Wait about a minute for the board to restart, then try again.",
                    "If the problem continues, check for firmware updates in the Vestaboard app.",
                ]
            }
        
        else:
            logger.warning(f"Board connection test: unexpected HTTP {response.status_code} ({api_mode} mode)")
            return {
                "success": False,
                "message": f"Received an unexpected response from the board (HTTP {response.status_code}).",
                "error": f"HTTP {response.status_code}",
                "troubleshooting": [
                    "Try unplugging the Vestaboard for 10 seconds and plugging it back in.",
                    "Check for firmware updates in the Vestaboard app.",
                    "If the problem continues, try using the other connection mode (Local or Cloud).",
                ]
            }
            
    except ValueError as e:
        # Invalid configuration (missing required fields)
        logger.warning("Board connection test failed - invalid config", exc_info=True)
        return {
            "success": False,
            "message": "Board connection configuration is invalid.",
            "error": "Configuration error"
        }
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Board connection test error: {e}")
        if use_cloud:
            return {
                "success": False,
                "message": "Could not connect to the Vestaboard cloud service.",
                "error": "Connection error",
                "troubleshooting": [
                    "Make sure the device running FiestaBoard has a working internet connection.",
                    "Try opening https://rw.vestaboard.com in a browser to verify the service is reachable.",
                    "If you use a VPN or corporate network, make sure it allows connections to rw.vestaboard.com.",
                ]
            }
        else:
            return {
                "success": False,
                "message": "Could not connect to the board. The board may be off or not on the same network.",
                "error": "Connection error",
                "troubleshooting": [
                    "Make sure the Vestaboard is powered on (check for the LED on the back).",
                    "Make sure both FiestaBoard and the Vestaboard are on the same Wi-Fi network.",
                    "Double-check the board's IP address — you can find it on your router's admin page or use FiestaBoard's network scan.",
                    "Make sure the Local API is enabled on your board (see https://docs.vestaboard.com/docs/local-api/authentication).",
                ]
            }
    except requests.exceptions.Timeout as e:
        logger.error(f"Board connection test timeout: {e}")
        if use_cloud:
            return {
                "success": False,
                "message": "Connection to the Vestaboard cloud service timed out.",
                "error": "Timeout",
                "troubleshooting": [
                    "Check that the device running FiestaBoard has a stable internet connection.",
                    "The Vestaboard cloud service may be experiencing issues — try again in a few minutes.",
                ]
            }
        else:
            return {
                "success": False,
                "message": "Connection to the board timed out. The board may be off or the IP address may be wrong.",
                "error": "Timeout",
                "troubleshooting": [
                    "Make sure the Vestaboard is powered on.",
                    "Double-check the IP address in the Vestaboard app under Settings.",
                    "Make sure both devices are on the same network.",
                    "Try using the board's IP address instead of a hostname.",
                ]
            }
    except Exception as e:
        logger.error(f"Board connection test error: {e}", exc_info=True)
        return {
            "success": False,
            "message": "Connection failed",
            "error": "Unexpected error",
            "troubleshooting": [
                "Make sure the Vestaboard is powered on and connected to your network.",
                "Try restarting FiestaBoard and the Vestaboard.",
                "Visit the Network Diagnostics page for a detailed connection check.",
            ]
        }


class EnablementTokenRequest(BaseModel):
    """Request model for exchanging enablement token for API key."""
    host: str
    enablement_token: str


class BoardScanRequest(BaseModel):
    """Request model for network board scanning."""
    timeout: Optional[float] = 4.0


@app.post("/config/board/enable-local-api")
async def enable_local_api(request: EnablementTokenRequest):
    """
    Exchange a Local API Enablement Token for a Local API Key.
    
    Users must email board support to receive an enablement token.
    This endpoint POSTs to the board to exchange it for the actual API key.
    
    Example body:
    {
        "host": "192.168.1.100",
        "enablement_token": "your-enablement-token-from-support"
    }
    
    Returns:
        success: Whether the exchange was successful
        api_key: The local API key (if successful)
        message: Human-readable status message
    """
    import requests as http_requests
    
    if not request.host:
        return {
            "success": False,
            "message": "Board IP address is required",
            "error": "Missing host parameter"
        }
    
    if not request.enablement_token:
        return {
            "success": False,
            "message": "Enablement token is required",
            "error": "Missing enablement_token parameter"
        }
    
    # Validate the host before composing the URL so an attacker can't
    # redirect this request away from the local board (SSRF).
    try:
        _validate_board_host(request.host)
        _validate_board_host_is_local_network(request.host)
    except HTTPException as exc:
        return {
            "success": False,
            "message": "Invalid board host",
            "error": exc.detail,
        }

    # Re-derive the host from a regex match so the downstream HTTP call is
    # not tracked as tainted by static-analysis tools (py/full-ssrf).
    # _validate_board_host already confirmed it is a bare IPv4 or hostname,
    # so the fullmatch is guaranteed to succeed.
    _hm = re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.\-]{0,252}", request.host)
    if not _hm:
        return {
            "success": False,
            "message": "Invalid board host",
            "error": "Host format rejected after validation",
        }
    _safe_host = _hm.group(0)
    # Build the URL for the local enablement endpoint
    url = f"http://{_safe_host}:7000/local-api/enablement"
    headers = {
        "X-Vestaboard-Local-Api-Enablement-Token": request.enablement_token
    }
    
    try:
        logger.info(f"Attempting to enable local API on {request.host}")
        response = http_requests.post(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            api_key = data.get("apiKey")
            
            if api_key:
                logger.info(f"Successfully enabled local API on {request.host}")
                return {
                    "success": True,
                    "api_key": api_key,
                    "message": "Local API enabled successfully! Your API key has been retrieved."
                }
            else:
                logger.warning(f"Local API enablement response missing apiKey: {data}")
                return {
                    "success": False,
                    "message": "Received response but no API key was provided",
                    "error": "Board response did not include an apiKey",
                }
        elif response.status_code == 401 or response.status_code == 403:
            logger.warning(f"Local API enablement failed - invalid token")
            return {
                "success": False,
                "message": "Invalid enablement token. Please check the token and try again.",
                "error": f"HTTP {response.status_code}: Unauthorized"
            }
        else:
            logger.warning(f"Local API enablement failed - HTTP {response.status_code}")
            return {
                "success": False,
                "message": f"Board returned an error (HTTP {response.status_code})",
                "error": f"HTTP {response.status_code}",
            }
            
    except http_requests.exceptions.ConnectionError as e:
        logger.error(f"Local API enablement connection error: {e}")
        return {
            "success": False,
            "message": "Could not connect to board. Please check the IP address and ensure the board is on the same network.",
            "error": "Connection error",
        }
    except http_requests.exceptions.Timeout as e:
        logger.error(f"Local API enablement timeout: {e}")
        return {
            "success": False,
            "message": "Connection timed out. Please check the IP address and try again.",
            "error": "Timeout",
        }
    except Exception as e:
        logger.error(f"Local API enablement error: {e}", exc_info=True)
        return {
            "success": False,
            "message": "Failed to enable local API",
            "error": "Unexpected error",
        }


@app.post("/config/board/scan")
async def scan_for_boards(request: BoardScanRequest = BoardScanRequest()):
    """
    Scan the local network for Vestaboard devices.

    Uses mDNS service browsing and subnet port probing (port 7000) to
    discover boards automatically so users don't have to enter an IP.

    Optional body:
    {
        "timeout": 4.0  // scan duration in seconds (default 4, max 15)
    }

    Returns:
        boards: list of discovered devices with ip, port, hostname, source
    """
    from src.system.mdns import scan_for_boards as _scan

    timeout = min(max(float(request.timeout or 4.0), 1.0), 15.0)

    boards = _scan(timeout=timeout)
    return {"boards": boards}


@app.get("/config/general")
async def get_general_config():
    """Get general configuration (timezone, refresh interval, etc.)."""
    config_manager = get_config_manager()
    return config_manager.get_general()


@app.put("/config/general")
async def update_general_config(request: dict):
    """
    Update general configuration.
    
    Body can include:
    - timezone: IANA timezone name (e.g., "America/Los_Angeles")
    - refresh_interval_seconds: Refresh interval in seconds
    - output_target: Output target ("ui", "board", or "both")
    - instance_name: Friendly name for this FiestaBoard install
    - time_format: "12h" or "24h" for web UI time display
    - date_format: "MM/DD/YYYY", "DD/MM/YYYY", or "YYYY-MM-DD"
    - welcome_message: Custom board greeting (empty = use default)
    """
    config_manager = get_config_manager()
    
    # Get current general config
    general_config = config_manager.get_general()
    
    # Update with provided values
    if "timezone" in request:
        general_config["timezone"] = request["timezone"]
    if "refresh_interval_seconds" in request:
        general_config["refresh_interval_seconds"] = request["refresh_interval_seconds"]
    if "output_target" in request:
        general_config["output_target"] = request["output_target"]
    if "instance_name" in request:
        general_config["instance_name"] = request["instance_name"]
    if "time_format" in request:
        general_config["time_format"] = request["time_format"]
    if "date_format" in request:
        general_config["date_format"] = request["date_format"]
    if "welcome_message" in request:
        general_config["welcome_message"] = request["welcome_message"]
    
    # Save back
    success = config_manager.set_general(general_config)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update general configuration")
    
    return {
        "status": "success",
        "general": general_config
    }


@app.get("/silence-status")
async def get_silence_status():
    """
    Get current silence mode status with UTC times.
    
    Returns:
    - enabled: Whether silence schedule is enabled
    - active: Whether silence mode is currently active
    - start_time_utc: Start time in UTC ISO format
    - end_time_utc: End time in UTC ISO format
    - current_time_utc: Current UTC time
    - next_change_utc: Time of next status change
    """
    from .time_service import get_time_service
    
    time_service = get_time_service()
    config_manager = get_config_manager()
    
    # Trigger migration if needed
    config_manager.migrate_silence_schedule_to_utc()
    
    silence_config = config_manager.get_feature("silence_schedule")
    enabled = silence_config.get("enabled", False)
    start_time = silence_config.get("start_time", "20:00+00:00")
    end_time = silence_config.get("end_time", "07:00+00:00")
    
    # Check if currently active
    active = False
    if enabled:
        active = time_service.is_time_in_window(start_time, end_time)
    
    # Get current UTC time
    current_utc = time_service.get_current_utc()
    current_time_utc = current_utc.strftime("%H:%M+00:00")
    
    # Determine next change time (simplified - just return start or end)
    next_change_utc = end_time if active else start_time
    
    return {
        "enabled": enabled,
        "active": active,
        "start_time_utc": start_time,
        "end_time_utc": end_time,
        "current_time_utc": current_time_utc,
        "next_change_utc": next_change_utc
    }


class SilenceScheduleRequest(BaseModel):
    """Request body for updating the silence schedule feature."""
    enabled: bool
    start_time: str
    end_time: str


@app.put("/settings/silence-schedule")
async def update_silence_schedule(request: SilenceScheduleRequest):
    """
    Update the silence schedule configuration.

    `silence_schedule` is a system feature (not a plugin). Times must be in
    UTC ISO format (e.g. "04:00+00:00"); the UI converts local time to UTC
    before calling this endpoint.
    """
    config_manager = get_config_manager()

    updated = {
        "enabled": request.enabled,
        "start_time": request.start_time,
        "end_time": request.end_time,
    }

    success = config_manager.set_feature("silence_schedule", updated)
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to persist silence schedule configuration",
        )

    logger.info(
        "Silence schedule updated: enabled=%s, start=%s, end=%s",
        request.enabled,
        request.start_time,
        request.end_time,
    )

    return {
        "status": "success",
        "config": config_manager.get_feature("silence_schedule") or updated,
    }


# =============================================================================
# Display Source Endpoints
# =============================================================================

@app.get("/displays")
async def list_displays():
    """
    List all available display types and their status.
    
    Returns information about each display source including whether
    it's currently available/configured.
    """
    display_service = get_display_service()
    displays = display_service.get_available_displays()
    return {
        "displays": displays,
        "total": len(displays),
        "available_count": sum(1 for d in displays if d["available"])
    }


@app.get("/displays/{display_type}")
async def get_display(display_type: str):
    """
    Get formatted output for a specific display type.
    
    Args:
        display_type: One of: weather, datetime, weather_datetime, 
                      home_assistant, star_trek, guest_wifi
    
    Returns:
        Formatted message text ready for display on board.
    """
    display_service = get_display_service()
    result = display_service.get_display(display_type)
    
    # Check for invalid display type (will have error message about valid types)
    if not result.available and result.error and "Unknown display type" in result.error:
        raise HTTPException(status_code=400, detail=result.error)
    
    if not result.available and result.error:
        raise HTTPException(status_code=503, detail=result.error)
    
    return {
        "display_type": result.display_type,
        "message": result.formatted,
        "lines": result.formatted.split('\n') if result.formatted else [],
        "line_count": len(result.formatted.split('\n')) if result.formatted else 0,
        "available": result.available
    }


# Deprecated: use /plugins/{plugin_id}/data instead
@app.get("/displays/{display_type}/raw")
async def get_display_raw(display_type: str, response: Response):
    """
    Deprecated: Use /plugins/{plugin_id}/data instead.

    Get raw data from a display source (before formatting).
    
    This is useful for debugging or building custom displays.
    
    Args:
        display_type: Plugin ID (e.g., weather, datetime, stocks)
    
    Returns:
        Raw data dictionary from the source.
    """
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = f'</plugins/{display_type}/data>; rel="successor-version"'
    
    display_service = get_display_service()
    result = display_service.get_display(display_type)
    
    if not result.available and result.error:
        raise HTTPException(status_code=503, detail=result.error)
    
    return {
        "display_type": result.display_type,
        "data": result.raw,
        "available": result.available,
        "error": result.error
    }


@app.post("/displays/raw/batch")
async def get_displays_raw_batch(request: dict):
    """
    Get raw data from multiple display sources in one request.
    
    This is useful for efficiently fetching data for multiple plugins
    without making individual requests.
    
    Request body:
        {
            "display_types": ["baywheels", "muni", "weather", "stocks"],
            "enabled_only": true  // Optional, only fetch enabled plugins
        }
    
    Returns:
        {
            "displays": {
                "baywheels": {
                    "data": {...},
                    "available": true,
                    "error": null
                },
                ...
            },
            "total": 4,
            "successful": 3
        }
    """
    display_types = request.get("display_types", [])
    enabled_only = request.get("enabled_only", True)
    
    if not display_types:
        raise HTTPException(status_code=400, detail="display_types parameter required")
    
    if not isinstance(display_types, list):
        raise HTTPException(status_code=400, detail="display_types must be a list")
    
    display_service = get_display_service()
    results = {}
    
    for display_type in display_types:
        try:
            result = display_service.get_display(display_type)
            
            # Skip if enabled_only is true and plugin is not available
            if enabled_only and not result.available:
                continue
            
            results[display_type] = {
                "data": result.raw,
                "available": result.available,
                "error": result.error
            }
        except Exception as e:
            logger.error(f"Error fetching display {display_type}: {e}", exc_info=True)
            results[display_type] = {
                "data": {},
                "available": False,
                "error": str(e)
            }
    
    return {
        "displays": results,
        "total": len(display_types),
        "successful": sum(1 for r in results.values() if r.get("available", False))
    }


@app.post("/displays/{display_type}/send")
async def send_display(
    display_type: str,
    target: Optional[str] = None
):
    """
    Send a display to the configured target (ui, board, or both).
    
    Args:
        display_type: The display type to send
        target: Override output target (ui, board, both). If not provided,
                uses the configured default.
    
    Returns:
        Result of the send operation.
    """
    if target is not None and target not in VALID_OUTPUT_TARGETS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid target: {target}. Valid targets: {VALID_OUTPUT_TARGETS}"
        )
    
    display_service = get_display_service()
    settings_service = get_settings_service()
    service = get_service()
    
    if not service or not service.vb_client:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    # Get the display content (validates display_type against plugin registry)
    result = display_service.get_display(display_type)
    
    # Check for invalid display type
    if not result.available and result.error and "Unknown display type" in result.error:
        raise HTTPException(status_code=400, detail=result.error)
    
    if not result.available:
        raise HTTPException(status_code=503, detail=result.error or "Display not available")
    
    # Determine target
    if target is None:
        send_to_board = settings_service.should_send_to_board()
    else:
        send_to_board = target in ["board", "both"]
    
    sent_to_board = False
    if send_to_board:
        transition = settings_service.get_transition_settings()
        # Use first board's device type for dimensions (flagship vs note)
        board_settings = settings_service.get_board_settings()
        device_type = "flagship"
        if board_settings.boards:
            device_type = board_settings.boards[0].get("device_type", "flagship")
        dims = get_dimensions(device_type)
        board_array = text_to_board_array(result.formatted, rows=dims.rows, cols=dims.cols)
        success, was_sent = service.vb_client.send_characters(
            board_array,
            strategy=transition.strategy,
            step_interval_ms=transition.step_interval_ms,
            step_size=transition.step_size
        )
        sent_to_board = was_sent
        if not success:
            raise HTTPException(status_code=500, detail="Failed to send to board")
    
    return {
        "status": "success",
        "display_type": display_type,
        "message": result.formatted,
        "sent_to_board": sent_to_board,
        "target": target or settings_service.get_output_settings().target,
    }


# =============================================================================
# Bay Wheels Station Search Endpoints
# =============================================================================

@app.get("/baywheels/stations")
async def list_all_baywheels_stations():
    """
    List all Bay Wheels stations with current status.
    
    Returns all stations from the GBFS feed with their current bike availability.
    """
    from src.utils.baywheels import BayWheelsSource, STATION_STATUS_URL
    import requests
    
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
            
            result.append({
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
            })
        
        return {
            "stations": result,
            "total": len(result)
        }
    except Exception as e:
        logger.error(f"Error listing Bay Wheels stations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/baywheels/stations/nearby")
async def find_nearby_baywheels_stations(
    lat: float = Query(..., description="Latitude"),
    lng: float = Query(..., description="Longitude"),
    radius: float = Query(2.0, description="Search radius in kilometers"),
    limit: int = Query(10, description="Maximum number of results")
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
    from src.utils.baywheels import BayWheelsSource, STATION_STATUS_URL
    import requests
    
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
            "radius_km": radius
        }
    except Exception as e:
        logger.error(f"Error finding nearby Bay Wheels stations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/baywheels/stations/search")
async def search_baywheels_stations_by_address(
    address: str = Query(..., description="Address to search near"),
    radius: float = Query(2.0, description="Search radius in kilometers"),
    limit: int = Query(10, description="Maximum number of results")
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
    from src.utils.baywheels import BayWheelsSource, STATION_STATUS_URL
    import requests
    
    try:
        # Geocode address using Nominatim
        geocode_url = "https://nominatim.openstreetmap.org/search"
        geocode_params = {
            "q": address,
            "format": "json",
            "limit": 1
        }
        geocode_headers = {
            "User-Agent": "FiestaBoard-Service/1.0"
        }
        
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
            "radius_km": radius
        }
    except HTTPException:
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"Error geocoding address: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail=f"Geocoding service unavailable: {str(e)}")
    except Exception as e:
        logger.error(f"Error searching Bay Wheels stations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Queue-Times (Disney Parks) proxy for settings picker
# =============================================================================

QUEUE_TIMES_BASE = "https://queue-times.com"
QUEUE_TIMES_CACHE: Dict[str, Any] = {}
QUEUE_TIMES_CACHE_TIME: Dict[str, float] = {}
QUEUE_TIMES_CACHE_TTL = 10 * 60  # 10 minutes
DISNEY_GROUP_ID = 2  # Walt Disney Attractions


def _queue_times_get(path: str) -> Any:
    """Fetch from queue-times.com with simple in-memory cache."""
    now = time.time()
    if path in QUEUE_TIMES_CACHE and (now - QUEUE_TIMES_CACHE_TIME.get(path, 0)) < QUEUE_TIMES_CACHE_TTL:
        return QUEUE_TIMES_CACHE[path]
    url = f"{QUEUE_TIMES_BASE}{path}"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        QUEUE_TIMES_CACHE[path] = data
        QUEUE_TIMES_CACHE_TIME[path] = now
        return data
    except Exception as e:
        logger.warning(f"Queue-Times fetch failed for {path}: {e}")
        if path in QUEUE_TIMES_CACHE:
            return QUEUE_TIMES_CACHE[path]
        raise


@app.get("/queue-times/parks")
async def list_disney_parks():
    """
    List Disney parks for the settings picker (user-friendly names).
    Returns parks from Walt Disney Attractions group only.
    """
    try:
        data = await asyncio.to_thread(_queue_times_get, "/parks.json")
        for group in data:
            if group.get("id") == DISNEY_GROUP_ID:
                parks = group.get("parks", [])
                out = [{"id": p["id"], "name": p["name"], "country": p.get("country"), "timezone": p.get("timezone")} for p in parks]
                out.sort(key=lambda x: (x.get("name") or "").lower())
                return out
        return []
    except Exception as e:
        logger.error(f"Error listing Disney parks: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail="Failed to fetch parks from Queue-Times")


@app.get("/queue-times/parks/{park_id}/rides")
async def list_park_rides(park_id: int):
    """
    List rides for a park for the settings picker (user-friendly names).
    Returns id and name for each ride from the park's queue_times.
    """
    try:
        data = await asyncio.to_thread(_queue_times_get, f"/parks/{park_id}/queue_times.json")
        rides = []
        for land in data.get("lands", []):
            for ride in land.get("rides", []):
                rides.append({"id": ride["id"], "name": ride["name"]})
        rides.sort(key=lambda x: (x.get("name") or "").lower())
        return rides
    except Exception as e:
        logger.error(f"Error listing rides for park {park_id}: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail="Failed to fetch rides from Queue-Times")


# =============================================================================
# MUNI Endpoints
# =============================================================================

@app.get("/muni/stops")
async def list_all_muni_stops():
    """
    List all SF Muni stops with metadata.
    
    Returns all stops from the 511.org transit API with cached data (24hr TTL).
    """
    import requests
    import time
    
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
        # We'll use the configured MUNI API key
        from src.config import Config
        api_key = Config.MUNI_API_KEY
        
        if not api_key:
            raise HTTPException(status_code=400, detail="MUNI API key not configured")
        
        url = "http://api.511.org/transit/stops"
        params = {
            "api_key": api_key,
            "operator_id": "SF",
            "format": "json"
        }
        
        response = await asyncio.to_thread(requests.get, url, params=params, timeout=15)
        response.raise_for_status()
        
        # Handle BOM if present
        content = response.text
        if content.startswith('\ufeff'):
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
            
            stops.append({
                "stop_code": stop_code,
                "stop_id": stop_id,
                "name": name,
                "lat": float(lat) if lat else None,
                "lon": float(lon) if lon else None,
            })
        
        result = {
            "stops": stops,
            "total": len(stops)
        }
        
        # Update cache
        with _muni_stops_cache_lock:
            _muni_stops_cache = result
            _muni_stops_cache_time = current_time
        
        return result
        
    except Exception as e:
        logger.error(f"Error listing Muni stops: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/muni/stops/nearby")
async def find_nearby_muni_stops(
    lat: float = Query(..., description="Latitude"),
    lng: float = Query(..., description="Longitude"),
    radius: float = Query(0.5, description="Search radius in kilometers"),
    limit: int = Query(10, description="Maximum number of results")
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
            
            a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
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
                        
                        stop["routes"] = sorted(list(routes))
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
            "radius_km": radius
        }
        
    except Exception as e:
        logger.error(f"Error finding nearby Muni stops: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/muni/stops/search")
async def search_muni_stops_by_address(
    address: str = Query(..., description="Address to search near"),
    radius: float = Query(0.5, description="Search radius in kilometers"),
    limit: int = Query(10, description="Maximum number of results")
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
        geocode_params = {
            "q": address,
            "format": "json",
            "limit": 1
        }
        geocode_headers = {
            "User-Agent": "FiestaBoard-Service/1.0"
        }
        
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
            "radius_km": radius
        }
        
    except HTTPException:
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"Error geocoding address: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail=f"Geocoding service unavailable: {str(e)}")
    except Exception as e:
        logger.error(f"Error searching Muni stops: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Stocks Endpoints
# =============================================================================

@app.get("/stocks/search")
async def search_stock_symbols(
    query: str = Query(..., description="Search query (symbol or company name)"),
    limit: int = Query(10, ge=1, le=50, description="Maximum number of results")
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
        from src.config import Config
        
        # Get Finnhub API key if configured
        finnhub_api_key = Config.FINNHUB_API_KEY if Config.FINNHUB_API_KEY else None
        
        results = StocksSource.search_symbols(
            query=query,
            limit=limit,
            finnhub_api_key=finnhub_api_key
        )
        
        return {
            "symbols": results,
            "count": len(results),
            "query": query
        }
    except Exception as e:
        logger.error(f"Error searching stock symbols: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail="Failed to validate stock symbol")


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
        geocode_params = {
            "q": address,
            "format": "json",
            "limit": 1
        }
        geocode_headers = {
            "User-Agent": "FiestaBoard-Service/1.0"
        }
        
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
            "formatted_address": location.get("display_name", address)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error geocoding address: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
    from src.config import Config
    
    origin = request.get("origin")
    destination = request.get("destination")
    destination_name = request.get("destination_name", "DESTINATION")
    
    if not origin or not destination:
        raise HTTPException(status_code=400, detail="origin and destination required")
    
    # Get API key from config
    api_key = getattr(Config, 'GOOGLE_ROUTES_API_KEY', None)
    if not api_key:
        raise HTTPException(status_code=400, detail="Google Routes API key not configured")
    
    try:
        # Create a temporary TrafficSource to test the route
        # Pass as a list of routes (expected format)
        routes = [{
            "origin": origin,
            "destination": destination,
            "destination_name": destination_name,
            "travel_mode": request.get("travel_mode", "DRIVE")
        }]
        
        traffic_source = TrafficSource(
            api_key=api_key,
            routes=routes
        )
        
        # Fetch traffic data to validate (blocking HTTP call - run in thread pool)
        data = await asyncio.to_thread(traffic_source.fetch_traffic_data)
        
        if not data:
            return {
                "valid": False,
                "error": "Failed to validate route. This could be due to: 1) Invalid addresses, 2) Google Routes API not enabled, 3) API key issues. Check the API logs for details."
            }
        
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
            "destination_coords": destination_coords
        }
        
    except Exception as e:
        logger.error(f"Error validating traffic route: {e}", exc_info=True)
        return {
            "valid": False,
            "error": "Failed to validate route"
        }


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
        "available_strategies": VALID_STRATEGIES
    }


@app.put("/settings/transitions")
async def update_transition_settings(request: dict):
    """
    Update transition animation settings.
    
    Body can include:
    - strategy: One of column, reverse-column, edges-to-center, row, diagonal, random, or null
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
            strategy=strategy,
            step_interval_ms=step_interval_ms,
            step_size=step_size
        )
        
        return {
            "status": "success",
            "settings": transition.to_dict()
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/settings/output")
async def get_output_settings():
    """Get current output target settings."""
    settings_service = get_settings_service()
    output = settings_service.get_output_settings()
    return {
        "target": output.target,
        "effective_target": output.target,
        "available_targets": VALID_OUTPUT_TARGETS
    }


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
        return {
            "status": "success",
            "settings": output.to_dict()
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/settings/active-page")
async def get_active_page():
    """Get the currently active page ID."""
    settings_service = get_settings_service()
    page_id = settings_service.get_active_page_id()
    return {
        "page_id": page_id
    }


@app.put("/settings/active-page")
async def set_active_page(request: dict):
    """
    Set the active page ID.
    
    Body should include:
    - page_id: Page ID to set as active, or null to clear
    
    When a page is set, it will be immediately rendered and sent to the board.
    """
    settings_service = get_settings_service()
    page_service = get_page_service()
    service = get_service()
    
    page_id = request.get("page_id")
    carousel_service = get_carousel_service()

    # Validate page or carousel exists if not clearing
    page = None
    render_page_id = page_id
    if page_id is not None:
        if is_carousel_id(page_id):
            carousel = carousel_service.get_carousel(page_id)
            if not carousel:
                raise HTTPException(status_code=404, detail=f"Carousel not found: {page_id}")
            render_page_id = carousel_service.resolve_page_id(page_id)
            if render_page_id:
                page = page_service.get_page(render_page_id)
        else:
            page = page_service.get_page(page_id)
            if not page:
                raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")

    # Set the active page (stores the carousel ID or page ID as-is)
    settings_service.set_active_page_id(page_id)
    
    # Immediately send to board if a page is set
    sent_to_board = False
    if render_page_id and page and service and service.vb_client and settings_service.should_send_to_board():
        result = page_service.preview_page(render_page_id, force_refresh=True)
        if result and result.available:
            system_transition = settings_service.get_transition_settings()
            strategy = page.transition_strategy if page.transition_strategy else system_transition.strategy
            interval_ms = page.transition_interval_ms if page.transition_interval_ms is not None else system_transition.step_interval_ms
            step_size = page.transition_step_size if page.transition_step_size is not None else system_transition.step_size
            
            dims = get_dimensions(page.device_type)
            board_array = text_to_board_array(result.formatted, rows=dims.rows, cols=dims.cols)
            success, was_sent = service.vb_client.send_characters(
                board_array,
                strategy=strategy,
                step_interval_ms=interval_ms,
                step_size=step_size
            )
            sent_to_board = was_sent
            if not success:
                logger.warning(f"Failed to send active page to board: {page_id}")
    
    return {
        "status": "success",
        "page_id": page_id,
        "sent_to_board": sent_to_board,
    }


@app.get("/settings/polling")
async def get_polling_settings():
    """Get current polling interval settings."""
    settings_service = get_settings_service()
    polling = settings_service.get_polling_settings()
    return {
        "interval_seconds": polling.interval_seconds
    }


@app.put("/settings/polling")
async def update_polling_settings(request: dict):
    """
    Update polling interval settings.
    
    Body should include:
    - interval_seconds: Polling interval in seconds (minimum 10)
    
    Note: Changing this setting requires restarting the service to take effect.
    """
    if "interval_seconds" not in request:
        raise HTTPException(status_code=400, detail="interval_seconds parameter required")
    
    settings_service = get_settings_service()
    
    try:
        interval_seconds = int(request["interval_seconds"])
        polling = settings_service.set_polling_interval(interval_seconds)
        return {
            "status": "success",
            "settings": polling.to_dict(),
            "requires_restart": True
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
            return {"status": "success", "settings": board.to_dict()}
        if "boards" in request:
            boards = request["boards"]
            if not isinstance(boards, list):
                raise HTTPException(status_code=400, detail="boards must be a list")
            board = settings_service.set_boards(boards)
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
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/settings/board/add")
async def add_board_instance(request: dict):
    """Add a new board instance. Body: device_type, optional name and other board fields."""
    if "device_type" not in request:
        raise HTTPException(status_code=400, detail="device_type is required")
    settings_service = get_settings_service()
    try:
        board = settings_service.add_board(request)
        return {"status": "success", "settings": board.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/settings/board/{board_id}")
async def remove_board_instance(board_id: str):
    """Remove a board instance by ID."""
    settings_service = get_settings_service()
    try:
        board = settings_service.remove_board(board_id)
        return {"status": "success", "settings": board.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
async def get_location_sun_times(date: Optional[str] = None):
    """
    Get sunrise and sunset times for the configured location on a given date.

    Query params:
    - date: ISO date string (YYYY-MM-DD); defaults to today in the configured timezone.

    Returns sunrise and sunset as HH:MM strings, or null values if location is not
    configured or sun times cannot be computed (e.g. polar day/night).
    """
    from .schedules.sun_times import get_sun_times
    from datetime import date as date_cls
    import pytz

    settings_service = get_settings_service()
    location = settings_service.get_location_settings()

    if location.latitude is None or location.longitude is None:
        return {"sunrise": None, "sunset": None, "location_configured": False}

    timezone_str = "UTC"
    try:
        from .config import Config
        timezone_str = Config.TIMEZONE or "UTC"
    except Exception:
        logger.debug("Could not get timezone from config, using UTC")

    if date:
        try:
            target_date = date_cls.fromisoformat(date)
        except ValueError:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    else:
        tz = pytz.timezone(timezone_str)
        target_date = datetime.now(tz).date()

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
    from .schedules.sun_times import get_sun_times
    from datetime import date as date_cls, timedelta

    settings_service = get_settings_service()
    location = settings_service.get_location_settings()

    if location.latitude is None or location.longitude is None:
        return {"location_configured": False, "dates": {}}

    timezone_str = "UTC"
    try:
        from .config import Config
        timezone_str = Config.TIMEZONE or "UTC"
    except Exception:
        logger.debug("Could not get timezone from config, using UTC")

    try:
        start = date_cls.fromisoformat(week_start)
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid week_start format. Use YYYY-MM-DD.")

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

    return {
        "general": general,
        "silence_schedule": {"config": silence_feature},
        "polling": {
            "interval_seconds": polling.interval_seconds
        },
        "transitions": {**transitions.to_dict(), "available_strategies": VALID_STRATEGIES},
        "output": output.to_dict(),
        "board": board.to_dict(),
        "mqtt": mqtt.to_dict(mask_secrets=True),
        "display": display.to_dict(),
        "location": location.to_dict(),
        "status": {
            "running": _service_running,
        }
    }


# ==================== Debug Endpoints ====================

def _get_server_ip() -> str:
    """Get the server's IP address."""
    import socket
    try:
        # Create a socket to determine the IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "unknown"


def _get_service_uptime() -> Optional[float]:
    """Get service uptime in seconds."""
    if _service_start_time is None:
        return None
    return time.time() - _service_start_time


def _format_uptime(seconds: Optional[float]) -> str:
    """Format uptime seconds as 'Xd Xh Xm'."""
    if seconds is None:
        return "not running"
    
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0 or len(parts) == 0:
        parts.append(f"{minutes}m")
    
    return " ".join(parts)


def _get_board_client():
    """Get the board client from the service."""
    service = get_service()
    if service and service.vb_client:
        return service.vb_client
    return None


@app.post("/debug/blank")
async def debug_blank_board():
    """Clear the board by filling with space characters (code 0)."""
    client = _get_board_client()
    if not client:
        raise HTTPException(status_code=400, detail="Board not configured")
    
    settings_service = get_settings_service()
    if not settings_service.should_send_to_board():
        return {
            "status": "success",
            "message": "Board blank (output target is UI only)"
        }
    
    try:
        # Create a 6x22 array filled with spaces (code 0)
        blank_array = [[0] * 22 for _ in range(6)]
        success, was_sent = client.send_characters(blank_array, force=True)
        
        if success:
            return {
                "status": "success",
                "message": "Board blanked successfully"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to blank board")
    except Exception as e:
        logger.error(f"Error blanking board: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/debug/fill")
async def debug_fill_board(request: dict):
    """Fill the board with a single character.
    
    Body: {"character_code": number} - code must be 0-71
    """
    character_code = request.get("character_code")
    if character_code is None:
        raise HTTPException(status_code=400, detail="character_code is required")
    
    if not isinstance(character_code, int) or character_code < 0 or character_code > 71:
        raise HTTPException(status_code=400, detail="character_code must be 0-71")
    
    client = _get_board_client()
    if not client:
        raise HTTPException(status_code=400, detail="Board not configured")
    
    settings_service = get_settings_service()
    if not settings_service.should_send_to_board():
        return {
            "status": "success",
            "message": f"Board filled with character {character_code} (output target is UI only)"
        }
    
    try:
        # Create a 6x22 array filled with the specified character
        fill_array = [[character_code] * 22 for _ in range(6)]
        success, was_sent = client.send_characters(fill_array, force=True)
        
        if success:
            return {
                "status": "success",
                "message": f"Board filled with character {character_code}"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to fill board")
    except Exception as e:
        logger.error(f"Error filling board: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/debug/info")
async def debug_show_info():
    """Display debug information on the board."""
    client = _get_board_client()
    if not client:
        raise HTTPException(status_code=400, detail="Board not configured")
    
    settings_service = get_settings_service()
    send_to_board = settings_service.should_send_to_board()
    
    # Gather system info
    board_ip = Config.BOARD_HOST or "not set"
    server_ip = _get_server_ip()
    uptime = _get_service_uptime()
    uptime_str = _format_uptime(uptime)
    connection_mode = Config.BOARD_API_MODE.upper()
    version = __version__
    
    # Get current timestamp
    from .time_service import get_time_service
    time_service = get_time_service()
    now = time_service.get_current_time()
    timestamp = now.strftime("%H:%M")
    
    # Build debug info text (6 lines max, 22 chars each)
    debug_text = f"""DEBUG INFO
BOARD: {board_ip[:15]}
SERVER: {server_ip[:14]}
UP: {uptime_str[:18]}
{connection_mode[:20]} API
V{version[:7]} {timestamp}"""
    
    if not send_to_board:
        return {
            "status": "success",
            "message": "Debug info displayed (output target is UI only)",
            "debug_info": debug_text
        }
    
    try:
        # Convert text to board array
        from .text_to_board import text_to_board_array
        board_array = text_to_board_array(debug_text, use_color_tiles=False)
        
        success, was_sent = client.send_characters(board_array, force=True)
        
        if success:
            return {
                "status": "success",
                "message": "Debug info sent to board",
                "debug_info": debug_text
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to send debug info")
    except Exception as e:
        logger.error(f"Error sending debug info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/debug/test-connection")
async def debug_test_connection():
    """Test connection to the board."""
    client = _get_board_client()
    if not client:
        raise HTTPException(status_code=400, detail="Board not configured")
    
    try:
        start_time = time.time()
        connected = client.test_connection()
        latency = round((time.time() - start_time) * 1000)  # ms
        
        if connected:
            return {
                "status": "success",
                "message": f"Connection successful (latency: {latency}ms)",
                "connected": True,
                "latency_ms": latency
            }
        else:
            return {
                "status": "error",
                "message": "Connection failed",
                "connected": False,
                "latency_ms": None
            }
    except Exception as e:
        logger.error(f"Error testing connection: {e}", exc_info=True)
        return {
            "status": "error",
            "message": "Connection test failed",
            "connected": False,
            "latency_ms": None
        }


@app.post("/debug/clear-cache")
async def debug_clear_cache():
    """Clear the board client's message cache."""
    client = _get_board_client()
    if not client:
        raise HTTPException(status_code=400, detail="Board not configured")
    
    try:
        client.clear_cache()
        return {
            "status": "success",
            "message": "Cache cleared - next message will be sent regardless of content"
        }
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/debug/cache-status")
async def debug_get_cache_status():
    """Get current cache status for debugging."""
    client = _get_board_client()
    if not client:
        raise HTTPException(status_code=400, detail="Board not configured")
    
    try:
        cache_status = client.get_cache_status()
        return {
            "status": "success",
            "cache": cache_status
        }
    except Exception as e:
        logger.error(f"Error getting cache status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/debug/system-info")
async def debug_get_system_info():
    """Get system information without sending to board."""
    # Gather all system info
    board_ip = Config.BOARD_HOST or ""
    server_ip = _get_server_ip()
    uptime_seconds = _get_service_uptime()
    uptime_formatted = _format_uptime(uptime_seconds)
    connection_mode = Config.BOARD_API_MODE
    version = __version__
    
    # Get current timestamp
    from .time_service import get_time_service
    time_service = get_time_service()
    timestamp = time_service.create_utc_timestamp()
    
    # Get cache status if available
    client = _get_board_client()
    cache_status = client.get_cache_status() if client else None
    
    # Check if board is configured
    board_configured = bool(board_ip and (
        (connection_mode == "local" and Config.BOARD_LOCAL_API_KEY) or
        (connection_mode == "cloud" and Config.BOARD_READ_WRITE_KEY)
    ))
    
    return {
        "board_ip": board_ip,
        "server_ip": server_ip,
        "uptime_seconds": uptime_seconds,
        "uptime_formatted": uptime_formatted,
        "connection_mode": connection_mode,
        "version": version,
        "timestamp": timestamp,
        "cache_status": cache_status,
        "board_configured": board_configured,
        "service_running": _service_running,
    }


@app.get("/debug/network-diagnostics")
async def debug_network_diagnostics():
    """Run network diagnostics to troubleshoot connectivity issues.

    Checks DNS resolution, internet connectivity, and Vestaboard reachability.
    """
    from .network_diagnostics import run_full_diagnostics

    board_host = Config.BOARD_HOST or None
    board_port = 7000
    board_api_key = Config.BOARD_LOCAL_API_KEY or None
    use_cloud = (Config.BOARD_API_MODE or "local").lower() == "cloud"
    cloud_key = Config.BOARD_READ_WRITE_KEY or None

    try:
        results = run_full_diagnostics(
            board_host=board_host,
            board_port=board_port,
            board_api_key=board_api_key,
            use_cloud=use_cloud,
            cloud_key=cloud_key,
        )
        return {"status": "success", "diagnostics": results}
    except Exception as e:
        logger.error(f"Error running network diagnostics: {e}")
        raise HTTPException(status_code=500, detail="Network diagnostics failed")


# =============================================================================
# Pages Endpoints
# =============================================================================

@app.get("/pages")
async def list_pages():
    """List all saved pages."""
    page_service = get_page_service()
    pages = page_service.list_pages()
    
    return {
        "pages": [p.model_dump() for p in pages],
        "total": len(pages)
    }


@app.get("/pages/current-display")
async def get_current_display():
    """Get the template content of the currently active board display.

    Resolves carousels and schedule mode to find the actual page being shown.
    For template pages, returns the raw template and line metadata so the
    caller can use it as a starting point for a new page.  For other page
    types, returns the rendered output lines.

    Returns 404 when no active page can be determined.
    """
    settings_service = get_settings_service()
    page_service = get_page_service()
    carousel_service = get_carousel_service()

    # Determine the active page ID (schedule-aware)
    if settings_service.is_schedule_enabled():
        from .time_service import get_time_service
        time_service = get_time_service()
        now = time_service.get_current_time()
        current_time = now.time()
        current_day = now.strftime("%A").lower()
        schedule_service = get_schedule_service()
        active_page_id = schedule_service.get_active_page_id(current_time, current_day)
    else:
        active_page_id = settings_service.get_active_page_id()

    if not active_page_id:
        raise HTTPException(status_code=404, detail="No active page set")

    # Resolve carousel to underlying page
    if is_carousel_id(active_page_id):
        resolved = carousel_service.resolve_page_id(active_page_id)
        if not resolved:
            raise HTTPException(status_code=404, detail="Carousel could not be resolved")
        active_page_id = resolved

    page = page_service.get_page(active_page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Active page not found")

    response: dict = {
        "page_id": page.id,
        "page_name": page.name,
        "page_type": page.type,
        "device_type": page.device_type,
    }

    if page.type == "template" and page.template:
        # Return raw template so variables like {{weather.temp}} are preserved
        response["template"] = page.template
        response["line_metadata"] = (
            [m.model_dump() for m in page.line_metadata]
            if page.line_metadata
            else None
        )
    else:
        # For single/composite pages, return the rendered output as template lines
        result = page_service.preview_page(active_page_id, force_refresh=True)
        if result and result.available:
            response["template"] = result.formatted.split("\n")
            response["line_metadata"] = None
        else:
            response["template"] = []
            response["line_metadata"] = None

    return response


@app.post("/pages")
async def create_page(page_data: PageCreate):
    """
    Create a new page.
    
    Page types:
    - single: Display a single source (set display_type)
    - composite: Combine rows from multiple sources (set rows)
    - template: Custom templated content (set template)
    """
    page_service = get_page_service()
    
    try:
        page = page_service.create_page(page_data)
        return {
            "status": "success",
            "page": page.model_dump()
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/pages/{page_id}")
async def get_page(page_id: str):
    """Get a page by ID."""
    page_service = get_page_service()
    page = page_service.get_page(page_id)
    
    if not page:
        raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")
    
    return page.model_dump()


@app.put("/pages/{page_id}")
async def update_page(page_id: str, page_data: PageUpdate):
    """Update an existing page."""
    page_service = get_page_service()
    
    try:
        page = page_service.update_page(page_id, page_data)
        if not page:
            raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")
        
        return {
            "status": "success",
            "page": page.model_dump()
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/pages/{page_id}")
async def delete_page(page_id: str):
    """Delete a page.
    
    If this is the last page, a default welcome page is automatically created
    to ensure there is always at least one page.
    
    If the deleted page was the active display page, the active page will be
    updated to another valid page automatically.
    """
    page_service = get_page_service()
    
    result = page_service.delete_page(page_id)
    
    if not result.deleted:
        raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")
    
    response = {
        "status": "success",
        "message": f"Page {page_id} deleted",
        "default_page_created": result.default_page_created,
        "active_page_updated": result.active_page_updated,
    }
    
    if result.default_page_created:
        response["message"] = f"Page {page_id} deleted. A default welcome page was created."
        response["new_page_id"] = result.new_page_id
    
    if result.active_page_updated:
        response["new_active_page_id"] = result.new_active_page_id
    
    return response


@app.post("/pages/{page_id}/preview")
async def preview_page(
    page_id: str,
    force_refresh: bool = Query(default=False, description="Force fresh render, bypass cache")
):
    """
    Preview a page's rendered output.
    
    Uses cached preview by default for fast responses. Set force_refresh=true
    to always render fresh (useful when editing or displaying active page).
    
    Args:
        page_id: The page ID to preview
        force_refresh: If true, bypass cache and always render fresh
    
    Returns:
        The formatted text that would be displayed.
    """
    page_service = get_page_service()
    settings_service = get_settings_service()
    
    # Always force refresh for the active page to ensure it's up-to-date
    active_page_id = settings_service.get_active_page_id()
    if page_id == active_page_id:
        force_refresh = True
    
    result = page_service.preview_page(page_id, force_refresh=force_refresh)
    
    if result is None:
        raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")
    
    if not result.available:
        raise HTTPException(status_code=503, detail=result.error or "Page rendering failed")
    
    return {
        "page_id": page_id,
        "message": result.formatted,
        "lines": result.formatted.split('\n'),
        "display_type": result.display_type,
        "raw": result.raw
    }


@app.post("/pages/preview/batch")
async def preview_pages_batch(request: dict):
    """
    Preview multiple pages in a single request.
    
    Request body:
        {
            "page_ids": ["page1", "page2", ...],
            "force_refresh": false  // Optional, defaults to false
        }
    
    Returns a dict mapping page_id to preview data (or error).
    Uses cached previews by default for fast responses.
    Active page is always rendered fresh regardless of force_refresh setting.
    Template context (plugin data) is built once and shared across all page renders.
    """
    page_ids = request.get("page_ids", [])
    force_refresh = request.get("force_refresh", False)
    
    if not isinstance(page_ids, list):
        raise HTTPException(status_code=400, detail="page_ids must be a list")
    
    page_service = get_page_service()
    settings_service = get_settings_service()
    active_page_id = settings_service.get_active_page_id()
    results = {}
    
    # Use batch preview to build template context once for all pages
    batch_results = page_service.preview_pages_batch(
        page_ids,
        force_refresh=force_refresh,
        active_page_id=active_page_id,
    )
    
    for page_id in page_ids:
        result = batch_results.get(page_id)
        if result is None:
            results[page_id] = {
                "error": "Page not found",
                "available": False
            }
        elif not result.available:
            results[page_id] = {
                "error": result.error or "Page rendering failed",
                "available": False
            }
        else:
            results[page_id] = {
                "page_id": page_id,
                "message": result.formatted,
                "lines": result.formatted.split('\n'),
                "display_type": result.display_type,
                "raw": result.raw,
                "available": True
            }
    
    return {
        "previews": results,
        "total": len(page_ids),
        "successful": sum(1 for r in results.values() if r.get("available", False))
    }


@app.get("/pages/cache/stats")
async def get_page_cache_stats():
    """
    Get preview cache statistics.
    
    Returns information about the preview cache including size,
    cached page IDs, and TTL configuration.
    """
    page_service = get_page_service()
    return page_service.get_cache_stats()


@app.post("/pages/cache/clear")
async def clear_page_cache(request: dict = None):
    """
    Clear preview cache.
    
    Request body (optional):
        {
            "page_id": "page123"  // Clear specific page, omit to clear all
        }
    
    Clears the preview cache, forcing fresh renders on next preview.
    Useful for testing or when data sources have been updated.
    """
    page_service = get_page_service()
    
    page_id = None
    if request:
        page_id = request.get("page_id")
    
    page_service._invalidate_cache(page_id)
    
    if page_id:
        return {
            "status": "success",
            "message": f"Cache cleared for page {page_id}"
        }
    else:
        return {
            "status": "success",
            "message": "All preview caches cleared"
        }


@app.post("/pages/{page_id}/send")
async def send_page(page_id: str, target: Optional[str] = None):
    """
    Send a page to the configured target.
    
    Args:
        page_id: The page ID
        target: Override output target (ui, board, both)
    """
    if target is not None and target not in VALID_OUTPUT_TARGETS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid target: {target}. Valid targets: {VALID_OUTPUT_TARGETS}"
        )
    
    page_service = get_page_service()
    settings_service = get_settings_service()
    service = get_service()
    
    if not service or not service.vb_client:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    # Get the page for transition settings
    page = page_service.get_page(page_id)
    if not page:
        raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")
    
    # Render the page - always force fresh render when sending to board
    result = page_service.preview_page(page_id, force_refresh=True)
    
    if result is None:
        raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")
    
    if not result.available:
        raise HTTPException(status_code=503, detail=result.error or "Page rendering failed")
    
    # Determine target
    if target is None:
        send_to_board = settings_service.should_send_to_board()
    else:
        send_to_board = target in ["board", "both"]
    
    sent_to_board = False
    if send_to_board:
        # CRITICAL: Block ALL manual sends during silence mode to prevent wake-ups
        if Config.is_silence_mode_active():
            logger.info("Silence mode is active - blocking manual page send to prevent wake-up")
            sent_to_board = False
            # Don't raise error, just skip sending
        else:
            # Use page-level transitions if set, otherwise fall back to system defaults
            system_transition = settings_service.get_transition_settings()
            strategy = page.transition_strategy if page.transition_strategy else system_transition.strategy
            interval_ms = page.transition_interval_ms if page.transition_interval_ms is not None else system_transition.step_interval_ms
            step_size = page.transition_step_size if page.transition_step_size is not None else system_transition.step_size
            
            # Convert to board array with dimensions for page's device type (flagship vs note)
            dims = get_dimensions(page.device_type)
            board_array = text_to_board_array(result.formatted, rows=dims.rows, cols=dims.cols)
            success, was_sent = service.vb_client.send_characters(
                board_array,
                strategy=strategy,
                step_interval_ms=interval_ms,
                step_size=step_size
            )
            sent_to_board = was_sent
            if not success:
                raise HTTPException(status_code=500, detail="Failed to send to board")
    
    return {
        "status": "success",
        "page_id": page_id,
        "message": result.formatted,
        "sent_to_board": sent_to_board,
        "target": target or settings_service.get_output_settings().target,
    }


# =============================================================================
# Schedule Endpoints
# =============================================================================

def _enrich_schedule_with_sun_times(schedule_dict: dict) -> dict:
    """Add resolved_start_time / resolved_end_time to a schedule dict.

    For fixed-type schedules the resolved times equal the stored times.
    For sun-based schedules (sunrise/sunset) the times are computed
    dynamically for today using the configured location.
    """
    start_type = schedule_dict.get("start_type", "fixed")
    end_type = schedule_dict.get("end_type", "fixed")

    if start_type == "fixed" and end_type == "fixed":
        schedule_dict["resolved_start_time"] = schedule_dict["start_time"]
        schedule_dict["resolved_end_time"] = schedule_dict.get("end_time")
        return schedule_dict

    from datetime import date as date_type
    from .schedules.sun_times import resolve_schedule_sun_times

    settings = get_settings_service()
    loc = settings.get_location_settings()
    timezone_str = "UTC"
    try:
        from .config import Config
        timezone_str = Config.TIMEZONE or "UTC"
    except Exception:
        logger.debug("Could not get timezone from config, using UTC")

    resolved_start, resolved_end = resolve_schedule_sun_times(
        start_type=start_type,
        start_sun_offset=schedule_dict.get("start_sun_offset", 0),
        start_time_fallback=schedule_dict["start_time"],
        end_type=end_type,
        end_sun_offset=schedule_dict.get("end_sun_offset", 0),
        end_time_fallback=schedule_dict.get("end_time"),
        latitude=loc.latitude,
        longitude=loc.longitude,
        target_date=date_type.today(),
        timezone_str=timezone_str,
    )
    schedule_dict["resolved_start_time"] = resolved_start
    schedule_dict["resolved_end_time"] = resolved_end
    return schedule_dict

@app.get("/schedules")
async def list_schedules(board_id: Optional[str] = None):
    """List schedule entries, optionally for one board (query: board_id=).
    
    Use board_id=* to get ALL schedules across all boards (useful for cleanup/admin).
    """
    schedule_service = get_schedule_service()
    settings_service = get_settings_service()
    schedules = schedule_service.list_schedules(board_id=board_id)
    
    # When listing all boards (board_id="*"), default_page_id and enabled don't make sense
    if board_id == "*":
        return {
            "schedules": [_enrich_schedule_with_sun_times(s.model_dump()) for s in schedules],
            "total": len(schedules),
            "default_page_id": None,
            "enabled": False,
        }
    
    return {
        "schedules": [_enrich_schedule_with_sun_times(s.model_dump()) for s in schedules],
        "total": len(schedules),
        "default_page_id": schedule_service.get_default_page(board_id=board_id),
        "enabled": settings_service.is_schedule_enabled(board_id=board_id),
    }


@app.post("/schedules")
async def create_schedule(schedule_data: ScheduleCreate):
    """Create a new schedule entry.
    
    Args:
        schedule_data: Schedule configuration
        
    Returns:
        Created schedule entry
    """
    schedule_service = get_schedule_service()
    
    try:
        schedule = schedule_service.create_schedule(schedule_data)
        return _enrich_schedule_with_sun_times(schedule.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# Specific routes must come BEFORE parameterized routes
# to avoid /schedules/{schedule_id} matching everything

@app.get("/schedules/active/page")
async def get_active_schedule(board_id: Optional[str] = None):
    """Get the currently active page based on schedule (optional query: board_id=)."""
    schedule_service = get_schedule_service()
    settings_service = get_settings_service()
    if not settings_service.is_schedule_enabled(board_id=board_id):
        return {
            "page_id": settings_service.get_active_page_id(),
            "source": "manual",
            "schedule_enabled": False,
        }
    from .time_service import get_time_service
    time_service = get_time_service()
    now = time_service.get_current_time()
    current_time = now.time()
    current_day = now.strftime("%A").lower()
    page_id = schedule_service.get_active_page_id(current_time, current_day, board_id=board_id)
    return {
        "page_id": page_id,
        "source": "schedule" if page_id else "none",
        "schedule_enabled": True,
        "current_time": now.strftime("%H:%M"),
        "current_day": current_day,
        "default_page_id": schedule_service.get_default_page(board_id=board_id),
    }


@app.post("/schedules/validate")
async def validate_schedules(request: Optional[dict] = Body(None)):
    """Validate schedules for overlaps and gaps. Body optional: {"board_id": "..."}."""
    schedule_service = get_schedule_service()
    board_id = request.get("board_id") if request else None
    result = schedule_service.validate_schedules(board_id=board_id)
    return result.model_dump()


@app.get("/schedules/default-page")
async def get_default_page(board_id: Optional[str] = None):
    """Get the default page ID for schedule gaps (optional query: board_id=)."""
    schedule_service = get_schedule_service()
    return {"default_page_id": schedule_service.get_default_page(board_id=board_id)}


@app.put("/schedules/default-page")
async def set_default_page(request: dict):
    """Set the default page ID for schedule gaps. Body: page_id, optional board_id."""
    if "page_id" not in request:
        raise HTTPException(status_code=400, detail="page_id parameter required")
    page_id = request["page_id"]
    board_id = request.get("board_id")
    if page_id is not None:
        if is_carousel_id(page_id):
            carousel_service = get_carousel_service()
            if not carousel_service.get_carousel(page_id):
                raise HTTPException(status_code=404, detail=f"Carousel not found: {page_id}")
        else:
            page_service = get_page_service()
            if not page_service.get_page(page_id):
                raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")
    schedule_service = get_schedule_service()
    schedule_service.set_default_page(page_id, board_id=board_id)
    return {"status": "success", "default_page_id": page_id}


@app.get("/schedules/enabled")
async def get_schedule_enabled(board_id: Optional[str] = None):
    """Check if schedule mode is enabled (optional query: board_id=)."""
    settings_service = get_settings_service()
    return {"enabled": settings_service.is_schedule_enabled(board_id=board_id)}


@app.put("/schedules/enabled")
async def set_schedule_enabled(request: dict):
    """Enable or disable schedule mode. Body: enabled, optional board_id."""
    if "enabled" not in request:
        raise HTTPException(status_code=400, detail="enabled parameter required")
    enabled = request["enabled"]
    if not isinstance(enabled, bool):
        raise HTTPException(status_code=400, detail="enabled must be boolean")
    board_id = request.get("board_id")
    settings_service = get_settings_service()
    settings_service.set_schedule_enabled(enabled, board_id=board_id)
    return {
        "status": "success",
        "enabled": enabled,
        "message": f"Schedule mode {'enabled' if enabled else 'disabled'}",
    }


# Parameterized routes come LAST to avoid matching specific paths

@app.get("/schedules/{schedule_id}")
async def get_schedule(schedule_id: str):
    """Get a schedule entry by ID.
    
    Args:
        schedule_id: Schedule ID
        
    Returns:
        Schedule entry
    """
    schedule_service = get_schedule_service()
    schedule = schedule_service.get_schedule(schedule_id)
    
    if not schedule:
        raise HTTPException(status_code=404, detail=f"Schedule not found: {schedule_id}")
    
    return _enrich_schedule_with_sun_times(schedule.model_dump())


@app.put("/schedules/{schedule_id}")
async def update_schedule(schedule_id: str, schedule_data: ScheduleUpdate):
    """Update an existing schedule entry.
    
    Args:
        schedule_id: Schedule ID
        schedule_data: Fields to update
        
    Returns:
        Updated schedule entry
    """
    schedule_service = get_schedule_service()
    
    try:
        schedule = schedule_service.update_schedule(schedule_id, schedule_data)
        if not schedule:
            raise HTTPException(status_code=404, detail=f"Schedule not found: {schedule_id}")
        return _enrich_schedule_with_sun_times(schedule.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str):
    """Delete a schedule entry.
    
    Args:
        schedule_id: Schedule ID
        
    Returns:
        Success status
    """
    schedule_service = get_schedule_service()
    
    deleted = schedule_service.delete_schedule(schedule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Schedule not found: {schedule_id}")
    
    return {
        "status": "success",
        "message": f"Schedule {schedule_id} deleted"
    }


# =============================================================================
# Carousel Endpoints
# =============================================================================

@app.get("/carousels")
async def list_carousels():
    """List all carousels."""
    carousel_service = get_carousel_service()
    carousels = carousel_service.list_carousels()
    return {
        "carousels": [c.model_dump() for c in carousels],
        "total": len(carousels),
    }


@app.post("/carousels")
async def create_carousel(data: CarouselCreate):
    """Create a new carousel."""
    carousel_service = get_carousel_service()
    page_service = get_page_service()

    for pid in data.page_ids:
        if not page_service.get_page(pid):
            raise HTTPException(status_code=400, detail=f"Page not found: {pid}")

    try:
        carousel = carousel_service.create_carousel(data)
        return {"status": "success", "carousel": carousel.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/carousels/{carousel_id}")
async def get_carousel(carousel_id: str):
    """Get a carousel by ID."""
    carousel_service = get_carousel_service()
    carousel = carousel_service.get_carousel(carousel_id)
    if not carousel:
        raise HTTPException(status_code=404, detail=f"Carousel not found: {carousel_id}")
    return carousel.model_dump()


@app.put("/carousels/{carousel_id}")
async def update_carousel(carousel_id: str, data: CarouselUpdate):
    """Update an existing carousel."""
    carousel_service = get_carousel_service()
    page_service = get_page_service()

    if data.page_ids is not None:
        for pid in data.page_ids:
            if not page_service.get_page(pid):
                raise HTTPException(status_code=400, detail=f"Page not found: {pid}")

    try:
        carousel = carousel_service.update_carousel(carousel_id, data)
        if not carousel:
            raise HTTPException(status_code=404, detail=f"Carousel not found: {carousel_id}")
        return {"status": "success", "carousel": carousel.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/carousels/{carousel_id}")
async def delete_carousel(carousel_id: str):
    """Delete a carousel."""
    carousel_service = get_carousel_service()
    deleted = carousel_service.delete_carousel(carousel_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Carousel not found: {carousel_id}")
    return {"status": "success", "message": f"Carousel {carousel_id} deleted"}


# =============================================================================
# Template Endpoints
# =============================================================================

@app.get("/templates/variables")
async def get_template_variables():
    """
    Get available template variables by source.
    
    Returns a dictionary mapping source names to available field names.
    Use these in templates as {{source.field}}, e.g., {{weather.temperature}}.
    Also includes rich metadata (descriptions, types, previews) and variable
    groups when declared by the plugin.
    """
    template_engine = get_template_engine()
    registry = get_plugin_registry()

    result = {
        "variables": template_engine.get_available_variables(),
        "max_lengths": template_engine.get_variable_max_lengths(),
        "variable_metadata": registry.get_all_variables_with_metadata(),
        "variable_groups": registry.get_all_variable_groups(),
        "colors": {
            "red": 63,
            "orange": 64,
            "yellow": 65,
            "green": 66,
            "blue": 67,
            "violet": 68,
            "white": 69,
            "black": 70,
        },
        "symbols": ["sun", "star", "cloud", "rain", "snow", "storm", "fog", "partly", "heart", "check", "x"],
        "filters": ["pad:N", "truncate:N", "wrap"],
        "formatting": {
            "fill_space": {
                "syntax": "{{fill_space}}",
                "description": "Expands to fill remaining space on the line. Use multiple for multi-column layouts."
            },
            "fill_space_repeat": {
                "syntax": "{{fill_space_repeat:pattern}}",
                "description": "Fills remaining space with repeating colors or characters. Examples: {{fill_space_repeat:red}} or {{fill_space_repeat:-}}"
            }
        },
        "syntax_examples": {
            "variable": "{{weather.temperature}}",
            "variable_with_filter": "{{weather.temperature|pad:3}}",
            "color_inline": "{{red}} Warning {{red}}",
            "color_code": "{63}",
            "symbol": "{sun}",
            "wrap": "{{star_trek.quote|wrap}}",
            "fill_space": "Left{{fill_space}}Right",
            "fill_space_three_columns": "A{{fill_space}}B{{fill_space}}C",
        }
    }
    return result


@app.post("/templates/validate")
async def validate_template(request: dict):
    """
    Validate template syntax.
    
    Body should include:
    - template: Template string or list of lines to validate
    
    Returns validation errors if any.
    """
    if "template" not in request:
        raise HTTPException(status_code=400, detail="template parameter required")
    
    template = request["template"]
    
    # Handle both string and list input
    if isinstance(template, list):
        template = '\n'.join(template)
    
    template_engine = get_template_engine()
    errors = template_engine.validate_template(template)
    
    return {
        "valid": len(errors) == 0,
        "errors": [
            {"line": e.line, "column": e.column, "message": e.message}
            for e in errors
        ]
    }


@app.post("/templates/render")
async def render_template(request: dict):
    """
    Render a template with current data.
    
    Body should include:
    - template: Template string or list of lines to render
    
    Useful for previewing template output before saving as a page.
    """
    if "template" not in request:
        raise HTTPException(status_code=400, detail="template parameter required")
    
    template = request["template"]
    device_type = request.get("device_type")
    
    # Determine line count from device type
    from .devices import DEVICE_DIMENSIONS, DEFAULT_DEVICE_TYPE
    dims = DEVICE_DIMENSIONS.get(device_type or DEFAULT_DEVICE_TYPE,
                                  DEVICE_DIMENSIONS[DEFAULT_DEVICE_TYPE])
    num_rows = dims.rows
    
    # Early return for empty templates to avoid unnecessary processing
    if isinstance(template, list):
        if not template or all(not line.strip() for line in template):
            return {
                "rendered": "\n".join([""] * num_rows),
                "lines": [""] * num_rows,
                "line_count": num_rows
            }
    elif isinstance(template, str) and not template.strip():
        return {
            "rendered": "\n".join([""] * num_rows),
            "lines": [""] * num_rows,
            "line_count": num_rows
        }
    
    template_engine = get_template_engine()
    line_metadata = request.get("line_metadata")
    
    try:
        if isinstance(template, list):
            logger.info(f"Rendering template lines: {template}")
            rendered = template_engine.render_lines(template, line_metadata=line_metadata, device_type=device_type)
        else:
            logger.info(f"Rendering template string: {template}")
            rendered = template_engine.render(template)
        
        return {
            "rendered": rendered,
            "lines": rendered.split('\n'),
            "line_count": len(rendered.split('\n'))
        }
    except Exception as e:
        logger.error(f"Template rendering error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Template rendering failed: {str(e)}")


@app.post("/templates/render/live")
async def render_template_live(request: dict):
    """
    Render a template and send it to a board (live edit mode).

    Body should include:
    - template: Template string or list of lines to render
    - board_id: Optional board ID to target (defaults to first configured board)

    Returns the rendered result plus whether it was sent to the board.
    """
    if "template" not in request:
        raise HTTPException(status_code=400, detail="template parameter required")

    template = request["template"]
    board_id = request.get("board_id")

    template_engine = get_template_engine()
    settings_service = get_settings_service()
    line_metadata = request.get("line_metadata")
    device_type = request.get("device_type")

    # Determine line count from device type
    from .devices import DEVICE_DIMENSIONS, DEFAULT_DEVICE_TYPE
    dims = DEVICE_DIMENSIONS.get(device_type or DEFAULT_DEVICE_TYPE,
                                  DEVICE_DIMENSIONS[DEFAULT_DEVICE_TYPE])
    num_rows = dims.rows

    # Render the template
    try:
        if isinstance(template, list):
            if not template or all(not line.strip() for line in template):
                return {
                    "rendered": "\n".join([""] * num_rows),
                    "lines": [""] * num_rows,
                    "line_count": num_rows,
                    "sent_to_board": False,
                    "board_id": board_id,
                }
            rendered = template_engine.render_lines(template, line_metadata=line_metadata, device_type=device_type)
        else:
            if not template.strip():
                return {
                    "rendered": "\n".join([""] * num_rows),
                    "lines": [""] * num_rows,
                    "line_count": num_rows,
                    "sent_to_board": False,
                    "board_id": board_id,
                }
            rendered = template_engine.render(template)
    except Exception as e:
        logger.error(f"Template rendering error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Template rendering failed: {str(e)}")

    # Find the target board
    board_settings = settings_service.get_board_settings()
    boards = board_settings.boards if board_settings else []

    target_board = None
    if board_id:
        for b in boards:
            if b.get("id") == board_id:
                target_board = b
                break
        if not target_board:
            raise HTTPException(status_code=404, detail=f"Board not found: {board_id}")
    elif boards:
        target_board = boards[0]

    sent_to_board = False
    if target_board:
        client = board_client_from_board_dict(target_board)
        if client:
            device_type = target_board.get("device_type", "flagship")
            dims = get_dimensions(device_type)
            board_array = text_to_board_array(rendered, rows=dims.rows, cols=dims.cols)

            transition_settings = settings_service.get_transition_settings()
            try:
                success, was_sent = await asyncio.to_thread(
                    client.send_characters,
                    board_array,
                    strategy=transition_settings.strategy,
                    step_interval_ms=transition_settings.step_interval_ms,
                    step_size=transition_settings.step_size,
                    force=True,
                )
                sent_to_board = was_sent
            except Exception as e:
                logger.error(f"Live send to board failed: {e}", exc_info=True)

    return {
        "rendered": rendered,
        "lines": rendered.split('\n'),
        "line_count": len(rendered.split('\n')),
        "sent_to_board": sent_to_board,
        "board_id": target_board.get("id") if target_board else None,
    }


@app.get("/cache-status")
async def get_cache_status():
    """Get the current client-side cache status for the board client."""
    service = get_service()
    if not service or not service.vb_client:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    return service.vb_client.get_cache_status()


@app.post("/clear-cache")
async def clear_cache():
    """
    Clear the client-side message cache.
    
    This forces the next update to be sent to the board, 
    even if the message content hasn't changed.
    """
    service = get_service()
    if not service or not service.vb_client:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    service.vb_client.clear_cache()
    return {"status": "success", "message": "Cache cleared - next update will be sent to board"}



@app.post("/force-refresh")
async def force_refresh():
    """
    Force a display refresh, ignoring the cache.
    
    Unlike /refresh, this will send to the board even if the message 
    content hasn't changed. Useful when you want to resync the board.
    """
    service = get_service()
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    # Clear cache to force send
    if service.vb_client:
        service.vb_client.clear_cache()
    
    try:
        service.fetch_and_display()
        return {"status": "success", "message": "Display force-refreshed successfully"}
    except Exception as e:
        logger.error(f"Error force-refreshing display: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to force refresh: {str(e)}")


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
            result_entities.append({
                "entity_id": e["entity_id"],
                "state": e["state"],
                "attributes": attrs,
                "friendly_name": attrs.get("friendly_name", e["entity_id"]),
            })
        return {"entities": result_entities}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to fetch entities: {str(e)}")


# Legacy endpoints /preview and /publish-preview have been removed.
# Use /pages/{page_id}/preview and /pages/{page_id}/send instead.
# Set the active page with PUT /settings/active-page for automatic board updates.


# =============================================================================
# Plugin API Endpoints
# =============================================================================

# Import plugin system
try:
    from .plugins import get_plugin_registry
    PLUGIN_SYSTEM_AVAILABLE = True
except ImportError:
    PLUGIN_SYSTEM_AVAILABLE = False
    get_plugin_registry = None


class PluginConfigRequest(BaseModel):
    """Request body for plugin configuration updates."""
    config: Dict[str, Any]


class PluginEnableRequest(BaseModel):
    """Request body for enabling/disabling a plugin."""
    enabled: bool


@app.get("/plugins")
async def list_plugins():
    """
    List all available plugins.
    
    Returns plugins with their status, metadata, and whether they're enabled.
    """
    if not PLUGIN_SYSTEM_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Plugin system is not available."
        )
    
    registry = get_plugin_registry()
    plugins = registry.list_plugins()
    
    # Add configuration status (masked)
    config_manager = get_config_manager()
    for plugin in plugins:
        plugin_config = config_manager.get_plugin_config(plugin["id"])
        if plugin_config:
            plugin["configured"] = True
            # Add masked config
            plugin["config"] = config_manager._mask_sensitive(plugin_config)
        else:
            plugin["configured"] = False
            plugin["config"] = {}
    
    return {
        "plugins": plugins,
        "plugin_system_enabled": True,
        "total": len(plugins),
        "enabled_count": sum(1 for p in plugins if p.get("enabled", False))
    }


@app.get("/plugins/variables/all")
async def get_all_plugin_variables():
    """
    Get all template variables from enabled plugins.
    
    Returns a combined view of all variables for the template editor.
    """
    if not PLUGIN_SYSTEM_AVAILABLE:
        # Fall back to legacy variables
        template_engine = get_template_engine()
        return {
            "variables": template_engine.get_available_variables(),
            "max_lengths": template_engine.get_variable_max_lengths(),
            "plugin_system_enabled": False
        }
    
    registry = get_plugin_registry()
    
    return {
        "variables": registry.get_all_variables(),
        "max_lengths": registry.get_all_max_lengths(),
        "plugin_system_enabled": True
    }


@app.get("/plugins/errors")
async def get_plugin_errors():
    """
    Get any plugin load errors.
    
    Returns errors from plugins that failed to load.
    """
    if not PLUGIN_SYSTEM_AVAILABLE:
        return {
            "errors": {},
            "plugin_system_enabled": False
        }
    
    registry = get_plugin_registry()
    
    return {
        "errors": registry.get_load_errors(),
        "plugin_system_enabled": True
    }


@app.get("/plugins/registry")
async def list_registry_plugins():
    """
    List all plugins available in the curated plugin registry.

    Returns registry entries with their installation status.
    """
    if not PLUGIN_SYSTEM_AVAILABLE:
        raise HTTPException(
            status_code=503, detail="Plugin system is not available."
        )

    registry = get_plugin_registry()

    return {
        "entries": registry.get_registry_entries(),
        "plugin_system_enabled": True,
    }


@app.get("/plugins/updates")
async def get_plugin_updates():
    """
    Return cached update availability for all installed external plugins.

    Results are refreshed by a background task every 6 hours.  Call
    ``POST /plugins/updates/check`` to trigger an immediate check.
    """
    if not PLUGIN_SYSTEM_AVAILABLE:
        raise HTTPException(
            status_code=503, detail="Plugin system is not available."
        )

    registry = get_plugin_registry()
    return {"updates": registry.get_update_status()}


@app.get("/plugins/{plugin_id}")
async def get_plugin(plugin_id: str):
    """
    Get details for a specific plugin.
    
    Returns the plugin's manifest, configuration, and status.
    """
    if not PLUGIN_SYSTEM_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Plugin system is not available."
        )
    
    registry = get_plugin_registry()
    manifest = registry.get_manifest(plugin_id)
    
    if not manifest:
        raise HTTPException(
            status_code=404,
            detail=f"Plugin not found: {plugin_id}"
        )
    
    # Get configuration
    config_manager = get_config_manager()
    plugin_config = config_manager.get_plugin_config(plugin_id)
    
    # Check for demo page
    has_demo = manifest.demo is not None
    demo_page_id = None
    if has_demo:
        page_service = get_page_service()
        demo_page = page_service.get_demo_page(plugin_id)
        if demo_page:
            demo_page_id = demo_page.id

    # Instance information
    base_id, instance_label = registry.parse_instance_key(plugin_id)
    instances = registry.list_instances(base_id) if not instance_label else []

    return {
        "id": plugin_id,
        "name": manifest.name,
        "version": manifest.version,
        "description": manifest.description,
        "author": manifest.author,
        "icon": manifest.icon,
        "category": manifest.category,
        "enabled": registry.is_enabled(plugin_id),
        "config": config_manager._mask_sensitive(plugin_config) if plugin_config else {},
        "settings_schema": manifest.settings_schema,
        "variables": manifest.raw.get("variables", {}),
        "max_lengths": manifest.max_lengths,
        "env_vars": manifest.env_vars,
        "documentation": manifest.documentation,
        "has_demo": has_demo,
        "demo_page_id": demo_page_id,
        "instance_label": instance_label,
        "base_plugin_id": base_id,
        "instances": instances,
    }


@app.get("/plugins/{plugin_id}/manifest")
async def get_plugin_manifest(plugin_id: str):
    """
    Get the full manifest for a plugin.
    
    Returns the raw manifest data for UI rendering.
    """
    if not PLUGIN_SYSTEM_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Plugin system is not available."
        )
    
    registry = get_plugin_registry()
    manifest = registry.get_manifest(plugin_id)
    
    if not manifest:
        raise HTTPException(
            status_code=404,
            detail=f"Plugin not found: {plugin_id}"
        )
    
    return manifest.raw


@app.put("/plugins/{plugin_id}/config")
async def update_plugin_config(plugin_id: str, request: PluginConfigRequest):
    """
    Update configuration for a plugin.
    
    Args:
        plugin_id: Plugin identifier
        request: Configuration to apply
    
    Example body:
    {
        "config": {
            "api_key": "your-api-key",
            "location": "San Francisco, CA",
            "refresh_seconds": 300
        }
    }
    """
    if not PLUGIN_SYSTEM_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Plugin system is not available."
        )
    
    registry = get_plugin_registry()
    
    # Check if plugin exists
    if not registry.get_plugin(plugin_id):
        raise HTTPException(
            status_code=404,
            detail=f"Plugin not found: {plugin_id}"
        )
    
    # Validate configuration against manifest schema
    errors = registry.set_plugin_config(plugin_id, request.config)
    if errors:
        logger.error(f"Plugin '{plugin_id}' config validation failed: {errors}")
        raise HTTPException(
            status_code=400,
            detail={"errors": errors}
        )
    
    # Save to config file
    config_manager = get_config_manager()
    config_manager.set_plugin_config(plugin_id, request.config)
    
    # Reset services to pick up new config
    reset_display_service()
    reset_template_engine()
    
    logger.info(f"Plugin '{plugin_id}' configuration updated")
    
    # Return masked config
    updated = config_manager.get_plugin_config(plugin_id)
    
    return {
        "status": "success",
        "plugin_id": plugin_id,
        "config": config_manager._mask_sensitive(updated) if updated else {}
    }


@app.post("/plugins/{plugin_id}/enable")
async def enable_plugin(plugin_id: str):
    """
    Enable a plugin.
    
    Enables the plugin in both the registry and persists to config.
    """
    if not PLUGIN_SYSTEM_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Plugin system is not available."
        )
    
    registry = get_plugin_registry()
    
    if not registry.get_plugin(plugin_id):
        raise HTTPException(
            status_code=404,
            detail=f"Plugin not found: {plugin_id}"
        )
    
    # Enable in registry
    success = registry.enable_plugin(plugin_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to enable plugin: {plugin_id}"
        )
    
    # Persist to config
    config_manager = get_config_manager()
    config_manager.enable_plugin(plugin_id)
    
    # Reset services
    reset_display_service()
    reset_template_engine()
    
    logger.info(f"Plugin '{plugin_id}' enabled")
    
    return {
        "status": "success",
        "plugin_id": plugin_id,
        "enabled": True
    }


@app.post("/plugins/{plugin_id}/disable")
async def disable_plugin(plugin_id: str):
    """
    Disable a plugin.
    
    Disables the plugin in both the registry and persists to config.
    """
    if not PLUGIN_SYSTEM_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Plugin system is not available."
        )
    
    registry = get_plugin_registry()
    
    if not registry.get_plugin(plugin_id):
        raise HTTPException(
            status_code=404,
            detail=f"Plugin not found: {plugin_id}"
        )
    
    # Disable in registry
    success = registry.disable_plugin(plugin_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to disable plugin: {plugin_id}"
        )
    
    # Persist to config
    config_manager = get_config_manager()
    config_manager.disable_plugin(plugin_id)
    
    # Reset services
    reset_display_service()
    reset_template_engine()
    
    logger.info(f"Plugin '{plugin_id}' disabled")
    
    return {
        "status": "success",
        "plugin_id": plugin_id,
        "enabled": False
    }


@app.get("/plugins/{plugin_id}/data")
async def get_plugin_data(plugin_id: str):
    """
    Fetch current data from a plugin.
    
    Returns the plugin's latest data, formatted output, and status.
    """
    if not PLUGIN_SYSTEM_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Plugin system is not available."
        )
    
    registry = get_plugin_registry()
    
    if not registry.get_plugin(plugin_id):
        raise HTTPException(
            status_code=404,
            detail=f"Plugin not found: {plugin_id}"
        )
    
    if not registry.is_enabled(plugin_id):
        raise HTTPException(
            status_code=400,
            detail=f"Plugin not enabled: {plugin_id}"
        )
    
    result = registry.fetch_plugin_data(plugin_id)

    # Return 503 when plugin data is unavailable (e.g. not configured, auth failure)
    # so monitoring (Grafana) and request log show it as an error for triage
    if not result.available:
        raise HTTPException(
            status_code=503,
            detail=result.error or "Plugin data not available"
        )

    return {
        "plugin_id": plugin_id,
        "available": result.available,
        "data": result.data,
        "formatted": result.formatted,
        "error": result.error
    }


@app.get("/plugins/{plugin_id}/variables")
async def get_plugin_variables(plugin_id: str):
    """
    Get template variables exposed by a plugin.
    
    Returns the variables schema for use in the template editor.
    """
    if not PLUGIN_SYSTEM_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Plugin system is not available."
        )
    
    registry = get_plugin_registry()
    manifest = registry.get_manifest(plugin_id)
    
    if not manifest:
        raise HTTPException(
            status_code=404,
            detail=f"Plugin not found: {plugin_id}"
        )
    
    return {
        "plugin_id": plugin_id,
        "variables": manifest.raw.get("variables", {}),
        "max_lengths": manifest.max_lengths,
        "color_rules_schema": manifest.raw.get("color_rules_schema", {})
    }


# ── Plugin Demo Pages ────────────────────────────────────────────────────────


@app.get("/plugins/{plugin_id}/demo-page")
async def get_plugin_demo_page(plugin_id: str):
    """
    Check whether a demo page exists for this plugin.

    Returns ``exists: true`` and the page id when one is found.
    """
    if not PLUGIN_SYSTEM_AVAILABLE:
        raise HTTPException(status_code=503, detail="Plugin system is not available.")

    registry = get_plugin_registry()
    manifest = registry.get_manifest(plugin_id)
    if not manifest:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")

    if manifest.demo is None:
        return {"exists": False, "page_id": None, "has_demo_template": False}

    page_service = get_page_service()
    demo_page = page_service.get_demo_page(plugin_id)
    return {
        "exists": demo_page is not None,
        "page_id": demo_page.id if demo_page else None,
        "has_demo_template": True,
    }


@app.post("/plugins/{plugin_id}/demo-page")
async def create_plugin_demo_page(plugin_id: str):
    """
    Create (or recreate) the demo page for a plugin.

    The demo page is a singleton per plugin -- calling this endpoint when a
    demo page already exists will delete the old one and create a fresh copy.
    """
    if not PLUGIN_SYSTEM_AVAILABLE:
        raise HTTPException(status_code=503, detail="Plugin system is not available.")

    registry = get_plugin_registry()
    manifest = registry.get_manifest(plugin_id)
    if not manifest:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")

    if manifest.demo is None:
        raise HTTPException(
            status_code=400,
            detail=f"Plugin '{plugin_id}' does not include a demo page template.",
        )

    # Check that required settings are configured
    settings_schema = manifest.settings_schema
    required_fields = settings_schema.get("required", [])
    if required_fields:
        config_manager = get_config_manager()
        plugin_config = config_manager.get_plugin_config(plugin_id) or {}
        missing = [
            f for f in required_fields
            if f != "enabled" and not plugin_config.get(f)
        ]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Required settings not configured: {', '.join(missing)}. "
                       f"Configure them first before creating a demo page.",
            )

    page_service = get_page_service()
    page, recreated = page_service.create_demo_page(plugin_id, manifest.demo)

    return {
        "status": "recreated" if recreated else "created",
        "page": page.model_dump(),
    }


# ── Plugin Instances ────────────────────────────────────────────────────────


class PluginInstanceCreateRequest(BaseModel):
    """Request body for creating a new plugin instance."""
    label: str


@app.get("/plugins/{plugin_id}/instances")
async def list_plugin_instances(plugin_id: str):
    """
    List all instances of a plugin.

    Returns the instances (excluding the base) for the given plugin.
    """
    if not PLUGIN_SYSTEM_AVAILABLE:
        raise HTTPException(
            status_code=503, detail="Plugin system is not available."
        )

    registry = get_plugin_registry()

    # Resolve base plugin id (strip instance label if present)
    base_id, _ = registry.parse_instance_key(plugin_id)

    if not registry.get_plugin(base_id):
        raise HTTPException(
            status_code=404,
            detail=f"Plugin not found: {base_id}"
        )

    instances = registry.list_instances(base_id)

    return {
        "plugin_id": base_id,
        "instances": instances,
        "total": len(instances),
    }


@app.post("/plugins/{plugin_id}/instances")
async def create_plugin_instance(plugin_id: str, request: PluginInstanceCreateRequest):
    """
    Create a new instance of a plugin.

    The new instance starts disabled with an empty configuration.
    It can be configured and enabled independently via the standard
    plugin config/enable endpoints using the compound key
    ``{plugin_id}:{label}``.
    """
    if not PLUGIN_SYSTEM_AVAILABLE:
        raise HTTPException(
            status_code=503, detail="Plugin system is not available."
        )

    registry = get_plugin_registry()

    # Resolve base plugin id
    base_id, _ = registry.parse_instance_key(plugin_id)

    if not registry.get_plugin(base_id):
        raise HTTPException(
            status_code=404,
            detail=f"Plugin not found: {base_id}"
        )

    errors = registry.create_instance(base_id, request.label)
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    compound_key = registry.make_instance_key(base_id, request.label)

    # Persist empty config so the instance survives restarts
    config_manager = get_config_manager()
    config_manager.set_plugin_config(compound_key, {"enabled": False})

    # Reset services so the new instance is available to templates immediately
    reset_display_service()
    reset_template_engine()

    logger.info(f"Created plugin instance: {compound_key}")

    return {
        "status": "success",
        "plugin_id": base_id,
        "instance_label": request.label,
        "instance_key": compound_key,
        "message": f"Instance '{request.label}' created for plugin '{base_id}'.",
    }


@app.delete("/plugins/{plugin_id}/instances/{instance_label}")
async def delete_plugin_instance(plugin_id: str, instance_label: str):
    """
    Delete a plugin instance.

    Removes the instance from the registry and its persisted configuration.
    """
    if not PLUGIN_SYSTEM_AVAILABLE:
        raise HTTPException(
            status_code=503, detail="Plugin system is not available."
        )

    registry = get_plugin_registry()

    # Resolve base plugin id
    base_id, _ = registry.parse_instance_key(plugin_id)

    errors = registry.delete_instance(base_id, instance_label)
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    compound_key = registry.make_instance_key(base_id, instance_label)

    # Remove persisted config
    config_manager = get_config_manager()
    config_manager.delete_plugin_config(compound_key)

    # Reset services
    reset_display_service()
    reset_template_engine()

    logger.info(f"Deleted plugin instance: {compound_key}")

    return {
        "status": "success",
        "plugin_id": base_id,
        "instance_label": instance_label,
        "instance_key": compound_key,
        "message": f"Instance '{instance_label}' of plugin '{base_id}' deleted.",
    }


# ── External Plugin Management ──────────────────────────────────────────────


class ExternalPluginInstallRequest(BaseModel):
    """Request body for installing an external plugin."""
    repository: str
    plugin_id: Optional[str] = None
    branch: str = ""


@app.post("/plugins/registry/{plugin_id}/install")
async def install_registry_plugin(plugin_id: str):
    """
    Install a plugin from the curated registry by its id.
    """
    if not PLUGIN_SYSTEM_AVAILABLE:
        raise HTTPException(
            status_code=503, detail="Plugin system is not available."
        )

    registry = get_plugin_registry()
    errors = registry.install_from_registry(plugin_id)

    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    return {
        "status": "success",
        "plugin_id": plugin_id,
        "message": f"Plugin '{plugin_id}' installed from registry.",
    }


@app.post("/plugins/install")
async def install_external_plugin(request: ExternalPluginInstallRequest):
    """
    Install a plugin from a public git repository URL.

    The repository does not need to follow the ``fiestaboard-plugin--``
    naming convention (that requirement only applies to registry plugins).
    """
    if not PLUGIN_SYSTEM_AVAILABLE:
        raise HTTPException(
            status_code=503, detail="Plugin system is not available."
        )

    # Constrain user-provided branch names to a small safe subset so command
    # arguments are selected from trusted values at this API boundary.
    safe_branch = request.branch or ""
    allowed_branches = {"", "main", "master", "develop"}
    if safe_branch not in allowed_branches:
        raise HTTPException(
            status_code=400,
            detail="branch must be one of: main, master, develop",
        )

    registry = get_plugin_registry()
    errors = registry.install_from_git(
        request.repository,
        plugin_id=request.plugin_id,
        branch=safe_branch,
    )

    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    # Derive the final plugin id
    pid = request.plugin_id
    if pid is None:
        from .plugins.sources import repo_name_from_url, plugin_id_from_repo_name
        pid = plugin_id_from_repo_name(repo_name_from_url(request.repository))

    return {
        "status": "success",
        "plugin_id": pid,
        "message": f"Plugin '{pid}' installed from {request.repository}.",
    }


@app.delete("/plugins/{plugin_id}/uninstall")
async def uninstall_external_plugin(plugin_id: str):
    """
    Uninstall an external (non-built-in) plugin.

    Built-in plugins shipped with FiestaBoard cannot be uninstalled.
    """
    if not PLUGIN_SYSTEM_AVAILABLE:
        raise HTTPException(
            status_code=503, detail="Plugin system is not available."
        )

    registry = get_plugin_registry()

    # Collect instance compound keys before uninstall so we can purge their configs
    instance_keys = [
        p["id"]
        for p in registry.list_plugins()
        if p.get("base_plugin_id") == plugin_id and p.get("instance_label")
    ]

    errors = registry.uninstall_external_plugin(plugin_id)

    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    config_manager = get_config_manager()
    for compound_key in instance_keys:
        config_manager.delete_plugin_config(compound_key)

    return {
        "status": "success",
        "plugin_id": plugin_id,
        "message": f"Plugin '{plugin_id}' has been uninstalled.",
    }


@app.post("/plugins/updates/check")
async def trigger_plugin_update_check():
    """
    Trigger an immediate update check for all external plugins.

    This runs synchronously and may take a few seconds per plugin
    (one ``git ls-remote`` per installed external plugin).
    """
    if not PLUGIN_SYSTEM_AVAILABLE:
        raise HTTPException(
            status_code=503, detail="Plugin system is not available."
        )

    registry = get_plugin_registry()
    results = registry.check_for_updates()
    plugins_with_updates = [pid for pid, has_update in results.items() if has_update]
    return {
        "checked": len(results),
        "updates_available": plugins_with_updates,
    }


@app.post("/plugins/{plugin_id}/update")
async def update_plugin(plugin_id: str):
    """
    Fetch the latest commits for an external plugin from its remote and reload it.

    Built-in plugins cannot be updated via this endpoint.
    """
    if not PLUGIN_SYSTEM_AVAILABLE:
        raise HTTPException(
            status_code=503, detail="Plugin system is not available."
        )

    registry = get_plugin_registry()
    source = registry.get_plugin_source(plugin_id)

    if source is None:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found.")

    if source.source_type == "builtin":
        raise HTTPException(
            status_code=400,
            detail=f"Plugin '{plugin_id}' is a built-in plugin and cannot be updated this way.",
        )

    if not source.local_path:
        raise HTTPException(
            status_code=400,
            detail=f"Plugin '{plugin_id}' has no local path for updating.",
        )

    from pathlib import Path as _Path
    import os as _os
    from .plugins.sources import get_external_plugins_dir
    local_path = _Path(source.local_path)
    # Verify local_path is within the external plugins directory before
    # passing it to subprocess calls — canonical path-injection barrier.
    _ext_root = _os.path.realpath(str(get_external_plugins_dir()))
    _real_local = _os.path.realpath(str(local_path))
    try:
        _common = _os.path.commonpath([_ext_root, _real_local])
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid plugin path.")
    if _common != _ext_root or _real_local == _ext_root:
        raise HTTPException(status_code=400, detail="Invalid plugin path.")
    local_path = _Path(_real_local)

    if not (local_path / ".git").is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"Plugin '{plugin_id}' is not a git repository.",
        )

    from .plugins.sources import clone_or_update_repo
    # repo_url is not needed for the update path (fetch uses existing origin remote)
    ok, err = clone_or_update_repo("", local_path)
    if not ok:
        raise HTTPException(status_code=500, detail=f"Update failed: {err}")

    reloaded = registry.reload_plugin(plugin_id)
    if reloaded is None:
        errors = registry.get_load_errors().get(plugin_id, [])
        detail = "; ".join(errors) if errors else "Plugin failed to reload after update."
        raise HTTPException(status_code=500, detail=detail)

    registry._update_status.pop(plugin_id, None)

    return {
        "status": "success",
        "plugin_id": plugin_id,
        "message": f"Plugin '{plugin_id}' has been updated and reloaded.",
    }


@app.post("/plugins/updates/apply")
async def apply_all_plugin_updates():
    """
    Fetch and reload all external plugins that have a pending update.

    Uses the cached update status from the last check — call
    ``POST /plugins/updates/check`` first if you want a fresh scan before
    applying.  Returns 200 even when some plugins fail so the caller can
    inspect partial results.
    """
    if not PLUGIN_SYSTEM_AVAILABLE:
        raise HTTPException(
            status_code=503, detail="Plugin system is not available."
        )

    registry = get_plugin_registry()
    pending = [
        pid for pid, has_update in registry.get_update_status().items() if has_update
    ]

    if not pending:
        return {"updated": [], "failed": {}, "message": "No updates available."}

    from pathlib import Path as _Path
    import os as _os
    from .plugins.sources import clone_or_update_repo, get_external_plugins_dir

    updated: list = []
    failed: dict = {}
    _ext_root = _os.path.realpath(str(get_external_plugins_dir()))

    for plugin_id in pending:
        source = registry.get_plugin_source(plugin_id)
        if source is None or not source.local_path:
            failed[plugin_id] = "Plugin source not found."
            continue

        _real_local = _os.path.realpath(str(_Path(source.local_path)))
        try:
            _common = _os.path.commonpath([_ext_root, _real_local])
        except ValueError:
            failed[plugin_id] = "Invalid plugin path."
            continue
        if _common != _ext_root or _real_local == _ext_root:
            failed[plugin_id] = "Invalid plugin path."
            continue
        local_path = _Path(_real_local)
        if not (local_path / ".git").is_dir():
            failed[plugin_id] = "Plugin is not a git repository."
            continue

        ok, err = clone_or_update_repo("", local_path)
        if not ok:
            failed[plugin_id] = f"git fetch failed: {err}"
            continue

        reloaded = registry.reload_plugin(plugin_id)
        if reloaded is None:
            errors = registry.get_load_errors().get(plugin_id, [])
            failed[plugin_id] = "; ".join(errors) if errors else "Reload failed."
            continue

        registry._update_status.pop(plugin_id, None)
        updated.append(plugin_id)
        logger.info("Bulk update: applied update for plugin '%s'", plugin_id)

    return {
        "updated": updated,
        "failed": failed,
        "message": f"Updated {len(updated)} plugin(s); {len(failed)} failed.",
    }


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
        raise HTTPException(
            status_code=503, detail="Plugin system is not available."
        )

    from .triggers.service import get_trigger_service
    registry = get_plugin_registry()
    trigger_service = get_trigger_service()

    checked = 0
    for plugin_id, plugin in registry.trigger_plugins.items():
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
    import requests as req
    import defusedxml.ElementTree as DefusedET

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
    _validate_request_url(url)
    # Re-derive url from a strict allowlist regex so the downstream HTTP call is not
    # tracked as tainted by static-analysis tools (py/full-ssrf).
    _safe_url_m = re.fullmatch(
        r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+",
        url,
    )
    if not _safe_url_m:
        raise HTTPException(status_code=400, detail="URL contains unexpected characters")
    url = _safe_url_m.group(0)

    host = urlparse(url).hostname or ""
    allowed_hosts = _get_generic_data_allowed_hosts()
    if not allowed_hosts:
        raise HTTPException(
            status_code=400,
            detail="No allowed hosts configured for generic-data test fetch",
        )
    if not _is_host_allowed(host, allowed_hosts):
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
            kwargs["data"] = (
                interpolate_string(body, _interp_vars)
                if isinstance(body, str)
                else body
            )

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
        raise HTTPException(status_code=504, detail="Request timed out")
    except req.exceptions.ConnectionError:
        raise HTTPException(status_code=502, detail="Connection error — check the URL")
    except req.exceptions.HTTPError:
        # Don't echo the upstream exception (URL/headers/status) back to the
        # caller — generic message is enough for a "test fetch" feature.
        raise HTTPException(status_code=502, detail="HTTP error from remote service")
    except Exception:
        logger.exception("generic-data test-fetch failed")
        raise HTTPException(status_code=500, detail="Failed to fetch data")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

