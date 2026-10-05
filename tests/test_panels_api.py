"""Tests for the FiestaPanel API endpoints.

Phase 2 slice 8 moved the handlers to ``src/panels/routes.py`` and applied the
API conventions: create answers 201 with the bare panel, update answers the
bare panel with an always-present ``incompatible_references``, and delete
answers ``{"id": ...}``. Collaborator stubs patch ``src.panels.routes.<name>``,
where the router binds them. ``tests/test_panels_contract.py`` pins the same
contract by value.
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.outputs import OutputRuntime
from src.panels.models import Panel
from src.panels.service import PanelService
from src.panels.storage import PanelStorage
from src.virtual_board_client import VirtualBoardClient


def _runtime(client):
    """A board runtime as ``runtime_for`` returns it: the client bound to its OutputRuntime,
    which knows the board's output (``fiestapanel`` for a virtual client)."""
    output = OutputRuntime(output_id="fiestapanel" if isinstance(client, VirtualBoardClient) else "vestaboard")
    bind = getattr(client, "set_output_runtime", None)
    if bind is not None:
        bind(output)
    return SimpleNamespace(client=client, output=output, polled_characters=None, polled_at=None)


@pytest.fixture
def client():
    from src.api_server import app

    return TestClient(app)


@pytest.fixture
def mock_panel_service():
    with patch("src.panels.routes.get_panel_service") as mock:
        service = Mock()
        mock.return_value = service
        yield service


def _panel(**overrides):
    defaults = {"name": "Living Room TV", "board_id": "vboard-1"}
    defaults.update(overrides)
    return Panel(**defaults)


class TestPanelCrudEndpoints:
    def test_list_panels(self, client, mock_panel_service):
        """GET /panels returns panels with board geometry attached."""
        mock_panel_service.list_panels.return_value = [_panel()]
        with patch("src.panels.routes._find_board") as find_board:
            find_board.return_value = {
                "id": "vboard-1",
                "device_type": "note_array",
                "notes_wide": 2,
                "notes_tall": 4,
            }
            response = client.get("/panels")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["panels"][0]["device_type"] == "note_array"
        assert data["panels"][0]["board_missing"] is False
        assert (data["panels"][0]["rows"], data["panels"][0]["cols"]) == (12, 30)

    def test_list_panels_reports_orphaned_board(self, client, mock_panel_service):
        """A panel whose virtual board was deleted reports board_missing."""
        mock_panel_service.list_panels.return_value = [_panel()]
        with patch("src.panels.routes._find_board", return_value=None):
            response = client.get("/panels")
        assert response.status_code == 200
        assert response.json()["panels"][0]["board_missing"] is True

    def test_patch_unknown_panel_404s(self, client, mock_panel_service):
        mock_panel_service.update_panel.return_value = None
        response = client.patch("/panels/nope", json={"name": "X"})
        assert response.status_code == 404

    def test_patch_updates_panel(self, client, mock_panel_service):
        mock_panel_service.update_panel.return_value = _panel(name="Bedroom TV")
        response = client.patch("/panels/abc", json={"name": "Bedroom TV"})
        assert response.status_code == 200
        assert response.json()["name"] == "Bedroom TV"

    def test_delete_unknown_panel_404s(self, client, mock_panel_service):
        mock_panel_service.delete_panel.return_value = None
        response = client.delete("/panels/nope")
        assert response.status_code == 404


class TestPublicPanelEndpoints:
    def test_public_endpoints_resolve_short_codes(self, client, mock_panel_service):
        """/panel/1 (TV-typable short URL) resolves via get_panel_by_ref."""
        mock_panel_service.get_panel_by_ref.return_value = _panel(short_code=1)
        with patch("src.panels.routes._find_board", return_value=None):
            response = client.get("/panel/1")
        assert response.status_code == 200
        mock_panel_service.get_panel_by_ref.assert_called_with("1")

    def test_display_ref_without_designation_gets_distinct_detail(self, client, mock_panel_service):
        """The kiosk URL needs actionable copy before a panel is designated."""
        mock_panel_service.get_panel_by_ref.return_value = None
        response = client.get("/panel/display")
        assert response.status_code == 404
        assert response.json()["detail"] == "No display panel selected"
        response = client.get("/panel/display/frame")
        assert response.status_code == 404
        assert response.json()["detail"] == "No display panel selected"

    def test_get_panel_returns_board_geometry(self, client, mock_panel_service):
        mock_panel_service.get_panel_by_ref.return_value = _panel()
        board = {
            "id": "vboard-1",
            "device_type": "note",
            "board_color": "white",
            "api_mode": "virtual",
        }
        with patch("src.panels.routes._find_board", return_value=board):
            response = client.get("/panel/abc123def456")
        assert response.status_code == 200
        data = response.json()
        assert (data["rows"], data["cols"]) == (3, 15)
        assert data["board_color"] == "white"
        assert data["board_missing"] is False

    def test_get_panel_unknown_404s_with_stable_detail(self, client, mock_panel_service):
        mock_panel_service.get_panel_by_ref.return_value = None
        response = client.get("/panel/nope")
        assert response.status_code == 404
        assert response.json()["detail"] == "Panel not found"

    def test_get_panel_orphaned_board(self, client, mock_panel_service):
        mock_panel_service.get_panel_by_ref.return_value = _panel()
        with patch("src.panels.routes._find_board", return_value=None):
            response = client.get("/panel/abc123def456")
        assert response.status_code == 200
        data = response.json()
        assert data["board_missing"] is True
        assert data["rows"] is None

    def test_frame_returns_sent_grid(self, client, mock_panel_service):
        mock_panel_service.get_panel_by_ref.return_value = _panel()
        vclient = VirtualBoardClient(device_type="note")
        grid = [[7] * 15 for _ in range(3)]
        vclient.send_characters(grid)
        board = {"id": "vboard-1", "device_type": "note", "api_mode": "virtual"}
        display = Mock()
        display.runtime_for.return_value = _runtime(vclient)
        with (
            patch("src.panels.routes._find_board", return_value=board),
            patch("src.panels.routes.get_service", return_value=display),
        ):
            response = client.get("/panel/abc123def456/frame")
        assert response.status_code == 200
        data = response.json()
        assert data["characters"] == grid
        assert (data["rows"], data["cols"]) == (3, 15)
        assert data["updated_at"] is not None
        assert isinstance(data["message"], str)

    def test_frame_empty_board_returns_nulls_with_dims(self, client, mock_panel_service):
        mock_panel_service.get_panel_by_ref.return_value = _panel()
        vclient = VirtualBoardClient(device_type="flagship")
        board = {"id": "vboard-1", "device_type": "flagship", "api_mode": "virtual"}
        display = Mock()
        display.runtime_for.return_value = _runtime(vclient)
        with (
            patch("src.panels.routes._find_board", return_value=board),
            patch("src.panels.routes.get_service", return_value=display),
        ):
            response = client.get("/panel/abc123def456/frame")
        assert response.status_code == 200
        data = response.json()
        assert data["characters"] is None
        assert data["message"] is None
        assert (data["rows"], data["cols"]) == (6, 22)
        assert data["updated_at"] is None

    def test_frame_never_http_reads_a_non_virtual_client(self, client, mock_panel_service):
        """A panel misconfigured onto a physical board must not trigger live reads."""
        mock_panel_service.get_panel_by_ref.return_value = _panel()
        board = {"id": "vboard-1", "device_type": "flagship", "api_mode": "local"}
        physical = Mock(spec=["read_current_message"])
        display = Mock()
        display.runtime_for.return_value = _runtime(physical)
        with (
            patch("src.panels.routes._find_board", return_value=board),
            patch("src.panels.routes.get_service", return_value=display),
        ):
            response = client.get("/panel/abc123def456/frame")
        assert response.status_code == 200
        physical.read_current_message.assert_not_called()


class TestPanelOrchestration:
    """POST/DELETE co-manage the virtual board through the settings service."""

    def _fake_settings_service(self, initial_boards: list[dict] | None = None):
        boards: list[dict] = [dict(b) for b in (initial_boards or [])]

        def add_board(board: dict):
            boards.append(dict(board))

        def remove_board(board_id: str):
            # Mirror the real service's last-board rule — hiding it here is
            # exactly what masked the stranded-virtual-board bug.
            if len(boards) <= 1:
                raise ValueError("Cannot remove the last board. At least one board is required.")
            before = len(boards)
            boards[:] = [b for b in boards if b.get("id") != board_id]
            if len(boards) == before:
                raise ValueError(f"Board with ID '{board_id}' not found")
            # `board_type` and `devices` are part of the real
            # BoardSettings.to_dict payload; DELETE /settings/board/{id}
            # validates its response against BoardSettingsResponse since the
            # conventions pass, so this double has to carry them too.
            return SimpleNamespace(
                to_dict=lambda: {
                    "board_type": "black",
                    "boards": boards,
                    "devices": sorted({b.get("device_type", "flagship") for b in boards}),
                }
            )

        def set_boards(new_boards: list[dict]):
            if not new_boards:
                raise ValueError("At least one board instance is required")
            # The real service normalizes each dict through BoardInstance,
            # which generates a fresh id when none is provided.
            from src.devices import BoardInstance

            boards[:] = [BoardInstance.from_dict(dict(b)).to_dict() for b in new_boards]

        return SimpleNamespace(
            add_board=add_board,
            remove_board=remove_board,
            set_boards=set_boards,
            boards=boards,
            get_board_settings=lambda: SimpleNamespace(boards=boards),
            get_primary_board_id=lambda: "primary-board",
        )

    def test_create_panel_creates_autofit_virtual_board(self, client, tmp_path):
        """The board's grid is computed per character from the TV size (65" 16:9 → 14 rows × 34 cols)."""
        real_service = PanelService(storage=PanelStorage(storage_file=str(tmp_path / "p.json")))
        fake_settings = self._fake_settings_service()
        with (
            patch("src.panels.routes.get_panel_service", return_value=real_service),
            patch("src.panels.routes.get_settings_service", return_value=fake_settings),
            patch("src.panels.routes.reinitialize_board_clients") as reinit,
        ):
            response = client.post(
                "/panels",
                json={"name": "Hall TV", "screen_diagonal_inches": 65},
            )
        # RE-PINNED (Phase 2 slice 8): create answers 201 with the bare panel.
        assert response.status_code == 201
        panel = response.json()
        assert len(fake_settings.boards) == 1
        board = fake_settings.boards[0]
        assert board["api_mode"] == "virtual"
        assert board["device_type"] == "panel"
        assert (board["grid_rows"], board["grid_cols"]) == (14, 34)
        assert board["id"] == panel["board_id"]
        assert reinit.called
        assert real_service.get_panel(panel["id"]) is not None

    def test_resize_recomputes_the_grid(self, client, tmp_path):
        """Changing the TV size re-fits the virtual board's dimensions."""
        real_service = PanelService(storage=PanelStorage(storage_file=str(tmp_path / "p.json")))
        fake_settings = self._fake_settings_service()
        with (
            patch("src.panels.routes.get_panel_service", return_value=real_service),
            patch("src.panels.routes.get_settings_service", return_value=fake_settings),
            patch("src.panels.routes.reinitialize_board_clients"),
        ):
            created = client.post("/panels", json={"name": "Hall TV", "screen_diagonal_inches": 43}).json()
            board = fake_settings.boards[0]
            assert (board["grid_rows"], board["grid_cols"]) == (9, 22)

            response = client.patch(f"/panels/{created['id']}", json={"screen_diagonal_inches": 85})
        assert response.status_code == 200
        board = fake_settings.boards[0]
        assert (board["grid_rows"], board["grid_cols"]) == (18, 45)

    def test_create_with_aspect_sizes_the_grid_and_round_trips(self, client, tmp_path):
        """The aspect must both size the board AND persist on the panel —
        the first implementation computed the 21:9 grid but silently stored
        16:9, so the next size edit would have re-fit the wrong shape."""
        real_service = PanelService(storage=PanelStorage(storage_file=str(tmp_path / "p.json")))
        fake_settings = self._fake_settings_service()
        with (
            patch("src.panels.routes.get_panel_service", return_value=real_service),
            patch("src.panels.routes.get_settings_service", return_value=fake_settings),
            patch("src.panels.routes.reinitialize_board_clients"),
        ):
            created = client.post(
                "/panels",
                json={"name": "Wide TV", "screen_diagonal_inches": 55, "screen_aspect_w": 21, "screen_aspect_h": 9},
            ).json()
        assert created["screen_aspect_w"] == 21
        assert created["screen_aspect_h"] == 9
        board = fake_settings.boards[0]
        assert (board["grid_rows"], board["grid_cols"]) == (9, 30)
        stored = real_service.get_panel(created["id"])
        assert stored is not None
        assert (stored.screen_aspect_w, stored.screen_aspect_h) == (21, 9)

    def test_aspect_change_refits_the_grid(self, client, tmp_path):
        """Changing the aspect ratio re-fits the board like a size change:
        a 55" 16:9 panel is 12×29; the same TV declared 21:9 fits 9×30."""
        real_service = PanelService(storage=PanelStorage(storage_file=str(tmp_path / "p.json")))
        fake_settings = self._fake_settings_service()
        with (
            patch("src.panels.routes.get_panel_service", return_value=real_service),
            patch("src.panels.routes.get_settings_service", return_value=fake_settings),
            patch("src.panels.routes.reinitialize_board_clients"),
        ):
            created = client.post("/panels", json={"name": "Wide TV", "screen_diagonal_inches": 55}).json()
            board = fake_settings.boards[0]
            assert (board["grid_rows"], board["grid_cols"]) == (12, 29)

            response = client.patch(f"/panels/{created['id']}", json={"screen_aspect_w": 21, "screen_aspect_h": 9})
        assert response.status_code == 200
        assert response.json()["screen_aspect_w"] == 21
        board = fake_settings.boards[0]
        assert (board["grid_rows"], board["grid_cols"]) == (9, 30)

    def test_delete_panel_removes_virtual_board(self, client, tmp_path):
        real_service = PanelService(storage=PanelStorage(storage_file=str(tmp_path / "p.json")))
        fake_settings = self._fake_settings_service(
            initial_boards=[{"id": "physical-1", "device_type": "flagship", "api_mode": "local"}]
        )
        with (
            patch("src.panels.routes.get_panel_service", return_value=real_service),
            patch("src.panels.routes.get_settings_service", return_value=fake_settings),
            patch("src.panels.routes.reinitialize_board_clients"),
        ):
            created = client.post("/panels", json={"name": "Hall TV", "screen_diagonal_inches": 43}).json()
            assert len(fake_settings.boards) == 2
            response = client.delete(f"/panels/{created['id']}")
        assert response.status_code == 200
        assert [b["id"] for b in fake_settings.boards] == ["physical-1"]
        assert real_service.get_panel(created["id"]) is None

    # Release on delete / re-fit is core's now: tests/test_panel_frame_store.py.

    def test_delete_last_panel_swaps_in_a_default_board(self, client, tmp_path):
        """Deleting the only panel when its virtual board is the only board
        must not strand the virtual board as an unremovable primary.

        The last-board rule forbids removing it outright, so the route swaps
        in a fresh default board — the same state a data reset produces.
        """
        real_service = PanelService(storage=PanelStorage(storage_file=str(tmp_path / "p.json")))
        fake_settings = self._fake_settings_service()
        with (
            patch("src.panels.routes.get_panel_service", return_value=real_service),
            patch("src.panels.routes.get_settings_service", return_value=fake_settings),
            patch("src.panels.routes.reinitialize_board_clients"),
        ):
            created = client.post("/panels", json={"name": "Hall TV", "screen_diagonal_inches": 43}).json()
            assert len(fake_settings.boards) == 1  # the virtual board is the only board
            response = client.delete(f"/panels/{created['id']}")
        assert response.status_code == 200
        assert real_service.get_panel(created["id"]) is None
        assert len(fake_settings.boards) == 1
        replacement = fake_settings.boards[0]
        assert replacement["id"] != created["board_id"]
        assert replacement.get("api_mode") != "virtual"

    def test_resize_reports_references_the_board_no_longer_fits(self, client, tmp_path):
        """A TV-size change reshapes the grid; refs to now-misfit pages are
        reported warn-only, mirroring PUT /pages/{id} (issue #1250)."""
        real_service = PanelService(storage=PanelStorage(storage_file=str(tmp_path / "p.json")))
        fake_settings = self._fake_settings_service()
        stale = [{"page_id": "p1", "page_name": "Big Page", "surface": "schedule", "schedule_id": "s1"}]
        with (
            patch("src.panels.routes.get_panel_service", return_value=real_service),
            patch("src.panels.routes.get_settings_service", return_value=fake_settings),
            patch("src.panels.routes.reinitialize_board_clients"),
            patch("src.panels.routes.find_incompatible_board_references", return_value=stale) as finder,
        ):
            created = client.post("/panels", json={"name": "Hall TV", "screen_diagonal_inches": 43}).json()

            resized = client.patch(f"/panels/{created['id']}", json={"screen_diagonal_inches": 85})
            assert resized.status_code == 200
            assert resized.json()["incompatible_references"] == stale
            assert finder.called

            finder.reset_mock()
            renamed = client.patch(f"/panels/{created['id']}", json={"name": "Lounge TV"})
        assert renamed.status_code == 200
        # RE-PINNED (Phase 2 slice 8): always present, null when nothing was
        # re-fit — the key used to be absent, which the client had to special-case.
        assert renamed.json()["incompatible_references"] is None
        assert not finder.called

    def test_remove_board_endpoint_refuses_a_panel_backed_board(self, client, tmp_path):
        """DELETE /settings/board/{id} on a board a panel still references
        must 409 — removing it blanks the TV and orphans the panel."""
        real_service = PanelService(storage=PanelStorage(storage_file=str(tmp_path / "p.json")))
        fake_settings = self._fake_settings_service(
            initial_boards=[{"id": "physical-1", "device_type": "flagship", "api_mode": "local"}]
        )
        with (
            patch("src.panels.routes.get_panel_service", return_value=real_service),
            # DELETE /settings/board/{id} is still an api_server handler and
            # resolves the panel service through its own binding, so the stub
            # has to cover both until the settings slice lands.
            patch("src.api_server.get_panel_service", return_value=real_service),
            patch("src.panels.routes.get_settings_service", return_value=fake_settings),
            patch("src.api_server.get_settings_service", return_value=fake_settings),
            patch("src.panels.routes.reinitialize_board_clients"),
        ):
            created = client.post("/panels", json={"name": "Hall TV", "screen_diagonal_inches": 43}).json()

            response = client.delete(f"/settings/board/{created['board_id']}")
            assert response.status_code == 409
            assert "Hall TV" in response.json()["detail"]
            assert any(b["id"] == created["board_id"] for b in fake_settings.boards)

            # Unreferenced boards still remove normally.
            response = client.delete("/settings/board/physical-1")
        assert response.status_code == 200
        assert [b["id"] for b in fake_settings.boards] == [created["board_id"]]

    def test_delete_tolerates_already_deleted_board(self, client, tmp_path):
        real_service = PanelService(storage=PanelStorage(storage_file=str(tmp_path / "p.json")))
        fake_settings = self._fake_settings_service()
        with (
            patch("src.panels.routes.get_panel_service", return_value=real_service),
            patch("src.panels.routes.get_settings_service", return_value=fake_settings),
            patch("src.panels.routes.reinitialize_board_clients"),
        ):
            created = client.post("/panels", json={"name": "Hall TV", "screen_diagonal_inches": 43}).json()
            fake_settings.boards.clear()  # board deleted out-of-band
            response = client.delete(f"/panels/{created['id']}")
        assert response.status_code == 200
        assert real_service.get_panel(created["id"]) is None
