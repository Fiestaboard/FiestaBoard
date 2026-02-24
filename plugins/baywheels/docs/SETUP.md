# Bay Wheels Setup Guide

Bay Wheels integration allows you to track bike availability at multiple stations in the San Francisco Bay Area. The visual station finder makes it easy to find and monitor stations near your locations.

## Overview

**What it does:**
- Displays real-time bike availability (electric and classic bikes)
- Tracks multiple stations simultaneously (up to 4)
- Shows dock availability for bike returns
- Provides visual station finder with map-based selection
- No API key required (uses public GBFS feed)

**Use Cases:**
- Check bike availability before leaving home/work
- Monitor stations near multiple locations (home, office, gym, etc.)
- Track both electric and classic bike availability
- Ensure dock availability for bike returns

## Prerequisites

- ✅ No API key required
- ✅ Bay Wheels stations in your area
- ✅ Web UI access for station finder

## Quick Setup

### 1. Enable Bay Wheels

Via Web UI (Recommended):
1. Go to the **Integrations** page
2. Find **Bay Wheels** section
3. Toggle the **Bay Wheels** plugin on
4. Click **Save Changes**

Via Environment Variables:
```bash
# Add to .env
BAYWHEELS_ENABLED=true
BAYWHEELS_REFRESH_SECONDS=60  # Optional: refresh interval (default: 60)
```

### 2. Add Stations Using Station Finder

The web UI provides a visual station finder:

1. Go to the **Bay Wheels** plugin on the **Integrations** page
2. Click **Find Stations** button
3. Use one of three methods to find stations:

**Method A: Search by Address**
```
Enter address: "123 Market St, San Francisco"
→ Shows nearby stations within 2km
```

**Method B: Use Current Location**
```
Click "Use My Location"
→ Browser requests location permission
→ Shows stations near you
```

**Method C: Enter Coordinates**
```
Latitude: 40.7128
Longitude: -74.0060
→ Shows nearby stations
```

4. **Select stations** from the results (up to 4)
   - Each station shows:
     - Station name and address
     - Distance from search location
     - Current bike availability (electric/classic)
     - Dock availability
     - Capacity

5. Click **Add Station** for each one you want to monitor

6. **Save** your configuration

### 3. Create a Page to Display Bay Wheels Data

1. Go to **Pages** and click **New**
2. Choose **Template** page type
3. Add your template using Bay Wheels variables:

**Example Template:**
```
{center}BAY WHEELS
{baywheels.stations.0.station_name}
E-Bikes: {baywheels.stations.0.electric_bikes}
Classic: {baywheels.stations.0.classic_bikes}

{baywheels.stations.1.station_name}
E-Bikes: {baywheels.stations.1.electric_bikes}
Classic: {baywheels.stations.1.classic_bikes}
```

4. **Save** and **Set as Active**

## Template Variables

### Station-Specific Variables

Access individual stations using index (0-3):

```
{baywheels.stations.0.station_name}       # Station name (e.g., "19th St BART")
{baywheels.stations.0.electric_bikes}    # Number of electric bikes available
{baywheels.stations.0.classic_bikes}     # Number of classic bikes available
{baywheels.stations.0.num_bikes_available} # Total bikes available
{baywheels.stations.0.is_renting}        # "Yes" or "No"
```

### Aggregate Variables

Total across all configured stations:

```
{baywheels.total_electric}    # Total electric bikes across all stations
{baywheels.total_classic}     # Total classic bikes across all stations
{baywheels.total_bikes}       # Total bikes across all stations
```

### Station Count

```
{baywheels.station_count}     # Number of configured stations
```

## Example Templates

![Bay Wheels Display](./baywheels-display.png)

### Simple Single Station

```
{center}BAY WHEELS
19th & Telegraph
E-Bikes: {baywheels.stations.0.electric_bikes}
Classic: {baywheels.stations.0.classic_bikes}
```

### Multiple Stations Compact

```
{center}BIKE SHARE
HOME: {baywheels.stations.0.electric_bikes}E {baywheels.stations.0.classic_bikes}C
WORK: {baywheels.stations.1.electric_bikes}E {baywheels.stations.1.classic_bikes}C
GYM:  {baywheels.stations.2.electric_bikes}E {baywheels.stations.2.classic_bikes}C
```

### Aggregate Summary

```
{center}BAY WHEELS TOTAL
{baywheels.station_count} Stations Monitored
E-Bikes: {baywheels.total_electric}
Classic: {baywheels.total_classic}
Bikes: {baywheels.total_bikes}
```

### With Station Names

```
{center}BIKE AVAILABILITY
{baywheels.stations.0.station_name}
E:{baywheels.stations.0.electric_bikes} C:{baywheels.stations.0.classic_bikes}

{baywheels.stations.1.station_name}
E:{baywheels.stations.1.electric_bikes} C:{baywheels.stations.1.classic_bikes}
```

## Configuration Reference

### Environment Variables

```bash
# Enable Bay Wheels
BAYWHEELS_ENABLED=true

# Refresh interval (seconds)
BAYWHEELS_REFRESH_SECONDS=60  # Default: 60 (1 minute)
```

### config.json Format

```json
{
  "features": {
    "baywheels": {
      "enabled": true,
      "refresh_seconds": 60,
      "station_ids": [
        "19th-st-bart",
        "market-9th-st",
        "embarcadero-plaza",
        "ferry-building"
      ],
      "station_names": [
        "19TH",
        "MKT",
        "EMB",
        "FERRY"
      ]
    }
  }
}
```

## Tips and Best Practices

### Choosing Stations

1. **Monitor key locations**: Home, work, gym, etc.
2. **Include backup options**: Stations close together for alternatives
3. **Check capacity**: Higher capacity stations = more reliable availability
4. **Consider routes**: Stations along your common routes

### Refresh Interval

- **60 seconds** (default): Good balance for most uses
- **30 seconds**: If you need very fresh data before leaving
- **120 seconds**: To reduce API calls (data still very current)

### Station Names

When configuring manually, use short names that fit on the display:
- ✅ "19TH", "WORK", "GYM", "HOME"
- ❌ "19th Street BART Station" (too long)

### Checking Availability Trends

Bay Wheels data shows current availability. For best results:
- Check 5-10 minutes before leaving
- Have backup stations identified
- Consider time of day patterns (morning/evening commute)

## Troubleshooting

### No Stations Showing in Finder

**Problem:** Station finder returns no results

**Solutions:**
1. **Increase search radius**: Try 3-5km instead of 2km
2. **Check location**: Ensure you're in Bay Area (SF, Oakland, San Jose, Berkeley)
3. **Verify GBFS feed**: Test https://gbfs.baywheels.com/gbfs/en/station_information.json

### Station Shows Zero Bikes

**Problem:** Station always shows 0 bikes/docks

**Solutions:**
1. **Check station status**: Station might be temporarily closed
2. **Verify station ID**: Re-add station using station finder
3. **Check GBFS status feed**: Station might be disabled for maintenance

### Data Not Updating

**Problem:** Bike counts seem stale

**Solutions:**
1. **Check refresh interval**: Verify BAYWHEELS_REFRESH_SECONDS is set
2. **Check logs**: Look for GBFS API errors
3. **Restart service**: Docker containers might need restart
4. **Test GBFS directly**: 
   ```bash
   curl https://gbfs.baywheels.com/gbfs/en/station_status.json
   ```

### Station Names Too Long

**Problem:** Station names overflow on display

**Solutions:**
1. **Use truncate filter**: `{baywheels.stations.0.station_name|truncate:22}`
2. **Configure custom names**: Set short names in config.json
3. **Use abbreviations**: "BART" instead of "BART Station"

## Data Source

Bay Wheels uses the **GBFS (General Bikeshare Feed Specification)** standard:

- **Station Info**: https://gbfs.baywheels.com/gbfs/en/station_information.json
- **Station Status**: https://gbfs.baywheels.com/gbfs/en/station_status.json
- **Update Frequency**: Real-time (updates every 10-30 seconds at source)
- **Coverage**: San Francisco, Oakland, Berkeley, San Jose, Emeryville

## Advanced Usage

### Conditional Display Based on Availability

```python
# In template (when template language supports conditionals)
{% if baywheels.stations.0.electric_bikes > 2 %}
  Plenty of e-bikes available!
{% else %}
  Limited e-bikes, consider classic
{% endif %}
```

### Combining with Other Features

```
{center}MORNING COMMUTE
Muni: {muni.stops.0.formatted}
Bikes: {baywheels.stations.0.electric_bikes}E
Traffic: {traffic.routes.0.duration_minutes}m
```

### Multiple Station Comparisons

```
{center}WHICH STATION?
19th: {baywheels.stations.0.electric_bikes}E {baywheels.stations.0.classic_bikes}C
Mkt:  {baywheels.stations.1.electric_bikes}E {baywheels.stations.1.classic_bikes}C
Emb:  {baywheels.stations.2.electric_bikes}E {baywheels.stations.2.classic_bikes}C
```

## API Reference

### REST API Endpoints

```bash
# List all Bay Wheels stations
GET /baywheels/stations

# Find stations near location
GET /baywheels/stations/nearby?lat=40.7128&lng=-74.0060&radius=2.0

# Search stations by address
GET /baywheels/stations/search?address=123+Market+St&radius=2.0
```

## Related Features

- **Muni Transit**: Track transit arrivals alongside bike availability
- **Traffic**: Compare bike vs. drive times
- **Weather**: Check weather before biking

## Resources

- [Bay Wheels Website](https://www.baywheels.com/)
- [Bay Wheels System Map](https://www.baywheels.com/system-data)
- [GBFS Specification](https://github.com/MobilityData/gbfs)
- [Real-time Station Map](https://www.baywheels.com/map)

---

**Next Steps:**
1. Enable Bay Wheels in Settings
2. Use station finder to add your favorite stations
3. Create a page with bike availability
4. Set as active page or combine with other transit data

