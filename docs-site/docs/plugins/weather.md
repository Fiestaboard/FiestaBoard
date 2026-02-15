---
sidebar_position: 3
---

# Weather Plugin

Display current weather conditions on your board with temperature, conditions, UV index, and more.

## Overview

The Weather plugin provides real-time weather data for your location, including:

- Current temperature (°F or °C)
- Weather conditions (Sunny, Cloudy, Rain, etc.)
- High and low temperatures
- UV index
- Humidity
- Wind speed

## Setup

### 1. Get an API Key

**WeatherAPI.com (Recommended):**
1. Sign up at [weatherapi.com](https://www.weatherapi.com/)
2. Free tier: 1 million calls/month
3. No credit card required

**OpenWeatherMap (Alternative):**
1. Sign up at [openweathermap.org](https://openweathermap.org/api)
2. Free tier: 1,000 calls/day

### 2. Configure in `.env`

```bash
WEATHER_API_KEY=your_api_key_here
WEATHER_PROVIDER=weatherapi          # or "openweathermap"
WEATHER_LOCATION=San Francisco, CA   # City, State or City, Country
```

### 3. Enable the Plugin

Go to **Integrations** in the Web UI and toggle the Weather plugin on.

## Available Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{weather.temperature}` | Current temperature | `72°F` |
| `{weather.conditions}` | Current conditions | `Sunny` |
| `{weather.high}` | Today's high | `78°F` |
| `{weather.low}` | Today's low | `58°F` |
| `{weather.uv}` | UV index | `6` |
| `{weather.humidity}` | Humidity percentage | `65%` |
| `{weather.wind}` | Wind speed | `12 mph` |

## Color Rules

The Weather plugin supports automatic color coding based on temperature:

| Temperature Range | Color | Code |
|-------------------|-------|------|
| ≥ 90°F (32°C) | 🟥 Red | `{63}` |
| 80–89°F (27–31°C) | 🟧 Orange | `{64}` |
| 70–79°F (21–26°C) | 🟨 Yellow | `{65}` |
| 60–69°F (16–20°C) | 🟩 Green | `{66}` |
| 45–59°F (7–15°C) | 🟦 Blue | `{67}` |
| < 45°F (< 7°C) | 🟪 Violet | `{68}` |

## Weather Symbols

The board uses special characters for weather conditions:

| Symbol | Condition |
|--------|-----------|
| `*` | ☀️ Sunny |
| `%` | ⛅ Partly Cloudy |
| `O` | ☁️ Cloudy |
| `/` | 🌧️ Rain |
| `!` | ⛈️ Thunderstorm |
| `~` | 🌫️ Fog |

## Example Page Layout

```
┌──────────────────────┐
│  SAN FRANCISCO  72*F │
│  SUNNY     H78  L58  │
│  UV 6   HUMIDITY 65% │
│                      │
│                      │
│                      │
└──────────────────────┘
```

## Next Steps

- [Plugins Overview](/docs/plugins/overview) — See all available plugins
- [Color Guide](/docs/reference/color-guide) — Learn about color formatting
- [Character Codes](/docs/reference/character-codes) — Board character reference
