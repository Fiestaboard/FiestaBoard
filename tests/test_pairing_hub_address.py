# ruff: noqa: F811 - pytest fixtures are imported from their home module
"""H18: the "Connect a phone" QR never tells the phone to use localhost.

A browser on the hub itself (``http://localhost:4420``) would otherwise put
its own origin in the pairing QR, an address that means the phone, not the
hub, once scanned. The offer now carries ``hub_addresses``, every address a
phone on the network might reach, best first: the browser's own origin
unless it is loopback, the operator's ``FIESTABOARD_EXTERNAL_URL``, the mDNS
name the hub advertises (``<hostname>.local``, as H13's TXT ``host=``), then
its LAN address. The QR uses the first, or the one the web picks from that
list. No loopback address is ever offered; with none left the offer is a 409.
"""

import logging
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from tests.test_auth_pairing import PASSWORD, auth, browser  # noqa: F401 - fixtures


class _Mdns:
    def __init__(self, running=True, url="http://fiestaboard.local:4420"):
        self.is_running = running
        self.local_url = url


@pytest.fixture
def network(monkeypatch):
    """The hub's view of its network, steerable per test: mDNS up, LAN at 192.168.1.50, not in Docker."""
    state = {"mdns": _Mdns(), "ip": "192.168.1.50", "docker": False}
    try:
        from src.auth import hub_addresses
    except ImportError:  # before H18: nothing to steer, and the tests say what is missing
        hub_addresses = None
    if hub_addresses is not None:
        monkeypatch.setattr(hub_addresses, "mdns_service", lambda: state["mdns"])
        monkeypatch.setattr(hub_addresses, "lan_ipv4", lambda: state["ip"])
        # The bridge test, not "in Docker": host networking keeps a real 172.16/12 LAN (review S3).
        monkeypatch.setattr(hub_addresses, "in_bridge_network", lambda: state["docker"], raising=False)
        monkeypatch.setattr(hub_addresses, "_warned", set(), raising=False)
    monkeypatch.delenv("FIESTABOARD_EXTERNAL_URL", raising=False)
    return state


def _signed_in(base_url):
    client = TestClient(app, base_url=base_url, headers={"User-Agent": "Mozilla/5.0 Test browser"})
    assert client.post("/auth/login", json={"username": "admin", "password": PASSWORD}).status_code == 200
    context = client.get("/auth/sessions/context")
    client.headers.update({"Origin": base_url, "X-CSRF-Token": context.json()["csrf_token"]})
    return client


@pytest.fixture
def on_the_hub(auth):
    """A browser on the hub itself."""
    return _signed_in("http://localhost:4420")


def _offer(client, **body):
    return client.post("/auth/pairing", json=body)


def _ok(client, **body):
    response = _offer(client, **body)
    assert response.status_code == 200, response.text
    return response.json()


def _qr_hub(payload):
    fields = parse_qs(urlsplit(payload["qr_payload"]).fragment)
    return fields["hub"][0]


def _urls(payload):
    return [address["url"] for address in payload["hub_addresses"]]


# ── from loopback ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "base_url",
    [
        "http://localhost:4420",
        "http://127.0.0.1:4420",
        "http://[::1]:4420",
        "http://app.localhost:4420",
        "http://0.0.0.0:4420",
    ],
)
def test_a_browser_on_the_hub_gets_the_mdns_name_not_loopback(auth, network, base_url):
    payload = _ok(_signed_in(base_url))

    assert payload["hub"] == "http://fiestaboard.local:4420" == _qr_hub(payload)
    assert payload["hub_addresses"] == [
        {"url": "http://fiestaboard.local:4420", "kind": "mdns"},
        {"url": "http://192.168.1.50:4420", "kind": "lan"},
    ]
    for loopback in ("localhost", "127.0.0.1", "[::1]"):
        assert loopback not in payload["qr_payload"]


def test_without_mdns_the_lan_address_is_offered_on_the_browsers_port(auth, network):
    network["mdns"] = _Mdns(running=False)

    payload = _ok(_signed_in("http://localhost:8080"))

    assert payload["hub"] == "http://192.168.1.50:8080" == _qr_hub(payload)
    assert payload["hub_addresses"] == [{"url": "http://192.168.1.50:8080", "kind": "lan"}]


def test_the_operators_external_url_comes_first(auth, network, on_the_hub, monkeypatch):
    monkeypatch.setenv("FIESTABOARD_EXTERNAL_URL", "https://board.example.net/")

    payload = _ok(on_the_hub)

    assert payload["hub"] == "https://board.example.net"
    assert payload["hub_addresses"][0] == {"url": "https://board.example.net", "kind": "configured"}


@pytest.mark.parametrize("configured", ["http://localhost:4420", "http://127.0.0.1:4420", "not a url", "ftp://x"])
def test_an_unusable_external_url_is_skipped(auth, network, on_the_hub, monkeypatch, configured):
    monkeypatch.setenv("FIESTABOARD_EXTERNAL_URL", configured)

    assert _urls(_ok(on_the_hub)) == ["http://fiestaboard.local:4420", "http://192.168.1.50:4420"]


def test_a_docker_bridge_address_is_not_a_lan_address(auth, network, on_the_hub):
    """Inside Docker's default bridge the hub sees 172.17.x, which no phone can reach."""
    network.update(ip="172.17.0.2", docker=True)

    assert _urls(_ok(on_the_hub)) == ["http://fiestaboard.local:4420"]


def test_the_same_range_outside_docker_is_a_lan_address(auth, network, on_the_hub):
    network.update(ip="172.20.4.9", docker=False)

    assert "http://172.20.4.9:4420" in _urls(_ok(on_the_hub))


@pytest.mark.parametrize("ip", ["127.0.0.1", "0.0.0.0", ""])
def test_no_loopback_or_unknown_lan_address_is_offered(auth, network, on_the_hub, ip):
    network["ip"] = ip

    assert _urls(_ok(on_the_hub)) == ["http://fiestaboard.local:4420"]


def test_with_nothing_a_phone_can_reach_there_is_no_offer(auth, network, on_the_hub):
    network.update(mdns=_Mdns(running=False), ip="127.0.0.1")

    response = _offer(on_the_hub)

    assert response.status_code == 409
    assert response.json()["error"] == "no_reachable_address"
    with auth.sessions.transaction() as db:
        assert db.execute("SELECT COUNT(*) FROM pairings").fetchone()[0] == 0


# ── from the network ────────────────────────────────────────────────────────


def test_a_browser_on_the_network_keeps_its_own_origin_first(auth, network, browser):
    payload = _ok(browser)

    assert payload["hub"] == "http://testserver" == _qr_hub(payload)
    assert payload["hub_addresses"] == [
        {"url": "http://testserver", "kind": "browser"},
        {"url": "http://fiestaboard.local:4420", "kind": "mdns"},
        {"url": "http://192.168.1.50", "kind": "lan"},
    ]


def test_an_address_is_listed_once(auth, network):
    network["mdns"] = _Mdns(url="http://192.168.1.50:4420")

    assert _urls(_ok(_signed_in("http://192.168.1.50:4420"))) == ["http://192.168.1.50:4420"]


# ── the web picks ───────────────────────────────────────────────────────────


def test_the_web_may_pick_another_listed_address(auth, network, on_the_hub):
    payload = _ok(on_the_hub, hub="http://192.168.1.50:4420")

    assert payload["hub"] == "http://192.168.1.50:4420" == _qr_hub(payload)


@pytest.mark.parametrize(
    "hub", ["http://localhost:4420", "https://attacker.example", "http://192.168.1.50:9999", "javascript:alert(1)"]
)
def test_an_address_not_on_the_list_is_refused(auth, network, on_the_hub, hub):
    """The QR can only point at this hub: a picked address must be one it offered."""
    response = _offer(on_the_hub, hub=hub)

    # A body that passed validation and is refused on meaning: 400, never a
    # hand-raised 422 (API_CONVENTIONS, #1923; review M1).
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"
    with auth.sessions.transaction() as db:
        assert db.execute("SELECT COUNT(*) FROM pairings").fetchone()[0] == 0


@pytest.mark.parametrize(
    ("host", "loopback"),
    [
        ("localhost", True),
        ("LOCALHOST", True),
        ("app.localhost", True),
        ("127.0.0.1", True),
        ("127.8.9.10", True),
        ("::1", True),
        ("[::1]", True),
        ("0.0.0.0", True),
        ("::", True),
        ("fiestaboard.local", False),
        ("192.168.1.50", False),
        ("[fd00::1]", False),
        ("localhost.example.com", False),
        ("localhost.", True),
        ("LocalHost.", True),
        ("app.localhost.", True),
    ],
)
def test_what_counts_as_loopback(host, loopback):
    from src.auth.hub_addresses import is_loopback

    assert is_loopback(host) is loopback


def test_a_trailing_dot_localhost_origin_never_reaches_the_qr(auth, network):
    payload = _ok(_signed_in("http://localhost.:4420"))

    assert payload["hub"] == "http://fiestaboard.local:4420"
    assert "localhost" not in payload["qr_payload"]


# ── a misconfigured external URL is said, once (review S2) ──────────────────


def test_a_malformed_external_url_is_logged_once(auth, network, on_the_hub, monkeypatch, caplog):
    monkeypatch.setenv("FIESTABOARD_EXTERNAL_URL", "https://hub.example.com/fiesta")
    caplog.set_level(logging.WARNING, logger="src.auth.hub_addresses")

    _ok(on_the_hub)
    _ok(on_the_hub)

    warnings = [r.getMessage() for r in caplog.records if r.name == "src.auth.hub_addresses"]
    assert len(warnings) == 1
    assert "FIESTABOARD_EXTERNAL_URL" in warnings[0] and "scheme://host[:port]" in warnings[0]


@pytest.mark.parametrize("configured", [None, "https://hub.example.com:8443"])
def test_an_unset_or_good_external_url_is_not_logged(auth, network, on_the_hub, monkeypatch, caplog, configured):
    if configured:
        monkeypatch.setenv("FIESTABOARD_EXTERNAL_URL", configured)
    caplog.set_level(logging.WARNING, logger="src.auth.hub_addresses")

    _ok(on_the_hub)

    assert [r for r in caplog.records if r.name == "src.auth.hub_addresses"] == []


# ── a bridge network, not merely Docker (review S3) ─────────────────────────


@pytest.mark.parametrize(
    ("dockerenv", "docker0", "bridge"),
    [(True, False, True), (True, True, False), (False, False, False), (False, True, False)],
    ids=["bridge-container", "host-network-container", "no-docker", "docker-host-itself"],
)
def test_a_bridge_network_is_docker_without_the_hosts_docker0(tmp_path, monkeypatch, dockerenv, docker0, bridge):
    """In a bridge container the host's ``docker0`` is not visible; with
    ``network_mode: host`` it is, and the container's LAN address is real."""
    from src.auth import hub_addresses

    marker, iface = tmp_path / ".dockerenv", tmp_path / "docker0"
    if dockerenv:
        marker.touch()
    if docker0:
        iface.mkdir()
    monkeypatch.setattr(hub_addresses, "DOCKERENV", marker)
    monkeypatch.setattr(hub_addresses, "HOST_DOCKER_BRIDGE", iface)

    assert hub_addresses.in_bridge_network() is bridge
