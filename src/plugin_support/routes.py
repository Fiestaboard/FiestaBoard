"""FastAPI router for the two plugin-specific platform routes that are alive.

``GET /home-assistant/entities`` backs
``web/src/components/home-assistant-entity-picker.tsx``;
``POST /generic-data/test-fetch`` backs the "Test & Preview" button in
``web/src/components/plugin-settings/json-path-mapper-field.tsx``. Those two
consumers are why these are converted rather than deprecated — see
``src/plugin_support/__init__.py`` for the audit of all thirteen.

Phase 2, Task 8. Converted to ``docs/internal/reference/API_CONVENTIONS.md``:
a declared ``response_model`` on both, ``request: dict`` replaced by a
Pydantic model on the test fetch, and the failure codes declared in
``responses=``. ``tests/conventions_manifest.json`` lists ``plugin-support``.

The SSRF handling in ``generic_data_test_fetch`` moved **verbatim**, including
the parts that read as redundant (the ``_validate_request_url`` call, then the
allowlist regex, then the ``ipaddress`` ``is_global`` gate, then the
``urlunsplit`` rebuild). Those steps are what CodeQL's ``py/full-ssrf`` query
recognises as sanitizers; simplifying them would remove a security gate rather
than a duplication.
"""

from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urlparse

import requests
from fastapi import APIRouter, HTTPException

from src.api_errors import errors
from src.config_manager import get_config_manager

from .models import (
    GenericDataTestFetchRequest,
    GenericDataTestFetchResponse,
    HomeAssistantEntitiesResponse,
    HomeAssistantEntity,
)
from .url_guard import _get_generic_data_allowed_hosts, _is_host_allowed, _validate_request_url

logger = logging.getLogger(__name__)

router = APIRouter(tags=["plugin-support"])


@router.get(
    "/home-assistant/entities",
    response_model=HomeAssistantEntitiesResponse,
    responses=errors(503),
)
async def get_home_assistant_entities():
    """
    Get all available entities from Home Assistant.

    Returns list of entities with their current state and all attributes.
    Used by the UI to populate entity picker dropdowns.
    """
    from src.utils.home_assistant import get_home_assistant_source

    ha_source = get_home_assistant_source()
    if not ha_source:
        raise HTTPException(status_code=503, detail="Home Assistant not configured")

    try:
        # Call Home Assistant /api/states to get ALL entities
        response = await asyncio.to_thread(
            requests.get,
            f"{ha_source.base_url}/api/states",
            headers=ha_source.headers,
            timeout=ha_source.timeout,
        )
        response.raise_for_status()
        entities = response.json()

        # Transform to simpler format for UI (HA may omit or null attributes)
        result_entities = []
        for e in entities:
            attrs = e.get("attributes") or {}
            result_entities.append(
                HomeAssistantEntity(
                    entity_id=e["entity_id"],
                    state=e["state"],
                    attributes=attrs,
                    friendly_name=attrs.get("friendly_name", e["entity_id"]),
                )
            )
        return HomeAssistantEntitiesResponse(entities=result_entities)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to fetch entities: {str(e)}") from e


@router.post(
    "/generic-data/test-fetch",
    response_model=GenericDataTestFetchResponse,
    responses=errors(400, 500, 502, 504),
)
async def generic_data_test_fetch(request: GenericDataTestFetchRequest):
    """Fetch a URL and return the parsed response structure for mapping preview.

    Reuses the same parsing logic as the generic_data plugin so the preview
    matches real behaviour.  Response body is capped at 1 MB.
    """
    import defusedxml.ElementTree as DefusedET
    import requests as req

    from src.plugins.config_interpolation import get_builtin_variables, interpolate_string

    try:
        _tz = get_config_manager().get_general().get("timezone") or "America/Los_Angeles"
        _interp_vars = get_builtin_variables(timezone=_tz)
    except Exception:
        _interp_vars = get_builtin_variables()

    url = interpolate_string((request.url or "").strip(), _interp_vars)
    fmt = request.format
    method = request.method
    headers_list = request.headers
    body = request.body

    # Validate the URL: scheme must be http(s) and credentials are not allowed
    # (defence against SSRF/credential leaks).
    _SSRF_BLOCKED_DETAILS = {
        "URL must not target internal network resources",
        "URL host is not allowed",
        "URL host resolves to a non-public IP",
    }
    try:
        _validate_request_url(url)
    except HTTPException as _url_exc:
        if _url_exc.detail in _SSRF_BLOCKED_DETAILS:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Test & Preview can't reach local or private network addresses "
                    f"({urlparse(url).hostname}). This restriction only applies to the "
                    "preview feature — your plugin will still fetch this URL normally "
                    "when your page runs."
                ),
            ) from _url_exc
        raise
    # Re-derive url from a strict allowlist regex so the downstream HTTP call is not
    # tracked as tainted by static-analysis tools (py/full-ssrf).
    _safe_url_m = re.fullmatch(
        r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+",
        url,
    )
    if not _safe_url_m:
        raise HTTPException(status_code=400, detail="URL contains unexpected characters")
    url = _safe_url_m.group(0)

    # Resolve the URL host and confirm it is a public/global IP address.
    # CodeQL's ``py/full-ssrf`` IpAddressSanitizer recognises an
    # ``ipaddress`` object gated by a positive ``is_global`` check.
    import ipaddress as _ipaddress_mod
    import socket as _socket_mod

    _parsed_url = urlparse(url)
    _host_for_check = (_parsed_url.hostname or "").strip()
    try:
        _resolved_ip = _ipaddress_mod.ip_address(_host_for_check)
    except ValueError:
        try:
            _addrinfo = _socket_mod.getaddrinfo(
                _host_for_check,
                _parsed_url.port or (443 if _parsed_url.scheme == "https" else 80),
            )
        except _socket_mod.gaierror:
            raise HTTPException(status_code=400, detail="URL host could not be resolved") from None
        _resolved_ips = [info[4][0] for info in _addrinfo if info and len(info) >= 5 and info[4]]
        if not _resolved_ips:
            raise HTTPException(status_code=400, detail="URL host did not resolve") from None
        _resolved_ip = _ipaddress_mod.ip_address(_resolved_ips[0])
    # Positive ``is_global`` check — the CodeQL-recognised IpAddressSanitizer.
    if not _resolved_ip.is_global:
        raise HTTPException(status_code=400, detail="URL host resolves to a non-public IP")

    # After the IP barrier passes, rebuild ``url`` via ``urlunsplit`` from
    # the parsed components.  This routes the final URL string through
    # ``urllib.parse``'s structural reconstruction, which CodeQL's
    # ``py/full-ssrf`` query treats as a flow-breaking transformation
    # because the output is composed from individually-validated parts
    # (scheme is one of {"http","https"}; host already passed the
    # IpAddressSanitizer above).
    from urllib.parse import urlunsplit as _urlunsplit

    _safe_scheme = "https" if _parsed_url.scheme == "https" else "http"
    _safe_netloc = _host_for_check
    if _parsed_url.port:
        _safe_netloc = f"{_safe_netloc}:{int(_parsed_url.port)}"
    url = _urlunsplit((_safe_scheme, _safe_netloc, _parsed_url.path or "", _parsed_url.query or "", ""))

    host = _host_for_check
    allowed_hosts = _get_generic_data_allowed_hosts()
    # When GENERIC_DATA_ALLOWED_HOSTS is set, enforce the allowlist.
    # When it is unset, _validate_request_url above already blocks SSRF
    # (private IPs, loopback, .local) so we allow any public host.
    if allowed_hosts and not _is_host_allowed(host, allowed_hosts):
        raise HTTPException(
            status_code=400,
            detail="URL host is not in the allowlist",
        )

    headers: dict = {
        "Accept": "application/json" if fmt == "json" else "application/xml",
    }
    for h in headers_list:
        n = (h.name or "").strip()
        v = (h.value or "").strip()
        if n and v:
            headers[n] = interpolate_string(v, _interp_vars)

    try:
        kwargs: dict = {"headers": headers, "timeout": 15, "allow_redirects": False}
        if method == "POST" and body:
            kwargs["data"] = interpolate_string(body, _interp_vars) if isinstance(body, str) else body

        resp = req.request(method, url, **kwargs)
        resp.raise_for_status()

        if len(resp.content) > 1_048_576:
            raise HTTPException(status_code=400, detail="Response too large (exceeds 1 MB)")

        if fmt == "xml":
            from plugins.generic_data import _xml_to_dict

            # ``defusedxml`` disables external entity expansion, DTDs and
            # entity bombs by default, mitigating XXE attacks.
            root = DefusedET.fromstring(resp.text)
            parsed = _xml_to_dict(root)
        else:
            parsed = resp.json()

        return GenericDataTestFetchResponse(ok=True, data=parsed)
    except HTTPException:
        raise
    except req.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Request timed out") from None
    except req.exceptions.ConnectionError:
        raise HTTPException(status_code=502, detail="Connection error — check the URL") from None
    except req.exceptions.HTTPError:
        # Don't echo the upstream exception (URL/headers/status) back to the
        # caller — generic message is enough for a "test fetch" feature.
        raise HTTPException(status_code=502, detail="HTTP error from remote service") from None
    except Exception:
        logger.exception("generic-data test-fetch failed")
        raise HTTPException(status_code=500, detail="Failed to fetch data") from None


# =============================================================================
# Backup & Restore — export and import all user data as a single JSON file
# =============================================================================
