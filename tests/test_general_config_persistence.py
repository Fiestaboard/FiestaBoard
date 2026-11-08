"""Rejected general settings must not leak into clock state or later saves."""

import errno
import json
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

INSTANT = datetime(2026, 7, 15, 12, tzinfo=UTC)
NEW_TIMEZONE = "America/New_York"


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return INSTANT.astimezone(tz) if tz is not None else INSTANT.replace(tzinfo=None)


@contextmanager
def general_client():
    import src.collections.service as collections_module
    import src.config_manager as config_module
    import src.pages.service as pages_module
    import src.schedules.service as schedules_module
    import src.settings.service as settings_module
    import src.time_service as time_module
    from src.config_api.routes import router as config_router
    from src.pages.models import PageCreate
    from src.schedules.models import ScheduleEntry
    from src.schedules.routes import router as schedules_router

    with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
        root = Path(directory)
        path = root / "config.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "general": {"timezone": "UTC", "instance_name": "Original", "refresh_interval_seconds": 45},
                    "plugins": {},
                }
            )
        )
        stack.enter_context(patch.dict(os.environ, {"FIESTABOARD_DATA_DIR": directory}))
        stack.enter_context(patch.object(config_module.ConfigManager, "_instance", None))
        for module, attribute in (
            (time_module, "_time_service"),
            (settings_module, "_settings_service"),
            (pages_module, "_page_service"),
            (schedules_module, "_schedule_service"),
            (collections_module, "_collection_service"),
        ):
            stack.enter_context(patch.object(module, attribute, None))
        stack.enter_context(patch.object(time_module, "datetime", FixedDatetime))
        stack.enter_context(patch("src.schedules.sun_times.datetime", FixedDatetime))
        manager = config_module.get_config_manager()
        settings = settings_module.get_settings_service()
        settings.set_schedule_enabled(True)
        pages = pages_module.get_page_service()
        morning = pages.create_page(PageCreate(name="Morning", type="template", template=["MORNING"]))
        fallback = pages.create_page(PageCreate(name="Fallback", type="template", template=["FALLBACK"]))
        schedules = schedules_module.get_schedule_service()
        schedules.storage.create(ScheduleEntry(page_id=morning.id, start_time="08:00", end_time="09:00"))
        schedules.storage.set_default_page_id(fallback.id)
        clock = time_module.get_time_service()
        app = FastAPI()
        app.include_router(config_router)
        app.include_router(schedules_router)
        with TestClient(app) as client:
            yield SimpleNamespace(
                client=client,
                manager=manager,
                path=path,
                clock=clock,
                time_module=time_module,
                morning=morning,
                fallback=fallback,
            )


def failed_write():
    return patch(
        "src.config_manager.write_json_atomic", side_effect=OSError(errno.ENOSPC, "synthetic config save failure")
    )


class TestGeneralConfigPersistence(unittest.TestCase):
    def reject_timezone(self, fixture):
        before = fixture.path.read_bytes()
        with failed_write():
            response = fixture.client.put("/config/general", json={"timezone": NEW_TIMEZONE})
        self.assertEqual(response.status_code, 500, response.text)
        self.assertEqual(fixture.path.read_bytes(), before)

    def assert_timezone_coherent(self, fixture, expected):
        self.assertEqual(fixture.manager.get_general()["timezone"], expected)
        self.assertEqual(fixture.client.get("/config/general").json()["timezone"], expected)
        self.assertEqual(fixture.time_module.get_time_service().default_timezone, expected)
        self.assertEqual(json.loads(fixture.path.read_text())["general"]["timezone"], expected)

    def test_rejected_timezone_keeps_the_running_config_and_clock(self):
        with general_client() as fixture:
            self.reject_timezone(fixture)
            self.assert_timezone_coherent(fixture, "UTC")
            self.assertIs(fixture.time_module.get_time_service(), fixture.clock)

    def test_successful_retry_uses_the_saved_timezone_for_actual_schedule_selection(self):
        with general_client() as fixture:
            self.reject_timezone(fixture)
            response = fixture.client.put("/config/general", json={"timezone": NEW_TIMEZONE})
            self.assertEqual(response.status_code, 200, response.text)
            active = fixture.client.get("/schedules/active/page").json()
            self.assertEqual(active["current_time"], "08:00", active)
            self.assertEqual(active["page_id"], fixture.morning.id, active)
            self.assert_timezone_coherent(fixture, NEW_TIMEZONE)

    def test_unrelated_general_save_does_not_commit_the_rejected_timezone(self):
        with general_client() as fixture:
            self.reject_timezone(fixture)
            response = fixture.client.put("/config/general", json={"instance_name": "Accepted name"})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["instance_name"], "Accepted name")
            self.assert_timezone_coherent(fixture, "UTC")

    def test_other_section_save_and_reload_do_not_commit_the_rejected_timezone(self):
        with general_client() as fixture:
            self.reject_timezone(fixture)
            self.assertTrue(fixture.manager.set_feature("silence_schedule", {"enabled": True}))
            from src.config_manager import ConfigManager

            self.assertEqual(json.loads(fixture.path.read_text())["general"]["timezone"], "UTC")
            with patch.object(ConfigManager, "_instance", None):
                reloaded = ConfigManager(config_path=str(fixture.path))
                self.assertIsNot(reloaded, fixture.manager)
                self.assertEqual(reloaded.get_general()["timezone"], "UTC")
                self.assertTrue(reloaded.get_feature("silence_schedule")["enabled"])

    def test_reader_and_later_writer_see_rollback_before_failure_is_reported(self):
        with general_client() as fixture:
            import src.config_manager as config_module

            reported = threading.Event()
            finish = threading.Event()
            real_write = config_module.write_json_atomic
            real_error = config_module.logger.error
            failed = False

            def first_write_fails(*args, **kwargs):
                nonlocal failed
                if not failed:
                    failed = True
                    raise OSError(errno.ENOSPC, "synthetic config save failure")
                return real_write(*args, **kwargs)

            def hold_report(message, *args, **kwargs):
                if str(message).startswith("Failed to update general settings"):
                    reported.set()
                    if not finish.wait(5):
                        raise AssertionError("failure-report barrier was not released")
                real_error(message, *args, **kwargs)

            with (
                patch.object(config_module, "write_json_atomic", side_effect=first_write_fails),
                patch.object(config_module.logger, "error", side_effect=hold_report),
                ThreadPoolExecutor(max_workers=1) as executor,
            ):
                future = executor.submit(fixture.manager.set_general, {"timezone": NEW_TIMEZONE})
                try:
                    self.assertTrue(reported.wait(5))
                    self.assertEqual(fixture.manager.get_general()["timezone"], "UTC")
                    self.assertTrue(fixture.manager.set_general({"instance_name": "Concurrent accepted"}))
                finally:
                    finish.set()
                self.assertFalse(future.result(timeout=5))
            self.assert_timezone_coherent(fixture, "UTC")
            self.assertEqual(fixture.manager.get_general()["instance_name"], "Concurrent accepted")

    def test_rejected_non_timezone_field_is_not_published(self):
        with general_client() as fixture:
            with failed_write():
                response = fixture.client.put("/config/general", json={"instance_name": "Rejected name"})
            self.assertEqual(response.status_code, 500, response.text)
            self.assertEqual(fixture.manager.get_general()["instance_name"], "Original")

    def test_ordinary_timezone_change_updates_clock_and_schedule(self):
        with general_client() as fixture:
            response = fixture.client.put("/config/general", json={"timezone": NEW_TIMEZONE})
            self.assertEqual(response.status_code, 200, response.text)
            self.assert_timezone_coherent(fixture, NEW_TIMEZONE)
            active = fixture.client.get("/schedules/active/page").json()
            self.assertEqual(active["page_id"], fixture.morning.id, active)

    def test_noop_timezone_preserves_cached_clock_and_other_fields(self):
        with general_client() as fixture:
            response = fixture.client.put("/config/general", json={"timezone": "UTC"})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIs(fixture.time_module.get_time_service(), fixture.clock)
            self.assertEqual(response.json()["instance_name"], "Original")
            self.assertEqual(response.json()["refresh_interval_seconds"], 45)
