---
sidebar_position: 1
---

# Quick Start

Get FiestaBoard running in minutes with Docker Compose.

## Prerequisites

- **Docker** and **Docker Compose** installed on your system
- A split-flap board with Read/Write API key
- A Weather API key (free from WeatherAPI.com)

## Installation

### Option 1: Installation Script (Recommended)

The easiest way to get started is with our installation script:

```bash
# Mac/Linux
./scripts/install.sh

# Windows (PowerShell)
.\scripts\install.ps1
```

The script will guide you through the setup process.

### Option 2: Manual Setup

1. **Clone the repository**

```bash
git clone https://github.com/roblesi/FiestaBoard.git
cd FiestaBoard
```

2. **Create your environment file**

```bash
cp env.example .env
```

3. **Edit `.env` with your API keys**

```bash
# Required
BOARD_READ_WRITE_KEY=your_board_key_here
WEATHER_API_KEY=your_weather_api_key_here
WEATHER_PROVIDER=weatherapi
WEATHER_LOCATION=San Francisco, CA
TIMEZONE=America/Los_Angeles
```

4. **Start FiestaBoard**

```bash
# Build and run (first time)
docker-compose up --build

# Or run in background
docker-compose up -d --build
```

## Access Your Dashboard

Once running, access FiestaBoard at:

| Service | URL |
|---------|-----|
| **Web UI** | http://localhost:8080 |
| **API** | http://localhost:8000 |
| **API Docs** | http://localhost:8000/docs |

## Start the Display Service

1. Open http://localhost:8080 in your browser
2. Click the **"▶ Start Service"** button
3. Your board will start updating!

## Stop FiestaBoard

```bash
docker-compose down
```

## Getting API Keys

### Board API Key

1. Go to [web.vestaboard.com](https://web.vestaboard.com)
2. Navigate to the API section
3. Enable Read/Write API
4. Copy your Read/Write API key

### Weather API Key

**Recommended: WeatherAPI.com**
- Sign up at [weatherapi.com](https://www.weatherapi.com/)
- Free tier: 1 million calls/month
- No credit card required

## Next Steps

- [Configure Plugins](/docs/plugins/overview) - Enable and configure data sources
- [Local Development](/docs/setup/local-development) - Set up a development environment
- [Create Custom Plugins](/docs/development/plugin-guide) - Build your own plugins
