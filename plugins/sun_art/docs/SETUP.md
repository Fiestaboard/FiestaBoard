# Sun Art Setup Guide

The Sun Art feature displays a full-screen 6x22 bit image pattern that changes based on the sun's position throughout the day. Watch the pattern evolve from night through dawn, sunrise, morning, noon, afternoon, sunset, and dusk.

![Sun Art Display](./sun-art-display.png)

## Overview

**What it does:**
- Displays a full-screen visual pattern representing the sun's position
- Automatically updates throughout the day as the sun moves
- Shows 8 distinct stages: night, dawn, sunrise, morning, noon, afternoon, sunset, dusk
- Uses your location (latitude/longitude) for accurate sun calculations
- Provides both string and array format outputs

**Use Cases:**
- Beautiful ambient display that changes with the time of day
- Visual indicator of sun position and time
- Decorative full-screen pattern for your board
- Combine with other plugins for a complete daily display

## Prerequisites

- ✅ Coordinates (latitude, longitude) for your location
- ✅ Timezone configured in general settings (used for time calculations)
- ✅ No API keys required (calculations are done locally)

## Quick Setup

### 1. Enable Sun Art

Via Web UI (Recommended):
1. Go to the **Integrations** page
2. Find **Sun Art** section
3. Toggle the **Sun Art** plugin on
4. Enter your **Latitude** and **Longitude**
5. Set **Refresh Interval** (default: 300 seconds / 5 minutes)
6. Click **Save Changes**

Via Environment Variables:
```bash
# Add to .env
SUN_ART_ENABLED=true
SUN_ART_LATITUDE=40.7128
SUN_ART_LONGITUDE=-74.0060
SUN_ART_REFRESH_SECONDS=300
```

### 2. Find Your Coordinates

**Option 1: Use Location Discovery Button (Easiest)**
1. In the Sun Art settings, you'll see a location button (📍) next to the latitude/longitude fields
2. Click the button
3. Allow browser location access when prompted
4. Your coordinates will be automatically filled in

**Option 2: Google Maps**
1. Open [Google Maps](https://www.google.com/maps)
2. Right-click on your location
3. Click the coordinates at the top
4. Copy latitude and longitude

**Option 3: GPS Device**
- Use your phone's GPS or a dedicated GPS device
- Format: Decimal degrees (e.g., 40.7128, -74.0060)

**Option 4: Online Tools**
- [LatLong.net](https://www.latlong.net/)
- [GPS Coordinates](https://www.gps-coordinates.net/)

### 3. Configure Refresh Interval

The refresh interval determines how often the sun position is recalculated and the pattern is updated.

- **Default**: 300 seconds (5 minutes)
- **Minimum**: 60 seconds
- **Recommended**: 300 seconds for smooth transitions without excessive computation

Shorter intervals (60-120 seconds) provide more frequent updates but use more CPU.
Longer intervals (600+ seconds) are more efficient but may miss subtle transitions.

### 4. Verify Timezone

The plugin uses the timezone from **General Settings** for sun calculations. Make sure your timezone is correctly configured:

1. Go to the **Settings** page under **General Settings**
2. Check that **Timezone** is set correctly (e.g., "America/Los_Angeles")
3. The current time display should match your local time

## Understanding Sun Stages

The pattern changes through 8 distinct stages throughout the day. The transitions are based on the sun's elevation angle and whether it's rising or setting.

### Stage Transitions

| Stage | Elevation Range | When It Occurs | Pattern Description |
|-------|----------------|----------------|---------------------|
| **Night** | < -6° | After dusk ends, before dawn begins | Dark pattern with black and blue tiles |
| **Dawn** | -6° to 0° | ~30-40 min before sunrise (twilight) | Gradual lightening from blue sky to orange horizon |
| **Sunrise** | 0° to 5° | At sunrise, first ~20-30 min after | Brightening with circular sun at horizon, orange/yellow gradient |
| **Morning** | 5° to 30° | ~30 min after sunrise until ~2 hours | Full circular sun pattern, yellow/orange colors, clear sky/land separation |
| **Noon** | 30° to 90° | Peak sun elevation (midday) | Brightest pattern, white/yellow sun high in sky |
| **Afternoon** | 5° to 30° | ~2 hours before sunset until ~30 min before | Similar to morning, sun lower in sky |
| **Sunset** | 0° to 5° | At sunset, last ~20-30 min before | Dimming with circular sun at horizon, orange/red colors |
| **Dusk** | -6° to 0° | ~30-40 min after sunset (twilight) | Fading to dark, orange to blue to black |

### Visual Pattern Details

Each stage has distinct visual characteristics:

- **Night**: Dark background with subtle blue accents
- **Dawn/Dusk**: Clear horizon line separating blue sky from orange land
- **Sunrise/Sunset**: Circular sun visible at horizon with distinct sky, sun, and land zones
- **Morning/Afternoon**: Full circular sun in blue sky, with clear horizon line and distinct land pattern
- **Noon**: Brightest white/yellow sun high in sky

### Transition Times

The exact times for each stage depend on:
- **Your location** (latitude/longitude) - affects sunrise/sunset times
- **The date** (season) - affects sun elevation and day length
- **Your timezone** - must be correctly configured in General Settings

**Example transitions** (varies by location and season):
- **Dawn begins**: ~30-40 minutes before sunrise
- **Sunrise**: When sun elevation reaches 0° (sun appears on horizon)
- **Morning begins**: ~20-30 minutes after sunrise (sun elevation > 5°)
- **Noon**: When sun reaches peak elevation (varies by season)
- **Afternoon begins**: When sun elevation drops below 30° (afternoon)
- **Sunset begins**: ~20-30 minutes before sunset (sun elevation < 5°)
- **Sunset**: When sun elevation reaches 0° (sun disappears below horizon)
- **Dusk ends**: ~30-40 minutes after sunset (sun elevation < -6°)

## Using Sun Art in Templates

### Basic Full-Screen Display

Simply use the `sun_art` variable to display the full pattern:

```
{{sun_art.sun_art}}
```

This will fill the entire 6x22 board with the current sun pattern.

### With Stage Information

Add the stage name above the pattern:

```
{{sun_art.sun_stage}}
{{sun_art.sun_art}}
```

### Time to Sunrise/Sunset

Display when the next sunrise or sunset will occur:

```
STAGE: {{sun_art.sun_stage}}
RISE: {{sun_art.time_to_sunrise}}
SET: {{sun_art.time_to_sunset}}
```

### Daytime Indicator

Show whether it's currently daytime:

```
{{sun_art.is_daytime}}
{{sun_art.sun_art}}
```

### Sun Position

Display the current sun elevation angle:

```
SUN: {{sun_art.sun_position}}°
{{sun_art.sun_art}}
```

## Troubleshooting

### Pattern Not Updating

**Issue**: Pattern stays the same even after time passes.

**Solutions**:
- Check that refresh interval is set appropriately (not too long)
- Verify the plugin is enabled
- Check that latitude/longitude are correctly configured
- Ensure timezone in general settings is correct

### Wrong Sun Position

**Issue**: Pattern doesn't match the actual sun position.

**Solutions**:
- Verify latitude/longitude coordinates are accurate
- Check timezone in general settings matches your location
- Ensure system time is correct
- Try refreshing the page or restarting the service

### Location Discovery Not Working

**Issue**: Location button doesn't populate coordinates.

**Solutions**:
- Ensure browser has location permissions enabled
- Try a different browser
- Manually enter coordinates using Google Maps or other tool
- Check browser console for error messages

### Pattern Looks Wrong

**Issue**: Pattern doesn't look right for the time of day.

**Solutions**:
- Verify coordinates are correct (check with Google Maps)
- Check timezone settings
- Ensure refresh interval allows for updates
- Check that the current time matches your local time

## Advanced Configuration

### Custom Refresh Intervals

For more frequent updates (e.g., every minute):
- Set refresh interval to 60 seconds
- Note: This increases CPU usage

For less frequent updates (e.g., every 10 minutes):
- Set refresh interval to 600 seconds
- Pattern will update less frequently but use less resources

### Multiple Locations

If you want sun art for different locations, you can:
1. Create multiple pages in FiestaBoard
2. Configure each page with different coordinates
3. Switch between pages to see different locations

Note: The plugin currently supports one location per instance. For multiple locations, use multiple plugin instances or pages.

## Examples

### Example Coordinates

Common locations for testing:

- **New York, NY**: 40.7128, -74.0060
- **New York, NY**: 40.7128, -74.0060
- **London, UK**: 51.5074, -0.1278
- **Tokyo, Japan**: 35.6762, 139.6503
- **Sydney, Australia**: -33.8688, 151.2093

### Example Templates

**Simple full-screen:**
```
{{sun_art.sun_art}}
```

**With stage and time:**
```
{{sun_art.sun_stage}}
{{sun_art.time_to_sunrise}}
{{sun_art.sun_art}}
```

**Informative display:**
```
SUN ART
STAGE: {{sun_art.sun_stage}}
POS: {{sun_art.sun_position}}°
{{sun_art.sun_art}}
```

## Technical Notes

- Sun calculations use the `astral` library for accuracy
- Patterns are generated locally (no external API calls)
- Calculations account for atmospheric refraction
- Works at all latitudes (equator to poles)
- Handles edge cases (midnight sun, polar night)

## Support

For issues or questions:
- Check the [main README](../README.md) for technical details
- Review plugin logs for error messages
- Verify configuration settings
- Test with known coordinates (San Francisco example above)
