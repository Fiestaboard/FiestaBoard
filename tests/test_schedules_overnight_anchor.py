"""Overnight windows belong to their start day, including validation coverage."""

from datetime import date, time

import pytest

from src.schedules.models import ScheduleEntry
from src.schedules.service import ScheduleService
from src.schedules.storage import ScheduleStorage


@pytest.fixture
def service(tmp_path, monkeypatch):
    service = ScheduleService(ScheduleStorage(str(tmp_path / "schedules.json")))
    monkeypatch.setattr(service, "_get_location", lambda: (None, None, "UTC"))
    return service


def add(service, **kwargs):
    entry = ScheduleEntry(page_id="night", start_time="23:00", end_time="02:00", **kwargs)
    service.storage.create(entry)
    return entry


@pytest.mark.parametrize(
    "today,day,hour,want",
    [
        (date(2026, 6, 15), "monday", 1, False),
        (date(2026, 6, 15), "monday", 23, True),
        (date(2026, 6, 16), "tuesday", 1, True),
        (date(2026, 6, 16), "tuesday", 2, False),
    ],
)
def test_weekly_window_uses_start_day(service, monkeypatch, today, day, hour, want):
    monkeypatch.setattr("src.schedules.service.get_today_in_timezone", lambda tz: today)
    add(service, day_pattern="custom", custom_days=["monday"])
    assert (service.get_active_schedule_entry(time(hour), day) is not None) is want


@pytest.mark.parametrize(
    "recurrence",
    [
        {"recurrence_type": "one_off_date", "one_off_date": "2026-12-31"},
        {"recurrence_type": "annual_date", "annual_date": "12-31"},
        {"recurrence_type": "one_off_date", "one_off_date": "2026-12-30", "one_off_end_date": "2026-12-31"},
        {"recurrence_type": "annual_date", "annual_date": "12-30", "annual_end_date": "12-31"},
    ],
)
@pytest.mark.parametrize("today,want", [(date(2026, 12, 30), False), (date(2027, 1, 1), True)])
def test_date_window_uses_start_date(service, monkeypatch, recurrence, today, want):
    monkeypatch.setattr("src.schedules.service.get_today_in_timezone", lambda tz: today)
    add(service, **recurrence)
    assert (service.get_active_schedule_entry(time(1), today.strftime("%A").lower()) is not None) is want


@pytest.mark.parametrize("day,want", [("monday", True), ("tuesday", False)])
def test_overlap_uses_day_of_actual_coverage(service, day, want):
    add(service, day_pattern="custom", custom_days=["monday"])
    service.storage.create(
        ScheduleEntry(page_id="morning", start_time="01:00", end_time="03:00", day_pattern="custom", custom_days=[day])
    )
    assert service.validate_schedules().valid is want


@pytest.mark.parametrize("start_day,next_day", [("monday", "tuesday"), ("sunday", "monday")])
def test_gap_coverage_moves_to_next_day(service, start_day, next_day):
    add(service, day_pattern="custom", custom_days=[start_day])
    gaps = service.validate_schedules().gaps
    assert [(g.start_time, g.end_time) for g in gaps if start_day in g.days] == [("00:00", "23:00")]
    assert [(g.start_time, g.end_time) for g in gaps if next_day in g.days] == [("02:00", "23:59")]


def test_sunrise_end_is_resolved_on_following_date(service, monkeypatch):
    monkeypatch.setattr("src.schedules.service.get_today_in_timezone", lambda tz: date(2026, 6, 16))

    def sun_times(**kwargs):
        return "23:00", "01:00" if kwargs["target_date"] == date(2026, 6, 15) else "02:00"

    monkeypatch.setattr("src.schedules.service.resolve_schedule_sun_times", sun_times)
    add(service, day_pattern="custom", custom_days=["monday"], end_type="sunrise")
    assert service.get_active_schedule_entry(time(1, 30), "tuesday") is not None
