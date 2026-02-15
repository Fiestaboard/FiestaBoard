---
sidebar_position: 6
---

# Getting API Keys

FiestaBoard integrates with several external services. This page explains how to get the API keys you need.

## Required API Keys

These are needed for basic functionality:

### Board Read/Write API Key

**Required** for sending content to your board.

1. Go to [web.vestaboard.com](https://web.vestaboard.com)
2. Log in with your board account
3. Navigate to the API section
4. Enable the **Read/Write API**
5. Copy your API key

```bash
# In .env
BOARD_READ_WRITE_KEY=your_key_here
```

### Weather API Key

**Required** for the weather plugin.

**Option 1: WeatherAPI.com (Recommended)**
1. Sign up at [weatherapi.com](https://www.weatherapi.com/)
2. Free tier: 1 million calls/month, no credit card required
3. Copy your API key from the dashboard

**Option 2: OpenWeatherMap**
1. Sign up at [openweathermap.org](https://openweathermap.org/api)
2. Free tier: 1,000 calls/day
3. Copy your API key

```bash
# In .env
WEATHER_API_KEY=your_key_here
WEATHER_PROVIDER=weatherapi  # or "openweathermap"
```

## Optional API Keys

These unlock additional plugins:

### Google Routes API (Traffic Plugin)

For commute times and live traffic conditions.

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Enable the **Routes API**
4. Set up billing (required, but $200/month free credit)
5. Create an API key under **Credentials**

```bash
# In .env
GOOGLE_ROUTES_API_KEY=your_key_here
```

See the [Traffic Plugin](/docs/plugins/traffic) guide for detailed setup.

### Home Assistant Token

For displaying smart home device states.

1. Open your Home Assistant instance
2. Go to your profile (click your name in the sidebar)
3. Scroll to **Long-Lived Access Tokens**
4. Click **Create Token**
5. Copy the token

```bash
# In .env
HOME_ASSISTANT_URL=http://your-ha-instance:8123
HOME_ASSISTANT_TOKEN=your_token_here
```

### Last.fm API Key

For displaying currently playing music.

1. Create an account at [last.fm](https://www.last.fm/)
2. Go to [last.fm/api/account/create](https://www.last.fm/api/account/create)
3. Fill in the application details
4. Copy your API key

```bash
# In .env
LASTFM_API_KEY=your_key_here
LASTFM_USERNAME=your_username
```

### 511.org API Key (Muni Transit)

For San Francisco Muni transit predictions.

1. Register at [511.org](https://511.org/open-data/token)
2. Request an API key (free)
3. Copy the key

```bash
# In .env
MUNI_API_KEY=your_key_here
```

### WSDOT API Key (Washington State Ferries)

For ferry schedules and alerts.

1. Go to [wsdot.wa.gov/traffic/api](https://wsdot.wa.gov/traffic/api/)
2. Request a free API key
3. Copy the key

```bash
# In .env
WSDOT_API_KEY=your_key_here
```

### PurpleAir / OpenWeatherMap (Air Quality)

For AQI and fog conditions.

```bash
# In .env - use one of:
PURPLEAIR_API_KEY=your_key_here
# or
OWM_API_KEY=your_openweathermap_key
```

## API Key Summary

| Plugin | API Key Required | Free Tier | Sign Up |
|--------|-----------------|-----------|---------|
| Weather | ✅ Required | 1M calls/month | [weatherapi.com](https://www.weatherapi.com/) |
| Traffic | ✅ Required | $200/month credit | [Google Cloud](https://console.cloud.google.com/) |
| Home Assistant | ✅ Required | Self-hosted | Your HA instance |
| Last.fm | ✅ Required | Unlimited | [last.fm](https://www.last.fm/api/) |
| Muni Transit | ✅ Required | Free | [511.org](https://511.org/open-data/token) |
| WSDOT Ferries | ✅ Required | Free | [wsdot.wa.gov](https://wsdot.wa.gov/traffic/api/) |
| Air Quality | ✅ Required | Varies | PurpleAir or OWM |
| Stocks | Optional | Free | [finnhub.io](https://finnhub.io/) |
| Sports Scores | Optional | Free | [thesportsdb.com](https://www.thesportsdb.com/) |
| Bay Wheels | ❌ None | — | — |
| Date & Time | ❌ None | — | — |
| Disney Parks | ❌ None | — | — |
| Guest WiFi | ❌ None | — | — |
| Star Trek Quotes | ❌ None | — | — |
| Sun Art | ❌ None | — | — |
| Surf | ❌ None | — | — |
| Visual Clock | ❌ None | — | — |
| Nearby Aircraft | Optional | Free | [OpenSky Network](https://opensky-network.org/) |

## Next Steps

- [Plugins Overview](/docs/plugins/overview) — Configure and enable plugins
- [Quick Start](/docs/setup/quick-start) — Get FiestaBoard running
