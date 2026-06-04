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
- Pollen levels (grass, tree, weed) via Open-Meteo
- Configurable location via coordinates

## Setup

### 1. Get API Keys

**PurpleAir (for AQI):**
1. Sign up at [PurpleAir](https://www.purpleair.com/)
2. Request an API key from the PurpleAir data page

**OpenWeatherMap (for visibility/fog):**
1. Sign up at [OpenWeatherMap](https://openweathermap.org/api)
2. Free tier: 1,000 calls/day

Pollen data is fetched from [Open-Meteo](https://open-meteo.com/) automatically and requires no API key.

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
| `{air_fog.fog_color}` | Color indicator for fog status | `{65}` |
| `{air_fog.is_foggy}` | Whether fog is present | `true` |
| `{air_fog.visibility}` | Visibility distance | `8.5 MILES` |
| `{air_fog.grass_pollen}` | Grass pollen count | `12` |
| `{air_fog.grass_pollen_level}` | Grass pollen level text | `LOW` |
| `{air_fog.grass_pollen_color}` | Color indicator for grass pollen | `{66}` |
| `{air_fog.tree_pollen}` | Tree pollen count | `45` |
| `{air_fog.tree_pollen_level}` | Tree pollen level text | `MODERATE` |
| `{air_fog.tree_pollen_color}` | Color indicator for tree pollen | `{65}` |
| `{air_fog.weed_pollen}` | Weed pollen count | `8` |
| `{air_fog.weed_pollen_level}` | Weed pollen level text | `LOW` |
| `{air_fog.weed_pollen_color}` | Color indicator for weed pollen | `{66}` |
| `{air_fog.formatted}` | Formatted display string | `AQI 42 GOOD` |

## Next Steps

- [Weather Plugin](/docs/plugins/weather) -- Pair with weather data
- [Plugins Overview](/docs/plugins/overview) -- See all available plugins
