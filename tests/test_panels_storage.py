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
        updated = storage.update("nope", {"name": "X"})
        assert updated is None

    def test_delete(self, tmp_path):
        storage = PanelStorage(storage_file=str(tmp_path / "panels.json"))
        panel = storage.create(_panel())
        deleted = storage.delete(panel.id)
        assert deleted is True
        assert storage.get(panel.id) is None
        deleted_again = storage.delete(panel.id)
        assert deleted_again is False

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

    def test_codes_held_by_unparseable_entries_are_not_reissued(self, tmp_path):
        """A failed-to-parse entry keeps its short code reserved.

        Unparseable entries are preserved in storage (never silently
        deleted); handing their code to a new panel would put two entries
        with the same short_code on disk, making /p/{n} resolution
        dict-order dependent.
        """
        path = tmp_path / "panels.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": CURRENT_SCHEMA_VERSION,
                    "panels": [
                        {"id": "validvalid12", "short_code": 1, "name": "ok", "board_id": "b1"},
                        # Missing required "name" → fails Pydantic validation
                        # on load but is preserved with its code.
                        {"id": "brokenbroken", "short_code": 2, "board_id": "b2"},
                    ],
                }
            )
        )
        storage = PanelStorage(storage_file=str(path))
        assert storage.count() == 1  # the broken entry did not parse

        created = storage.create(_panel(name="new"))
        assert created.short_code == 3

        codes = [p.get("short_code") for p in json.loads(path.read_text())["panels"]]
        assert sorted(codes) == [1, 2, 3]


class TestSchemaMigrationV5:
    def test_v4_panels_get_default_aspect_stamped(self, tmp_path):
        """Panels created before aspect ratios existed were sized for 16:9."""
        path = tmp_path / "panels.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 4,
                    "panels": [
                        {
                            "id": "aaaaaaaaaaaa",
                            "short_code": 1,
                            "name": "one",
                            "board_id": "b1",
                            "animations_enabled": False,
                            "is_display": False,
                        }
                    ],
                }
            )
        )
        storage = PanelStorage(storage_file=str(path))
        panel = storage.get("aaaaaaaaaaaa")
        assert panel is not None
        assert panel.screen_aspect_w == 16.0
        assert panel.screen_aspect_h == 9.0
        on_disk = json.loads(path.read_text())
        assert on_disk["schema_version"] == CURRENT_SCHEMA_VERSION
        assert on_disk["panels"][0]["screen_aspect_w"] == 16.0
        assert on_disk["panels"][0]["screen_aspect_h"] == 9.0


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

    def test_v2_panels_get_animations_enabled_stamped(self, tmp_path):
        """v2 entries predate the animation toggle; v3 stamps the default."""
        path = tmp_path / "panels.json"
        v2 = {
            "schema_version": 2,
            "panels": [{"id": "aaaaaaaaaaaa", "short_code": 1, "name": "one", "board_id": "b1"}],
        }
        path.write_text(json.dumps(v2))
        storage = PanelStorage(storage_file=str(path))
        assert storage.list_all()[0].animations_enabled is False
        data = json.loads(path.read_text())
        assert data["schema_version"] == CURRENT_SCHEMA_VERSION
        assert data["panels"][0]["animations_enabled"] is False
        assert data["panels"][0]["is_display"] is False

    def test_migration_is_idempotent(self, tmp_path):
        path = tmp_path / "panels.json"
        v1 = {"schema_version": 1, "panels": [{"id": "aaaaaaaaaaaa", "name": "one", "board_id": "b1"}]}
        path.write_text(json.dumps(v1))
        PanelStorage(storage_file=str(path))
        reloaded = PanelStorage(storage_file=str(path))
        assert [p.short_code for p in reloaded.list_all()] == [1]
