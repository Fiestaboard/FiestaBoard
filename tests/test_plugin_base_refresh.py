"""Tests for PluginBase generic refresh interval and caching support."""

from datetime import datetime, timedelta

from src.plugins.base import (
    DEFAULT_REFRESH_SECONDS,
    MIN_REFRESH_SECONDS,
    PluginBase,
    PluginResult,
)

MANIFEST_WITH_REFRESH = {
    "id": "test_plugin",
    "name": "Test Plugin",
    "version": "1.0.0",
    "min_refresh_seconds": 30,
    "settings_schema": {
        "type": "object",
        "properties": {
            "refresh_seconds": {
                "type": "integer",
                "default": 120,
                "minimum": 30,
                "maximum": 600,
            }
        },
    },
}

MANIFEST_WITH_HIGH_FLOOR = {
    "id": "test_plugin",
    "name": "Test Plugin",
    "version": "1.0.0",
    "min_refresh_seconds": 240,
    "settings_schema": {
        "type": "object",
        "properties": {
            "refresh_seconds": {
                "type": "integer",
                "default": 300,
                "minimum": 240,
                "maximum": 3600,
            }
        },
    },
}

MANIFEST_WITHOUT_REFRESH = {
    "id": "test_plugin",
    "name": "Test Plugin",
    "version": "1.0.0",
    "settings_schema": {
        "type": "object",
        "properties": {"enabled": {"type": "boolean", "default": False}},
    },
}

MANIFEST_BARE = {
    "id": "test_plugin",
    "name": "Test Plugin",
    "version": "1.0.0",
}

MANIFEST_LIVE_DATA = {
    "id": "test_plugin",
    "name": "Test Plugin",
    "version": "1.0.0",
    "live_data": True,
}

MANIFEST_LIVE_DATA_WITH_SCHEMA = {
    "id": "test_plugin",
    "name": "Test Plugin",
    "version": "1.0.0",
    "live_data": True,
    "settings_schema": {
        "type": "object",
        "properties": {
            "refresh_seconds": {"type": "integer", "default": 120, "minimum": 30},
        },
    },
}


class ConcretePlugin(PluginBase):
    """Concrete plugin for testing base class behavior."""

    def __init__(self, manifest, fetch_fn=None):
        super().__init__(manifest)
        self._fetch_fn = fetch_fn
        self.fetch_call_count = 0

    @property
    def plugin_id(self) -> str:
        return "test_plugin"

    def fetch_data(self) -> PluginResult:
        self.fetch_call_count += 1
        if self._fetch_fn:
            return self._fetch_fn()
        return PluginResult(available=True, data={"value": self.fetch_call_count})


class FailingPlugin(PluginBase):
    """Plugin that always fails to fetch data."""

    @property
    def plugin_id(self) -> str:
        return "failing_plugin"

    def fetch_data(self) -> PluginResult:
        return PluginResult(available=False, error="always fails")


# --- live_data property ---


class TestLiveDataProperty:
    def test_defaults_to_false(self):
        plugin = ConcretePlugin(MANIFEST_BARE)
        assert plugin.live_data is False

    def test_false_when_not_declared(self):
        plugin = ConcretePlugin(MANIFEST_WITH_REFRESH)
        assert plugin.live_data is False

    def test_true_when_manifest_opts_in(self):
        plugin = ConcretePlugin(MANIFEST_LIVE_DATA)
        assert plugin.live_data is True

    def test_explicit_false(self):
        manifest = {**MANIFEST_BARE, "live_data": False}
        plugin = ConcretePlugin(manifest)
        assert plugin.live_data is False


# --- _get_refresh_schema ---


class TestGetRefreshSchema:
    def test_returns_schema_when_present(self):
        plugin = ConcretePlugin(MANIFEST_WITH_REFRESH)
        schema = plugin._get_refresh_schema()
        assert schema is not None
        assert schema["default"] == 120
        assert schema["minimum"] == 30
        assert schema["maximum"] == 600

    def test_returns_none_when_absent(self):
        plugin = ConcretePlugin(MANIFEST_WITHOUT_REFRESH)
        assert plugin._get_refresh_schema() is None

    def test_returns_none_for_bare_manifest(self):
        plugin = ConcretePlugin(MANIFEST_BARE)
        assert plugin._get_refresh_schema() is None


# --- refresh_seconds property ---


class TestRefreshSecondsProperty:
    def test_returns_manifest_default_when_no_config(self):
        plugin = ConcretePlugin(MANIFEST_WITH_REFRESH)
        assert plugin.refresh_seconds == 120

    def test_returns_configured_value(self):
        plugin = ConcretePlugin(MANIFEST_WITH_REFRESH)
        plugin._config = {"refresh_seconds": 60}
        assert plugin.refresh_seconds == 60

    def test_defaults_to_300s_without_schema(self):
        """Plugins without a refresh_seconds schema get a safe 5-minute cache by default.

        Before this fix the property returned ``None`` (meaning "no cache"),
        which caused random-data plugins like Star Trek Quotes to re-fetch
        on every poll tick and flip the board every ~14 seconds.
        """
        plugin = ConcretePlugin(MANIFEST_WITHOUT_REFRESH)
        assert plugin.refresh_seconds == DEFAULT_REFRESH_SECONDS

    def test_defaults_to_300s_for_bare_manifest(self):
        plugin = ConcretePlugin(MANIFEST_BARE)
        assert plugin.refresh_seconds == DEFAULT_REFRESH_SECONDS

    def test_returns_none_when_live_data_true(self):
        """``live_data: true`` opts out of caching and signals "always fresh"."""
        plugin = ConcretePlugin(MANIFEST_LIVE_DATA)
        assert plugin.refresh_seconds is None

    def test_live_data_overrides_explicit_schema(self):
        """``live_data: true`` wins even when refresh_seconds is declared in the schema."""
        plugin = ConcretePlugin(MANIFEST_LIVE_DATA_WITH_SCHEMA)
        assert plugin.refresh_seconds is None

    def test_falls_back_to_global_default_when_schema_missing_default(self):
        manifest = {
            "id": "test_plugin",
            "name": "Test",
            "version": "1.0.0",
            "settings_schema": {
                "type": "object",
                "properties": {"refresh_seconds": {"type": "integer", "minimum": 10}},
            },
        }
        plugin = ConcretePlugin(manifest)
        assert plugin.refresh_seconds == DEFAULT_REFRESH_SECONDS


# --- get_data caching ---


class TestGetDataCaching:
    def test_caches_successful_result(self):
        plugin = ConcretePlugin(MANIFEST_WITH_REFRESH)
        plugin._config = {"refresh_seconds": 300}

        result1 = plugin.get_data()
        result2 = plugin.get_data()

        assert result1.data == {"value": 1}
        assert result2.data == {"value": 1}
        assert plugin.fetch_call_count == 1

    def test_refreshes_after_expiry(self):
        plugin = ConcretePlugin(MANIFEST_WITH_REFRESH)
        plugin._config = {"refresh_seconds": 60}

        plugin.get_data()
        assert plugin.fetch_call_count == 1

        plugin._last_fetch_time = datetime.now() - timedelta(seconds=120)
        plugin.get_data()
        assert plugin.fetch_call_count == 2

    def test_caches_with_default_300s_when_no_schema(self):
        """Plugins without a refresh_seconds schema should still cache.

        Regression test for the board-flipping bug: previously a plugin
        with no ``refresh_seconds`` in its manifest fell through to
        ``fetch_data()`` on every call, causing random-data plugins to
        pick a fresh value every poll tick.
        """
        plugin = ConcretePlugin(MANIFEST_WITHOUT_REFRESH)

        plugin.get_data()
        plugin.get_data()
        assert plugin.fetch_call_count == 1

    def test_caches_with_default_300s_for_bare_manifest(self):
        plugin = ConcretePlugin(MANIFEST_BARE)

        plugin.get_data()
        plugin.get_data()
        assert plugin.fetch_call_count == 1

    def test_default_cache_expires_after_300s(self):
        plugin = ConcretePlugin(MANIFEST_BARE)

        plugin.get_data()
        assert plugin.fetch_call_count == 1

        plugin._last_fetch_time = datetime.now() - timedelta(seconds=DEFAULT_REFRESH_SECONDS + 1)
        plugin.get_data()
        assert plugin.fetch_call_count == 2

    def test_live_data_skips_cache_entirely(self):
        """``live_data: true`` calls ``fetch_data()`` every time."""
        plugin = ConcretePlugin(MANIFEST_LIVE_DATA)

        plugin.get_data()
        plugin.get_data()
        plugin.get_data()
        assert plugin.fetch_call_count == 3

    def test_live_data_does_not_populate_cache(self):
        plugin = ConcretePlugin(MANIFEST_LIVE_DATA)

        plugin.get_data()
        assert plugin._cached_result is None
        assert plugin._last_fetch_time is None

    def test_does_not_cache_failed_result(self):
        plugin = FailingPlugin(MANIFEST_WITH_REFRESH)
        plugin._config = {"refresh_seconds": 300}

        result1 = plugin.get_data()
        result2 = plugin.get_data()

        assert not result1.available
        assert not result2.available
        assert plugin._cached_result is None

    def test_uses_manifest_default_refresh(self):
        plugin = ConcretePlugin(MANIFEST_WITH_REFRESH)

        plugin.get_data()
        assert plugin.fetch_call_count == 1

        plugin.get_data()
        assert plugin.fetch_call_count == 1

    def test_returns_cached_before_interval(self):
        plugin = ConcretePlugin(MANIFEST_WITH_REFRESH)
        plugin._config = {"refresh_seconds": 300}

        plugin.get_data()
        plugin._last_fetch_time = datetime.now() - timedelta(seconds=100)

        result = plugin.get_data()
        assert plugin.fetch_call_count == 1
        assert result.data == {"value": 1}


# --- clear_cache ---


class TestClearCache:
    def test_forces_refetch(self):
        plugin = ConcretePlugin(MANIFEST_WITH_REFRESH)
        plugin._config = {"refresh_seconds": 300}

        plugin.get_data()
        assert plugin.fetch_call_count == 1

        plugin.clear_cache()

        plugin.get_data()
        assert plugin.fetch_call_count == 2

    def test_clears_both_fields(self):
        plugin = ConcretePlugin(MANIFEST_WITH_REFRESH)
        plugin.get_data()

        assert plugin._cached_result is not None
        assert plugin._last_fetch_time is not None

        plugin.clear_cache()

        assert plugin._cached_result is None
        assert plugin._last_fetch_time is None


# --- config change clears cache ---


class TestConfigChangeClearsCache:
    def test_setting_new_config_clears_cache(self):
        plugin = ConcretePlugin(MANIFEST_WITH_REFRESH)
        plugin._config = {"refresh_seconds": 300}

        plugin.get_data()
        assert plugin.fetch_call_count == 1

        plugin.config = {"refresh_seconds": 120}

        plugin.get_data()
        assert plugin.fetch_call_count == 2

    def test_setting_same_config_preserves_cache(self):
        plugin = ConcretePlugin(MANIFEST_WITH_REFRESH)
        plugin._config = {"refresh_seconds": 300}

        plugin.get_data()
        assert plugin.fetch_call_count == 1

        plugin.config = {"refresh_seconds": 300}

        plugin.get_data()
        assert plugin.fetch_call_count == 1


# --- disable clears cache ---


class TestDisableClearsCache:
    def test_disabling_clears_cache(self):
        plugin = ConcretePlugin(MANIFEST_WITH_REFRESH)
        plugin._config = {"refresh_seconds": 300}
        plugin.enabled = True

        plugin.get_data()
        assert plugin.fetch_call_count == 1

        plugin.enabled = False
        assert plugin._cached_result is None

        plugin.enabled = True
        plugin.get_data()
        assert plugin.fetch_call_count == 2


# --- _validate_refresh_seconds ---


class TestValidateRefreshSeconds:
    def test_valid_value(self):
        plugin = ConcretePlugin(MANIFEST_WITH_REFRESH)
        assert plugin._validate_refresh_seconds({"refresh_seconds": 120}) == []

    def test_at_minimum(self):
        plugin = ConcretePlugin(MANIFEST_WITH_REFRESH)
        assert plugin._validate_refresh_seconds({"refresh_seconds": 30}) == []

    def test_at_maximum(self):
        plugin = ConcretePlugin(MANIFEST_WITH_REFRESH)
        assert plugin._validate_refresh_seconds({"refresh_seconds": 600}) == []

    def test_below_minimum(self):
        plugin = ConcretePlugin(MANIFEST_WITH_REFRESH)
        errors = plugin._validate_refresh_seconds({"refresh_seconds": 10})
        assert len(errors) == 1
        assert "at least 30 seconds" in errors[0]

    def test_above_maximum(self):
        plugin = ConcretePlugin(MANIFEST_WITH_REFRESH)
        errors = plugin._validate_refresh_seconds({"refresh_seconds": 1000})
        assert len(errors) == 1
        assert "must not exceed 600 seconds" in errors[0]

    def test_non_numeric(self):
        plugin = ConcretePlugin(MANIFEST_WITH_REFRESH)
        errors = plugin._validate_refresh_seconds({"refresh_seconds": "fast"})
        assert len(errors) == 1
        assert "must be a number" in errors[0]

    def test_missing_key_is_ok(self):
        plugin = ConcretePlugin(MANIFEST_WITH_REFRESH)
        assert plugin._validate_refresh_seconds({}) == []

    def test_no_schema_skips_validation(self):
        plugin = ConcretePlugin(MANIFEST_WITHOUT_REFRESH)
        assert plugin._validate_refresh_seconds({"refresh_seconds": 1}) == []

    def test_bare_manifest_skips_validation(self):
        plugin = ConcretePlugin(MANIFEST_BARE)
        assert plugin._validate_refresh_seconds({"refresh_seconds": 1}) == []

    def test_uses_global_defaults_when_schema_omits_bounds(self):
        manifest = {
            "id": "test_plugin",
            "name": "Test",
            "version": "1.0.0",
            "settings_schema": {
                "type": "object",
                "properties": {"refresh_seconds": {"type": "integer"}},
            },
        }
        plugin = ConcretePlugin(manifest)
        assert plugin._validate_refresh_seconds({"refresh_seconds": MIN_REFRESH_SECONDS}) == []
        errors = plugin._validate_refresh_seconds({"refresh_seconds": MIN_REFRESH_SECONDS - 1})
        assert len(errors) == 1

    def test_float_value_accepted(self):
        plugin = ConcretePlugin(MANIFEST_WITH_REFRESH)
        assert plugin._validate_refresh_seconds({"refresh_seconds": 120.0}) == []

    def test_uses_explicit_min_refresh_seconds_as_floor(self):
        plugin = ConcretePlugin(MANIFEST_WITH_HIGH_FLOOR)
        errors = plugin._validate_refresh_seconds({"refresh_seconds": 100})
        assert len(errors) == 1
        assert "at least 240 seconds" in errors[0]

    def test_accepts_value_at_explicit_floor(self):
        plugin = ConcretePlugin(MANIFEST_WITH_HIGH_FLOOR)
        assert plugin._validate_refresh_seconds({"refresh_seconds": 240}) == []


# --- min_refresh_seconds property ---


class TestMinRefreshSecondsProperty:
    def test_returns_explicit_manifest_value(self):
        plugin = ConcretePlugin(MANIFEST_WITH_HIGH_FLOOR)
        assert plugin.min_refresh_seconds == 240

    def test_falls_back_to_schema_minimum(self):
        manifest = {
            "id": "test_plugin",
            "name": "Test",
            "version": "1.0.0",
            "settings_schema": {
                "type": "object",
                "properties": {"refresh_seconds": {"type": "integer", "minimum": 60}},
            },
        }
        plugin = ConcretePlugin(manifest)
        assert plugin.min_refresh_seconds == 60

    def test_falls_back_to_global_minimum(self):
        manifest = {
            "id": "test_plugin",
            "name": "Test",
            "version": "1.0.0",
            "settings_schema": {
                "type": "object",
                "properties": {"refresh_seconds": {"type": "integer"}},
            },
        }
        plugin = ConcretePlugin(manifest)
        assert plugin.min_refresh_seconds == MIN_REFRESH_SECONDS

    def test_returns_none_without_refresh_schema(self):
        plugin = ConcretePlugin(MANIFEST_WITHOUT_REFRESH)
        assert plugin.min_refresh_seconds is None

    def test_explicit_overrides_schema_minimum(self):
        manifest = {
            "id": "test_plugin",
            "name": "Test",
            "version": "1.0.0",
            "min_refresh_seconds": 120,
            "settings_schema": {
                "type": "object",
                "properties": {"refresh_seconds": {"type": "integer", "minimum": 60}},
            },
        }
        plugin = ConcretePlugin(manifest)
        assert plugin.min_refresh_seconds == 120


# --- runtime clamping ---


class TestRuntimeClamping:
    def test_clamps_below_floor(self):
        plugin = ConcretePlugin(MANIFEST_WITH_HIGH_FLOOR)
        plugin._config = {"refresh_seconds": 10}
        assert plugin.refresh_seconds == 240

    def test_does_not_clamp_valid_value(self):
        plugin = ConcretePlugin(MANIFEST_WITH_HIGH_FLOOR)
        plugin._config = {"refresh_seconds": 300}
        assert plugin.refresh_seconds == 300

    def test_clamps_at_boundary(self):
        plugin = ConcretePlugin(MANIFEST_WITH_HIGH_FLOOR)
        plugin._config = {"refresh_seconds": 239}
        assert plugin.refresh_seconds == 240

    def test_exact_floor_not_clamped(self):
        plugin = ConcretePlugin(MANIFEST_WITH_HIGH_FLOOR)
        plugin._config = {"refresh_seconds": 240}
        assert plugin.refresh_seconds == 240

    def test_clamping_prevents_fast_polling(self):
        """Even if config bypasses validation, runtime enforces the floor."""
        plugin = ConcretePlugin(MANIFEST_WITH_HIGH_FLOOR)
        plugin._config = {"refresh_seconds": 1}

        plugin.get_data()
        assert plugin.fetch_call_count == 1

        plugin.get_data()
        assert plugin.fetch_call_count == 1

    def test_no_clamping_without_floor(self):
        """When the manifest declares no refresh_seconds schema there's no floor
        to clamp against, but the property now returns the safe 300s default
        rather than None (and ignores stray config values for refresh_seconds
        since the schema doesn't acknowledge the field).
        """
        plugin = ConcretePlugin(MANIFEST_WITHOUT_REFRESH)
        plugin._config = {"refresh_seconds": 1}
        assert plugin.refresh_seconds == DEFAULT_REFRESH_SECONDS
