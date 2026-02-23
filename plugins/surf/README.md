# Surf Conditions Plugin

![Surf Conditions Display](./docs/surf-display.png)

Display surf conditions including wave height, swell period, and quality rating.

**→ [Setup Guide](./docs/SETUP.md)** - Location configuration

## Overview

The Surf plugin fetches real-time marine data from Open-Meteo (free, no API key required) to display surf conditions at your favorite spot.

## Features

- Wave height in feet
- Swell period in seconds
- Quality rating (Excellent, Good, Fair, Poor)
- Wind speed and direction
- No API key required!

## Template Variables

```
{{surf.wave_height}}      # Wave height in feet (e.g., "4.5")
{{surf.swell_period}}     # Swell period in seconds (e.g., "12")
{{surf.quality}}          # Quality rating (EXCELLENT, GOOD, FAIR, POOR)
{{surf.quality_color}}    # Color tile for quality
{{surf.wind_speed}}       # Wind speed in mph
{{surf.wind_direction}}   # Wind direction (N, NE, E, etc.)
{{surf.formatted}}        # Pre-formatted message
```

## Example Templates

### Simple Surf Check

```
{center}SURF CHECK
{{surf.wave_height}}ft @ {{surf.swell_period}}s
{{surf.quality}}
```

### With Quality Color

```
{center}EXAMPLE SURF SPOT
{{surf.quality_color}} {{surf.quality}}
WAVES: {{surf.wave_height}}ft
PERIOD: {{surf.swell_period}}s
WIND: {{surf.wind_speed}}mph {{surf.wind_direction}}
```

### Compact

```
{center}{{surf.formatted}}
{{surf.quality}}
```

## Quality Rating

The quality rating is calculated based on swell period and wind speed:

| Rating | Criteria |
|--------|----------|
| EXCELLENT | Period > 12s AND Wind < 12mph |
| GOOD | Period > 10s AND Wind < 15mph |
| FAIR | Period > 8s OR Wind < 20mph |
| POOR | Otherwise |

## Configuration

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| enabled | boolean | false | Enable/disable the plugin |
| latitude | number | 34.0259 | Surf spot latitude |
| longitude | number | -118.7798 | Surf spot longitude |
| refresh_seconds | integer | 300 | Update interval |

## Popular Surf Spots

| Location | Latitude | Longitude |
|----------|----------|-----------|
| Example Location A | 34.0259 | -118.7798 |
| Example Location B | 37.4947 | -122.4956 |
| Example Location C | 36.9541 | -122.0261 |
| Pipeline, HI | 21.6650 | -158.0530 |

## Author

FiestaBoard Team

Hang loose! 🤙

