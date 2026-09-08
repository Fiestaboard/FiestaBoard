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

**The SSRF sanitiser in :func:`exchange_enablement_token` is deliberately
contiguous with the request it guards.** CodeQL's ``py/full-ssrf`` recognises
the shape — an ``ipaddress.IPv4Address`` derivation plus the
``is_private``/``is_loopback``/``is_link_local`` gate, with the sink in the
same function — and the two historical ``py/full-ssrf`` alerts on this code
were closed by exactly that sequence. It moved whole: the guard, the address
it derives, the URL built from that address and the ``requests.post`` that
uses it are still one unbroken block, in one function. Only the exception
class raised on rejection changed, because a domain module may not import
``fastapi``. Do not split it, reorder it, or "tidy" it.

Collaborators resolve from their canonical homes at **module import time**, so
this module never loads ``src.api_server``. Tests that need to stub one patch
it where this module binds it — ``src.config_api.service.<name>``.
"""

from __future__ import annotations

import asyncio
import logging

import requests

from src.board_guards import validate_board_host, validate_board_host_is_local_network
from src.config_manager import get_config_manager
from src.settings.service import get_settings_service

from .models import BoardTestRequest, ConfigValidationResponse, EnablementTokenRequest

logger = logging.getLogger(__name__)


class BoardProbeError(Exception):
    """A ``/config`` operation refused, or failed, with the answer to give.

    ``status_code`` and ``detail`` are handed to ``HTTPException`` verbatim by
    the router. They are part of this domain's recorded contract
    (``tests/test_config_contract.py``), not a transport detail.
    """

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


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


def _verdict_for_ok_response(response, api_mode: str) -> dict:
    """The verdict for an HTTP 200 from the board: is this board data?"""
    from src.board_client import is_successful_board_read_response

    # The whole read stays inside one ``except ValueError`` on purpose: the
    # shape inspection is part of "could this body be read at all", and
    # splitting it would send a ValueError raised past ``json()`` to the
    # caller's own ``except ValueError`` — a different answer entirely.
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
            f"JSON keys: {', '.join(sorted(data))}" if isinstance(data, dict) else f"body type: {type(data).__name__}"
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


def _verdict_for_rejected_auth(status_code: int, use_cloud: bool) -> dict:
    """The verdict for a 401/403 — a key the far end would not accept."""
    if use_cloud:
        return {
            "success": False,
            "message": f"Your API key was rejected by the Vestaboard cloud service (HTTP {status_code}).",
            "error": f"HTTP {status_code}",
            "troubleshooting": [
                "Go to https://web.vestaboard.com and sign in to your account.",
                "Make sure you are copying the Read/Write API key (not the subscription key or installable key).",
                "Paste the key into the Cloud API Key field and try again.",
            ],
        }
    return {
        "success": False,
        "message": f"Your API key was rejected by the board (HTTP {status_code}).",
        "error": f"HTTP {status_code}",
        "troubleshooting": [
            "Verify your Local API key is correct — it was provided when you enabled the Local API with your enablement token.",
            "If you need a new key, request an enablement token at https://www.vestaboard.com/local-api",
            "Paste the correct key into the Local API Key field and try again.",
            "If the key was recently regenerated, the old key will no longer work.",
        ],
    }


def _verdict_for_unexpected_status(status_code: int, api_mode: str) -> dict:
    """The verdict for a 5xx, or for anything else the board answered."""
    if status_code >= 500:
        logger.warning(f"Board connection test: server error HTTP {status_code} ({api_mode} mode)")
        return {
            "success": False,
            "message": f"The board returned an error (HTTP {status_code}). It may be temporarily unavailable.",
            "error": f"HTTP {status_code}",
            "troubleshooting": [
                "Try unplugging the Vestaboard for 10 seconds and plugging it back in.",
                "Wait about a minute for the board to restart, then try again.",
                "If the problem continues, check for firmware updates in the Vestaboard app.",
            ],
        }
    logger.warning(f"Board connection test: unexpected HTTP {status_code} ({api_mode} mode)")
    return {
        "success": False,
        "message": f"Received an unexpected response from the board (HTTP {status_code}).",
        "error": f"HTTP {status_code}",
        "troubleshooting": [
            "Try unplugging the Vestaboard for 10 seconds and plugging it back in.",
            "Check for firmware updates in the Vestaboard app.",
            "If the problem continues, try using the other connection mode (Local or Cloud).",
        ],
    }


def _verdict_for_connection_error(use_cloud: bool) -> dict:
    """The verdict when no socket could be opened at all."""
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


def _verdict_for_timeout(use_cloud: bool) -> dict:
    """The verdict when the far end accepted the socket but never answered."""
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


async def probe_board_connection(request: BoardTestRequest) -> dict:
    """Test a board connection with the supplied credentials, saving nothing.

    A *probe*: the endpoint's job is to report what the board said, so "your
    key was rejected" is the requested answer at 200 through
    ``BoardTestResponse``, not a transport failure. Preconditions the server
    rejects before probing (missing credential, unsafe host) really are 400,
    and unanticipated errors really are 500 (#1887, Task 10a). Making the
    upstream verdicts 4xx would tell the wizard the request was malformed when
    it was not.

    That contract used to be recorded as a ``no_200_on_failure`` exception in
    ``tests/conventions_manifest.json``; the rule reads the *handler's* AST, so
    the exception went dead the moment this body moved down here.
    ``tests/test_config_contract.py`` and
    ``tests/test_status_code_correctness.py`` pin it by value instead.
    """
    from src.board_client import BoardClient

    api_mode, api_key, use_cloud, host = _probe_credentials(request)

    try:
        # Create temporary client with provided credentials
        client = BoardClient(api_key=api_key, host=host, use_cloud=use_cloud, skip_unchanged=False, port=request.port)

        # Test the connection directly so we can inspect HTTP status codes
        # (read_current_message() swallows errors and returns None, losing details)
        response = await asyncio.to_thread(requests.get, client.base_url, headers=client.headers, timeout=10)

        if response.status_code == 200:
            return _verdict_for_ok_response(response, api_mode)
        if response.status_code in (401, 403):
            logger.warning(f"Board connection test: auth rejected HTTP {response.status_code} ({api_mode} mode)")
            return _verdict_for_rejected_auth(response.status_code, use_cloud)
        return _verdict_for_unexpected_status(response.status_code, api_mode)
    except ValueError as e:
        # BoardClient rejected the credentials/host combination outright, so
        # no probe happened: a precondition failure, not a board verdict.
        logger.warning("Board connection test failed - invalid config", exc_info=True)
        raise BoardProbeError(400, "Board connection configuration is invalid.") from e
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Board connection test error: {e}")
        return _verdict_for_connection_error(use_cloud)
    except requests.exceptions.Timeout as e:
        logger.error(f"Board connection test timeout: {e}")
        return _verdict_for_timeout(use_cloud)
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


def _verdict_for_enablement_response(response, host: str) -> dict:
    """Interpret the board's answer to an enablement-token exchange."""
    if response.status_code == 200:
        data = response.json()
        api_key = data.get("apiKey")
        if api_key:
            logger.info(f"Successfully enabled local API on {host}")
            return {
                "success": True,
                "api_key": api_key,
                "message": "Local API enabled successfully! Your API key has been retrieved.",
            }
        logger.warning(f"Local API enablement response missing apiKey: {data}")
        return {
            "success": False,
            "message": "Received response but no API key was provided",
            "error": "Board response did not include an apiKey",
        }
    if response.status_code in (401, 403):
        logger.warning("Local API enablement failed - invalid token")
        return {
            "success": False,
            "message": "Invalid enablement token. Please check the token and try again.",
            "error": f"HTTP {response.status_code}: Unauthorized",
        }
    logger.warning(f"Local API enablement failed - HTTP {response.status_code}")
    return {
        "success": False,
        "message": f"Board returned an error (HTTP {response.status_code})",
        "error": f"HTTP {response.status_code}",
    }


async def exchange_enablement_token(request: EnablementTokenRequest) -> dict:
    """Exchange a Local API Enablement Token for a Local API Key.

    The board issues the key; this only carries the token to it. Same declared
    verdict contract as :func:`probe_board_connection` (#1887): "that
    enablement token is not valid" is the board's answer at 200 through
    ``EnableLocalApiResponse``, while the SSRF and host-validation rejections
    are 400 and an unanticipated failure is 500. Pinned by value in
    ``tests/test_config_contract.py``.

    **The SSRF sequence below is CodeQL-recognised (``py/full-ssrf``) and is
    reproduced verbatim from the router it moved out of.** The address
    derivation, the private-network gate, the URL built from the derived
    address and the request that uses it are one contiguous block on purpose.
    See this module's docstring.
    """
    import requests as http_requests

    if not request.host:
        raise BoardProbeError(400, "Board IP address is required")

    if not request.enablement_token:
        raise BoardProbeError(400, "Enablement token is required")

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
            raise BoardProbeError(400, "host could not be resolved") from exc
        _resolved = [info[4][0] for info in _addrinfo if info and len(info) >= 5 and info[4]]
        if not _resolved:
            raise BoardProbeError(400, "host did not resolve to an IPv4 address") from None
        _ip_obj = _ipaddress_mod.IPv4Address(_resolved[0])

    if not (_ip_obj.is_private or _ip_obj.is_loopback or _ip_obj.is_link_local):
        raise BoardProbeError(400, "host must be on a private network")
    _safe_host = _ip_obj.compressed
    url = f"http://{_safe_host}:7000/local-api/enablement"
    headers = {"X-Vestaboard-Local-Api-Enablement-Token": request.enablement_token}

    try:
        logger.info(f"Attempting to enable local API on {request.host}")
        response = http_requests.post(url, headers=headers, timeout=10)
        return _verdict_for_enablement_response(response, request.host)
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
    except BoardProbeError:
        # The twin of the router's `except HTTPException: raise` — see
        # ``probe_board_connection`` for why this arm has to precede the
        # broad one below.
        raise
    except Exception as e:
        logger.error(f"Local API enablement error: {e}", exc_info=True)
        raise BoardProbeError(500, "Failed to enable local API.") from e
