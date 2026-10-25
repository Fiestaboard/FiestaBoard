"""Settings v7: display plugins need no opt-in.

The "Third-party displays (beta)" switch is gone. Every display plugin —
bundled with the image, from the marketplace or from a git URL — is
installable and usable on every install. What this module pins:

1. the v6 -> v7 migration drops ``plugins.output_plugins_enabled`` whatever
   its value, keeps every other plugin setting, is idempotent and counts;
2. a v6 file loads at v7 with the key gone and its pre-migration snapshot in
   ``settings.json.v6_backup``; a saved file never writes it back;
3. the API keeps the field as a deprecated, read-only ``true`` (until v11) on
   ``GET /settings/plugins`` and the ``/settings/beta`` alias; a ``PUT`` of it
   is accepted and changes nothing — an old client that turns it "off" gets
   no gate back.

The output side (no 409, every installed output builds, the safety fences
unchanged) is pinned in test_outputs_install.py, test_output_plugin_e2e.py,
test_output_seed_and_gate.py and test_outputs_board_create.py.
"""

from __future__ import annotations

import copy
import json
import logging

import pytest
from fastapi.testclient import TestClient


def _v6_data(plugins: dict | None) -> dict:
    data: dict = {"schema_version": 6, "board": {"board_type": "black", "boards": []}}
    if plugins is not None:
        data["plugins"] = plugins
    return data


# ---------------------------------------------------------------------------
# 1. The migration
# ---------------------------------------------------------------------------


class TestMigrateV6ToV7:
    @pytest.mark.parametrize("was_on", [True, False])
    def test_it_drops_the_opt_in_whatever_its_value(self, was_on):
        from src.settings.service import _migrate_v6_to_v7

        data = _v6_data({"auto_update": False, "transition_plugins_enabled": True, "output_plugins_enabled": was_on})
        assert _migrate_v6_to_v7(data) == 1
        assert data["plugins"] == {"auto_update": False, "transition_plugins_enabled": True}

    def test_it_is_idempotent(self):
        from src.settings.service import _migrate_v6_to_v7

        data = _v6_data({"output_plugins_enabled": False})
        _migrate_v6_to_v7(data)
        once = copy.deepcopy(data)
        assert _migrate_v6_to_v7(data) == 0
        assert data == once

    @pytest.mark.parametrize("plugins", [None, {}, "not-a-dict", {"auto_update": True}])
    def test_a_file_without_the_key_needs_nothing(self, plugins):
        from src.settings.service import _migrate_v6_to_v7

        data = _v6_data(plugins)
        before = copy.deepcopy(data)
        assert _migrate_v6_to_v7(data) == 0
        assert data == before

    def test_it_is_the_registered_v7_migration(self):
        from src.settings.service import CURRENT_SETTINGS_SCHEMA_VERSION, MIGRATIONS, _migrate_v6_to_v7

        assert CURRENT_SETTINGS_SCHEMA_VERSION == 7
        assert MIGRATIONS[-1] == (7, _migrate_v6_to_v7)


# ---------------------------------------------------------------------------
# 2. Loading and saving
# ---------------------------------------------------------------------------


def test_a_v6_file_with_the_opt_in_off_loads_at_v7_without_it(tmp_path, caplog):
    from src.settings.service import SettingsService

    path = tmp_path / "settings.json"
    path.write_text(json.dumps(_v6_data({"auto_update": False, "output_plugins_enabled": False})))
    v6 = path.read_bytes()

    with caplog.at_level(logging.INFO, logger="src.settings.service"):
        service = SettingsService(settings_file=str(path))

    assert "Settings schema migration v6->v7: 1 change(s) applied" in caplog.text
    assert (tmp_path / "settings.json.v6_backup").read_bytes() == v6
    on_disk = json.loads(path.read_text())
    assert on_disk["schema_version"] == 7
    assert "output_plugins_enabled" not in on_disk["plugins"]
    assert on_disk["plugins"]["auto_update"] is False
    assert service.get_plugin_settings().auto_update is False


def test_a_saved_file_never_writes_the_opt_in(tmp_path):
    from src.settings.service import SettingsService

    path = tmp_path / "settings.json"
    service = SettingsService(settings_file=str(path))
    service.update_plugin_settings({"output_plugins_enabled": False, "auto_update": False})
    on_disk = json.loads(path.read_text())
    assert set(on_disk["plugins"]) == {"auto_update", "transition_plugins_enabled"}


# ---------------------------------------------------------------------------
# 3. The API: a deprecated, read-only true
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    from src.api_server import app

    return TestClient(app)


class TestApi:
    def test_plugin_settings_report_display_plugins_as_always_on(self, client):
        body = client.get("/settings/plugins").json()
        assert body["output_plugins_enabled"] is True

    def test_turning_it_off_is_accepted_and_changes_nothing(self, client):
        response = client.put("/settings/plugins", json={"output_plugins_enabled": False})
        assert response.status_code == 200
        assert response.json()["output_plugins_enabled"] is True
        assert client.get("/settings/plugins").json()["output_plugins_enabled"] is True

    def test_it_still_rejects_a_non_bool(self, client):
        """Same body contract as before: a deprecated field stays strict."""
        assert client.put("/settings/plugins", json={"output_plugins_enabled": "yes"}).status_code == 422

    def test_the_beta_alias_reports_it_as_on(self, client):
        client.put("/settings/beta", json={"output_plugins_enabled": False})
        assert client.get("/settings/beta").json()["settings"]["output_plugins_enabled"] is True

    def test_the_field_is_marked_deprecated_in_the_schema(self):
        from src.api_server import app
        from src.v1.visibility import build_internal_openapi

        schema = build_internal_openapi(app)["components"]["schemas"]
        assert schema["PluginSettingsResponse"]["properties"]["output_plugins_enabled"].get("deprecated") is True
        assert schema["PluginSettingsUpdate"]["properties"]["output_plugins_enabled"].get("deprecated") is True
