"""A failed output recovery must not skip healthy boards later in the pass."""

import errno
import unittest
from unittest.mock import Mock, patch

from src.main import BoardRuntime, DisplayService
from src.outputs.hooks import DevicePoll


class TestOutputPollIsolation(unittest.TestCase):
    def setup_boards(self):
        service = DisplayService.__new__(DisplayService)
        first = BoardRuntime(Mock(), "first")
        other = BoardRuntime(Mock(), "other")
        for rt in (first, other):
            rt.last_active_page_content = "UNCHANGED"
            rt.last_active_page_id = "current-page"
        first.client.poll_device.return_value = DevicePoll(config={"host": "new-address.example"})
        other.client.poll_device.return_value = DevicePoll(restarted=True)
        service.runtimes = {"first": first, "other": other}
        settings = Mock()
        settings.is_paused.return_value = False
        settings.get_polling_settings.return_value.board_read_interval_local = 0
        return service, first, other, settings

    def one_poll_pass(self, service, settings):
        service.running = True

        def stop():
            service.running = False

        with (
            patch("src.main.get_settings_service", return_value=settings),
            patch.object(service, "_get_board_read_interval", return_value=0),
            patch.object(service, "_retry_failed_board_inits"),
            patch.object(service, "_poll_all_boards_once", side_effect=stop) as readback,
            patch.object(service, "_board_poll_tick", return_value=0),
            patch("src.main.time.sleep"),
        ):
            service._board_poll_loop()
            readback.assert_called_once()

    def test_save_failure_does_not_starve_another_boards_restart_recovery(self):
        service, first, other, settings = self.setup_boards()
        settings.update_board_output_config.side_effect = OSError(errno.ENOSPC, "synthetic disk full")
        with self.assertLogs("src.main", level="ERROR") as logs:
            self.one_poll_pass(service, settings)
        other.client.poll_device.assert_called_once()
        self.assertIsNone(other.last_active_page_content)
        other.client.clear_cache.assert_called_once()
        self.assertEqual(first.last_active_page_content, "UNCHANGED")
        first.client.clear_cache.assert_not_called()
        self.assertTrue(any("first" in line and "synthetic disk full" in line for line in logs.output))

    def test_recovery_can_retry_on_the_next_pass_without_quarantining_other_boards(self):
        service, first, other, settings = self.setup_boards()
        settings.update_board_output_config.side_effect = [OSError(errno.ENOSPC, "synthetic disk full"), True]
        with self.assertLogs("src.main", level="ERROR"):
            self.one_poll_pass(service, settings)
        other.client.poll_device.assert_called_once()
        self.one_poll_pass(service, settings)
        self.assertEqual(settings.update_board_output_config.call_count, 2)
        self.assertIsNone(first.last_active_page_content)
        first.client.clear_cache.assert_called_once()
        self.assertEqual(other.client.poll_device.call_count, 2)

    def test_paused_first_board_remains_untouched_and_second_recovers(self):
        service, first, other, settings = self.setup_boards()
        settings.is_paused.side_effect = lambda board_id: board_id == "first"
        self.one_poll_pass(service, settings)
        first.client.poll_device.assert_not_called()
        first.client.clear_cache.assert_not_called()
        settings.update_board_output_config.assert_not_called()
        self.assertEqual(first.last_active_page_content, "UNCHANGED")
        self.assertIsNone(other.last_active_page_content)
