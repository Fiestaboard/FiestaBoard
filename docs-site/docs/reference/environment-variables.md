---
sidebar_position: 4
---

# Environment Variables

All FiestaBoard configuration is done through the `.env` file. This page documents every available environment variable.

## Required Variables

These must be set for FiestaBoard to function:

| Variable | Description | Example |
|----------|-------------|---------|
| `BOARD_READ_WRITE_KEY` | Board API key for sending content (local mode) | `your_api_key` |
| `WEATHER_API_KEY` | Weather data API key | `your_weather_key` |
| `WEATHER_PROVIDER` | Weather API provider | `weatherapi` or `openweathermap` |
| `WEATHER_LOCATION` | Location for weather data | `San Francisco, CA` |
| `TIMEZONE` | Your local timezone | `America/Los_Angeles` |

## Board Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `BOARD_READ_WRITE_KEY` | Board Read/Write API key (used in local mode) | — |
| `FB_API_MODE` | API mode (`local` or `cloud`) | `local` |
| `FB_READ_WRITE_KEY` | Board API key (used when `FB_API_MODE=cloud`) | — |
| `BOARD_TRANSITION` | Transition animation style | — |
| `BOARD_TRANSITION_SPEED` | Transition speed (ms) | — |

:::info Board API Key Variables
Use `BOARD_READ_WRITE_KEY` for local mode (default). Use `FB_READ_WRITE_KEY` with `FB_API_MODE=cloud` for cloud mode. See the [Cloud API Setup](/docs/setup/cloud-api) guide for details.
:::

## Weather

| Variable | Description | Default |
|----------|-------------|---------|
| `WEATHER_API_KEY` | API key | — |
| `WEATHER_PROVIDER` | Provider (`weatherapi` / `openweathermap`) | `weatherapi` |
| `WEATHER_LOCATION` | Location string | — |

## Location & Timezone

| Variable | Description | Default |
|----------|-------------|---------|
| `TIMEZONE` | TZ database timezone name | `America/Los_Angeles` |
| `LATITUDE` | Latitude for location-based plugins | — |
| `LONGITUDE` | Longitude for location-based plugins | — |

## Plugin API Keys

| Variable | Plugin | Description |
|----------|--------|-------------|
| `GOOGLE_ROUTES_API_KEY` | Traffic | Google Routes API key |
| `HOME_ASSISTANT_URL` | Home Assistant | HA instance URL |
| `HOME_ASSISTANT_TOKEN` | Home Assistant | Long-lived access token |
| `LASTFM_API_KEY` | Last.fm | Last.fm API key |
| `LASTFM_USERNAME` | Last.fm | Last.fm username |
| `MUNI_API_KEY` | Muni Transit | 511.org API key |
| `WSDOT_API_KEY` | WSDOT Ferries | WSDOT API key |
| `PURPLEAIR_API_KEY` | Air Quality | PurpleAir API key |
| `OWM_API_KEY` | Air Quality | OpenWeatherMap API key |
| `FINNHUB_API_KEY` | Stocks | Finnhub API key (optional) |
| `SPORTS_API_KEY` | Sports Scores | TheSportsDB API key (optional) |

## Guest WiFi

| Variable | Description | Default |
|----------|-------------|---------|
| `GUEST_WIFI_SSID` | WiFi network name | — |
| `GUEST_WIFI_PASSWORD` | WiFi password | — |

## Silence Schedule

| Variable | Description | Default |
|----------|-------------|---------|
| `SILENCE_START_TIME` | Quiet hours start (HH:MM) | — |
| `SILENCE_END_TIME` | Quiet hours end (HH:MM) | — |

## System Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `REFRESH_INTERVAL_SECONDS` | Display update interval | `60` |
| `LOG_LEVEL` | Logging level | `INFO` |

## Example `.env` File

```bash
# Board Configuration
BOARD_READ_WRITE_KEY=your_board_key_here

# Weather
WEATHER_API_KEY=your_weather_key_here
WEATHER_PROVIDER=weatherapi
WEATHER_LOCATION=San Francisco, CA

# Timezone
TIMEZONE=America/Los_Angeles

# Optional: Traffic
GOOGLE_ROUTES_API_KEY=your_google_key

# Optional: Home Assistant
HOME_ASSISTANT_URL=http://192.168.1.100:8123
HOME_ASSISTANT_TOKEN=your_ha_token

# Optional: Silence Schedule
SILENCE_START_TIME=22:00
SILENCE_END_TIME=07:00
```

## Next Steps

- [Quick Start](/docs/setup/quick-start) — Getting started with FiestaBoard
- [Docker Setup](/docs/setup/docker-setup) — Docker configuration
- [API Keys](/docs/setup/api-keys) — Getting API keys for plugins
