"""Tests for post-upgrade config auto-restore (#1102 / #948)."""

from src.api_server import _build_post_upgrade_restore_set


def test_restore_set_recovers_timezone_lost_to_default():
    snap = {"general": {"timezone": "America/New_York", "instance_name": "Kitchen"}}
    live = {"general": {"timezone": "America/Los_Angeles", "instance_name": ""}}
    result = _build_post_upgrade_restore_set(snap, live)
    assert result["general"]["timezone"] == "America/New_York"
    assert result["general"]["instance_name"] == "Kitchen"


def test_restore_set_ignores_unchanged_general():
    snap = {"general": {"timezone": "America/New_York", "instance_name": "Kitchen"}}
    live = {"general": {"timezone": "America/New_York", "instance_name": "Kitchen"}}
    result = _build_post_upgrade_restore_set(snap, live)
    assert "general" not in result


def test_restore_set_recovers_disabled_enabled_plugin_with_secrets():
    snap = {"plugins": {"weather": {"enabled": True, "api_key": "real-key", "location": "NYC"}}}
    live = {"plugins": {"weather": {"enabled": False}}}
    result = _build_post_upgrade_restore_set(snap, live)
    assert result["plugins"]["weather"] == snap["plugins"]["weather"]


def test_restore_set_recovers_missing_enabled_plugin():
    snap = {"plugins": {"stocks": {"enabled": True, "finnhub_api_key": "k"}}}
    live = {"plugins": {}}
    result = _build_post_upgrade_restore_set(snap, live)
    assert "stocks" in result["plugins"]


def test_restore_set_recovers_plugin_that_lost_only_its_secret():
    snap = {"plugins": {"weather": {"enabled": True, "openweathermap_api_key": "real"}}}
    live = {"plugins": {"weather": {"enabled": True, "openweathermap_api_key": ""}}}
    result = _build_post_upgrade_restore_set(snap, live)
    assert result["plugins"]["weather"]["openweathermap_api_key"] == "real"


def test_restore_set_does_not_resurrect_disabled_plugin():
    # User deliberately disabled it under the old version -> snapshot has enabled False.
    snap = {"plugins": {"weather": {"enabled": False, "api_key": "real-key"}}}
    live = {"plugins": {}}
    result = _build_post_upgrade_restore_set(snap, live)
    assert result.get("plugins", {}) == {}


def test_restore_set_empty_when_nothing_regressed():
    snap = {"general": {"timezone": "America/New_York"}, "plugins": {"weather": {"enabled": True}}}
    live = {"general": {"timezone": "America/New_York"}, "plugins": {"weather": {"enabled": True}}}
    assert _build_post_upgrade_restore_set(snap, live) == {}
