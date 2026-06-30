---
sidebar_position: 1
description: "Get FiestaBoard running on your Vestaboard in minutes. Flash a Raspberry Pi, use Docker Hub, or run the install wizard."
keywords: [FiestaBoard quick start, FiestaPi, Docker setup, getting started, Vestaboard setup, Vestaboard quick start, Vestaboard Docker, split-flap dashboard]
---

# Quick Start

Get FiestaBoard running in under 5 minutes.

## Option A: Raspberry Pi — FiestaPi (Easiest)

Have a Raspberry Pi? Flash a microSD card and boot. No Docker setup, no command line.

**→ [FiestaPi Quick Start](/docs/setup/raspberry-pi)** — Download, flash, boot, done.

FiestaPi includes self-updating out of the box — when a new version is released, an **Update Now** button appears in Settings and handles everything for you.

---

## Options B & C: Docker (any computer)

Running on a laptop, desktop, NAS, or server? You need:
- **Your board's API key** ([how to find it](#getting-your-board-api-key))
- **Docker and Docker Compose** ([install Docker Desktop](https://docs.docker.com/desktop/))

If you've never used Docker before, try the [Beginner's Guide](/docs/setup/beginners-guide) instead.

### Option B: Docker Hub (No Pi)

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

### Option C: Install Wizard

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

1. Request a Local API enablement token at [vestaboard.com/local-api](https://www.vestaboard.com/local-api)
2. After approval, Vestaboard emails you the token
3. Use the token to enable the Local API — FiestaBoard's **Settings** page can do this for you, or see the [Vestaboard Local API docs](https://docs.vestaboard.com/docs/local-api/authentication)
4. Save the API key and note the board's IP address

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

For the easiest Pi experience, flash the **[FiestaPi image](/docs/setup/raspberry-pi)** instead. It comes pre-configured with self-update enabled. For advanced setups (Pi you already have with Docker), see the [Raspberry Pi Deployment guide](/docs/deployment/raspberry-pi).

## Next Steps

- **[Your First 10 Minutes](/docs/setup/first-10-minutes)** - Create your first page and enable plugins
- **[Plugins Overview](/docs/plugins/overview)** - See all 23 available plugins
- **[Beginner's Guide](/docs/setup/beginners-guide)** - More detailed step-by-step instructions
- **[Docker Setup](/docs/setup/docker-setup)** - Understand the Docker architecture
