---
sidebar_position: 1
description: "FiestaBoard is an open-source server that lets split-flap display owners use plugins to get data onto their board."
keywords: [FiestaBoard, split-flap display, Vestaboard, smart dashboard, live display, open source]
---

# Introduction to FiestaBoard

**FiestaBoard** is an open-source server that connects to your split-flap display and lets you control what it shows. You bring the board and the API keys for the services you care about — FiestaBoard handles pulling data from those services and formatting it for your display.

## What Does FiestaBoard Do?

If you already own a split-flap display, FiestaBoard gives you a self-hosted platform with a plugin system to get data onto your board:

- **18 Built-in Plugins**: Weather, stocks, transit, sports, Disney park wait times, ferry schedules, and more
- **Multi-Device Support**: Create pages for both Vestaboard Flagship (22×6) and Note (15×3) — the editor and preview adapt to each device's dimensions
- **Multi-Board Management**: Configure and manage multiple physical boards from the Settings page
- **WYSIWYG Page Editor**: Create pages with a visual editor that shows exactly how content will appear
- **Schedule Mode**: Visual calendar to schedule which pages display when
- **Modern Web UI**: Manage pages, configure plugins, and monitor your display
- **Docker Ready**: One-command deployment on any system
- **Plugin Architecture**: Easily create your own custom data sources

## Quick Start

### Prerequisites

- **A split-flap display** you already own
- **Your board's API key**
- **Docker and Docker Compose** installed

### Using the Installation Script

The install wizard handles everything — it collects your board API key, creates the configuration, and starts the server:

```bash
# Mac/Linux
./scripts/install.sh

# Windows (PowerShell)
.\scripts\install.ps1
```

**Access your FiestaBoard:**
- **Web UI**: http://localhost:3000
- **API**: http://localhost:3000
- **API Docs**: http://localhost:3000/docs

## Available Plugins

| Plugin | Description |
|--------|-------------|
| 🌤️ Weather | Current conditions, UV index, high/low temps |
| 📈 Stocks | Real-time stock prices with color indicators |
| 🚇 Muni Transit | SF Muni arrival predictions |
| 🏆 Sports Scores | NFL, Soccer, NHL, NBA scores |
| 🌊 Surf Conditions | Wave height and quality ratings |
| 🖖 Star Trek Quotes | Random quotes from TNG, Voyager, DS9 |
| 🚗 Traffic | Travel time with live traffic |
| 💨 Air Quality | AQI and fog conditions |
| 🏠 Home Assistant | Smart home status display |
| 🏰 Disney Parks | Wait times from Queue-Times.com |
| 🚢 WSDOT Ferries | WA State ferry schedules and alerts |
| And more... | 18 plugins total |

## Next Steps

- [Beginners Guide](/docs/setup/beginners-guide) - Step-by-step setup for new users
- [Setup Guide](/docs/setup/quick-start) - Detailed installation instructions
- [V2 Migration Guide](/docs/setup/v2-migration) - Upgrading from V1
- [Features Overview](/docs/features/page-editor) - Page editor, scheduling, and more
- [Plugin Configuration](/docs/plugins/overview) - Configure your data sources
- [Reference](/docs/reference/api-endpoints) - API endpoints, character codes, and colors
- [Deployment](/docs/deployment/raspberry-pi) - Raspberry Pi and production deployment
- [Plugin Development](/docs/development/plugin-guide) - Create custom plugins
- [Troubleshooting](/docs/troubleshooting) - Common issues and solutions
