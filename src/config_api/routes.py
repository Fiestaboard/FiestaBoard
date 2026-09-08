"""FastAPI router for the ``/config`` endpoints.

The eleven handlers here were moved verbatim from ``src/api_server.py``
(Phase 2, Task 8) and then converted to
``docs/internal/reference/API_CONVENTIONS.md``: a declared ``response_model``
on every route, Pydantic request bodies instead of bare ``dict``s, a single
``{"detail": str}`` error contract, and the 4xx each route can actually raise
declared in ``responses=``. ``tests/conventions_manifest.json`` lists ``config``
so a regression fails the build.

Collaborators resolve from their canonical homes at **module import time**, so
this module never loads ``src.api_server``
(``tests/test_config_decoupled.py`` asserts that in a fresh interpreter).
Tests that need to stub a collaborator patch it where this module binds it —
``src.config_api.routes.<name>``.

``config`` carries eight checked-in exceptions to the ratchet, all in the
manifest with reasons: six ``declared_errors`` (this domain is read-heavy —
six routes are parameterless reads of local state with no failure path) and
two ``no_200_on_failure`` (the probe endpoints' declared verdict contract,
#1887).
"""

from __future__ import annotations

import asyncio
import logging

import requests
from fastapi import APIRouter, HTTPException, Response

from src.api_errors import errors
from src.board_guards import primary_board_entry, validate_board_host, validate_board_host_is_local_network
from src.config import Config
from src.config_manager import get_config_manager
from src.display_runtime import get_service, reinitialize_board_clients
from src.settings.service import get_settings_service
from src.time_service import reset_time_service

from .models import (
    BoardConfigResetResponse,
    BoardConfigResponse,
    BoardConfigUpdate,
    BoardConfigUpdateResponse,
    BoardScanRequest,
    BoardScanResponse,
    BoardTestRequest,
    BoardTestResponse,
    ConfigSummaryResponse,
    ConfigValidationResponse,
    EnableLocalApiResponse,
    EnablementTokenRequest,
    FullConfigResponse,
    GeneralConfig,
    GeneralConfigUpdate,
    LegacyBoardConfig,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["config"])


@router.get("/config", response_model=ConfigSummaryResponse)
async def get_config():
    """Get current configuration summary (without sensitive keys)."""
    return Config.get_summary()


# =============================================================================
# Configuration Management Endpoints
# =============================================================================


@router.get("/config/full", response_model=FullConfigResponse)
async def get_full_config():
    """
    Get the full configuration with sensitive fields masked.

    Returns the complete config structure including all features and settings.
    API keys and passwords are masked with '***'.
    """
    config_manager = get_config_manager()
    return config_manager.get_all_masked()


# Deprecated /config/board shim (issue #1760): board credentials are unified
# on the settings boards store. These endpoints keep their legacy wire shapes
# during deprecation but read from and write through the settings service —
# the config.json board block is left on disk untouched as a rollback copy
# for older versions and is never read at runtime.
_CONFIG_BOARD_SUCCESSOR_LINK = '</settings/board>; rel="successor-version"'
_LEGACY_BOARD_CONNECTION_FIELDS = ("api_mode", "local_api_key", "cloud_key", "note_array_token", "host")
_LEGACY_BOARD_SENSITIVE_FIELDS = ("local_api_key", "cloud_key", "note_array_token")


def _legacy_board_config_view() -> dict:
    """Project the primary settings board into the legacy config.json board
    shape (the recorded ``GET/PUT /config/board`` wire contract).

    Transition fields come from the settings transitions section — the copy
    the runtime actually uses.
    """
    board = primary_board_entry() or {}
    transitions = get_settings_service().get_transition_settings()
    return {
        "api_mode": board.get("api_mode") or "local",
        "local_api_key": board.get("local_api_key") or "",
        "cloud_key": board.get("cloud_key") or "",
        "note_array_token": board.get("note_array_token") or "",
        "host": board.get("host") or "",
        "transition_strategy": transitions.strategy,
        "transition_interval_ms": transitions.step_interval_ms,
        "transition_step_size": transitions.step_size,
    }


def _mask_legacy_board_view(view: dict) -> LegacyBoardConfig:
    """Mask non-empty sensitive fields with '***' (legacy masking contract)."""
    masked = {key: ("***" if key in _LEGACY_BOARD_SENSITIVE_FIELDS and value else value) for key, value in view.items()}
    return LegacyBoardConfig(**masked)


# Deprecated: use GET /settings/board instead.
#
# The Deprecation/Link header pair and the "Deprecated:" first line of the
# docstring have both been served since #1760, but the OpenAPI operation
# carried no ``deprecated`` flag — so Swagger, and every client generated
# from the schema, rendered this shim as a first-class route. The flag costs
# nothing and the endpoint keeps answering exactly as before; removal stays
# tracked on #1760.
@router.get("/config/board", response_model=BoardConfigResponse, deprecated=True)
async def get_board_config(response: Response):
    """Deprecated: use GET /settings/board instead (issue #1760).

    Get board connection configuration (keys masked). Served from the
    settings boards store — the single source of truth for board credentials.
    """
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = _CONFIG_BOARD_SUCCESSOR_LINK

    return BoardConfigResponse(
        config=_mask_legacy_board_view(_legacy_board_config_view()),
        api_modes=["local", "cloud"],
    )


# Deprecated: use PUT /settings/board instead (same reasoning as the GET).
@router.put(
    "/config/board",
    response_model=BoardConfigUpdateResponse,
    responses=errors(400, 422),
    deprecated=True,
)
async def update_board_config(request: BoardConfigUpdate, response: Response):
    """Deprecated: use PUT /settings/board instead (issue #1760).

    Update board connection configuration. Writes go to the primary board in
    the settings boards store ONLY — the legacy config.json board block is no
    longer written (it stays on disk as a rollback copy for older versions).

    Example body:
    {
        "api_mode": "local",
        "local_api_key": "your-key",
        "host": "192.168.1.100"
    }
    """
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = _CONFIG_BOARD_SUCCESSOR_LINK

    settings_service = get_settings_service()
    boards = [dict(b) for b in (settings_service.get_board_settings().boards or []) if isinstance(b, dict)]
    if not boards:
        from src.devices import BoardInstance

        boards = [BoardInstance(name="My Board", device_type="flagship", board_color="black").to_dict()]

    # exclude_unset, not exclude_none: "host only" must leave the stored key
    # alone, while an explicit ``{"host": null}`` still clears it — the exact
    # semantics of the ``if key in request`` comprehension this replaced.
    updates = request.model_dump(exclude_unset=True)
    boards[0].update(updates)
    try:
        settings_service.set_boards(boards)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    reinitialize_board_clients()

    return BoardConfigUpdateResponse(
        status="success",
        config=_mask_legacy_board_view(_legacy_board_config_view()),
    )


@router.delete("/config/board", response_model=BoardConfigResetResponse)
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
        from src.devices import BoardInstance

        settings_svc = get_settings_service()
        settings_svc.set_boards(
            [
                BoardInstance(
                    name="My Board",
                    device_type="flagship",
                    board_color="black",
                    enabled=True,
                    api_mode="local",
                    host="",
                    local_api_key="",
                    cloud_key="",
                ).to_dict()
            ]
        )
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to reset multi-board settings during board config reset")

    # Reinitialize the board client (will be unconfigured)
    service = get_service()
    if service:
        service.reinitialize_board_client()

    return BoardConfigResetResponse(
        status="reset",
        message="Board config cleared; backend is in first-run mode",
    )


@router.get("/config/validate", response_model=ConfigValidationResponse)
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
    is_valid, validation_errors = config_manager.validate()

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
    has_connection_attempt = False
    try:
        from src.devices import BoardInstance

        board_settings = get_settings_service().get_board_settings()
        for b in board_settings.boards or []:
            try:
                instance = BoardInstance.from_dict(b)
            except Exception:  # pragma: no cover - defensive
                continue
            if instance.has_connection_attempt:
                has_connection_attempt = True
            if instance.is_connection_configured:
                has_configured_board_instance = True
                break
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to inspect multi-board settings during validate_config")

    # A board with SOME connection detail but not a working set is
    # *misconfigured*, not first-run: it must surface as a per-board error
    # (#1813), never bounce an existing install back into the setup wizard.
    # Before #1760 the legacy config.json copy masked this case; with
    # settings as the single credential source the distinction is load-
    # bearing (a token-less note array replacing the only board used to
    # keep the wizard away purely via the stale legacy copy).
    if has_connection_attempt and not has_configured_board_instance:
        is_first_run = False

    if has_configured_board_instance:
        is_first_run = False
        missing_fields = [f for f in missing_fields if not f.startswith("board.")]
        board_error_prefixes = ("Board cloud_key", "Board local_api_key", "Board host")
        validation_errors = [e for e in validation_errors if not e.startswith(board_error_prefixes)]
        is_valid = len(validation_errors) == 0

    return ConfigValidationResponse(
        valid=is_valid,
        is_first_run=is_first_run,
        errors=validation_errors,
        missing_fields=missing_fields,
    )


@router.post(
    "/config/board/test",
    response_model=BoardTestResponse,
    response_model_exclude_none=True,
    responses=errors(400, 422, 500),
)
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

    Status codes:
        200: the probe ran and this is its verdict (``success`` may be False)
        400: the probe could not be attempted — a credential is missing or
             the host is not one this server will connect to
        500: an unanticipated server-side error
    """
    from src.board_client import BoardClient, is_successful_board_read_response

    api_mode = request.api_mode.lower()

    # Validate required fields based on mode
    if api_mode == "cloud":
        if not request.cloud_key:
            raise HTTPException(status_code=400, detail="Cloud API key is required")
        api_key = request.cloud_key
        use_cloud = True
        host = None
    else:  # local mode
        if not request.local_api_key:
            raise HTTPException(status_code=400, detail="Local API key is required")
        if not request.host:
            raise HTTPException(status_code=400, detail="Board host/IP is required for Local API")
        api_key = request.local_api_key
        use_cloud = False
        host = request.host
        # The host guard is the reason this endpoint cannot be pointed at an
        # arbitrary URL. Its 400 propagates unchanged: swallowing it into a
        # 200 body made a refused request look like a failed probe (#1887).
        validate_board_host(host)

    try:
        # Create temporary client with provided credentials
        client = BoardClient(api_key=api_key, host=host, use_cloud=use_cloud, skip_unchanged=False, port=request.port)

        # Test the connection directly so we can inspect HTTP status codes
        # (read_current_message() swallows errors and returns None, losing details)
        response = await asyncio.to_thread(requests.get, client.base_url, headers=client.headers, timeout=10)

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
                logger.warning(f"Board connection test: HTTP 200 but unrecognized response ({api_mode} mode): {detail}")
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
                    ],
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
                    ],
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
                    ],
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
                ],
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
                ],
            }

    except ValueError as e:
        # BoardClient rejected the credentials/host combination outright, so
        # no probe happened: a precondition failure, not a board verdict.
        logger.warning("Board connection test failed - invalid config", exc_info=True)
        raise HTTPException(status_code=400, detail="Board connection configuration is invalid.") from e
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
                ],
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
                ],
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
                ],
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
                ],
            }
    except HTTPException:
        raise
    except Exception as e:
        # Not a board verdict — the probe itself broke. Detail stays generic;
        # the exception is in the log, not in the response (#1887).
        logger.error(f"Board connection test error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Board connection test failed unexpectedly.") from e


@router.post(
    "/config/board/enable-local-api",
    response_model=EnableLocalApiResponse,
    response_model_exclude_none=True,
    responses=errors(400, 422, 500),
)
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

    Status codes:
        200: the exchange was attempted and this is the board's answer
        400: the exchange could not be attempted — a field is missing or the
             host is not one this server will contact
        500: an unanticipated server-side error
    """
    import requests as http_requests

    if not request.host:
        raise HTTPException(status_code=400, detail="Board IP address is required")

    if not request.enablement_token:
        raise HTTPException(status_code=400, detail="Enablement token is required")

    # Validate the host before composing the URL so an attacker can't
    # redirect this request away from the local board (SSRF). These 400s
    # propagate unchanged — downgrading them to a 200 body meant a blocked
    # SSRF attempt and a board that rejected the token were the same
    # response to every client (#1887).
    validate_board_host(request.host)
    validate_board_host_is_local_network(request.host)

    # Resolve the host to a concrete IPv4 address and ensure it is a private/
    # loopback/link-local address.  Using the ``ipaddress`` module's
    # ``is_private``/``is_loopback``/``is_link_local`` checks is the
    # CodeQL-recognised sanitiser for ``py/full-ssrf``: downstream sinks see
    # a value derived from an ``IPv4Address`` object, not from raw user input.
    import ipaddress as _ipaddress_mod
    import socket as _socket_mod

    try:
        _ip_obj = _ipaddress_mod.IPv4Address(request.host)
    except ValueError:
        try:
            _addrinfo = _socket_mod.getaddrinfo(
                request.host, None, family=_socket_mod.AF_INET, type=_socket_mod.SOCK_STREAM
            )
        except _socket_mod.gaierror as exc:
            raise HTTPException(status_code=400, detail="host could not be resolved") from exc
        _resolved = [info[4][0] for info in _addrinfo if info and len(info) >= 5 and info[4]]
        if not _resolved:
            raise HTTPException(status_code=400, detail="host did not resolve to an IPv4 address") from None
        _ip_obj = _ipaddress_mod.IPv4Address(_resolved[0])

    if not (_ip_obj.is_private or _ip_obj.is_loopback or _ip_obj.is_link_local):
        raise HTTPException(status_code=400, detail="host must be on a private network")
    _safe_host = _ip_obj.compressed
    url = f"http://{_safe_host}:7000/local-api/enablement"
    headers = {"X-Vestaboard-Local-Api-Enablement-Token": request.enablement_token}

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
                    "message": "Local API enabled successfully! Your API key has been retrieved.",
                }
            else:
                logger.warning(f"Local API enablement response missing apiKey: {data}")
                return {
                    "success": False,
                    "message": "Received response but no API key was provided",
                    "error": "Board response did not include an apiKey",
                }
        elif response.status_code == 401 or response.status_code == 403:
            logger.warning("Local API enablement failed - invalid token")
            return {
                "success": False,
                "message": "Invalid enablement token. Please check the token and try again.",
                "error": f"HTTP {response.status_code}: Unauthorized",
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Local API enablement error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to enable local API.") from e


@router.post("/config/board/scan", response_model=BoardScanResponse, responses=errors(422))
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
    return BoardScanResponse(boards=boards)


@router.get("/config/general", response_model=GeneralConfig)
async def get_general_config():
    """Get general configuration (timezone, refresh interval, etc.)."""
    config_manager = get_config_manager()
    return config_manager.get_general()


@router.put("/config/general", response_model=GeneralConfig, responses=errors(422, 500))
async def update_general_config(request: GeneralConfigUpdate):
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

    general_config = config_manager.get_general()

    # exclude_unset: a caller who did not mention a field must not overwrite
    # it with the model default. The wizard and the settings page both save
    # one field at a time.
    updates = request.model_dump(exclude_unset=True)
    timezone_changed = "timezone" in updates and updates["timezone"] != general_config.get("timezone")
    general_config.update(updates)

    # Save back
    success = config_manager.set_general(general_config)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update general configuration")

    # The scheduler resolves "now" via the cached TimeService singleton, which
    # reads Config.GENERAL_TIMEZONE only once at creation. Without rebuilding it
    # here, a timezone change would update the Date/Time plugin (it re-reads
    # config every render) but leave schedule rotations firing in the stale
    # timezone (defaulting to Pacific), so they'd run hours off (issue #1273).
    if timezone_changed:
        reset_time_service()

    return GeneralConfig(**general_config)
