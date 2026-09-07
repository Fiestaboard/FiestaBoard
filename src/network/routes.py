"""FastAPI router for the ``/network/wifi`` endpoints (FiestaPi only).

The seven handlers here were moved verbatim from ``src/api_server.py``
(Phase 2, Task 8) and then converted to
``docs/internal/reference/API_CONVENTIONS.md``: a declared ``response_model``
on every route, the failure codes each route can raise declared in
``responses=``, and one error contract — FastAPI's ``{"detail": <string>}``
— replacing the two hand-rolled dict payloads the handlers used to raise.
``tests/conventions_manifest.json`` lists ``network`` so a regression fails the
build.

The WiFi service singleton already had a canonical home
(``src.network.wifi.get_wifi_service``), so this module imports nothing from
``src.api_server`` (``tests/test_network_decoupled.py`` asserts that in a fresh
interpreter) and no test patch target changed with the move.

Why the refusals are what they are
----------------------------------
``501`` for "this deployment cannot manage WiFi" rather than ``503``: the
capability is absent by design off the FiestaPi image, not temporarily down,
and ``GET /network/wifi/capability`` exists precisely so the UI can hide the
whole Network tab instead of discovering it one 501 at a time. ``400`` for a
``WiFiError``: every one of them is nmcli refusing an operation the caller
asked for (bad passphrase, unknown profile, no wireless device).
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from src.api_errors import errors

from .models import (
    ForgottenNetworkResponse,
    SavedNetworkModel,
    WiFiCapabilityResponse,
    WiFiConnectRequest,
    WiFiConnectResponse,
    WiFiNetworkModel,
    WiFiStatusModel,
)
from .wifi import WiFiError, get_wifi_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["network"])

#: Served when the deployment cannot manage WiFi and the service offered no
#: reason of its own.
UNAVAILABLE_FALLBACK = "WiFi management is unavailable on this deployment."


def _require_capability():
    """The WiFi service, or a 501 saying why this deployment has no WiFi API."""
    service = get_wifi_service()
    capability = service.capability()
    if not capability.available:
        raise HTTPException(status_code=501, detail=capability.reason or UNAVAILABLE_FALLBACK)
    return service


def _wifi_error(exc: WiFiError) -> HTTPException:
    """nmcli refused the operation — the caller's problem, so a 400."""
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/network/wifi/capability", response_model=WiFiCapabilityResponse)
async def wifi_capability():
    """Feature probe — does this deployment support WiFi management?

    The UI calls this once on load and hides the Network tab when the
    answer is False, so generic Docker users never see WiFi controls.
    """
    cap = get_wifi_service().capability()
    return WiFiCapabilityResponse(available=cap.available, reason=cap.reason)


@router.get("/network/wifi/status", response_model=WiFiStatusModel, responses=errors(400, 501))
async def wifi_status():
    """The current association: SSID, addresses, signal, internet reachability."""
    svc = _require_capability()
    try:
        status = await asyncio.to_thread(svc.status)
    except WiFiError as exc:
        raise _wifi_error(exc) from exc
    return WiFiStatusModel(**status.__dict__)


@router.post("/network/wifi/scan", response_model=list[WiFiNetworkModel], responses=errors(400, 501))
async def wifi_scan():
    """Trigger a rescan and return de-duplicated networks (strongest signal)."""
    svc = _require_capability()
    try:
        networks = await asyncio.to_thread(svc.scan)
    except WiFiError as exc:
        raise _wifi_error(exc) from exc
    return [WiFiNetworkModel(**n.__dict__) for n in networks]


@router.get("/network/wifi/saved", response_model=list[SavedNetworkModel], responses=errors(400, 501))
async def wifi_saved():
    """The stored NetworkManager profiles this device will auto-join."""
    svc = _require_capability()
    try:
        saved = await asyncio.to_thread(svc.saved_networks)
    except WiFiError as exc:
        raise _wifi_error(exc) from exc
    return [SavedNetworkModel(**s.__dict__) for s in saved]


@router.post("/network/wifi/connect", response_model=WiFiConnectResponse, responses=errors(400, 501))
async def wifi_connect(payload: WiFiConnectRequest):
    """Create/replace a persistent profile and activate it.

    Returns the new status plus a `connectivity_confirmed` flag so the
    UI can warn the user when the AP associates but the internet probe
    fails (typical for wrong password / captive portal).
    """
    svc = _require_capability()
    try:
        result = await svc.connect(ssid=payload.ssid, password=payload.password, hidden=payload.hidden)
    except WiFiError as exc:
        raise _wifi_error(exc) from exc
    return WiFiConnectResponse(
        status=WiFiStatusModel(**result.status.__dict__),
        connectivity_confirmed=result.connectivity_confirmed,
        message=result.message,
    )


@router.post("/network/wifi/disconnect", response_model=WiFiStatusModel, responses=errors(400, 501))
async def wifi_disconnect():
    """Bring the active connection down and report the resulting status."""
    svc = _require_capability()
    try:
        status = await svc.disconnect()
    except WiFiError as exc:
        raise _wifi_error(exc) from exc
    return WiFiStatusModel(**status.__dict__)


@router.delete(
    "/network/wifi/saved/{con_name}",
    response_model=ForgottenNetworkResponse,
    responses=errors(400, 501),
)
async def wifi_forget(con_name: str):
    """Delete a stored profile so the device stops auto-joining it."""
    svc = _require_capability()
    try:
        await svc.forget(con_name)
    except WiFiError as exc:
        raise _wifi_error(exc) from exc
    return ForgottenNetworkResponse(name=con_name)
