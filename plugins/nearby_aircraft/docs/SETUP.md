# Nearby Aircraft Setup Guide

The Nearby Aircraft feature displays real-time information about aircraft flying within a specified radius of your location. Shows call sign, altitude, ground speed, and squawk code - perfect for aviation enthusiasts, pilots, or anyone curious about what's flying overhead.

## Overview

**What it does:**
- Displays up to 10 nearby aircraft in real-time
- Shows call sign, altitude (feet), ground speed (knots), and squawk code
- Updates automatically based on your refresh interval
- Supports authenticated and unauthenticated API access
- Filters aircraft by distance from your location

**Use Cases:**
- Monitor aircraft traffic near your location
- Track commercial flights overhead
- Educational tool for aviation enthusiasts
- Real-time air traffic awareness

## Prerequisites

- ✅ Coordinates (latitude, longitude) for your location
- ✅ Optional: OpenSky Network account for higher rate limits
- ✅ Internet connection for API access

## Quick Setup

### 1. Enable Nearby Aircraft

Via Web UI (Recommended):
1. Go to the **Integrations** page
2. Find **Nearby Aircraft** section
3. Toggle the **Nearby Aircraft** plugin on
4. Enter your **Latitude** and **Longitude**
5. Set **Radius (km)** (default: 50 km)
6. Click **Save Changes**

Via Environment Variables:
```bash
# Add to .env
NEARBY_AIRCRAFT_ENABLED=true
NEARBY_AIRCRAFT_LATITUDE=40.7128
NEARBY_AIRCRAFT_LONGITUDE=-74.0060
NEARBY_AIRCRAFT_RADIUS_KM=50
NEARBY_AIRCRAFT_MAX_COUNT=4
NEARBY_AIRCRAFT_REFRESH_SECONDS=120
```

### 2. Find Your Coordinates

**Option 1: Google Maps**
1. Open [Google Maps](https://www.google.com/maps)
2. Right-click on your location
3. Click the coordinates at the top
4. Copy latitude and longitude

**Option 2: GPS Device**
- Use your phone's GPS or a dedicated GPS device
- Format: Decimal degrees (e.g., 40.7128, -74.0060)

**Option 3: Online Tools**
- [LatLong.net](https://www.latlong.net/)
- [GPS Coordinates](https://www.gps-coordinates.net/)

### 3. (Optional) Get OpenSky API Credentials

For higher rate limits and better reliability:

1. **Create Account**
   - Go to [OpenSky Network](https://opensky-network.org/)
   - Click **Sign Up** or **Login**
   - Create a free account

2. **Generate API Client**
   - Log in to your account
   - Go to **Account** → **API Clients**
   - Click **Create New Client**
   - Copy your **Client ID** and **Client Secret**

3. **Add Credentials**
   - In the **Nearby Aircraft** plugin on the **Integrations** page
   - Paste **Client ID** and **Client Secret**
   - Click **Save Changes**

**Rate Limits:**
- **Unauthenticated**: 400 API credits/day (1 request per 10 seconds)
- **Authenticated**: 4,000 API credits/day (~10 requests per second)
- **Active Contributors**: 8,000 API credits/day (with ADS-B receiver)

## Configuration Reference

### Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| enabled | boolean | false | Enable/disable the plugin |
| latitude | number | - | Center latitude (-90 to 90) |
| longitude | number | - | Center longitude (-180 to 180) |
| radius_km | number | 50 | Search radius in kilometers |
| client_id | string | - | OpenSky OAuth2 client ID (optional) |
| client_secret | string | - | OpenSky OAuth2 client secret (optional) |
| max_aircraft | integer | 4 | Maximum aircraft to display (1-10) |
| refresh_seconds | integer | 120 | Update interval (minimum 10 seconds) |

### Environment Variables

```bash
# Required
NEARBY_AIRCRAFT_ENABLED=true
NEARBY_AIRCRAFT_LATITUDE=40.7128
NEARBY_AIRCRAFT_LONGITUDE=-74.0060

# Optional
NEARBY_AIRCRAFT_RADIUS_KM=50          # Default: 50 km
OPENSKY_CLIENT_ID=your_client_id      # For authenticated access
OPENSKY_CLIENT_SECRET=your_secret     # For authenticated access
NEARBY_AIRCRAFT_MAX_COUNT=4           # Default: 4 aircraft
NEARBY_AIRCRAFT_REFRESH_SECONDS=120   # Default: 120 seconds (2 min)
```

### config.json Format

```json
{
  "features": {
    "nearby_aircraft": {
      "enabled": true,
      "latitude": 40.7128,
      "longitude": -74.0060,
      "radius_km": 50,
      "client_id": "your_client_id",
      "client_secret": "your_client_secret",
      "max_aircraft": 4,
      "refresh_seconds": 120
    }
  }
}
```

## Template Variables

### Primary Aircraft (Closest)

```
{{nearby_aircraft.call_sign}}        # Call sign (e.g., "AAY453")
{{nearby_aircraft.altitude}}         # Altitude in feet (e.g., "4575")
{{nearby_aircraft.ground_speed}}     # Ground speed in knots (e.g., "279")
{{nearby_aircraft.squawk}}           # Squawk code (e.g., "1603")
{{nearby_aircraft.formatted}}        # Pre-formatted line
{{nearby_aircraft.aircraft_count}}   # Number of aircraft found
```

### Individual Aircraft (Array)

```
{{nearby_aircraft.aircraft.0.call_sign}}        # First aircraft call sign
{{nearby_aircraft.aircraft.0.altitude}}         # First aircraft altitude
{{nearby_aircraft.aircraft.0.ground_speed}}     # First aircraft speed
{{nearby_aircraft.aircraft.0.squawk}}           # First aircraft squawk
{{nearby_aircraft.aircraft.0.formatted}}        # First aircraft formatted
{{nearby_aircraft.aircraft.0.distance_km}}      # Distance in km

{{nearby_aircraft.aircraft.1.call_sign}}        # Second aircraft
{{nearby_aircraft.aircraft.1.formatted}}         # Second aircraft formatted
```

## Example Templates

### Default Format (Matches Screenshot)

![Nearby Aircraft Display](./nearby-aircraft-display.png)

```
{center}NEARBY AIRCRAFT
{{nearby_aircraft.headers}}
{{nearby_aircraft.aircraft.0.formatted}}
{{nearby_aircraft.aircraft.1.formatted}}
{{nearby_aircraft.aircraft.2.formatted}}
{{nearby_aircraft.aircraft.3.formatted}}
```

**Note:** The `{{nearby_aircraft.headers}}` variable automatically generates aligned column headers that match the width of your aircraft data, ensuring perfect column alignment.

Output example:
```
   NEARBY AIRCRAFT
CALLSGN  ALT   GS  SQWK
ITY630   40000 393 2513
AAY453   4575  279 1603
DAL 1792 34150 490 2105
EDV5002  16925 437 3602
```

### Compact View

```
{center}AIRCRAFT OVERHEAD
{{nearby_aircraft.aircraft.0.call_sign}} {{nearby_aircraft.aircraft.0.altitude}}ft
{{nearby_aircraft.aircraft.1.call_sign}} {{nearby_aircraft.aircraft.1.altitude}}ft
{{nearby_aircraft.aircraft.2.call_sign}} {{nearby_aircraft.aircraft.2.altitude}}ft
```

### With Distance

```
{center}NEARBY AIRCRAFT
{{nearby_aircraft.aircraft.0.call_sign}} {{nearby_aircraft.aircraft.0.distance_km}}km
{{nearby_aircraft.aircraft.1.call_sign}} {{nearby_aircraft.aircraft.1.distance_km}}km
{{nearby_aircraft.aircraft.2.call_sign}} {{nearby_aircraft.aircraft.2.distance_km}}km
```

### Detailed View

```
{center}AIRCRAFT TRACKING
CALL: {{nearby_aircraft.call_sign}}
ALT: {{nearby_aircraft.altitude}}ft
SPD: {{nearby_aircraft.ground_speed}}kt
SQWK: {{nearby_aircraft.squawk}}
COUNT: {{nearby_aircraft.aircraft_count}}
```

## Refresh Interval Guidelines

Choose based on your needs and authentication status:

**Unauthenticated (No API Key):**
- **120 seconds (2 min)**: Default, safe for rate limits
- **300 seconds (5 min)**: Very safe, fewer API calls
- **60 seconds**: Possible but may hit rate limits

**Authenticated (With API Key):**
- **60 seconds (1 min)**: Frequent updates
- **30 seconds**: Very frequent (if needed)
- **120 seconds**: Balanced (recommended)

**Note:** OpenSky rate limits:
- Unauthenticated: 1 request per 10 seconds
- Authenticated: ~10 requests per second

## Radius Selection

Choose radius based on your location and needs:

**Urban Areas (Airports nearby):**
- **25-50 km**: Default, good for most areas
- **10-25 km**: Very local, fewer aircraft
- **50-100 km**: Wider area, more aircraft

**Rural Areas:**
- **50-100 km**: Default, may need larger radius
- **100-200 km**: Very wide area

**Near Major Airports:**
- **10-25 km**: Focus on immediate area
- **25-50 km**: Standard approach/departure paths

## Troubleshooting

### No Aircraft Found

**Problem:** Display shows "NO AIRCRAFT NEARBY"

**Solutions:**
1. **Check radius**: Increase `radius_km` (try 100 km)
2. **Check location**: Verify latitude/longitude are correct
3. **Check time**: Fewer aircraft at night or in remote areas
4. **Check logs**: Look for API errors in container logs
5. **Test API**: Visit [OpenSky Network](https://opensky-network.org/) to verify coverage

### Rate Limit Errors

**Problem:** "API rate limit exceeded" error

**Solutions:**
1. **Increase refresh interval**: Set `refresh_seconds` to 300+ (5+ minutes)
2. **Get API credentials**: Register for OpenSky account and add client_id/secret
3. **Check cache**: Plugin uses cached data when possible
4. **Wait**: Unauthenticated limit is 1 req/10 sec

### Missing Call Signs

**Problem:** Some aircraft show ICAO addresses instead of call signs

**Solutions:**
1. **Normal behavior**: Not all aircraft broadcast call signs
2. **ICAO address**: Plugin shows 24-bit hex address as fallback
3. **Filtering**: Aircraft without call signs are still included if they have other data

### Altitude/Speed Missing

**Problem:** Some aircraft don't show altitude or speed

**Solutions:**
1. **Data availability**: Not all aircraft broadcast all data
2. **Filtering**: Plugin skips aircraft without required data (altitude, speed)
3. **Coverage**: OpenSky coverage varies by region

### Authentication Not Working

**Problem:** OAuth token errors or authentication failures

**Solutions:**
1. **Verify credentials**: Check client_id and client_secret are correct
2. **Check account**: Ensure OpenSky account is active
3. **Regenerate**: Create new API client in OpenSky account
4. **Fallback**: Plugin works without authentication (lower rate limits)

## Data Source

**OpenSky Network API:**
- **API**: https://opensky-network.org/api
- **Coverage**: Global (varies by region)
- **Update Frequency**: Real-time (updated every few seconds)
- **Rate Limits**: See above
- **Authentication**: OAuth2 client credentials (optional)
- **Documentation**: https://openskynetwork.github.io/opensky-api/

**Data Fields:**
- **Call Sign**: Flight identifier (may be null, uses ICAO address as fallback)
- **Altitude**: Geometric (GPS) or barometric altitude in meters (converted to feet)
- **Ground Speed**: Velocity in m/s (converted to knots)
- **Squawk**: Transponder code (4-digit, may be null)

## Advanced Usage

### Combining with Other Features

```
{center}MORNING BRIEF
AIRCRAFT: {{nearby_aircraft.aircraft_count}}
{{nearby_aircraft.aircraft.0.call_sign}} {{nearby_aircraft.aircraft.0.altitude}}ft

WEATHER: {{weather.temperature}}° {{weather.condition}}
STOCKS: {{stocks.stocks.0.formatted}}
```

### Custom Formatting

```
{center}AIR TRAFFIC
{{nearby_aircraft.aircraft.0.call_sign|pad:8}} {{nearby_aircraft.aircraft.0.altitude|pad:6}}ft
{{nearby_aircraft.aircraft.1.call_sign|pad:8}} {{nearby_aircraft.aircraft.1.altitude|pad:6}}ft
```

## Related Features

- **Flights**: Alternative flight tracking using aviationstack API
- **Weather**: Combine with weather for complete aviation dashboard
- **DateTime**: Add current time to aircraft display

## Resources

- [OpenSky Network](https://opensky-network.org/)
- [OpenSky API Documentation](https://openskynetwork.github.io/opensky-api/)
- [OpenSky FAQ](https://opensky-network.org/about/faq)
- [FlightAware](https://flightaware.com/) - Alternative flight tracking
- [ADS-B Exchange](https://www.adsbexchange.com/) - Alternative data source

---

**Next Steps:**
1. Enable Nearby Aircraft in Settings
2. Enter your coordinates (latitude, longitude)
3. (Optional) Get OpenSky API credentials for higher rate limits
4. Create a page with aircraft display template
5. Set as active page or combine with other data
