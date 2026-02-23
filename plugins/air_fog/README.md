# Air Quality & Fog Plugin

![Air Quality & Fog Display](./docs/air-fog-display.png)

Display air quality index (AQI) and fog/visibility conditions.

**→ [Setup Guide](./docs/SETUP.md)** - API key registration and configuration

## Overview

The Air Quality & Fog plugin combines data from PurpleAir (air quality) and OpenWeatherMap (visibility) to give you a complete picture of outdoor conditions.

## Features

- Real-time AQI from nearby PurpleAir sensors
- Visibility and fog detection
- Color-coded status indicators
- Configurable location

## Template Variables

```
{{air_fog.aqi}}          # Air Quality Index (0-500)
{{air_fog.air_status}}   # Status text (GOOD, MODERATE, UNHEALTHY, etc.)
{{air_fog.air_color}}    # Color tile for AQI
{{air_fog.fog_status}}   # Fog status (CLEAR, HAZE, FOG)
{{air_fog.fog_color}}    # Color tile for fog
{{air_fog.is_foggy}}     # Yes/No
{{air_fog.visibility}}   # Visibility distance (e.g., "5.2mi")
{{air_fog.formatted}}    # Pre-formatted message
```

## Example Templates

### Simple Status

```
{center}AIR & FOG
AQI: {{air_fog.aqi}} {{air_fog.air_status}}
VIS: {{air_fog.visibility}}
FOG: {{air_fog.fog_status}}
```

### With Colors

```
{center}CONDITIONS
{{air_fog.air_color}} AQI: {{air_fog.aqi}}
{{air_fog.fog_color}} FOG: {{air_fog.fog_status}}
```

## Quick Setup

For detailed setup instructions including API key registration, see the **[Setup Guide](./docs/SETUP.md)**.

## Configuration

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| enabled | boolean | false | Enable/disable the plugin |
| purpleair_api_key | string | - | PurpleAir API key |
| openweathermap_api_key | string | - | OpenWeatherMap API key |
| purpleair_sensor_id | string | - | Optional specific sensor ID |
| latitude | number | 40.7128 | Location latitude |
| longitude | number | -74.0060 | Location longitude |
| refresh_seconds | integer | 300 | Update interval |

## AQI Levels

| AQI | Status | Color |
|-----|--------|-------|
| 0-50 | Good | Green |
| 51-100 | Moderate | Yellow |
| 101-150 | Unhealthy (Sensitive) | Orange |
| 151-200 | Unhealthy | Red |
| 201-300 | Very Unhealthy | Purple |
| 301+ | Hazardous | Maroon |

## Author

FiestaBoard Team

