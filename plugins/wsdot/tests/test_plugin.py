"""Unit tests for the WSDOT plugin."""

import pytest
from unittest.mock import patch, Mock

import requests

from src.plugins.base import PluginResult


def _load_manifest():
    import json
    from pathlib import Path
    path = Path(__file__).parent.parent / "manifest.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _plugin():
    from plugins.wsdot import WsdotPlugin
    return WsdotPlugin(_load_manifest())


class TestWsdotPluginId:
    """Test plugin identification."""

    def test_plugin_id(self):
        plugin = _plugin()
        assert plugin.plugin_id == "wsdot"


class TestWsdotValidateConfig:
    """Test configuration validation."""

    def test_valid_config(self):
        plugin = _plugin()
        errors = plugin.validate_config({
            "api_access_code": "test-code",
            "routes": [{"route_id": 7}],
            "refresh_seconds": 120,
        })
        assert errors == []

    def test_missing_api_access_code(self):
        plugin = _plugin()
        with patch("plugins.wsdot.os.getenv", return_value=None):
            errors = plugin.validate_config({
                "routes": [{"route_id": 7}],
            })
        assert any("access code" in e.lower() for e in errors)

    def test_missing_routes(self):
        plugin = _plugin()
        errors = plugin.validate_config({
            "api_access_code": "test-code",
            "routes": [],
        })
        assert any("route" in e.lower() for e in errors)

    def test_refresh_seconds_too_low(self):
        plugin = _plugin()
        errors = plugin.validate_config({
            "api_access_code": "test-code",
            "routes": [{"route_id": 7}],
            "refresh_seconds": 30,
        })
        assert any("60" in e or "refresh" in e.lower() for e in errors)


class TestWsdotFetchData:
    """Test fetch_data with mocked API."""

    def test_fetch_data_no_access_code(self):
        plugin = _plugin()
        plugin.config = {}
        with patch.dict("os.environ", {}, clear=True):
            result = plugin.fetch_data()
        assert result.available is False
        assert "access code" in (result.error or "").lower()

    def test_fetch_data_no_routes(self):
        plugin = _plugin()
        plugin.config = {"api_access_code": "test-code", "routes": []}
        result = plugin.fetch_data()
        assert result.available is False
        assert "route" in (result.error or "").lower()

    @patch("plugins.wsdot.requests.get")
    def test_fetch_data_success(self, mock_get):
        def get_side_effect(url, params=None, **kwargs):
            if "scheduletoday" in url:
                return Mock(
                    status_code=200,
                    json=lambda: [
                        {
                            "DepartureTime": "08:00",
                            "VesselID": 1,
                            "VesselName": "Wenatchee",
                            "SpacesLeft": 45,
                        },
                        {
                            "DepartureTime": "09:30",
                            "VesselID": 2,
                            "Direction": "B",
                            "VesselName": "Tacoma",
                            "SpacesLeft": 12,
                        },
                    ],
                    raise_for_status=Mock(),
                )
            if "vesselbasics" in url:
                return Mock(
                    status_code=200,
                    json=lambda: [
                        {"VesselID": 1, "VesselName": "Wenatchee"},
                        {"VesselID": 2, "VesselName": "Tacoma"},
                    ],
                    raise_for_status=Mock(),
                )
            if "terminalsailingspace" in url or "terminalwaittimes" in url or "alerts" in url:
                return Mock(status_code=200, json=lambda: [], raise_for_status=Mock())
            return Mock(status_code=404, raise_for_status=Mock(side_effect=Exception("404")))

        mock_get.side_effect = get_side_effect

        plugin = _plugin()
        plugin.config = {"api_access_code": "test-code", "routes": [{"route_id": 7}]}
        result = plugin.fetch_data()

        assert result.available is True
        assert result.data is not None
        assert result.data.get("route_count") == 1
        assert "routes" in result.data
        assert len(result.data["routes"]) == 1
        route = result.data["routes"][0]
        assert "departures_ab" in route or "departures_ba" in route
        assert result.formatted_lines is not None
        assert len(result.formatted_lines) <= 6

    @patch("plugins.wsdot.requests.get")
    def test_fetch_data_api_error(self, mock_get):
        mock_get.side_effect = Exception("Network error")

        plugin = _plugin()
        plugin.config = {"api_access_code": "test-code", "routes": [{"route_id": 7}]}
        result = plugin.fetch_data()

        assert result.available is False
        assert result.error is not None

    @patch("plugins.wsdot.requests.get")
    def test_fetch_data_partial_success(self, mock_get):
        """When one route fails (404), others can still be returned."""
        def get_side_effect(url, params=None, **kwargs):
            if "scheduletoday/7" in url:
                return Mock(
                    status_code=200,
                    json=lambda: [{"DepartureTime": "10:00", "VesselID": 1, "VesselName": "Test"}],
                    raise_for_status=Mock(),
                )
            if "scheduletoday/99" in url:
                # 404: _get catches HTTPError and returns None, plugin adds "No data" route
                resp = Mock(status_code=404)
                resp.raise_for_status.side_effect = requests.exceptions.HTTPError("404")
                resp.json.return_value = {}
                return resp
            if "vesselbasics" in url:
                return Mock(status_code=200, json=lambda: [{"VesselID": 1, "VesselName": "Test"}], raise_for_status=Mock())
            if "terminalsailingspace" in url or "terminalwaittimes" in url or "alerts" in url:
                return Mock(status_code=200, json=lambda: [], raise_for_status=Mock())
            resp = Mock(status_code=404)
            resp.raise_for_status.side_effect = requests.exceptions.HTTPError("404")
            resp.json.return_value = {}
            return resp

        mock_get.side_effect = get_side_effect

        plugin = _plugin()
        plugin.config = {"api_access_code": "test-code", "routes": [{"route_id": 7}, {"route_id": 99}]}
        result = plugin.fetch_data()

        assert result.available is True
        assert result.data["route_count"] == 2
        routes = result.data["routes"]
        assert len(routes) == 2
        # First route has data, second has "No data"
        assert any(r.get("formatted") and r["formatted"] != "No data" for r in routes)


class TestWsdotDataVariables:
    """Test that returned data matches manifest variables."""

    @patch("plugins.wsdot.requests.get")
    def test_variables_match_manifest(self, mock_get):
        def get_side_effect(url, params=None, **kwargs):
            if "scheduletoday" in url:
                return Mock(
                    status_code=200,
                    json=lambda: [{"DepartureTime": "08:00", "VesselID": 1, "VesselName": "Wenatchee"}],
                    raise_for_status=Mock(),
                )
            if "vesselbasics" in url:
                return Mock(status_code=200, json=lambda: [{"VesselID": 1, "VesselName": "Wenatchee"}], raise_for_status=Mock())
            if "terminalsailingspace" in url or "terminalwaittimes" in url or "alerts" in url:
                return Mock(status_code=200, json=lambda: [], raise_for_status=Mock())
            return Mock(status_code=200, json=lambda: [], raise_for_status=Mock())

        mock_get.side_effect = get_side_effect

        plugin = _plugin()
        plugin.config = {"api_access_code": "x", "routes": [{"route_id": 7}]}
        result = plugin.fetch_data()
        assert result.available and result.data

        manifest = _load_manifest()
        simple = set(manifest.get("variables", {}).get("simple", []))
        for var in simple:
            assert var in result.data, f"Variable '{var}' declared in manifest but not in data"


class TestFormatRouteLine:
    """Test _format_route_line (route + time + spots, spots show '--' when missing)."""

    def test_formatted_includes_double_dash_when_no_spots(self):
        from plugins.wsdot import _format_route_line
        out = _format_route_line(route_id=9, scheduled_time="06:15", spots_remaining="", max_len=22)
        assert "--" in out
        assert "06:15" in out
        assert "Edm-King" in out or "Edm" in out

    def test_formatted_includes_spots_when_present(self):
        from plugins.wsdot import _format_route_line
        out = _format_route_line(route_id=1, scheduled_time="05:05", spots_remaining="59", max_len=22)
        assert "59" in out
        assert "05:05" in out
        assert "Sea-Bain" in out or "Sea" in out

    def test_formatted_truncates_spots_to_three_chars(self):
        from plugins.wsdot import _format_route_line
        out = _format_route_line(route_id=1, scheduled_time="05:05", spots_remaining="135", max_len=22)
        assert "135" in out


class TestParseTime:
    """Test _parse_time (.NET /Date(ms)/ and plain strings)."""

    def test_parse_time_net_date_format(self):
        from plugins.wsdot import _parse_time
        # 1770212100000 ms -> reasonable HH:MM in Pacific
        s = "/Date(1770212100000-0800)/"
        out = _parse_time(s)
        assert isinstance(out, str)
        assert len(out) <= 5
        assert ":" in out or out == ""

    def test_parse_time_plain_hhmm(self):
        from plugins.wsdot import _parse_time
        assert _parse_time("06:15") == "06:15"
        assert _parse_time("08:00") == "08:00"

    def test_parse_time_none_returns_empty(self):
        from plugins.wsdot import _parse_time
        assert _parse_time(None) == ""


class TestGetDriveUpSpace:
    """Test _get_drive_up_space and terminal fallback, vessel ID normalization."""

    def test_drive_up_space_vessel_id_string_matches_int(self):
        """Terminals API may return vesselId as string; schedule as int. Both should match."""
        plugin = _plugin()
        plugin._sailing_space = {
            8: {
                "TerminalID": 8,
                "DepartingSpaces": [
                    {
                        "Departure": "/Date(1738658100000-0800)/",
                        "VesselID": "5",
                        "SpaceForArrivalTerminals": [{"DriveUpSpaceCount": 42}],
                    },
                ],
            },
        }
        # Schedule passes vessel_id as int 5
        result = plugin._get_drive_up_space_for_terminal(
            terminal_id=8,
            departure_date_str="/Date(1738658100000-0800)/",
            vessel_id=5,
        )
        assert result == "42"

    def test_drive_up_space_fallback_to_other_terminal(self):
        """When primary terminal has no data, try route's other terminal."""
        plugin = _plugin()
        # Edmonds (8) has no entry; Kingston (12) has the sailing
        plugin._sailing_space = {
            12: {
                "TerminalID": 12,
                "DepartingSpaces": [
                    {
                        "Departure": "/Date(1738658100000-0800)/",
                        "VesselID": 10,
                        "SpaceForArrivalTerminals": [{"DriveUpSpaceCount": 99}],
                    },
                ],
            },
        }
        result = plugin._get_drive_up_space(
            terminal_id=8,
            departure_date_str="/Date(1738658100000-0800)/",
            vessel_id=10,
            route_id=9,
        )
        assert result == "99"

    def test_drive_up_space_extract_count_from_item_when_no_array(self):
        """DriveUpSpaceCount can be on the departure item when not in SpaceForArrivalTerminals."""
        plugin = _plugin()
        plugin._sailing_space = {
            7: {
                "TerminalID": 7,
                "DepartingSpaces": [
                    {
                        "Departure": "/Date(1738658100000-0800)/",
                        "VesselID": 1,
                        "DriveUpSpaceCount": 17,
                    },
                ],
            },
        }
        result = plugin._get_drive_up_space_for_terminal(
            terminal_id=7,
            departure_date_str="/Date(1738658100000-0800)/",
            vessel_id=1,
        )
        assert result == "17"


class TestScheduleTerminalCombosAndSpots:
    """Test schedule with TerminalCombos and spots from terminalsailingspace."""

    @patch("plugins.wsdot.requests.get")
    def test_formatted_line_has_dash_when_no_spots_for_route(self, mock_get):
        """When terminalsailingspace has no data for a route, formatted line still shows '--' for spots."""
        def get_side_effect(url, params=None, **kwargs):
            if "scheduletoday" in url:
                return Mock(
                    status_code=200,
                    json=lambda: {
                        "TerminalCombos": [
                            {
                                "DepartingTerminalID": 8,
                                "Times": [
                                    {
                                        "DepartureTime": "/Date(1738658100000-0800)/",
                                        "VesselID": 10,
                                        "VesselName": "Test Vessel",
                                    },
                                ],
                            },
                        ],
                    },
                    raise_for_status=Mock(),
                )
            if "vesselbasics" in url:
                return Mock(
                    status_code=200,
                    json=lambda: [{"VesselID": 10, "VesselName": "Test Vessel"}],
                    raise_for_status=Mock(),
                )
            if "terminalsailingspace" in url or "terminalwaittimes" in url or "alerts" in url:
                return Mock(status_code=200, json=lambda: [], raise_for_status=Mock())
            return Mock(status_code=404, raise_for_status=Mock(side_effect=Exception("404")))

        mock_get.side_effect = get_side_effect
        plugin = _plugin()
        plugin.config = {"api_access_code": "x", "routes": [{"route_id": 9}]}
        result = plugin.fetch_data()
        assert result.available is True
        assert result.data["route_count"] == 1
        route = result.data["routes"][0]
        assert "formatted" in route
        assert "--" in route["formatted"]


class TestWsdotCleanup:
    """Test cleanup."""

    def test_cleanup_clears_cache(self):
        plugin = _plugin()
        plugin._cache = {"routes": []}
        plugin._vessel_names = {1: "X"}
        plugin.cleanup()
        assert plugin._cache is None
        assert plugin._vessel_names == {}
