# 🎯 Beginner's Guide to Setting Up FiestaBoard

**New to coding or technical setups? No worries!** This guide will walk you through everything step-by-step.

## What is FiestaBoard?

FiestaBoard is a server you run on your computer (or a Raspberry Pi) that connects to your split-flap display. It uses plugins to pull in data — weather, stocks, transit times, sports scores, and more — and displays it on your board. You choose which plugins to enable and bring the API keys for the services you care about.

## What You'll Need

1. **A split-flap display** that's already set up and working with the board's app
2. **Your board's API key** (you'll get this in Step 2)
3. **A computer** — Mac, Windows, or Linux
4. **About 15 minutes** for the initial setup

## Step 1: Install Docker Desktop

Docker is free software that runs FiestaBoard. Think of it as a container that packages everything the app needs.

### For Mac:
1. Go to [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/)
2. Click "Download for Mac" (choose the right version for your Mac — Intel or Apple Silicon)
3. Open the downloaded file and drag Docker to your Applications folder
4. Open Docker from Applications — it will ask for permission to run
5. Wait for Docker to start (you'll see a whale icon in your menu bar)

### For Windows:
1. Go to [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
2. Click "Download for Windows"
3. Run the installer and follow the prompts
4. Restart your computer when prompted
5. Open Docker Desktop — it should start automatically

### For Linux:
- Follow the instructions at [Docker Desktop for Linux](https://docs.docker.com/desktop/install/linux-install/)

## Step 2: Get Your Board API Key

Your board API key is what lets FiestaBoard send content to your display.

### Local API (Recommended — faster, supports animations)
1. Open the board's mobile app
2. Go to **Settings** → **Local API**
3. Copy the API key and note your board's IP address

### Cloud API (Alternative — works from anywhere)
1. Go to [web.vestaboard.com](https://web.vestaboard.com) and log in
2. Click on your board name
3. Look for "Settings" or "API" in the menu
4. Find "Read/Write API" and click "Enable"
5. Copy the key that appears — paste it somewhere safe

## Step 3: Set Up FiestaBoard

You **don't** need to download the FiestaBoard source code. The pre-built Docker images are published to the GitHub Container Registry — Docker will pull them for you automatically.

### Create a project folder

1. **Open Terminal** (Mac/Linux) or **PowerShell** (Windows)
2. **Create a folder and go into it:**

   **Mac/Linux:**
   ```bash
   mkdir ~/FiestaBoard && cd ~/FiestaBoard
   ```

   **Windows (PowerShell):**
   ```powershell
   mkdir $HOME\FiestaBoard; cd $HOME\FiestaBoard
   ```

### Download the two files you need

You only need two small files — the Docker Compose configuration and the environment template.

**Mac/Linux:**
```bash
curl -O https://raw.githubusercontent.com/Fiestaboard/FiestaBoard/main/docker-compose.ghcr.yml
curl -O https://raw.githubusercontent.com/Fiestaboard/FiestaBoard/main/env.example
```

**Windows (PowerShell):**
```powershell
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/Fiestaboard/FiestaBoard/main/docker-compose.ghcr.yml" -OutFile "docker-compose.ghcr.yml"
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/Fiestaboard/FiestaBoard/main/env.example" -OutFile "env.example"
```

> **Don't have `curl`?** You can also open those URLs in your browser, then use **File → Save As** to save them into your FiestaBoard folder.

### Create your configuration file

**Mac/Linux:**
```bash
cp env.example .env
```

**Windows (PowerShell):**
```powershell
Copy-Item env.example .env
```

Now open the `.env` file in any text editor (Notepad, TextEdit, VS Code, etc.) and set your board API key from Step 2.

For **Local API** mode (recommended), find these lines and update them:
```
BOARD_API_MODE=local
BOARD_LOCAL_API_KEY=paste_your_local_api_key_here
BOARD_HOST=192.168.0.11  # Replace with your board's IP address
```

For **Cloud API** mode, set:
```
BOARD_API_MODE=cloud
BOARD_READ_WRITE_KEY=paste_your_read_write_key_here
```

Save the file when you're done.

## Step 4: Start FiestaBoard

1. Make sure Docker Desktop is running (look for the whale icon)
2. In your Terminal or PowerShell, run:

   ```bash
   docker compose -f docker-compose.ghcr.yml up -d
   ```

3. Docker will automatically download the FiestaBoard images and start the services
4. Wait about 30 seconds for everything to start up

## Step 5: Use the Web Interface

Once Docker finishes pulling and starting the containers:

1. **Open your web browser** (Chrome, Safari, Firefox, etc.)
2. **Go to:** `http://localhost:4420`
3. You'll see the FiestaBoard control panel!
4. **Click the green "▶ Start Service" button**
5. **Watch your board** — it should start updating!

> **Note:** The API runs on port **6969** and the Web UI on port **4420**. You can change these in the `docker-compose.ghcr.yml` file if needed.

## Step 6: Add Plugins

Now that your server is running, you can enable plugins to display different data:

1. In the web interface, go to the **Integrations** page
2. Enable the plugins you want (Weather, Stocks, Transit, etc.)
3. For plugins that need API keys, enter them directly in the Integrations page — it links to setup instructions for each one
4. Create pages using the **Page Editor** to design what appears on your board

> **Tip:** Many plugins work without any API key (Date & Time, Star Trek Quotes, Guest WiFi, Visual Clock, and more). Start with those while you gather API keys for others.

## 🎉 You're Done!

Your board should now be updating automatically!

### To stop FiestaBoard:
- Go back to your Terminal/PowerShell window
- Type: `docker compose -f docker-compose.ghcr.yml down` and press Enter

### To start it again later:
- Open Terminal/PowerShell
- Navigate to the FiestaBoard folder
- Type: `docker compose -f docker-compose.ghcr.yml up -d` and press Enter
- Go to `http://localhost:4420` and click Start Service

### To update to the latest version:
- Open Terminal/PowerShell
- Navigate to the FiestaBoard folder
- Run:
  ```bash
  docker compose -f docker-compose.ghcr.yml pull
  docker compose -f docker-compose.ghcr.yml up -d
  ```

## Need Help?

### Common Issues:

**"Docker is not running"**
- Make sure Docker Desktop is open and the whale icon is in your menu bar (Mac) or system tray (Windows)

**"Connection refused" when accessing http://localhost:4420**
- Wait a minute after starting, then refresh your browser
- Make sure Docker containers are running: `docker compose -f docker-compose.ghcr.yml ps`

**"Invalid API key"**
- Double-check you copied the key correctly (no extra spaces!)
- Make sure your `.env` file is named exactly `.env` (not `env.txt` or `.env.txt`)

**Board not updating**
- Make sure you clicked "Start Service" in the web interface
- Check the logs in your Terminal/Command Prompt window for errors
- Verify your board API key has the right permissions

### Still stuck?

- Check the main [Troubleshooting section](../../README.md#troubleshooting) in the README
- Open an issue on GitHub with details about your problem

## What's Next?

- **Enable plugins** — Go to the Integrations page in the web UI
- **Create pages** — Use the Page Editor to design your board layouts
- **[Set up a schedule](../../README.md#system-features)** — Configure which pages show at which times
- **Browse plugin docs** — Each plugin has setup instructions in `plugins/<plugin_name>/docs/SETUP.md`

