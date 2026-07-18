"""Tests for per-board display driving (issue #1243).

Covers:
  - _build_board_clients builds one client per configured board and keeps
    vb_client pointing at the primary
  - reinitialize_board_client prunes caches for removed boards
  - _update_secondary_boards sends each secondary board its own scheduled
    page via its own client, and skips paused / disabled / schedule-off
    boards, silence mode, and unchanged content
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.main import DisplayService


def _time_service():
    svc = MagicMock()
    svc.get_current_time.return_value = datetime(2026, 7, 15, 12, 0, 0)
    return svc


def _board(board_id: str, name: str, **overrides) -> dict:
    board = {
        "id": board_id,
        "name": name,
        "device_type": "flagship",
        "board_color": "black",
        "enabled": True,
        "paused": False,
        "api_mode": "local",
        "host": "mock-host",
        "port": 7000,
        "local_api_key": "test-key",
        "schedule_enabled": True,
    }
    board.update(overrides)
    return board


TRANSITIONS = SimpleNamespace(strategy="instant", step_interval_ms=0, step_size=1)


def _settings_service(boards, paused_ids=(), schedule_off_ids=()):
    svc = MagicMock()
    svc.get_board_settings.return_value = SimpleNamespace(boards=boards)
    svc.is_paused.side_effect = lambda board_id=None: board_id in paused_ids
    svc.is_schedule_enabled.side_effect = lambda board_id=None: board_id not in schedule_off_ids
    svc.get_transition_settings.return_value = TRANSITIONS
    return svc


def _page_service(page_id: str, content: str):
    svc = MagicMock()
    page = SimpleNamespace(
        id=page_id,
        device_type="flagship",
        notes_wide=1,
        notes_tall=1,
        transition_strategy=None,
        transition_interval_ms=None,
        transition_step_size=None,
    )
    svc.get_page.return_value = page
    svc.preview_page.return_value = SimpleNamespace(available=True, formatted=content, error=None)
    return svc


def _schedule_service(active_by_board: dict):
    svc = MagicMock()
    svc.get_active_page_id.side_effect = lambda t, d, board_id=None: active_by_board.get(board_id)
    return svc


@pytest.fixture
def service():
    return DisplayService()


class TestBuildBoardClients:
    def test_builds_one_client_per_board_with_credentials(self, service):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        clients = {"b1": MagicMock(), "b2": MagicMock()}
        with (
            patch("src.main.get_settings_service", return_value=_settings_service(boards)),
            patch("src.main.board_client_from_board_dict", side_effect=lambda b: clients[b["id"]]),
        ):
            service._build_board_clients()

        assert service.board_clients == clients
        assert service.vb_client is clients["b1"]
        clients["b1"].read_current_message.assert_called_once_with(sync_cache=True)

    def test_board_without_credentials_gets_no_client(self, service):
        boards = [_board("b1", "One"), _board("b2", "Two", local_api_key="", cloud_key="")]
        with (
            patch("src.main.get_settings_service", return_value=_settings_service(boards)),
            patch("src.main.board_client_from_board_dict", side_effect=lambda b: MagicMock()),
        ):
            service._build_board_clients()

        assert set(service.board_clients) == {"b1"}

    def test_reinitialize_prunes_caches_of_removed_boards(self, service):
        boards = [_board("b2", "Two", port=7001)]
        service._secondary_last_sent = {"b2": ("p", "c"), "b-gone": ("p", "c")}
        with (
            patch("src.main.get_settings_service", return_value=_settings_service(boards)),
            patch("src.main.board_client_from_board_dict", side_effect=lambda b: MagicMock()),
        ):
            assert service.reinitialize_board_client() is True

        assert set(service.board_clients) == {"b2"}
        assert set(service._secondary_last_sent) == {"b2"}


class TestUpdateSecondaryBoards:
    def _run(self, service, boards, *, paused=(), schedule_off=(), active=None, content="HELLO BOARD TWO"):
        active = active if active is not None else {"b2": "page-2"}
        with (
            patch("src.main.get_settings_service", return_value=_settings_service(boards, paused, schedule_off)),
            patch("src.main.get_page_service", return_value=_page_service("page-2", content)),
            patch("src.main.get_schedule_service", return_value=_schedule_service(active)),
            patch("src.main.get_collection_service", return_value=MagicMock()),
            patch("src.time_service.get_time_service", return_value=_time_service()),
            patch("src.main.Config") as mock_config,
        ):
            mock_config.is_silence_mode_active.return_value = False
            service._update_secondary_boards()

    def test_secondary_board_receives_its_scheduled_page(self, service):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        client = MagicMock()
        client.send_characters.return_value = (True, True)
        service.board_clients = {"b1": MagicMock(), "b2": client}

        self._run(service, boards)

        client.send_characters.assert_called_once()
        rows = client.send_characters.call_args.args[0]
        assert len(rows) == 6 and len(rows[0]) == 22  # flagship dimensions
        assert service._secondary_last_sent["b2"] == ("page-2", "HELLO BOARD TWO")

    def test_primary_client_is_never_used_for_secondary_content(self, service):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        primary = MagicMock()
        secondary = MagicMock()
        secondary.send_characters.return_value = (True, True)
        service.board_clients = {"b1": primary, "b2": secondary}

        self._run(service, boards)

        primary.send_characters.assert_not_called()

    def test_unchanged_content_is_not_resent(self, service):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        client = MagicMock()
        client.send_characters.return_value = (True, True)
        service.board_clients = {"b2": client}

        self._run(service, boards)
        self._run(service, boards)

        assert client.send_characters.call_count == 1

    def test_paused_secondary_board_is_skipped(self, service):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        client = MagicMock()
        service.board_clients = {"b2": client}

        self._run(service, boards, paused=("b2",))

        client.send_characters.assert_not_called()

    def test_schedule_disabled_secondary_board_is_skipped(self, service):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        client = MagicMock()
        service.board_clients = {"b2": client}

        self._run(service, boards, schedule_off=("b2",))

        client.send_characters.assert_not_called()

    def test_disabled_secondary_board_is_skipped(self, service):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001, enabled=False)]
        client = MagicMock()
        service.board_clients = {"b2": client}

        self._run(service, boards)

        client.send_characters.assert_not_called()

    def test_no_matching_schedule_sends_nothing(self, service):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        client = MagicMock()
        service.board_clients = {"b2": client}

        self._run(service, boards, active={"b2": None})

        client.send_characters.assert_not_called()

    def test_silence_mode_silences_secondary_boards(self, service):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        client = MagicMock()
        service.board_clients = {"b2": client}
        with (
            patch("src.main.get_settings_service", return_value=_settings_service(boards)),
            patch("src.main.get_page_service", return_value=_page_service("page-2", "X")),
            patch("src.main.get_schedule_service", return_value=_schedule_service({"b2": "page-2"})),
            patch("src.time_service.get_time_service", return_value=_time_service()),
            patch("src.main.Config") as mock_config,
        ):
            mock_config.is_silence_mode_active.return_value = True
            service._update_secondary_boards()

        client.send_characters.assert_not_called()

    def test_single_board_is_a_noop(self, service):
        boards = [_board("b1", "One")]
        client = MagicMock()
        service.board_clients = {"b1": client}

        self._run(service, boards)

        client.send_characters.assert_not_called()

    def test_send_failure_does_not_cache_content(self, service):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        client = MagicMock()
        client.send_characters.return_value = (False, False)
        service.board_clients = {"b2": client}

        self._run(service, boards)

        assert "b2" not in service._secondary_last_sent
