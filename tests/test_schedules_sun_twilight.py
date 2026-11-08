"""Real solar events and persisted schedule HTTP when civil twilight is absent."""

import json
import os
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from astral import Observer
from astral.sun import sunrise, sunset
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.schedules.sun_times import get_sun_times, resolve_schedule_sun_times

DAY = date(2026, 6, 21)
LATITUDE = 64.1466
LONGITUDE = -21.9426
TIMEZONE = "Atlantic/Reykjavik"


@contextmanager
def solar_schedule_client():
    """Real config/stores/routers; only the clock is fixed, with no board output."""
    import src.collections.service as collection_module
    import src.config_manager as config_module
    import src.pages.service as pages_module
    import src.schedules.routes as routes
    import src.schedules.service as schedule_module
    import src.settings.service as settings_module
    from src.pages.routes import router as page_router

    with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
        root = Path(directory)
        (root / "config.json").write_text(
            json.dumps({"schema_version": 2, "general": {"timezone": TIMEZONE}, "plugins": {}})
        )
        stack.enter_context(patch.dict(os.environ, {"FIESTABOARD_DATA_DIR": str(root)}))
        stack.enter_context(patch.object(config_module.ConfigManager, "_instance", None))
        modules = (
            (settings_module, "_settings_service"),
            (schedule_module, "_schedule_service"),
            (pages_module, "_page_service"),
            (collection_module, "_collection_service"),
        )
        for module, attribute in modules:
            stack.enter_context(patch.object(module, attribute, None))
        settings = settings_module.get_settings_service()
        settings.update_location_settings({"latitude": LATITUDE, "longitude": LONGITUDE})
        settings.set_schedule_enabled(True)
        stack.enter_context(patch("src.schedules.sun_times.get_today_in_timezone", return_value=DAY))
        stack.enter_context(patch.object(schedule_module, "get_today_in_timezone", return_value=DAY))
        clock = SimpleNamespace(get_current_time=lambda: datetime(2026, 6, 21, 3, 0, tzinfo=ZoneInfo(TIMEZONE)))
        stack.enter_context(patch.object(routes, "get_time_service", return_value=clock))
        app = FastAPI()
        app.include_router(page_router)
        app.include_router(routes.router)
        with TestClient(app) as client:
            page = client.post(
                "/pages",
                json={
                    "name": "Solar fixture",
                    "type": "template",
                    "device_type": "flagship",
                    "template": ["SUN", "", "", "", "", ""],
                },
            )
            assert page.status_code == 201, page.text
            created = client.post(
                "/schedules",
                json={
                    "page_id": page.json()["id"],
                    "start_time": "12:00",
                    "end_time": "23:59",
                    "day_pattern": "all",
                    "start_type": "sunrise",
                },
            )
            assert created.status_code == 201, created.text
            yield client, created.json(), page.json()["id"], modules


class TestSunTimesWithoutCivilTwilight(unittest.TestCase):
    def test_primary_events_available_without_civil_twilight(self):
        for latitude, longitude, timezone in (
            (LATITUDE, LONGITUDE, TIMEZONE),
            (64.8378, -147.7164, "America/Anchorage"),
        ):
            with self.subTest(timezone=timezone):
                observer = Observer(latitude, longitude)
                expected = {
                    "sunrise": sunrise(observer, date=DAY, tzinfo=ZoneInfo(timezone)),
                    "sunset": sunset(observer, date=DAY, tzinfo=ZoneInfo(timezone)),
                }
                self.assertEqual(
                    get_sun_times(latitude, longitude, DAY, timezone),
                    expected,
                    "Available sunrise/sunset must not depend on civil dawn/dusk",
                )

    def test_schedule_http_exposes_real_sunrise_instead_of_fallback(self):
        with solar_schedule_client() as (client, created, _, _):
            expected = sunrise(Observer(LATITUDE, LONGITUDE), date=DAY, tzinfo=ZoneInfo(TIMEZONE)).strftime("%H:%M")
            self.assertEqual(created["resolved_start_time"], expected)
            self.assertEqual(client.get("/schedules/" + created["id"]).json()["resolved_start_time"], expected)

    def test_schedule_http_selects_page_after_available_sunrise(self):
        with solar_schedule_client() as (client, _, page_id, _):
            response = client.get("/schedules/active/page")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json()["page_id"],
                page_id,
                "03:00 is after the actual 02:56 sunrise, before the 12:00 fallback",
            )

    def test_persisted_location_and_schedule_select_page_after_reload(self):
        with solar_schedule_client() as (client, _, page_id, modules):
            from src.config_manager import ConfigManager

            ConfigManager._instance = None
            for module, attribute in modules:
                setattr(module, attribute, None)
            response = client.get("/schedules/active/page")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["page_id"], page_id)

    def test_true_polar_day_retains_stored_fallback(self):
        self.assertIsNone(get_sun_times(89.0, 0.0, DAY, "UTC"))
        self.assertEqual(
            resolve_schedule_sun_times("sunrise", 0, "06:00", "sunset", 0, "20:00", 89.0, 0.0, DAY, "UTC"),
            ("06:00", "20:00"),
        )


if __name__ == "__main__":
    unittest.main()
