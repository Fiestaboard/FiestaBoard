# Board Character Codes & Weather Icons

## Overview

The board uses numeric character codes (0-63) to represent different characters. While it doesn't support traditional graphical icons, we can use creative character combinations and symbols to represent weather conditions.

## Character Codes

The board has 64 spinning character modules, each with different characters. The basic mapping includes:

- **Letters**: A-Z (codes 1-26)
- **Numbers**: 0-9 (codes 27-36)
- **Punctuation**: Period, comma, exclamation, question mark, etc.
- **Symbols**: Asterisk (*), slash (/), percent (%), etc.

## Weather Symbols

We've implemented weather symbols using available characters:

| Condition | Symbol | Character Code | Description |
|-----------|--------|----------------|-------------|
| Clear/Sunny | `O` | 15 (O) | Sunny weather |
| Partly Cloudy | `%` | 54 (PERCENT) | Partly cloudy |
| Cloudy/Overcast | `O` | 15 (O) | Cloudy weather |
| Rain | `/` | 59 (SLASH) | Rainy weather |
| Thunderstorm | `!` | 37 (EXCLAMATION) | Stormy weather |
| Snow | `O` | 15 (O) | Snowy weather |
| Fog/Mist | `-` | 44 (DASH) | Foggy conditions |

## Usage in Code

### Getting Weather Symbol

```python
from src.board_chars import get_weather_symbol

symbol_info = get_weather_symbol("Sunny")
# Returns: {
#     "symbol": "O",
#     "char_code": 15,
#     "description": "Sunny"
# }
```

### Using in Messages

The message formatter automatically includes weather symbols:

```python
from src.formatters.message_formatter import get_message_formatter

formatter = get_message_formatter()
weather_data = {
    'location': 'San Francisco',
    'condition': 'Sunny',
    'temperature': 75
}

message = formatter.format_weather(weather_data)
# Output:
# San Francisco: O Sunny
# Temp: 75°F
```

## Display Examples

### Sunny Weather
```
San Francisco: O Sunny
Temp: 75°F
```

### Rainy Weather
```
San Francisco: / Rain
Temp: 59°F
Humidity: 75% | Wind: 8 mph
```

### Cloudy Weather
```
San Francisco: O Overcast
Temp: 65°F
```

## Character Code Reference

The `BoardChars` class provides constants for all character codes:

```python
from src.board_chars import BoardChars

# Letters
BoardChars.A  # 1
BoardChars.B  # 2
# ... etc

# Numbers
BoardChars.ZERO  # 27
BoardChars.ONE   # 28
# ... etc

# Symbols
BoardChars.EXCLAMATION  # 37
BoardChars.SLASH        # 59
BoardChars.PERCENT      # 54
```

## Converting Text to Codes

```python
from src.board_chars import BoardChars

# Convert single character
code = BoardChars.get_char_code("A")  # Returns 1

# Convert text string
codes = BoardChars.text_to_codes("HELLO")
# Returns: [8, 5, 12, 12, 15]
```

## Notes

1. **Character codes**: These mappings are based on the [official Vestaboard character codes documentation](https://docs.vestaboard.com/docs/charactercodes/).

2. **No true icons**: The board doesn't support graphical icons, so we use creative character combinations.

3. **Color support**: The board supports colors via FBML (Board Markup Language), which could be used to enhance weather displays (e.g., yellow for sunny, blue for rain).

4. **Extensibility**: The `get_weather_symbol()` function can be extended to support more conditions or use different character combinations.

## Future Enhancements

- **FBML Integration**: Add color support for weather conditions
- **Custom Symbols**: Create multi-character patterns for more complex weather icons
- **Character Code Verification**: Verify codes against official board documentation
- **Extended Weather Conditions**: Add support for more specific conditions (drizzle, sleet, etc.)

## References

- [Board Documentation](https://docs.vestaboard.com/)
- [FBML Documentation](https://docs.vestaboard.com/docs/vbml)
