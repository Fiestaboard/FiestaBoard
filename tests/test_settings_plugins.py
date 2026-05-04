"""Tests for plugin settings: /settings/plugins endpoints and auto-apply logic."""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api_server import _auto_apply_plugin_updates, app
from src.settings.service import PluginSettings, get_settings_service

client = TestClient(app)


def _reset_plugin_settings():
    """Reset plugin settings to defaults between tests."""
    get_settings_service().update_plugin_settings({"auto_update": True})


# ---------------------------------------------------------------------------
# PluginSettings dataclass
# ---------------------------------------------------------------------------

class TestPluginSettingsDataclass:
    def test_defaults(self):
        s = PluginSettings()
        assert s.auto_update is True

    def test_to_dict(self):
        s = PluginSettings(auto_update=False)
        assert s.to_dict() == {"auto_update": False}

    def test_from_dict_explicit_false(self):
        s = PluginSettings.from_dict({"auto_update": False})
        assert s.auto_update is False

    def test_from_dict_explicit_true(self):
        s = PluginSettings.from_dict({"auto_update": True})
        assert s.auto_update is True

    def test_from_dict_missing_key_defaults_to_true(self):
        s = PluginSettings.from_dict({})
        assert s.auto_update is True

    def test_from_dict_coerces_truthy(self):
        s = PluginSettings.from_dict({"auto_update": 1})
        assert s.auto_update is True

    def test_from_dict_coerces_falsy(self):
        s = PluginSettings.from_dict({"auto_update": 0})
        assert s.auto_update is False


# ---------------------------------------------------------------------------
# GET /settings/plugins
# ---------------------------------------------------------------------------

class TestGetPluginSettings:
    def setup_method(self):
        _reset_plugin_settings()

    def test_returns_200(self):
        response = client.get("/settings/plugins")
        assert response.status_code == 200

    def test_default_auto_update_is_true(self):
        response = client.get("/settings/plugins")
        body = response.json()
        assert "settings" in body
        assert body["settings"]["auto_update"] is True

    def test_reflects_disabled_state(self):
        get_settings_service().update_plugin_settings({"auto_update": False})
        response = client.get("/settings/plugins")
        assert response.json()["settings"]["auto_update"] is False


# ---------------------------------------------------------------------------
# PUT /settings/plugins
# ---------------------------------------------------------------------------

class TestPutPluginSettings:
    def setup_method(self):
        _reset_plugin_settings()

    def test_disable_auto_update(self):
        response = client.put("/settings/plugins", json={"auto_update": False})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["settings"]["auto_update"] is False

    def test_enable_auto_update(self):
        get_settings_service().update_plugin_settings({"auto_update": False})
        response = client.put("/settings/plugins", json={"auto_update": True})
        assert response.status_code == 200
        assert response.json()["settings"]["auto_update"] is True

    def test_persisted_across_get(self):
        client.put("/settings/plugins", json={"auto_update": False})
        response = client.get("/settings/plugins")
        assert response.json()["settings"]["auto_update"] is False

    def test_empty_body_does_not_error(self):
        response = client.put("/settings/plugins", json={})
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# /settings/all includes plugins section
# ---------------------------------------------------------------------------

def test_settings_all_includes_plugins_section():
    _reset_plugin_settings()
    response = client.get("/settings/all")
    assert response.status_code == 200
    data = response.json()
    assert "plugins" in data
    assert "auto_update" in data["plugins"]

def test_settings_all_plugins_consistent_with_dedicated_endpoint():
    _reset_plugin_settings()
    all_data = client.get("/settings/all").json()
    plugin_data = client.get("/settings/plugins").json()
    assert all_data["plugins"]["auto_update"] == plugin_data["settings"]["auto_update"]


# ---------------------------------------------------------------------------
# _auto_apply_plugin_updates helper
# ---------------------------------------------------------------------------

def _make_registry(plugin_ids, local_path_exists=True, has_git=True):
    """Build a minimal mock registry for _auto_apply_plugin_updates tests."""
    registry = MagicMock()

    def get_source(pid):
        source = MagicMock()
        source.local_path = f"/fake/external_plugins/{pid}" if local_path_exists else None
        return source

    registry.get_plugin_source.side_effect = get_source

    def reload(pid):
        return MagicMock()

    registry.reload_plugin.side_effect = reload
    registry._update_status = {pid: True for pid in plugin_ids}
    return registry


def test_auto_apply_updates_external_plugin(tmp_path):
    plugin_id = "my_plugin"
    plugin_dir = tmp_path / plugin_id
    plugin_dir.mkdir()
    (plugin_dir / ".git").mkdir()

    registry = MagicMock()
    source = MagicMock()
    source.local_path = str(plugin_dir)
    registry.get_plugin_source.return_value = source
    registry.reload_plugin.return_value = MagicMock()
    registry._update_status = {plugin_id: True}

    with patch("src.plugins.sources.get_external_plugins_dir", return_value=tmp_path), \
         patch("src.plugins.sources.clone_or_update_repo", return_value=(True, "")) as mock_clone:
        asyncio.run(_auto_apply_plugin_updates(registry, [plugin_id]))

    mock_clone.assert_called_once_with("", plugin_id, external_dir=tmp_path)
    registry.reload_plugin.assert_called_once_with(plugin_id)
    assert plugin_id not in registry._update_status


def test_auto_apply_skips_plugin_with_no_source(tmp_path):
    registry = MagicMock()
    registry.get_plugin_source.return_value = None
    registry._update_status = {"ghost": True}

    with patch("src.plugins.sources.get_external_plugins_dir", return_value=tmp_path):
        asyncio.run(_auto_apply_plugin_updates(registry, ["ghost"]))

    registry.reload_plugin.assert_not_called()


def test_auto_apply_skips_plugin_outside_external_dir(tmp_path):
    plugin_id = "escape_plugin"
    outside_dir = tmp_path.parent / "outside"
    outside_dir.mkdir(exist_ok=True)
    (outside_dir / ".git").mkdir()

    registry = MagicMock()
    source = MagicMock()
    source.local_path = str(outside_dir)
    registry.get_plugin_source.return_value = source
    registry._update_status = {plugin_id: True}

    with patch("src.plugins.sources.get_external_plugins_dir", return_value=tmp_path):
        asyncio.run(_auto_apply_plugin_updates(registry, [plugin_id]))

    registry.reload_plugin.assert_not_called()


def test_auto_apply_skips_plugin_without_git_dir(tmp_path):
    plugin_id = "no_git"
    plugin_dir = tmp_path / plugin_id
    plugin_dir.mkdir()
    # No .git directory

    registry = MagicMock()
    source = MagicMock()
    source.local_path = str(plugin_dir)
    registry.get_plugin_source.return_value = source
    registry._update_status = {plugin_id: True}

    with patch("src.plugins.sources.get_external_plugins_dir", return_value=tmp_path):
        asyncio.run(_auto_apply_plugin_updates(registry, [plugin_id]))

    registry.reload_plugin.assert_not_called()


def test_auto_apply_handles_git_fetch_failure(tmp_path):
    plugin_id = "bad_fetch"
    plugin_dir = tmp_path / plugin_id
    plugin_dir.mkdir()
    (plugin_dir / ".git").mkdir()

    registry = MagicMock()
    source = MagicMock()
    source.local_path = str(plugin_dir)
    registry.get_plugin_source.return_value = source
    registry._update_status = {plugin_id: True}

    with patch("src.plugins.sources.get_external_plugins_dir", return_value=tmp_path), \
         patch("src.plugins.sources.clone_or_update_repo", return_value=(False, "network error")):
        asyncio.run(_auto_apply_plugin_updates(registry, [plugin_id]))

    registry.reload_plugin.assert_not_called()
    assert registry._update_status[plugin_id] is True


def test_auto_apply_handles_reload_failure(tmp_path):
    plugin_id = "bad_reload"
    plugin_dir = tmp_path / plugin_id
    plugin_dir.mkdir()
    (plugin_dir / ".git").mkdir()

    registry = MagicMock()
    source = MagicMock()
    source.local_path = str(plugin_dir)
    registry.get_plugin_source.return_value = source
    registry.reload_plugin.return_value = None  # reload failed
    registry._update_status = {plugin_id: True}

    with patch("src.plugins.sources.get_external_plugins_dir", return_value=tmp_path), \
         patch("src.plugins.sources.clone_or_update_repo", return_value=(True, "")):
        asyncio.run(_auto_apply_plugin_updates(registry, [plugin_id]))

    assert registry._update_status[plugin_id] is True


def test_auto_apply_multiple_plugins_partial_success(tmp_path):
    good_id = "good_plugin"
    bad_id = "bad_plugin"

    good_dir = tmp_path / good_id
    good_dir.mkdir()
    (good_dir / ".git").mkdir()

    bad_dir = tmp_path / bad_id
    bad_dir.mkdir()
    (bad_dir / ".git").mkdir()

    registry = MagicMock()

    def get_source(pid):
        s = MagicMock()
        s.local_path = str(tmp_path / pid)
        return s

    registry.get_plugin_source.side_effect = get_source
    registry.reload_plugin.return_value = MagicMock()
    registry._update_status = {good_id: True, bad_id: True}

    def fake_clone(url, pid, external_dir):
        return (True, "") if pid == good_id else (False, "fetch error")

    with patch("src.plugins.sources.get_external_plugins_dir", return_value=tmp_path), \
         patch("src.plugins.sources.clone_or_update_repo", side_effect=fake_clone):
        asyncio.run(_auto_apply_plugin_updates(registry, [good_id, bad_id]))

    assert good_id not in registry._update_status
    assert registry._update_status[bad_id] is True
