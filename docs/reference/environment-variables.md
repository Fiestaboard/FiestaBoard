---
sidebar_position: 4
description: "Reference for the common FiestaBoard .env configuration variables for API keys, display settings, and plugin options."
keywords: [FiestaBoard environment variables, .env config, configuration reference, settings, env file]
---

# Environment Variables

This is a **reference page** for developers and advanced users. Most users don't need to edit `.env` at all. The [install wizard](/docs/setup/quick-start) creates it during setup, and **all plugin configuration (API keys, settings, etc.) is done through the web UI's Integrations page**.

This reference is useful for:

- **Development** - setting up a local dev environment
- **Advanced configuration** - tuning settings the web UI doesn't expose
- **Troubleshooting** - understanding what each variable controls

:::tip
**Plugin API keys should be entered through the web UI**, not `.env`. The Integrations page provides setup instructions and validates your keys. Environment variables listed below for plugins are supported for backward compatibility but the web UI is the recommended way to configure them.
:::

## Board Connection

These variables control how FiestaBoard connects to your board. The install wizard and web UI set these for you -- manual editing is not required.

| Variable | Description | Default |
|----------|-------------|---------|
| `BOARD_API_MODE` | API connection mode (`local` or `cloud`) | `local` |
| `BOARD_LOCAL_API_KEY` | Board Local API key (when `BOARD_API_MODE=local`) | - |
| `BOARD_HOST` | Board IP or hostname, e.g. `192.168.0.11` (when `BOARD_API_MODE=local`) | - |
| `BOARD_READ_WRITE_KEY` | Board Read/Write API key (when `BOARD_API_MODE=cloud`) | - |
| `BOARD_NOTE_ARRAY_TOKEN` | Vestaboard Cloud API token for Note Array boards (`X-Vestaboard-Token`, not the Read/Write key). Normally set per-board in the UI; see [Note Arrays](/docs/setup/note-arrays). | - |

:::info Board API Key Variables
Use `BOARD_LOCAL_API_KEY` + `BOARD_HOST` for local mode (default). Use `BOARD_READ_WRITE_KEY` for cloud mode. See the [Cloud API Setup](/docs/setup/cloud-api) guide for details.
:::

## Board Transition & Display

These control the board's animation and where output is sent. The `BOARD_TRANSITION_*` variables apply in local mode only; `OUTPUT_TARGET` applies in both modes.

| Variable | Description | Default |
|----------|-------------|---------|
| `BOARD_TRANSITION_STRATEGY` | Transition animation style (local mode only) | - |
| `BOARD_TRANSITION_INTERVAL_MS` | Delay between animation steps | `0` |
| `BOARD_TRANSITION_STEP_SIZE` | Columns/rows per animation step | `0` |
| `OUTPUT_TARGET` | Where rendered content goes: `ui` (preview only), `board` (send to board), or `both` | `board` |

## Weather

| Variable | Description | Default |
|----------|-------------|---------|
| `WEATHER_API_KEY` | API key | - |
| `WEATHER_PROVIDER` | Provider (`weatherapi` / `openweathermap`) | `weatherapi` |
| `WEATHER_LOCATION` | Location string | - |

## Location & Timezone

| Variable | Description | Default |
|----------|-------------|---------|
| `TIMEZONE` | TZ database timezone name | `America/Los_Angeles` |
| `SURF_LATITUDE` | Latitude for surf plugin | - |
| `SURF_LONGITUDE` | Longitude for surf plugin | - |
| `AIR_FOG_LATITUDE` | Latitude for air quality plugin | - |
| `AIR_FOG_LONGITUDE` | Longitude for air quality plugin | - |

## Plugin API Keys

| Variable | Plugin | Description |
|----------|--------|-------------|
| `GOOGLE_ROUTES_API_KEY` | Traffic | Google Routes API key |
| `HOME_ASSISTANT_BASE_URL` | Home Assistant | HA instance URL |
| `HOME_ASSISTANT_ACCESS_TOKEN` | Home Assistant | Long-lived access token |
| `LASTFM_API_KEY` | Last.fm | Last.fm API key |
| `LASTFM_USERNAME` | Last.fm | Last.fm username |
| `MUNI_API_KEY` | Muni Transit | 511.org API key |
| `WSDOT_API_ACCESS_CODE` | WSDOT Ferries | WSDOT API access code |
| `PURPLEAIR_API_KEY` | Air Quality | PurpleAir API key |
| `OPENWEATHERMAP_API_KEY` | Air Quality | OpenWeatherMap API key |
| `FINNHUB_API_KEY` | Stocks | Finnhub API key (optional) |
| `SPORTS_SCORES_API_KEY` | Sports Scores | TheSportsDB API key (optional) |

## Guest WiFi

| Variable | Description | Default |
|----------|-------------|---------|
| `GUEST_WIFI_SSID` | WiFi network name | - |
| `GUEST_WIFI_PASSWORD` | WiFi password | - |

## Silence Schedule

| Variable | Description | Default |
|----------|-------------|---------|
| `SILENCE_SCHEDULE_START_TIME` | Quiet hours start (HH:MM) | - |
| `SILENCE_SCHEDULE_END_TIME` | Quiet hours end (HH:MM) | - |

## Network / mDNS

| Variable | Description | Default |
|----------|-------------|---------|
| `MDNS_HOSTNAME` | Hostname advertised via mDNS/Bonjour (without `.local` suffix). Devices on the same network can reach FiestaBoard at `http://<hostname>.local:4420`. Set to empty to disable mDNS. | `fiestaboard` |

## System Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `REFRESH_INTERVAL_SECONDS` | Display update interval (seconds) | `300` |
| `VERSION` | Build version (set automatically during Docker builds -- do not change) | `dev` |

## FiestaUpdater

These variables control the optional [`fiestaupdater`](/docs/deployment/fiestaupdater) sidecar that powers one-click in-app updates. On [FiestaPi](/docs/setup/raspberry-pi) they're configured automatically on first boot.

| Variable | Description | Default |
|----------|-------------|---------|
| `COMPOSE_PROFILES` | Set to `fiestaupdater` to enable the updater sidecar in the compose stack. | - |
| `FIESTAUPDATER_TOKEN` | Shared bearer token (64 hex chars) used to authenticate the FiestaBoard API → sidecar calls. Generate with `head -c 32 /dev/urandom \| od -An -tx1 \| tr -d ' \n'`. | - |
| `FIESTAUPDATER_SERVICE` | Compose service name the sidecar is allowed to update. Validated against `^[a-z0-9_-]+$`. | `fiestaboard` |
| `FIESTAUPDATER_COMPOSE_FILE` | Path inside the sidecar container to the mounted compose file. | `/compose/docker-compose.yml` |
| `FIESTAUPDATER_PORT` | Port the sidecar listens on (Docker internal network only — never published to the host). | `8765` |
| `COMPOSE_PROJECT_NAME` | Compose project name the sidecar should target. Must match the project the main stack runs under. | `fiestaboard` |

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
HOME_ASSISTANT_BASE_URL=http://192.168.1.100:8123
HOME_ASSISTANT_ACCESS_TOKEN=your_ha_token

# Optional: Silence Schedule
SILENCE_SCHEDULE_START_TIME=22:00
SILENCE_SCHEDULE_END_TIME=07:00
```

## Next Steps

- [Quick Start](/docs/setup/quick-start) - Getting started with FiestaBoard
- [Docker Setup](/docs/setup/docker-setup) - Docker configuration
- [API Keys](/docs/setup/api-keys) - Getting API keys for plugins
