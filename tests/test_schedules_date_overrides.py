"""Tests for date-specific schedule overrides (annual / one-off).

Covers issue #790 — specific-date schedules that override the weekly rotation
for birthdays, holidays, anniversaries, etc.
"""

import tempfile
from datetime import date, time, timedelta
from pathlib import Path

import pytest

from src.schedules.models import (
    ScheduleCreate,
    ScheduleEntry,
    _mmdd_in_range,
    _valid_iso_date,
    _valid_mmdd,
)
from src.schedules.service import ScheduleService
from src.schedules.storage import ScheduleStorage


@pytest.fixture
def temp_storage_file():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
        path = f.name
    yield path
    Path(path).unlink(missing_ok=True)


@pytest.fixture
def service(temp_storage_file):
    storage = ScheduleStorage(storage_file=temp_storage_file)
    return ScheduleService(storage=storage)


def _set_today(monkeypatch, today_date: date) -> None:
    """Pin the service's notion of "today" for deterministic resolution."""
    monkeypatch.setattr(
        "src.schedules.service.get_today_in_timezone",
        lambda _tz: today_date,
    )
    # _get_location uses settings_service; stub to skip real settings.
    monkeypatch.setattr(
        ScheduleService,
        "_get_location",
        lambda self: (None, None, "UTC"),
    )


class TestMMDDHelpers:
    def test_valid_mmdd_accepts_leap_day(self):
        assert _valid_mmdd("02-29")

    def test_valid_mmdd_rejects_feb_30(self):
        assert not _valid_mmdd("02-30")

    def test_valid_mmdd_rejects_bad_format(self):
        assert not _valid_mmdd("2-9")
        assert not _valid_mmdd("13-01")

    def test_valid_iso_date(self):
        assert _valid_iso_date("2026-06-15")
        assert not _valid_iso_date("2026-13-01")
        assert not _valid_iso_date("2026/06/15")

    def test_mmdd_range_single_day(self):
        assert _mmdd_in_range("06-15", "06-15", None)
        assert not _mmdd_in_range("06-16", "06-15", None)

    def test_mmdd_range_inclusive(self):
        assert _mmdd_in_range("06-15", "06-14", "06-16")
        assert _mmdd_in_range("06-14", "06-14", "06-16")
        assert _mmdd_in_range("06-16", "06-14", "06-16")
        assert not _mmdd_in_range("06-17", "06-14", "06-16")

    def test_mmdd_range_year_boundary_wrap(self):
        assert _mmdd_in_range("12-31", "12-30", "01-02")
        assert _mmdd_in_range("01-01", "12-30", "01-02")
        assert _mmdd_in_range("01-02", "12-30", "01-02")
        assert not _mmdd_in_range("01-03", "12-30", "01-02")
        assert not _mmdd_in_range("12-29", "12-30", "01-02")


class TestScheduleEntryValidation:
    def _base(self, **overrides):
        defaults = {
            "page_id": "p1",
            "start_time": "08:00",
            "end_time": "16:00",
        }
        defaults.update(overrides)
        return ScheduleEntry(**defaults)

    def test_weekly_default_is_unchanged(self):
        entry = self._base(day_pattern="weekdays")
        assert entry.recurrence_type == "weekly"
        assert entry.is_valid()

    def test_annual_requires_annual_date(self):
        entry = self._base(recurrence_type="annual_date")
        errors = entry.validate_config()
        assert any("annual_date" in e for e in errors)

    def test_annual_accepts_valid_mmdd(self):
        entry = self._base(recurrence_type="annual_date", annual_date="06-15")
        assert entry.is_valid()

    def test_annual_range_validates_end_date(self):
        entry = self._base(
            recurrence_type="annual_date",
            annual_date="12-24",
            annual_end_date="12-31",
        )
        assert entry.is_valid()

    def test_one_off_requires_date(self):
        entry = self._base(recurrence_type="one_off_date")
        assert not entry.is_valid()

    def test_one_off_end_date_must_be_on_or_after_start(self):
        entry = self._base(
            recurrence_type="one_off_date",
            one_off_date="2026-12-26",
            one_off_end_date="2026-12-24",
        )
        errors = entry.validate_config()
        assert any("on or after" in e for e in errors)

    def test_custom_days_not_required_for_annual(self):
        # day_pattern=custom would normally need custom_days, but on an
        # annual_date entry the day pattern is ignored.
        entry = self._base(
            recurrence_type="annual_date",
            annual_date="07-04",
            day_pattern="custom",
        )
        assert entry.is_valid()


class TestAppliesToDate:
    def _entry(self, **overrides):
        defaults = {
            "page_id": "p1",
            "start_time": "00:00",
            "end_time": "23:59",
        }
        defaults.update(overrides)
        return ScheduleEntry(**defaults)

    def test_weekly_always_true(self):
        entry = self._entry()
        assert entry.applies_to_date(date(2026, 1, 1))

    def test_annual_matches_same_mmdd(self):
        entry = self._entry(recurrence_type="annual_date", annual_date="06-15")
        assert entry.applies_to_date(date(2026, 6, 15))
        assert entry.applies_to_date(date(2099, 6, 15))
        assert not entry.applies_to_date(date(2026, 6, 16))

    def test_annual_range_year_boundary(self):
        entry = self._entry(
            recurrence_type="annual_date",
            annual_date="12-30",
            annual_end_date="01-02",
        )
        assert entry.applies_to_date(date(2026, 12, 31))
        assert entry.applies_to_date(date(2027, 1, 1))
        assert not entry.applies_to_date(date(2026, 12, 29))

    def test_one_off_matches_exact_date(self):
        entry = self._entry(recurrence_type="one_off_date", one_off_date="2026-06-15")
        assert entry.applies_to_date(date(2026, 6, 15))
        assert not entry.applies_to_date(date(2027, 6, 15))

    def test_one_off_range(self):
        entry = self._entry(
            recurrence_type="one_off_date",
            one_off_date="2026-06-15",
            one_off_end_date="2026-06-17",
        )
        assert entry.applies_to_date(date(2026, 6, 15))
        assert entry.applies_to_date(date(2026, 6, 16))
        assert entry.applies_to_date(date(2026, 6, 17))
        assert not entry.applies_to_date(date(2026, 6, 18))


class TestActivePageResolution:
    def test_annual_overrides_weekly(self, service, monkeypatch):
        # Weekly entry covering all days, plus an annual entry for "today".
        _set_today(monkeypatch, date(2026, 6, 15))
        weekly = service.create_schedule(
            ScheduleCreate(
                page_id="weekly-page",
                start_time="00:00",
                end_time=None,
                day_pattern="all",
            )
        )
        annual = service.create_schedule(
            ScheduleCreate(
                page_id="birthday-page",
                start_time="08:00",
                end_time="16:00",
                recurrence_type="annual_date",
                annual_date="06-15",
            )
        )

        # Inside the birthday window — annual wins
        assert service.get_active_page_id(time(10, 0), "monday") == "birthday-page"
        # Before the window — weekly wins
        assert service.get_active_page_id(time(7, 0), "monday") == "weekly-page"
        # After the window — weekly wins again
        assert service.get_active_page_id(time(17, 0), "monday") == "weekly-page"

        assert annual.id != weekly.id

    def test_one_off_overrides_annual_and_weekly(self, service, monkeypatch):
        _set_today(monkeypatch, date(2026, 6, 15))
        service.create_schedule(
            ScheduleCreate(
                page_id="weekly-page",
                start_time="00:00",
                end_time=None,
                day_pattern="all",
            )
        )
        service.create_schedule(
            ScheduleCreate(
                page_id="birthday-page",
                start_time="08:00",
                end_time="16:00",
                recurrence_type="annual_date",
                annual_date="06-15",
            )
        )
        service.create_schedule(
            ScheduleCreate(
                page_id="special-event-page",
                start_time="10:00",
                end_time="12:00",
                recurrence_type="one_off_date",
                one_off_date="2026-06-15",
            )
        )

        # Within one-off window
        assert service.get_active_page_id(time(11, 0), "monday") == "special-event-page"
        # Within annual but outside one-off
        assert service.get_active_page_id(time(9, 0), "monday") == "birthday-page"
        # Outside both
        assert service.get_active_page_id(time(17, 0), "monday") == "weekly-page"

    def test_annual_does_not_match_on_wrong_date(self, service, monkeypatch):
        _set_today(monkeypatch, date(2026, 6, 16))
        service.create_schedule(
            ScheduleCreate(
                page_id="weekly-page",
                start_time="00:00",
                end_time=None,
                day_pattern="all",
            )
        )
        service.create_schedule(
            ScheduleCreate(
                page_id="birthday-page",
                start_time="08:00",
                end_time="16:00",
                recurrence_type="annual_date",
                annual_date="06-15",
            )
        )
        # Wrong day — annual entry ignored
        assert service.get_active_page_id(time(10, 0), "tuesday") == "weekly-page"

    def test_annual_range_holiday(self, service, monkeypatch):
        _set_today(monkeypatch, date(2026, 12, 25))
        service.create_schedule(
            ScheduleCreate(
                page_id="weekly-page",
                start_time="00:00",
                end_time=None,
                day_pattern="all",
            )
        )
        service.create_schedule(
            ScheduleCreate(
                page_id="holiday-page",
                start_time="00:00",
                end_time=None,
                recurrence_type="annual_date",
                annual_date="12-24",
                annual_end_date="12-26",
            )
        )
        assert service.get_active_page_id(time(15, 0), "friday") == "holiday-page"

    def test_most_recent_annual_wins_among_overlapping(self, service, monkeypatch):
        _set_today(monkeypatch, date(2026, 6, 15))
        first = service.create_schedule(
            ScheduleCreate(
                page_id="annual-first",
                start_time="08:00",
                end_time="16:00",
                recurrence_type="annual_date",
                annual_date="06-15",
            )
        )
        # Force the second entry to be strictly newer
        first.created_at = first.created_at - timedelta(seconds=5)
        service.storage._schedules[first.id] = first

        service.create_schedule(
            ScheduleCreate(
                page_id="annual-second",
                start_time="08:00",
                end_time="16:00",
                recurrence_type="annual_date",
                annual_date="06-15",
            )
        )

        assert service.get_active_page_id(time(10, 0), "monday") == "annual-second"


class TestValidation:
    def test_annual_entries_skipped_in_overlap_detection(self, service, monkeypatch):
        # A weekly and an annual entry covering the same time slot must not be
        # reported as overlapping — date overrides are intentional.
        _set_today(monkeypatch, date(2026, 6, 15))
        service.create_schedule(
            ScheduleCreate(
                page_id="weekly-page",
                start_time="08:00",
                end_time="16:00",
                day_pattern="all",
            )
        )
        service.create_schedule(
            ScheduleCreate(
                page_id="birthday-page",
                start_time="08:00",
                end_time="16:00",
                recurrence_type="annual_date",
                annual_date="06-15",
            )
        )
        result = service.validate_schedules()
        assert result.overlaps == []


class TestStorageMigration:
    def test_loads_legacy_file_without_schema_version(self, tmp_path):
        """v0 file (no schema_version) loads, migrates, and gets recurrence_type=weekly."""
        import json

        legacy_path = tmp_path / "schedules.json"
        legacy_path.write_text(
            json.dumps(
                {
                    "schedules": [
                        {
                            "id": "abc",
                            "board_id": "",
                            "page_id": "page-1",
                            "start_time": "09:00",
                            "end_time": "17:00",
                            "day_pattern": "weekdays",
                            "enabled": True,
                            "created_at": "2026-01-01T00:00:00+00:00",
                        }
                    ],
                    "default_page_id": None,
                    "default_page_by_board": {},
                }
            )
        )

        storage = ScheduleStorage(storage_file=str(legacy_path))

        assert len(storage._schedules) == 1
        entry = next(iter(storage._schedules.values()))
        assert entry.recurrence_type == "weekly"

        # Resaved file should now carry schema_version = 1
        resaved = json.loads(legacy_path.read_text())
        assert resaved["schema_version"] == 1

        # And the v0 backup was created
        backup = legacy_path.with_suffix(".json.v0_backup")
        assert backup.exists()
