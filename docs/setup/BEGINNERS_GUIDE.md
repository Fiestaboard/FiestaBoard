# Beginner's Guide to Setting Up FiestaBoard

**New to coding or technical setups? No worries!** This guide will walk you through everything step-by-step.

## What is FiestaBoard?

FiestaBoard is a server you run on your computer (or a Raspberry Pi) that connects to your split-flap display. It uses plugins to pull in data - weather, stocks, transit times, sports scores, and more - and displays it on your board. You choose which plugins to enable and bring the API keys for the services you care about.

## What You'll Need

1. **A split-flap display** that's already set up and working with the board's app
2. **Your board's API key** (you'll get this in Step 2)
3. **A computer** - Mac, Windows, or Linux
4. **About 15 minutes** for the initial setup

## Step 1: Install Docker Desktop

Docker is free software that runs FiestaBoard. Think of it as a container that packages everything the app needs.

### For Mac:
1. Go to [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/)
2. Click "Download for Mac" (choose the right version for your Mac, Intel or Apple Silicon)
3. Open the downloaded file and drag Docker to your Applications folder
4. Open Docker from Applications. It will ask for permission to run
5. Wait for Docker to start (you'll see a whale icon in your menu bar)

### For Windows:
1. Go to [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
2. Click "Download for Windows"
3. Run the installer and follow the prompts
4. Restart your computer when prompted
5. Open Docker Desktop. It should start automatically

### For Linux:
- Follow the instructions at [Docker Desktop for Linux](https://docs.docker.com/desktop/install/linux-install/)

## Step 2: Get Your Board API Key

Your board API key is what lets FiestaBoard send content to your display.

### Local API (Recommended, faster, supports animations)
1. Open the board's mobile app
2. Go to **Settings** → **Local API**
3. Copy the API key and note your board's IP address

### Cloud API (Alternative, works from anywhere)
1. Go to [web.vestaboard.com](https://web.vestaboard.com) and log in
2. Click on your board name
3. Look for "Settings" or "API" in the menu
4. Find "Read/Write API" and click "Enable"
5. Copy the key that appears, paste it somewhere safe

## Step 3: Set Up FiestaBoard

You **don't** need to download the FiestaBoard source code. The pre-built Docker images are published to the GitHub Container Registry. Docker pulls them for you automatically:

```
ghcr.io/fiestaboard/fiestaboard-api:latest
ghcr.io/fiestaboard/fiestaboard-ui:latest
```

You just need to create two small files: a `docker-compose.yml` and a `.env` with your board API key.

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

### Create `docker-compose.yml`

Create a new file called `docker-compose.yml` in your FiestaBoard folder. Open any text editor (Notepad, TextEdit, VS Code, etc.), paste the following, and save it:

```yaml
version: '3.8'
services:
  fiestaboard-api:
    image: ghcr.io/fiestaboard/fiestaboard-api:latest
    container_name: fiestaboard-api
    env_file: .env
    environment:
      - PRODUCTION=true
    restart: unless-stopped
    pull_policy: always
    ports:
      - "6969:8000"
    volumes:
      - ./data:/app/data

  fiestaboard-ui:
    image: ghcr.io/fiestaboard/fiestaboard-ui:latest
    container_name: fiestaboard-ui
    restart: unless-stopped
    pull_policy: always
    ports:
      - "4420:3000"
    environment:
      - FIESTA_API_URL=${FIESTA_API_URL:-}
    depends_on:
      - fiestaboard-api
```

> **Note:** Make sure the file is named exactly `docker-compose.yml` (not `docker-compose.yml.txt`).

### Create your `.env` file

Create another new file called `.env` (just a dot followed by "env") in the same FiestaBoard folder.

For **Local API** mode (recommended), add these lines:
```
BOARD_API_MODE=local
BOARD_LOCAL_API_KEY=paste_your_local_api_key_here
BOARD_HOST=192.168.0.11
```
Replace the API key with your key from Step 2, and replace `192.168.0.11` with your board's IP address.

For **Cloud API** mode, add these lines instead:
```
BOARD_API_MODE=cloud
BOARD_READ_WRITE_KEY=paste_your_read_write_key_here
```

Save the file.

> **Tip:** For a full list of configuration options, see the [`env.example`](https://github.com/Fiestaboard/FiestaBoard/blob/main/env.example) file on GitHub. But the lines above are all you need to get started.

## Step 4: Start FiestaBoard

1. Make sure Docker Desktop is running (look for the whale icon)
2. In your Terminal or PowerShell, run:

   ```bash
   docker compose up -d
   ```

3. Docker will automatically pull the FiestaBoard images from GHCR and start the services
4. Wait about 30 seconds for everything to start up

## Step 5: Use the Web Interface

Once Docker finishes pulling and starting the containers:

1. **Open your web browser** (Chrome, Safari, Firefox, etc.)
2. **Go to:** `http://localhost:4420`
3. You'll see the FiestaBoard control panel!
4. **Click the green "▶ Start Service" button**
5. **Watch your board** - it should start updating!

> **Note:** The API runs on port **6969** and the Web UI on port **4420**. You can change these in your `docker-compose.yml` file if needed.

## Step 6: Add Plugins

Now that your server is running, you can enable plugins to display different data:

1. In the web interface, go to the **Integrations** page
2. Enable the plugins you want (Weather, Stocks, Transit, etc.)
3. For plugins that need API keys, enter them directly in the Integrations page. It links to setup instructions for each one
4. Create pages using the **Page Editor** to design what appears on your board

> **Tip:** Many plugins work without any API key (Date & Time, Star Trek Quotes, Guest WiFi, Visual Clock, and more). Start with those while you gather API keys for others.

## You're Done!

Your board should now be updating automatically!

### To stop FiestaBoard:
- Go back to your Terminal/PowerShell window
- Type: `docker compose down` and press Enter

### To start it again later:
- Open Terminal/PowerShell
- Navigate to the FiestaBoard folder
- Type: `docker compose up -d` and press Enter
- Go to `http://localhost:4420` and click Start Service

### To update to the latest version:
- Open Terminal/PowerShell
- Navigate to the FiestaBoard folder
- Run:
  ```bash
  docker compose pull
  docker compose up -d
  ```

## Need Help?

### Common Issues:

**"Docker is not running"**
- Make sure Docker Desktop is open and the whale icon is in your menu bar (Mac) or system tray (Windows)

**"Connection refused" when accessing http://localhost:4420**
- Wait a minute after starting, then refresh your browser
- Make sure Docker containers are running: `docker compose ps`

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

- **Enable plugins** - Go to the Integrations page in the web UI
- **Create pages** - Use the Page Editor to design your board layouts
- **[Set up a schedule](../../README.md#system-features)** - Configure which pages show at which times
- **Browse plugin docs** - Each plugin has setup instructions in `plugins/<plugin_name>/docs/SETUP.md`

