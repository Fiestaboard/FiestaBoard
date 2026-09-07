"""Deprecation headers on the plugin-specific platform routes (issue #1915).

Eleven routes in ``src/api_server.py`` each serve a single plugin, which
CLAUDE.md forbids for ``src/`` code. They are being retired in favour of a
per-plugin ``options`` provider, but two of them (muni and stocks) are
published as public "API Endpoints" in sibling plugin SETUP guides, so they
are *deprecated with a sunset date* rather than deleted outright.

Every one of the eleven handlers must therefore advertise the pending removal
with ``Deprecation: true`` and an RFC 8594 ``Sunset`` header. Each handler sets
those headers as its first statement (before any network I/O), so these tests
call the handlers directly with a mock response and a patched data boundary,
and assert on the headers regardless of whether the downstream call succeeds.

Reverting the ``_mark_plugin_route_deprecated(response)`` call in any handler
makes that handler's case fail (``response.headers`` stays empty).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from unittest.mock import Mock, patch

import pytest

import src.api_server as api
from src.api_server import _PLUGIN_ROUTE_SUNSET


def _mock_response() -> Mock:
    resp = Mock()
    resp.headers = {}
    return resp


def _swallow(coro) -> None:
    """Run a handler coroutine, discarding any downstream failure.

    The deprecation headers are set before any I/O, so the header assertions
    hold whether the handler returns normally or raises after that point.
    """
    try:
        asyncio.run(coro)
    except Exception:
        pass


def _no_network():
    """Force any handler that reaches ``asyncio.to_thread`` to fail fast."""
    return patch("asyncio.to_thread", side_effect=RuntimeError("no network in test"))


# Each invoke() applies whatever patches keep the handler off the network, then
# runs it against the supplied mock response.
def _invoke_baywheels_stations(resp: Mock) -> None:
    with _no_network():
        _swallow(api.list_all_baywheels_stations(resp))


def _invoke_baywheels_nearby(resp: Mock) -> None:
    with _no_network():
        _swallow(api.find_nearby_baywheels_stations(resp, lat=40.7128, lng=-74.0060))


def _invoke_baywheels_search(resp: Mock) -> None:
    with _no_network():
        _swallow(api.search_baywheels_stations_by_address(resp, address="123 Main St, Anytown"))


def _invoke_muni_stops(resp: Mock) -> None:
    api._muni_stops_cache = None
    with patch("src.config.Config.MUNI_API_KEY", ""):
        _swallow(api.list_all_muni_stops(resp))


def _invoke_muni_nearby(resp: Mock) -> None:
    api._muni_stops_cache = None
    with patch("src.config.Config.MUNI_API_KEY", ""):
        _swallow(api.find_nearby_muni_stops(resp, lat=40.7128, lng=-74.0060))


def _invoke_muni_search(resp: Mock) -> None:
    with _no_network():
        _swallow(api.search_muni_stops_by_address(resp, address="123 Main St, Anytown"))


def _invoke_transit_cache_status(resp: Mock) -> None:
    _swallow(api.get_transit_cache_status(resp))


def _invoke_stocks_search(resp: Mock) -> None:
    with patch("src.utils.stocks.StocksSource.search_symbols", return_value=[]):
        _swallow(api.search_stock_symbols(resp, query="GOOG"))


def _invoke_stocks_validate(resp: Mock) -> None:
    with patch("src.utils.stocks.StocksSource.validate_symbol", return_value={"valid": False, "symbol": "GOOG"}):
        _swallow(api.validate_stock_symbol({"symbol": "GOOG"}, resp))


def _invoke_traffic_geocode(resp: Mock) -> None:
    with _no_network():
        _swallow(api.geocode_address({"address": "123 Main St, Anytown"}, resp))


def _invoke_traffic_validate(resp: Mock) -> None:
    with patch("src.config.Config.GOOGLE_ROUTES_API_KEY", "", create=True):
        _swallow(api.validate_traffic_route({"origin": "a", "destination": "b"}, resp))


DEPRECATED_HANDLERS = [
    ("GET /baywheels/stations", _invoke_baywheels_stations),
    ("GET /baywheels/stations/nearby", _invoke_baywheels_nearby),
    ("GET /baywheels/stations/search", _invoke_baywheels_search),
    ("GET /muni/stops", _invoke_muni_stops),
    ("GET /muni/stops/nearby", _invoke_muni_nearby),
    ("GET /muni/stops/search", _invoke_muni_search),
    ("GET /transit/cache/status", _invoke_transit_cache_status),
    ("GET /stocks/search", _invoke_stocks_search),
    ("POST /stocks/validate", _invoke_stocks_validate),
    ("POST /traffic/routes/geocode", _invoke_traffic_geocode),
    ("POST /traffic/routes/validate", _invoke_traffic_validate),
]


@pytest.mark.parametrize("route, invoke", DEPRECATED_HANDLERS, ids=[r for r, _ in DEPRECATED_HANDLERS])
def test_route_advertises_deprecation(route: str, invoke) -> None:
    """Every plugin-specific platform route sets the Deprecation header."""
    resp = _mock_response()
    invoke(resp)
    assert resp.headers.get("Deprecation") == "true", f"{route} missing Deprecation header"


@pytest.mark.parametrize("route, invoke", DEPRECATED_HANDLERS, ids=[r for r, _ in DEPRECATED_HANDLERS])
def test_route_advertises_sunset(route: str, invoke) -> None:
    """Every plugin-specific platform route sets the Sunset header."""
    resp = _mock_response()
    invoke(resp)
    assert resp.headers.get("Sunset") == _PLUGIN_ROUTE_SUNSET, f"{route} missing Sunset header"


def test_sunset_is_a_future_rfc8594_http_date() -> None:
    """The sunset constant parses as an HTTP-date and is in the future."""
    parsed = parsedate_to_datetime(_PLUGIN_ROUTE_SUNSET)
    assert parsed.tzinfo is not None, "Sunset must be an absolute (GMT) HTTP-date"
    assert parsed > datetime.now(timezone.utc), "Sunset date must be in the future"
