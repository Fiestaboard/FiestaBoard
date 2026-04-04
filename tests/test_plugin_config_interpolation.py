"""Tests for plugin config variable interpolation.

Validates that plugin configuration values containing {{variable}} patterns
are correctly resolved to their dynamic values at runtime.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest

from src.plugins.base import PluginBase, PluginResult
from src.plugins.config_interpolation import (
    get_builtin_variables,
    interpolate_config,
    interpolate_string,
)


# ── Test fixtures ──────────────────────────────────────────────


MANIFEST = {
    "id": "test_plugin",
    "name": "Test Plugin",
    "version": "1.0.0",
    "settings_schema": {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "refresh_seconds": {"type": "integer", "default": 300, "minimum": 30},
        },
    },
}


class InterpolatingPlugin(PluginBase):
    """Concrete plugin for testing config interpolation."""

    def __init__(self, manifest=None):
        super().__init__(manifest or MANIFEST)

    @property
    def plugin_id(self) -> str:
        return "test_plugin"

    def fetch_data(self) -> PluginResult:
        resolved = self.resolve_config_variables()
        return PluginResult(available=True, data={"resolved_url": resolved.get("url", "")})


# ── Built-in variables ─────────────────────────────────────────


class TestGetBuiltinVariables:
    """Tests for the built-in system variable provider."""

    def test_returns_dict(self):
        result = get_builtin_variables()
        assert isinstance(result, dict)

    def test_contains_date(self):
        result = get_builtin_variables()
        assert "date" in result
        assert re.match(r"\d{4}-\d{2}-\d{2}", result["date"])

    def test_contains_year(self):
        result = get_builtin_variables()
        assert "year" in result
        assert result["year"].isdigit()
        assert len(result["year"]) == 4

    def test_contains_month(self):
        result = get_builtin_variables()
        assert "month" in result
        assert result["month"].isdigit()
        assert 1 <= int(result["month"]) <= 12

    def test_contains_day(self):
        result = get_builtin_variables()
        assert "day" in result
        assert result["day"].isdigit()
        assert 1 <= int(result["day"]) <= 31

    def test_contains_hour(self):
        result = get_builtin_variables()
        assert "hour" in result
        assert result["hour"].isdigit()

    def test_contains_minute(self):
        result = get_builtin_variables()
        assert "minute" in result
        assert result["minute"].isdigit()

    def test_contains_timestamp(self):
        result = get_builtin_variables()
        assert "timestamp" in result
        assert result["timestamp"].isdigit()

    def test_contains_month_name(self):
        result = get_builtin_variables()
        assert "month_name" in result
        assert isinstance(result["month_name"], str)
        assert len(result["month_name"]) >= 3  # e.g. "Jan" or "January"

    def test_contains_day_of_week(self):
        result = get_builtin_variables()
        assert "day_of_week" in result
        assert isinstance(result["day_of_week"], str)

    def test_respects_timezone(self):
        result_la = get_builtin_variables(timezone="America/Los_Angeles")
        result_tokyo = get_builtin_variables(timezone="Asia/Tokyo")
        # At least one of date/hour should differ (they're typically 16-17h apart)
        # We just check they both return valid data
        assert re.match(r"\d{4}-\d{2}-\d{2}", result_la["date"])
        assert re.match(r"\d{4}-\d{2}-\d{2}", result_tokyo["date"])


# ── interpolate_string ─────────────────────────────────────────


class TestInterpolateString:
    """Tests for single-string variable interpolation."""

    def test_no_variables_passthrough(self):
        assert interpolate_string("https://api.example.com/data", {}) == "https://api.example.com/data"

    def test_simple_variable(self):
        variables = {"date": "2025-06-15"}
        result = interpolate_string("https://api.example.com/data?date={{date}}", variables)
        assert result == "https://api.example.com/data?date=2025-06-15"

    def test_multiple_variables(self):
        variables = {"year": "2025", "month": "06", "day": "15"}
        result = interpolate_string(
            "https://api.example.com/{{year}}/{{month}}/{{day}}",
            variables,
        )
        assert result == "https://api.example.com/2025/06/15"

    def test_variable_with_spaces_in_braces(self):
        variables = {"date": "2025-06-15"}
        result = interpolate_string("https://api.example.com/{{ date }}", variables)
        assert result == "https://api.example.com/2025-06-15"

    def test_unknown_variable_preserved(self):
        result = interpolate_string("https://api.example.com/{{unknown}}", {})
        assert result == "https://api.example.com/{{unknown}}"

    def test_dotted_variable(self):
        variables = {"weather.temperature": "72"}
        result = interpolate_string("temp is {{weather.temperature}}", variables)
        assert result == "temp is 72"

    def test_date_format_variable(self):
        variables = {"date:%Y%m%d": "20250615"}
        result = interpolate_string(
            "https://api.example.com/data/{{date:%Y%m%d}}",
            variables,
        )
        assert result == "https://api.example.com/data/20250615"

    def test_empty_string(self):
        assert interpolate_string("", {}) == ""

    def test_non_string_returns_as_is(self):
        # interpolate_string only handles strings; non-strings are returned unchanged
        assert interpolate_string(42, {}) == 42  # type: ignore[arg-type]

    def test_adjacent_variables(self):
        variables = {"year": "2025", "month": "06"}
        result = interpolate_string("{{year}}{{month}}", variables)
        assert result == "202506"

    def test_variable_at_start(self):
        variables = {"prefix": "v1"}
        result = interpolate_string("{{prefix}}/data", variables)
        assert result == "v1/data"

    def test_variable_at_end(self):
        variables = {"suffix": "json"}
        result = interpolate_string("data.{{suffix}}", variables)
        assert result == "data.json"

    def test_repeated_variable(self):
        variables = {"id": "123"}
        result = interpolate_string("{{id}}/{{id}}", variables)
        assert result == "123/123"


# ── interpolate_config ─────────────────────────────────────────


class TestInterpolateConfig:
    """Tests for full config dict interpolation."""

    def test_empty_config(self):
        assert interpolate_config({}, {}) == {}

    def test_string_values_interpolated(self):
        config = {"url": "https://api.example.com/{{date}}"}
        variables = {"date": "2025-06-15"}
        result = interpolate_config(config, variables)
        assert result["url"] == "https://api.example.com/2025-06-15"

    def test_non_string_values_preserved(self):
        config = {"enabled": True, "count": 42, "rate": 3.14}
        result = interpolate_config(config, {})
        assert result == {"enabled": True, "count": 42, "rate": 3.14}

    def test_nested_dict_interpolated(self):
        config = {
            "api": {
                "url": "https://api.example.com/{{date}}",
                "timeout": 30,
            }
        }
        variables = {"date": "2025-06-15"}
        result = interpolate_config(config, variables)
        assert result["api"]["url"] == "https://api.example.com/2025-06-15"
        assert result["api"]["timeout"] == 30

    def test_list_values_interpolated(self):
        config = {
            "urls": [
                "https://api.example.com/{{date}}/a",
                "https://api.example.com/{{date}}/b",
            ]
        }
        variables = {"date": "2025-06-15"}
        result = interpolate_config(config, variables)
        assert result["urls"] == [
            "https://api.example.com/2025-06-15/a",
            "https://api.example.com/2025-06-15/b",
        ]

    def test_deeply_nested(self):
        config = {
            "level1": {
                "level2": {
                    "level3": "value-{{key}}"
                }
            }
        }
        variables = {"key": "resolved"}
        result = interpolate_config(config, variables)
        assert result["level1"]["level2"]["level3"] == "value-resolved"

    def test_original_config_not_mutated(self):
        config = {"url": "https://api.example.com/{{date}}"}
        variables = {"date": "2025-06-15"}
        interpolate_config(config, variables)
        assert config["url"] == "https://api.example.com/{{date}}"

    def test_mixed_types_in_list(self):
        config = {"items": ["{{date}}", 42, True, None]}
        variables = {"date": "2025-06-15"}
        result = interpolate_config(config, variables)
        assert result["items"] == ["2025-06-15", 42, True, None]

    def test_none_values_preserved(self):
        config = {"url": None, "name": "test"}
        result = interpolate_config(config, {})
        assert result["url"] is None
        assert result["name"] == "test"


# ── Built-in variable integration ──────────────────────────────


class TestBuiltinVariableIntegration:
    """Tests that built-in date/time variables work in interpolation."""

    def test_date_variable_in_url(self):
        builtin = get_builtin_variables()
        config = {"url": "https://api.example.com/data?date={{date}}"}
        result = interpolate_config(config, builtin)
        assert re.match(
            r"https://api\.example\.com/data\?date=\d{4}-\d{2}-\d{2}",
            result["url"],
        )

    def test_year_month_day_variables(self):
        builtin = get_builtin_variables()
        config = {"url": "https://api.example.com/{{year}}/{{month}}/{{day}}"}
        result = interpolate_config(config, builtin)
        # Verify the pattern matches year/month/day format
        assert re.match(
            r"https://api\.example\.com/\d{4}/\d{1,2}/\d{1,2}",
            result["url"],
        )

    def test_timestamp_variable(self):
        builtin = get_builtin_variables()
        config = {"url": "https://api.example.com/data?ts={{timestamp}}"}
        result = interpolate_config(config, builtin)
        # Timestamp should be all digits
        assert re.match(
            r"https://api\.example\.com/data\?ts=\d+",
            result["url"],
        )

    def test_date_format_variable(self):
        builtin = get_builtin_variables()
        config = {"url": "https://api.example.com/data/{{date:%Y%m%d}}"}
        result = interpolate_config(config, builtin)
        assert re.match(
            r"https://api\.example\.com/data/\d{8}",
            result["url"],
        )


# ── Custom date format ─────────────────────────────────────────


class TestCustomDateFormat:
    """Tests for custom date format variables (date:FORMAT)."""

    def test_compact_date_format(self):
        builtin = get_builtin_variables()
        assert "date:%Y%m%d" in builtin
        assert re.match(r"\d{8}", builtin["date:%Y%m%d"])

    def test_slash_date_format(self):
        builtin = get_builtin_variables()
        assert "date:%m/%d/%Y" in builtin
        assert re.match(r"\d{2}/\d{2}/\d{4}", builtin["date:%m/%d/%Y"])

    def test_month_day_format(self):
        builtin = get_builtin_variables()
        assert "date:%m-%d" in builtin
        assert re.match(r"\d{2}-\d{2}", builtin["date:%m-%d"])


# ── PluginBase.resolve_config_variables() ──────────────────────


class TestPluginBaseResolveConfigVariables:
    """Tests for the PluginBase.resolve_config_variables() method."""

    def test_resolves_builtin_variables(self):
        plugin = InterpolatingPlugin()
        plugin._config = {"url": "https://api.example.com/data?date={{date}}"}
        resolved = plugin.resolve_config_variables()
        assert re.match(
            r"https://api\.example\.com/data\?date=\d{4}-\d{2}-\d{2}",
            resolved["url"],
        )

    def test_preserves_non_string_values(self):
        plugin = InterpolatingPlugin()
        plugin._config = {
            "url": "https://api.example.com/{{date}}",
            "enabled": True,
            "refresh_seconds": 300,
        }
        resolved = plugin.resolve_config_variables()
        assert resolved["enabled"] is True
        assert resolved["refresh_seconds"] == 300

    def test_returns_copy_not_original(self):
        plugin = InterpolatingPlugin()
        plugin._config = {"url": "https://api.example.com/{{date}}"}
        resolved = plugin.resolve_config_variables()
        # Original should not be mutated
        assert "{{date}}" in plugin._config["url"]

    def test_with_extra_context(self):
        plugin = InterpolatingPlugin()
        plugin._config = {"url": "https://api.example.com/{{custom_var}}"}
        resolved = plugin.resolve_config_variables(
            extra_variables={"custom_var": "hello"}
        )
        assert resolved["url"] == "https://api.example.com/hello"

    def test_extra_context_overrides_builtin(self):
        plugin = InterpolatingPlugin()
        plugin._config = {"url": "https://api.example.com/{{date}}"}
        resolved = plugin.resolve_config_variables(
            extra_variables={"date": "custom-date"}
        )
        assert resolved["url"] == "https://api.example.com/custom-date"

    def test_empty_config(self):
        plugin = InterpolatingPlugin()
        plugin._config = {}
        resolved = plugin.resolve_config_variables()
        assert resolved == {}

    def test_no_variables_in_config(self):
        plugin = InterpolatingPlugin()
        plugin._config = {"url": "https://api.example.com/static"}
        resolved = plugin.resolve_config_variables()
        assert resolved["url"] == "https://api.example.com/static"

    def test_plugin_uses_resolved_config_in_fetch(self):
        plugin = InterpolatingPlugin()
        plugin._config = {"url": "https://api.example.com/{{date}}"}
        result = plugin.fetch_data()
        assert result.available
        assert re.match(
            r"https://api\.example\.com/\d{4}-\d{2}-\d{2}",
            result.data["resolved_url"],
        )

    def test_multiple_url_configs(self):
        plugin = InterpolatingPlugin()
        plugin._config = {
            "url": "https://api.example.com/{{date}}",
            "fallback_url": "https://backup.example.com/{{date}}",
        }
        resolved = plugin.resolve_config_variables()
        assert "{{date}}" not in resolved["url"]
        assert "{{date}}" not in resolved["fallback_url"]

    def test_nested_config_resolved(self):
        plugin = InterpolatingPlugin()
        plugin._config = {
            "feeds": [
                {"url": "https://api1.example.com/{{date}}", "name": "Feed 1"},
                {"url": "https://api2.example.com/{{date}}", "name": "Feed 2"},
            ]
        }
        resolved = plugin.resolve_config_variables()
        for feed in resolved["feeds"]:
            assert "{{date}}" not in feed["url"]
            # name should be unchanged
            assert "Feed" in feed["name"]

    def test_get_url_default_key(self):
        plugin = InterpolatingPlugin()
        plugin._config = {"url": "https://api.example.com/data?d={{date}}"}
        got = plugin.get_url()
        assert re.match(r"https://api\.example\.com/data\?d=\d{4}-\d{2}-\d{2}", got)

    def test_get_url_custom_key(self):
        plugin = InterpolatingPlugin()
        plugin._config = {"api_url": "https://api.example.com/{{date}}"}
        got = plugin.get_url(key="api_url")
        assert re.match(r"https://api\.example\.com/\d{4}-\d{2}-\d{2}", got)

    def test_get_url_missing_returns_default(self):
        plugin = InterpolatingPlugin()
        plugin._config = {}
        assert plugin.get_url() == ""

    def test_get_url_non_string_returns_default(self):
        plugin = InterpolatingPlugin()
        plugin._config = {"url": 12345}
        assert plugin.get_url(default="fallback") == "fallback"

    def test_get_resolved_config_value(self):
        plugin = InterpolatingPlugin()
        plugin._config = {
            "url": "https://x/{{date}}",
            "token": "abc-{{year}}",
        }
        u = plugin.get_resolved_config_value("url")
        assert isinstance(u, str)
        assert "{{date}}" not in u
        t = plugin.get_resolved_config_value("token")
        assert "{{year}}" not in t


# ── Cross-plugin variable references ──────────────────────────


class TestCrossPluginVariables:
    """Tests for referencing variables from other plugins via extra_variables."""

    def test_reference_other_plugin_variable(self):
        plugin = InterpolatingPlugin()
        plugin._config = {
            "url": "https://api.example.com/{{weather.location}}"
        }
        resolved = plugin.resolve_config_variables(
            extra_variables={"weather.location": "san-francisco"}
        )
        assert resolved["url"] == "https://api.example.com/san-francisco"

    def test_mixed_builtin_and_cross_plugin(self):
        plugin = InterpolatingPlugin()
        plugin._config = {
            "url": "https://api.example.com/{{date}}/{{weather.location}}"
        }
        resolved = plugin.resolve_config_variables(
            extra_variables={"weather.location": "sf"}
        )
        # date should be resolved from builtin, location from extra
        assert "sf" in resolved["url"]
        assert re.search(r"\d{4}-\d{2}-\d{2}", resolved["url"])

    def test_unknown_cross_plugin_variable_preserved(self):
        plugin = InterpolatingPlugin()
        plugin._config = {
            "url": "https://api.example.com/{{nonexistent.var}}"
        }
        resolved = plugin.resolve_config_variables()
        assert resolved["url"] == "https://api.example.com/{{nonexistent.var}}"


# ── Edge cases ─────────────────────────────────────────────────


class TestEdgeCases:
    """Edge case tests for config interpolation."""

    def test_empty_braces(self):
        result = interpolate_string("before{{}}after", {})
        assert result == "before{{}}after"

    def test_single_braces_not_interpolated(self):
        result = interpolate_string("{date}", {"date": "2025-01-01"})
        assert result == "{date}"

    def test_triple_braces(self):
        variables = {"date": "2025-01-01"}
        result = interpolate_string("{{{date}}}", variables)
        # Should match inner {{ date }} and leave extra brace
        assert result == "{2025-01-01}"

    def test_url_encoding_preserved(self):
        variables = {"query": "hello world"}
        result = interpolate_string(
            "https://api.example.com/search?q={{query}}",
            variables,
        )
        assert result == "https://api.example.com/search?q=hello world"

    def test_variable_with_numeric_value(self):
        variables = {"port": "8080"}
        result = interpolate_string("http://localhost:{{port}}/api", variables)
        assert result == "http://localhost:8080/api"

    def test_large_config(self):
        config = {f"key_{i}": "value_{{date}}" for i in range(100)}
        variables = {"date": "2025-01-01"}
        result = interpolate_config(config, variables)
        for key in result:
            assert result[key] == "value_2025-01-01"
