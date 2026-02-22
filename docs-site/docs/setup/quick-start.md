---
sidebar_position: 1
description: "Get FiestaBoard running in minutes with Docker. Quick setup guide for your split-flap display."
keywords: [FiestaBoard quick start, Docker setup, getting started, Vestaboard setup, split-flap dashboard]
---

# Quick Start

Get FiestaBoard running in minutes with Docker Compose.

## Prerequisites

- **A split-flap display** you already own and have set up
- **Your board's API key** (Local API or Cloud Read/Write key)
- **Docker** and **Docker Compose** installed on your system

That's it. The install wizard handles the rest. Plugins that need external API keys (weather, traffic, etc.) can be configured later through the web UI.

## Installation (Recommended)

Run the setup wizard — it will collect your board API key, device type, and configuration, then start the server:

```bash
# Mac/Linux
./scripts/install.sh

# Windows (PowerShell)
.\scripts\install.ps1
```

The wizard will ask for:
1. **Board API key** (Local API key or Cloud Read/Write key)
2. **Device type** — Flagship (22×6) or Note (15×3)
3. **Board color** — Black or White

When it finishes, FiestaBoard is running.

## Access Your Dashboard

Once running, access FiestaBoard at:

| Service | URL |
|---------|-----|
| **Web UI** | http://localhost:3000 |
| **API** | http://localhost:3000 |
| **API Docs** | http://localhost:3000/docs |

## Start the Display Service

1. Open http://localhost:3000 in your browser
2. Click the **"▶ Start Service"** button
3. Your board will start updating!

## Stop FiestaBoard

```bash
docker-compose down
```

## Getting Your Board API Key

Have your board API key ready before running the wizard.

### Local API (Recommended)

1. Open the board's mobile app
2. Go to **Settings** → **Local API**
3. Copy your API key and note the board's IP address

### Cloud API (Alternative)

1. Go to [web.vestaboard.com](https://web.vestaboard.com)
2. Navigate to the API section
3. Enable Read/Write API
4. Copy your Read/Write API key

## Manual Setup (Development)

If you're setting up a development environment or prefer not to use the wizard, you can configure FiestaBoard manually:

1. **Clone the repository**

```bash
git clone https://github.com/Fiestaboard/FiestaBoard.git
cd FiestaBoard
```

2. **Create your environment file**

```bash
cp env.example .env
```

3. **Edit `.env` with your board API key**

For Local API (recommended):
```bash
BOARD_API_MODE=local
BOARD_LOCAL_API_KEY=your_local_api_key_here
BOARD_HOST=192.168.0.11
TIMEZONE=America/Los_Angeles
```

For Cloud API:
```bash
BOARD_API_MODE=cloud
BOARD_READ_WRITE_KEY=your_board_key_here
TIMEZONE=America/Los_Angeles
```

4. **Start FiestaBoard**

```bash
docker-compose up -d --build
```

5. **Configure plugins in the web UI** — go to the Integrations page at http://localhost:8080 to enable plugins and enter API keys.

See `env.example` for all available environment variables (useful for development).

## Next Steps

- [Configure Plugins](/docs/plugins/overview) - Enable and configure data sources via the Integrations page
- [Local Development](/docs/setup/local-development) - Set up a development environment for contributing
- [Create Custom Plugins](/docs/development/plugin-guide) - Build your own plugins
- [V2 Migration Guide](/docs/setup/v2-migration) - Upgrading from a V1 installation
