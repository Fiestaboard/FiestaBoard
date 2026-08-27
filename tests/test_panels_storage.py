"""Tests for FiestaPanel JSON storage."""

import json

from src.panels.models import Panel
from src.panels.storage import CURRENT_SCHEMA_VERSION, PanelStorage


def _panel(**overrides):
    defaults = {"name": "Kitchen TV", "board_id": "board-1"}
    defaults.update(overrides)
    return Panel(**defaults)


class TestPanelStorage:
    def test_create_and_get_round_trip(self, tmp_path):
        storage = PanelStorage(storage_file=str(tmp_path / "panels.json"))
        panel = storage.create(_panel())
        assert storage.get(panel.id) == panel

    def test_file_carries_schema_version(self, tmp_path):
        path = tmp_path / "panels.json"
        storage = PanelStorage(storage_file=str(path))
        storage.create(_panel())
        data = json.loads(path.read_text())
        assert data["schema_version"] == CURRENT_SCHEMA_VERSION
        assert len(data["panels"]) == 1

    def test_reload_preserves_panels_and_datetimes(self, tmp_path):
        path = tmp_path / "panels.json"
        storage = PanelStorage(storage_file=str(path))
        panel = storage.create(_panel())
        reloaded = PanelStorage(storage_file=str(path)).get(panel.id)
        assert reloaded is not None
        assert reloaded.created_at == panel.created_at
        assert reloaded.auto_dim == panel.auto_dim

    def test_update_changes_fields_and_bumps_updated_at(self, tmp_path):
        storage = PanelStorage(storage_file=str(tmp_path / "panels.json"))
        panel = storage.create(_panel())
        updated = storage.update(panel.id, {"name": "Bedroom TV", "screen_diagonal_inches": 65.0})
        assert updated is not None
        assert updated.name == "Bedroom TV"
        assert updated.screen_diagonal_inches == 65.0
        assert updated.calibration_scale == panel.calibration_scale
        assert updated.updated_at >= panel.updated_at

    def test_update_unknown_id_returns_none(self, tmp_path):
        storage = PanelStorage(storage_file=str(tmp_path / "panels.json"))
        assert storage.update("nope", {"name": "X"}) is None

    def test_delete(self, tmp_path):
        storage = PanelStorage(storage_file=str(tmp_path / "panels.json"))
        panel = storage.create(_panel())
        assert storage.delete(panel.id) is True
        assert storage.get(panel.id) is None
        assert storage.delete(panel.id) is False

    def test_list_all_sorted_by_name(self, tmp_path):
        storage = PanelStorage(storage_file=str(tmp_path / "panels.json"))
        storage.create(_panel(name="zeta"))
        storage.create(_panel(name="Alpha"))
        names = [p.name for p in storage.list_all()]
        assert names == ["Alpha", "zeta"]

    def test_missing_file_loads_empty(self, tmp_path):
        storage = PanelStorage(storage_file=str(tmp_path / "panels.json"))
        assert storage.list_all() == []


class TestShortCodes:
    def test_create_assigns_sequential_short_codes(self, tmp_path):
        storage = PanelStorage(storage_file=str(tmp_path / "panels.json"))
        first = storage.create(_panel(name="one"))
        second = storage.create(_panel(name="two"))
        assert first.short_code == 1
        assert second.short_code == 2

    def test_deleted_code_is_reused_lowest_first(self, tmp_path):
        storage = PanelStorage(storage_file=str(tmp_path / "panels.json"))
        first = storage.create(_panel(name="one"))
        storage.create(_panel(name="two"))
        storage.delete(first.id)
        third = storage.create(_panel(name="three"))
        assert third.short_code == 1

    def test_short_codes_survive_reload(self, tmp_path):
        path = tmp_path / "panels.json"
        storage = PanelStorage(storage_file=str(path))
        panel = storage.create(_panel(name="one"))
        reloaded = PanelStorage(storage_file=str(path)).get(panel.id)
        assert reloaded is not None
        assert reloaded.short_code == panel.short_code


class TestSchemaMigrationV2:
    def test_v1_panels_get_short_codes_backfilled(self, tmp_path):
        """Panels stored before short codes existed are assigned them on load."""
        path = tmp_path / "panels.json"
        v1 = {
            "schema_version": 1,
            "panels": [
                {"id": "aaaaaaaaaaaa", "name": "beta", "board_id": "b1"},
                {"id": "bbbbbbbbbbbb", "name": "alpha", "board_id": "b2"},
            ],
        }
        path.write_text(json.dumps(v1))
        storage = PanelStorage(storage_file=str(path))
        codes = sorted(p.short_code for p in storage.list_all())
        assert codes == [1, 2]
        data = json.loads(path.read_text())
        assert data["schema_version"] == CURRENT_SCHEMA_VERSION
        assert CURRENT_SCHEMA_VERSION == 2

    def test_migration_is_idempotent(self, tmp_path):
        path = tmp_path / "panels.json"
        v1 = {"schema_version": 1, "panels": [{"id": "aaaaaaaaaaaa", "name": "one", "board_id": "b1"}]}
        path.write_text(json.dumps(v1))
        PanelStorage(storage_file=str(path))
        reloaded = PanelStorage(storage_file=str(path))
        assert [p.short_code for p in reloaded.list_all()] == [1]
