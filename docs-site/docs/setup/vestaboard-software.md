---
sidebar_position: 10
title: "Split-Flap Display Software"
description: "FiestaBoard is free, open-source software for split-flap displays. Add plugins, scheduling, and a visual editor to your board. Compatible with Vestaboard Flagship and Note."
keywords: [split-flap display software, Vestaboard software, Vestaboard app, Vestaboard dashboard, split-flap dashboard, display software, Vestaboard plugins, Vestaboard open source, split-flap display app, best software for Vestaboard, third party split-flap software, self-hosted display software, FiestaBoard]
---

# Split-Flap Display Software

If you own a split-flap display and you're looking for software to get more out of it, **FiestaBoard** is a free, open-source platform built for split-flap display owners. It connects to your board via the Local API or Cloud API and gives you a plugin system, visual page editor, and scheduling — all through a self-hosted web interface.

FiestaBoard is compatible with split-flap displays including the Flagship (22×6) and Note (15×3) form factors.

## Why Split-Flap Display Owners Use FiestaBoard

FiestaBoard automates what your board displays throughout the day — no manual message-sending required. It's designed for people who want their split-flap display to be a living dashboard, not just a message board.

| Feature | FiestaBoard |
|---------|------------|
| **23 data plugins** | Weather, stocks, transit, sports scores, Disney park wait times, aircraft tracking, and more |
| **Visual page editor** | WYSIWYG editor that shows exactly how content will look on your board |
| **Schedule mode** | Automate which page shows at which time — morning commute, afternoon stocks, evening weather |
| **Silence schedule** | Set quiet hours so your board doesn't flip at night |
| **Plugin system** | Build your own plugins to display any data you want |
| **Self-hosted** | Runs on your own hardware — your data stays with you |
| **Multi-device support** | Manage multiple board sizes from one interface |
| **Open source** | MIT licensed, community-driven, fully transparent |

## How It Works

FiestaBoard connects to your split-flap display through either the **Local API** (recommended — faster, supports animations) or the **Cloud API** (works from anywhere). Once connected, FiestaBoard manages what your board displays based on the pages and schedule you configure.

```
Your Board ← API → FiestaBoard Server ← Plugins → Weather, Stocks, Transit, etc.
```

You can still send one-off messages through your board's official app anytime — FiestaBoard automates the data-driven content in between.

### Connecting Your Board

1. **Local API** — Open your board's mobile app → Settings → Local API → copy your API key and note the board's IP. [Full guide →](/docs/setup/quick-start#getting-your-board-api-key)
2. **Cloud API** — Go to your board's web interface → Settings → API → Enable Read/Write API → copy the key. [Full guide →](/docs/setup/cloud-api)

## What Can You Display?

With FiestaBoard's 23 built-in plugins, your split-flap display can show:

- **Weather** — Temperature, UV index, precipitation, high/low, sunset time
- **Stocks** — Real-time prices with color-coded change indicators
- **Sports scores** — NFL, NBA, NHL, Soccer match scores
- **Transit times** — SF Muni arrivals, traffic commute times, ferry schedules
- **Home automation** — Smart home status via Home Assistant
- **Music** — Currently playing track from Last.fm
- **Surf conditions** — Wave height and quality ratings
- **Aircraft tracking** — Real-time flights near your location
- **Disney park wait times** — Live ride queue times
- **And more** — Star Trek quotes, visual clock, countdown timers, dad jokes, guest WiFi credentials

Many plugins work without any API key. [See all 23 plugins →](/docs/plugins/overview)

## Getting Started

FiestaBoard runs in Docker — one command and you're up. You need:

1. A split-flap display that's already set up and connected to your network
2. Your board's API key (Local API or Cloud API)
3. Docker installed on any computer ([free download](https://docs.docker.com/get-started/get-docker/))

```bash
# Download the compose file
curl -O https://raw.githubusercontent.com/Fiestaboard/FiestaBoard/main/docker-compose.hub.yml

# Start FiestaBoard
docker-compose -f docker-compose.hub.yml up -d
```

Open **http://localhost:4420**, enter your board's API key, and you're running.

**New to Docker or the command line?** Follow the [Beginner's Guide](/docs/setup/beginners-guide) for step-by-step instructions with screenshots.

**Already comfortable with Docker?** The [Quick Start](/docs/setup/quick-start) gets you running in under 5 minutes.

## Runs Anywhere

FiestaBoard runs on any system with Docker:

- **Mac, Windows, Linux** — Desktop or server
- **Raspberry Pi** — Perfect for an always-on split-flap display controller. [Raspberry Pi guide →](/docs/deployment/raspberry-pi)
- **Home server / NAS** — Run alongside your other Docker services

## Free and Open Source

FiestaBoard is **MIT licensed** and **completely free**. There are no subscriptions, no accounts to create, and no data sent to third-party servers (beyond the APIs you choose to enable). Your board, your data, your rules.

- [GitHub Repository](https://github.com/Fiestaboard/FiestaBoard)
- [Docker Hub](https://hub.docker.com/r/fiestaboard/fiestaboard)
- [Discord Community](https://discord.gg/ujasGntNhQ)
- [Full Documentation](https://fiestaboard.app)

## Frequently Asked Questions

### Does FiestaBoard replace my board's official app?

No. FiestaBoard runs alongside the official app. You can still send messages through the official app anytime — FiestaBoard automates the data-driven content between your manual messages.

### Which board sizes does FiestaBoard support?

FiestaBoard supports the Flagship (22×6 characters) and Note (15×3 characters) form factors. The editor and plugins adapt to each board's dimensions automatically.

### Is FiestaBoard free?

Yes, completely. FiestaBoard is open-source software released under the MIT license. There are no paid tiers, subscriptions, or usage limits.

### Do I need to be technical to use FiestaBoard?

Basic comfort with copy-pasting terminal commands is helpful, but the [Beginner's Guide](/docs/setup/beginners-guide) walks through every step with screenshots. Once installed, everything is managed through a web interface — no code or config files needed.

### Can I build my own plugins?

Yes. FiestaBoard has a [plugin development guide](/docs/development/plugin-guide) that walks you through creating custom plugins to display any data source you want on your split-flap display.
