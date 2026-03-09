# Allergy & Health Plugin Setup

## Overview

The Allergy & Health plugin displays pollen counts, air quality data, and health risk indicators for your location using the free Open-Meteo Air Quality API.

**No API key is required.**

## Quick Setup

### 1. Enable the Plugin

Go to **Integrations** in FiestaBoard and enable **Allergy & Health**.

### 2. Configure Your Location

Set the latitude and longitude for the area you want to monitor. The default location is San Francisco, CA.

You can find your coordinates at [latlong.net](https://www.latlong.net/).

### 3. Use in Templates

Use the plugin variables in your board templates:

```
{health.allergy_risk_color} GRASS: {health.grass_pollen} FLU: {health.flu_risk}
```

## Environment Variables

You can also configure the plugin using environment variables:

| Variable | Description |
|---|---|
| `HEALTH_LATITUDE` | Location latitude |
| `HEALTH_LONGITUDE` | Location longitude |

## Troubleshooting

### Plugin shows no data

- Pollen data may not be available for all regions. It is best supported in Europe and North America.
- Check that your latitude and longitude values are correct.
- The Open-Meteo API may be temporarily unavailable — data will refresh on the next interval.

### Pollen values are all zero

- Pollen levels vary by season. During winter months, pollen counts are typically zero.
- Some regions may have limited pollen monitoring coverage.

## Data Source

All data is provided by the [Open-Meteo Air Quality API](https://open-meteo.com/en/docs/air-quality-api).

## Support

- [FiestaBoard Repository](https://github.com/FiestaBoard/FiestaBoard)
- [Issue Tracker](https://github.com/FiestaBoard/FiestaBoard/issues)
