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

The domain's behaviour lives in ``src/config_api/service.py``, created when
``config_api`` opted into ``tests/test_layering_ratchet.py``: the first-run
determination, the board probe and the enablement exchange were 421 lines of
router with no HTTP in them. They raise
:class:`~src.config_api.service.BoardProbeError`; the handlers translate it and
change nothing about the status or the detail.

``config`` carries six checked-in ``declared_errors`` exceptions to the
conventions ratchet — this domain is read-heavy, and six routes are
parameterless reads of local state with no failure path.

It carried two more, ``no_200_on_failure`` on the probe endpoints, until those
bodies moved down. That rule walks the *handler's own AST*, so a handler that
no longer builds the ``{"success": false, ...}`` verdict stops tripping it, and
``validate_manifest`` fails the build on an exception whose rule already
passes. Nothing about the contract changed — ``tests/test_config_contract.py``
and ``tests/test_status_code_correctness.py`` pin every status/verdict pair by
value, which is stronger than the AST proxy was — and the deleted reasons are
preserved on the service functions.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Response

from src.api_errors import errors
from src.board_guards import primary_board_entry
from src.config import Config
from src.config_manager import get_config_manager
from src.display_runtime import get_service, reinitialize_board_clients
from src.settings.service import get_settings_service
from src.time_service import reset_time_service

from . import service
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


def _as_http(exc: service.BoardProbeError) -> HTTPException:
    """The domain's refusal, in the transport's vocabulary.

    Status and detail pass through untouched — ``tests/test_config_contract.py``
    pins every pair by value.
    """
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


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
    return service.determine_config_validity()


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
    try:
        return await service.probe_board_connection(request)
    except service.BoardProbeError as exc:
        raise _as_http(exc) from exc


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
    try:
        return await service.exchange_enablement_token(request)
    except service.BoardProbeError as exc:
        raise _as_http(exc) from exc


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
