"""Tests for the FiestaPanel service layer."""

from src.panels.models import AutoDim, PanelCreate, PanelUpdate
from src.panels.service import PanelService, get_panel_service
from src.panels.storage import PanelStorage


def _service(tmp_path):
    return PanelService(storage=PanelStorage(storage_file=str(tmp_path / "panels.json")))


class TestPanelServiceCrud:
    def test_create_binds_board_id(self, tmp_path):
        service = _service(tmp_path)
        panel = service.create_panel(
            PanelCreate(name="TV", screen_diagonal_inches=65),
            board_id="board-9",
        )
        assert panel.board_id == "board-9"
        assert panel.screen_diagonal_inches == 65
        assert service.get_panel(panel.id) == panel

    def test_list_panels(self, tmp_path):
        service = _service(tmp_path)
        service.create_panel(PanelCreate(name="B"), board_id="b1")
        service.create_panel(PanelCreate(name="A"), board_id="b2")
        assert [p.name for p in service.list_panels()] == ["A", "B"]

    def test_update_only_touches_set_fields(self, tmp_path):
        """PanelUpdate uses exclude_unset — unset fields must not reset others."""
        service = _service(tmp_path)
        panel = service.create_panel(PanelCreate(name="TV"), board_id="b1")
        service.update_panel(panel.id, PanelUpdate(auto_dim=AutoDim(enabled=True)))
        updated = service.update_panel(panel.id, PanelUpdate(name="Kitchen"))
        assert updated is not None
        assert updated.name == "Kitchen"
        assert updated.auto_dim.enabled is True
        assert updated.screen_diagonal_inches == panel.screen_diagonal_inches

    def test_update_unknown_returns_none(self, tmp_path):
        assert _service(tmp_path).update_panel("nope", PanelUpdate(name="X")) is None

    def test_delete_returns_deleted_panel_with_board_id(self, tmp_path):
        """Routes need the deleted panel's board_id to remove the virtual board."""
        service = _service(tmp_path)
        panel = service.create_panel(PanelCreate(name="TV"), board_id="b7")
        deleted = service.delete_panel(panel.id)
        assert deleted is not None
        assert deleted.board_id == "b7"
        assert service.get_panel(panel.id) is None

    def test_delete_unknown_returns_none(self, tmp_path):
        assert _service(tmp_path).delete_panel("nope") is None


class TestSingleton:
    def test_get_panel_service_returns_same_instance(self):
        assert get_panel_service() is get_panel_service()
