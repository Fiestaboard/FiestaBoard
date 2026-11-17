"""Where a phone can reach this hub, for the "Connect a phone" QR (H18).

The QR tells the phone which address to sign in at. The browser's own origin
is the natural answer, unless that browser runs on the hub itself
(``http://localhost:4420``): scanned, a loopback address means the phone.
So the offer lists every address a phone on the network might reach, best
first, and never a loopback one:

1. ``browser``: the browser's origin, when it is not loopback;
2. ``configured``: the operator's ``FIESTABOARD_EXTERNAL_URL``;
3. ``mdns``: the ``<hostname>.local`` name this hub advertises (the same name
   as H13's TXT ``host=``), while the advertisement is up;
4. ``lan``: this host's LAN IPv4, on the browser's port. Inside a bridged
   container that address is the container's own, which no phone can
   reach, so it is left out there whatever its range (Docker's 172.16.0.0/12,
   Podman's 10.88.0.0/16, or a user-defined network) (H18b). A container is
   told by Docker's ``/.dockerenv`` or Podman's ``/run/.containerenv``; a
   bridged one from ``network_mode: host`` by the host's ``docker0`` /
   ``podman0`` interface: visible in a host-network container, absent in a
   bridged one. (A host with that default bridge removed reads as bridged;
   set ``FIESTABOARD_EXTERNAL_URL`` there.)
"""

from __future__ import annotations

import ipaddress
import logging
import os
from pathlib import Path
from typing import Any

from .origins import normalized_origin

Origin = tuple[str, str, int]
#: Docker's and Podman's in-container marker files.
CONTAINER_MARKERS = (Path("/.dockerenv"), Path("/run/.containerenv"))
#: The hosts' default-bridge interfaces (seen inside a container only with host networking).
HOST_BRIDGES = (Path("/sys/class/net/docker0"), Path("/sys/class/net/podman0"))

logger = logging.getLogger(__name__)
#: The malformed FIESTABOARD_EXTERNAL_URL values already logged (say it once, not per offer).
_warned: set[str] = set()


def mdns_service() -> Any:
    from src.system.mdns import get_mdns_service

    return get_mdns_service()


def lan_ipv4() -> str:
    from src.system.mdns import local_ipv4

    return local_ipv4()


def in_bridge_network() -> bool:
    """Whether this runs in a bridged container (Docker or Podman), where the LAN address seen is the container's."""
    return any(m.exists() for m in CONTAINER_MARKERS) and not any(b.exists() for b in HOST_BRIDGES)


def is_loopback(host: str) -> bool:
    """Whether *host* means "this machine" to whoever reads it (a scanning phone included)."""
    host = host.strip("[]").rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_unspecified


def origin_url(origin: Origin) -> str:
    """``scheme://host[:port]`` without a default port."""
    scheme, host, port = origin
    if ":" in host:
        host = f"[{host}]"
    default = 443 if scheme == "https" else 80
    return f"{scheme}://{host}" + ("" if port == default else f":{port}")


def _lan(origin: Origin | None) -> Origin | None:
    ip = lan_ipv4()
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if address.is_loopback or address.is_unspecified or in_bridge_network():
        return None
    scheme, port = (origin[0], origin[2]) if origin else ("http", int(os.environ.get("MDNS_PORT", "4420")))
    return scheme, ip, port


def _configured() -> Origin | None:
    """``FIESTABOARD_EXTERNAL_URL`` as an origin; a malformed one is logged (once) and skipped."""
    raw = os.environ.get("FIESTABOARD_EXTERNAL_URL", "").strip()
    if not raw:
        return None
    origin = normalized_origin(raw)
    if origin is None and raw not in _warned:
        _warned.add(raw)
        logger.warning(
            "FIESTABOARD_EXTERNAL_URL=%r is not used for the phone pairing QR: it must be "
            "scheme://host[:port] with no path (a sub-path reverse proxy is not supported here)",
            raw,
        )
    return origin


def hub_addresses(origin: Origin | None) -> list[dict[str, str]]:
    """``[{url, kind}]``: where a phone may reach this hub, best first, each once, never loopback."""
    service = mdns_service()
    candidates: list[tuple[Origin | None, str]] = [
        (origin, "browser"),
        (_configured(), "configured"),
        (normalized_origin(service.local_url) if service.is_running else None, "mdns"),
        (_lan(origin), "lan"),
    ]
    addresses: list[dict[str, str]] = []
    for candidate, kind in candidates:
        if candidate is None or is_loopback(candidate[1]):
            continue
        url = origin_url(candidate)
        if all(address["url"] != url for address in addresses):
            addresses.append({"url": url, "kind": kind})
    return addresses


def pick(addresses: list[dict[str, str]], wanted: str | None) -> str | None:
    """The address the QR should carry: *wanted* when it is one of *addresses*
    (compared after normalising), else the first; ``None`` if *wanted* is not
    listed or nothing is."""
    if wanted is None:
        return addresses[0]["url"] if addresses else None
    normalized = normalized_origin(wanted)
    url = origin_url(normalized) if normalized else None
    return url if any(address["url"] == url for address in addresses) else None
