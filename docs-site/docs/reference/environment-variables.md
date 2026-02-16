---
sidebar_position: 4
description: "Complete reference of FiestaBoard .env configuration variables for API keys, display settings, and plugin options."
keywords: [FiestaBoard environment variables, .env config, configuration reference, settings, env file]
---

# Environment Variables

This is a **reference page** for all available `.env` configuration variables. Most self-hosting users don't need to edit `.env` directly — the [install wizard](/docs/setup/quick-start) creates it during setup, and plugins are configured through the web UI's Integrations page.

This reference is useful for:
- **Development** — setting up a local dev environment
- **Advanced configuration** — tuning settings the web UI doesn't expose
- **Troubleshooting** — understanding what each variable controls

## Required Variables

These must be set for FiestaBoard to connect to your board:

| Variable | Description | Example |
|----------|-------------|---------|
| `BOARD_API_MODE` | API connection mode | `local` or `cloud` |
| `BOARD_LOCAL_API_KEY` | Board Local API key (when `BOARD_API_MODE=local`) | `your_api_key` |
| `BOARD_HOST` | Board IP or hostname (when `BOARD_API_MODE=local`) | `192.168.0.11` |
| `BOARD_READ_WRITE_KEY` | Board Read/Write API key (when `BOARD_API_MODE=cloud`) | `your_api_key` |
| `TIMEZONE` | Your local timezone | `America/Los_Angeles` |

## Board Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `BOARD_API_MODE` | API mode (`local` or `cloud`) | `local` |
| `BOARD_LOCAL_API_KEY` | Local API key | — |
| `BOARD_HOST` | Board IP or hostname (local mode) | — |
| `BOARD_READ_WRITE_KEY` | Cloud Read/Write API key | — |
| `BOARD_TRANSITION_STRATEGY` | Transition animation style (local mode only) | — |
| `BOARD_TRANSITION_INTERVAL_MS` | Delay between animation steps | `0` |
| `BOARD_TRANSITION_STEP_SIZE` | Columns/rows per animation step | `0` |

:::info Board API Key Variables
Use `BOARD_LOCAL_API_KEY` + `BOARD_HOST` for local mode (default). Use `BOARD_READ_WRITE_KEY` for cloud mode. See the [Cloud API Setup](/docs/setup/cloud-api) guide for details.
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
# Board Configuration (required)
BOARD_API_MODE=local
BOARD_LOCAL_API_KEY=your_local_api_key_here
BOARD_HOST=192.168.0.11

# Timezone
TIMEZONE=America/Los_Angeles

# Optional: Weather
WEATHER_API_KEY=your_weather_key_here
WEATHER_PROVIDER=weatherapi
WEATHER_LOCATION=San Francisco, CA

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
