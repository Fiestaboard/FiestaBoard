"""Replies from a retired output must not update its replacement."""

import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.main import BoardRuntime, DisplayService
from src.outputs.hooks import DevicePoll
from src.outputs.native_playlist import NativePageSelection


class TestOutputPollEpoch(unittest.TestCase):
    @staticmethod
    def runtime(board_id):
        rt = BoardRuntime(Mock(), board_id)
        rt.last_active_page_content = "CURRENT"
        rt.last_active_page_id = "page"
        return rt

    def test_retired_poll_cannot_save_moved_settings_or_invalidate_replacement(self):
        reports = (
            DevicePoll(config={"host": "old-discovered.example"}),
            DevicePoll(restarted=True),
            DevicePoll(overwritten=True),
            DevicePoll(native_selection=NativePageSelection("old-page")),
        )
        for news in reports:
            for replace in (False, True):
                with self.subTest(news=news, replace=replace):
                    service = DisplayService.__new__(DisplayService)
                    old = self.runtime("board")
                    old.native_playlist = SimpleNamespace(entries=[SimpleNamespace(page_id="old-page")])
                    old.native_selection = NativePageSelection("before")
                    replacement = self.runtime("board")
                    other = self.runtime("other")
                    service.runtimes = {"board": old, "other": other}
                    entered, release = threading.Event(), threading.Event()

                    def poll(news=news, entered=entered, release=release):
                        entered.set()
                        if not release.wait(5):
                            raise AssertionError("test did not release poll")
                        return news

                    old.client.poll_device.side_effect = poll
                    other.client.poll_device.return_value = DevicePoll(restarted=True)
                    settings = Mock()
                    settings.is_paused.return_value = False
                    settings.is_auto_restore.return_value = True
                    with (
                        patch("src.main.get_settings_service", return_value=settings),
                        ThreadPoolExecutor(1) as executor,
                    ):
                        future = executor.submit(service._poll_output_devices)
                        try:
                            self.assertTrue(entered.wait(5))
                            if replace:
                                service.runtimes["board"] = replacement
                            else:
                                del service.runtimes["board"]
                            release.set()
                            future.result(timeout=5)
                        finally:
                            release.set()
                    settings.update_board_output_config.assert_not_called()
                    self.assertEqual(replacement.last_active_page_content, "CURRENT")
                    replacement.client.clear_cache.assert_not_called()
                    self.assertEqual(old.native_selection, NativePageSelection("before"))
                    self.assertFalse(old.showing_out_of_band)
                    self.assertIsNone(old.overwritten_at)
                    self.assertIsNone(other.last_active_page_content)
                    other.client.clear_cache.assert_called_once()

    def test_current_poll_still_persists_move_and_invalidates_only_its_board(self):
        service = DisplayService.__new__(DisplayService)
        current, other = self.runtime("board"), self.runtime("other")
        service.runtimes = {"board": current, "other": other}
        current.client.poll_device.return_value = DevicePoll(config={"host": "moved.example"})
        other.client.poll_device.return_value = None
        settings = Mock()
        settings.is_paused.return_value = False
        with patch("src.main.get_settings_service", return_value=settings):
            service._poll_output_devices()
        settings.update_board_output_config.assert_called_once_with("board", {"host": "moved.example"})
        current.client.clear_cache.assert_called_once()
        self.assertIsNone(current.last_active_page_content)
        self.assertEqual(other.last_active_page_content, "CURRENT")
