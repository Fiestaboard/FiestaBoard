---
sidebar_position: 8
description: "Display Disney park wait times and other entertainment data on your split-flap display with FiestaBoard."
keywords: [FiestaBoard entertainment plugin, Disney wait times, theme park, split-flap entertainment, Vestaboard fun]
---

# Entertainment Plugins

FiestaBoard includes several fun entertainment plugins.

## Disney Parks Queue Times

Display real-time wait times for Disney theme park rides. **No API key required.**

### Setup

1. Enable the Disney Parks plugin in the Web UI **Integrations** page
2. Select your park:
   - Disneyland
   - Disney California Adventure
   - Walt Disney World (Magic Kingdom, EPCOT, Hollywood Studios, Animal Kingdom)

### Available Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{disney_parks_times.wait_times}` | Formatted wait times | `SPACE MTN 45 MIN` |

---

## Last.fm Now Playing

Display what's currently playing on your music services (Spotify, Apple Music, etc.) via Last.fm scrobbling.

### Setup

1. Create an account at [last.fm](https://www.last.fm/)
2. Set up scrobbling from your music app (Spotify, Apple Music, etc.)
3. Create an API application at [last.fm/api/account/create](https://www.last.fm/api/account/create)
4. Go to **Integrations** in the Web UI
5. Toggle the **Last.fm** plugin on
6. Enter your API key and username

### Available Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{last_fm.now_playing}` | Currently playing track | `BOHEMIAN RHAPSODY` |

---

## Star Trek Quotes

Display random quotes from Star Trek: The Next Generation, Voyager, and Deep Space Nine. **No API key required.**

### Setup

1. Enable the Star Trek Quotes plugin in the Web UI
2. (Optional) Select preferred series

### Available Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{star_trek_quotes.quote}` | Random Star Trek quote | `MAKE IT SO` |

### Series Color Coding

| Series | Color |
|--------|-------|
| The Next Generation | 🟨 Yellow |
| Deep Space Nine | 🟥 Red |
| Voyager | 🟦 Blue |

---

## Guest WiFi

Display your guest WiFi network name and password. **No API key required.**

### Setup

1. Go to **Integrations** in the Web UI
2. Toggle the **Guest WiFi** plugin on
3. Enter your WiFi network name and password in the settings

### Color Coding

| Element | Color |
|---------|-------|
| Header | 🟩 Green |
| SSID | 🟦 Blue |
| Password | 🟪 Violet |

---

## Other Entertainment Plugins

### Surf Conditions

Display wave height and swell conditions. **No API key required.**

### Sun Art

A full-screen artistic sun pattern that changes based on the sun's position throughout the day. **No API key required.**

### Visual Clock

A full-screen pixel-art style clock display. **No API key required.**

### Nearby Aircraft

Display real-time aircraft data from the OpenSky Network. Works without an API key, but an optional OpenSky account provides higher rate limits.

## Next Steps

- [Plugins Overview](/docs/plugins/overview) - See all available plugins
- [Plugin Configuration](/docs/plugins/configuration) - General plugin management
