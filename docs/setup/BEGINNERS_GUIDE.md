# Beginner's Guide to Setting Up FiestaBoard

**New to coding or technical setups? No worries!** This guide will walk you through everything step-by-step.

> **Full version online:** For the most up-to-date beginner's guide with images, visit [fiestaboard.app/docs/setup/beginners-guide](https://fiestaboard.app/docs/setup/beginners-guide).

## What is FiestaBoard?

FiestaBoard is a server you run on your computer (or a Raspberry Pi) that connects to your split-flap display. It uses plugins to pull in data - weather, stocks, transit times, sports scores, and more - and displays it on your board. You choose which plugins to enable and bring the API keys for the services you care about.

## What You'll Need

1. **A split-flap display** that's already set up and working with the board's app
2. **Your board's API key** (you'll get this in Step 2)
3. **A computer** - Mac, Windows, or Linux
4. **About 15 minutes** for the initial setup

> You only need your board API key to get started. No other API keys or configuration are required up front -- plugins like weather, stocks, and transit are all set up later through the web interface.

## Step 1: Install Docker Desktop

Docker is free software that runs FiestaBoard. Think of it as a container that packages everything the app needs. Installation takes just a few minutes.

### For Mac:
1. Go to the [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/) install page
2. Click "Download for Mac" (choose the right version for your Mac -- Intel or Apple Silicon)
3. Open the downloaded file and drag Docker to your Applications folder
4. Open Docker from Applications. It will ask for permission to run
5. Wait for Docker to start (you'll see a whale icon in your menu bar)

### For Windows:
1. Go to the [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/) install page
2. Click "Download for Windows"
3. Run the installer and follow the prompts
4. Restart your computer when prompted
5. Open Docker Desktop. It should start automatically

### For Linux:
1. Open a terminal and run:
   ```bash
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   sudo usermod -aG docker $USER
   ```
2. Log out and back in for the group change to take effect
3. Verify Docker is working: `docker --version`

## Step 2: Get Your Board API Key

Your board API key is what lets FiestaBoard send content to your display.

### Local API (Recommended, faster, supports animations)
1. Open the board's mobile app
2. Go to **Settings** > **Local API**
3. Copy the API key and note your board's IP address

### Cloud API (Alternative, works from anywhere)
1. Go to [web.vestaboard.com](https://web.vestaboard.com) and log in
2. Click on your board name
3. Navigate to the API section
4. Find "Read/Write API" and click "Enable"
5. Copy the key that appears, paste it somewhere safe

## Step 3: Get FiestaBoard Running

### Easiest: Pull from Docker Hub (no clone needed)

Open Terminal (Mac/Linux) or PowerShell (Windows) and run these two commands:

```bash
curl -O https://raw.githubusercontent.com/Fiestaboard/FiestaBoard/main/docker-compose.hub.yml

docker-compose -f docker-compose.hub.yml up -d
```

Wait for it to finish (1-2 minutes the first time). When you see the terminal prompt again, skip to Step 4.

### Alternative: Clone and Install Wizard

```bash
git clone https://github.com/Fiestaboard/FiestaBoard.git
cd FiestaBoard
```

Then run the installation script:

**For Mac/Linux:**
```bash
./scripts/install.sh
```

**For Windows (PowerShell):**
```powershell
.\scripts\install.ps1
```

The script will:
- Check that Docker is installed and running
- Ask for your board API key and settings
- Start the server
- Open the setup wizard in your browser

### No Git? Download ZIP

1. Go to the FiestaBoard repository on GitHub
2. Click the green "Code" button
3. Click "Download ZIP"
4. Extract the ZIP file to a location you'll remember (like Documents)
5. Open Terminal/PowerShell and navigate to the extracted folder
6. Run the install script as shown above

## Step 4: Connect and Start

1. Open **http://localhost:4420** in your browser
2. The setup wizard will guide you through connecting your board
3. The display service starts automatically once your board is connected

Your board should now be displaying content!

## Step 5: Make It Yours

1. Go to the **Integrations** page and enable some plugins (many need no API key -- try Date & Time, Star Trek Quotes, or Visual Clock)
2. Go to **Pages** and create a new page using the visual editor
3. Insert live data using the **Variables** button
4. Go to **Schedule** to automate which pages show at which times

> **Tip:** Many plugins work without any API key (Date & Time, Star Trek Quotes, Guest WiFi, Visual Clock, and more). Start with those while you gather API keys for others.

For a full walkthrough, see **[Your First 10 Minutes](https://fiestaboard.app/docs/setup/first-10-minutes)**.

## Stopping and Starting

### To stop FiestaBoard:
```bash
docker-compose down
```

### To start it again later:
```bash
docker-compose up -d
```
Then go to **http://localhost:4420** — the service starts automatically.

> If you used the Docker Hub method, use `docker-compose -f docker-compose.hub.yml up -d` instead.

## Need Help?

### Common Issues:

**"Docker is not running"**
- Make sure Docker Desktop is open and the whale icon is in your menu bar (Mac) or system tray (Windows)

**"Connection refused" when accessing http://localhost:4420**
- Wait 30-60 seconds after starting, then refresh your browser
- Make sure Docker containers are running: `docker ps`

**Board not updating**
- Make sure the dashboard shows **Running** at http://localhost:4420
- Verify your board API key is correct in Settings
- For local mode: make sure your board and computer are on the same WiFi network
- Check the logs: `docker-compose logs -f`

### Still stuck?

- Check the full [Troubleshooting Guide](https://fiestaboard.app/docs/troubleshooting)
- Ask in the [Discord community](https://discord.gg/wc9dDfte)
- [Open an issue](https://github.com/Fiestaboard/FiestaBoard/issues) on GitHub

## What's Next?

- **[Your First 10 Minutes](https://fiestaboard.app/docs/setup/first-10-minutes)** - What to do right after setup
- **[Plugin Configuration](https://fiestaboard.app/docs/plugins/configuration)** - Enable and configure data sources
- **[Schedule Mode](https://fiestaboard.app/docs/features/schedule)** - Automate your display
- **[Raspberry Pi Deployment](https://fiestaboard.app/docs/deployment/raspberry-pi)** - Set up an always-on board
