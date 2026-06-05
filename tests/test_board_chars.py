"""Tests for board character codes and symbol mappings."""

import pytest

from src.board_chars import (
    WEATHER_SYMBOLS,
    BoardChars,
    FiestaboardChars,
    get_weather_symbol,
)


class TestBoardCharsLetterCodes:
    """Tests for letter codes A-Z (codes 1-26)."""

    @pytest.mark.parametrize(
        "char,expected",
        [
            ("A", 1),
            ("B", 2),
            ("C", 3),
            ("D", 4),
            ("E", 5),
            ("F", 6),
            ("G", 7),
            ("H", 8),
            ("I", 9),
            ("J", 10),
            ("K", 11),
            ("L", 12),
            ("M", 13),
            ("N", 14),
            ("O", 15),
            ("P", 16),
            ("Q", 17),
            ("R", 18),
            ("S", 19),
            ("T", 20),
            ("U", 21),
            ("V", 22),
            ("W", 23),
            ("X", 24),
            ("Y", 25),
            ("Z", 26),
        ],
    )
    def test_uppercase_letters(self, char, expected):
        """All uppercase letters map to codes 1-26."""
        assert BoardChars.get_char_code(char) == expected

    def test_lowercase_letters_normalized_to_uppercase(self):
        """Lowercase letters are normalized to uppercase codes."""
        assert BoardChars.get_char_code("a") == 1
        assert BoardChars.get_char_code("z") == 26


class TestBoardCharsNumberCodes:
    """Tests for number codes (1-9 = 27-35, 0 = 36)."""

    @pytest.mark.parametrize(
        "char,expected",
        [
            ("1", 27),
            ("2", 28),
            ("3", 29),
            ("4", 30),
            ("5", 31),
            ("6", 32),
            ("7", 33),
            ("8", 34),
            ("9", 35),
            ("0", 36),
        ],
    )
    def test_number_codes(self, char, expected):
        """Numbers 1-9 map to 27-35, 0 maps to 36."""
        assert BoardChars.get_char_code(char) == expected


class TestBoardCharsSpecialCharacters:
    """Tests for special character codes."""

    @pytest.mark.parametrize(
        "char,expected",
        [
            (" ", BoardChars.SPACE),
            ("!", BoardChars.EXCLAMATION),
            ("@", BoardChars.AT),
            ("#", BoardChars.POUND),
            ("$", BoardChars.DOLLAR),
            ("(", BoardChars.LEFT_PAREN),
            (")", BoardChars.RIGHT_PAREN),
            ("-", BoardChars.DASH),
            ("+", BoardChars.PLUS),
            ("&", BoardChars.AMPERSAND),
            ("=", BoardChars.EQUALS),
            (";", BoardChars.SEMICOLON),
            (":", BoardChars.COLON),
            ("'", BoardChars.SINGLE_QUOTE),
            ('"', BoardChars.DOUBLE_QUOTE),
            ("%", BoardChars.PERCENT),
            (",", BoardChars.COMMA),
            (".", BoardChars.PERIOD),
            ("/", BoardChars.SLASH),
            ("?", BoardChars.QUESTION),
            ("°", BoardChars.DEGREE),
            ("❤", BoardChars.DEGREE),
            ("♥", BoardChars.DEGREE),
        ],
    )
    def test_special_char_codes(self, char, expected):
        """Special characters map to correct codes."""
        assert BoardChars.get_char_code(char) == expected

    def test_space_returns_zero(self):
        """Space character returns code 0."""
        assert BoardChars.get_char_code(" ") == 0


class TestBoardCharsUnknownCharacter:
    """Tests for unknown character handling."""

    def test_unknown_char_returns_none(self):
        """Unknown characters return None from get_char_code."""
        assert BoardChars.get_char_code("é") is None
        assert BoardChars.get_char_code("ñ") is None
        assert BoardChars.get_char_code("€") is None
        assert BoardChars.get_char_code("™") is None
        assert BoardChars.get_char_code("") is None


class TestBoardCharsColorCodes:
    """Tests for color code lookups."""

    @pytest.mark.parametrize(
        "color_name,expected",
        [
            ("red", BoardChars.RED),
            ("orange", BoardChars.ORANGE),
            ("yellow", BoardChars.YELLOW),
            ("green", BoardChars.GREEN),
            ("blue", BoardChars.BLUE),
            ("violet", BoardChars.VIOLET),
            ("purple", BoardChars.VIOLET),
            ("white", BoardChars.WHITE),
            ("black", BoardChars.BLACK),
            ("filled", BoardChars.FILLED),
        ],
    )
    def test_color_code_lookups(self, color_name, expected):
        """All color names map to correct codes."""
        assert BoardChars.get_color_code(color_name) == expected

    def test_purple_alias_for_violet(self):
        """Purple is alias for violet (same code)."""
        assert BoardChars.get_color_code("purple") == BoardChars.get_color_code("violet")

    def test_color_case_insensitive(self):
        """Color lookups are case-insensitive."""
        assert BoardChars.get_color_code("RED") == BoardChars.RED
        assert BoardChars.get_color_code("Green") == BoardChars.GREEN

    def test_unknown_color_returns_none(self):
        """Unknown color names return None."""
        assert BoardChars.get_color_code("cyan") is None
        assert BoardChars.get_color_code("magenta") is None
        assert BoardChars.get_color_code("") is None


class TestBoardCharsTextToCodes:
    """Tests for text_to_codes conversion."""

    def test_normal_text(self):
        """Normal text converts to correct codes."""
        result = BoardChars.text_to_codes("HELLO")
        assert result == [8, 5, 12, 12, 15]

    def test_text_with_spaces(self):
        """Spaces convert to 0."""
        result = BoardChars.text_to_codes("A B")
        assert result == [1, 0, 2]

    def test_text_with_numbers_and_punctuation(self):
        """Numbers and punctuation convert correctly."""
        result = BoardChars.text_to_codes("HI!")
        assert result == [8, 9, BoardChars.EXCLAMATION]

    def test_empty_string(self):
        """Empty string returns empty list."""
        assert BoardChars.text_to_codes("") == []

    def test_unknown_char_fallback_to_space(self):
        """Unknown characters fallback to SPACE (0)."""
        result = BoardChars.text_to_codes("AéB")
        assert result == [1, BoardChars.SPACE, 2]

    def test_multiple_unknown_chars_fallback(self):
        """Multiple unknown chars all fallback to space."""
        result = BoardChars.text_to_codes("éñ€")
        assert result == [BoardChars.SPACE, BoardChars.SPACE, BoardChars.SPACE]

    def test_mixed_known_and_unknown(self):
        """Mix of known and unknown chars."""
        result = BoardChars.text_to_codes("Café")
        # C=3, a=1, f=6, é=SPACE
        assert result == [3, 1, 6, BoardChars.SPACE]


class TestWeatherSymbols:
    """Tests for get_weather_symbol function."""

    def test_exact_match(self):
        """Exact match returns correct symbol."""
        result = get_weather_symbol("Clear")
        assert result["symbol"] == "O"
        assert result["char_code"] == BoardChars.O
        assert result["description"] == "Sunny"

    def test_case_insensitive_match(self):
        """Case-insensitive match works."""
        result = get_weather_symbol("clear")
        assert result["symbol"] == "O"
        assert result["description"] == "Sunny"

        result = get_weather_symbol("RAINY")
        assert result["symbol"] == "/"
        assert result["description"] == "Rain"

    def test_partial_match_condition_contains_key(self):
        """Partial match when condition contains key (e.g. 'Very Heavy Rain' contains 'Heavy Rain')."""
        # "Heavy Rain" is in WEATHER_SYMBOLS; "Very Heavy Rain" contains "Heavy Rain"
        # The partial match checks: key.lower() in condition_lower OR condition_lower in key.lower()
        # "heavy rain" in "very heavy rain" -> True
        result = get_weather_symbol("Very Heavy Rain")
        assert result["symbol"] == "/"
        # Partial match returns first match; "Rain" or "Heavy Rain" may match
        assert result["description"] in ("Rain", "Hvy Rain")

    def test_partial_match_key_in_condition(self):
        """Partial match when key is substring of condition."""
        result = get_weather_symbol("Light Rain Showers")
        # "Light Rain" or "Rain" might match - "rain" is in "light rain showers"
        assert "symbol" in result
        assert "char_code" in result
        assert "description" in result

    def test_unknown_condition_fallback(self):
        """Unknown condition returns fallback with ? symbol."""
        result = get_weather_symbol("Unknown Condition XYZ")
        assert result["symbol"] == "?"
        assert result["char_code"] == BoardChars.QUESTION
        assert result["description"] == "Unknown "  # Truncated to 8 chars

    def test_unknown_condition_long_description_truncated(self):
        """Long unknown condition description is truncated to 8 chars."""
        result = get_weather_symbol("VeryLongUnknownCondition")
        assert result["symbol"] == "?"
        assert len(result["description"]) == 8
        assert result["description"] == "VeryLong"

    def test_strips_whitespace(self):
        """Condition string is stripped of whitespace."""
        result = get_weather_symbol("  Clear  ")
        assert result["symbol"] == "O"
        assert result["description"] == "Sunny"

    def test_weather_symbols_dict_keys(self):
        """WEATHER_SYMBOLS has expected keys."""
        expected_conditions = [
            "Clear",
            "Sunny",
            "Partly Cloudy",
            "Cloudy",
            "Overcast",
            "Rain",
            "Rainy",
            "Light Rain",
            "Heavy Rain",
            "Thunderstorm",
            "Storm",
            "Snow",
            "Snowy",
            "Fog",
            "Mist",
        ]
        for cond in expected_conditions:
            assert cond in WEATHER_SYMBOLS
            assert "symbol" in WEATHER_SYMBOLS[cond]
            assert "char_code" in WEATHER_SYMBOLS[cond]
            assert "description" in WEATHER_SYMBOLS[cond]


class TestFiestaboardCharsAlias:
    """Tests for FiestaboardChars backward compatibility alias."""

    def test_alias_same_as_board_chars(self):
        """FiestaboardChars is alias for BoardChars."""
        assert FiestaboardChars is BoardChars

    def test_alias_has_same_methods(self):
        """FiestaboardChars has same methods and constants."""
        assert FiestaboardChars.get_char_code("A") == BoardChars.get_char_code("A")
        assert FiestaboardChars.get_color_code("red") == BoardChars.get_color_code("red")
        assert FiestaboardChars.text_to_codes("HI") == BoardChars.text_to_codes("HI")
        assert FiestaboardChars.SPACE == BoardChars.SPACE
        assert FiestaboardChars.A == BoardChars.A
