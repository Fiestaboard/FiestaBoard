"""An unknown board_id must be a 404 on every write path (Phase 2, Task 10c; #1888).

Four live endpoints accepted a free-form ``board_id`` and reported success:

* ``PUT /schedules/default-page`` wrote a phantom entry via
  ``ScheduleStorage.set_default_page_id``;
* ``PUT /schedules/enabled`` reached ``SettingsService.set_schedule_enabled``,
  which logged "Board not found" and returned the settings unchanged, while
  the route answered ``{"status": "success", "enabled": true}``;
* ``POST /schedules`` and ``PUT /schedules/{id}`` persisted a schedule bound
  to a board that does not exist, because ``check_ref_board_compatibility``
  passes silently on an unknown board.

The 404 pattern already existed inline in nine other handlers; this pins the
shared ``_require_board`` helper they now all share.

**Reads deliberately keep falling back** — see the "board_id validation" note
in ``docs/internal/reference/API_CONVENTIONS.md``. The read pins at the
bottom of this module exist so that decision cannot be reversed by accident.
"""

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.api_server import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def one_board():
    """Patch the boards list to a single known board, ``board-1``."""
    board_settings = Mock()
    board_settings.boards = [{"id": "board-1", "name": "Flagship", "device_type": "flagship"}]
    settings = Mock()
    settings.get_board_settings.return_value = board_settings
    settings.get_primary_board_id.return_value = "board-1"
    settings.is_schedule_enabled.return_value = False
    # Three modules resolve this collaborator after Phase 2 §2.3, and the
    # board verdict depends on which one the caller holds: the schedules and
    # pages routers bind it at import time, and `require_board` reads the
    # boards list through `src.board_guards`. Stub all three so the "unknown
    # board" verdict and `is_schedule_enabled` are decided by this fixture
    # whichever path a handler takes.
    with (
        patch("src.api_server.get_settings_service", return_value=settings),
        patch("src.schedules.routes.get_settings_service", return_value=settings),
        patch("src.board_guards.get_settings_service", return_value=settings),
    ):
        yield settings


class TestScheduleWritesRejectUnknownBoards:
    def test_set_default_page_404s_and_writes_nothing(self, client, one_board):
        schedule_service = Mock()
        page_service = Mock()
        page_service.get_page.return_value = Mock(id="page-1")
        with (
            patch("src.schedules.routes.get_schedule_service", return_value=schedule_service),
            patch("src.schedules.routes.get_page_service", return_value=page_service),
        ):
            response = client.put(
                "/schedules/default-page",
                json={"page_id": "page-1", "board_id": "ghost-board"},
            )
        assert response.status_code == 404
        assert "ghost-board" in response.json()["detail"]
        schedule_service.set_default_page.assert_not_called()

    def test_set_schedule_enabled_404s_and_writes_nothing(self, client, one_board):
        response = client.put("/schedules/enabled", json={"enabled": True, "board_id": "ghost-board"})
        assert response.status_code == 404
        one_board.set_schedule_enabled.assert_not_called()

    def test_create_schedule_404s_and_persists_nothing(self, client, one_board):
        schedule_service = Mock()
        with patch("src.schedules.routes.get_schedule_service", return_value=schedule_service):
            response = client.post(
                "/schedules",
                json={
                    "board_id": "ghost-board",
                    "page_id": "page-1",
                    "start_time": "09:00",
                    "end_time": "17:00",
                },
            )
        assert response.status_code == 404
        schedule_service.create_schedule.assert_not_called()

    def test_update_schedule_404s_and_does_not_reparent(self, client, one_board):
        schedule_service = Mock()
        with patch("src.schedules.routes.get_schedule_service", return_value=schedule_service):
            response = client.put("/schedules/sched-1", json={"board_id": "ghost-board"})
        assert response.status_code == 404
        schedule_service.update_schedule.assert_not_called()


class TestKnownAndOmittedBoardIdsStillWork:
    """The guard must reject only genuinely unknown ids."""

    def test_known_board_id_is_accepted(self, client, one_board):
        schedule_service = Mock()
        with patch("src.schedules.routes.get_schedule_service", return_value=schedule_service):
            response = client.put("/schedules/enabled", json={"enabled": True, "board_id": "board-1"})
        assert response.status_code == 200
        one_board.set_schedule_enabled.assert_called_once()

    def test_omitted_board_id_still_means_the_primary_board(self, client, one_board):
        response = client.put("/schedules/enabled", json={"enabled": True})
        assert response.status_code == 200
        one_board.set_schedule_enabled.assert_called_once()

    def test_empty_board_id_still_means_the_default_board(self, client, one_board):
        """``ScheduleCreate.board_id`` defaults to "" = default/first board."""
        schedule_service = Mock()
        created = Mock()
        created.model_dump.return_value = {
            "id": "s1",
            "board_id": "",
            "page_id": "page-1",
            "start_time": "09:00",
            "end_time": "17:00",
            "start_type": "fixed",
            "end_type": "fixed",
        }
        created.page_id = "page-1"
        created.board_id = ""
        schedule_service.create_schedule.return_value = created
        compat = Mock(ok=True, warnings=[])
        with (
            patch("src.schedules.routes.get_schedule_service", return_value=schedule_service),
            patch("src.schedules.routes.check_ref_board_compatibility", return_value=compat),
        ):
            response = client.post(
                "/schedules",
                json={"page_id": "page-1", "start_time": "09:00", "end_time": "17:00"},
            )
        assert response.status_code == 201  # 201 since the conventions pass


class TestServiceLevelDefenceInDepth:
    """`set_paused` / `set_active_page_id` are NOT reachable with an unknown
    board over HTTP today — every route that reaches them validates first, or
    404s on its own path parameter. These are belt-and-braces so a future
    caller cannot recreate the phantom write."""

    def test_set_paused_rejects_an_unknown_board(self, tmp_path):
        from src.settings.service import SettingsService

        service = SettingsService(str(tmp_path / "settings.json"))
        service.get_board_settings().boards = [{"id": "board-1"}]
        with pytest.raises(ValueError, match="ghost-board"):
            service.set_paused(True, board_id="ghost-board")

    def test_set_active_page_id_rejects_an_unknown_board(self, tmp_path):
        from src.settings.service import SettingsService

        service = SettingsService(str(tmp_path / "settings.json"))
        service.get_board_settings().boards = [{"id": "board-1"}]
        with pytest.raises(ValueError, match="ghost-board"):
            service.set_active_page_id("page-1", board_id="ghost-board")

    def test_set_active_page_id_does_not_write_a_phantom_entry(self, tmp_path):
        from src.settings.service import SettingsService

        service = SettingsService(str(tmp_path / "settings.json"))
        service.get_board_settings().boards = [{"id": "board-1"}]
        with pytest.raises(ValueError):
            service.set_active_page_id("page-1", board_id="ghost-board")
        assert "ghost-board" not in service.get_active_page_settings().by_board


class TestReadsDeliberatelyFallBack:
    """Documented asymmetry: reads answer with the safe default rather than
    404, because a board-scoped poll racing a board deletion is normal and
    a read cannot corrupt anything. Changing this is a decision, not a fix.

    Both HTTP pins below carry a **control**: the same call for the *known*
    board answers something else. Without it they passed with the ``one_board``
    fixture and every service patch removed — an empty store answers ``[]`` and
    ``false`` for every board id, so they could not tell "the read falls back
    for an unknown board" from "there is nothing in the store".
    """

    @staticmethod
    def _schedule_for(board_id):
        from src.schedules.models import ScheduleEntry

        return ScheduleEntry(
            id="sched-1",
            board_id=board_id,
            page_id="page-1",
            start_time="09:00",
            end_time="17:00",
        )

    def test_list_schedules_returns_empty_for_an_unknown_board(self, client, one_board):
        by_board = {"board-1": [self._schedule_for("board-1")]}
        schedule_service = Mock()
        schedule_service.list_schedules.side_effect = lambda board_id=None: by_board.get(board_id, [])
        schedule_service.get_default_page.side_effect = lambda board_id=None: (
            "page-1" if board_id == "board-1" else None
        )
        with patch("src.schedules.routes.get_schedule_service", return_value=schedule_service):
            known = client.get("/schedules", params={"board_id": "board-1"})
            unknown = client.get("/schedules", params={"board_id": "ghost-board"})

        # Control: the store is not empty, and a board-scoped read can see it.
        assert known.status_code == 200
        assert [s["id"] for s in known.json()["schedules"]] == ["sched-1"]
        # The unknown board falls back to the empty list instead of 404ing.
        assert unknown.status_code == 200
        assert unknown.json()["schedules"] == []

    def test_get_schedule_enabled_returns_false_for_an_unknown_board(self, client, one_board):
        one_board.is_schedule_enabled.side_effect = lambda board_id=None: board_id == "board-1"

        known = client.get("/schedules/enabled", params={"board_id": "board-1"})
        unknown = client.get("/schedules/enabled", params={"board_id": "ghost-board"})

        # Control: the route reports a real per-board verdict, not a constant.
        assert known.status_code == 200
        assert known.json()["enabled"] is True
        # The unknown board falls back to False instead of 404ing.
        assert unknown.status_code == 200
        assert unknown.json()["enabled"] is False

    def test_settings_service_answers_false_for_an_unknown_board(self, tmp_path):
        """The fallback itself, at the layer that decides it — no stubs."""
        from src.settings.service import SettingsService

        service = SettingsService(str(tmp_path / "settings.json"))
        service.get_board_settings().boards = [{"id": "board-1", "schedule_enabled": True}]

        assert service.is_schedule_enabled(board_id="board-1") is True
        assert service.is_schedule_enabled(board_id="ghost-board") is False
