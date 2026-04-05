"""Tests for the generic_data plugin.

Coverage requirement: 80% minimum
"""

import json
import re
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock

import pytest

from plugins.generic_data import (
    GenericDataPlugin,
    _resolve_path,
    _xml_to_dict,
    _build_feeds,
    MAX_RESPONSE_BYTES,
    MAX_FEEDS,
)
from src.plugins.base import PluginResult


# ---------------------------------------------------------------------------
# _resolve_path unit tests
# ---------------------------------------------------------------------------

class TestResolvePath:
    """Tests for the dot-notation path resolver."""

    def test_simple_key(self):
        assert _resolve_path({"name": "Alice"}, "name") == "Alice"

    def test_nested_key(self):
        data = {"current": {"temp": 72}}
        assert _resolve_path(data, "current.temp") == 72

    def test_deeply_nested(self):
        data = {"a": {"b": {"c": {"d": "deep"}}}}
        assert _resolve_path(data, "a.b.c.d") == "deep"

    def test_array_index(self):
        data = {"items": [{"name": "first"}, {"name": "second"}]}
        assert _resolve_path(data, "items[0].name") == "first"
        assert _resolve_path(data, "items[1].name") == "second"

    def test_root_array_index(self):
        data = [10, 20, 30]
        assert _resolve_path(data, "[0]") == 10
        assert _resolve_path(data, "[2]") == 30

    def test_missing_key_returns_none(self):
        assert _resolve_path({"a": 1}, "b") is None

    def test_missing_nested_key_returns_none(self):
        assert _resolve_path({"a": {"b": 1}}, "a.c") is None

    def test_out_of_bounds_index_returns_none(self):
        data = {"items": [1, 2]}
        assert _resolve_path(data, "items[5]") is None

    def test_none_data_returns_none(self):
        assert _resolve_path(None, "key") is None

    def test_path_through_non_dict_returns_none(self):
        data = {"a": "string"}
        assert _resolve_path(data, "a.b") is None

    def test_index_on_non_list_returns_none(self):
        data = {"items": "not_a_list"}
        assert _resolve_path(data, "items[0]") is None


# ---------------------------------------------------------------------------
# _xml_to_dict unit tests
# ---------------------------------------------------------------------------

class TestXmlToDict:
    """Tests for XML to dict conversion."""

    def test_simple_element(self):
        import defusedxml.ElementTree as ElementTree
        root = ElementTree.fromstring("<root><name>Test</name></root>")
        result = _xml_to_dict(root)
        assert result == {"name": "Test"}

    def test_nested_elements(self):
        import defusedxml.ElementTree as ElementTree
        xml = "<root><parent><child>value</child></parent></root>"
        root = ElementTree.fromstring(xml)
        result = _xml_to_dict(root)
        assert result == {"parent": {"child": "value"}}

    def test_repeated_tags_become_list(self):
        import defusedxml.ElementTree as ElementTree
        xml = "<root><item>a</item><item>b</item><item>c</item></root>"
        root = ElementTree.fromstring(xml)
        result = _xml_to_dict(root)
        assert result == {"item": ["a", "b", "c"]}

    def test_empty_element(self):
        import defusedxml.ElementTree as ElementTree
        root = ElementTree.fromstring("<root><empty/></root>")
        result = _xml_to_dict(root)
        assert result == {"empty": ""}


# ---------------------------------------------------------------------------
# _build_feeds unit tests
# ---------------------------------------------------------------------------

class TestBuildFeeds:
    """Tests for feed normalisation."""

    def test_single_feed_from_top_level(self):
        config = {
            "url": "https://example.com/data",
            "format": "json",
            "mappings": [{"variable": "x", "path": "y"}],
        }
        feeds = _build_feeds(config)
        assert len(feeds) == 1
        assert feeds[0]["url"] == "https://example.com/data"

    @patch.dict("os.environ", {"GENERIC_DATA_URL": "https://env.example.com/data"})
    def test_single_feed_from_env(self):
        config = {"mappings": [{"variable": "x", "path": "y"}]}
        feeds = _build_feeds(config)
        assert len(feeds) == 1
        assert feeds[0]["url"] == "https://env.example.com/data"

    def test_multi_feed(self):
        config = {
            "feeds": [
                {"url": "https://a.com", "mappings": [{"variable": "a", "path": "x"}]},
                {"url": "https://b.com", "mappings": [{"variable": "b", "path": "y"}]},
            ]
        }
        feeds = _build_feeds(config)
        assert len(feeds) == 2

    @patch.dict("os.environ", {"GENERIC_DATA_URL": ""})
    def test_empty_config_returns_empty(self):
        feeds = _build_feeds({})
        assert feeds == []

    def test_feeds_takes_precedence_over_top_level(self):
        config = {
            "url": "https://ignored.com",
            "mappings": [{"variable": "ignored", "path": "x"}],
            "feeds": [
                {"url": "https://used.com", "mappings": [{"variable": "a", "path": "y"}]},
            ],
        }
        feeds = _build_feeds(config)
        assert len(feeds) == 1
        assert feeds[0]["url"] == "https://used.com"


# ---------------------------------------------------------------------------
# GenericDataPlugin — single-feed tests (backward compatibility)
# ---------------------------------------------------------------------------

class TestGenericDataPlugin:
    """Test suite for GenericDataPlugin — single-feed mode."""

    def test_plugin_id(self, sample_manifest):
        plugin = GenericDataPlugin(sample_manifest)
        assert plugin.plugin_id == "generic_data"

    def test_validate_config_valid(self, sample_manifest, sample_config):
        plugin = GenericDataPlugin(sample_manifest)
        errors = plugin.validate_config(sample_config)
        assert len(errors) == 0

    @patch.dict("os.environ", {"GENERIC_DATA_URL": ""})
    def test_validate_config_missing_url(self, sample_manifest):
        plugin = GenericDataPlugin(sample_manifest)
        config = {"mappings": [{"variable": "x", "path": "y"}]}
        errors = plugin.validate_config(config)
        assert any("url" in e.lower() for e in errors)

    @patch.dict("os.environ", {"GENERIC_DATA_URL": "https://env.example.com/data"})
    def test_validate_config_url_from_env(self, sample_manifest):
        plugin = GenericDataPlugin(sample_manifest)
        config = {"mappings": [{"variable": "x", "path": "y"}]}
        errors = plugin.validate_config(config)
        assert not any("url" in e.lower() for e in errors)

    def test_validate_config_invalid_url(self, sample_manifest):
        plugin = GenericDataPlugin(sample_manifest)
        config = {
            "url": "ftp://bad.com/data",
            "mappings": [{"variable": "x", "path": "y"}],
        }
        errors = plugin.validate_config(config)
        assert any("http" in e.lower() for e in errors)

    def test_validate_config_missing_mappings(self, sample_manifest):
        plugin = GenericDataPlugin(sample_manifest)
        config = {"url": "https://example.com/data", "mappings": []}
        errors = plugin.validate_config(config)
        assert any("mapping" in e.lower() for e in errors)

    def test_validate_config_invalid_variable_name(self, sample_manifest):
        plugin = GenericDataPlugin(sample_manifest)
        config = {
            "url": "https://example.com/data",
            "mappings": [{"variable": "Bad-Name!", "path": "x"}],
        }
        errors = plugin.validate_config(config)
        assert any("lowercase" in e.lower() for e in errors)

    def test_validate_config_duplicate_variable(self, sample_manifest):
        plugin = GenericDataPlugin(sample_manifest)
        config = {
            "url": "https://example.com/data",
            "mappings": [
                {"variable": "temp", "path": "a"},
                {"variable": "temp", "path": "b"},
            ],
        }
        errors = plugin.validate_config(config)
        assert any("duplicate" in e.lower() for e in errors)

    def test_validate_config_missing_mapping_fields(self, sample_manifest):
        plugin = GenericDataPlugin(sample_manifest)
        config = {
            "url": "https://example.com/data",
            "mappings": [{"variable": "", "path": ""}],
        }
        errors = plugin.validate_config(config)
        assert len(errors) >= 2

    def test_validate_config_unsupported_format(self, sample_manifest):
        plugin = GenericDataPlugin(sample_manifest)
        config = {
            "url": "https://example.com/data",
            "format": "csv",
            "mappings": [{"variable": "x", "path": "y"}],
        }
        errors = plugin.validate_config(config)
        assert any("format" in e.lower() for e in errors)

    def test_validate_config_unsupported_method(self, sample_manifest):
        plugin = GenericDataPlugin(sample_manifest)
        config = {
            "url": "https://example.com/data",
            "method": "DELETE",
            "mappings": [{"variable": "x", "path": "y"}],
        }
        errors = plugin.validate_config(config)
        assert any("method" in e.lower() for e in errors)

    def test_validate_config_low_refresh(self, sample_manifest):
        plugin = GenericDataPlugin(sample_manifest)
        config = {
            "url": "https://example.com/data",
            "mappings": [{"variable": "x", "path": "y"}],
            "refresh_seconds": 5,
        }
        errors = plugin.validate_config(config)
        assert any("refresh" in e.lower() for e in errors)

    def test_validate_config_header_missing_name(self, sample_manifest):
        plugin = GenericDataPlugin(sample_manifest)
        config = {
            "url": "https://example.com/data",
            "mappings": [{"variable": "x", "path": "y"}],
            "headers": [{"name": "", "value": "v"}],
        }
        errors = plugin.validate_config(config)
        assert any("header" in e.lower() for e in errors)

    def test_validate_config_header_missing_value(self, sample_manifest):
        plugin = GenericDataPlugin(sample_manifest)
        config = {
            "url": "https://example.com/data",
            "mappings": [{"variable": "x", "path": "y"}],
            "headers": [{"name": "Authorization", "value": ""}],
        }
        errors = plugin.validate_config(config)
        assert any("header" in e.lower() for e in errors)

    @patch("plugins.generic_data.requests.request")
    def test_fetch_data_json_success(
        self, mock_request, sample_manifest, sample_config, sample_json_response
    ):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.content = b'x' * 100
        mock_resp.json.return_value = sample_json_response
        mock_resp.raise_for_status = Mock()
        mock_request.return_value = mock_resp

        plugin = GenericDataPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.available is True
        assert result.error is None
        assert result.data is not None
        assert result.data["temperature"] == "72"
        assert result.data["condition"] == "Sunny"
        assert result.data["feed_count"] == "1"

    @patch("plugins.generic_data.requests.request")
    def test_fetch_data_interpolates_url_placeholders(
        self, mock_request, sample_manifest, sample_json_response
    ):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.content = b"x" * 100
        mock_resp.json.return_value = sample_json_response
        mock_resp.raise_for_status = Mock()
        mock_request.return_value = mock_resp

        plugin = GenericDataPlugin(sample_manifest)
        plugin.config = {
            "url": "https://api.example.com/data?d={{date}}",
            "format": "json",
            "mappings": [{"variable": "temperature", "path": "current.temp_f"}],
        }
        result = plugin.fetch_data()

        assert result.available is True
        mock_request.assert_called_once()
        called_url = mock_request.call_args[0][1]
        assert "{{" not in called_url
        assert re.search(r"d=\d{4}-\d{2}-\d{2}", called_url)

    @patch("plugins.generic_data.requests.request")
    def test_fetch_data_interpolates_header_values(
        self, mock_request, sample_manifest, sample_json_response
    ):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.content = b"x" * 100
        mock_resp.json.return_value = sample_json_response
        mock_resp.raise_for_status = Mock()
        mock_request.return_value = mock_resp

        plugin = GenericDataPlugin(sample_manifest)
        plugin.config = {
            "url": "https://api.example.com/data",
            "format": "json",
            "headers": [{"name": "X-Date", "value": "day-{{date}}"}],
            "mappings": [{"variable": "temperature", "path": "current.temp_f"}],
        }
        result = plugin.fetch_data()

        assert result.available is True
        hdrs = mock_request.call_args.kwargs["headers"]
        assert "{{" not in hdrs["X-Date"]
        assert re.match(r"day-\d{4}-\d{2}-\d{2}", hdrs["X-Date"])

    @patch("plugins.generic_data.requests.request")
    def test_fetch_data_with_default_value(
        self, mock_request, sample_manifest, sample_json_response
    ):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.content = b'x' * 100
        mock_resp.json.return_value = sample_json_response
        mock_resp.raise_for_status = Mock()
        mock_request.return_value = mock_resp

        plugin = GenericDataPlugin(sample_manifest)
        plugin.config = {
            "url": "https://api.example.com/data",
            "format": "json",
            "mappings": [
                {"variable": "missing_field", "path": "nonexistent.path", "default": "fallback"},
            ],
        }
        result = plugin.fetch_data()

        assert result.available is True
        assert result.data["missing_field"] == "fallback"

    @patch("plugins.generic_data.requests.request")
    def test_fetch_data_array_path(
        self, mock_request, sample_manifest, sample_json_response
    ):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.content = b'x' * 100
        mock_resp.json.return_value = sample_json_response
        mock_resp.raise_for_status = Mock()
        mock_request.return_value = mock_resp

        plugin = GenericDataPlugin(sample_manifest)
        plugin.config = {
            "url": "https://api.example.com/data",
            "format": "json",
            "mappings": [
                {"variable": "first_day", "path": "forecast[0].day"},
                {"variable": "first_high", "path": "forecast[0].high"},
            ],
        }
        result = plugin.fetch_data()

        assert result.available is True
        assert result.data["first_day"] == "Monday"
        assert result.data["first_high"] == "75"

    @patch("plugins.generic_data.requests.request")
    def test_fetch_data_xml_success(
        self, mock_request, sample_manifest, sample_xml_response
    ):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.content = sample_xml_response.encode()
        mock_resp.text = sample_xml_response
        mock_resp.raise_for_status = Mock()
        mock_request.return_value = mock_resp

        plugin = GenericDataPlugin(sample_manifest)
        plugin.config = {
            "url": "https://api.example.com/data.xml",
            "format": "xml",
            "mappings": [
                {"variable": "temp", "path": "current.temp"},
                {"variable": "city", "path": "location.name"},
            ],
        }
        result = plugin.fetch_data()

        assert result.available is True
        assert result.data["temp"] == "72"
        assert result.data["city"] == "San Francisco"

    @patch("plugins.generic_data.requests.request")
    @patch.dict("os.environ", {"GENERIC_DATA_URL": "https://env.example.com/data"})
    def test_fetch_data_url_from_env(
        self, mock_request, sample_manifest, sample_json_response
    ):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.content = b'x' * 100
        mock_resp.json.return_value = sample_json_response
        mock_resp.raise_for_status = Mock()
        mock_request.return_value = mock_resp

        plugin = GenericDataPlugin(sample_manifest)
        plugin.config = {
            "format": "json",
            "mappings": [
                {"variable": "temp", "path": "current.temp_f"},
            ],
        }
        result = plugin.fetch_data()

        assert result.available is True
        mock_request.assert_called_once()
        assert mock_request.call_args[0][1] == "https://env.example.com/data"

    @patch.dict("os.environ", {"GENERIC_DATA_URL": ""})
    def test_fetch_data_missing_url(self, sample_manifest):
        plugin = GenericDataPlugin(sample_manifest)
        plugin.config = {"mappings": [{"variable": "x", "path": "y"}]}
        result = plugin.fetch_data()

        assert result.available is False
        assert "url" in result.error.lower()

    def test_fetch_data_no_mappings(self, sample_manifest):
        plugin = GenericDataPlugin(sample_manifest)
        plugin.config = {"url": "https://example.com/data", "mappings": []}
        result = plugin.fetch_data()

        assert result.available is False
        assert "mapping" in result.error.lower()

    @patch("plugins.generic_data.requests.request")
    def test_fetch_data_timeout(self, mock_request, sample_manifest, sample_config):
        import requests as req
        mock_request.side_effect = req.exceptions.Timeout("timed out")

        plugin = GenericDataPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.available is False
        assert "timed out" in result.error.lower()

    @patch("plugins.generic_data.requests.request")
    def test_fetch_data_connection_error(self, mock_request, sample_manifest, sample_config):
        import requests as req
        mock_request.side_effect = req.exceptions.ConnectionError("refused")

        plugin = GenericDataPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.available is False
        assert "connection" in result.error.lower()

    @patch("plugins.generic_data.requests.request")
    def test_fetch_data_http_error(self, mock_request, sample_manifest, sample_config):
        import requests as req
        mock_resp = Mock()
        mock_resp.raise_for_status.side_effect = req.exceptions.HTTPError("404 Not Found")
        mock_request.return_value = mock_resp

        plugin = GenericDataPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.available is False
        assert "http" in result.error.lower()

    @patch("plugins.generic_data.requests.request")
    def test_fetch_data_response_too_large(
        self, mock_request, sample_manifest, sample_config
    ):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.content = b'x' * (MAX_RESPONSE_BYTES + 1)
        mock_resp.raise_for_status = Mock()
        mock_request.return_value = mock_resp

        plugin = GenericDataPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.available is False
        assert "too large" in result.error.lower()

    @patch("plugins.generic_data.requests.request")
    def test_fetch_data_invalid_json(self, mock_request, sample_manifest, sample_config):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.content = b'not json'
        mock_resp.json.side_effect = ValueError("No JSON")
        mock_resp.raise_for_status = Mock()
        mock_request.return_value = mock_resp

        plugin = GenericDataPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.available is False
        assert "parse" in result.error.lower()

    @patch("plugins.generic_data.requests.request")
    def test_fetch_data_formatted_lines(
        self, mock_request, sample_manifest, sample_config, sample_json_response
    ):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.content = b'x' * 100
        mock_resp.json.return_value = sample_json_response
        mock_resp.raise_for_status = Mock()
        mock_request.return_value = mock_resp

        plugin = GenericDataPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.formatted_lines is not None
        assert len(result.formatted_lines) == 6

    @patch("plugins.generic_data.requests.request")
    def test_fetch_data_post_with_body(
        self, mock_request, sample_manifest, sample_json_response
    ):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.content = b'x' * 100
        mock_resp.json.return_value = sample_json_response
        mock_resp.raise_for_status = Mock()
        mock_request.return_value = mock_resp

        plugin = GenericDataPlugin(sample_manifest)
        plugin.config = {
            "url": "https://api.example.com/query",
            "format": "json",
            "method": "POST",
            "body": '{"query": "test"}',
            "mappings": [
                {"variable": "city", "path": "location.name"},
            ],
        }
        result = plugin.fetch_data()

        assert result.available is True
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args[0][0] == "POST"
        assert call_args[1]["data"] == '{"query": "test"}'

    @patch("plugins.generic_data.requests.request")
    def test_fetch_data_custom_headers(
        self, mock_request, sample_manifest, sample_json_response
    ):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.content = b'x' * 100
        mock_resp.json.return_value = sample_json_response
        mock_resp.raise_for_status = Mock()
        mock_request.return_value = mock_resp

        plugin = GenericDataPlugin(sample_manifest)
        plugin.config = {
            "url": "https://api.example.com/data",
            "format": "json",
            "headers": [
                {"name": "Authorization", "value": "Bearer token123"},
                {"name": "X-Custom", "value": "value"},
            ],
            "mappings": [{"variable": "city", "path": "location.name"}],
        }
        result = plugin.fetch_data()

        assert result.available is True
        call_headers = mock_request.call_args[1]["headers"]
        assert call_headers["Authorization"] == "Bearer token123"
        assert call_headers["X-Custom"] == "value"

    @patch("plugins.generic_data.requests.request")
    def test_fetch_data_all_manifest_variables(
        self, mock_request, sample_manifest, sample_config, sample_json_response
    ):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.content = b'x' * 100
        mock_resp.json.return_value = sample_json_response
        mock_resp.raise_for_status = Mock()
        mock_request.return_value = mock_resp

        plugin = GenericDataPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.available is True
        data = result.data

        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        simple = manifest["variables"]["simple"]
        var_names = list(simple.keys()) if isinstance(simple, dict) else list(simple)
        for var in var_names:
            assert var in data, f"Variable '{var}' declared in manifest but not in data"

    def test_get_formatted_display_no_config(self, sample_manifest):
        plugin = GenericDataPlugin(sample_manifest)
        plugin.config = {}
        lines = plugin.get_formatted_display()
        assert lines is None

    def test_cleanup(self, sample_manifest):
        plugin = GenericDataPlugin(sample_manifest)
        plugin.cleanup()


# ---------------------------------------------------------------------------
# Multi-feed tests
# ---------------------------------------------------------------------------

class TestMultiFeed:
    """Tests for multi-feed configuration."""

    def test_validate_multi_feed_valid(self, sample_manifest, multi_feed_config):
        plugin = GenericDataPlugin(sample_manifest)
        errors = plugin.validate_config(multi_feed_config)
        assert len(errors) == 0

    def test_validate_multi_feed_duplicate_vars_across_feeds(self, sample_manifest):
        plugin = GenericDataPlugin(sample_manifest)
        config = {
            "feeds": [
                {
                    "url": "https://a.com",
                    "mappings": [{"variable": "temp", "path": "a"}],
                },
                {
                    "url": "https://b.com",
                    "mappings": [{"variable": "temp", "path": "b"}],
                },
            ],
        }
        errors = plugin.validate_config(config)
        assert any("duplicate" in e.lower() for e in errors)

    def test_validate_multi_feed_missing_url(self, sample_manifest):
        plugin = GenericDataPlugin(sample_manifest)
        config = {
            "feeds": [
                {"url": "", "mappings": [{"variable": "x", "path": "y"}]},
            ],
        }
        errors = plugin.validate_config(config)
        assert any("url" in e.lower() for e in errors)

    def test_validate_multi_feed_too_many(self, sample_manifest):
        plugin = GenericDataPlugin(sample_manifest)
        config = {
            "feeds": [
                {"url": f"https://example.com/{i}", "mappings": [{"variable": f"v{i}", "path": "x"}]}
                for i in range(MAX_FEEDS + 1)
            ],
        }
        errors = plugin.validate_config(config)
        assert any("maximum" in e.lower() for e in errors)

    def test_validate_empty_config(self, sample_manifest):
        plugin = GenericDataPlugin(sample_manifest)
        errors = plugin.validate_config({})
        assert any("feed" in e.lower() for e in errors)

    @patch("plugins.generic_data.requests.request")
    def test_fetch_multi_feed_success(
        self,
        mock_request,
        sample_manifest,
        multi_feed_config,
        sample_json_response,
        traffic_json_response,
    ):
        """Both feeds succeed — variables from both appear in result."""
        weather_resp = Mock()
        weather_resp.status_code = 200
        weather_resp.content = b'x' * 100
        weather_resp.json.return_value = sample_json_response
        weather_resp.raise_for_status = Mock()

        traffic_resp = Mock()
        traffic_resp.status_code = 200
        traffic_resp.content = b'x' * 100
        traffic_resp.json.return_value = traffic_json_response
        traffic_resp.raise_for_status = Mock()

        mock_request.side_effect = [weather_resp, traffic_resp]

        plugin = GenericDataPlugin(sample_manifest)
        plugin.config = multi_feed_config
        result = plugin.fetch_data()

        assert result.available is True
        assert result.data["temperature"] == "72"
        assert result.data["condition"] == "Sunny"
        assert result.data["commute_time"] == "25 min"
        assert result.data["traffic_status"] == "moderate"
        assert result.data["feed_count"] == "2"
        assert mock_request.call_count == 2

    @patch("plugins.generic_data.requests.request")
    def test_fetch_multi_feed_partial_failure(
        self,
        mock_request,
        sample_manifest,
        multi_feed_config,
        sample_json_response,
    ):
        """One feed fails, the other succeeds — partial data returned."""
        import requests as req

        weather_resp = Mock()
        weather_resp.status_code = 200
        weather_resp.content = b'x' * 100
        weather_resp.json.return_value = sample_json_response
        weather_resp.raise_for_status = Mock()

        mock_request.side_effect = [
            weather_resp,
            req.exceptions.Timeout("timed out"),
        ]

        plugin = GenericDataPlugin(sample_manifest)
        plugin.config = multi_feed_config
        result = plugin.fetch_data()

        assert result.available is True
        assert result.data["temperature"] == "72"
        assert "commute_time" not in result.data

    @patch("plugins.generic_data.requests.request")
    def test_fetch_multi_feed_all_fail(
        self, mock_request, sample_manifest, multi_feed_config
    ):
        """All feeds fail — result is unavailable."""
        import requests as req

        mock_request.side_effect = [
            req.exceptions.ConnectionError("refused"),
            req.exceptions.Timeout("timed out"),
        ]

        plugin = GenericDataPlugin(sample_manifest)
        plugin.config = multi_feed_config
        result = plugin.fetch_data()

        assert result.available is False
        assert "connection" in result.error.lower()

    @patch("plugins.generic_data.requests.request")
    def test_fetch_multi_feed_mixed_formats(
        self, mock_request, sample_manifest, sample_xml_response
    ):
        """Feed 1 is JSON, feed 2 is XML — both parsed correctly."""
        json_resp = Mock()
        json_resp.status_code = 200
        json_resp.content = b'x' * 100
        json_resp.json.return_value = {"value": 42}
        json_resp.raise_for_status = Mock()

        xml_resp = Mock()
        xml_resp.status_code = 200
        xml_resp.content = sample_xml_response.encode()
        xml_resp.text = sample_xml_response
        xml_resp.raise_for_status = Mock()

        mock_request.side_effect = [json_resp, xml_resp]

        plugin = GenericDataPlugin(sample_manifest)
        plugin.config = {
            "feeds": [
                {
                    "url": "https://json.example.com",
                    "format": "json",
                    "mappings": [{"variable": "number", "path": "value"}],
                },
                {
                    "url": "https://xml.example.com",
                    "format": "xml",
                    "mappings": [{"variable": "city", "path": "location.name"}],
                },
            ],
        }
        result = plugin.fetch_data()

        assert result.available is True
        assert result.data["number"] == "42"
        assert result.data["city"] == "San Francisco"

    def test_fetch_no_feeds(self, sample_manifest):
        plugin = GenericDataPlugin(sample_manifest)
        plugin.config = {}
        result = plugin.fetch_data()
        assert result.available is False
        assert "feed" in result.error.lower()

    def test_validate_multi_feed_error_prefix(self, sample_manifest):
        """Multi-feed validation errors include feed number prefix."""
        plugin = GenericDataPlugin(sample_manifest)
        config = {
            "feeds": [
                {"url": "https://a.com", "mappings": [{"variable": "ok", "path": "x"}]},
                {"url": "", "mappings": [{"variable": "y", "path": "z"}]},
            ],
        }
        errors = plugin.validate_config(config)
        assert any("feed 2" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestPluginEdgeCases:
    """Tests for edge cases and error handling."""

    @patch("plugins.generic_data.requests.request")
    def test_empty_response_body(self, mock_request, sample_manifest):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.content = b'{}'
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status = Mock()
        mock_request.return_value = mock_resp

        plugin = GenericDataPlugin(sample_manifest)
        plugin.config = {
            "url": "https://example.com/empty",
            "format": "json",
            "mappings": [{"variable": "val", "path": "missing", "default": "none"}],
        }
        result = plugin.fetch_data()

        assert result.available is True
        assert result.data["val"] == "none"

    @patch("plugins.generic_data.requests.request")
    def test_mapping_with_empty_variable_skipped(self, mock_request, sample_manifest):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"a": 1}'
        mock_resp.json.return_value = {"a": 1}
        mock_resp.raise_for_status = Mock()
        mock_request.return_value = mock_resp

        plugin = GenericDataPlugin(sample_manifest)
        plugin.config = {
            "url": "https://example.com/data",
            "format": "json",
            "mappings": [
                {"variable": "", "path": ""},
                {"variable": "val", "path": "a"},
            ],
        }
        result = plugin.fetch_data()

        assert result.available is True
        assert result.data["val"] == "1"
        assert "" not in result.data

    @patch("plugins.generic_data.requests.request")
    def test_unexpected_exception(self, mock_request, sample_manifest, sample_config):
        mock_request.side_effect = RuntimeError("unexpected")

        plugin = GenericDataPlugin(sample_manifest)
        plugin.config = sample_config
        result = plugin.fetch_data()

        assert result.available is False
        assert "unexpected" in result.error.lower()


# ---------------------------------------------------------------------------
# Manifest metadata tests
# ---------------------------------------------------------------------------

class TestManifestMetadata:
    """Tests for the rich metadata format in the generic_data manifest."""

    def test_manifest_uses_dict_simple_format(self):
        """Manifest uses the dict format for simple variables with metadata."""
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        simple = manifest["variables"]["simple"]
        assert isinstance(simple, dict), "simple should use the rich dict format"

    def test_all_variables_have_descriptions(self):
        """Every variable in the manifest has a description."""
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        simple = manifest["variables"]["simple"]
        for var_name, meta in simple.items():
            assert "description" in meta and meta["description"], \
                f"Variable '{var_name}' missing description"

    def test_all_variables_have_valid_groups(self):
        """Every variable references a group that is defined."""
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        groups = set(manifest["variables"].get("groups", {}).keys())
        simple = manifest["variables"]["simple"]
        for var_name, meta in simple.items():
            group = meta.get("group", "")
            if group:
                assert group in groups, \
                    f"Variable '{var_name}' references undefined group '{group}'"

    def test_groups_are_defined(self):
        """Manifest defines variable groups."""
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        groups = manifest["variables"].get("groups", {})
        assert len(groups) > 0, "Manifest should define at least one group"
        for group_id, group_def in groups.items():
            assert "label" in group_def, f"Group '{group_id}' missing label"

    def test_dynamic_flag_preserved(self):
        """Manifest preserves dynamic=true for user-defined variables."""
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        assert manifest["variables"].get("dynamic") is True, \
            "dynamic flag should be true for generic_data plugin"
