"""Value-level contract goldens for the /network/wifi API (Phase 2 §2, Task 8).

Pinned as **values**, not shapes: the shape corpus in
``tests/test_response_shape_goldens.py`` records key sets and type names, so it
cannot see a swapped ``ssid``, a signal strength that stopped being reported,
a 501 that became a 400, or an error body whose only readable text moved from
one key to another. Those are exactly the regressions an extraction plus a
conventions pass can introduce.

Recorded against the unmodified trunk first (commit 1 of this PR), then
re-pinned by the conventions pass. What deliberately changed, and nothing else:

* **One error contract.** ``_wifi_unavailable`` served
  ``{"detail": {"status": "unavailable", "reason": ...}}`` and ``_wifi_error``
  served ``{"detail": {"status": "error", "error": ...}}``. Both now serve
  FastAPI's ``{"detail": <string>}`` carrying the same sentence — the shape
  ``docs/internal/reference/API_CONVENTIONS.md`` §"Error contract" mandates.
  The web client already stringified a dict detail
  (``web/src/lib/api/core.ts``), so the user-visible effect is a toast that
  reads ``auth failed`` instead of
  ``{"status":"error","error":"auth failed"}``.
* **``DELETE /network/wifi/saved/{con_name}`` returns the forgotten profile**
  (``{"name": "HomeNet"}``, a declared ``ForgottenNetworkResponse``) instead of
  the ``{"status": "ok"}`` envelope the conventions ban, which the untyped
  ``response_model=dict[str, str]`` had let through.

Every other value — the capability probe, the status/scan/saved/connect
payloads, the 501-when-unavailable rule, the 400-on-``WiFiError`` rule, and
which service method each route calls — is unchanged from the pre-conversion
recording. None was weakened.

This file supersedes ``tests/test_api_wifi.py``, which it absorbed: every
behavior that file asserted is asserted here, by value, plus seven more.

Seam targets
------------
The WiFi service singleton is ``src.network.wifi.get_wifi_service``, which the
extraction did not move, so no ``patch()`` target in this file changed when the
handlers left ``src/api_server.py``.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.network.wifi import (
    SavedNetwork,
    WiFiCapability,
    WiFiConnectResult,
    WiFiError,
    WiFiNetwork,
    WiFiStatus,
    get_wifi_service,
)

#: Every route but ``/capability`` refuses with this status when the
#: deployment cannot manage WiFi. 501 (not 503) because the capability is
#: absent by design off the FiestaPi image, not temporarily down.
UNAVAILABLE_STATUS = 501


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_capability_cache():
    svc = get_wifi_service()
    svc._cached_capability = None
    yield
    svc._cached_capability = None


@pytest.fixture
def available():
    svc = get_wifi_service()
    svc._cached_capability = WiFiCapability(available=True)
    return svc


@pytest.fixture
def unavailable():
    svc = get_wifi_service()
    svc._cached_capability = WiFiCapability(
        available=False, reason="WiFi management is only available on the FiestaPi image."
    )
    return svc


CONNECTED = WiFiStatus(
    connected=True,
    ssid="HomeNet",
    ip_address="192.168.1.42",
    gateway="192.168.1.1",
    signal=75,
    internet_reachable=True,
)


# ---------------------------------------------------------------------------
# capability — the probe the UI hides the whole Network tab on
# ---------------------------------------------------------------------------


def test_capability_reports_available_with_no_reason_on_a_pi(client, available):
    resp = client.get("/network/wifi/capability")
    assert resp.status_code == 200
    assert resp.json() == {"available": True, "reason": None}


def test_capability_reports_unavailable_with_the_service_reason(client, unavailable):
    resp = client.get("/network/wifi/capability")
    assert resp.status_code == 200
    assert resp.json() == {
        "available": False,
        "reason": "WiFi management is only available on the FiestaPi image.",
    }


def test_capability_answers_200_even_when_wifi_is_unmanageable(client, unavailable):
    """The probe is the one route that must never refuse — it *is* the refusal."""
    assert client.get("/network/wifi/capability").status_code == 200


# ---------------------------------------------------------------------------
# every other route refuses when the capability is absent
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
def test_routes_refuse_with_501_when_wifi_is_unmanageable(client, unavailable, method, path):
    resp = getattr(client, method)(path)
    assert resp.status_code == UNAVAILABLE_STATUS
    # Re-pinned: the reason is the whole detail string, not a nested dict.
    assert resp.json()["detail"] == "WiFi management is only available on the FiestaPi image."


def test_connect_refuses_with_501_when_wifi_is_unmanageable(client, unavailable):
    resp = client.post("/network/wifi/connect", json={"ssid": "HomeNet", "password": "x"})
    assert resp.status_code == UNAVAILABLE_STATUS
    # Re-pinned: the reason is the whole detail string, not a nested dict.
    assert resp.json()["detail"] == "WiFi management is only available on the FiestaPi image."


def test_the_refusal_falls_back_to_a_sentence_when_the_service_gives_no_reason(client):
    svc = get_wifi_service()
    svc._cached_capability = WiFiCapability(available=False, reason=None)
    resp = client.get("/network/wifi/status")
    assert resp.status_code == UNAVAILABLE_STATUS
    assert resp.json()["detail"] == "WiFi management is unavailable on this deployment."


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def test_status_reports_every_field_of_the_current_connection(client, available):
    with patch.object(get_wifi_service(), "status", return_value=CONNECTED):
        resp = client.get("/network/wifi/status")
    assert resp.status_code == 200
    assert resp.json() == {
        "connected": True,
        "ssid": "HomeNet",
        "ip_address": "192.168.1.42",
        "gateway": "192.168.1.1",
        "signal": 75,
        "internet_reachable": True,
    }


def test_status_reports_a_wifi_error_as_400_carrying_the_message(client, available):
    with patch.object(get_wifi_service(), "status", side_effect=WiFiError("nmcli broken")):
        resp = client.get("/network/wifi/status")
    assert resp.status_code == 400
    # Re-pinned: the message is the detail, not detail["error"].
    assert resp.json()["detail"] == "nmcli broken"


# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------


def test_scan_returns_the_networks_the_service_found_in_order(client, available):
    found = [
        WiFiNetwork(ssid="HomeNet", signal=80, security="WPA2", in_use=True),
        WiFiNetwork(ssid="GuestNet", signal=55, security="WPA2", in_use=False),
    ]
    with patch.object(get_wifi_service(), "scan", return_value=found):
        resp = client.post("/network/wifi/scan")
    assert resp.status_code == 200
    assert resp.json() == [
        {"ssid": "HomeNet", "signal": 80, "security": "WPA2", "in_use": True},
        {"ssid": "GuestNet", "signal": 55, "security": "WPA2", "in_use": False},
    ]


def test_scan_reports_a_wifi_error_as_400(client, available):
    with patch.object(get_wifi_service(), "scan", side_effect=WiFiError("no wireless device")):
        resp = client.post("/network/wifi/scan")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "no wireless device"


# ---------------------------------------------------------------------------
# saved + forget
# ---------------------------------------------------------------------------


def test_saved_returns_the_stored_profiles(client, available):
    with patch.object(
        get_wifi_service(), "saved_networks", return_value=[SavedNetwork(name="HomeNet", autoconnect=True)]
    ):
        resp = client.get("/network/wifi/saved")
    assert resp.status_code == 200
    assert resp.json() == [{"name": "HomeNet", "autoconnect": True}]


def test_forget_deletes_the_named_profile_and_names_it_back(client, available):
    async def _ok(_name):
        return None

    with patch.object(get_wifi_service(), "forget", side_effect=_ok) as forget:
        resp = client.delete("/network/wifi/saved/HomeNet")
    assert resp.status_code == 200
    # Re-pinned: the deleted profile, not {"status": "ok"}.
    assert resp.json() == {"name": "HomeNet"}
    forget.assert_awaited_once_with("HomeNet")


def test_forget_reports_a_wifi_error_as_400(client, available):
    async def _boom(_name):
        raise WiFiError("profile not found")

    with patch.object(get_wifi_service(), "forget", side_effect=_boom):
        resp = client.delete("/network/wifi/saved/Nope")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "profile not found"


# ---------------------------------------------------------------------------
# connect + disconnect
# ---------------------------------------------------------------------------


def test_connect_returns_the_new_status_the_confirmation_flag_and_the_message(client, available):
    result = WiFiConnectResult(status=CONNECTED, connectivity_confirmed=True, message="Connected to HomeNet.")

    async def _connect(**kwargs):
        return result

    with patch.object(get_wifi_service(), "connect", side_effect=_connect) as connect:
        resp = client.post("/network/wifi/connect", json={"ssid": "HomeNet", "password": "hunter2"})
    assert resp.status_code == 200
    assert resp.json() == {
        "status": {
            "connected": True,
            "ssid": "HomeNet",
            "ip_address": "192.168.1.42",
            "gateway": "192.168.1.1",
            "signal": 75,
            "internet_reachable": True,
        },
        "connectivity_confirmed": True,
        "message": "Connected to HomeNet.",
    }
    connect.assert_awaited_once_with(ssid="HomeNet", password="hunter2", hidden=False)


def test_connect_defaults_hidden_to_false_and_password_to_none(client, available):
    result = WiFiConnectResult(status=CONNECTED, connectivity_confirmed=False, message="Associated.")

    async def _connect(**kwargs):
        return result

    with patch.object(get_wifi_service(), "connect", side_effect=_connect) as connect:
        resp = client.post("/network/wifi/connect", json={"ssid": "OpenNet"})
    assert resp.status_code == 200
    assert resp.json()["connectivity_confirmed"] is False
    connect.assert_awaited_once_with(ssid="OpenNet", password=None, hidden=False)


def test_connect_reports_a_wifi_error_as_400(client, available):
    async def _boom(**kwargs):
        raise WiFiError("auth failed")

    with patch.object(get_wifi_service(), "connect", side_effect=_boom):
        resp = client.post("/network/wifi/connect", json={"ssid": "HomeNet", "password": "bad"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "auth failed"


def test_connect_rejects_a_body_with_no_ssid_as_422(client, available):
    assert client.post("/network/wifi/connect", json={"password": "x"}).status_code == 422


def test_disconnect_returns_the_status_after_the_teardown(client, available):
    offline = WiFiStatus(
        connected=False, ssid=None, ip_address=None, gateway=None, signal=None, internet_reachable=False
    )

    async def _disc():
        return offline

    with patch.object(get_wifi_service(), "disconnect", side_effect=_disc):
        resp = client.post("/network/wifi/disconnect")
    assert resp.status_code == 200
    assert resp.json() == {
        "connected": False,
        "ssid": None,
        "ip_address": None,
        "gateway": None,
        "signal": None,
        "internet_reachable": False,
    }


def test_disconnect_reports_a_wifi_error_as_400(client, available):
    async def _boom():
        raise WiFiError("nmcli down failed")

    with patch.object(get_wifi_service(), "disconnect", side_effect=_boom):
        resp = client.post("/network/wifi/disconnect")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "nmcli down failed"
