---
sidebar_position: 1
description: "Get FiestaBoard running on your Vestaboard in minutes with Docker. Quick setup guide for Vestaboard Flagship and Note."
keywords: [FiestaBoard quick start, Docker setup, getting started, Vestaboard setup, Vestaboard quick start, Vestaboard Docker, split-flap dashboard]
---

# Quick Start

Get FiestaBoard running in under 5 minutes.

## What You'll Need

- **Your board's API key** ([how to find it](#getting-your-board-api-key))
- **Docker and Docker Compose** installed on your system

:::tip Don't have Docker yet?
Docker Desktop is free and takes a few minutes to install:
[Mac](https://docs.docker.com/desktop/setup/install/mac-install/) | [Windows](https://docs.docker.com/desktop/setup/install/windows-install/) | [Linux](https://docs.docker.com/desktop/setup/install/linux/)

If you've never used Docker before, the [Beginner's Guide](/docs/setup/beginners-guide) walks through every step.
:::

## Option A: Docker Hub (Simplest)

No repository to clone. Just two commands:

```bash
# Download the compose file
curl -O https://raw.githubusercontent.com/Fiestaboard/FiestaBoard/main/docker-compose.hub.yml

# Start FiestaBoard (pulls the image automatically)
docker compose -f docker-compose.hub.yml up -d
```

Open **http://localhost:4420** in your browser. You'll see the FiestaBoard dashboard.

:::tip Accessing from another device?
FiestaBoard advertises itself on your local network via mDNS/Bonjour. From any device on the same network you can use **http://fiestaboard.local:4420**. If `.local` addresses don't work on your network, use your server's IP address instead (e.g. `http://192.168.1.50:4420`).
:::

## Option B: Install Wizard

Clone the repository and run the install script. It checks prerequisites, starts the server, and opens the setup wizard in your browser:

```bash
git clone https://github.com/Fiestaboard/FiestaBoard.git
cd FiestaBoard

# Mac/Linux
./scripts/install.sh

# Windows (PowerShell)
.\scripts\install.ps1
```

The wizard asks for your board API key, device type, and board color, then starts everything for you.

## Connect Your Board

Once FiestaBoard is running at **http://localhost:4420**:

1. The setup wizard will guide you through connecting your board (or go to **Settings** if you've already been through setup)
2. Once connected, the display service starts automatically
3. Verify the dashboard shows **Running** — your board is now connected!

<ThemedScreenshot src="/img/guides/settings-board-config.png" alt="Settings page with board API key and IP address inputs" />

## What to Do Next

Now that FiestaBoard is running, you'll want to:

1. **Enable some plugins** - Go to the **Integrations** page and turn on plugins like Date & Time, Star Trek Quotes, or Weather
2. **Create your first page** - Go to **Pages**, click **New**, and use the visual editor to design what your board shows
3. **Set up a schedule** - Go to **Schedule** to automate which pages display at which times

:::tip Start simple
Many plugins need no API key: Date & Time, Star Trek Quotes, Guest WiFi, Visual Clock, Sun Art, Disney Parks, Surf Conditions, and more. Start with those while you gather API keys for weather, traffic, etc.
:::

<ThemedScreenshot src="/img/guides/integrations-full.png" alt="Integrations page showing all plugins with toggle switches" />

<ThemedScreenshot src="/img/guides/schedule-calendar-populated.png" alt="Schedule calendar with multiple time-based entries" />

For a full walkthrough, see **[Your First 10 Minutes](/docs/setup/first-10-minutes)**.

## Getting Your Board API Key

Have your board API key ready before running setup. There are two connection modes:

### Local API (Recommended)

Faster updates, supports transition animations, works over your local network.

1. Open the board's mobile app
2. Go to **Settings** > **Local API**
3. Copy your API key and note the board's IP address

### Cloud API (Alternative)

Works from anywhere with internet. No transition animations. See [Cloud API Setup](/docs/setup/cloud-api) for details.

1. Go to [web.vestaboard.com](https://web.vestaboard.com)
2. Navigate to the API section
3. Enable **Read/Write API**
4. Copy your key

## Stopping and Restarting

```bash
# Stop FiestaBoard
docker compose down

# Start again later (no rebuild needed)
docker compose up -d
```

After restarting, open **http://localhost:4420** — the service resumes automatically.

## Running on a Raspberry Pi?

The same Docker image works on Raspberry Pi (ARM64). Follow the steps above on your Pi, or see the [Raspberry Pi Guide](/docs/deployment/raspberry-pi) for auto-start on boot and performance tips.

## Next Steps

- **[Your First 10 Minutes](/docs/setup/first-10-minutes)** - Create your first page and enable plugins
- **[Plugins Overview](/docs/plugins/overview)** - See all 23 available plugins
- **[Beginner's Guide](/docs/setup/beginners-guide)** - More detailed step-by-step instructions
- **[Docker Setup](/docs/setup/docker-setup)** - Understand the Docker architecture
