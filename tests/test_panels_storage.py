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
