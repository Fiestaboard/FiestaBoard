# Air Quality & Fog Monitoring Setup Guide

The Air Quality & Fog feature monitors air quality (AQI from PM2.5) and fog conditions, providing intelligent alerts for Bay Area fog and wildfire smoke. Perfect for planning your day and staying informed about air quality.

## Overview

**What it does:**
- Real-time Air Quality Index (AQI) from PM2.5 concentrations
- Intelligent fog detection based on visibility and weather
- Pollen/allergen levels (grass, tree, weed) via Open-Meteo (free, no API key)
- Wildfire smoke alerts when AQI > 100
- Dew point calculation for fog prediction
- Dual data sources: PurpleAir (air quality) + OpenWeatherMap (visibility) + Open-Meteo (pollen)
- Color-coded alerts (green/yellow/orange/red)

**Use Cases:**
- Monitor air quality during wildfire season
- Track San Francisco fog conditions ("Karl the Fog")
- Plan outdoor activities based on air quality
- Get early morning fog alerts before commuting
- Health monitoring for sensitive individuals

## Prerequisites

At least one API key required:
- ✅ **PurpleAir API key** (optional, for air quality)
- ✅ **OpenWeatherMap API key** (optional, for visibility/fog)

**Note:** You need at least one API key. Both are recommended for full features.

## Quick Setup

### 1. Get API Keys

#### PurpleAir (Air Quality Data)

1. Go to [purpleair.com](https://www2.purpleair.com/)
2. Create a free account
3. Go to **API Keys** section
4. Generate API key
5. Copy your API key

**Features with PurpleAir:**
- Real-time PM2.5 measurements
- AQI calculation
- Wildfire smoke detection
- Nearby sensor averaging

#### OpenWeatherMap (Visibility/Fog Data)

1. Go to [openweathermap.org](https://openweathermap.org/)
2. Sign up for free account
3. Go to **API Keys** section
4. Copy your API key (usually auto-generated)

**Features with OpenWeatherMap:**
- Visibility measurements
- Humidity and temperature
- Fog detection
- Dew point calculation

### 2. Enable Air Quality & Fog

Via Web UI (Recommended):
1. Go to the **Integrations** page
2. Find **Air Quality & Fog** section
3. Toggle the **Air Quality & Fog** plugin on
4. Enter your API keys (at least one)
5. Click **Save Changes**

Via Environment Variables:
```bash
# Add to .env
AIR_FOG_ENABLED=true

# PurpleAir settings (optional)
PURPLEAIR_API_KEY=your_purpleair_api_key_here
PURPLEAIR_SENSOR_ID=  # Optional: specific sensor ID

# OpenWeatherMap settings (optional)
OPENWEATHERMAP_API_KEY=your_openweathermap_api_key_here

# Location (default: San Francisco)
AIR_FOG_LATITUDE=40.7128
AIR_FOG_LONGITUDE=-74.0060

# Refresh interval (default: 5 minutes)
AIR_FOG_REFRESH_SECONDS=300
```

### 3. Configure Location (Optional)

**Default Location:** Example coordinates (40.7128, -74.0060)

To monitor a different location:

Via Web UI:
1. Go to the **Air Quality & Fog** plugin on the **Integrations** page
2. Enter **Latitude** and **Longitude**
3. Click **Save Changes**

Via Environment Variables:
```bash
# Example: Oakland
AIR_FOG_LATITUDE=37.8044
AIR_FOG_LONGITUDE=-122.2712

# Example: Berkeley
AIR_FOG_LATITUDE=37.8715
AIR_FOG_LONGITUDE=-122.2730
```

### 4. (Optional) Specify PurpleAir Sensor

For precise monitoring of a specific sensor:

```bash
PURPLEAIR_SENSOR_ID=12345
```

Without a sensor ID, FiestaBoard averages nearby outdoor sensors within ~5km.

### 5. Create a Page to Display Air Quality/Fog Data

1. Go to **Pages** and click **New**
2. Choose **Template** page type
3. Add your template using air quality variables:

**Example Template:**
```
{center}AIR & FOG
{air_fog.formatted}
AQI: {air_fog.aqi}
Fog: {air_fog.fog_status}
```

4. **Save** and **Set as Active**

## Template Variables

### Pre-Formatted Message

```
{air_fog.formatted}           # Pre-formatted display string
```

### Air Quality

```
{air_fog.aqi}                 # Air Quality Index value (e.g., "42")
{air_fog.air_status}          # Status text (e.g., "AIR: GOOD", "AIR: UNHEALTHY")
{air_fog.air_color}           # Color code (GREEN, YELLOW, ORANGE, RED, PURPLE, MAROON)
```

### Fog Conditions

```
{air_fog.fog_status}          # Fog status (e.g., "FOG: HEAVY", "CLEAR")
{air_fog.fog_color}           # Color code (GREEN, YELLOW, ORANGE)
{air_fog.is_foggy}            # Boolean: "true" or "false"
{air_fog.visibility}          # Visibility in meters
```

### Pollen / Allergens

Pollen data from [Open-Meteo](https://open-meteo.com/) — free, no API key required.

```
{air_fog.grass_pollen}        # Grass pollen concentration (grains/m³)
{air_fog.grass_pollen_level}  # Severity: LOW, MODERATE, HIGH, VERY HIGH
{air_fog.grass_pollen_color}  # Color code based on severity
{air_fog.tree_pollen}         # Tree pollen concentration (grains/m³, birch+alder+olive)
{air_fog.tree_pollen_level}   # Severity: LOW, MODERATE, HIGH, VERY HIGH
{air_fog.tree_pollen_color}   # Color code based on severity
{air_fog.weed_pollen}         # Weed pollen concentration (grains/m³, ragweed+mugwort)
{air_fog.weed_pollen_level}   # Severity: LOW, MODERATE, HIGH, VERY HIGH
{air_fog.weed_pollen_color}   # Color code based on severity
```

## AQI Categories & Color Coding

Air quality automatically categorized using US EPA standards:

### GOOD 🟢 (0-50)
- **Color**: GREEN
- **Meaning**: Air quality is satisfactory
- **Action**: None, enjoy outdoor activities

### MODERATE 🟡 (51-100)
- **Color**: YELLOW
- **Meaning**: Acceptable for most people
- **Action**: Unusually sensitive people should consider limiting prolonged outdoor exertion

### UNHEALTHY FOR SENSITIVE GROUPS 🟠 (101-150)
- **Color**: ORANGE
- **Meaning**: Sensitive groups may experience effects
- **Action**: Children, elderly, and people with respiratory conditions should limit outdoor exertion

### UNHEALTHY 🔴 (151-200)
- **Color**: RED
- **Meaning**: Everyone may experience effects
- **Action**: Everyone should limit prolonged outdoor exertion

### VERY UNHEALTHY 🟣 (201-300)
- **Color**: PURPLE
- **Meaning**: Health alert, everyone may experience serious effects
- **Action**: Everyone should avoid prolonged outdoor exertion

### HAZARDOUS 🟤 (301+)
- **Color**: MAROON
- **Meaning**: Emergency conditions
- **Action**: Everyone should avoid all outdoor activities

## Fog Detection Logic

Intelligent fog detection based on multiple factors:

### HEAVY FOG 🟠 (Orange)
Triggered when:
- **Visibility** < 1,600 meters (1 mile) OR
- **Humidity** > 95% AND **Temperature** < 60°F

**Action**: Expect significantly reduced visibility

### LIGHT FOG 🟡 (Yellow)
Triggered when:
- **Visibility** between 1,600-3,000 meters

**Action**: Some reduction in visibility

### CLEAR 🟢 (Green)
- **Visibility** > 3,000 meters
- **Normal conditions**

## Example Templates

![Air Quality and Fog Display](./air-fog-display.png)

### Compact Alert

```
{center}AIR & FOG
{air_fog.formatted}
{air_fog.air_status}
```

Output example:
```
     AIR & FOG
AQI:42 VIS:0.8mi
AIR: GOOD
```

### Allergy & Health

```
{center}ALLERGY & HEALTH
{{air_fog.grass_pollen_color}} GRASS: {air_fog.grass_pollen}
{{air_fog.tree_pollen_color}} TREES: {air_fog.tree_pollen}
{{air_fog.weed_pollen_color}} WEEDS: {air_fog.weed_pollen}
AQI: {air_fog.aqi}
```

Output example:
```
  ALLERGY & HEALTH
🟢 GRASS: 0
🟠 TREES: 65
🟢 WEEDS: 0
AQI: 32
```

### Detailed Conditions

```
{center}AIR QUALITY & FOG
AQI: {air_fog.aqi} ({air_fog.air_status})

Visibility: {air_fog.visibility}m
Fog: {air_fog.fog_status}
```

### Simple AQI Only

```
{center}AIR QUALITY
{air_fog.air_status}
AQI: {air_fog.aqi}
```

### Fog Alert Only

```
{center}FOG CONDITIONS
{air_fog.fog_status}
Visibility: {air_fog.visibility}m
```

### Morning Commute Check

```
{center}MORNING CONDITIONS
{air_fog.formatted}

Weather: {weather.temperature}°
Commute: {traffic.routes.0.duration_minutes}m
```

### With Color Coding

```
{center}AIR & FOG
{{air_fog.air_color}}{air_fog.air_status}
{{air_fog.fog_color}}{air_fog.fog_status}
AQI:{air_fog.aqi} VIS:{air_fog.visibility}m
```

## Configuration Reference

### Environment Variables

```bash
# Enable monitoring
AIR_FOG_ENABLED=true

# PurpleAir configuration (optional, for air quality)
PURPLEAIR_API_KEY=your_purpleair_api_key_here
PURPLEAIR_SENSOR_ID=  # Optional: specific sensor

# OpenWeatherMap configuration (optional, for visibility/fog)
OPENWEATHERMAP_API_KEY=your_openweathermap_api_key_here

# Location (default: San Francisco)
AIR_FOG_LATITUDE=40.7128
AIR_FOG_LONGITUDE=-74.0060

# Refresh interval (seconds, default: 300 = 5 minutes)
AIR_FOG_REFRESH_SECONDS=300
```

### config.json Format

```json
{
  "features": {
    "air_fog": {
      "enabled": true,
      "purpleair_api_key": "your_key",
      "purpleair_sensor_id": null,
      "openweathermap_api_key": "your_key",
      "latitude": 40.7128,
      "longitude": -74.0060,
      "refresh_seconds": 300
    }
  }
}
```

## Tips and Best Practices

### API Key Strategy

**Option 1: Both APIs (Recommended)**
- Full features (AQI + fog detection)
- Most accurate and reliable
- Best user experience

**Option 2: PurpleAir Only**
- Air quality monitoring only
- Good for wildfire season
- Missing visibility/fog data

**Option 3: OpenWeatherMap Only**
- Fog detection only
- Missing PM2.5 air quality
- Good for fog-prone areas

### Location Selection

1. **Urban areas**: Use general city coordinates
2. **Specific neighborhood**: Use precise coordinates for local conditions
3. **Multiple locations**: Create separate pages for different spots
4. **Sensor selection**: Specify PurpleAir sensor ID for exact location

### Refresh Interval

- **300 seconds (5 min)**: Default, good for most uses
- **180 seconds (3 min)**: More frequent updates during poor air quality
- **600 seconds (10 min)**: Less frequent, save API calls
- **900 seconds (15 min)**: Casual monitoring

**Note:** Air quality and fog don't change rapidly, 5-minute refresh is plenty.

### Wildfire Season Monitoring

During wildfire season (typically July-November in California):
- **Check AQI before outdoor activities**
- **Set lower refresh interval** (3-5 minutes)
- **Monitor for UNHEALTHY levels** (AQI > 150)
- **Keep windows closed** when AQI > 100
- **Use N95 masks** when AQI > 150

### Karl the Fog (SF Fog)

San Francisco's famous fog is most common:
- **Months**: June-August (summer fog season)
- **Time**: Morning and evening
- **Areas**: Western neighborhoods, Ocean Beach, Golden Gate
- **Pattern**: Burns off by afternoon, returns evening

## Troubleshooting

### No Data Showing

**Problem:** Air quality/fog data empty or not loading

**Solutions:**
1. **Check API keys**: Verify at least one key is correct
2. **Test APIs directly**:
   ```bash
   # PurpleAir
   curl -H "X-API-Key: YOUR_KEY" "https://api.purpleair.com/v1/sensors/12345"
   
   # OpenWeatherMap
   curl "https://api.openweathermap.org/data/2.5/weather?lat=40.7128&lon=-74.0060&appid=YOUR_KEY"
   ```
3. **Check logs**: Look for API errors
4. **Verify location**: Ensure coordinates are valid
5. **Restart service**: Docker containers might need restart

### AQI Shows Zero or Very Low Always

**Problem:** AQI always shows 0 or very low

**Solutions:**
1. **Check PurpleAir key**: Ensure key is valid and active
2. **Verify sensors nearby**: Your area might not have sensors
3. **Check sensor ID**: If specified, ensure it's correct
4. **Location**: Try city center coordinates (more sensors)
5. **Check PurpleAir map**: https://map.purpleair.com/

### No Fog Detection

**Problem:** Fog status always shows CLEAR

**Solutions:**
1. **Check OpenWeatherMap key**: Ensure key is valid
2. **Verify visibility data**: Some locations might not report visibility
3. **Check thresholds**: Fog requires visibility < 1600m or high humidity + low temp
4. **Time of day**: Fog more common morning/evening
5. **Season**: Fog seasonal in many areas

### High API Usage / Rate Limiting

**Problem:** API rate limit errors

**Solutions:**
1. **Increase refresh interval**: Set to 600 or 900 seconds
2. **Check free tier limits**:
   - PurpleAir: Generous limits
   - OpenWeatherMap: 60 calls/minute, 1000/day free tier
3. **Verify no duplicate requests**: Check logs
4. **Consider paid tier**: If limits consistently exceeded

### Inaccurate Readings

**Problem:** Data doesn't match other sources

**Solutions:**
1. **Check sensor location**: PurpleAir sensors vary by location
2. **Specify sensor ID**: Choose specific high-quality sensor
3. **Allow averaging**: Without sensor ID, system averages nearby sensors
4. **Compare sources**: Check PurpleAir map vs. AirNow.gov
5. **Consider micro-climate**: Local conditions vary

## Data Sources

### PurpleAir
- **API**: https://api.purpleair.com/
- **Coverage**: Community sensor network (thousands of sensors)
- **Measurement**: PM2.5 (particulate matter < 2.5 microns)
- **Update Frequency**: Real-time (10-30 second updates at sensors)
- **Free Tier**: Generous limits for personal use

### OpenWeatherMap
- **API**: https://api.openweathermap.org/
- **Coverage**: Global weather data
- **Measurement**: Visibility, temperature, humidity, weather conditions
- **Update Frequency**: Updated every 10 minutes
- **Free Tier**: 60 calls/minute, 1,000,000 calls/month

### Open-Meteo (Pollen / Allergens)
- **API**: https://open-meteo.com/en/docs/air-quality-api
- **Coverage**: Global pollen data
- **Measurement**: Grass, birch, alder, ragweed, mugwort, olive pollen (grains/m³)
- **Update Frequency**: Hourly
- **Free Tier**: Free for non-commercial use, no API key required

### AQI Calculation
- **Standard**: US EPA AQI formula for PM2.5
- **Method**: Linear interpolation between breakpoints
- **Reference**: https://www.airnow.gov/aqi/aqi-basics/

## Advanced Usage

### Combining Features

```
{center}DAILY BRIEFING
{air_fog.formatted}

Weather: {weather.temperature}° {weather.condition}
Surf: {surf.wave_height}ft {surf.quality}
Commute: {traffic.routes.0.duration_minutes}m
```

### Conditional Alerts

```python
# In advanced template logic
if air_fog.aqi > 150:
    display("⚠️ UNHEALTHY AIR - STAY INSIDE")
elif air_fog.is_foggy == "true":
    display("🌫️ FOG ALERT - DRIVE CAREFULLY")
else:
    display("✅ CONDITIONS NORMAL")
```

### Multiple Locations

Create separate pages for different locations:
- Home AQI
- Work AQI
- Kids' school AQI
- Outdoor activity location

## Health Guidelines by AQI

**0-50 (GOOD)**
- ✅ Outdoor activities safe for everyone

**51-100 (MODERATE)**
- ✅ Most people safe
- ⚠️ Unusually sensitive: consider reducing prolonged outdoor exertion

**101-150 (UNHEALTHY FOR SENSITIVE)**
- ⚠️ Children, elderly, respiratory conditions: limit outdoor exertion
- ✅ General public: can be outdoors

**151-200 (UNHEALTHY)**
- ⚠️ Everyone: limit prolonged outdoor exertion
- 🔴 Sensitive groups: avoid outdoor exertion

**201-300 (VERY UNHEALTHY)**
- 🔴 Everyone: avoid prolonged outdoor exertion
- 🚨 Sensitive groups: remain indoors

**301+ (HAZARDOUS)**
- 🚨 Everyone: avoid all outdoor activity
- 🏠 Remain indoors with windows closed
- 😷 Wear N95 mask if must go outside

## Related Features

- **Weather**: Combined air quality + weather conditions
- **Traffic**: Check AQI before commute decision
- **DateTime**: Time-based fog patterns (morning fog common)

## Resources

- [PurpleAir Map](https://map.purpleair.com/)
- [AirNow.gov](https://www.airnow.gov/) - Official US AQI
- [EPA AQI Guide](https://www.airnow.gov/aqi/aqi-basics/)
- [Bay Area Air Quality](https://www.baaqmd.gov/)
- [SF Fog Forecast](https://www.weatherstreet.com/states/california-fog-forecast.htm)

---

**Next Steps:**
1. Get API keys (PurpleAir and/or OpenWeatherMap)
2. Enable Air Quality & Fog in Settings
3. Enter API keys and configure location
4. Create a page with air quality/fog alerts
5. Set as active page or add to morning briefing
6. Stay informed and breathe easy! 🌬️

