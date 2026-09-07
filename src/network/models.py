"""Wire models for the ``/network/wifi`` API.

Moved verbatim from ``src/api_server.py`` (Phase 2, Task 8). They describe
NetworkManager state as the UI consumes it, which is deliberately *not* the
dataclasses in :mod:`src.network.wifi` — those are the service's own vocabulary
and carry fields the API has never published.
"""

from __future__ import annotations

from pydantic import BaseModel


class WiFiCapabilityResponse(BaseModel):
    """Feature probe: can this deployment manage WiFi at all?"""

    available: bool
    reason: str | None = None


class WiFiNetworkModel(BaseModel):
    """One access point seen by a scan."""

    ssid: str
    signal: int  # 0..100
    security: str
    in_use: bool


class SavedNetworkModel(BaseModel):
    """One stored NetworkManager profile."""

    name: str
    autoconnect: bool


class WiFiStatusModel(BaseModel):
    """The current association, if any."""

    connected: bool
    ssid: str | None = None
    ip_address: str | None = None
    gateway: str | None = None
    signal: int | None = None
    internet_reachable: bool


class WiFiConnectRequest(BaseModel):
    """Body of ``POST /network/wifi/connect``."""

    ssid: str
    password: str | None = None
    hidden: bool = False


class WiFiConnectResponse(BaseModel):
    """The new status plus whether the internet probe actually succeeded."""

    status: WiFiStatusModel
    connectivity_confirmed: bool
    message: str


class ForgottenNetworkResponse(BaseModel):
    """The profile ``DELETE /network/wifi/saved/{con_name}`` removed."""

    name: str
