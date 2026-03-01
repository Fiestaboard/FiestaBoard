"""REST API server for FiestaBoard Display Service."""

import logging
import logging.handlers
import threading
import time
import os
import json
import requests
from typing import Optional, Dict, Any, List
from collections import deque
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, Body, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Load environment variables from .env file
load_dotenv()

from . import __version__
from .main import DisplayService
from .config import Config
from .config_manager import get_config_manager
from .displays.service import get_display_service, reset_display_service, DisplayResult
from .settings.service import get_settings_service, VALID_STRATEGIES, VALID_OUTPUT_TARGETS
from .pages.service import get_page_service, DeleteResult
from .pages.models import PageCreate, PageUpdate
from .schedules.service import get_schedule_service
from .schedules.models import ScheduleCreate, ScheduleUpdate
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

# Global service instance
_service: Optional[DisplayService] = None
_service_lock = threading.Lock()
_service_thread: Optional[threading.Thread] = None
_service_running = False
_dev_mode = False  # When True, preview only - don't send to board
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


# Create FastAPI app
app = FastAPI(
    title="FiestaBoard Display API",
    description="REST API for controlling and monitoring the FiestaBoard Display Service",
    version=__version__
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
    global _service_running, _service, _service_start_time
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


@app.on_event("startup")
async def startup_event():
    """Initialize service on startup."""
    global _dev_mode, _service_thread, _shutting_down
    _shutting_down = False
    logger.info("API server starting up...")
    
    # Set up file-based logging
    _setup_file_logging()
    
    # Auto-enable dev mode in local development (when not in production)
    # Check if we're in a development environment
    is_production = os.getenv("PRODUCTION", "false").lower() == "true"
    if not is_production:
        _dev_mode = True
        logger.info("Dev mode auto-enabled for local development")
    
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


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    global _service, _service_running, _shutting_down
    logger.info("API server shutting down...")
    _shutting_down = True
    _service_running = False
    if _service:
        _service.running = False

    # Stop mDNS advertisement
    try:
        from .system.mdns import stop_mdns
        stop_mdns()
    except Exception:
        pass


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

GITHUB_PACKAGE_URL = "https://github.com/Fiestaboard/FiestaBoard/pkgs/container/fiestaboard"
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
        latest_version = _check_dockerhub_for_latest()
        
        if not latest_version:
            latest_version = _check_github_releases_for_latest()
        
        if latest_version:
            update_available = _is_newer_version(latest_version, __version__)
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
    global _dev_mode
    service = get_service()
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    settings_service = get_settings_service()
    
    status = StatusResponse(
        running=_service_running,
        initialized=service is not None,
        config_summary=Config.get_summary()
    )
    # Add dev mode to config summary for UI
    status.config_summary["dev_mode"] = _dev_mode
    # Add active page ID to config summary
    status.config_summary["active_page_id"] = settings_service.get_active_page_id()
    return status


@app.post("/start")
async def start_service(background_tasks: BackgroundTasks):
    """Start the background service."""
    global _service_thread, _service_running, _service, _shutting_down
    
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
    time.sleep(0.5)
    
    if _service_running:
        return {"status": "started", "message": "Service started successfully"}
    else:
        raise HTTPException(status_code=500, detail="Service failed to start - check logs for details")


@app.post("/stop")
async def stop_service():
    """Stop the background service."""
    global _service_running, _service, _shutting_down
    
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
    global _dev_mode
    service = get_service()
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        service.fetch_and_display(dev_mode=_dev_mode)
        if _dev_mode:
            return {
                "status": "success", 
                "message": "Display previewed (dev mode enabled - not sent to board)",
                "dev_mode": True
            }
        return {"status": "success", "message": "Display refreshed successfully"}
    except Exception as e:
        logger.error(f"Error refreshing display: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to refresh display: {str(e)}")


@app.post("/send-message")
async def send_message(request: MessageRequest):
    """Send a custom message to the board."""
    global _dev_mode
    service = get_service()
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    if _dev_mode:
        logger.info(f"[DEV MODE] Would send message (not actually sending):\n{request.text}")
        return {
            "status": "success", 
            "message": "Message previewed (dev mode enabled - not sent to board)",
            "dev_mode": True
        }
    
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
    
    global _dev_mode
    
    if _dev_mode:
        logger.info("[DEV MODE] Would send welcome message (not actually sending)")
        return {
            "status": "success", 
            "message": "Welcome message previewed (dev mode enabled - not sent to board)",
            "dev_mode": True
        }
    
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
        # Colorful welcome template (matches pages.json welcome page)
        welcome_template = [
            "{{red}}{{red}}{{orange}}{{yellow}}{{orange}}{{red}}{{violet}}{{red}}{{orange}}{{yellow}}{{red}}{{orange}}{{violet}}{{yellow}}{{red}}{{orange}}{{red}}{{yellow}}{{violet}}{{orange}}{{red}}{{yellow}}",
            "{{orange}}{{yellow}}{{red}}{{violet}}{{yellow}}{{orange}}{{red}}{{yellow}}{{violet}}{{orange}}{{yellow}}{{red}}{{orange}}{{violet}}{{yellow}}{{orange}}{{red}}{{violet}}{{yellow}}{{red}}{{orange}}{{red}}",
            "HIYA FROM FIESTABOARD",
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


@app.get("/config/validate")
async def validate_config():
    """
    Validate the current configuration.
    
    Returns validation status, first-run detection, and any errors found.
    Used by the setup wizard to determine if onboarding is needed.
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
    from .board_client import BoardClient
    
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
        # Create temporary client with provided credentials
        client = BoardClient(
            api_key=api_key,
            host=host,
            use_cloud=use_cloud,
            skip_unchanged=False
        )
        
        # Test the connection by reading current message
        result = client.read_current_message()
        
        if result is not None:
            logger.info(f"Board connection test successful ({api_mode} mode)")
            return {
                "success": True,
                "message": "Successfully connected to your board!",
                "api_mode": api_mode
            }
        else:
            logger.warning(f"Board connection test failed - no response ({api_mode} mode)")
            return {
                "success": False,
                "message": "Could not read from board - please check your credentials",
                "error": "Board returned no data"
            }
            
    except ValueError as e:
        # Invalid configuration (missing required fields)
        logger.warning(f"Board connection test failed - invalid config: {e}")
        return {
            "success": False,
            "message": str(e),
            "error": f"Configuration error: {str(e)}"
        }
    except Exception as e:
        # Network or other errors
        error_msg = str(e)
        
        # Provide user-friendly error messages
        if "Connection refused" in error_msg or "Failed to establish" in error_msg:
            friendly_msg = "Could not connect to board. Please check the IP address and ensure the board is on the same network."
        elif "401" in error_msg or "403" in error_msg or "Unauthorized" in error_msg:
            friendly_msg = "Invalid API key. Please check your credentials."
        elif "timeout" in error_msg.lower():
            friendly_msg = "Connection timed out. Please check the IP address and network connection."
        else:
            friendly_msg = f"Connection failed: {error_msg}"
        
        logger.error(f"Board connection test error: {e}")
        return {
            "success": False,
            "message": friendly_msg,
            "error": error_msg
        }


class EnablementTokenRequest(BaseModel):
    """Request model for exchanging enablement token for API key."""
    host: str
    enablement_token: str


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
    
    # Build the URL for the local enablement endpoint
    url = f"http://{request.host}:7000/local-api/enablement"
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
                    "error": f"Response: {data}"
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
                "error": response.text
            }
            
    except http_requests.exceptions.ConnectionError as e:
        logger.error(f"Local API enablement connection error: {e}")
        return {
            "success": False,
            "message": "Could not connect to board. Please check the IP address and ensure the board is on the same network.",
            "error": str(e)
        }
    except http_requests.exceptions.Timeout as e:
        logger.error(f"Local API enablement timeout: {e}")
        return {
            "success": False,
            "message": "Connection timed out. Please check the IP address and try again.",
            "error": str(e)
        }
    except Exception as e:
        logger.error(f"Local API enablement error: {e}")
        return {
            "success": False,
            "message": f"Failed to enable local API: {str(e)}",
            "error": str(e)
        }


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
                uses the configured default based on dev_mode.
    
    Returns:
        Result of the send operation.
    """
    global _dev_mode
    
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
        # Use settings-based logic
        send_to_board = settings_service.should_send_to_board(_dev_mode)
    else:
        send_to_board = target in ["board", "both"]
    
    # Send to board if appropriate (explicit target=board/both can bypass dev_mode)
    sent_to_board = False
    explicit_target = target is not None and target in ["board", "both"]
    if send_to_board and (explicit_target or not _dev_mode):
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
        "target": target or ("ui" if _dev_mode else settings_service.get_output_settings().target),
        "dev_mode": _dev_mode
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
        # Get station information
        station_info = BayWheelsSource._get_station_information()
        
        # Get current status
        response = requests.get(STATION_STATUS_URL, timeout=10)
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
        stations = BayWheelsSource.find_stations_near_location(lat, lng, radius, limit)
        
        # Get current status for these stations
        response = requests.get(STATION_STATUS_URL, timeout=10)
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
        
        geocode_response = requests.get(geocode_url, params=geocode_params, headers=geocode_headers, timeout=10)
        geocode_response.raise_for_status()
        geocode_data = geocode_response.json()
        
        if not geocode_data:
            raise HTTPException(status_code=404, detail=f"Address not found: {address}")
        
        location = geocode_data[0]
        lat = float(location["lat"])
        lng = float(location["lon"])
        
        # Find nearby stations
        stations = BayWheelsSource.find_stations_near_location(lat, lng, radius, limit)
        
        # Get current status for these stations
        response = requests.get(STATION_STATUS_URL, timeout=10)
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
        data = _queue_times_get("/parks.json")
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
        data = _queue_times_get(f"/parks/{park_id}/queue_times.json")
        rides = []
        for land in data.get("lands", []):
            for ride in land.get("rides", []):
                rides.append({"id": ride["id"], "name": ride["name"]})
        rides.sort(key=lambda x: (x.get("name") or "").lower())
        return rides
    except HTTPException:
        raise
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
    cache_key = "_muni_stops_cache"
    cache_time_key = "_muni_stops_cache_time"
    CACHE_TTL = 24 * 60 * 60  # 24 hours
    
    # Check if we have cached data
    if not hasattr(list_all_muni_stops, cache_key):
        setattr(list_all_muni_stops, cache_key, None)
        setattr(list_all_muni_stops, cache_time_key, 0)
    
    cached_data = getattr(list_all_muni_stops, cache_key)
    cache_time = getattr(list_all_muni_stops, cache_time_key)
    current_time = time.time()
    
    # Return cached data if still valid
    if cached_data and (current_time - cache_time) < CACHE_TTL:
        return cached_data
    
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
        
        response = requests.get(url, params=params, timeout=15)
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
        setattr(list_all_muni_stops, cache_key, result)
        setattr(list_all_muni_stops, cache_time_key, current_time)
        
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
        
        geocode_response = requests.get(geocode_url, params=geocode_params, headers=geocode_headers, timeout=10)
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
        from datetime import datetime
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
        raise HTTPException(status_code=500, detail=str(e))


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
        
        response = requests.get(geocode_url, params=geocode_params, headers=geocode_headers, timeout=10)
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
        
        # Fetch traffic data to validate
        data = traffic_source.fetch_traffic_data()
        
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
            "error": str(e)
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
    global _dev_mode
    settings_service = get_settings_service()
    output = settings_service.get_output_settings()
    return {
        "target": output.target,
        "dev_mode": _dev_mode,
        "effective_target": "ui" if _dev_mode else output.target,
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
    
    When a page is set, it will be immediately rendered and sent to the board
    (unless dev_mode is enabled).
    """
    global _dev_mode
    
    settings_service = get_settings_service()
    page_service = get_page_service()
    service = get_service()
    
    page_id = request.get("page_id")
    
    # Validate page exists if not clearing
    page = None
    if page_id is not None:
        page = page_service.get_page(page_id)
        if not page:
            raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")
    
    # Set the active page
    settings_service.set_active_page_id(page_id)
    
    # Immediately send to board if a page is set
    sent_to_board = False
    if page_id and page and service and service.vb_client and not _dev_mode:
        # Force fresh render when setting active page
        result = page_service.preview_page(page_id, force_refresh=True)
        if result and result.available:
            # Use page-level transitions if set, otherwise fall back to system defaults
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
        "dev_mode": _dev_mode
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
    - service status (running, dev_mode)
    """
    global _service_running, _dev_mode
    
    settings_service = get_settings_service()
    config_manager = get_config_manager()
    
    # Get silence schedule config
    silence_config = config_manager.get_plugin_config("silence_schedule")
    
    # Get all other settings
    general = config_manager.get_general()
    polling = settings_service.get_polling_settings()
    transitions = settings_service.get_transition_settings()
    output = settings_service.get_output_settings()
    board = settings_service.get_board_settings()
    
    return {
        "general": general,
        "silence_schedule": silence_config or {},
        "polling": {
            "interval_seconds": polling.interval_seconds
        },
        "transitions": transitions.to_dict(),
        "output": output.to_dict(),
        "board": board.to_dict(),
        "status": {
            "running": _service_running,
            "dev_mode": _dev_mode
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
    global _service_start_time
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
    global _dev_mode
    
    client = _get_board_client()
    if not client:
        raise HTTPException(status_code=400, detail="Board not configured")
    
    settings_service = get_settings_service()
    send_to_board = settings_service.should_send_to_board(_dev_mode)
    
    if not send_to_board:
        return {
            "status": "success",
            "message": "Board blank (preview only - dev mode active)"
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
    global _dev_mode
    
    character_code = request.get("character_code")
    if character_code is None:
        raise HTTPException(status_code=400, detail="character_code is required")
    
    if not isinstance(character_code, int) or character_code < 0 or character_code > 71:
        raise HTTPException(status_code=400, detail="character_code must be 0-71")
    
    client = _get_board_client()
    if not client:
        raise HTTPException(status_code=400, detail="Board not configured")
    
    settings_service = get_settings_service()
    send_to_board = settings_service.should_send_to_board(_dev_mode)
    
    if not send_to_board:
        return {
            "status": "success",
            "message": f"Board filled with character {character_code} (preview only - dev mode active)"
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
    global _dev_mode
    
    client = _get_board_client()
    if not client:
        raise HTTPException(status_code=400, detail="Board not configured")
    
    settings_service = get_settings_service()
    send_to_board = settings_service.should_send_to_board(_dev_mode)
    
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
            "message": "Debug info displayed (preview only - dev mode active)",
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
        logger.error(f"Error testing connection: {e}")
        return {
            "status": "error",
            "message": str(e),
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
    global _service_running, _dev_mode
    
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
        "dev_mode": _dev_mode
    }


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
    global _dev_mode
    
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
        send_to_board = settings_service.should_send_to_board(_dev_mode)
    else:
        send_to_board = target in ["board", "both"]
    
    # Send to board if appropriate (explicit target=board/both can bypass dev_mode)
    sent_to_board = False
    explicit_target = target is not None and target in ["board", "both"]
    if send_to_board and (explicit_target or not _dev_mode):
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
        "target": target or ("ui" if _dev_mode else settings_service.get_output_settings().target),
        "dev_mode": _dev_mode
    }


# =============================================================================
# Schedule Endpoints
# =============================================================================

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
            "schedules": [s.model_dump() for s in schedules],
            "total": len(schedules),
            "default_page_id": None,
            "enabled": False,
        }
    
    return {
        "schedules": [s.model_dump() for s in schedules],
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
        return schedule.model_dump()
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
    
    return schedule.model_dump()


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
        return schedule.model_dump()
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
# Template Endpoints
# =============================================================================

@app.get("/templates/variables")
async def get_template_variables():
    """
    Get available template variables by source.
    
    Returns a dictionary mapping source names to available field names.
    Use these in templates as {{source.field}}, e.g., {{weather.temperature}}.
    Also includes max character lengths for validation.
    """
    template_engine = get_template_engine()
    return {
        "variables": template_engine.get_available_variables(),
        "max_lengths": template_engine.get_variable_max_lengths(),
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
    
    # Early return for empty templates to avoid unnecessary processing
    if isinstance(template, list):
        if not template or all(not line.strip() for line in template):
            return {
                "rendered": "\n".join([""] * 6),
                "lines": [""] * 6,
                "line_count": 6
            }
    elif isinstance(template, str) and not template.strip():
        return {
            "rendered": "\n".join([""] * 6),
            "lines": [""] * 6,
            "line_count": 6
        }
    
    template_engine = get_template_engine()
    line_metadata = request.get("line_metadata")
    
    try:
        if isinstance(template, list):
            logger.info(f"Rendering template lines: {template}")
            rendered = template_engine.render_lines(template, line_metadata=line_metadata)
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
def render_template_live(request: dict):
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

    # Render the template
    try:
        if isinstance(template, list):
            if not template or all(not line.strip() for line in template):
                return {
                    "rendered": "\n".join([""] * 6),
                    "lines": [""] * 6,
                    "line_count": 6,
                    "sent_to_board": False,
                    "board_id": board_id,
                }
            rendered = template_engine.render_lines(template, line_metadata=line_metadata)
        else:
            if not template.strip():
                return {
                    "rendered": "\n".join([""] * 6),
                    "lines": [""] * 6,
                    "line_count": 6,
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
                success, was_sent = client.send_characters(
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


@app.get("/dev-mode")
async def get_dev_mode():
    """Get current dev mode status."""
    global _dev_mode
    return {"dev_mode": _dev_mode}


@app.post("/dev-mode")
async def set_dev_mode(request: dict):
    """Enable or disable dev mode (preview only, no actual sending)."""
    global _dev_mode
    if "dev_mode" in request:
        _dev_mode = bool(request["dev_mode"])
        logger.info(f"Dev mode {'enabled' if _dev_mode else 'disabled'}")
        return {
            "status": "success",
            "dev_mode": _dev_mode,
            "message": f"Dev mode {'enabled' if _dev_mode else 'disabled'}"
        }
    raise HTTPException(status_code=400, detail="dev_mode parameter required")


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
    global _dev_mode
    service = get_service()
    if not service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    if _dev_mode:
        return {
            "status": "success", 
            "message": "Force refresh previewed (dev mode enabled - not sent to board)",
            "dev_mode": True
        }
    
    # Clear cache to force send
    if service.vb_client:
        service.vb_client.clear_cache()
    
    try:
        service.fetch_and_display(dev_mode=False)
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
        response = requests.get(
            f"{ha_source.base_url}/api/states",
            headers=ha_source.headers,
            timeout=ha_source.timeout
        )
        response.raise_for_status()
        entities = response.json()
        
        # Transform to simpler format for UI
        return {
            "entities": [
                {
                    "entity_id": e["entity_id"],
                    "state": e["state"],
                    "attributes": e["attributes"],
                    "friendly_name": e["attributes"].get("friendly_name", e["entity_id"])
                }
                for e in entities
            ]
        }
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
        "documentation": manifest.documentation
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

