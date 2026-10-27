"""The network hint core derives from the requesting browser's address.

In Docker bridge mode (the default) the container's own address names a
container network, so a scan needs the user's LAN from somewhere. The web UI
sends ``hint_host`` only when the page was opened at a private IPv4 literal;
at ``http://fiestaboard.local:4420`` it sends nothing. Core then falls back
to the address the request came from — trusted only as the in-container
nginx reports it — and only when that address says something about the LAN.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from src.outputs import client_hint
from src.outputs.actions import _checked_input
from src.outputs.client_hint import client_address, client_lan_hint, parse_route_table
from src.outputs.hooks import HINT_HOST, OutputActionSpec
from src.plugins.loader import PluginLoader

DOCKER_BRIDGE = (ipaddress.IPv4Network("172.17.0.0/16"),)


@pytest.fixture
def bridge_mode():
    """The container sits on Docker's default bridge, 172.17.0.0/16, on a Linux host."""
    with (
        mock.patch.object(client_hint, "interface_networks", return_value=DOCKER_BRIDGE),
        mock.patch.object(client_hint, "_docker_desktop", return_value=False),
    ):
        yield


def _request(peer: str | None, headers: dict[str, str] | None = None):
    client = SimpleNamespace(host=peer, port=50000) if peer is not None else None
    lowered = {k.lower(): v for k, v in (headers or {}).items()}
    return SimpleNamespace(client=client, headers=lowered)


# --- whose address it is ---------------------------------------------------------------------


def test_a_direct_peer_is_the_client():
    assert client_address(_request("192.168.1.20")) == "192.168.1.20"


def test_behind_the_in_container_nginx_the_real_ip_header_is_the_client():
    assert client_address(_request("127.0.0.1", {"X-Real-IP": "192.168.1.20"})) == "192.168.1.20"


def test_behind_the_in_container_nginx_without_real_ip_the_last_forwarded_hop_is_the_client():
    request = _request("127.0.0.1", {"X-Forwarded-For": "10.9.9.9, 192.168.1.20"})
    assert client_address(request) == "192.168.1.20"


def test_a_peer_that_is_not_loopback_cannot_name_another_client_by_header():
    request = _request("203.0.113.9", {"X-Real-IP": "192.168.1.20", "X-Forwarded-For": "192.168.1.20"})
    assert client_address(request) == "203.0.113.9"


def test_an_ipv6_loopback_peer_is_trusted_like_ipv4_loopback():
    assert client_address(_request("::1", {"X-Real-IP": "192.168.1.20"})) == "192.168.1.20"


def test_no_peer_is_no_client():
    assert client_address(_request(None, {"X-Real-IP": "192.168.1.20"})) is None


# --- whether the address is a usable hint ----------------------------------------------------


def test_a_lan_client_in_bridge_mode_is_a_hint(bridge_mode):
    assert client_lan_hint(_request("127.0.0.1", {"X-Real-IP": "192.168.1.20"})) == "192.168.1.20"


def test_the_docker_bridge_gateway_is_not_a_hint(bridge_mode):
    """A browser on the Docker host itself reaches the container from 172.17.0.1."""
    assert client_lan_hint(_request("127.0.0.1", {"X-Real-IP": "172.17.0.1"})) is None


def test_an_address_on_any_of_the_containers_own_networks_is_not_a_hint():
    networks = (ipaddress.IPv4Network("172.18.0.0/16"), ipaddress.IPv4Network("10.20.0.0/24"))
    with (
        mock.patch.object(client_hint, "interface_networks", return_value=networks),
        mock.patch.object(client_hint, "_docker_desktop", return_value=False),
    ):
        assert client_lan_hint(_request("10.20.0.7")) is None
        assert client_lan_hint(_request("172.18.0.1")) is None
        assert client_lan_hint(_request("10.20.1.7")) == "10.20.1.7"


def test_the_home_assistant_supervisor_is_not_a_hint(bridge_mode):
    assert client_lan_hint(_request("127.0.0.1", {"X-Real-IP": "172.30.32.2"})) is None


def test_a_request_through_home_assistant_ingress_is_not_a_hint(bridge_mode):
    request = _request("127.0.0.1", {"X-Real-IP": "192.168.1.20", "X-Ingress-Path": "/api/hassio_ingress/abc"})
    assert client_lan_hint(request) is None


def test_docker_desktops_vm_network_is_not_a_hint():
    """Docker Desktop NATs every published-port connection to 192.168.65.1."""
    with (
        mock.patch.object(client_hint, "interface_networks", return_value=DOCKER_BRIDGE),
        mock.patch.object(client_hint, "_docker_desktop", return_value=True),
    ):
        assert client_lan_hint(_request("127.0.0.1", {"X-Real-IP": "192.168.65.1"})) is None


def test_192_168_65_is_an_ordinary_lan_off_docker_desktop(bridge_mode):
    assert client_lan_hint(_request("127.0.0.1", {"X-Real-IP": "192.168.65.40"})) == "192.168.65.40"


@pytest.mark.parametrize("address", ["127.0.0.1", "8.8.8.8", "fe80::1", "2001:db8::5", "not-an-ip", ""])
def test_a_loopback_public_or_ipv6_client_is_not_a_hint(bridge_mode, address):
    assert client_lan_hint(_request("127.0.0.1", {"X-Real-IP": address})) is None


def test_an_ipv4_mapped_ipv6_client_is_unwrapped(bridge_mode):
    assert client_lan_hint(_request("::ffff:192.168.1.20")) == "192.168.1.20"


def test_host_networking_lan_client_on_a_different_network_is_a_hint():
    """``network_mode: host``: the interfaces are the LAN's; a client elsewhere is still a hint."""
    with (
        mock.patch.object(client_hint, "interface_networks", return_value=(ipaddress.IPv4Network("10.0.1.0/24"),)),
        mock.patch.object(client_hint, "_docker_desktop", return_value=False),
    ):
        assert client_lan_hint(_request("10.0.2.30")) == "10.0.2.30"


def test_no_request_is_no_hint():
    assert client_lan_hint(None) is None


# --- the container's own networks --------------------------------------------------------------

_ROUTES = (
    "Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT\n"
    "eth0\t00000000\t010011AC\t0003\t0\t0\t0\t00000000\t0\t0\t0\n"
    "eth0\t000011AC\t00000000\t0001\t0\t0\t0\t0000FFFF\t0\t0\t0\n"
    "eth1\t0000A8C0\t00000000\t0001\t0\t0\t0\t00FFFFFF\t0\t0\t0\n"
    "eth1\t0002000A\t0100A8C0\t0003\t0\t0\t0\t00FFFFFF\t0\t0\t0\n"
)


def test_the_route_table_names_the_directly_connected_networks():
    """The default route and routes via a gateway are not this host's networks."""
    assert parse_route_table(_ROUTES) == (
        ipaddress.IPv4Network("172.17.0.0/16"),
        ipaddress.IPv4Network("192.168.0.0/24"),
    )


def test_an_unreadable_route_table_names_no_networks():
    assert parse_route_table("garbage\nnot a route\n") == ()


# --- the action input check: the fallback ----------------------------------------------------

_TIMEOUT_ONLY = {"type": "object", "properties": {"timeout": {"type": "number"}}, "additionalProperties": False}


def test_discover_without_a_browser_hint_gets_the_client_hint():
    spec = OutputActionSpec(id="discover", label="Scan", input_schema=_TIMEOUT_ONLY)
    assert _checked_input(spec, {"timeout": 3}, client_hint="192.168.1.20") == {"timeout": 3, HINT_HOST: "192.168.1.20"}


def test_discover_with_an_empty_browser_hint_gets_the_client_hint():
    spec = OutputActionSpec(id="discover", label="Scan")
    assert _checked_input(spec, {HINT_HOST: ""}, client_hint="192.168.1.20") == {HINT_HOST: "192.168.1.20"}


def test_the_browsers_hint_wins_over_the_client_hint():
    spec = OutputActionSpec(id="discover", label="Scan")
    assert _checked_input(spec, {HINT_HOST: "10.0.0.9"}, client_hint="192.168.1.20") == {HINT_HOST: "10.0.0.9"}


def test_an_action_declaring_the_hint_gets_the_client_hint_when_the_browser_sent_none():
    schema = {"type": "object", "properties": {HINT_HOST: {"type": "string"}}}
    spec = OutputActionSpec(id="find_pixoo", label="Find", input_schema=schema)
    assert _checked_input(spec, {}, client_hint="192.168.1.20") == {HINT_HOST: "192.168.1.20"}


def test_an_action_declaring_the_hint_keeps_the_browsers_hint():
    schema = {"type": "object", "properties": {HINT_HOST: {"type": "string"}}}
    spec = OutputActionSpec(id="find_pixoo", label="Find", input_schema=schema)
    assert _checked_input(spec, {HINT_HOST: "10.0.0.9"}, client_hint="192.168.1.20") == {HINT_HOST: "10.0.0.9"}


def test_a_custom_action_that_does_not_declare_the_hint_never_gets_the_client_hint():
    spec = OutputActionSpec(id="pair", label="Pair")
    assert _checked_input(spec, {}, client_hint="192.168.1.20") == {}


def test_the_hint_source_is_logged_at_debug_and_nothing_else(caplog):
    spec = OutputActionSpec(id="discover", label="Scan")
    with caplog.at_level(logging.DEBUG, logger="src.outputs.actions"):
        _checked_input(spec, {}, client_hint="192.168.1.20")
        _checked_input(spec, {HINT_HOST: "10.0.0.9"}, client_hint="192.168.1.20")
        _checked_input(spec, {}, client_hint=None)
    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG]
    assert messages == [
        "Action discover: network hint from client address",
        "Action discover: network hint from browser",
        "Action discover: network hint from none",
    ]
    assert not any("192.168.1.20" in m or "10.0.0.9" in m for m in messages)


# --- through the routes -----------------------------------------------------------------------

FIXTURE = Path(__file__).parent / "fixtures" / "plugins" / "recording_output"
PLUGIN_ID = "recording_output"


@pytest.fixture
def bundled(tmp_path):
    root = tmp_path / "plugins"
    target = root / PLUGIN_ID
    shutil.copytree(FIXTURE, target, ignore=shutil.ignore_patterns("__pycache__"))
    path = target / "manifest.json"
    manifest = json.loads(path.read_text("utf-8"))
    manifest["output"]["actions"] = [{"id": "discover", "label": "Find signs"}]
    path.write_text(json.dumps(manifest), "utf-8")
    loader = PluginLoader(plugins_dir=root, external_dirs=[])
    assert loader.load_plugin(PLUGIN_ID) is not None, loader.load_errors
    yield loader
    loader.unload_plugin(PLUGIN_ID)


def _draft_discover(peer: tuple[str, int], headers: dict[str, str], body_input: dict) -> list:
    from src.api_server import app

    plugin_class = sys.modules[f"plugins.{PLUGIN_ID}"].RecordingOutput
    seen: list = []

    def discover(cls, timeout, hint=None):
        seen.append(hint)
        return []

    with mock.patch.object(plugin_class, "discover", classmethod(discover)):
        resp = TestClient(app, client=peer).post(
            f"/outputs/{PLUGIN_ID}/actions/discover",
            json={"output_config": {"host": "192.0.2.50"}, "input": body_input},
            headers=headers,
        )
    assert resp.status_code == 200, resp.text
    return seen


def test_the_draft_discover_route_falls_back_to_the_client_behind_nginx(bundled, bridge_mode):
    """``http://fiestaboard.local:4420``: the page sends no hint; nginx names the client."""
    assert _draft_discover(("127.0.0.1", 40000), {"X-Real-IP": "192.168.1.20"}, {}) == ["192.168.1.20"]


def test_the_draft_discover_route_ignores_a_spoofed_header_from_a_non_loopback_peer(bundled, bridge_mode):
    assert _draft_discover(("203.0.113.9", 40000), {"X-Real-IP": "192.168.1.20"}, {}) == [None]


def test_the_draft_discover_route_prefers_the_browsers_hint(bundled, bridge_mode):
    seen = _draft_discover(("127.0.0.1", 40000), {"X-Real-IP": "192.168.1.20"}, {HINT_HOST: "10.0.0.9"})
    assert seen == ["10.0.0.9"]


def test_the_draft_discover_route_gives_no_hint_for_the_docker_host_itself(bundled, bridge_mode):
    assert _draft_discover(("127.0.0.1", 40000), {"X-Real-IP": "172.17.0.1"}, {}) == [None]


def test_the_saved_board_action_route_hands_the_client_hint_on(bridge_mode):
    from src.api_server import app

    with mock.patch("src.outputs.routes.run_saved_action", new=mock.AsyncMock()) as run:
        run.return_value = {"status": "ok", "message": "", "guidance": [], "fields": None, "geometry": None}
        resp = TestClient(app, client=("127.0.0.1", 40000)).post(
            "/boards/b1/actions/discover", json={"input": {}}, headers={"X-Real-IP": "192.168.1.20"}
        )
    assert resp.status_code == 200, resp.text
    assert run.await_args.kwargs["client_hint"] == "192.168.1.20"


def test_the_legacy_vestaboard_scan_is_handed_the_client_hint(bridge_mode):
    from src.api_server import app

    with mock.patch("plugins.vestaboard.discovery.discover", return_value=[]) as scan:
        resp = TestClient(app, client=("127.0.0.1", 40000)).post(
            "/config/board/scan", json={"timeout": 2}, headers={"X-Real-IP": "192.168.1.20"}
        )
    assert resp.status_code == 200, resp.text
    scan.assert_called_once_with(2.0, hint="192.168.1.20")
