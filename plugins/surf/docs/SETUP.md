# Surf Conditions Setup Guide

The Surf feature provides real-time surf conditions including wave height, swell period, wind data, and automatic quality ratings. Perfect for surfers checking conditions before heading out.

## Overview

**What it does:**
- Real-time wave height (in feet) and swell period (in seconds)
- Wind speed and direction
- Automatic surf quality assessment based on conditions
- Configurable location (uses example coordinates by default)
- No API key required (uses free Open-Meteo Marine API)

**Use Cases:**
- Check surf before heading to the beach
- Monitor swell period for quality waves
- Track wind conditions for optimal surfing
- Get instant quality ratings (EXCELLENT, GOOD, FAIR, POOR)

## Prerequisites

- ✅ No API key required
- ✅ Coastal location with surf conditions
- ✅ Internet connection

## Quick Setup

### 1. Enable Surf Monitoring

Via Web UI (Recommended):
1. Go to the **Integrations** page
2. Find **Surf Conditions** section
3. Toggle the **Surf** plugin on
4. Click **Save Changes**

Via Environment Variables:
```bash
# Add to .env
SURF_ENABLED=true
SURF_LATITUDE=34.0259   # Example location (default)
SURF_LONGITUDE=-118.7798  # Example location (default)
SURF_REFRESH_SECONDS=600  # Optional: 10 minutes (default)
```

### 2. Configure Location (Optional)

**Default Location:** Example coordinates (34.0259, -118.7798)

To monitor a different surf spot:

Via Web UI:
1. Go to the **Surf** plugin on the **Integrations** page
2. Enter **Latitude** and **Longitude**
3. Click **Save Changes**

Via Environment Variables:
```bash
# Example: Santa Cruz
SURF_LATITUDE=36.9500
SURF_LONGITUDE=-122.0200

# Example: Pacifica
SURF_LATITUDE=37.6099
SURF_LONGITUDE=-122.4968

# Example: Half Moon Bay
SURF_LATITUDE=37.5028
SURF_LONGITUDE=-122.4782
```

### 3. Create a Page to Display Surf Data

1. Go to **Pages** and click **New**
2. Choose **Template** page type
3. Add your template using surf variables:

**Example Template:**
```
{center}SURF REPORT
{surf.formatted}
Quality: {surf.quality}
Wind: {surf.wind_speed}mph {surf.wind_direction}
```

4. **Save** and **Set as Active**

## Template Variables

### Pre-Formatted Message

```
{surf.formatted}
# Example: "OB SURF: 4.5ft @ 12s"
```

Includes location abbreviation, wave height, and swell period.

### Wave Data

```
{surf.wave_height}           # Wave height in feet (e.g., "4.5")
{surf.swell_period}          # Swell period in seconds (e.g., "12.0")
```

### Wind Conditions

```
{surf.wind_speed}            # Wind speed in mph (e.g., "8.5")
{surf.wind_direction}        # Wind direction (e.g., "W")
```

### Quality Rating

```
{surf.quality}               # Quality rating (EXCELLENT, GOOD, FAIR, POOR)
{surf.quality_color}         # Color for display (GREEN, YELLOW, ORANGE, RED)
```

## Quality Rating System

Surf quality is automatically calculated based on swell period and wind conditions:

### EXCELLENT 🟢 (Green)
- **Swell Period**: > 12 seconds
- **Wind Speed**: < 12 mph
- **Conditions**: Long period swell with light winds
- **Best for**: All surfers, clean waves

### GOOD 🟡 (Yellow)
- **Swell Period**: > 10 seconds
- **Wind Speed**: < 15 mph
- **Conditions**: Decent period swell with moderate winds
- **Best for**: Intermediate+ surfers

### FAIR 🟠 (Orange)
- **Swell Period**: > 8 seconds OR
- **Wind Speed**: < 20 mph
- **Conditions**: Manageable but not ideal
- **Best for**: Experienced surfers, practice days

### POOR 🔴 (Red)
- **Swell Period**: ≤ 8 seconds
- **Wind Speed**: ≥ 20 mph
- **Conditions**: Short period swell with strong winds
- **Best for**: Stay home, check back later

## Example Templates

![Surf Conditions Display](./surf-display.png)

### Compact Report

```
{center}SURF CHECK
{surf.formatted}
{surf.quality}
Wind: {surf.wind_speed}mph {surf.wind_direction}
```

Output:
```
     SURF CHECK
OB SURF: 4.5ft @ 12s
EXCELLENT
Wind: 8mph W
```

### Detailed Conditions

```
{center}EXAMPLE SURF SPOT
Wave Height: {surf.wave_height}ft
Swell Period: {surf.swell_period}s
Quality: {surf.quality}
Wind: {surf.wind_speed}mph {surf.wind_direction}
```

### Quick Check

```
{center}SURF: {surf.quality}
{surf.wave_height}ft @ {surf.swell_period}s
Wind: {surf.wind_speed}mph
```

### With Color Coding

```
{center}SURF CONDITIONS
{surf.formatted}
{{surf.quality_color}}{surf.quality}
Wind: {surf.wind_direction} {surf.wind_speed}mph
```

### Multi-Location (Manual)

For multiple locations, configure different instances or create manual display:

```
{center}EXAMPLE SURF SPOTS
Spot A: 4-5ft @ 12s GOOD
Spot B: 3-4ft @ 10s FAIR
Spot C: 5-6ft @ 14s EXCELLENT
```

## Configuration Reference

### Environment Variables

```bash
# Enable surf monitoring
SURF_ENABLED=true

# Location coordinates (example values)
SURF_LATITUDE=34.0259
SURF_LONGITUDE=-118.7798

# Refresh interval in seconds (default: 600 = 10 minutes)
SURF_REFRESH_SECONDS=600
```

### config.json Format

```json
{
  "features": {
    "surf": {
      "enabled": true,
      "latitude": 34.0259,
      "longitude": -118.7798,
      "refresh_seconds": 600
    }
  }
}
```

## Example Surf Spot Coordinates

**Example Locations:**
- Example location: `34.0259, -118.7798` (default)
- Fort Point: `37.8107, -122.4744`

**Pacifica**
- Linda Mar: `37.6099, -122.4968`
- Rockaway Beach: `37.6091, -122.4969`

**Half Moon Bay**
- Mavericks: `37.4925, -122.4977`
- Half Moon Bay: `37.5028, -122.4782`

**Santa Cruz**
- Steamer Lane: `36.9520, -122.0273`
- Pleasure Point: `36.9652, -121.9788`

**Marin**
- Stinson Beach: `37.9015, -122.6438`
- Bolinas: `37.9099, -122.6863`

## Understanding Surf Metrics

### Wave Height

- **Measurement**: Maximum wave height in feet
- **Good waves**: 3-6 feet for most surfers
- **Big waves**: 6+ feet for experienced surfers
- **Flat**: < 2 feet, usually not worth surfing

### Swell Period

- **What it is**: Time between wave sets in seconds
- **Short period** (< 8s): Wind swell, choppy, weak waves
- **Medium period** (8-12s): Mixed swell, rideable
- **Long period** (> 12s): Ground swell, powerful, clean waves
- **Ideal**: 12-16 seconds for quality surf

### Wind Conditions

**Direction Matters:**
- **Offshore wind** (from land): Cleans up waves, improves shape
- **Onshore wind** (from ocean): Messes up waves, creates chop
- **Cross-shore**: Moderate effect

**Speed Matters:**
- **< 10 mph**: Ideal, glassy conditions
- **10-15 mph**: Good, manageable
- **15-20 mph**: Choppy, more difficult
- **> 20 mph**: Poor conditions, blown out

### Cardinal Directions

- **N** (North): 0°
- **NE** (Northeast): 45°
- **E** (East): 90°
- **SE** (Southeast): 135°
- **S** (South): 180°
- **SW** (Southwest): 225°
- **W** (West): 270°
- **NW** (Northwest): 315°

## Tips and Best Practices

### Checking Conditions

1. **Check early**: Conditions often best in morning (lighter wind)
2. **Multiple checks**: Conditions change throughout day
3. **Swell period matters**: Prioritize long-period swells
4. **Wind direction**: Know if offshore/onshore for your spot
5. **Tide awareness**: Some spots better at certain tides (not shown in data)

### Refresh Interval

- **600 seconds (10 min)**: Default, good balance
- **300 seconds (5 min)**: If conditions changing rapidly
- **900 seconds (15 min)**: Less frequent updates, save API calls
- **1800 seconds (30 min)**: Casual checking

**Note:** Marine conditions don't change rapidly, 10-15 minute refresh is plenty.

### Location Accuracy

- Use coordinates of actual surf break
- Offshore spots may show different conditions than beach
- Bay-facing spots have different swell exposure than ocean-facing

### Quality Rating Context

Quality ratings are automated but consider:
- **Crowd levels**: Not factored in
- **Tide**: Not factored in (some spots tide-dependent)
- **Local knowledge**: Automated rating is a guide, not absolute
- **Skill level**: "FAIR" for experts might be "POOR" for beginners

## Troubleshooting

### No Data Showing

**Problem:** Surf data empty or not loading

**Solutions:**
1. **Check location**: Verify coordinates are correct
2. **Check logs**: Look for Open-Meteo API errors
3. **Test API directly**:
   ```bash
   curl "https://marine-api.open-meteo.com/v1/marine?latitude=34.0259&longitude=-118.7798&current=wave_height,swell_wave_period"
   ```
4. **Verify coastal location**: API works best for coastal coordinates
5. **Restart service**: Docker containers might need restart

### Wave Height Shows Zero

**Problem:** Wave height always 0 or very low

**Solutions:**
1. **Check location**: Might be too far from coast or in bay
2. **Check for swell**: No swell = no waves (seasonal)
3. **Verify coordinates**: Ensure lat/lon correct for surf spot
4. **Time of year**: Some locations have seasonal swell patterns

### Quality Rating Unexpected

**Problem:** Quality doesn't match expectations

**Solutions:**
1. **Check thresholds**: Review quality calculation logic
2. **Local conditions**: Automated rating doesn't know your spot
3. **Other factors**: Tide, sandbars, crowd not factored in
4. **Use as guide**: Combine with local knowledge and cams

### Stale Data

**Problem:** Conditions don't seem current

**Solutions:**
1. **Check refresh interval**: Verify SURF_REFRESH_SECONDS
2. **Check logs**: Look for API errors
3. **Verify API status**: Open-Meteo might be down
4. **Restart service**: Clear any stuck caches

## Data Source

Surf uses **Open-Meteo Marine API**:

- **API**: https://marine-api.open-meteo.com/
- **Coverage**: Global ocean and coastal areas
- **Update Frequency**: Every 1-3 hours at source
- **Forecast**: Includes current and forecast data
- **Rate Limits**: Very generous, free tier sufficient
- **No API Key**: Completely free to use

**Wind Data** from Open-Meteo Weather API:
- **API**: https://api.open-meteo.com/
- **Same Coverage**: Global
- **Complements**: Marine API with wind data

## Advanced Usage

### Combining with Other Features

```
{center}MORNING SURF CHECK
{surf.formatted}
Quality: {surf.quality}

Weather: {weather.temperature}° {weather.condition}
Commute: {muni.stops.0.formatted}
```

### Multiple Spots (Manual)

```
{center}BAY AREA SURF
OB: {surf.wave_height}ft GOOD
PC: 3ft FAIR
SC: 5ft EXCELLENT
Check cams before driving!
```

### Conditional Display

```python
# In advanced template logic
if surf.quality == "EXCELLENT":
    display("GO SURF NOW! 🏄")
elif surf.quality == "GOOD":
    display("Worth checking out")
else:
    display("Maybe tomorrow...")
```

## API Reference

### REST API Endpoints

```bash
# Get formatted surf display
GET /displays/surf

# Get raw surf data
GET /displays/surf/raw
```

Response includes all surf variables (wave_height, swell_period, quality, etc.)

## Related Features

- **Weather**: Check air temperature before heading out
- **Traffic**: See drive time to beach
- **DateTime**: Current time for early morning sessions

## Resources

- [Open-Meteo Marine API](https://open-meteo.com/en/docs/marine-weather-api)
- [NOAA Wave Watch](https://polar.ncep.noaa.gov/waves/)
- [Surfline](https://www.surfline.com/) - Commercial surf forecasts
- [Buoy Data](https://www.ndbc.noaa.gov/) - Raw buoy readings

## Understanding Swell Direction

While current implementation shows wave height and period, swell direction also matters:

**For example surf locations:**
- **NW Swell**: Most common, clean waves
- **W Swell**: Good conditions
- **SW Swell**: Can be good but depends on sandbar
- **N Swell**: Rare, often blown out

**For Santa Cruz:**
- **NW-W Swell**: Best conditions
- **SW Swell**: Works at many spots
- **S Swell**: Summer swells, warmer water

Check local surf reports for swell direction details.

---

**Next Steps:**
1. Enable Surf in Settings
2. Configure your favorite surf spot location
3. Create a page with surf conditions
4. Set as active page or combine with morning briefing
5. Check conditions before your session!

🏄 **Happy surfing!**

