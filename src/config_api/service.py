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

Vestaboard knowledge is not here. The probe and the enablement-token exchange
are the ``vestaboard`` output's ``test_connection`` and ``enable_local_api``
board-settings actions (``fiestaboard-output--vestaboard/actions.py``), run on
draft settings by :func:`src.outputs.actions.execute_action`; these routes
answer the outcome's ``detail`` — the probe's verdict, the exchange's — in
their recorded shapes, and the action's refusals pass through as
:class:`BoardProbeError`. What each probe status means lives in the plugin's
``probe.py``; **the CodeQL-recognised SSRF block** lives in its
``local_api.py``, moved whole and byte-for-byte; read its docstring before
touching it.

Collaborators resolve from their canonical homes at **module import time**, so
this module never loads ``src.api_server``. Tests that need to stub one patch
it where this module binds it — ``src.config_api.service.<name>``.
"""

from __future__ import annotations

import logging

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

        board_settings = get_settings_service().get_board_settings()
        for b in board_settings.boards or []:
            try:
                instance = BoardInstance.from_dict(b)
            except Exception:  # pragma: no cover - defensive
                continue
            status = instance.status
            if status is None:
                # An output with nothing to say about its settings (or one
                # that is not installed): the output is the configuration
                # (plan D13). A Pixoo-only install is not "first run" for
                # want of a key; a missing output is a per-board error,
                # never the wizard.
                has_connection_attempt = has_configured_board_instance = True
                break
            if status.attempted:
                has_connection_attempt = True
            if status.configured:
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


async def _vestaboard_draft_action(action: str, settings: dict, inputs: dict | None = None):
    """Run the ``vestaboard`` output's *action* on draft *settings*."""
    from src.outputs.actions import draft_board, execute_action
    from src.outputs.registry import VESTABOARD, output_registry

    definition = output_registry().get(VESTABOARD)
    if definition is None:
        raise BoardProbeError(503, "The Vestaboard output is not installed.")
    return await execute_action(
        definition, action, board=draft_board(definition, settings), board_id=None, inputs=inputs or {}
    )


async def probe_board_connection(request: BoardTestRequest) -> dict:
    """Test a board connection with the supplied credentials, saving nothing.

    A *probe*: the endpoint's job is to report what the board said, so "your
    key was rejected" is the requested answer at 200 through
    ``BoardTestResponse``, not a transport failure. Preconditions the server
    rejects before probing (missing credential, unsafe host) really are 400,
    and unanticipated errors really are 500 (#1887, Task 10a). Making the
    upstream verdicts 4xx would tell the wizard the request was malformed when
    it was not.

    The probe is the ``vestaboard`` output's ``test_connection`` action on
    the request's credentials as draft settings — a throwaway instance on a
    private runtime, never a board's live one — and its verdict
    (:meth:`~src.outputs.hooks.ConnectionCheck.to_verdict`, the outcome's
    ``detail``) is the response. The refusals (which credential is missing,
    in the recorded order; the host guard) are the action's.

    That contract used to be recorded as a ``no_200_on_failure`` exception in
    ``tests/conventions_manifest.json``; the rule reads the *handler's* AST, so
    the exception went dead the moment this body moved down here.
    ``tests/test_config_contract.py`` and
    ``tests/test_status_code_correctness.py`` pin it by value instead.
    """
    # Every field the request carries, as given: which of them a connection
    # needs (and in what order a missing one is refused) is the plugin's rule.
    settings = {
        "api_mode": request.api_mode,
        "cloud_key": request.cloud_key or "",
        "local_api_key": request.local_api_key or "",
        "host": request.host or "",
        "port": request.port,
    }
    try:
        outcome = await _vestaboard_draft_action("test_connection", settings)
        return dict(outcome.detail)
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

    The ``vestaboard`` output's ``enable_local_api`` action on the request
    as draft settings (``fiestaboard-output--vestaboard/local_api.py`` is
    where the CodeQL-recognised SSRF block lives, moved whole); the board's
    answer is the outcome's ``detail``. Its refusals are
    :class:`BoardProbeError` — the same class — so the router's handling is
    unchanged.
    """
    outcome = await _vestaboard_draft_action(
        "enable_local_api",
        {"host": request.host or ""},
        {"host": request.host or "", "enablement_token": request.enablement_token or ""},
    )
    return dict(outcome.detail)
