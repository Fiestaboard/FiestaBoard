# Board Color Guide

This guide explains how colors are used throughout the FiestaBoard Display Service to enhance visual communication.

## Overview

The board supports 8 color codes (63-70) that display as solid color tiles. The service uses these colors strategically to convey meaning and improve readability.

## Color Codes

| Code | Color  | Character Code | Usage |
|------|--------|----------------|-------|
| {63} | Red    | 63 | Alerts, hot temperatures, open doors, DS9 series |
| {64} | Orange | 64 | Warm temperatures |
| {65} | Yellow | 65 | Comfortable temperatures, warnings, TNG series |
| {66} | Green  | 66 | Good status, closed doors, cool temperatures, Guest WiFi |
| {67} | Blue   | 67 | Cold temperatures, Voyager series, WiFi SSID |
| {68} | Violet | 68 | Very cold temperatures, WiFi password |
| {69} | White  | 69 | (Reserved for future use) |
| {70} | Black  | 70 | (Reserved for future use) |

## Color Usage by Feature

### 1. Home Assistant Status

Colors indicate security status:

- **{66} Green**: Secure/Good
  - Doors: closed
  - Locks: locked
  - Windows: closed
  
- **{63} Red**: Needs Attention
  - Doors: open
  - Locks: unlocked
  - Windows: open
  
- **{65} Yellow**: Warning/Unknown
  - State: unavailable
  - State: unknown

**Example Display:**
```
House Status
Front Door: closed {66}
Garage: open {63}
Back Door: locked {66}
```

### 2. Weather Temperature

Colors represent temperature ranges (Fahrenheit):

- **{63} Red**: ≥90°F (Very hot)
- **{64} Orange**: 80-89°F (Hot)
- **{65} Yellow**: 70-79°F (Warm/Comfortable)
- **{66} Green**: 60-69°F (Comfortable/Cool)
- **{67} Blue**: 45-59°F (Cool)
- **{68} Violet**: <45°F (Cold)

**Example Display:**
```
San Francisco: * Sunny
Temp: {65}75°F
```

### 3. Star Trek Quotes

Each series has a signature color:

- **{65} Yellow**: TNG (The Next Generation)
  - Represents the classic gold command uniforms
  
- **{67} Blue**: Voyager
  - Represents the blue/teal science uniforms
  
- **{63} Red**: DS9 (Deep Space Nine)
  - Represents the command red uniforms

**Example Display:**
```
Make it so.

- Picard
  {65}TNG
```

### 4. Guest WiFi

Colors organize information:

- **{66} Green**: Header "Guest WiFi"
  - Welcoming, friendly color
  
- **{67} Blue**: SSID (Network Name)
  - Distinguishes network name
  
- **{68} Violet**: Password
  - Clearly separates password from SSID

**Example Display:**
```
{66}Guest WiFi

SSID: {67}GuestNetwork
Password: {68}Welcome123
```

## Technical Implementation

### Using Colors in Code

Colors are defined in `src/board_chars.py`:

```python
from src.board_chars import BoardChars

# Access color codes
red = BoardChars.RED      # 63
green = BoardChars.GREEN  # 66
blue = BoardChars.BLUE    # 67

# Get color by name
color_code = BoardChars.get_color_code("red")  # Returns 63
```

### Formatting with Colors

Colors are inserted using curly brace notation `{code}`:

```python
# Temperature with color
temp = 75
color = "{65}"  # Yellow
message = f"Temp: {color}{temp}°F"
# Result: "Temp: {65}75°F"
```

### Color in Text API

When using the board text API, color codes are embedded in the string:

```python
# Send colored message
vb_client.send_text("Status: {66}Good")
```

The board API automatically interprets `{63}` through `{70}` as color codes.

## Design Principles

### 1. Consistency

Colors maintain consistent meaning across features:
- Red = Alert/Hot
- Green = Good/Cool
- Yellow = Warning/Warm
- Blue = Information/Cold

### 2. Accessibility

Color choices consider:
- High contrast for readability
- Intuitive associations (red=danger, green=safe)
- Cultural color meanings

### 3. Purposeful Use

Colors are used to:
- Convey status at a glance
- Organize information hierarchically
- Add visual interest without clutter
- Enhance comprehension

## Color Combinations

### Effective Combinations

**Status Indicators:**
- Green + Red: Clear good/bad distinction
- Yellow: Neutral warning state

**Temperature Scale:**
- Red → Orange → Yellow → Green → Blue → Violet
- Creates intuitive hot-to-cold gradient

**Information Hierarchy:**
- Green header + Blue primary + Violet secondary
- Establishes clear visual hierarchy

### Avoiding Conflicts

- Don't use same color for conflicting meanings in same display
- Maintain sufficient contrast between adjacent colors
- Use colors sparingly - not every element needs color

## Customization

### Changing Temperature Thresholds

Edit `src/formatters/message_formatter.py`:

```python
def _get_temp_color(self, temp: int) -> str:
    if temp >= 95:  # Adjust threshold
        return "{63}"  # Red
    # ... more conditions
```

### Changing Series Colors

Edit `src/formatters/message_formatter.py`:

```python
series_info = {
    "tng": {"name": "TNG", "color": "{66}"},  # Change to green
    "voyager": {"name": "VOY", "color": "{63}"},  # Change to red
    "ds9": {"name": "DS9", "color": "{67}"}  # Change to blue
}
```

### Adding New Color Uses

```python
# Example: Add color to weather conditions
def format_weather(self, weather_data: Dict) -> str:
    temp = weather_data.get("temperature", "??")
    condition = weather_data.get("condition", "Unknown")
    
    # Add blue color to "Weather"
    lines = ["{67}Weather", ""]
    # ... rest of formatting
```

## Testing Colors

### Visual Test

Run the test script to see color codes in action:

```bash
cd /path/to/FiestaBoard
python3 -c "
import sys
sys.path.insert(0, 'src')
from src.formatters.message_formatter import get_message_formatter

formatter = get_message_formatter()

# Test Home Assistant colors
ha_data = {
    'Door': {'entity_id': 'binary_sensor.door', 'state': 'off'},
    'Window': {'entity_id': 'binary_sensor.window', 'state': 'on'}
}
print(formatter.format_house_status(ha_data))
"
```

### On Actual Board

The color codes display as solid color tiles on the physical board. Test by:

1. Enable a feature with colors (e.g., Home Assistant)
2. Deploy to your board
3. Observe the colored tiles in the display
4. Adjust colors if needed for better visibility

## Troubleshooting

### Colors Not Displaying

**Problem:** Color codes show as text `{63}` instead of colored tiles.

**Solution:**
- Verify you're using the Read/Write API (not older APIs)
- Check board firmware is up to date
- Ensure color codes are in correct format: `{63}` not `63`

### Wrong Colors Showing

**Problem:** Colors don't match expectations.

**Solution:**
- Verify color code numbers (63-70)
- Check for typos in color codes
- Test with simple message: `vb_client.send_text("{63}RED {66}GREEN")`

### Color Codes Truncated

**Problem:** Messages cut off when colors added.

**Solution:**
- Color codes add 4 characters: `{63}`
- Adjust `MAX_COLS` calculations to account for color codes
- See formatters for examples: `[:self.MAX_COLS + 4]`

## Future Enhancements

Potential color improvements:

- **Weather conditions**: Color-code weather symbols
- **Time of day**: Different colors for morning/afternoon/evening
- **Custom themes**: User-configurable color schemes
- **Animations**: Rotating colors for emphasis

## References

- [Board Character Codes](https://docs.vestaboard.com/docs/charactercodes)
- [FBML Documentation](https://docs.vestaboard.com/docs/vbml)
- Project: `src/board_chars.py`
- Project: `src/formatters/message_formatter.py`

## Summary

Colors enhance the board display by:
- ✅ Conveying status at a glance (red/green)
- ✅ Representing temperature ranges (hot to cold)
- ✅ Distinguishing series (Star Trek)
- ✅ Organizing information (Guest WiFi)
- ✅ Adding visual interest

Use colors purposefully and consistently for maximum impact!

