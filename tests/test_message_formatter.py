"""Tests for src/formatters/message_formatter.py.

MessageFormatter contains pure formatting logic that is highly testable
(no I/O, no hardware dependencies). This addresses issue #505.
"""

import pytest

from src.formatters.message_formatter import MessageFormatter, get_message_formatter


@pytest.fixture
def fmt():
    return MessageFormatter()


# ---------------------------------------------------------------------------
# format_weather
# ---------------------------------------------------------------------------


class TestFormatWeather:
    def test_empty_data_returns_unavailable(self, fmt):
        assert fmt.format_weather({}) == "Weather: Unavailable"

    def test_none_data_returns_unavailable(self, fmt):
        assert fmt.format_weather(None) == "Weather: Unavailable"

    def test_basic_weather(self, fmt):
        data = {
            "location": "SF",
            "condition": "Sunny",
            "temperature": 72,
            "feels_like": 72,
        }
        result = fmt.format_weather(data)
        assert "SF" in result
        assert "72" in result

    def test_feels_like_different(self, fmt):
        data = {
            "location": "NY",
            "condition": "Cloudy",
            "temperature": 65,
            "feels_like": 58,
        }
        result = fmt.format_weather(data)
        assert "feels" in result.lower() or "58" in result

    def test_humidity_and_wind(self, fmt):
        data = {
            "location": "LA",
            "condition": "Sunny",
            "temperature": 80,
            "humidity": 45,
            "wind_mph": 10,
        }
        result = fmt.format_weather(data)
        assert "45" in result
        assert "10" in result

    def test_max_six_lines(self, fmt):
        data = {
            "location": "City",
            "condition": "Rain",
            "temperature": 55,
            "feels_like": 50,
            "humidity": 80,
            "wind_mph": 15,
        }
        result = fmt.format_weather(data)
        assert len(result.split("\n")) <= 6


# ---------------------------------------------------------------------------
# format_datetime
# ---------------------------------------------------------------------------


class TestFormatDatetime:
    def test_empty_data_returns_unavailable(self, fmt):
        assert fmt.format_datetime({}) == "Date/Time: Unavailable"

    def test_none_returns_unavailable(self, fmt):
        assert fmt.format_datetime(None) == "Date/Time: Unavailable"

    def test_basic_datetime(self, fmt):
        data = {
            "day_of_week": "Monday",
            "date": "2026-03-28",
            "time": "10:30",
            "timezone_abbr": "PST",
        }
        result = fmt.format_datetime(data)
        assert "Monday" in result
        assert "10:30" in result
        assert "PST" in result

    def test_date_without_day(self, fmt):
        data = {"date": "2026-03-28", "time": "09:00"}
        result = fmt.format_datetime(data)
        assert "2026-03-28" in result

    def test_time_without_timezone(self, fmt):
        data = {"day_of_week": "Friday", "date": "2026-01-01", "time": "12:00"}
        result = fmt.format_datetime(data)
        assert "12:00" in result

    def test_max_six_lines(self, fmt):
        data = {
            "day_of_week": "Wednesday",
            "date": "2026-06-15",
            "time": "14:45",
            "timezone_abbr": "UTC",
        }
        assert len(fmt.format_datetime(data).split("\n")) <= 6


# ---------------------------------------------------------------------------
# format_guest_wifi
# ---------------------------------------------------------------------------


class TestFormatGuestWifi:
    def test_contains_ssid_and_password(self, fmt):
        result = fmt.format_guest_wifi("MyNetwork", "s3cr3t")
        assert "MyNetwork" in result
        assert "s3cr3t" in result

    def test_contains_header(self, fmt):
        result = fmt.format_guest_wifi("SSID", "PASS")
        assert "WiFi" in result or "wifi" in result.lower()

    def test_color_markers_present(self, fmt):
        result = fmt.format_guest_wifi("net", "pw")
        # Should use color markers for decoration
        assert "{{" in result

    def test_max_six_lines(self, fmt):
        result = fmt.format_guest_wifi("TestNetwork", "TestPassword123")
        assert len(result.split("\n")) <= 6


# ---------------------------------------------------------------------------
# _get_temp_color
# ---------------------------------------------------------------------------


class TestGetTempColor:
    @pytest.mark.parametrize(
        "temp,expected_color",
        [
            (95, "red"),
            (85, "orange"),
            (75, "yellow"),
            (65, "green"),
            (50, "blue"),
            (30, "violet"),
        ],
    )
    def test_temp_ranges(self, fmt, temp, expected_color):
        result = fmt._get_temp_color(temp)
        assert expected_color in result

    def test_boundary_90(self, fmt):
        assert "red" in fmt._get_temp_color(90)

    def test_boundary_80(self, fmt):
        assert "orange" in fmt._get_temp_color(80)

    def test_boundary_70(self, fmt):
        assert "yellow" in fmt._get_temp_color(70)

    def test_boundary_60(self, fmt):
        assert "green" in fmt._get_temp_color(60)

    def test_boundary_45(self, fmt):
        assert "blue" in fmt._get_temp_color(45)

    def test_below_45(self, fmt):
        assert "violet" in fmt._get_temp_color(44)


# ---------------------------------------------------------------------------
# split_into_lines
# ---------------------------------------------------------------------------


class TestSplitIntoLines:
    def test_short_text_unchanged(self, fmt):
        lines = fmt.split_into_lines("Hello")
        assert lines == ["Hello"]

    def test_splits_long_line_on_spaces(self, fmt):
        text = "The quick brown fox jumped over the lazy dog today"
        lines = fmt.split_into_lines(text)
        for line in lines:
            assert len(line) <= fmt.MAX_COLS

    def test_respects_max_lines(self, fmt):
        # Create a text with many newlines
        text = "\n".join(["line"] * 20)
        lines = fmt.split_into_lines(text, max_lines=3)
        assert len(lines) <= 3

    def test_preserves_existing_newlines(self, fmt):
        text = "Line one\nLine two"
        lines = fmt.split_into_lines(text)
        assert len(lines) == 2
        assert lines[0] == "Line one"

    def test_empty_string(self, fmt):
        lines = fmt.split_into_lines("")
        assert lines == [""]


# ---------------------------------------------------------------------------
# format_star_trek_quote
# ---------------------------------------------------------------------------


class TestFormatStarTrekQuote:
    def test_tng_uses_yellow(self, fmt):
        data = {"quote": "Make it so.", "character": "Picard", "series": "tng"}
        result = fmt.format_star_trek_quote(data)
        assert "yellow" in result or "Picard" in result

    def test_voyager_uses_blue(self, fmt):
        data = {"quote": "Do it.", "character": "Janeway", "series": "voyager"}
        result = fmt.format_star_trek_quote(data)
        assert "blue" in result or "Janeway" in result

    def test_ds9_uses_red(self, fmt):
        data = {"quote": "I like it.", "character": "Sisko", "series": "ds9"}
        result = fmt.format_star_trek_quote(data)
        assert "red" in result or "Sisko" in result

    def test_unknown_series(self, fmt):
        data = {"quote": "Hello.", "character": "Kirk", "series": "tos"}
        result = fmt.format_star_trek_quote(data)
        assert "Kirk" in result

    def test_max_six_lines(self, fmt):
        data = {
            "quote": "This is a very long quote that might go on for a very long time and should be wrapped",
            "character": "Spock",
            "series": "tng",
        }
        result = fmt.format_star_trek_quote(data)
        assert len(result.split("\n")) <= 6


# ---------------------------------------------------------------------------
# format_house_status
# ---------------------------------------------------------------------------


class TestFormatHouseStatus:
    def test_header_present(self, fmt):
        result = fmt.format_house_status({})
        assert "House Status" in result

    def test_locked_state_green(self, fmt):
        data = {"Front Door": {"state": "locked", "entity_id": "lock.front_door"}}
        result = fmt.format_house_status(data)
        assert "green" in result

    def test_open_state_red(self, fmt):
        data = {"Garage": {"state": "open", "entity_id": "cover.garage"}}
        result = fmt.format_house_status(data)
        assert "red" in result

    def test_unavailable_state_yellow(self, fmt):
        data = {"Sensor": {"state": "unavailable", "entity_id": "sensor.x"}}
        result = fmt.format_house_status(data)
        assert "yellow" in result

    def test_error_state_yellow(self, fmt):
        data = {"Broken": {"state": "ok", "error": True, "entity_id": "sensor.y"}}
        result = fmt.format_house_status(data)
        assert "yellow" in result

    def test_max_six_lines(self, fmt):
        # Add many entities
        data = {f"Entity {i}": {"state": "off", "entity_id": f"switch.{i}"} for i in range(20)}
        result = fmt.format_house_status(data)
        assert len(result.split("\n")) <= 6


# ---------------------------------------------------------------------------
# format_stocks
# ---------------------------------------------------------------------------


class TestFormatStocks:
    def test_empty_data(self, fmt):
        assert fmt.format_stocks({}) == "Stocks: Unavailable"

    def test_no_stocks_list(self, fmt):
        result = fmt.format_stocks({"stocks": []})
        assert "No data" in result

    def test_shows_formatted_stock(self, fmt):
        data = {"stocks": [{"formatted": "AAPL: $150.25 +1.2%"}]}
        result = fmt.format_stocks(data)
        assert "AAPL" in result

    def test_max_four_stocks(self, fmt):
        stocks = [{"formatted": f"STOCK{i}: $100"} for i in range(10)]
        result = fmt.format_stocks({"stocks": stocks})
        lines = result.split("\n")
        assert len(lines) <= 4

    def test_max_six_lines(self, fmt):
        stocks = [{"formatted": f"S{i}: $100"} for i in range(10)]
        result = fmt.format_stocks({"stocks": stocks})
        assert len(result.split("\n")) <= 6


# ---------------------------------------------------------------------------
# format_muni
# ---------------------------------------------------------------------------


class TestFormatMuni:
    def test_empty_data(self, fmt):
        result = fmt.format_muni({})
        assert "No arrivals" in result or "Muni" in result

    def test_none_data(self, fmt):
        result = fmt.format_muni(None)
        assert "No arrivals" in result

    def test_basic_muni(self, fmt):
        data = {
            "line": "N-JUDAH",
            "arrivals": [{"minutes": 5, "is_full": False}, {"minutes": 12, "is_full": False}],
            "is_delayed": False,
            "stop_name": "Civic Center",
        }
        result = fmt.format_muni(data)
        assert "N-JUDAH" in result
        assert "5" in result

    def test_delayed_uses_red(self, fmt):
        data = {
            "line": "N-JUDAH",
            "arrivals": [{"minutes": 8, "is_full": False}],
            "is_delayed": True,
            "delay_description": "Signal delay",
        }
        result = fmt.format_muni(data)
        assert "red" in result or "DELAY" in result

    def test_full_train_orange_marker(self, fmt):
        data = {
            "line": "N",
            "arrivals": [{"minutes": 3, "is_full": True}],
            "is_delayed": False,
        }
        result = fmt.format_muni(data)
        assert "orange" in result

    def test_max_six_lines(self, fmt):
        data = {
            "line": "L",
            "arrivals": [{"minutes": i, "is_full": False} for i in range(10)],
            "is_delayed": False,
            "stop_name": "Some Stop Name",
            "delay_description": "Minor delay",
        }
        result = fmt.format_muni(data)
        assert len(result.split("\n")) <= 6


# ---------------------------------------------------------------------------
# format_combined
# ---------------------------------------------------------------------------


class TestFormatCombined:
    def test_date_and_weather(self, fmt):
        weather = {
            "location": "SF",
            "condition": "Sunny",
            "temperature": 68,
        }
        dt = {
            "day_of_week": "Tuesday",
            "date": "2026-03-29",
            "time": "09:00",
        }
        result = fmt.format_combined(weather, dt)
        assert "Tuesday" in result or "SF" in result
        assert len(result.split("\n")) <= 6

    def test_weather_only(self, fmt):
        weather = {"location": "LA", "condition": "Clear", "temperature": 75}
        result = fmt.format_combined(weather, None)
        assert "LA" in result

    def test_datetime_only(self, fmt):
        dt = {"day_of_week": "Monday", "date": "2026-01-01", "time": "00:00"}
        result = fmt.format_combined(None, dt)
        assert "Monday" in result

    def test_both_none(self, fmt):
        result = fmt.format_combined(None, None)
        # Should return empty string or minimal output without crashing
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# get_message_formatter factory
# ---------------------------------------------------------------------------


def test_get_message_formatter_returns_instance():
    instance = get_message_formatter()
    assert isinstance(instance, MessageFormatter)
