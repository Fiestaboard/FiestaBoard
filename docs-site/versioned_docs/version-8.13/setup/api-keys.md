---
sidebar_position: 4
description: "API keys for FiestaBoard - only your board key is required to start. Plugin API keys are added as you enable them."
keywords: [FiestaBoard API keys, weather API, Google Routes API, plugin configuration, API setup]
---

# API Keys

FiestaBoard only requires your board's API key to start, and the install wizard collects it for you during setup. Plugin API keys are entered through the **web UI's Integrations page** as you enable plugins.

## Required: Board API Key

The install wizard asks for this during setup. If you need to find or change your key later:

### Local API Key (Recommended)

Faster updates, supports transition animations, requires same-network access.

1. Request a Local API enablement token at [the Vestaboard Local API token page](https://www.vestaboard.com/local-api)
2. After approval, Vestaboard will email you an enablement token
3. Use the enablement token to enable the Local API on your board — you can do this through FiestaBoard's **Settings** page (select the **Enablement Token** option) or via a `curl` command (see the [Vestaboard Local API docs](https://docs.vestaboard.com/docs/local-api/authentication))
4. Save the API key returned in the response

> For full details on Local API authentication, see the [official Vestaboard documentation](https://docs.vestaboard.com/docs/local-api/authentication).

### Cloud Read/Write API Key

Works from anywhere with internet. No transition animation support.

1. Go to [your Vestaboard account](https://web.vestaboard.com)
2. Log in with your board account
3. Navigate to the API section
4. Enable the **Read/Write API**
5. Copy your API key

> If you're setting up manually (without the wizard), see `env.example` for the environment variable names (`BOARD_LOCAL_API_KEY`, `BOARD_HOST`, `BOARD_READ_WRITE_KEY`, etc.).

<ThemedScreenshot src="/img/guides/settings-board-config.png" alt="Settings page with board API key and IP address inputs" />

## Plugin API Keys

These are optional. Enter them in the **Integrations page** of the web UI as you enable plugins. Many plugins work without any API key at all.

### Plugins That Need API Keys

| Plugin | Where to Get the Key | Free Tier |
|--------|---------------------|-----------|
| Weather | [WeatherAPI](https://www.weatherapi.com/) or [OpenWeatherMap](https://openweathermap.org/api) | 1M calls/month (WeatherAPI) |
| Traffic | [Google Cloud Console](https://console.cloud.google.com/) (Routes API) | $200/month credit |
| Home Assistant | Your HA instance → Profile → Long-Lived Access Tokens | Self-hosted |
| Last.fm | [last.fm/api/account/create](https://www.last.fm/api/account/create) | Unlimited |
| Muni Transit | [511.org Open Data token](https://511.org/open-data/token) | Free |
| WSDOT Ferries | [wsdot.wa.gov/traffic/api](https://wsdot.wa.gov/traffic/api/) | Free |
| Air Quality | PurpleAir or OpenWeatherMap | Varies |

### Plugins With Optional API Keys

| Plugin | API Key | What It Unlocks |
|--------|---------|----------------|
| Stocks | [Finnhub](https://finnhub.io/) | Better symbol search/autocomplete |
| Sports Scores | [TheSportsDB](https://www.thesportsdb.com/) | Extended data |
| Nearby Aircraft | [OpenSky Network](https://opensky-network.org/) | Higher rate limits |

### Plugins That Need No API Key

These work out of the box:

- Bay Wheels
- Date & Time
- Disney Parks
- Guest WiFi
- Star Trek Quotes
- Sun Art
- Surf
- Visual Clock

<ThemedScreenshot src="/img/guides/integrations-plugin-config.png" alt="Plugin settings modal for Weather plugin configuration" />

## Next Steps

- [Plugins Overview](/docs/plugins/overview) - Configure and enable plugins
- [Quick Start](/docs/setup/quick-start) - Get FiestaBoard running
