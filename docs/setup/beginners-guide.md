---
sidebar_position: 2
description: "Step-by-step beginner guide to installing and configuring FiestaBoard for your Vestaboard or split-flap display."
keywords: [FiestaBoard beginner guide, first time setup, step by step, Vestaboard tutorial, Vestaboard beginner guide, Vestaboard installation, installation guide]
---

# Beginner's Guide

Never used Docker or the command line before? No problem. This guide walks through every step clearly, from picking the easiest install path to seeing your first content on the board.

**Time needed:** About 15 minutes.

## What You'll Need

- A split-flap display that's already set up and working with the board's app
- Your board's API key (Step 2 below shows you where to find it)
- An internet connection
- **Either** a Raspberry Pi + microSD card (see [The Easiest Path: Flash a Raspberry Pi](#the-easiest-path-flash-a-raspberry-pi)), **or** a computer (Mac, Windows, or Linux) where we'll install Docker

## The Easiest Path: Flash a Raspberry Pi

:::tip 🥇 We strongly recommend this path for first-time users
The simplest, most reliable way to run FiestaBoard — even if you've never touched a Pi or a terminal — is to flash a Raspberry Pi with our pre-built **FiestaPi** image.

**No Docker setup. No command line. No config files. Self-updating with one click.**
:::

If you have (or are willing to buy) a Raspberry Pi, this is by far the easiest route. Here's the whole process:

1. **Get a Raspberry Pi** (3B or newer — the Pi 4, Pi 5, and the inexpensive [Pi Zero 2 W](https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/) all work), plus a microSD card (8 GB minimum, 16 GB+ recommended) and a 5 V power supply.
2. **Download Raspberry Pi Imager** — a free, official tool from the Raspberry Pi Foundation that flashes images to SD cards. Available for Mac, Windows, and Linux on [the Raspberry Pi Imager downloads page](https://www.raspberrypi.com/software/).
3. **Download the FiestaPi image** from our [GitHub Releases page](https://github.com/Fiestaboard/FiestaBoard/releases/latest) — grab the file named `FiestaPi-<version>-arm64.img.xz`.
4. **Flash the SD card** with Raspberry Pi Imager:
   - Choose Device → your Pi model
   - Choose OS → scroll to the bottom → **Use custom** → pick the `.img.xz` file you downloaded
   - Choose Storage → your SD card
   - Click **Next** and use **Edit Settings** to pre-configure your Wi-Fi network and timezone
   - Click **Write** and wait ~5 minutes
5. **Insert the SD card into the Pi, plug it in**, and wait 2–3 minutes for first boot.
6. **Open a browser** on any device on the same network and go to **[the FiestaBoard setup wizard](http://fiestapi.local:4420)** at `http://fiestapi.local:4420`.
7. **Skip ahead to Step 2** below to grab your board's API key, then enter it in the wizard. You're done.

That's the whole thing. No Docker. No Terminal. No PowerShell. The Pi runs FiestaBoard 24/7 and updates itself with one click in **Settings → System** when new versions release.

**→ For the full step-by-step Pi-flash guide with screenshots and troubleshooting, see [FiestaPi Quick Start](/docs/setup/raspberry-pi).**

---

## Alternative: Run on Your Computer with Docker

Don't have a Pi (or want to use a computer you already own)? Continue with the Docker-based setup below. It works, but there are more moving parts than the Pi-flash path.

## Step 1: Install Docker

Docker is free software that runs FiestaBoard in a self-contained package. You only need to install it once.

### Mac

1. Go to [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/)
2. Click **Download** (choose Intel or Apple Silicon based on your Mac)
3. Open the downloaded file and drag Docker to your Applications folder
4. Open Docker Desktop from Applications - it will ask for permission to run
5. Wait for Docker to finish starting (the whale icon in your menu bar will stop animating)

### Windows

1. Go to [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/)
2. Click **Download for Windows**
3. Run the installer and follow the prompts (enable WSL 2 if asked)
4. Restart your computer if prompted
5. Open Docker Desktop - it should start automatically

### Linux

Open a terminal and run:

```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
```

Log out and back in after running these commands, then verify Docker is working:

```bash
docker --version
```

## Step 2: Get Your Board API Key

Your board API key is what lets FiestaBoard talk to your display. You can use either the Local API or the Cloud API.

### Local API (Recommended)

This is faster and supports transition animations. Your board and computer need to be on the same WiFi network.

1. Go to [the Vestaboard Local API token page](https://www.vestaboard.com/local-api) and request a Local API enablement token
2. After approval, Vestaboard will email you the token
3. Use the token to enable the Local API on your board — FiestaBoard's setup wizard and **Settings** page can do this for you (select the **Enablement Token** option and enter the token), or see the [Vestaboard Local API docs](https://docs.vestaboard.com/docs/local-api/authentication) for how to do it via `curl`
4. Save the **API key** returned in the response, and note your board's **IP address** (you can find it on your router or use FiestaBoard's network scan)

### Cloud API

Use this if your board and computer are on different networks, or if Local API isn't available for your board.

1. Go to [your Vestaboard account at web.vestaboard.com](https://web.vestaboard.com) and log in
2. Navigate to the API section
3. Enable the **Read/Write API**
4. Copy the API key and save it somewhere safe

## Step 3: Get FiestaBoard Running

Choose the path that's easiest for you:

### Path A: Docker Hub Pull (Simplest - no Git needed)

This is the fastest way. Open **Terminal** (Mac/Linux) or **PowerShell** (Windows):

**On Mac:** Press Cmd+Space, type "Terminal", press Enter.
**On Windows:** Press the Windows key, type "PowerShell", press Enter.

Then paste these three commands one at a time:

```bash
mkdir -p ~/fiestaboard && cd ~/fiestaboard
```

```bash
curl -O https://raw.githubusercontent.com/Fiestaboard/FiestaBoard/main/docker-compose.hub.yml
```

```bash
docker compose -f docker-compose.hub.yml up -d
```

Wait for it to finish downloading and starting (this takes 1-2 minutes the first time). When you see the terminal prompt again, FiestaBoard is running. **Skip to Step 4.**

:::caution Remember this folder!
FiestaBoard stores all your settings (board API keys, weather keys, pages, schedules, etc.) in a `data` folder it creates inside `~/fiestaboard`. **Whenever you update FiestaBoard later, you must `cd ~/fiestaboard` first** so Docker can find that data folder. If you forget and run the update from a different folder, FiestaBoard will look like a brand-new install with nothing configured. (Don't worry — your old settings aren't deleted, they're just in the original folder. See [Troubleshooting](/docs/troubleshooting#settings-or-board-credentials-are-gone-after-an-update) if this happens.)
:::

### Path B: Clone and Install Wizard

If you'd prefer to use the install wizard that guides you through setup:

```bash
git clone https://github.com/Fiestaboard/FiestaBoard.git
cd FiestaBoard
```

Then run the install wizard:

```bash
# Mac/Linux
./scripts/install.sh

# Windows (PowerShell)
.\scripts\install.ps1
```

The wizard will:

- Check that Docker is installed and running
- Ask for your board API key and device type
- Start the server
- Open the setup page in your browser

### Path C: Download ZIP (No Git, No curl)

1. Go to [the FiestaBoard repository on GitHub](https://github.com/Fiestaboard/FiestaBoard)
2. Click the green **Code** button
3. Click **Download ZIP**
4. Extract the ZIP file to a folder you'll remember (like Documents)
5. Open Terminal/PowerShell and navigate to the extracted folder:

   ```bash
   cd ~/Documents/FiestaBoard    # Mac/Linux
   cd Documents\FiestaBoard      # Windows
   ```

6. Run the install wizard:

   ```bash
   ./scripts/install.sh           # Mac/Linux
   .\scripts\install.ps1          # Windows
   ```

## Step 4: Open FiestaBoard

1. Open your web browser (Chrome, Firefox, Safari, Edge - any will work)
2. Go to **http://localhost:4420**
3. You should see the FiestaBoard dashboard

<AppShot name="web-ui-home" alt="FiestaBoard Dashboard" />

<AppShot name="dashboard-running" alt="Dashboard with active page displayed on the board" />

:::tip Accessing from a phone or another computer?
FiestaBoard automatically advertises itself on your local network. Try **http://fiestaboard.local:4420** from any device on the same WiFi. If that doesn't work, use the IP address of the computer running FiestaBoard (e.g. `http://192.168.1.50:4420`).
:::

:::info Don't see anything?
If the page doesn't load, wait 30 seconds and try again - the server may still be starting up. Make sure Docker Desktop is running (look for the whale icon in your system tray or menu bar).
:::

## Step 5: Connect Your Board

If you used the install wizard (Path B or C), you may have already entered your API key. If not:

1. In the FiestaBoard dashboard, go to **Settings**
2. Enter your board API key (from Step 2)
3. If you're using the Local API, also enter your board's IP address (settings save automatically)

<AppShot name="settings-board-config" alt="Settings page with board API key and IP address inputs" />

## Step 6: Verify the Service is Running

1. Go to the main dashboard at **http://localhost:4420**
2. The display service starts automatically — verify the status shows **Running**
3. Your board should start updating within a few seconds

Congratulations - your board is now controlled by FiestaBoard!

## Step 7: Make It Yours

Now the fun part. Here's what to do next:

<AppShot name="integrations-full" alt="Integrations page showing all plugins with toggle switches" />

<AppShot name="page-editor-variable-picker-open" alt="Variable Picker dropdown open in the page editor" />

### Enable some plugins

1. Go to the **Integrations** page
2. Toggle on plugins you're interested in
3. Plugins that need API keys will show you where to get them

**Start with these (no API key needed):**

- Date & Time
- Star Trek Quotes
- Guest WiFi
- Visual Clock
- Sun Art
- Disney Parks
- Surf Conditions

### Create your first page

1. Go to the **Pages** section
2. Click **New**
3. Use the visual editor to type what you want on the board
4. Use the **Variables** button to insert live data (like `{weather.temperature}` or `{date_time.datetime}`)
5. Click **Save**

### Set it as active

1. Select your new page from the Pages list
2. Click to make it the active page
3. Your board will update within a minute

For a more detailed walkthrough of these features, see **[Your First 10 Minutes](/docs/setup/first-10-minutes)**.

## Stopping and Starting FiestaBoard

### To stop

Go back to your Terminal/PowerShell and type:

```bash
docker compose down
```

### To start again later

Open Terminal/PowerShell, navigate to the FiestaBoard folder (if applicable), and type:

```bash
docker compose up -d
```

Then go to **http://localhost:4420** — the service starts automatically.

:::tip
If you used Path A (Docker Hub pull), make sure you're in the folder where the `docker-compose.hub.yml` file is, and use:

```bash
docker compose -f docker-compose.hub.yml up -d
```

:::

## Common Issues

### "Docker is not running"

Make sure Docker Desktop is open. Look for the whale icon in your menu bar (Mac) or system tray (Windows). On Linux, run `sudo systemctl start docker`.

### Page won't load at http://localhost:4420

- Wait 30-60 seconds after starting - the server needs time to initialize
- Make sure Docker containers are running: type `docker ps` in Terminal/PowerShell
- Make sure nothing else is using port 4420

### Board not updating

1. Check that the service shows **Running** on the dashboard
2. Verify your board API key is correct (go to Settings)
3. For Local API: make sure your board and computer are on the same WiFi network
4. Check the logs: `docker compose logs -f`

### Still stuck?

- Check the full [Troubleshooting Guide](/docs/troubleshooting)
- Ask in the [Discord community](https://discord.gg/2GAqKnRF6h)
- [Open an issue](https://github.com/Fiestaboard/FiestaBoard/issues) on GitHub

## Next Steps

- **[Your First 10 Minutes](/docs/setup/first-10-minutes)** - Detailed walkthrough of creating pages, enabling plugins, and scheduling
- **[Plugins Overview](/docs/plugins/overview)** - See all 23 available plugins
- **[Schedule Mode](/docs/features/schedule)** - Automate when different pages display
- **[Quick Start](/docs/setup/quick-start)** - Condensed reference for experienced users
