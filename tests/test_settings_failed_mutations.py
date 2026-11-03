"""Rejected settings/default writes must not reach readers or a later save."""

import copy
import errno
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from src.schedules.models import ScheduleEntry
from src.schedules.storage import ScheduleStorage
from src.settings.service import SettingsService, TemporaryOverride


SETTINGS_WRITES = (
    ("output", lambda s: s.set_output_target("ui")),
    ("active primary", lambda s: s.set_active_page_id("rejected")),
    ("active secondary", lambda s: s.set_active_page_id("rejected", "b2")),
    ("clear active", lambda s: s.set_active_page_id(None)),
    ("polling", lambda s: s.set_polling_interval(45)),
    ("read intervals", lambda s: s.set_board_read_intervals(60, 240)),
    ("board type", lambda s: s.set_board_type("white")),
    ("devices", lambda s: s.set_devices(["note"])),
    ("boards", lambda s: s.set_boards([{"id": "b1", "device_type": "flagship", "name": "Rejected"}])),
    ("add board", lambda s: s.add_board({"id": "b3", "device_type": "note", "name": "Rejected"})),
    ("remove board", lambda s: s.remove_board("b2")),
    ("transition", lambda s: s.update_transition_settings(strategy="row")),
    ("output config", lambda s: s.update_board_output_config("b1", {"host": "192.0.2.1"})),
    ("pause primary", lambda s: s.set_paused(True)),
    ("pause secondary", lambda s: s.set_paused(True, "b2")),
    ("schedule primary", lambda s: s.set_schedule_enabled(True)),
    ("schedule secondary", lambda s: s.set_schedule_enabled(True, "b2")),
    ("schedule defer", lambda s: s.set_schedule_defer_on_reenable(True)),
    ("mqtt", lambda s: s.set_mqtt_settings({"enabled": True, "broker_host": "example.invalid"})),
    ("display", lambda s: s.update_display_settings({"reduce_motion": True})),
    ("location", lambda s: s.update_location_settings({"latitude": 10, "longitude": 20})),
    ("plugins", lambda s: s.update_plugin_settings({"auto_update": True})),
    ("wizard", lambda s: s.set_wizard_state("completed")),
    ("override", lambda s: s.set_temporary_override(TemporaryOverride(page_id="rejected"))),
    ("clear override", lambda s: s.clear_temporary_override()),
)


def settings_snapshot(service):
    sections = (
        "output",
        "active_page",
        "polling",
        "board",
        "schedule",
        "mqtt",
        "display",
        "location",
        "plugin",
    )
    result = {key: getattr(service, f"get_{key}_settings")().to_dict() for key in sections}
    override = service.peek_temporary_override()
    result["override"] = override.to_dict() if override else None
    result["wizard"] = service.get_wizard_state()
    return result


def seeded_settings(path):
    service = SettingsService(str(path))
    service.set_boards(
        [
            {"id": "b1", "device_type": "flagship", "name": "One"},
            {"id": "b2", "device_type": "note", "name": "Two"},
        ]
    )
    service.set_active_page_id("original")
    service.set_temporary_override(TemporaryOverride(page_id="original"))
    service.set_polling_interval(30)
    service.set_schedule_defer_on_reenable(False)
    service.update_plugin_settings({"auto_update": False})
    return service


class TestSettingsFailedMutations(unittest.TestCase):
    def test_rejected_settings_remain_unpublished_and_do_not_leak_into_later_save(self):
        for label, mutate in SETTINGS_WRITES:
            with self.subTest(setting=label), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "settings.json"
                service = seeded_settings(path)
                before = settings_snapshot(service)
                original_bytes = path.read_bytes()
                observed = []

                def refuse_commit(*args, **kwargs):
                    observed.append(settings_snapshot(service))
                    raise OSError(errno.ENOSPC, "synthetic disk full")

                with patch("src.atomic_io.os.replace", side_effect=refuse_commit):
                    with self.assertRaises(OSError):
                        mutate(service)
                self.assertEqual(path.read_bytes(), original_bytes)
                after_failure = settings_snapshot(service)
                service.set_polling_interval(90)
                expected = copy.deepcopy(before)
                expected["polling"]["interval_seconds"] = 90
                self.assertEqual(settings_snapshot(SettingsService(str(path))), expected)
                self.assertEqual(after_failure, before)
                self.assertEqual(observed, [before])

    def test_successful_settings_writes_publish_only_after_commit_and_survive_reload(self):
        for label, mutate in SETTINGS_WRITES:
            with self.subTest(setting=label), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "settings.json"
                service = seeded_settings(path)
                before = settings_snapshot(service)
                observed = []
                replace = os.replace

                def observe_commit(source, destination):
                    if Path(destination) == path:
                        observed.append(settings_snapshot(service))
                    return replace(source, destination)

                with patch("src.atomic_io.os.replace", side_effect=observe_commit):
                    mutate(service)
                self.assertEqual(observed, [before])
                after = settings_snapshot(service)
                self.assertNotEqual(after, before)
                self.assertEqual(settings_snapshot(SettingsService(str(path))), after)

    def test_concurrent_reader_does_not_observe_pending_write(self):
        with tempfile.TemporaryDirectory() as directory:
            service = seeded_settings(Path(directory) / "settings.json")
            entered = threading.Event()
            release = threading.Event()

            def refuse_commit(*args, **kwargs):
                entered.set()
                if not release.wait(timeout=5):
                    raise AssertionError("test did not release the pending write")
                raise OSError(errno.ENOSPC, "synthetic disk full")

            with ThreadPoolExecutor(max_workers=1) as pool:
                with patch("src.atomic_io.os.replace", side_effect=refuse_commit):
                    writer = pool.submit(service.set_polling_interval, 45)
                    try:
                        self.assertTrue(entered.wait(timeout=5))
                        self.assertEqual(service.get_polling_interval(), 30)
                    finally:
                        release.set()
                        with self.assertRaises(OSError):
                            writer.result(timeout=5)
            self.assertEqual(service.get_polling_interval(), 30)

    def test_invalid_second_read_interval_does_not_change_first_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            service = seeded_settings(Path(directory) / "settings.json")
            with self.assertRaises(ValueError):
                service.set_board_read_intervals(local_seconds=60, cloud_seconds=1)
            self.assertEqual(service.get_polling_settings().board_read_interval_local, 30)


class TestScheduleDefaultFailedMutations(unittest.TestCase):
    def test_rejected_default_set_or_clear_is_not_published_or_saved_later(self):
        for board in (None, "b1", "b2"):
            for requested in ("rejected", None):
                with self.subTest(board=board, requested=requested), tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "schedules.json"
                    service = ScheduleStorage(str(path))
                    service.set_default_page_id("legacy")
                    service.set_default_page_id("one", "b1")
                    service.set_default_page_id("two", "b2")
                    before = [service.get_default_page_id(b) for b in (None, "b1", "b2")]
                    original_bytes = path.read_bytes()
                    observed = []

                    def refuse_commit(*args, **kwargs):
                        observed.append([service.get_default_page_id(b) for b in (None, "b1", "b2")])
                        raise OSError(errno.ENOSPC, "synthetic disk full")

                    with patch("src.atomic_io.os.replace", side_effect=refuse_commit):
                        with self.assertRaises(OSError):
                            service.set_default_page_id(requested, board)
                    self.assertEqual(path.read_bytes(), original_bytes)
                    after_failure = [service.get_default_page_id(b) for b in (None, "b1", "b2")]
                    service.create(ScheduleEntry(id="accepted", page_id="page", start_time="09:00"))
                    reloaded = ScheduleStorage(str(path))
                    self.assertEqual([reloaded.get_default_page_id(b) for b in (None, "b1", "b2")], before)
                    self.assertEqual(after_failure, before)
                    self.assertEqual(observed, [before])

    def test_successful_default_clears_preserve_fallback_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schedules.json"
            service = ScheduleStorage(str(path))
            service.set_default_page_id("legacy")
            service.set_default_page_id("one", "b1")
            service.set_default_page_id(None, "b1")
            self.assertEqual(service.get_default_page_id("b1"), "legacy")
            service.set_default_page_id(None)
            self.assertIsNone(service.get_default_page_id("b1"))
            self.assertIsNone(ScheduleStorage(str(path)).get_default_page_id())

    def test_primary_default_and_legacy_clear_are_one_commit(self):
        from src.schedules.service import ScheduleService

        for failing_write in (1, 2):
            with self.subTest(failing_write=failing_write), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "schedules.json"
                storage = ScheduleStorage(str(path))
                storage.set_default_page_id("legacy")
                settings = seeded_settings(Path(directory) / "settings.json")
                service = ScheduleService(storage)
                before = path.read_bytes()
                replace = os.replace
                writes = 0

                def fail_commit(source, destination):
                    nonlocal writes
                    writes += 1
                    if writes == failing_write:
                        raise OSError(errno.ENOSPC, "synthetic disk full")
                    return replace(source, destination)

                with patch("src.schedules.service.get_settings_service", return_value=settings):
                    try:
                        with patch("src.atomic_io.os.replace", side_effect=fail_commit):
                            service.set_default_page("accepted")
                    except OSError:
                        self.assertEqual(path.read_bytes(), before)
                        self.assertEqual(service.get_default_page(), "legacy")
                    else:
                        reloaded = ScheduleStorage(str(path))
                        self.assertEqual(reloaded.get_default_page_id("b1"), "accepted")
                        self.assertIsNone(reloaded.get_default_page_id("b2"))
                        self.assertIsNone(reloaded.get_default_page_id())
