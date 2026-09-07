"""URL guard for the endpoints that fetch a user-supplied address.

Moved verbatim from ``src/api_server.py`` (Phase 2, Task 8) together with its
one caller, ``POST /generic-data/test-fetch``. The code is unchanged on
purpose: CodeQL's ``py/full-ssrf`` query recognises this exact shape — the
scheme allowlist, the ``ipaddress`` literal check, the ``getaddrinfo``
resolution, and the ``is_global`` sanitizer in the route itself — and
"tidying" any of it silently removes a sanitizer the security gate depends on.
"""

from __future__ import annotations

import os

from fastapi import HTTPException


def _validate_request_url(
    url: str,
    *,
    allow_http: bool = True,
    allow_https: bool = True,
) -> None:
    """Validate a user-supplied URL before using it in an HTTP request.

    Blocks credentialed URLs (``user:pass@host``), unsupported schemes and
    non-public destinations (loopback/private/link-local/etc.) to reduce SSRF
    risk. Raises :class:`HTTPException` (status 400) when the URL is rejected.
    """
    import ipaddress
    import socket
    from urllib.parse import urlparse

    if not isinstance(url, str) or not url:
        raise HTTPException(status_code=400, detail="URL is required")
    try:
        parsed = urlparse(url)
    except ValueError:
        raise HTTPException(status_code=400, detail="URL could not be parsed") from None
    allowed = []
    if allow_http:
        allowed.append("http")
    if allow_https:
        allowed.append("https")
    if parsed.scheme not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"URL scheme must be one of: {', '.join(allowed)}",
        )
    if not parsed.hostname:
        raise HTTPException(status_code=400, detail="URL is missing a host")
    if parsed.username is not None or parsed.password is not None:
        raise HTTPException(status_code=400, detail="URL must not contain credentials")
    # Block requests targeting private/loopback/link-local addresses to
    # prevent SSRF against internal services.
    _h = parsed.hostname.lower().rstrip(".")
    if _h in {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}:
        raise HTTPException(
            status_code=400,
            detail="URL must not target internal network resources",
        )
    try:
        _addr = ipaddress.ip_address(_h)
        if _addr.is_private or _addr.is_loopback or _addr.is_link_local or _addr.is_reserved or _addr.is_multicast:
            raise HTTPException(
                status_code=400,
                detail="URL must not target internal network resources",
            )
    except ValueError:
        pass  # Not an IP literal; hostname-based domains are permitted

    host = parsed.hostname.strip().lower()
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise HTTPException(status_code=400, detail="URL host is not allowed")

    def _is_non_public_ip(ip_str: str) -> bool:
        ip_obj = ipaddress.ip_address(ip_str)
        return (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_multicast
            or ip_obj.is_reserved
            or ip_obj.is_unspecified
        )

    try:
        if _is_non_public_ip(host):
            raise HTTPException(status_code=400, detail="URL host resolves to a non-public IP")
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
        except socket.gaierror:
            raise HTTPException(status_code=400, detail="URL host could not be resolved") from None

        for info in infos:
            resolved_ip = info[4][0]
            if _is_non_public_ip(resolved_ip):
                raise HTTPException(status_code=400, detail="URL host resolves to a non-public IP") from None


def _get_generic_data_allowed_hosts() -> list[str]:
    """Return normalized allowlisted hosts for generic-data test fetch.

    Reads comma-separated hostnames from ``GENERIC_DATA_ALLOWED_HOSTS``.
    Empty value means no hosts are allowed.
    """
    raw = os.getenv("GENERIC_DATA_ALLOWED_HOSTS", "")
    hosts = []
    for part in raw.split(","):
        h = part.strip().lower().rstrip(".")
        if h:
            hosts.append(h)
    return hosts


def _is_host_allowed(host: str, allowed_hosts: list[str]) -> bool:
    """Check whether host is exactly allowed or a subdomain of an allowed host."""
    h = (host or "").strip().lower().rstrip(".")
    for allowed in allowed_hosts:
        if h == allowed or h.endswith("." + allowed):
            return True
    return False
