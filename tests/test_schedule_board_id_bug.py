"""Tests for schedule board_id propagation in DisplayService polling.

Bug fix: check_and_send_active_page() and _get_active_ref_id() were calling
schedule_service.get_active_page_id() without passing the active board's ID.
Schedules created with a real board_id (e.g., from multi-board UI) were
silently ignored because the polling loop only looked for board_id="".
"""

from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest


class TestCheckAndSendActivePageBoardId:
    """Test that check_and_send_active_page passes board_id to schedule service."""

    @pytest.fixture
    def service_with_board(self):
        """Create a DisplayService with mocked dependencies that has a board with ID."""
        with (
            patch("src.main.Config") as mock_config,
            patch("src.main.get_settings_service") as mock_get_settings,
            patch("src.main.get_page_service") as mock_get_page,
            patch("src.main.get_schedule_service") as mock_get_schedule,
            patch("src.main.get_carousel_service"),
            patch("src.main.get_trigger_service") as mock_get_trigger,
        ):
            mock_config.validate.return_value = True
            mock_config.get_summary.return_value = {}
            mock_config.get_transition_settings.return_value = {"strategy": None}
            mock_config.is_silence_mode_active.return_value = False

            settings_service = Mock()
            settings_service.is_schedule_enabled.return_value = True
            settings_service.get_polling_interval.return_value = 60
            # Board has a real ID (not empty string)
            board_settings = Mock()
            board_settings.boards = [{"id": "board-abc-123", "name": "My Board"}]
            settings_service.get_board_settings.return_value = board_settings
            mock_get_settings.return_value = settings_service

            schedule_service = Mock()
            schedule_service.get_active_page_id.return_value = "page-1"
            mock_get_schedule.return_value = schedule_service

            page_service = Mock()
            mock_page = Mock()
            mock_page.id = "page-1"
            page_service.get_page.return_value = mock_page
            preview = Mock()
            preview.available = True
            preview.formatted = "Hello World"
            page_service.preview_page.return_value = preview
            mock_get_page.return_value = page_service

            # Trigger service returns no active triggers
            trigger_service = Mock()
            trigger_service.get_active_trigger.return_value = None
            mock_get_trigger.return_value = trigger_service

            from src.main import DisplayService

            svc = DisplayService()
            svc.vb_client = Mock()
            svc.vb_client.send_formatted.return_value = True

            yield svc, schedule_service

    def test_check_and_send_passes_board_id_to_schedule(self, service_with_board):
        """check_and_send_active_page must pass the first board's ID to get_active_page_id."""
        svc, schedule_service = service_with_board

        mock_now = datetime(2025, 6, 15, 12, 0, tzinfo=UTC)
        mock_time_service = Mock()
        mock_time_service.get_current_time.return_value = mock_now

        with (
            patch.object(svc, "_check_trigger_override", return_value=None),
            patch("src.time_service.get_time_service", return_value=mock_time_service),
        ):
            svc.check_and_send_active_page()

            # The schedule service MUST be called with board_id="board-abc-123"
            schedule_service.get_active_page_id.assert_called_once()
            call_kwargs = schedule_service.get_active_page_id.call_args
            # board_id should be passed (either as kwarg or positional)
            assert call_kwargs.kwargs.get("board_id") == "board-abc-123" or (
                len(call_kwargs.args) >= 3 and call_kwargs.args[2] == "board-abc-123"
            ), f"Expected board_id='board-abc-123', got call: {call_kwargs}"


class TestGetActiveRefIdBoardId:
    """Test that _get_active_ref_id passes board_id to schedule service."""

    @pytest.fixture
    def service_with_board(self):
        """Create a DisplayService with mocked dependencies that has a board with ID."""
        with (
            patch("src.main.Config") as mock_config,
            patch("src.main.get_settings_service") as mock_get_settings,
            patch("src.main.get_page_service"),
            patch("src.main.get_schedule_service") as mock_get_schedule,
            patch("src.main.get_trigger_service"),
        ):
            mock_config.validate.return_value = True
            mock_config.get_summary.return_value = {}
            mock_config.get_transition_settings.return_value = {"strategy": None}

            settings_service = Mock()
            settings_service.is_schedule_enabled.return_value = True
            board_settings = Mock()
            board_settings.boards = [{"id": "board-xyz-789", "name": "Berlin Board"}]
            settings_service.get_board_settings.return_value = board_settings
            mock_get_settings.return_value = settings_service

            schedule_service = Mock()
            schedule_service.get_active_page_id.return_value = "page-2"
            mock_get_schedule.return_value = schedule_service

            from src.main import DisplayService

            svc = DisplayService()

            yield svc, schedule_service

    def test_get_active_ref_id_passes_board_id(self, service_with_board):
        """_get_active_ref_id must pass the first board's ID to get_active_page_id."""
        svc, schedule_service = service_with_board

        mock_now = datetime(2025, 6, 15, 14, 0, tzinfo=UTC)
        mock_time_service = Mock()
        mock_time_service.get_current_time.return_value = mock_now

        with patch("src.time_service.get_time_service", return_value=mock_time_service):
            result = svc._get_active_ref_id()

            assert result == "page-2"
            schedule_service.get_active_page_id.assert_called_once()
            call_kwargs = schedule_service.get_active_page_id.call_args
            assert call_kwargs.kwargs.get("board_id") == "board-xyz-789" or (
                len(call_kwargs.args) >= 3 and call_kwargs.args[2] == "board-xyz-789"
            ), f"Expected board_id='board-xyz-789', got call: {call_kwargs}"
