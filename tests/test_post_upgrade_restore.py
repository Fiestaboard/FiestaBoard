"""Tests for post-upgrade config auto-restore (#1102 / #948)."""

import json
from unittest.mock import MagicMock

import src.api_server as api_server
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


def _seed_snapshot(tmp_path, config_payload):
    snap = tmp_path / "pre-update-20260101T000000.000Z.json"
    snap.write_text(json.dumps({"data": {"config": config_payload}}))
    return snap


def test_auto_restore_applies_general_and_plugins(tmp_path, monkeypatch):
    snap_path = _seed_snapshot(
        tmp_path,
        {
            "general": {"timezone": "America/New_York", "instance_name": "Kitchen"},
            "plugins": {"weather": {"enabled": True, "api_key": "real"}},
        },
    )
    cm = MagicMock()
    cm.version_changed_on_load = True
    cm.get_all.return_value = {
        "general": {"timezone": "America/Los_Angeles", "instance_name": ""},
        "plugins": {"weather": {"enabled": False}},
    }
    monkeypatch.setattr(api_server, "get_config_manager", lambda: cm)
    monkeypatch.setattr(api_server, "_resolve_snapshot_name", lambda name=None: snap_path)
    reset_called = MagicMock()
    monkeypatch.setattr(api_server, "reset_time_service", reset_called)
    monkeypatch.delenv("FIESTABOARD_AUTO_RESTORE", raising=False)

    summary = api_server._auto_restore_post_upgrade_regression()

    cm.set_general.assert_called_once()
    assert cm.set_general.call_args[0][0] == {
        "timezone": "America/New_York",
        "instance_name": "Kitchen",
    }
    cm.set_plugin_config.assert_called_once_with("weather", {"enabled": True, "api_key": "real"})
    reset_called.assert_called_once()
    # summary lists are sorted() -> alphabetical
    assert summary == {"general": ["instance_name", "timezone"], "plugins": ["weather"]}


def test_auto_restore_noop_when_not_version_change(tmp_path, monkeypatch):
    cm = MagicMock()
    cm.version_changed_on_load = False
    monkeypatch.setattr(api_server, "get_config_manager", lambda: cm)
    monkeypatch.delenv("FIESTABOARD_AUTO_RESTORE", raising=False)
    assert api_server._auto_restore_post_upgrade_regression() == {}
    cm.set_general.assert_not_called()


def test_auto_restore_noop_when_disabled_by_env(tmp_path, monkeypatch):
    cm = MagicMock()
    cm.version_changed_on_load = True
    monkeypatch.setattr(api_server, "get_config_manager", lambda: cm)
    monkeypatch.setenv("FIESTABOARD_AUTO_RESTORE", "0")
    assert api_server._auto_restore_post_upgrade_regression() == {}
    cm.set_general.assert_not_called()


def test_auto_restore_noop_when_nothing_regressed(tmp_path, monkeypatch):
    snap_path = _seed_snapshot(tmp_path, {"general": {"timezone": "America/New_York"}, "plugins": {}})
    cm = MagicMock()
    cm.version_changed_on_load = True
    cm.get_all.return_value = {"general": {"timezone": "America/New_York"}, "plugins": {}}
    monkeypatch.setattr(api_server, "get_config_manager", lambda: cm)
    monkeypatch.setattr(api_server, "_resolve_snapshot_name", lambda name=None: snap_path)
    monkeypatch.setattr(api_server, "reset_time_service", MagicMock())
    monkeypatch.delenv("FIESTABOARD_AUTO_RESTORE", raising=False)
    assert api_server._auto_restore_post_upgrade_regression() == {}
    cm.set_general.assert_not_called()
