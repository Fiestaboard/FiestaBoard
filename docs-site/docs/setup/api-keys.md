---
sidebar_position: 6
description: "API keys for FiestaBoard — only your board key is required to start. Plugin API keys are added as you enable them."
keywords: [FiestaBoard API keys, weather API, Google Routes API, plugin configuration, API setup]
---

# API Keys

FiestaBoard only requires your board's API key to start. Plugin API keys are optional and added as you enable plugins through the web UI.

## Required: Board API Key

You need one of these to connect FiestaBoard to your display:

### Local API Key (Recommended)

Faster updates, supports transition animations, requires same-network access.

1. Open the board's mobile app
2. Go to **Settings** → **Local API**
3. Copy your API key and note the board's IP address

```bash
# In .env
BOARD_API_MODE=local
BOARD_LOCAL_API_KEY=your_key_here
BOARD_HOST=192.168.0.11
```

### Cloud Read/Write API Key

Works from anywhere with internet. No transition animation support.

1. Go to [web.vestaboard.com](https://web.vestaboard.com)
2. Log in with your board account
3. Navigate to the API section
4. Enable the **Read/Write API**
5. Copy your API key

```bash
# In .env
BOARD_API_MODE=cloud
BOARD_READ_WRITE_KEY=your_key_here
```

## Plugin API Keys

These are optional — add them as you enable plugins. Many plugins work without any API key at all.

### Plugins That Need API Keys

| Plugin | Where to Get the Key | Free Tier |
|--------|---------------------|-----------|
| Weather | [weatherapi.com](https://www.weatherapi.com/) or [openweathermap.org](https://openweathermap.org/api) | 1M calls/month (WeatherAPI) |
| Traffic | [Google Cloud Console](https://console.cloud.google.com/) (Routes API) | $200/month credit |
| Home Assistant | Your HA instance → Profile → Long-Lived Access Tokens | Self-hosted |
| Last.fm | [last.fm/api/account/create](https://www.last.fm/api/account/create) | Unlimited |
| Muni Transit | [511.org/open-data/token](https://511.org/open-data/token) | Free |
| WSDOT Ferries | [wsdot.wa.gov/traffic/api](https://wsdot.wa.gov/traffic/api/) | Free |
| Air Quality | PurpleAir or OpenWeatherMap | Varies |

### Plugins With Optional API Keys

| Plugin | API Key | What It Unlocks |
|--------|---------|----------------|
| Stocks | [finnhub.io](https://finnhub.io/) | Better symbol search/autocomplete |
| Sports Scores | [thesportsdb.com](https://www.thesportsdb.com/) | Extended data |
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

## Next Steps

- [Plugins Overview](/docs/plugins/overview) — Configure and enable plugins
- [Quick Start](/docs/setup/quick-start) — Get FiestaBoard running
