"""The ``vestaboard`` output's connection check: what a probe's answer means.

Behind :meth:`BoardClient.check_connection <src.board_client.BoardClient.check_connection>`
(the driver's ``test_connection`` hook, structured). ``POST /config/board/test``
builds a draft driver for the unsaved credentials and serves
:meth:`ConnectionCheck.to_verdict <src.outputs.hooks.ConnectionCheck.to_verdict>`.

Moved from ``src/config_api/service.py``. Two things changed on purpose
(A4 wire-goldens finding 4): the probe now goes through the client's own
request path — its ``check_output_url`` fence and its ``(connect, read)``
timeout pair, ``(3, 10)`` local and ``(5, 10)`` cloud — instead of a
separate ``requests.get`` with a single ``timeout=10``. A board that cannot
be connected to is now told so after 3 s (5 s cloud), not 10.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from src.output_allowlist import OutputHostBlocked, check_output_url
from src.outputs.hooks import ConnectionCheck

logger = logging.getLogger(__name__)


def probe(url: str, headers: dict[str, str], timeout: tuple[float, float], *, use_cloud: bool) -> ConnectionCheck:
    """GET the board's read endpoint once and classify the answer.

    Raises what is not a board verdict: a ``ValueError`` (a URL or header
    the transport refuses — the credentials were unusable, so no probe
    happened) and anything unanticipated.
    """
    api_mode = "cloud" if use_cloud else "local"
    try:
        check_output_url(url)
        response = requests.get(url, headers=headers, timeout=timeout)
    except OutputHostBlocked as e:
        return ConnectionCheck.blocked(e.host)
    except ValueError:
        raise
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Board connection test error: {e}")
        return _connection_error(use_cloud)
    except requests.exceptions.Timeout as e:
        logger.error(f"Board connection test timeout: {e}")
        return _timeout(use_cloud)

    if response.status_code == 200:
        return _ok_response(response, api_mode)
    if response.status_code in (401, 403):
        logger.warning(f"Board connection test: auth rejected HTTP {response.status_code} ({api_mode} mode)")
        return _rejected_auth(response.status_code, use_cloud)
    return _unexpected_status(response.status_code, api_mode)


def _ok_response(response: Any, api_mode: str) -> ConnectionCheck:
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
            return ConnectionCheck(
                success=True,
                message="Successfully connected to your board!",
                details={"api_mode": api_mode},
            )
        detail = (
            f"JSON keys: {', '.join(sorted(data))}" if isinstance(data, dict) else f"body type: {type(data).__name__}"
        )
        logger.warning(f"Board connection test: HTTP 200 but unrecognized response ({api_mode} mode): {detail}")
        return ConnectionCheck(
            success=False,
            message="Connected to Vestaboard but the response shape was not recognized.",
            failure="bad_response",
            error=f"Unrecognized read response ({detail}).",
            troubleshooting=(
                "Update FiestaBoard to the latest version.",
                "If this persists, file an issue with the response keys shown above (no API keys).",
            ),
        )
    except ValueError:
        logger.warning(f"Board connection test: HTTP 200 but invalid JSON ({api_mode} mode)")
        return ConnectionCheck(
            success=False,
            message="Connected to the board but the response could not be read. The board may be starting up.",
            failure="bad_response",
            error="Invalid JSON response",
            troubleshooting=(
                "Wait 30 seconds and try again — the board may still be starting up.",
                "Try unplugging the board for 10 seconds and plugging it back in.",
            ),
        )


def _rejected_auth(status_code: int, use_cloud: bool) -> ConnectionCheck:
    """The verdict for a 401/403 — a key the far end would not accept."""
    if use_cloud:
        return ConnectionCheck(
            success=False,
            message=f"Your API key was rejected by the Vestaboard cloud service (HTTP {status_code}).",
            failure="auth",
            error=f"HTTP {status_code}",
            troubleshooting=(
                "Go to https://web.vestaboard.com and sign in to your account.",
                "Make sure you are copying the Read/Write API key (not the subscription key or installable key).",
                "Paste the key into the Cloud API Key field and try again.",
            ),
        )
    return ConnectionCheck(
        success=False,
        message=f"Your API key was rejected by the board (HTTP {status_code}).",
        failure="auth",
        error=f"HTTP {status_code}",
        troubleshooting=(
            "Verify your Local API key is correct — it was provided when you enabled the Local API with your enablement token.",
            "If you need a new key, request an enablement token at https://www.vestaboard.com/local-api",
            "Paste the correct key into the Local API Key field and try again.",
            "If the key was recently regenerated, the old key will no longer work.",
        ),
    )


def _unexpected_status(status_code: int, api_mode: str) -> ConnectionCheck:
    """The verdict for a 5xx, or for anything else the board answered."""
    if status_code >= 500:
        logger.warning(f"Board connection test: server error HTTP {status_code} ({api_mode} mode)")
        return ConnectionCheck(
            success=False,
            message=f"The board returned an error (HTTP {status_code}). It may be temporarily unavailable.",
            failure="server_error",
            error=f"HTTP {status_code}",
            troubleshooting=(
                "Try unplugging the Vestaboard for 10 seconds and plugging it back in.",
                "Wait about a minute for the board to restart, then try again.",
                "If the problem continues, check for firmware updates in the Vestaboard app.",
            ),
        )
    logger.warning(f"Board connection test: unexpected HTTP {status_code} ({api_mode} mode)")
    return ConnectionCheck(
        success=False,
        message=f"Received an unexpected response from the board (HTTP {status_code}).",
        failure="unexpected_status",
        error=f"HTTP {status_code}",
        troubleshooting=(
            "Try unplugging the Vestaboard for 10 seconds and plugging it back in.",
            "Check for firmware updates in the Vestaboard app.",
            "If the problem continues, try using the other connection mode (Local or Cloud).",
        ),
    )


def _connection_error(use_cloud: bool) -> ConnectionCheck:
    """The verdict when no socket could be opened at all."""
    if use_cloud:
        return ConnectionCheck(
            success=False,
            message="Could not connect to the Vestaboard cloud service.",
            failure="unreachable",
            error="Connection error",
            troubleshooting=(
                "Make sure the device running FiestaBoard has a working internet connection.",
                "Try opening https://rw.vestaboard.com in a browser to verify the service is reachable.",
                "If you use a VPN or corporate network, make sure it allows connections to rw.vestaboard.com.",
            ),
        )
    return ConnectionCheck(
        success=False,
        message="Could not connect to the board. The board may be off or not on the same network.",
        failure="unreachable",
        error="Connection error",
        troubleshooting=(
            "Make sure the Vestaboard is powered on.",
            "Make sure both FiestaBoard and the Vestaboard are on the same Wi-Fi network.",
            "Double-check the board's IP address — you can find it on your router's admin page or use FiestaBoard's network scan.",
            "Make sure the Local API is enabled on your board (see https://docs.vestaboard.com/docs/local-api/authentication).",
        ),
    )


def _timeout(use_cloud: bool) -> ConnectionCheck:
    """The verdict when the far end accepted the socket but never answered."""
    if use_cloud:
        return ConnectionCheck(
            success=False,
            message="Connection to the Vestaboard cloud service timed out.",
            failure="timeout",
            error="Timeout",
            troubleshooting=(
                "Check that the device running FiestaBoard has a stable internet connection.",
                "The Vestaboard cloud service may be experiencing issues — try again in a few minutes.",
            ),
        )
    return ConnectionCheck(
        success=False,
        message="Connection to the board timed out. The board may be off or the IP address may be wrong.",
        failure="timeout",
        error="Timeout",
        troubleshooting=(
            "Make sure the Vestaboard is powered on.",
            "Double-check the IP address in the Vestaboard app under Settings.",
            "Make sure both devices are on the same network.",
            "Try using the board's IP address instead of a hostname.",
        ),
    )
