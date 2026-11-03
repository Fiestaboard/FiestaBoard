"""Staged settings/default writes preserve feature revisions and per-board data."""

import copy
import errno
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.schedules.service import ScheduleService
from src.schedules.storage import DefaultPageRevisionConflict, ScheduleStorage
from src.settings.service import CURRENT_SETTINGS_SCHEMA_VERSION, SettingsService


def seed(path):
    settings = SettingsService(str(path))
    settings.set_boards(
        [
            {"id": "one", "name": "Primary", "device_type": "flagship"},
            {"id": "two", "name": "Secondary", "device_type": "note"},
        ]
    )
    return settings


class TestSettingsFailureRevisions(unittest.TestCase):
    def test_per_board_preferences_publish_after_commit_without_mutating_retained_board(self):
        mutations = (
            lambda s, bid: s.update_polling_settings(
                {"polling_interval_seconds": 75, "board_read_interval_local": 60}, bid
            ),
            lambda s, bid: s.set_schedule_defer_on_reenable(True, bid),
        )
        for index, mutate in enumerate(mutations):
            for board_id in (None, "two"):
                with self.subTest(mutation=index, board=board_id), tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "settings.json"
                    settings = seed(path)
                    retained = settings.get_board_settings()
                    before_board = copy.deepcopy(retained.to_dict())
                    before = path.read_bytes()
                    revision = settings.runtime_revision
                    with patch("src.atomic_io.os.replace", side_effect=OSError(errno.ENOSPC, "synthetic disk full")):
                        with self.assertRaises(OSError):
                            mutate(settings, board_id)
                    self.assertEqual(settings.runtime_revision, revision)
                    self.assertEqual(retained.to_dict(), before_board)
                    self.assertEqual(settings.get_board_settings().to_dict(), before_board)
                    self.assertEqual(path.read_bytes(), before)
                    mutate(settings, board_id)
                    self.assertNotEqual(settings.runtime_revision, revision)
                    self.assertEqual(retained.to_dict(), before_board)
                    persisted = json.loads(path.read_text())
                    self.assertEqual(persisted["schema_version"], CURRENT_SETTINGS_SCHEMA_VERSION)
                    self.assertNotIn("runtime_revision", persisted)
                    target = board_id or "one"
                    other = "one" if target == "two" else "two"
                    reloaded = SettingsService(str(path))
                    self.assertEqual(reloaded.get_board_settings().to_dict(), settings.get_board_settings().to_dict())
                    if index == 0:
                        self.assertEqual(reloaded.get_polling_settings(target).interval_seconds, 75)
                        self.assertEqual(reloaded.get_polling_settings(other).interval_seconds, 15)
                    else:
                        self.assertTrue(reloaded.get_schedule_settings(target).defer_on_reenable)
                        self.assertFalse(reloaded.get_schedule_settings(other).defer_on_reenable)

    def test_failed_default_write_keeps_service_token_retryable_and_rejects_stale_retry(self):
        for board_id in (None, "two"):
            with self.subTest(board=board_id), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "schedules.json"
                settings = seed(Path(directory) / "settings.json")
                storage = ScheduleStorage(str(path))
                storage.set_default_page_id("legacy")
                service = ScheduleService(storage)
                with patch("src.schedules.service.get_settings_service", return_value=settings):
                    before = service.get_default_page_state(board_id)
                    disk = path.read_bytes()
                    with patch("src.atomic_io.os.replace", side_effect=OSError(errno.ENOSPC, "synthetic disk full")):
                        with self.assertRaises(OSError):
                            service.set_default_page("accepted", board_id, expected_revision=before["revision"])
                    self.assertEqual(service.get_default_page_state(board_id), before)
                    self.assertEqual(path.read_bytes(), disk)
                    accepted = service.set_default_page("accepted", board_id, expected_revision=before["revision"])
                    self.assertEqual(accepted["default_page_id"], "accepted")
                    self.assertNotEqual(accepted["revision"], before["revision"])
                    with self.assertRaises(DefaultPageRevisionConflict):
                        service.set_default_page(None, board_id, expected_revision=before["revision"])
                    self.assertEqual(service.get_default_page_state(board_id), accepted)
                    self.assertEqual(ScheduleStorage(str(path)).get_default_page_id(board_id or "one"), "accepted")

    def test_rejected_primary_reorder_keeps_default_token_but_success_invalidates_it(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = seed(Path(directory) / "settings.json")
            service = ScheduleService(ScheduleStorage(str(Path(directory) / "schedules.json")))
            with patch("src.schedules.service.get_settings_service", return_value=settings):
                before = service.get_default_page_state()
                reversed_boards = list(reversed(copy.deepcopy(settings.get_board_settings().boards)))
                with patch("src.atomic_io.os.replace", side_effect=OSError(errno.ENOSPC, "synthetic disk full")):
                    with self.assertRaises(OSError):
                        settings.set_boards(reversed_boards)
                self.assertEqual(settings.get_primary_board_id(), "one")
                self.assertEqual(service.get_default_page_state(), before)
                settings.set_boards(reversed_boards)
                self.assertEqual(settings.get_primary_board_id(), "two")
                with self.assertRaises(DefaultPageRevisionConflict):
                    service.set_default_page("page", expected_revision=before["revision"])
