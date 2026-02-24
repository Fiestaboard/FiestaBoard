# Weather Setup Guide

The Weather feature displays current weather conditions with temperature, weather icons, and detailed information. It's a core feature that can be combined with other data for a complete morning briefing.

![Weather Display](./weather-display.png)

## Overview

**What it does:**
- Current temperature and "feels like" temperature
- Weather condition text and icons
- Wind speed and direction
- Humidity percentage
- Configurable location(s)
- Choice of weather providers (WeatherAPI or OpenWeatherMap)

**Use Cases:**
- Quick weather check before leaving home
- Monitor weather at multiple locations
- Combine with traffic/transit for commute planning
- Morning briefing with complete conditions

## Prerequisites

- ✅ Weather API key (required)
- ✅ Choice of provider: WeatherAPI (recommended) or OpenWeatherMap
- ✅ Location(s) to monitor

## Quick Setup

### 1. Choose a Weather Provider

**Option A: WeatherAPI (Recommended)**
- Free tier: 1 million calls/month
- No credit card required
- Sign up at [weatherapi.com](https://www.weatherapi.com/)

**Option B: OpenWeatherMap**
- Free tier: 1,000 calls/day
- No credit card required
- Sign up at [openweathermap.org](https://openweathermap.org/)

### 2. Get Your API Key

#### WeatherAPI.com
1. Go to [weatherapi.com](https://www.weatherapi.com/)
2. Click **Sign Up Free**
3. Complete registration
4. Go to **Dashboard** → **API Key**
5. Copy your API key

#### OpenWeatherMap
1. Go to [openweathermap.org](https://openweathermap.org/)
2. Click **Sign Up** / **API**
3. Complete registration
4. Go to **API Keys** tab
5. Copy your API key (auto-generated on signup)

### 3. Enable Weather

Via Web UI (Recommended):
1. Go to the **Integrations** page
2. Find **Weather** section
3. Toggle the **Weather** plugin on
4. Select **Provider** (weatherapi or openweathermap)
5. Enter your **API Key**
6. Enter **Location** (e.g., "San Francisco, CA")
7. Click **Save Changes**

Via Environment Variables:
```bash
# Add to .env
WEATHER_ENABLED=true
WEATHER_API_KEY=your_api_key_here
WEATHER_PROVIDER=weatherapi  # or openweathermap
WEATHER_LOCATION=San Francisco, CA
WEATHER_REFRESH_SECONDS=300  # Optional: 5 minutes (default)
```

### 4. Configure Location

Single location:
```bash
WEATHER_LOCATION=San Francisco, CA
```

Multiple locations (in config.json):
```json
{
  "features": {
    "weather": {
      "enabled": true,
      "api_key": "your_key",
      "provider": "weatherapi",
      "locations": [
        {"location": "San Francisco, CA", "name": "HOME"},
        {"location": "Oakland, CA", "name": "WORK"},
        {"location": "Berkeley, CA", "name": "GYM"}
      ],
      "refresh_seconds": 300
    }
  }
}
```

### 5. Create a Page to Display Weather

1. Go to **Pages** and click **New**
2. Choose **Template** page type
3. Add your template using weather variables:

**Example Template:**
```
{center}WEATHER
{weather.temperature}° {weather.condition}
Feels like: {weather.feels_like}°
Humidity: {weather.humidity}%
Wind: {weather.wind_speed}mph
```

4. **Save** and **Set as Active**

## Template Variables

### Single Location

```
{weather.temperature}        # Current temperature (e.g., "68")
{weather.feels_like}         # Feels like temperature (e.g., "65")
{weather.condition}          # Weather condition (e.g., "Partly Cloudy")
{weather.humidity}           # Humidity percentage (e.g., "75")
{weather.wind_speed}         # Wind speed in mph (e.g., "12")
{weather.location}           # Location name (e.g., "San Francisco")
```

### Multiple Locations

Access by index (0-based):
```
{weather.locations.0.temperature}
{weather.locations.0.condition}
{weather.locations.0.name}   # Custom location name (e.g., "HOME")

{weather.locations.1.temperature}
{weather.locations.1.condition}
{weather.locations.1.name}   # e.g., "WORK"
```

### Weather Icons

Text-based icons for display:
```
{sun}      - Sunny/Clear
{cloud}    - Cloudy
{partly}   - Partly Cloudy
{rain}     - Rain
{storm}    - Thunderstorm
{snow}     - Snow
{fog}      - Fog/Mist
```

## Example Templates

### Simple Weather

```
{center}WEATHER
{weather.temperature}° {weather.condition}
Feels like: {weather.feels_like}°
```

Output:
```
     WEATHER
68° Partly Cloudy
Feels like: 65°
```

### Detailed Conditions

```
{center}SF WEATHER
Temp: {weather.temperature}° (Feels {weather.feels_like}°)
Conditions: {weather.condition}
Humidity: {weather.humidity}%
Wind: {weather.wind_speed}mph
```

### With Icon

```
{center}WEATHER {weather.condition}
{weather.temperature}° {weather.condition}
Humidity: {weather.humidity}%
Wind: {weather.wind_speed}mph
```

### Multiple Locations

```
{center}WEATHER
HOME: {weather.locations.0.temperature}° {weather.locations.0.condition}
WORK: {weather.locations.1.temperature}° {weather.locations.1.condition}
GYM:  {weather.locations.2.temperature}° {weather.locations.2.condition}
```

### Compact Multi-Location

```
{center}TEMPS
{weather.locations.0.name}: {weather.locations.0.temperature}°
{weather.locations.1.name}: {weather.locations.1.temperature}°
{weather.locations.2.name}: {weather.locations.2.temperature}°
```

### Weather + DateTime (Classic)

```
{center}{date_time.date}
{date_time.time}

{weather.temperature}° {weather.condition}
Feels like: {weather.feels_like}°
```

### Morning Briefing

```
{center}MORNING BRIEF
Weather: {weather.temperature}° {weather.condition}
Commute: {traffic.routes.0.duration_minutes}m
Muni: {muni.stops.0.formatted}
AQI: {air_fog.aqi}
```

## Configuration Reference

### Environment Variables

```bash
# Required
WEATHER_ENABLED=true
WEATHER_API_KEY=your_api_key_here
WEATHER_PROVIDER=weatherapi  # or openweathermap

# Location (single location format)
WEATHER_LOCATION=San Francisco, CA

# Optional
WEATHER_REFRESH_SECONDS=300  # Default: 300 (5 minutes)
```

### config.json Format

#### Single Location
```json
{
  "features": {
    "weather": {
      "enabled": true,
      "api_key": "your_key_here",
      "provider": "weatherapi",
      "location": "San Francisco, CA",
      "refresh_seconds": 300
    }
  }
}
```

#### Multiple Locations
```json
{
  "features": {
    "weather": {
      "enabled": true,
      "api_key": "your_key_here",
      "provider": "weatherapi",
      "locations": [
        {
          "location": "San Francisco, CA",
          "name": "HOME"
        },
        {
          "location": "Oakland, CA",
          "name": "WORK"
        },
        {
          "location": "Berkeley, CA",
          "name": "GYM"
        }
      ],
      "refresh_seconds": 300
    }
  }
}
```

## Location Formats

Both providers support flexible location formats:

**City, State**
```
San Francisco, CA
New York, NY
```

**City, Country**
```
London, UK
Tokyo, Japan
Paris, France
```

**Zip Code (US)**
```
94103
10001
```

**Coordinates** (lat,lon)
```
40.7128,-74.0060
40.7128,-74.0060
```

**City Only** (may be ambiguous)
```
Portland  (could be OR or ME)
Springfield  (many states have one)
```

**Recommendation:** Use "City, State" or "City, Country" for best results.

## Weather Providers Comparison

### WeatherAPI (Recommended)

**Pros:**
- ✅ More generous free tier (1M calls/month)
- ✅ No credit card required
- ✅ Excellent documentation
- ✅ Fast response times
- ✅ Detailed weather data

**Cons:**
- ❌ Relatively new service
- ❌ Smaller community

**Free Tier:**
- 1,000,000 calls/month
- Real-time weather
- 3-day forecast
- Historical data (7 days)

**Rate with FiestaBoard:**
- Default: 12 calls/hour = ~8,640/month
- Well within free tier limits

### OpenWeatherMap

**Pros:**
- ✅ Established, trusted provider
- ✅ Large community
- ✅ Extensive documentation
- ✅ Many integrations

**Cons:**
- ❌ Lower free tier (1,000 calls/day)
- ❌ Requires account activation time (~2 hours)

**Free Tier:**
- 1,000 calls/day = 30,000/month
- 60 calls/minute
- Current weather
- 5-day forecast

**Rate with FiestaBoard:**
- Default: 12 calls/hour = ~288/day
- Within free tier but less headroom

## Tips and Best Practices

### Provider Selection

**Choose WeatherAPI if:**
- ✅ You want more API headroom
- ✅ You want instant activation
- ✅ You prefer simpler setup

**Choose OpenWeatherMap if:**
- ✅ You already have an account
- ✅ You use it for other projects
- ✅ You prefer established providers

### Refresh Interval

- **300 seconds (5 min)**: Default, good balance
- **600 seconds (10 min)**: Less frequent, save API calls
- **900 seconds (15 min)**: Casual checking
- **180 seconds (3 min)**: More frequent (active weather watching)

**Note:** Weather doesn't change rapidly, 5-10 minute refresh is plenty.

### Location Naming

For multiple locations, use short, memorable names:
- ✅ "HOME", "WORK", "GYM", "BEACH"
- ❌ "My House in San Francisco", "The Office Building Downtown"

Keep names ≤ 8 characters for clean display.

### Multiple Locations

**Best uses:**
- Home vs. work comparison
- City vs. beach/mountain
- Multiple family members' locations
- Trip planning (departure + destination)

**Limitations:**
- Each location uses one API call per refresh
- Free tier limits apply to total calls

## Condition Mapping

Common weather conditions and their icons:

**Clear/Sunny**
- Clear, Sunny
- Icon: `{sun}`

**Partly Cloudy**
- Partly Cloudy, Partly Sunny
- Icon: `{partly}`

**Cloudy**
- Cloudy, Overcast
- Icon: `{cloud}`

**Rain**
- Light Rain, Rain, Heavy Rain, Drizzle
- Icon: `{rain}`

**Storm**
- Thunderstorm, Stormy
- Icon: `{storm}`

**Snow**
- Snow, Light Snow, Heavy Snow, Flurries
- Icon: `{snow}`

**Fog/Mist**
- Fog, Mist, Haze
- Icon: `{fog}`

## Troubleshooting

### No Weather Data

**Problem:** Weather not showing or empty

**Solutions:**
1. **Check API key**: Verify key is correct and active
2. **Check provider**: Ensure provider matches your key
3. **Test API directly**:
   ```bash
   # WeatherAPI
   curl "http://api.weatherapi.com/v1/current.json?key=YOUR_KEY&q=San Francisco"
   
   # OpenWeatherMap
   curl "http://api.openweathermap.org/data/2.5/weather?q=San Francisco&appid=YOUR_KEY&units=imperial"
   ```
4. **Check location format**: Try "City, State" format
5. **Check logs**: Look for API errors
6. **Restart service**: Docker containers might need restart

### OpenWeatherMap "Invalid API Key"

**Problem:** OWM says API key invalid even though it's correct

**Solutions:**
1. **Wait for activation**: New OWM keys take ~2 hours to activate
2. **Check key status**: Login to OWM dashboard
3. **Regenerate key**: Try generating a new key
4. **Free tier active**: Ensure free tier is enabled in account

### Location Not Found

**Problem:** "Location not found" error

**Solutions:**
1. **Use full format**: "San Francisco, CA" not just "San Francisco"
2. **Try coordinates**: Use lat,lon format (40.7128,-74.0060)
3. **Check spelling**: Verify city/state spelling
4. **Try zip code**: US zip codes work well
5. **Test in browser**: Try location in weather provider's website

### Stale Data

**Problem:** Weather seems outdated

**Solutions:**
1. **Check refresh interval**: Verify WEATHER_REFRESH_SECONDS
2. **Check logs**: Look for API errors
3. **Verify API status**: Weather provider might be down
4. **Clear cache**: Restart service
5. **Test API**: Ensure API returning fresh data

### Rate Limit Errors

**Problem:** "Rate limit exceeded" in logs

**Solutions:**
1. **Increase refresh interval**: Set to 600 or 900 seconds
2. **Check multiple calls**: If using multiple locations, each counts
3. **Verify free tier limits**:
   - WeatherAPI: 1M/month
   - OpenWeatherMap: 1K/day
4. **Consider paid tier**: If consistently hitting limits

## Advanced Usage

### Combining with DateTime

```
{center}{date_time.day_of_week}, {date_time.date}
{date_time.time}

{weather.temperature}° {weather.condition}
Humidity: {weather.humidity}%
```

### Weather-Based Alerts

```python
# In advanced template logic
if weather.temperature > 90:
    display("🔥 HOT DAY - Stay hydrated!")
elif weather.condition == "Rain":
    display("☔ Bring an umbrella!")
elif weather.temperature < 40:
    display("🧊 COLD - Bundle up!")
```

### Comparison Display

```
{center}WEATHER COMPARISON
HOME: {weather.locations.0.temperature}°
WORK: {weather.locations.1.temperature}°
DIFF: {weather.locations.1.temperature - weather.locations.0.temperature}°
```

### Complete Dashboard

```
{center}DAILY BRIEF
{date_time.date} {date_time.time}

Weather: {weather.temperature}° {weather.condition}
AQI: {air_fog.aqi}
Surf: {surf.wave_height}ft {surf.quality}
Commute: {traffic.routes.0.duration_minutes}m
Transit: {muni.stops.0.formatted}
```

## API Reference

### REST API Endpoints

```bash
# Get formatted weather display
GET /displays/weather

# Get raw weather data
GET /displays/weather/raw
```

## Related Features

- **DateTime**: Combine for classic weather + time display
- **Air Quality**: Weather + AQI for outdoor planning
- **Surf**: Weather conditions for surf spots
- **Traffic**: Weather affects commute times
- **Home Assistant**: Indoor vs. outdoor temperature

## Resources

### WeatherAPI
- [Website](https://www.weatherapi.com/)
- [Documentation](https://www.weatherapi.com/docs/)
- [API Explorer](https://www.weatherapi.com/api-explorer.aspx)
- [Pricing](https://www.weatherapi.com/pricing.aspx)

### OpenWeatherMap
- [Website](https://openweathermap.org/)
- [Documentation](https://openweathermap.org/api)
- [API Guide](https://openweathermap.org/current)
- [Pricing](https://openweathermap.org/price)

### General
- [Weather Condition Codes](https://www.weatherapi.com/docs/weather_conditions.json)
- [Wind Speed Beaufort Scale](https://en.wikipedia.org/wiki/Beaufort_scale)

---

**Next Steps:**
1. Get your weather API key (WeatherAPI recommended)
2. Enable Weather in Settings
3. Enter API key and configure location(s)
4. Create a page with weather conditions
5. Set as active or combine with other features for complete briefing
6. Enjoy your weather at a glance! ☀️

