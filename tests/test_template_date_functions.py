"""Date/time functions in the inline expression language.

The language shipped with no date support at all, so "days until launch" or
"is it after 5pm" was impossible in a formula no matter what a plugin exposed —
authors needed a dedicated plugin for each one. These tests pin the semantics.

Every test injects ``__now__`` so the clock is deterministic; at render time the
engine injects the board's configured timezone instead.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.templates.engine import TemplateEngine
from src.templates.expressions import ensure_render_clock, evaluate

LA = ZoneInfo("America/Los_Angeles")

# Thursday, 2026-09-24 17:30 local.
NOW = datetime(2026, 9, 24, 17, 30, 0, tzinfo=LA)
CTX = {
    "__now__": NOW,
    "launch": {"date": "2026-12-25", "moment": "2026-09-24T19:45:00"},
    "bad": {"date": "not a date"},
}


class TestNowAndToday:
    def test_now_renders_as_date_and_time(self):
        assert evaluate("NOW()", CTX) == "2026-09-24 17:30"

    def test_today_truncates_to_midnight(self):
        assert evaluate("TODAY()", CTX) == "2026-09-24 00:00"

    def test_now_is_comparable_to_a_parsed_date(self):
        assert evaluate('IF(NOW() > DATE("2026-01-01"), "AFTER", "BEFORE")', CTX) == "AFTER"


class TestDateParsing:
    def test_parses_iso_date(self):
        assert evaluate('DATE("2026-12-25")', CTX) == "2026-12-25 00:00"

    def test_parses_iso_datetime(self):
        assert evaluate('DATE("2026-12-25T08:15:00")', CTX) == "2026-12-25 08:15"

    def test_parses_a_plugin_variable(self):
        assert evaluate("DATE(launch.date)", CTX) == "2026-12-25 00:00"

    def test_unparseable_is_value_error(self):
        assert evaluate("DATE(bad.date)", CTX) == "#VALUE"

    def test_date_of_a_date_is_idempotent(self):
        assert evaluate("DATE(DATE(launch.date))", CTX) == "2026-12-25 00:00"


class TestDateParts:
    def test_year_month_day(self):
        assert evaluate("YEAR(DATE(launch.date))", CTX) == "2026"
        assert evaluate("MONTH(DATE(launch.date))", CTX) == "12"
        assert evaluate("DAY(DATE(launch.date))", CTX) == "25"

    def test_hour_and_minute(self):
        assert evaluate("HOUR(NOW())", CTX) == "17"
        assert evaluate("MINUTE(NOW())", CTX) == "30"

    def test_weekday_is_iso_monday_is_one(self):
        # 2026-09-24 is a Thursday.
        assert evaluate("WEEKDAY(NOW())", CTX) == "4"

    def test_parts_accept_an_iso_string_directly(self):
        assert evaluate("YEAR(launch.date)", CTX) == "2026"

    def test_after_5pm_check(self):
        assert evaluate('IF(HOUR(NOW()) >= 17, "EVENING", "DAY")', CTX) == "EVENING"


class TestDateDiff:
    def test_days_between_defaults_to_days(self):
        assert evaluate('DATEDIFF(TODAY(), DATE("2026-12-25"))', CTX) == "92"

    def test_countdown_reads_naturally(self):
        assert evaluate('DATEDIFF(TODAY(), DATE(launch.date)) & " DAYS"', CTX) == "92 DAYS"

    def test_negative_when_end_is_in_the_past(self):
        assert evaluate('DATEDIFF(TODAY(), DATE("2026-09-20"))', CTX) == "-4"

    def test_hours_unit(self):
        assert evaluate('DATEDIFF(NOW(), DATE(launch.moment), "hours")', CTX) == "2"

    def test_minutes_unit(self):
        assert evaluate('DATEDIFF(NOW(), DATE(launch.moment), "minutes")', CTX) == "135"

    def test_weeks_unit(self):
        assert evaluate('DATEDIFF(TODAY(), DATE("2026-10-08"), "weeks")', CTX) == "2"

    def test_unknown_unit_is_value_error(self):
        assert evaluate('DATEDIFF(TODAY(), TODAY(), "fortnights")', CTX) == "#VALUE"


class TestDateAdd:
    def test_adds_days_by_default(self):
        assert evaluate("DATEADD(TODAY(), 7)", CTX) == "2026-10-01 00:00"

    def test_subtracts_with_a_negative_amount(self):
        assert evaluate("DATEADD(TODAY(), -1)", CTX) == "2026-09-23 00:00"

    def test_adds_hours(self):
        assert evaluate('DATEADD(NOW(), 3, "hours")', CTX) == "2026-09-24 20:30"

    def test_adds_months_clamping_to_month_end(self):
        assert evaluate('DATEADD(DATE("2026-01-31"), 1, "months")', CTX) == "2026-02-28 00:00"


class TestFormatDate:
    def test_friendly_tokens(self):
        assert evaluate('FORMATDATE(NOW(), "MM/DD")', CTX) == "09/24"

    def test_short_month_and_weekday_names(self):
        assert evaluate('FORMATDATE(NOW(), "ddd MMM DD")', CTX) == "THU SEP 24"

    def test_twelve_hour_clock(self):
        assert evaluate('FORMATDATE(NOW(), "hh:mm AP")', CTX) == "5:30 PM"

    def test_twenty_four_hour_clock(self):
        assert evaluate('FORMATDATE(NOW(), "HH:mm")', CTX) == "17:30"

    def test_two_digit_year(self):
        assert evaluate('FORMATDATE(NOW(), "YY")', CTX) == "26"

    def test_literal_text_survives(self):
        assert evaluate('FORMATDATE(NOW(), "DD of MMM")', CTX) == "24 of SEP"


class TestClockFallback:
    def test_uses_the_configured_clock_when_context_has_no_now(self):
        # No ``__now__``: falls back to the app's time service rather than
        # erroring, so a bare NOW() works in every caller.
        rendered = evaluate("YEAR(NOW())", {})
        assert rendered.isdigit() and int(rendered) >= 2026


class TestDatesInsideArrayFunctions:
    def test_sort_by_a_date_field(self):
        ctx = {
            "__now__": NOW,
            "cal": {
                "events": [
                    {"name": "B", "when": "2026-09-26"},
                    {"name": "A", "when": "2026-09-25"},
                ]
            },
        }
        assert evaluate('FOREACH(SORT(cal.events, "when"), item.name)', ctx) == "A\nB"

    def test_days_until_each_event(self):
        ctx = {
            "__now__": NOW,
            "cal": {"events": [{"name": "A", "when": "2026-09-27"}]},
        }
        out = evaluate('FOREACH(cal.events, item.name & " IN " & DATEDIFF(TODAY(), DATE(item.when)))', ctx)
        assert out == "A IN 3"


class TestRenderClockIsPinnedPerRender:
    """One board render sees one instant.

    Each date function resolves "now" independently, so before the engine
    pinned the clock two rows of the same board could land on either side of
    a minute — or a midnight — boundary.
    """

    @staticmethod
    def _advancing_clock(monkeypatch):
        """Make the app clock report a later instant on every single call."""
        ticks = iter(NOW + timedelta(days=i, minutes=i) for i in range(1, 100))

        class _Clock:
            def get_current_time(self):
                return next(ticks)

        monkeypatch.setattr("src.time_service.get_time_service", lambda: _Clock())

    def test_every_line_of_one_render_shares_the_same_instant(self, monkeypatch):
        self._advancing_clock(monkeypatch)

        rendered = TemplateEngine().render_lines(
            [
                "{{= NOW() }}",
                "{{= NOW() }}",
                "{{= TODAY() }}",
                '{{= FORMATDATE(NOW(), "DD MMM") }}',
            ],
            {},
        )
        lines = [line.strip() for line in rendered.split("\n")]

        # The first tick is 2026-09-25 17:31; a second reading of the clock
        # would be a day and a minute later.
        assert lines[0] == "2026-09-25 17:31"
        assert lines[1] == lines[0]
        assert lines[2] == "2026-09-25 00:00"
        assert lines[3] == "25 SEP"

    def test_direct_render_also_pins_one_instant(self, monkeypatch):
        self._advancing_clock(monkeypatch)

        assert TemplateEngine().render("{{= NOW() }}|{{= NOW() }}", {}) == "2026-09-25 17:31|2026-09-25 17:31"

    def test_ensure_render_clock_leaves_the_callers_context_alone(self, monkeypatch):
        self._advancing_clock(monkeypatch)
        context: dict = {"weather": {"temp": 72}}

        pinned = ensure_render_clock(context)

        assert context == {"weather": {"temp": 72}}
        assert isinstance(pinned["__now__"], datetime)

    def test_an_already_pinned_context_is_returned_unchanged(self):
        context = {"__now__": NOW}

        assert ensure_render_clock(context) is context
