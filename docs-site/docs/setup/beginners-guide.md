---
sidebar_position: 3
description: "Step-by-step beginner guide to installing and configuring FiestaBoard for your split-flap display."
keywords: [FiestaBoard beginner guide, first time setup, step by step, Vestaboard tutorial, installation guide]
---

# Beginners Guide

A step-by-step guide for getting FiestaBoard running, even if you've never used Docker or the command line before.

## What You'll Need

- A computer (Mac, Windows, or Linux)
- A split-flap display that's already set up and working with the board's app
- Your board's API key (you'll get this in Step 2)
- About 15 minutes

## Step 1: Install Docker

Docker is the tool that runs FiestaBoard. Think of it as a container that packages everything the app needs.

### Mac

1. Download [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/)
2. Open the downloaded `.dmg` file
3. Drag Docker to your Applications folder
4. Open Docker Desktop from Applications
5. Wait for Docker to finish starting (the whale icon in your menu bar will stop animating)

### Windows

1. Download [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
2. Run the installer
3. Follow the prompts (enable WSL 2 if asked)
4. Restart your computer if prompted
5. Open Docker Desktop

### Linux

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo apt-get install docker-compose-plugin
```

## Step 2: Get Your Board API Key

Your board API key is what lets FiestaBoard send content to your display.

### Local API (Recommended, faster, supports animations)

1. Open the board's mobile app
2. Go to **Settings** → **Local API**
3. Copy the API key and note your board's IP address

### Cloud API (Alternative, works from anywhere)

1. Go to [web.vestaboard.com](https://web.vestaboard.com)
2. Log in with your board account
3. Navigate to the API section
4. Enable the **Read/Write API**
5. Copy the API key, you'll need it in Step 4

## Step 3: Download FiestaBoard

### Option A: Using the Terminal (Recommended)

Open Terminal (Mac/Linux) or PowerShell (Windows):

```bash
git clone https://github.com/Fiestaboard/FiestaBoard.git
cd FiestaBoard
```

### Option B: Download ZIP

1. Go to [github.com/Fiestaboard/FiestaBoard](https://github.com/Fiestaboard/FiestaBoard)
2. Click the green **Code** button
3. Click **Download ZIP**
4. Extract the ZIP file
5. Open a terminal/PowerShell and navigate to the extracted folder

## Step 4: Run the Install Wizard

The install wizard handles everything. It collects your board API key, creates the configuration file, and starts the server.

```bash
# Mac/Linux
./scripts/install.sh

# Windows (PowerShell)
.\scripts\install.ps1
```

The script will guide you through entering your board API key and settings. When it finishes, FiestaBoard is running!

## Step 5: Open the Web UI

1. Open your web browser
2. Go to **http://localhost:8080**
3. You should see the FiestaBoard dashboard!

![FiestaBoard Dashboard](/img/web-ui-home.png)

## Step 6: Start the Display Service

1. In the web UI, click the **"▶ Start Service"** button
2. Your board will start updating with content!

## Step 7: Enable Plugins

Now that your server is running, add the data sources you care about:

1. Go to the **Integrations** page in the web UI
2. Enable the plugins you want
3. For plugins that need API keys (weather, traffic, etc.), enter them directly in the Integrations page. It links to setup instructions for each one

> **Tip:** Many plugins work without any API key: Date & Time, Star Trek Quotes, Guest WiFi, Visual Clock, Sun Art, and more. Start with those!

## What's Next?

Now that FiestaBoard is running:

- **Configure plugins** - Go to the [Integrations](/docs/plugins/overview) page to enable data sources
- **Create pages** - Use the [Page Editor](/docs/features/page-editor) to design what appears on your board
- **Set up schedules** - Use [Schedule Mode](/docs/features/schedule) to automate when different pages display

## Stopping FiestaBoard

To stop FiestaBoard, press `Ctrl+C` in the terminal, or run:

```bash
docker-compose down
```

To start it again later (without rebuilding):

```bash
docker-compose up
```

## Troubleshooting

### "Docker is not running"

Make sure Docker Desktop is open and running. Look for the whale icon in your system tray/menu bar.

### "Port already in use"

Another application is using port 8080 or 8000. Stop the other application or change the port in `docker-compose.yml`.

### "Board not updating"

1. Check that your board API key is correct in `.env`
2. Make sure the display service is started (click the ▶ button in the web UI)
3. For local mode: verify your board is on the same network
4. Check the logs: `docker-compose logs -f`

### Need more help?

- [Open an issue on GitHub](https://github.com/Fiestaboard/FiestaBoard/issues)
- Check the [Quick Start](/docs/setup/quick-start) guide for more details

## Next Steps

- [Quick Start](/docs/setup/quick-start) - More detailed setup instructions
- [Docker Setup](/docs/setup/docker-setup) - Understanding the Docker architecture
- [Plugins Overview](/docs/plugins/overview) - Configure your data sources
