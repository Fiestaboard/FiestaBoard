# SF Muni Transit Setup Guide

SF Muni integration provides real-time arrival predictions for San Francisco Municipal Railway (Muni) bus, light rail, and cable car lines. The visual stop finder makes it easy to find and monitor stops near your locations.

## Overview

**What it does:**
- Real-time arrival predictions for Muni lines
- Track multiple stops simultaneously (up to 4)
- Line filtering (e.g., show only N-Judah)
- Visual stop finder with address/location search
- Regional transit caching for fast responses

**Use Cases:**
- Check when the next bus/train arrives before leaving
- Monitor stops near home, work, and other locations
- Plan multimodal commutes
- Avoid missing your line during peak hours

## Prerequisites

- ✅ Free 511.org API key (required)
- ✅ Muni stops in San Francisco area
- ✅ Web UI access for stop finder

## Quick Setup

### 1. Get 511.org API Key

1. Go to [511.org/open-data](https://511.org/open-data/transit)
2. Click **Request Access** or **Sign Up**
3. Fill out the registration form
4. Verify your email
5. Go to **API Keys** section
6. Copy your API key (format: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`)

**Rate Limits:**
- Free tier: 60 requests per hour
- FiestaBoard's regional caching reduces usage to ~40 requests/hour

### 2. Enable Muni Transit

Via Web UI (Recommended):
1. Go to the **Integrations** page
2. Find **Muni Transit** section
3. Toggle the **Muni Transit** plugin on
4. Enter your 511.org API key
5. Click **Save Changes**

Via Environment Variables:
```bash
# Add to .env
MUNI_ENABLED=true
MUNI_API_KEY=your_511_org_api_key_here
MUNI_REFRESH_SECONDS=60  # Optional: refresh interval (default: 60)
```

### 3. Add Stops Using Stop Finder

The web UI provides a visual stop finder:

1. Go to the **Muni Transit** plugin on the **Integrations** page
2. Click **Find Stops** button
3. Use one of three methods to find stops:

**Method A: Search by Address**
```
Enter address: "Market St & 9th St, San Francisco"
→ Shows nearby stops within 0.5km
```

**Method B: Use Current Location**
```
Click "Use My Location"
→ Browser requests location permission
→ Shows stops near you
```

**Method C: Enter Coordinates**
```
Latitude: 40.7128
Longitude: -74.0060
→ Shows nearby stops
```

4. **Select stops** from the results (up to 4)
   - Each stop shows:
     - Stop name
     - Stop code (used by 511 API)
     - Lines serving this stop
     - Distance from search location

5. Click **Add Stop** for each one you want to monitor

6. **Optional:** Configure line filters
   - To show only specific lines (e.g., "N-Judah")
   - Leave blank to show all lines at that stop

7. **Save** your configuration

### 4. Create a Page to Display Muni Data

1. Go to **Pages** and click **New**
2. Choose **Template** page type
3. Add your template using Muni variables:

**Example Template:**
```
{center}MUNI ARRIVALS
{{muni.stops.0.formatted}}
{{muni.stops.1.formatted}}
```

4. **Save** and **Set as Active**

## Template Variables

### Stop-Specific Variables

Access individual stops using index (0-3):

```
{{muni.stops.0.formatted}}          # Pre-formatted arrival info
                                    # Example: "N 3m, 12m, 25m"

{{muni.stops.0.stop_name}}          # Stop name (e.g., "Market & 9th")
{{muni.stops.0.line}}               # Primary line at this stop
{{muni.stops.0.arrivals}}           # List of arrival times
{{muni.stops.0.next_arrival}}       # Minutes until next arrival
```

### Multiple Stops

```
{{muni.stops.1.formatted}}          # Second stop
{{muni.stops.2.formatted}}          # Third stop
{{muni.stops.3.formatted}}          # Fourth stop
```

### Stop Count

```
{{muni.stop_count}}                 # Number of configured stops
```

## Example Templates

![Muni Transit Display](./muni-display.png)

### Simple Single Stop

```
{center}MUNI ARRIVALS
Market & 9th St
{{muni.stops.0.formatted}}
```

### Multiple Stops

```
{center}MUNI TIMES
HOME STOP
{{muni.stops.0.formatted}}

WORK STOP
{{muni.stops.1.formatted}}
```

### Compact Multiple Stops

```
{center}MUNI
Home: {{muni.stops.0.formatted}}
Work: {{muni.stops.1.formatted}}
Gym:  {{muni.stops.2.formatted}}
```

### With Stop Names

```
{center}TRANSIT
{{muni.stops.0.stop_name}}
{{muni.stops.0.formatted}}

{{muni.stops.1.stop_name}}
{{muni.stops.1.formatted}}
```

### Line Filtered (N-Judah Only)

```
{center}N-JUDAH INBOUND
{{muni.stops.0.formatted}}
Next: {{muni.stops.0.next_arrival}}m
```

## Configuration Reference

### Environment Variables

```bash
# Required
MUNI_ENABLED=true
MUNI_API_KEY=your_511_org_api_key_here

# Optional
MUNI_REFRESH_SECONDS=60          # Default: 60 (1 minute)
```

### config.json Format

```json
{
  "features": {
    "muni": {
      "enabled": true,
      "api_key": "your_511_org_api_key",
      "refresh_seconds": 60,
      "stop_codes": [
        "15419",
        "17217",
        "13294"
      ],
      "stop_names": [
        "Market & 9th",
        "Valencia & 16th",
        "Mission & 24th"
      ],
      "transit_cache_enabled": true,
      "transit_cache_refresh_seconds": 90
    }
  }
}
```

## Regional Transit Cache

FiestaBoard uses an intelligent caching system to stay within 511.org API rate limits:

### How It Works

1. **Single Regional Request**: Fetches ALL Bay Area transit data in one API call
2. **90-Second Refresh**: Cache refreshes every 90 seconds (configurable)
3. **Instant Responses**: All Muni data served from cache with zero latency
4. **Graceful Degradation**: Serves stale cache if API unavailable
5. **Rate Limit Friendly**: Reduces API calls from 100+/hour to ~40/hour

### Benefits

- ✅ **Stays within free tier**: 60 requests/hour limit
- ✅ **Faster responses**: No API latency on each request
- ✅ **More reliable**: Works even if 511 API is slow/down
- ✅ **Fresh data**: 90-second cache means data is always current

### Configuration

```bash
# Enable caching (recommended, enabled by default)
TRANSIT_CACHE_ENABLED=true

# Cache refresh interval (seconds)
TRANSIT_CACHE_REFRESH_SECONDS=90  # Default: 90
```

### Monitoring Cache Health

Check cache status via API:
```bash
curl http://localhost:4420/api/transit/cache/status
```

Returns:
```json
{
  "last_refresh": 1234567890,
  "cache_age_seconds": 45,
  "is_stale": false,
  "agencies_cached": 10,
  "refresh_count": 156,
  "error_count": 0
}
```

## Tips and Best Practices

### Choosing Stops

1. **Identify your key locations**: Home, work, gym, favorite spots
2. **Find nearest stops**: Use stop finder with your addresses
3. **Check line coverage**: Ensure stops serve your needed lines
4. **Consider direction**: Some stops have separate codes for inbound/outbound

### Line Filtering

**When to filter:**
- ✅ You only take one line from a stop (e.g., N-Judah)
- ✅ Stop serves many lines and you want to reduce clutter
- ✅ You want separate displays for different lines

**When NOT to filter:**
- ❌ Stop only serves one or two lines (filtering unnecessary)
- ❌ You take whichever line comes first
- ❌ You want to see all options

### Refresh Interval

- **60 seconds** (default): Good balance for most uses
- **30 seconds**: If you need very fresh predictions
- **90 seconds**: Matches cache refresh, efficient

### Stop Names

Use short, recognizable names:
- ✅ "Home", "Work", "Gym", "Market&9th"
- ❌ "San Francisco Municipal Railway Stop at Market Street and 9th Street"

## Troubleshooting

### No Stops Showing in Finder

**Problem:** Stop finder returns no results

**Solutions:**
1. **Increase search radius**: Try 1km instead of 0.5km
2. **Check location**: Ensure you're in San Francisco area
3. **Verify API key**: Test with 511.org API directly
4. **Check stop database**: Some stops may not have coordinates

### API Rate Limit Errors

**Problem:** "Rate limit exceeded" errors in logs

**Solutions:**
1. **Enable transit cache**: Set `TRANSIT_CACHE_ENABLED=true`
2. **Increase cache refresh**: Set `TRANSIT_CACHE_REFRESH_SECONDS=120`
3. **Reduce refresh rate**: Increase `MUNI_REFRESH_SECONDS` to 90 or 120
4. **Check cache status**: Ensure cache is working properly

### No Arrival Predictions

**Problem:** Stop shows but no arrival times

**Solutions:**
1. **Check time of day**: Service may not be running (late night/early morning)
2. **Verify stop code**: Re-add stop using stop finder
3. **Check line filter**: Remove filters to see all lines
4. **Review logs**: Look for 511 API errors
5. **Test 511 API directly**: 
   ```bash
   curl "https://api.511.org/transit/StopMonitoring?api_key=YOUR_KEY&agency=SF&stopCode=15419"
   ```

### Stale Data / Not Updating

**Problem:** Arrival predictions seem old

**Solutions:**
1. **Check cache age**: Use cache status endpoint
2. **Verify refresh interval**: Check MUNI_REFRESH_SECONDS
3. **Check logs**: Look for cache refresh errors
4. **Restart service**: Containers might need restart
5. **Test 511 API**: Ensure API is responding

### Line Filter Not Working

**Problem:** Seeing all lines even with filter set

**Solutions:**
1. **Check line name format**: Use exact name (e.g., "N" not "N-Judah")
2. **Case sensitivity**: Try uppercase (e.g., "N" not "n")
3. **Check configuration**: Verify filter is saved in config.json
4. **Clear cache**: Stop/start service to reload config

## Data Source

Muni uses the **511.org Transit API**:

- **API**: https://511.org/open-data/transit
- **Protocol**: SIRI (Service Interface for Real-time Information)
- **Agency Code**: SF (San Francisco Municipal Railway)
- **Update Frequency**: Real-time (updates every 30-60 seconds at source)
- **Coverage**: All Muni lines (bus, light rail, cable car, streetcar)

## Advanced Usage

### Combining with Other Features

```
{center}MORNING COMMUTE
Muni: {{muni.stops.0.formatted}}
Bikes: {{baywheels.stations.0.electric_bikes}}E
Traffic: {{traffic.routes.0.duration_minutes}}m
Weather: {{weather.temperature}}° {{weather.condition}}
```

### Multiple Stops with Labels

```
{center}TRANSIT OPTIONS
N @ Church: {{muni.stops.0.formatted}}
L @ Church: {{muni.stops.1.formatted}}
22 @ Church: {{muni.stops.2.formatted}}
```

### Inbound vs Outbound

```
{center}N-JUDAH CHURCH ST
Inbound: {{muni.stops.0.formatted}}
Outbound: {{muni.stops.1.formatted}}
```

### Conditional Based on Time

```python
# Display different stops based on time of day
# Morning: Show stops near home
# Evening: Show stops near work
```

## API Reference

### REST API Endpoints

```bash
# List all Muni stops (cached, 24hr TTL)
GET /muni/stops

# Find stops near location
GET /muni/stops/nearby?lat=40.7128&lng=-74.0060&radius=0.5

# Search stops by address
GET /muni/stops/search?address=Market+St+and+9th+St&radius=0.5

# Get transit cache status
GET /transit/cache/status
```

## Line Codes Reference

Common Muni line codes for filtering:

**Light Rail (Metro)**
- N, J, K, L, M, T

**Bus (Major Lines)**
- 1, 5, 7, 8, 9, 14, 22, 24, 27, 30, 38, 43, 44, 48, 49

**Rapid Bus**
- 8AX, 8BX, 14R, 28R, 38R

**Cable Car**
- Powell-Mason, Powell-Hyde, California

**Historic Streetcar**
- F-Market

## Related Features

- **Bay Wheels**: Combine transit with bike share for multimodal trips
- **Traffic**: Compare Muni vs. driving times
- **Weather**: Check weather before commuting

## Resources

- [511.org Open Data](https://511.org/open-data/transit)
- [SFMTA Routes & Schedules](https://www.sfmta.com/routes)
- [Muni System Map](https://www.sfmta.com/maps/muni-system-map)
- [511 Real-time Map](https://511.org/transit)

---

**Next Steps:**
1. Get your free 511.org API key
2. Enable Muni Transit in Settings
3. Use stop finder to add your frequent stops
4. Create a page with arrival predictions
5. Set as active page or combine with other transit data

