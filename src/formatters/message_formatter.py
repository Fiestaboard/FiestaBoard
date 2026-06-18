"""Message formatting for board display.

The board supports:
- Characters: A-Z, 0-9, and limited punctuation (codes 0-62)
- Color tiles: Red, Orange, Yellow, Green, Blue, Violet, White, Black (codes 63-70)

Color markers like {{red}} or {{66}} create SOLID COLOR TILES, not colored text.
Use them as decorative indicators followed by a space, e.g., "{green} SSID: network"
"""

import logging

from src.board_chars import get_weather_symbol

logger = logging.getLogger(__name__)


class MessageFormatter:
    """Formats data for a configurable board character grid.

    Class-level MAX_ROWS/MAX_COLS remain for backward compatibility.
    Instance-level _rows/_cols reflect the target board's actual dimensions.
    """

    MAX_ROWS = 6
    MAX_COLS = 22

    def __init__(self, rows: int = 6, cols: int = 22) -> None:
        """Initialize message formatter.

        Args:
            rows: Number of rows for the target board (default 6 for flagship).
            cols: Number of columns for the target board (default 22 for flagship).
        """
        self._rows = rows
        self._cols = cols

    def format_weather(self, weather_data: dict) -> str:
        """
        Format weather data for display with weather symbols.

        Args:
            weather_data: Dictionary with weather information

        Returns:
            Formatted string (max 6 lines)
        """
        if not weather_data:
            return "Weather: Unavailable"

        lines = []

        # Get weather symbol
        condition = weather_data.get("condition", "Unknown")
        weather_symbol_info = get_weather_symbol(condition)
        symbol = weather_symbol_info.get("symbol", "?")

        # Location and condition with symbol
        location = weather_data.get("location", "Weather")
        # Format: "Location: * Sunny" or "Location: / Rainy"
        condition_display = weather_symbol_info.get("description", condition)
        lines.append(f"{location}: {symbol} {condition_display}")

        # Temperature
        temp = int(weather_data.get("temperature", 0))
        feels_like = int(weather_data.get("feels_like", temp))
        if temp == feels_like:
            lines.append(f"Temp: {temp}F")
        else:
            lines.append(f"Temp: {temp}F (feels {feels_like}F)")

        # Additional info
        humidity = weather_data.get("humidity")
        wind = weather_data.get("wind_mph")

        info_parts = []
        if humidity is not None:
            info_parts.append(f"Humidity: {humidity}%")
        if wind is not None:
            info_parts.append(f"Wind: {int(wind)} mph")

        if info_parts:
            lines.append(" | ".join(info_parts))

        # Ensure we don't exceed 6 rows
        return "\n".join(lines[: self._rows])

    def format_datetime(self, datetime_data: dict) -> str:
        """
        Format datetime data for display.

        Args:
            datetime_data: Dictionary with datetime information

        Returns:
            Formatted string (max 6 lines)
        """
        if not datetime_data:
            return "Date/Time: Unavailable"

        lines = []

        # Day of week and date
        day = datetime_data.get("day_of_week", "")
        date = datetime_data.get("date", "")
        if day and date:
            lines.append(f"{day}, {date}")
        else:
            lines.append(date or day)

        # Time with timezone
        time_str = datetime_data.get("time", "")
        tz_abbr = datetime_data.get("timezone_abbr", "")
        if time_str:
            if tz_abbr:
                lines.append(f"{time_str} {tz_abbr}")
            else:
                lines.append(time_str)

        return "\n".join(lines[: self._rows])

    def format_guest_wifi(self, ssid: str, password: str) -> str:
        """
        Format guest WiFi credentials for display.

        Uses colored tiles as decorative indicators:
        - Green tile for header (welcoming)
        - Blue tile for SSID
        - Violet tile for password

        Args:
            ssid: WiFi network name (SSID)
            password: WiFi password

        Returns:
            Formatted string (max 6 lines)
        """
        lines = []

        # Header with green tile indicator
        lines.append("{{green}} Guest WiFi")
        lines.append("")

        # SSID with blue tile indicator
        ssid_line = f"{{{{blue}}}} {ssid}"
        lines.append(ssid_line[: self._cols + 8])  # +8 for {{blue}} marker

        # Password with violet tile indicator
        pass_line = f"{{{{violet}}}} {password}"
        lines.append(pass_line[: self._cols + 10])  # +10 for {{violet}} marker

        # Ensure we don't exceed 6 rows
        return "\n".join(lines[: self._rows])

    def format_star_trek_quote(self, quote_data: dict) -> str:
        """
        Format Star Trek quote for display.

        Uses colored tiles to indicate the series:
        - Yellow tile for TNG (gold uniforms)
        - Blue tile for Voyager
        - Red tile for DS9 (command red)

        Args:
            quote_data: Dictionary with 'quote', 'character', and 'series' keys

        Returns:
            Formatted string (max 6 lines)
        """
        lines = []

        quote = quote_data.get("quote", "")
        character = quote_data.get("character", "")
        series = quote_data.get("series", "").lower()

        # Series name and color mapping
        series_config = {
            "tng": {"name": "TNG", "color": "{{yellow}}"},
            "voyager": {"name": "VOY", "color": "{{blue}}"},
            "ds9": {"name": "DS9", "color": "{{red}}"},
        }
        config = series_config.get(series, {"name": series.upper(), "color": ""})
        series_display = config["name"]
        series_color = config["color"]

        # Split quote into lines that fit
        quote_lines = self.split_into_lines(quote, max_lines=4)
        lines.extend(quote_lines)

        # Add separator if we have room
        if len(lines) < self._rows - 1:
            lines.append("")

        # Add attribution with series color tile if we have room
        if len(lines) < self._rows:
            if series_color and len(lines) < self._rows - 1:
                # Room for character line and series line with color
                lines.append(f"- {character}"[: self._cols])
                lines.append(f"{series_color} {series_display}"[: self._cols + 8])
            else:
                # Combine into one line
                lines.append(f"- {character} ({series_display})"[: self._cols])

        return "\n".join(lines[: self._rows])

    def format_house_status(self, status_data: dict[str, dict]) -> str:
        """
        Format house status from Home Assistant.

        Uses colored tiles as status indicators:
        - Green tile = closed/locked/off (secure/good)
        - Red tile = open/unlocked/on (needs attention)
        - Yellow tile = unavailable/unknown

        Args:
            status_data: Dictionary mapping entity names to status info
                        Example: {"Front Door": {"state": "on", ...}, ...}

        Returns:
            Formatted string (max 6 lines)
        """
        lines = []

        # Header
        lines.append("House Status")

        # Process each entity
        for name, info in status_data.items():
            if len(lines) >= self._rows:
                break

            state = info.get("state", "unknown").lower()
            error = info.get("error", False)
            entity_id = info.get("entity_id", "")

            # Determine status text and color indicator
            if error or state == "unavailable":
                indicator = "{{yellow}}"  # Warning/unknown
                status_text = "?"
            elif state in ["on", "open", "unlocked"]:
                indicator = "{{red}}"  # Needs attention
                # Convert to friendly text
                if state == "on" and ("door" in entity_id.lower() or "window" in entity_id.lower()):
                    status_text = "open"
                else:
                    status_text = state
            elif state in ["off", "closed", "locked"]:
                indicator = "{{green}}"  # Secure/good
                # Convert to friendly text
                if state == "off" and ("door" in entity_id.lower() or "window" in entity_id.lower()):
                    status_text = "closed"
                else:
                    status_text = state
            else:
                indicator = "{{yellow}}"  # Unknown state
                status_text = state[:6]  # Truncate unknown states

            # Format: "{color} Name: status"
            # Account for color marker length when truncating
            max_name_len = self._cols - len(f" : {status_text}") - 1  # -1 for indicator tile
            display_name = name[:max_name_len] if len(name) > max_name_len else name

            line = f"{indicator} {display_name}: {status_text}"
            lines.append(line)

        return "\n".join(lines[: self._rows])

    def format_combined(self, weather_data: dict | None, datetime_data: dict | None) -> str:
        """
        Format combined weather and datetime display.

        Uses colored tile before temperature to indicate temperature range:
        - Red = very hot (90F+)
        - Orange = hot (80-89F)
        - Yellow = warm (70-79F)
        - Green = comfortable (60-69F)
        - Blue = cool (45-59F)
        - Violet = cold (<45F)

        Args:
            weather_data: Weather information dictionary
            datetime_data: Datetime information dictionary

        Returns:
            Combined formatted string (max 6 lines)
        """
        lines = []

        # Date/Time header
        if datetime_data:
            day = datetime_data.get("day_of_week", "")
            date = datetime_data.get("date", "")
            time_str = datetime_data.get("time", "")

            if day and date:
                lines.append(f"{day}, {date}")
            elif date:
                lines.append(date)

            if time_str:
                lines.append(time_str)

            # Add separator if we have weather
            if weather_data and len(lines) < self._rows:
                lines.append("")

        # Weather information
        if weather_data:
            location = weather_data.get("location", "Weather")
            condition = weather_data.get("condition", "Unknown")
            temp = int(weather_data.get("temperature", 0))

            # Get weather symbol
            weather_symbol_info = get_weather_symbol(condition)
            symbol = weather_symbol_info.get("symbol", "?")
            condition_display = weather_symbol_info.get("description", condition)

            # Get color tile for temperature indication
            temp_color = self._get_temp_color(temp)

            # Compact format to fit
            if len(lines) + 2 <= self._rows:
                lines.append(f"{location}: {symbol} {condition_display}")
                # Temperature with color tile indicator before the number
                lines.append(f"Temp: {temp_color} {temp}F")
            elif len(lines) + 1 <= self._rows:
                # Very compact - color tile before temp
                lines.append(f"{location}: {temp_color} {temp}F")

        # Ensure we don't exceed 6 rows
        result = "\n".join(lines[: self._rows])

        # Truncate each line to 22 characters if needed (accounting for color markers)
        result_lines = result.split("\n")
        truncated = []
        for line in result_lines:
            # Don't count color markers toward the 22 char limit
            # They get stripped during conversion
            truncated.append(line)

        return "\n".join(truncated)

    def _get_temp_color(self, temp: int) -> str:
        """
        Get color marker for temperature display.

        Creates a single colored tile to indicate temperature range.

        Args:
            temp: Temperature in Fahrenheit

        Returns:
            Color marker string (e.g., "{{red}}" for hot)
        """
        if temp >= 90:
            return "{{red}}"  # Very hot
        if temp >= 80:
            return "{{orange}}"  # Hot
        if temp >= 70:
            return "{{yellow}}"  # Warm
        if temp >= 60:
            return "{{green}}"  # Comfortable
        if temp >= 45:
            return "{{blue}}"  # Cool
        return "{{violet}}"  # Cold

    def split_into_lines(self, text: str, max_lines: int = MAX_ROWS) -> list[str]:
        """
        Split text into lines, respecting max length.

        Args:
            text: Text to split
            max_lines: Maximum number of lines

        Returns:
            List of lines (each max 22 characters)
        """
        lines = text.split("\n")
        result = []

        for line in lines[:max_lines]:
            # If line is too long, try to split on spaces
            if len(line) > self._cols:
                words = line.split()
                current_line = ""

                for word in words:
                    if len(current_line) + len(word) + 1 <= self._cols:
                        if current_line:
                            current_line += " " + word
                        else:
                            current_line = word
                    else:
                        if current_line:
                            result.append(current_line)
                        current_line = word

                if current_line:
                    result.append(current_line)
            else:
                result.append(line)

        return result[:max_lines]

    def format_muni(self, muni_data: dict) -> str:
        """
        Format Muni transit data for display.

        Uses colored tiles as status indicators:
        - Red tile = delay status
        - Orange = occupancy is full

        Format: "N-JUDAH: 4, 12, 19 MIN (DELAY)"

        Args:
            muni_data: Dictionary with Muni arrival information

        Returns:
            Formatted string (max 6 lines)
        """
        if not muni_data:
            return "Muni: No arrivals"

        lines = []

        # Get data
        line = muni_data.get("line", "MUNI")
        arrivals = muni_data.get("arrivals", [])
        is_delayed = muni_data.get("is_delayed", False)
        delay_description = muni_data.get("delay_description", "")
        stop_name = muni_data.get("stop_name", "")

        # Header with transit icon indicator
        if is_delayed:
            lines.append("{{red}} MUNI Transit")
        else:
            lines.append("{{blue}} MUNI Transit")

        # Stop name (if available and fits)
        if stop_name:
            lines.append(stop_name[: self._cols])

        # Format arrival times
        if arrivals:
            times = []
            for arr in arrivals:
                mins = arr.get("minutes", 0)
                is_full = arr.get("is_full", False)

                if is_full:
                    # Orange marker for full trains
                    times.append(f"{{{{orange}}}}{mins}")
                else:
                    times.append(str(mins))

            time_str = ", ".join(times)

            # Line name and times
            suffix = " MIN"
            if is_delayed:
                suffix = " MIN (DELAY)"

            arrival_line = f"{line}: {time_str}{suffix}"

            # Apply delay color if needed
            if is_delayed:
                arrival_line = f"{{{{red}}}}{arrival_line}"

            lines.append(arrival_line[: self._cols + 10])  # Account for color markers
        else:
            lines.append(f"{line}: No arrivals")

        # Add delay description if present
        if delay_description and len(lines) < self._rows:
            lines.append(delay_description[: self._cols])

        return "\n".join(lines[: self._rows])

    def format_stocks(self, stocks_data: dict) -> str:
        """
        Format stocks data for display.

        Args:
            stocks_data: Dictionary with stocks information

        Returns:
            Formatted string (max 6 lines)
        """
        if not stocks_data:
            return "Stocks: Unavailable"

        stocks = stocks_data.get("stocks", [])
        if not stocks:
            return "Stocks: No data available"

        lines = []

        # Display up to 4 stocks (one per line, or combine if space allows)
        for stock in stocks[:4]:
            formatted = stock.get("formatted", "")
            if formatted:
                lines.append(formatted)

        # Ensure we don't exceed 6 rows
        return "\n".join(lines[: self._rows])


def get_message_formatter(rows: int = 6, cols: int = 22) -> MessageFormatter:
    """Get message formatter instance sized for a specific board.

    Args:
        rows: Number of rows for the target board (default 6 for flagship).
        cols: Number of columns for the target board (default 22 for flagship).
    """
    return MessageFormatter(rows=rows, cols=cols)
