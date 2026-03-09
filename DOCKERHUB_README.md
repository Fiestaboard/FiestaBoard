# FiestaBoard

<p align="center">
  <img src="https://raw.githubusercontent.com/Fiestaboard/FiestaBoard/main/web/public/icons/icon-192x192.png" alt="FiestaBoard" width="120" height="120">
</p>

<p align="center">
  <strong>Open-source self-hosted platform for controlling split-flap displays</strong>
</p>

<p align="center">
  <a href="https://fiestaboard.app">Documentation</a> &bull;
  <a href="https://github.com/Fiestaboard/FiestaBoard">GitHub</a> &bull;
  <a href="https://discord.gg/ujasGntNhQ">Discord</a>
</p>

---

## What is FiestaBoard?

FiestaBoard is a free, open-source server that connects to your Vestaboard or compatible split-flap display and lets you control what it shows. Compatible with Vestaboard Flagship (22x6) and Note (15x3). Use built-in plugins to display weather, stocks, sports scores, transit times, surf conditions, and more.

You bring the board and the API keys for the services you care about. FiestaBoard handles the rest.

## Quick Start

```bash
docker pull fiestaboard/fiestaboard:latest
```

Create a `docker-compose.yml`:

```yaml
services:
  fiestaboard:
    image: fiestaboard/fiestaboard:latest
    ports:
      - "4420:3000"
    volumes:
      - ./data:/app/data
    restart: unless-stopped
```

Start it:

```bash
docker-compose up -d
```

Then open **http://localhost:4420** to connect your board and start the service.

> **Accessing from other devices:** FiestaBoard advertises itself on your local network via mDNS/Bonjour. Open **http://fiestaboard.local:4420** from any device on the same network. If `.local` addresses don't work, use your server's IP instead (e.g. `http://192.168.1.50:4420`).

## What You Can Display

FiestaBoard includes **23 built-in plugins**. Many work without any API key at all:

| Plugin | Description | API Key? |
|--------|-------------|----------|
| Weather | Temperature, UV, precipitation, high/low | Yes (free) |
| Stocks | Stock prices with color indicators | Optional |
| Sports Scores | NFL, Soccer, NHL, NBA scores | Optional |
| Traffic | Travel time with live traffic | Yes (free tier) |
| Home Assistant | Smart home status display | Yes (self-hosted) |
| Surf Conditions | Wave height and quality | No |
| Date & Time | Multiple formats with timezone support | No |
| Disney Parks | Wait times from Queue-Times.com | No |
| Last.fm | Currently playing music | Yes (free) |
| Visual Clock | Large pixel-art clock | No |
| Star Trek Quotes | Quotes from TNG, Voyager, DS9 | No |
| And 12 more... | Transit, aircraft, ferries, WiFi, sun art, countdown, etc. | Varies |

## Key Features

- **WYSIWYG Page Editor** - Design pages visually with real-time preview
- **Schedule Mode** - Automate which pages show at which times
- **Multi-Device Support** - Vestaboard Flagship (22x6) and Note (15x3)
- **Silence Schedule** - Set quiet hours so the board doesn't flip at night
- **Plugin Architecture** - Extend with your own custom data sources

## Screenshots

<p align="center">
  <img src="https://raw.githubusercontent.com/Fiestaboard/FiestaBoard/main/images/web-ui-home.png" alt="Web UI" width="600">
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/Fiestaboard/FiestaBoard/main/images/page-editor-wysiwyg.png" alt="Page Editor" width="600">
</p>

## Multi-Architecture Support

Images are available for:
- `linux/amd64` (standard x86_64 desktops and servers)
- `linux/arm64` (Raspberry Pi 3B+/4/5 with 64-bit OS, Apple Silicon)

Both architectures are included in every release.

## Documentation

Full documentation at **[fiestaboard.app](https://fiestaboard.app)**:

- [Beginner's Guide](https://fiestaboard.app/docs/setup/beginners-guide) - Step-by-step for new users
- [Your First 10 Minutes](https://fiestaboard.app/docs/setup/first-10-minutes) - What to do after setup
- [Plugin Configuration](https://fiestaboard.app/docs/plugins/configuration) - Enable and configure data sources
- [Raspberry Pi Deployment](https://fiestaboard.app/docs/deployment/raspberry-pi) - Always-on setup
- [Troubleshooting](https://fiestaboard.app/docs/troubleshooting) - Common issues and solutions

## Source Code

FiestaBoard is open source under the MIT License.

- **GitHub**: [github.com/Fiestaboard/FiestaBoard](https://github.com/Fiestaboard/FiestaBoard)
- **Issues**: [github.com/Fiestaboard/FiestaBoard/issues](https://github.com/Fiestaboard/FiestaBoard/issues)
- **Contributing**: [CONTRIBUTING.md](https://github.com/Fiestaboard/FiestaBoard/blob/main/CONTRIBUTING.md)
