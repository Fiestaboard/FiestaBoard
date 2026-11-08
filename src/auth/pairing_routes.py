"""Pair a phone by QR code (H11).

A signed-in browser asks for a pairing offer and shows it as a QR code. The
FiestaBoard phone app scans it and claims the offer, and receives the same
``fb_mob_`` credential with scope ``control`` that a password sign-in gives
(``src/auth/scopes.py``).

The one-time code is in the QR's URL fragment and in the claim's JSON body,
never in a request URL, so no access log, proxy or Referer ever sees it. It
lives five minutes, works once, and only the newest offer of an account is
live. Claims are rate limited per address, and a wrong code counts against the
same lockout as a wrong password.
"""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Request

from src.api_errors import errors

from . import routes as auth_routes
from .browser_routes import require_browser_mutation, require_browser_session
from .device_models import (
    AuthFlowError,
    DeviceMetadata,
    DeviceTokenResult,
    PairingClaim,
    PairingOffer,
    PairingState,
    Success,
)
from .device_service import PAIRING_SECONDS, DeviceService, hub_identity
from .origins import normalized_origin
from .service import get_auth_service

router = APIRouter(prefix="/auth/pairing", tags=["auth"])
RESPONSES = errors(400, 401, 403, 404, 409, 422, 429, 503)

#: The scheme and host the phone apps register for a scanned pairing code.
QR_PREFIX = "fiestaboard://pair#"
_CLAIM_FAILURES = frozenset({"invalid_grant", "expired_token"})


def _hub_url(origin: tuple[str, str, int] | None) -> str:
    """``scheme://host[:port]`` from a validated origin, without a default port."""
    if origin is None:
        return ""
    scheme, host, port = origin
    if ":" in host:
        host = f"[{host}]"
    default = 443 if scheme == "https" else 80
    return f"{scheme}://{host}" + ("" if port == default else f":{port}")


@router.post("", response_model=PairingOffer, responses=RESPONSES)
def create_offer(request: Request):
    """Create a five-minute, single-use pairing code for a phone and return it as a QR payload.

    Browser session only (portal origin and CSRF token required). Cancels this
    account's earlier pending offers. Needs device sign-in to be on.
    """
    browser = require_browser_mutation(request)
    # require_browser_mutation has checked this origin against the portal's own address.
    hub = _hub_url(normalized_origin(request.headers.get("origin", "")))
    pairing_id, code = DeviceService(get_auth_service()).create_pairing(browser)
    install_id, name = hub_identity()
    fragment = urlencode({"v": "1", "hub": hub, "id": install_id, "name": name, "code": code})
    return PairingOffer(pairing_id=pairing_id, qr_payload=QR_PREFIX + fragment, expires_in=PAIRING_SECONDS)


@router.delete("", response_model=Success, responses=RESPONSES)
def cancel_offers(request: Request):
    """Cancel this account's pending pairing codes (the Connect a phone dialog closed)."""
    browser = require_browser_mutation(request)
    DeviceService(get_auth_service()).cancel_pairings(browser.username)
    return Success()


@router.get("/{pairing_id}", response_model=PairingState, responses=RESPONSES)
def offer_state(pairing_id: str, request: Request):
    """Whether a pairing offer is still waiting, was claimed (and by which phone), expired or was cancelled."""
    browser = require_browser_session(request)
    state = DeviceService(get_auth_service()).pairing_state(browser.username, pairing_id)
    if state is None:
        raise AuthFlowError("not_found", "No such pairing code.", 404)
    return state


@router.post("/claim", response_model=DeviceTokenResult, responses=RESPONSES)
def claim(payload: PairingClaim, request: Request):
    """Trade a scanned pairing code for a phone sign-in with scope ``control``.

    For the iOS and Android apps only. Needs no session: the code is the
    credential. Each address gets ten attempts a minute, and a wrong, used or
    expired code counts towards the sign-in lockout.
    """
    ip = auth_routes._client_ip(request)
    auth_routes._check_lockout(ip)
    service = DeviceService(get_auth_service())
    service.limit("pairing-claim:" + ip, 10)
    metadata = DeviceMetadata(
        client_id=payload.client_id, device_name=payload.device_name, app_version=payload.app_version
    )
    try:
        return service.claim_pairing(payload.pairing_code, metadata)
    except AuthFlowError as exc:
        if exc.error in _CLAIM_FAILURES:
            auth_routes._record_failure(ip)
        raise
