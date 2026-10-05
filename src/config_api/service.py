"""Domain behaviour behind the ``/config`` endpoints.

``src/config_api/`` was the one converted domain with no service module at
all: 421 lines of first-run determination, board probing and Local API
enablement lived in the router, which is what
``tests/test_layering_ratchet.py``'s ``router_no_domain_logic`` rule flagged on
all three of its handlers.

Nothing here imports ``fastapi``. Refusals are raised as
:class:`BoardProbeError`, carrying the status and detail the router hands
straight to ``HTTPException`` — ``tests/test_config_contract.py`` pins every
one of those pairs by value. Two exceptions travel *through* this module
rather than from it: ``src.board_guards.validate_board_host`` and
``validate_board_host_is_local_network`` still raise ``HTTPException`` for the
whole app, so their 400s pass through untouched.

Vestaboard knowledge is not here: the connection probe is the draft
driver's ``check_connection`` (what each status means lives in
``src/outputs/vestaboard/connection.py``), and the enablement-token exchange
is the ``vestaboard`` output's ``enable_local_api`` action
(``src/outputs/vestaboard/local_api.py``). **That module now holds the
CodeQL-recognised SSRF block**, moved whole and byte-for-byte; read its
docstring before touching it.

Collaborators resolve from their canonical homes at **module import time**, so
this module never loads ``src.api_server``. Tests that need to stub one patch
it where this module binds it — ``src.config_api.service.<name>``.
"""

from __future__ import annotations

import asyncio
import logging

from src.board_guards import validate_board_host
from src.config_manager import get_config_manager
from src.outputs.hooks import OutputActionError
from src.settings.service import VALID_WIZARD_STATES, get_settings_service

from .models import BoardTestRequest, ConfigValidationResponse, EnablementTokenRequest

logger = logging.getLogger(__name__)


#: A ``/config`` operation refused, or failed, with the answer to give.
#: ``status_code`` and ``detail`` are handed to ``HTTPException`` verbatim by
#: the router. They are part of this domain's recorded contract
#: (``tests/test_config_contract.py``), not a transport detail. It is the
#: outputs' :class:`~src.outputs.hooks.OutputActionError`, so a refusal raised
#: inside an output action (``enable_local_api``) is this class too.
BoardProbeError = OutputActionError


# ---------------------------------------------------------------------------
# GET /config/validate — the first-run determination
# ---------------------------------------------------------------------------


def _multi_board_connection_state() -> tuple[bool, bool]:
    """``(has_configured_board_instance, has_connection_attempt)``.

    Reads the multi-board settings store, which is the credential source of
    truth since #1760. Defensive throughout: a store this cannot parse must
    not decide the wizard question on its own.
    """
    has_configured_board_instance = False
    has_connection_attempt = False
    try:
        from src.devices import BoardInstance
        from src.outputs.registry import VESTABOARD, resolve_output_id

        board_settings = get_settings_service().get_board_settings()
        for b in board_settings.boards or []:
            if resolve_output_id(b) != VESTABOARD:
                # A FiestaPanel or an output plugin's board: its output is
                # the configuration (plan D13). A Pixoo-only install is not
                # "first run" for want of a Vestaboard key; an output that
                # is not installed is a per-board error, never the wizard.
                has_connection_attempt = has_configured_board_instance = True
                break
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
    return has_configured_board_instance, has_connection_attempt


def determine_config_validity() -> ConfigValidationResponse:
    """Validate the configuration and decide whether this is a first run.

    First run (plan D13, D18): **no board has a usable output AND the setup
    wizard was neither completed nor skipped**. A usable output is a
    Vestaboard with any connection detail (#1813: misconfigured is not
    unconfigured), a FiestaPanel, or any output plugin's board. The legacy
    ``config.json`` board block still counts as a configured Vestaboard (an
    install that predates the boards store), but nothing has to write it any
    more — the deprecated ``PUT /config/board`` keeps working, unneeded.

    A board is considered configured when either the legacy single-board
    config has the required credentials, or any board instance configured via
    the multi-board settings service has connection credentials. That keeps
    users who set a board up through Settings (rather than the wizard) out of
    onboarding.
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
    has_configured_board_instance, has_connection_attempt = _multi_board_connection_state()

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

    # The wizard ended — finished, or "I'll add a display later" — so it never
    # comes back on its own, board or no board (plan D18). Kept server-side so
    # the answer holds in every browser, not just the one that clicked.
    if get_settings_service().get_wizard_state() in VALID_WIZARD_STATES:
        is_first_run = False

    return ConfigValidationResponse(
        valid=is_valid,
        is_first_run=is_first_run,
        errors=validation_errors,
        missing_fields=missing_fields,
    )


# ---------------------------------------------------------------------------
# POST /config/board/test — the connection probe
# ---------------------------------------------------------------------------


def _probe_credentials(request: BoardTestRequest) -> tuple[str, str, bool, str | None]:
    """``(api_mode, api_key, use_cloud, host)`` for a probe that can be run.

    The order of these refusals is recorded: a local-mode body missing both
    its key and its host is told about the key first, and the host guard runs
    only once a host is present.
    """
    api_mode = request.api_mode.lower()
    if api_mode == "cloud":
        if not request.cloud_key:
            raise BoardProbeError(400, "Cloud API key is required")
        return api_mode, request.cloud_key, True, None
    if not request.local_api_key:
        raise BoardProbeError(400, "Local API key is required")
    if not request.host:
        raise BoardProbeError(400, "Board host/IP is required for Local API")
    # The host guard is the reason this endpoint cannot be pointed at an
    # arbitrary URL. Its 400 propagates unchanged: swallowing it into a
    # 200 body made a refused request look like a failed probe (#1887).
    validate_board_host(request.host)
    return api_mode, request.local_api_key, False, request.host


async def probe_board_connection(request: BoardTestRequest) -> dict:
    """Test a board connection with the supplied credentials, saving nothing.

    A *probe*: the endpoint's job is to report what the board said, so "your
    key was rejected" is the requested answer at 200 through
    ``BoardTestResponse``, not a transport failure. Preconditions the server
    rejects before probing (missing credential, unsafe host) really are 400,
    and unanticipated errors really are 500 (#1887, Task 10a). Making the
    upstream verdicts 4xx would tell the wizard the request was malformed when
    it was not.

    The probe itself is the driver's: a DRAFT driver for the unsaved
    credentials (the runtime factory's draft door — a private runtime, never
    a board's live one) runs its ``check_connection`` over its own request
    path, and the structured :class:`~src.outputs.hooks.ConnectionCheck` is
    served as the verdict. What a status means for a Vestaboard lives with
    the output (``src/outputs/vestaboard/connection.py``).

    That contract used to be recorded as a ``no_200_on_failure`` exception in
    ``tests/conventions_manifest.json``; the rule reads the *handler's* AST, so
    the exception went dead the moment this body moved down here.
    ``tests/test_config_contract.py`` and
    ``tests/test_status_code_correctness.py`` pin it by value instead.
    """
    from src.outputs.factory import draft_driver

    _api_mode, api_key, use_cloud, host = _probe_credentials(request)

    try:
        draft = (
            {"api_mode": "cloud", "cloud_key": api_key}
            if use_cloud
            else {
                "api_mode": "local",
                "local_api_key": api_key,
                "host": host,
                "port": request.port,
            }
        )
        driver = draft_driver(draft)
        if driver is None:
            raise ValueError("no usable connection in the supplied credentials")

        check = await asyncio.to_thread(driver.check_connection)
        return check.to_verdict()
    except ValueError as e:
        # The driver refused the credentials/host combination outright, so
        # no probe happened: a precondition failure, not a board verdict.
        logger.warning("Board connection test failed - invalid config", exc_info=True)
        raise BoardProbeError(400, "Board connection configuration is invalid.") from e
    except BoardProbeError:
        # The twin of the router's `except HTTPException: raise`: without it
        # the broad arm below would swallow this function's own refusal and
        # re-raise it as a 500 (the stuttering "500: ..." bug, fixed once).
        raise
    except Exception as e:
        # Not a board verdict — the probe itself broke. Detail stays generic;
        # the exception is in the log, not in the response (#1887).
        logger.error(f"Board connection test error: {e}", exc_info=True)
        raise BoardProbeError(500, "Board connection test failed unexpectedly.") from e


# ---------------------------------------------------------------------------
# POST /config/board/enable-local-api — the enablement-token exchange
# ---------------------------------------------------------------------------


async def exchange_enablement_token(request: EnablementTokenRequest) -> dict:
    """Exchange a Local API Enablement Token for a Local API Key.

    The ``vestaboard`` output's ``enable_local_api`` action
    (``src/outputs/vestaboard/local_api.py``, where the CodeQL-recognised
    SSRF block now lives, moved whole). Its refusals are
    :class:`BoardProbeError` — the same class — so the router's handling is
    unchanged.
    """
    from src.outputs.registry import VESTABOARD, output_action

    return await output_action(VESTABOARD, "enable_local_api")(request)
