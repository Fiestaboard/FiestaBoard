"""The Vestaboard ``enable_local_api`` action.

Exchanges a Local API Enablement Token for a Local API Key.
``POST /config/board/enable-local-api`` (pinned in FiestaBoard's
``tests/golden/api_routes.json``) and the board settings "Enable Local API"
action both run :func:`exchange_enablement_token`.

**The SSRF sanitiser in :func:`exchange_enablement_token` is deliberately
contiguous with the request it guards.** CodeQL's ``py/full-ssrf`` recognises
the shape — an ``ipaddress.IPv4Address`` derivation plus the
``is_private``/``is_loopback``/``is_link_local`` gate, with the sink in the
same function — and the two historical ``py/full-ssrf`` alerts on this code
were closed by exactly that sequence. It has now moved three times, each time
whole: from the router to ``src/config_api/service.py``, from there to
``src/outputs/vestaboard/local_api.py``, and from there into this plugin,
byte-for-byte. The guard, the address it derives, the URL built from that
address and the ``requests.post`` that uses it are still one unbroken block,
in one function. ``BoardProbeError`` is FiestaBoard's ``OutputActionError``
under the name the block has always raised, so not one line of the block
changed. Do not split it, reorder it, or "tidy" it.

Collaborators bind at **module import time**; tests that need to stub one
patch it where this module binds it — ``<package>.local_api.<name>``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.plugins import (
    ConnectionCheck,
    OutputHostBlocked,
    check_output_host,
    validate_board_host,
    validate_board_host_is_local_network,
)
from src.plugins import OutputActionError as BoardProbeError

logger = logging.getLogger(__name__)


def _verdict_for_blocked_host(host: str | None) -> dict:
    """The verdict when FIESTABOARD_OUTPUTS_ALLOW_HOSTS refused the host."""
    return ConnectionCheck.blocked(host).to_verdict()


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


async def exchange_enablement_token(request: Any) -> dict:
    """Exchange a Local API Enablement Token for a Local API Key.

    The board issues the key; this only carries the token to it. Same declared
    verdict contract as
    FiestaBoard's ``probe_board_connection`` (#1887): "that
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

    # Before the SSRF block below (which must stay contiguous): the allowlist
    # is checked against the host the user typed, not the address derived
    # from it, so a dev allow-list of hostnames still matches.
    try:
        check_output_host(request.host)
    except OutputHostBlocked as e:
        return _verdict_for_blocked_host(e.host)

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
        # Off the event loop (#1826 class): a board that accepts the connection
        # and never answers holds the loop for the full 10s timeout otherwise.
        # The sink's arguments are unchanged and it stays adjacent to the
        # private-network gate above, so the SSRF barrier #1938 verified with
        # CodeQL is not reshaped — only the thread it runs on changes.
        response = await asyncio.to_thread(http_requests.post, url, headers=headers, timeout=10)
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
