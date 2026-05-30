"""Integration tests for the /network/wifi/* HTTP endpoints."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.network import wifi as wifi_module
from src.network.wifi import (
    SavedNetwork,
    WiFiCapability,
    WiFiConnectResult,
    WiFiError,
    WiFiNetwork,
    WiFiStatus,
    get_wifi_service,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_capability_cache():
    """Each test re-derives capability; the singleton's cache must not leak."""
    svc = get_wifi_service()
    svc._cached_capability = None
    yield
    svc._cached_capability = None


@pytest.fixture
def force_available():
    svc = get_wifi_service()
    svc._cached_capability = WiFiCapability(available=True)
    return svc


@pytest.fixture
def force_unavailable():
    svc = get_wifi_service()
    svc._cached_capability = WiFiCapability(
        available=False, reason="WiFi management is only available on the FiestaPi image."
    )
    return svc


# ---------------------------------------------------------------------------
# capability
# ---------------------------------------------------------------------------

def test_capability_returns_unavailable_off_pi(client, force_unavailable):
    resp = client.get("/network/wifi/capability")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert "FiestaPi" in body["reason"]


def test_capability_returns_available_on_pi(client, force_available):
    resp = client.get("/network/wifi/capability")
    assert resp.status_code == 200
    assert resp.json() == {"available": True, "reason": None}


# ---------------------------------------------------------------------------
# Endpoints return 501 when unavailable
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/network/wifi/status"),
        ("post", "/network/wifi/scan"),
        ("get", "/network/wifi/saved"),
        ("post", "/network/wifi/disconnect"),
        ("delete", "/network/wifi/saved/HomeNet"),
    ],
)
def test_endpoints_return_501_when_unavailable(client, force_unavailable, method, path):
    resp = getattr(client, method)(path)
    assert resp.status_code == 501
    assert "unavailable" in resp.json()["detail"]["status"]


def test_connect_returns_501_when_unavailable(client, force_unavailable):
    resp = client.post(
        "/network/wifi/connect",
        json={"ssid": "HomeNet", "password": "x"},
    )
    assert resp.status_code == 501


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

def test_status_returns_current_state(client, force_available):
    svc = get_wifi_service()
    fake = WiFiStatus(
        connected=True,
        ssid="HomeNet",
        ip_address="192.168.1.42",
        gateway="192.168.1.1",
        signal=75,
        internet_reachable=True,
    )
    with patch.object(svc, "status", return_value=fake):
        resp = client.get("/network/wifi/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ssid"] == "HomeNet"
    assert body["ip_address"] == "192.168.1.42"
    assert body["internet_reachable"] is True


def test_status_translates_wifi_error_to_400(client, force_available):
    svc = get_wifi_service()
    with patch.object(svc, "status", side_effect=WiFiError("nmcli broken")):
        resp = client.get("/network/wifi/status")
    assert resp.status_code == 400
    assert "nmcli broken" in resp.json()["detail"]["error"]


# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------

def test_scan_returns_networks(client, force_available):
    svc = get_wifi_service()
    fake = [
        WiFiNetwork(ssid="HomeNet", signal=80, security="WPA2", in_use=True),
        WiFiNetwork(ssid="GuestNet", signal=55, security="WPA2", in_use=False),
    ]
    with patch.object(svc, "scan", return_value=fake):
        resp = client.post("/network/wifi/scan")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["ssid"] == "HomeNet"
    assert body[0]["in_use"] is True


# ---------------------------------------------------------------------------
# saved + forget
# ---------------------------------------------------------------------------

def test_saved_returns_profiles(client, force_available):
    svc = get_wifi_service()
    fake = [SavedNetwork(name="HomeNet", autoconnect=True)]
    with patch.object(svc, "saved_networks", return_value=fake):
        resp = client.get("/network/wifi/saved")
    assert resp.status_code == 200
    assert resp.json() == [{"name": "HomeNet", "autoconnect": True}]


def test_forget_deletes_profile(client, force_available):
    svc = get_wifi_service()

    async def _ok(_name):
        return None

    with patch.object(svc, "forget", side_effect=_ok) as forget:
        resp = client.delete("/network/wifi/saved/HomeNet")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    forget.assert_awaited_once_with("HomeNet")


# ---------------------------------------------------------------------------
# connect + disconnect
# ---------------------------------------------------------------------------

def test_connect_returns_status_and_confirmation(client, force_available):
    svc = get_wifi_service()
    status = WiFiStatus(
        connected=True,
        ssid="HomeNet",
        ip_address="192.168.1.42",
        gateway="192.168.1.1",
        signal=80,
        internet_reachable=True,
    )
    result = WiFiConnectResult(
        status=status,
        connectivity_confirmed=True,
        message="Connected to HomeNet.",
    )

    async def _connect(**kwargs):
        return result

    with patch.object(svc, "connect", side_effect=_connect):
        resp = client.post(
            "/network/wifi/connect",
            json={"ssid": "HomeNet", "password": "hunter2"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["connectivity_confirmed"] is True
    assert body["status"]["ssid"] == "HomeNet"


def test_connect_translates_wifi_error(client, force_available):
    svc = get_wifi_service()

    async def _boom(**kwargs):
        raise WiFiError("auth failed")

    with patch.object(svc, "connect", side_effect=_boom):
        resp = client.post(
            "/network/wifi/connect",
            json={"ssid": "HomeNet", "password": "bad"},
        )
    assert resp.status_code == 400


def test_disconnect_returns_new_status(client, force_available):
    svc = get_wifi_service()
    fake = WiFiStatus(
        connected=False,
        ssid=None,
        ip_address=None,
        gateway=None,
        signal=None,
        internet_reachable=False,
    )

    async def _disc():
        return fake

    with patch.object(svc, "disconnect", side_effect=_disc):
        resp = client.post("/network/wifi/disconnect")
    assert resp.status_code == 200
    assert resp.json()["connected"] is False
