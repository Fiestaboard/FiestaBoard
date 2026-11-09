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

from urllib.parse import quote, urlencode

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
    PairingRequest,
    PairingState,
    Success,
)
from .device_service import PAIRING_SECONDS, DeviceService, hub_identity
from .hub_addresses import hub_addresses, pick
from .origins import normalized_origin
from .service import get_auth_service

router = APIRouter(prefix="/auth/pairing", tags=["auth"])
RESPONSES = errors(400, 401, 403, 404, 409, 422, 429, 503)

#: The scheme and host the phone apps register for a scanned pairing code.
QR_PREFIX = "fiestaboard://pair#"
_CLAIM_FAILURES = frozenset({"invalid_grant", "expired_token"})


def _hub_for(request: Request, payload: PairingRequest) -> tuple[str, list[dict[str, str]]]:
    """The QR's hub address and the list it came from (H18); never loopback."""
    # require_browser_mutation has checked this origin against the portal's own address.
    addresses = hub_addresses(normalized_origin(request.headers.get("origin", "")))
    if not addresses:
        raise AuthFlowError(
            "no_reachable_address",
            "A phone can't reach this hub at localhost. Open FiestaBoard at its network address "
            "(or set FIESTABOARD_EXTERNAL_URL) and try again.",
            409,
        )
    hub = pick(addresses, payload.hub)
    if hub is None:
        raise AuthFlowError("invalid_request", "hub must be one of this hub's hub_addresses.", 400)
    return hub, addresses


@router.post("", response_model=PairingOffer, responses=RESPONSES)
def create_offer(request: Request, payload: PairingRequest | None = None):
    """Create a five-minute, single-use pairing code for a phone and return it as a QR payload.

    Browser session only (portal origin and CSRF token required). Cancels this
    account's earlier pending offers. Needs device sign-in to be on. The QR's
    hub is never loopback: the first of ``hub_addresses``, or the listed one
    the body names. A 409 when no address a phone could reach is known.
    """
    browser = require_browser_mutation(request)
    hub, addresses = _hub_for(request, payload or PairingRequest())
    pairing_id, code = DeviceService(get_auth_service()).create_pairing(browser)
    install_id, name = hub_identity()
    # quote, not quote_plus: a space is %20, which every URL parser decodes (iOS's
    # URLComponents leaves "+" as "+").
    fragment = urlencode({"v": "1", "hub": hub, "id": install_id, "name": name, "code": code}, quote_via=quote)
    return PairingOffer(
        pairing_id=pairing_id,
        qr_payload=QR_PREFIX + fragment,
        hub=hub,
        expires_in=PAIRING_SECONDS,
        hub_addresses=addresses,
    )


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
