---
sidebar_position: 3
---

# Beginners Guide

A step-by-step guide for getting FiestaBoard running, even if you've never used Docker or the command line before.

## What You'll Need

- A computer (Mac, Windows, or Linux)
- A split-flap display board
- An internet connection
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

## Step 2: Get Your API Keys

You'll need two API keys to get started:

### Board API Key (Required)

1. Go to [web.vestaboard.com](https://web.vestaboard.com)
2. Log in with your board account
3. Navigate to the API section
4. Enable the **Read/Write API**
5. Copy the API key — you'll need it in Step 4

### Weather API Key (Required)

1. Go to [weatherapi.com](https://www.weatherapi.com/)
2. Click **Sign Up** (it's free!)
3. Verify your email
4. Go to your dashboard and copy your API key
5. Free tier gives you 1 million calls/month — more than enough

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

## Step 4: Configure FiestaBoard

### Using the Install Script (Easiest)

```bash
# Mac/Linux
./scripts/install.sh

# Windows (PowerShell)
.\scripts\install.ps1
```

The script will guide you through entering your API keys and other settings.

### Manual Configuration

1. Create your configuration file:

```bash
cp env.example .env
```

2. Open `.env` in any text editor and fill in your keys:

```bash
# Required - paste your keys here
BOARD_READ_WRITE_KEY=your_board_api_key_here
WEATHER_API_KEY=your_weather_api_key_here

# Your location for weather data
WEATHER_PROVIDER=weatherapi
WEATHER_LOCATION=San Francisco, CA

# Your timezone
TIMEZONE=America/Los_Angeles
```

:::tip Finding Your Timezone
Use the [TZ database name](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) for your timezone. Common examples:
- US East: `America/New_York`
- US Central: `America/Chicago`
- US Mountain: `America/Denver`
- US Pacific: `America/Los_Angeles`
- UK: `Europe/London`
:::

## Step 5: Start FiestaBoard

```bash
docker-compose up --build
```

The first time you run this, it will download and build everything. This may take a few minutes.

:::info
You'll see a lot of text scrolling by — that's normal! Wait until you see messages indicating the services are running.
:::

## Step 6: Open the Web UI

1. Open your web browser
2. Go to **http://localhost:8080**
3. You should see the FiestaBoard dashboard!

![FiestaBoard Dashboard](/img/web-ui-home.png)

## Step 7: Start the Display Service

1. In the web UI, click the **"▶ Start Service"** button
2. Your board will start updating with content!

## What's Next?

Now that FiestaBoard is running:

- **Configure plugins** — Go to the [Integrations](/docs/plugins/overview) page to enable weather, stocks, transit, and more
- **Create pages** — Use the [Page Editor](/docs/features/page-editor) to design what appears on your board
- **Set up schedules** — Use [Schedule Mode](/docs/features/schedule) to automate when different pages display

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

1. Check that your `BOARD_READ_WRITE_KEY` is correct in `.env`
2. Make sure the display service is started (click the ▶ button in the web UI)
3. Check the API docs at `http://localhost:8000/docs` for error messages

### Need more help?

- [Open an issue on GitHub](https://github.com/Fiestaboard/FiestaBoard/issues)
- Check the [Quick Start](/docs/setup/quick-start) guide for more details

## Next Steps

- [Quick Start](/docs/setup/quick-start) — More detailed setup instructions
- [Docker Setup](/docs/setup/docker-setup) — Understanding the Docker architecture
- [Plugins Overview](/docs/plugins/overview) — Configure your data sources
