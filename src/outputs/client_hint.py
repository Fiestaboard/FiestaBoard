"""The network hint core derives from the requesting browser's address.

A scan needs the user's LAN (:data:`~src.outputs.hooks.HINT_HOST`): in Docker
bridge mode, the default, the container's own address (``172.x``) names a
container network. The web UI sends the address the page was opened at, but
only when that is a private IPv4 literal — at ``http://fiestaboard.local:4420``
it sends nothing. Then core falls back to the address the request came from,
when that says something about the LAN (:func:`client_lan_hint`).

**Whose address.** nginx runs in the same container and proxies ``/api/`` to
uvicorn on ``127.0.0.1:8000``, setting ``X-Real-IP`` (and appending to
``X-Forwarded-For``) from its ``$remote_addr``. Uvicorn's proxy-headers
support (on by default, trusting ``127.0.0.1``) already rewrites
``request.client`` from ``X-Forwarded-For``'s last untrusted hop, so a peer
that is not loopback is taken as is. A loopback peer means uvicorn left it
alone (proxy headers off, or ``::1``); then — and only then — the in-container
nginx's ``X-Real-IP`` (else ``X-Forwarded-For``'s last hop) names the client.
A header from any other peer is ignored, so it cannot be spoofed.

**Which addresses are useless.** Anything :func:`~src.outputs.hooks.lan_hint`
refuses (loopback, public, IPv6 — an IPv4-mapped ``::ffff:a.b.c.d`` is
unwrapped first); an address on one of this container's own networks (the
Docker bridge gateway ``172.17.0.1`` is how a browser on the Docker host
itself arrives; under ``network_mode: host`` it is the LAN the output already
searches); the Home Assistant Supervisor's network (``172.30.32.0/23``) and
any request carrying ``X-Ingress-Path``, which come through HA ingress; and,
under Docker Desktop, its VM network (``192.168.65.0/24``), to which it NATs
every published-port connection. A refused address means no hint: the scan
runs as it did before.
"""

from __future__ import annotations

import ipaddress
import platform
from pathlib import Path
from typing import Any

from .hooks import lan_hint

#: Where a scan's network hint came from, as logged (never the address).
HINT_SOURCE_BROWSER = "browser"
HINT_SOURCE_CLIENT = "client address"
HINT_SOURCE_NONE = "none"

#: The Home Assistant Supervisor's network: an add-on reached through
#: ingress sees the Supervisor's proxy (``172.30.32.2``), not the browser.
HA_SUPERVISOR_NETWORK = ipaddress.IPv4Network("172.30.32.0/23")

#: Docker Desktop's VM network: it NATs every connection to a published port
#: to ``192.168.65.1``, whatever the browser's address.
DOCKER_DESKTOP_NETWORK = ipaddress.IPv4Network("192.168.65.0/24")

_ROUTE_TABLE = Path("/proc/net/route")
_RTF_GATEWAY = 0x2


def _hex_ipv4(value: str) -> ipaddress.IPv4Address:
    # /proc/net/route prints addresses as host-order (little-endian) hex.
    return ipaddress.IPv4Address(int(value, 16).to_bytes(4, "little"))


def parse_route_table(text: str) -> tuple[ipaddress.IPv4Network, ...]:
    """The directly connected networks in a ``/proc/net/route`` listing:
    not the default route, not a route via a gateway."""
    networks: list[ipaddress.IPv4Network] = []
    for line in text.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 8:
            continue
        try:
            destination, flags, mask = _hex_ipv4(fields[1]), int(fields[3], 16), _hex_ipv4(fields[7])
            network = ipaddress.IPv4Network(f"{destination}/{mask}")
        except ValueError:
            continue
        if network.prefixlen == 0 or flags & _RTF_GATEWAY or network in networks:
            continue
        networks.append(network)
    return tuple(networks)


def interface_networks() -> tuple[ipaddress.IPv4Network, ...]:
    """The networks this container (or host) is directly on; none off Linux."""
    try:
        return parse_route_table(_ROUTE_TABLE.read_text(encoding="ascii"))
    except OSError:
        return ()


def _docker_desktop() -> bool:
    """Whether this is Docker Desktop's VM (its kernel is LinuxKit)."""
    return "linuxkit" in platform.release().lower()


def _is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def client_address(request: Any) -> str | None:
    """The address *request* came from, as the in-container nginx saw it."""
    client = getattr(request, "client", None)
    peer = getattr(client, "host", None)
    if not peer:
        return None
    if not _is_loopback(peer):
        return peer
    headers = request.headers
    real_ip = (headers.get("x-real-ip") or "").strip()
    if real_ip:
        return real_ip
    forwarded = [hop.strip() for hop in (headers.get("x-forwarded-for") or "").split(",") if hop.strip()]
    return forwarded[-1] if forwarded else peer


def _unwrapped(address: str) -> str:
    try:
        parsed = ipaddress.ip_address(address.strip())
    except ValueError:
        return address
    mapped = getattr(parsed, "ipv4_mapped", None)
    return str(mapped) if mapped is not None else str(parsed)


def client_lan_hint(request: Any) -> str | None:
    """The requesting browser's address as a network hint, or ``None`` when
    it says nothing useful about the user's LAN (see the module docstring)."""
    if request is None or request.headers.get("x-ingress-path") is not None:
        return None
    address = client_address(request)
    hint = lan_hint(_unwrapped(address)) if address else None
    if hint is None:
        return None
    ip = ipaddress.IPv4Address(hint)
    if ip in HA_SUPERVISOR_NETWORK:
        return None
    if _docker_desktop() and ip in DOCKER_DESKTOP_NETWORK:
        return None
    if any(ip in network for network in interface_networks()):
        return None
    return hint
