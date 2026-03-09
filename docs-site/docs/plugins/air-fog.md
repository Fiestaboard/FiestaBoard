---
sidebar_position: 10
description: "Display real-time air quality (AQI) and fog/visibility conditions on your split-flap display with FiestaBoard."
keywords: [FiestaBoard air quality, AQI display, fog visibility, PurpleAir, split-flap air quality, Vestaboard weather]
---

# Air Quality & Fog

Display air quality index (AQI) and fog/visibility conditions on your board using PurpleAir and OpenWeatherMap data.

<BoardScreenshot src="/img/air-fog-display.png" alt="Air Quality and Fog on split-flap board" />

## Overview

The Air Quality & Fog plugin provides:

- Current AQI with color-coded status
- Fog and visibility conditions
- Configurable location via coordinates

## Setup

### 1. Get API Keys

**PurpleAir (for AQI):**
1. Sign up at [purpleair.com](https://www.purpleair.com/)
2. Request an API key from the PurpleAir data page

**OpenWeatherMap (for visibility/fog):**
1. Sign up at [openweathermap.org](https://openweathermap.org/api)
2. Free tier: 1,000 calls/day

### 2. Enable in the Web UI

1. Open **http://localhost:4420**
2. Go to the **Integrations** page
3. Toggle **Air Quality & Fog** on
4. Enter your API keys and set your location coordinates
5. Click **Save Changes**

## Available Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{air_fog.aqi}` | Air Quality Index value | `42` |
| `{air_fog.air_status}` | Air quality status text | `GOOD` |
| `{air_fog.air_color}` | Color indicator for AQI | `{66}` |
| `{air_fog.fog_status}` | Fog/visibility status | `LIGHT FOG` |
| `{air_fog.visibility}` | Visibility distance | `8.5 MILES` |
| `{air_fog.formatted}` | Formatted display string | `AQI 42 GOOD` |

## Next Steps

- [Weather Plugin](/docs/plugins/weather) -- Pair with weather data
- [Plugins Overview](/docs/plugins/overview) -- See all available plugins
