"""Shared request-address policy for browser, REST and MCP traffic."""

from __future__ import annotations

import ipaddress
import os
import re
import socket
from urllib.parse import urlsplit

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

_FIND_ORIGIN = "https://fiestaboard.app"
_HOST_LABELS = re.compile(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\Z", re.ASCII)


def _origin(value: str) -> tuple[str, str, int] | None:
    """Parse an exact HTTP origin, never a URL containing credentials or a path."""
    if not value or any(c.isspace() or ord(c) < 32 for c in value):
        return None
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        if (
            parsed.scheme not in {"http", "https"}
            or not host
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or "\\" in value
            or "?" in value
            or "#" in value
            or parsed.netloc.endswith(":")
            or "%" in host
        ):
            return None
        port = parsed.port
        if port == 0:
            return None
        host = host.lower()
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if not _HOST_LABELS.fullmatch(host) or ".." in host:
                return None
        return parsed.scheme, host, port if port is not None else (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return None


def configured_origins() -> list[str]:
    """Only exact, valid origins grant cross-origin browser access."""
    return [
        value.strip().rstrip("/")
        for value in os.environ.get("FIESTABOARD_CORS_ORIGINS", "").split(",")
        if _origin(value.strip()) is not None
    ]


def _trusted_origins() -> set[tuple[str, str, int]]:
    values = [*configured_origins(), os.environ.get("FIESTABOARD_EXTERNAL_URL", "")]
    return {origin for value in values if (origin := _origin(value)) is not None}


def _trusted_host(host: str, origins: set[tuple[str, str, int]]) -> bool:
    # IP literals do not depend on DNS. Never resolve an untrusted hostname
    # to decide whether to trust it: that would accept a changed DNS answer.
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    mdns = os.environ.get("MDNS_HOSTNAME", "fiestaboard").strip().lower().removesuffix(".local")
    known = {
        "localhost",
        "fiestaboard",
        "fiestaboard.local",
        "fiestapi",
        "fiestapi.local",
        socket.gethostname().lower(),
    }
    known.update({mdns, f"{mdns}.local"})
    known.update(origin[1] for origin in origins)
    for value in os.environ.get("FIESTABOARD_ALLOWED_HOSTS", "").split(","):
        parsed = _origin(f"http://{value.strip()}")
        if parsed is not None:
            known.add(parsed[1])
    return host in known


class RequestBoundaryMiddleware:
    """Reject untrusted addresses before any API handler or mounted transport."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        hosts = [v.decode("latin-1") for k, v in scope["headers"] if k.lower() == b"host"]
        origins = [v.decode("latin-1") for k, v in scope["headers"] if k.lower() == b"origin"]
        scheme = {"ws": "http", "wss": "https"}.get(scope["scheme"], scope["scheme"])
        address = _origin(f"{scheme}://{hosts[0]}") if len(hosts) == 1 and "/" not in hosts[0] else None
        allowed = _trusted_origins()
        status = 0
        if address is None or not _trusted_host(address[1], allowed):
            status = 400
        elif origins:
            origin = _origin(origins[0]) if len(origins) == 1 else None
            discovery = (
                scope["type"] == "http"
                and scope["method"] == "GET"
                and scope["path"] in {"/discover", "/api/discover"}
                and origins == [_FIND_ORIGIN]
            )
            if not discovery and (origin is None or origin not in allowed | {address}):
                status = 403
        elif any(k.lower() == b"sec-fetch-site" and v == b"cross-site" for k, v in scope["headers"]):
            # The OAuth relay returns by cross-site navigation. Its handler
            # authenticates the signed, single-use state; Host is still checked.
            callback = (
                scope["type"] == "http"
                and scope["method"] == "GET"
                and scope["path"] in {"/oauth/callback", "/api/oauth/callback"}
            )
            if not callback:
                status = 403
        if status:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            else:
                response = JSONResponse({"detail": "Request address is not allowed."}, status_code=status)
                await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
