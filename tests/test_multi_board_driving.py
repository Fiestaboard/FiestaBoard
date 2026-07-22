"""Tests for building/rebuilding per-board runtimes (issue #1243).

Covers ``DisplayService._build_board_clients`` / ``rebuild_board_clients``:
  - one runtime per configured board, ``vb_client`` pointing at the primary
  - note-array boards (token auth) are not filtered out
  - boards without a usable connection get no runtime
  - a rebuild prunes runtimes for removed boards

The per-board *driving* behaviour (routing, pause/schedule/silence isolation,
per-board caches) is covered by ``tests/test_per_board_engine.py``, which
exercises the unified ``check_and_send_for_board`` path.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.main import BoardRuntime, DisplayService


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


def _settings_service(boards):
    svc = MagicMock()
    svc.get_board_settings.return_value = SimpleNamespace(boards=boards)
    svc.get_primary_board_id.return_value = boards[0]["id"] if boards else None
    return svc


@pytest.fixture
def service():
    return DisplayService()


class TestBuildBoardClients:
    def test_builds_one_runtime_per_board_with_credentials(self, service):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        clients = {"b1": MagicMock(), "b2": MagicMock()}
        with (
            patch("src.main.get_settings_service", return_value=_settings_service(boards)),
            patch("src.main.board_client_from_board_dict", side_effect=lambda b: clients[b["id"]]),
        ):
            service._build_board_clients()

        assert service.board_clients == clients
        assert service.vb_client is clients["b1"]
        assert set(service.runtimes) == {"b1", "b2"}
        assert service._primary_board_id == "b1"
        clients["b1"].read_current_message.assert_called_once_with(sync_cache=True)

    def test_note_array_board_with_only_a_token_gets_a_runtime(self, service):
        """Note arrays authenticate with note_array_token, not local/cloud keys —
        the runtime build must not filter them out (issue #1243 item 3)."""
        boards = [
            _board("b1", "One"),
            _board(
                "b2",
                "Array",
                device_type="note_array",
                api_mode="cloud",
                host="",
                local_api_key="",
                cloud_key="",
                note_array_token="test-token",
                notes_wide=2,
                notes_tall=2,
            ),
        ]
        clients = {"b1": MagicMock(), "b2": MagicMock()}
        with (
            patch("src.main.get_settings_service", return_value=_settings_service(boards)),
            patch("src.main.board_client_from_board_dict", side_effect=lambda b: clients.get(b["id"])),
        ):
            service._build_board_clients()

        assert set(service.runtimes) == {"b1", "b2"}

    def test_board_without_credentials_gets_no_runtime(self, service):
        """Uses the REAL client factory: a board with no usable credential
        (no local key, cloud key, or note-array token) must yield no runtime."""
        boards = [_board("b1", "One"), _board("b2", "Two", local_api_key="", cloud_key="")]
        with patch("src.main.get_settings_service", return_value=_settings_service(boards)):
            service._build_board_clients(sync_cache=False)

        assert set(service.runtimes) == {"b1"}

    def test_unchanged_board_keeps_its_runtime_and_caches(self, service):
        """A diff-based rebuild must keep an unchanged board's runtime so its
        caches (last-sent content, silence state) survive editing another board."""
        boards = [_board("b1", "One")]
        original_client = MagicMock()

        with (
            patch("src.main.get_settings_service", return_value=_settings_service(boards)),
            patch("src.main.board_client_from_board_dict", return_value=original_client),
        ):
            service._build_board_clients(sync_cache=False)
            service.runtimes["b1"].last_active_page_content = "REMEMBER ME"

            # Rebuild with the same board config — runtime + cache must survive.
            service._build_board_clients(sync_cache=False)

        assert service.runtimes["b1"].client is original_client
        assert service.runtimes["b1"].last_active_page_content == "REMEMBER ME"

    def test_rebuild_prunes_removed_boards(self, service):
        service.runtimes = {"b-gone": BoardRuntime(client=MagicMock(), board_id="b-gone")}
        service._primary_board_id = "b-gone"
        boards = [_board("b2", "Two", port=7001)]
        with (
            patch("src.main.get_settings_service", return_value=_settings_service(boards)),
            patch("src.main.board_client_from_board_dict", side_effect=lambda b: MagicMock()),
        ):
            assert service.reinitialize_board_client() is True

        assert set(service.runtimes) == {"b2"}
        assert service._primary_board_id == "b2"
