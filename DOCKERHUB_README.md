# FiestaBoard 🌮

<p align="center">
  <img src="https://raw.githubusercontent.com/Fiestaboard/FiestaBoard/main/web/public/icons/icon-192x192.png" alt="FiestaBoard" width="120" height="120">
</p>

<p align="center">
  <strong>Open-source self-hosted platform for controlling split-flap displays</strong>
</p>

<p align="center">
  <a href="https://fiestaboard.app">📖 Documentation</a> •
  <a href="https://github.com/Fiestaboard/FiestaBoard">💻 GitHub</a> •
  <a href="https://discord.gg/wc9dDfte">💬 Discord</a>
</p>

---

## What is FiestaBoard?

FiestaBoard is an open-source server that lets you control what appears on your split-flap display (like a Vestaboard). It gives you a self-hosted platform with a plugin system to pull in data from the sources that matter to you — weather, stocks, transit, sports, surf conditions, and more — and display it on your board.

You bring the board. You bring the API keys for the services you care about. FiestaBoard handles the rest.

## Quick Start

```bash
docker pull fiestaboard/fiestaboard:latest
```

```yaml
# docker-compose.yml
services:
  fiestaboard:
    image: fiestaboard/fiestaboard:latest
    ports:
      - "4420:3000"
    volumes:
      - ./data:/app/data
    restart: unless-stopped
```

```bash
docker-compose up -d
```

Then open **http://localhost:4420** to access the web UI, connect your board, and start the service.

## Features

- **18+ Plugins**: Weather, stocks, sports scores, transit, surf, traffic, Home Assistant, Disney park wait times, and more
- **Rich WYSIWYG Page Editor**: Create pages with a visual editor that shows exactly how content will appear on your board
- **Schedule Mode**: Visual calendar to schedule which pages display at which times
- **Multi-Device Support**: Vestaboard Flagship (22×6) and Note (15×3)
- **Configurable Update Interval**: Control how often your board refreshes (10–3600 seconds)
- **Silence Schedule**: Configure quiet hours when the board won't update
- **Plugin Architecture**: Easily extend with custom plugins

## Available Plugins

| Plugin | Description |
|--------|-------------|
| Weather | Temperature, UV index, precipitation, high/low, sunset |
| Stocks | Stock prices with color-coded indicators |
| Sports Scores | NFL, Soccer, NHL, NBA match scores |
| Home Assistant | House status display (doors, garage, locks) |
| Traffic | Travel time with live traffic data |
| Surf Conditions | Wave height and quality ratings |
| Muni Transit | Real-time SF Muni arrivals |
| Disney Parks | Wait times from Queue-Times.com |
| Date & Time | Multiple formats with timezone support |
| Last.fm | Currently playing music |
| Nearby Aircraft | Real-time aircraft info from OpenSky |
| Air Quality & Fog | AQI and fog conditions |
| Bay Wheels | Bike availability at stations |
| WSDOT Ferries | WA ferry schedules and alerts |
| Guest WiFi | Display WiFi credentials |
| Star Trek Quotes | Quotes from TNG, Voyager, DS9 |
| Sun Art | Sun position-based art patterns |
| Visual Clock | Large pixel-art style clock |

## Screenshots

<p align="center">
  <img src="https://raw.githubusercontent.com/Fiestaboard/FiestaBoard/main/images/web-ui-home.png" alt="Web UI" width="600">
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/Fiestaboard/FiestaBoard/main/images/page-editor-wysiwyg.png" alt="Page Editor" width="600">
</p>

## Documentation

Full documentation is available at **[fiestaboard.app](https://fiestaboard.app)**, including:

- [Beginner's Setup Guide](https://fiestaboard.app/docs/setup/beginners-guide)
- [Docker Setup](https://fiestaboard.app/docs/setup/docker-setup)
- [Plugin Development Guide](https://fiestaboard.app/docs/development/plugin-development)
- [Environment Variables Reference](https://fiestaboard.app/docs/reference/environment-variables)

## Multi-Architecture Support

Images are available for:
- `linux/amd64` (standard x86_64)
- `linux/arm64` (Raspberry Pi 3B+/4/5 with 64-bit OS, Apple Silicon)

*ARM64 builds are included in every release.*

## Source Code

FiestaBoard is open source under the MIT License.

- **GitHub**: [github.com/Fiestaboard/FiestaBoard](https://github.com/Fiestaboard/FiestaBoard)
- **Issues**: [github.com/Fiestaboard/FiestaBoard/issues](https://github.com/Fiestaboard/FiestaBoard/issues)
- **Contributing**: [CONTRIBUTING.md](https://github.com/Fiestaboard/FiestaBoard/blob/main/CONTRIBUTING.md)
