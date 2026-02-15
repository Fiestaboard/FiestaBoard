# 🎯 Beginner's Guide to Setting Up FiestaBoard

**New to coding or technical setups? No worries!** This guide will walk you through everything step-by-step. You don't need to be a programmer - just follow along carefully.

## What You'll Need

Before starting, gather these items:

1. **A Computer** - Mac, Windows, or Linux all work
2. **Your Display Board** - Already set up and working with the board's app
3. **Internet Connection** - To download software and get real-time data
4. **About 30 minutes** - For the initial setup

## Step 1: Install Docker Desktop

Docker is free software that helps run FiestaBoard. Think of it as a mini-computer inside your computer that keeps everything organized.

### For Mac:
1. Go to [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/)
2. Click "Download for Mac" (choose the right version for your Mac - Intel or Apple Silicon)
3. Open the downloaded file and drag Docker to your Applications folder
4. Open Docker from Applications - it will ask for permission to run
5. Wait for Docker to start (you'll see a whale icon in your menu bar)

### For Windows:
1. Go to [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
2. Click "Download for Windows"
3. Run the installer and follow the prompts
4. Restart your computer when prompted
5. Open Docker Desktop - it should start automatically

### For Linux:
- Follow the instructions at [Docker Desktop for Linux](https://docs.docker.com/desktop/install/linux-install/)

## Step 2: Get Your API Keys

API keys are like passwords that let FiestaBoard talk to your board and get weather data. You'll need two keys to start:

### A. Board API Key

1. Go to [web.vestaboard.com](https://web.vestaboard.com) and log in
2. Click on your board name
3. Look for "Settings" or "API" in the menu
4. Find "Read/Write API" and click "Enable"
5. Copy the long key that appears - paste it somewhere safe (like a Notes app)

### B. Weather API Key

1. Go to [weatherapi.com](https://www.weatherapi.com/)
2. Click "Sign Up" (it's free - no credit card needed!)
3. Create an account with your email
4. After signing in, you'll see your API key on the dashboard
5. Copy this key and save it with your board API key

## Step 3: Download FiestaBoard

### Option A: If you have Git installed:
1. Open Terminal (Mac/Linux) or Command Prompt (Windows)
2. Navigate to where you want FiestaBoard (like your Documents folder)
3. Type: `git clone https://github.com/Fiestaboard/FiestaBoard.git`
4. Press Enter

### Option B: If you don't have Git:
1. Go to the FiestaBoard repository on GitHub
2. Click the green "Code" button
3. Click "Download ZIP"
4. Extract the ZIP file to a location you'll remember (like Documents)

## Step 4: Run the Installation Script

We've made this super easy! Just run one script and it will handle everything for you.

### For Mac/Linux:

1. **Open Terminal** (Press Cmd+Space, type "Terminal", press Enter)
2. **Navigate to the FiestaBoard folder:**
   ```bash
   cd Documents/FiestaBoard
   ```
   (Adjust the path if you put it somewhere else)

3. **Run the installation script:**
   ```bash
   ./scripts/install.sh
   ```

### For Windows:

1. **Open PowerShell** (Press Windows key, type "PowerShell", right-click and select "Run as Administrator")
2. **Navigate to the FiestaBoard folder:**
   ```powershell
   cd Documents\FiestaBoard
   ```
   (Adjust the path if you put it somewhere else)

3. **Run the installation script:**
   ```powershell
   .\scripts\install.ps1
   ```

### What the script does:

The installation script will:
- ✅ Check that Docker is installed and running
- ✅ Guide you through entering your API keys
- ✅ Ask for your location (optional)
- ✅ Create the configuration file automatically
- ✅ Build and start all the services
- ✅ Tell you when everything is ready!

Just follow the prompts and enter your API keys when asked. The script will handle the rest!

## Step 5: Use the Web Interface

Once the installation script completes, you'll see URLs to access FiestaBoard. Now for the fun part!

1. **Open your web browser** (Chrome, Safari, Firefox, etc.)
2. **Go to:** `http://localhost:8080`
3. You'll see the FiestaBoard control panel!
4. **Click the green "▶ Start Service" button** at the top
5. **Watch your board** - it should start updating!

## Step 6: Customize Your Display

Now you can personalize what shows on your board:

1. In the web interface, click **"Pages"** in the menu
2. You'll see different page options (Weather, Stocks, etc.)
3. Click **"Settings"** to enable features you want (like Star Trek quotes!)
4. Create your own pages by mixing and matching features
5. Select which page you want active

## 🎉 You're Done!

Your board should now be updating automatically! Here are some tips:

### To stop FiestaBoard:
- Go back to your Terminal/Command Prompt window
- Press `Ctrl+C` (on both Mac and Windows)
- Then type: `docker-compose down` and press Enter

### To start it again later:
- Open Terminal/Command Prompt/PowerShell
- Navigate to the FiestaBoard folder
  - Mac/Linux: `cd Documents/FiestaBoard`
  - Windows: `cd Documents\FiestaBoard`
- Type: `docker-compose up -d` and press Enter
- Go to `http://localhost:8080` and click Start Service

## Need Help?

### Common Issues:

**"Docker is not running"**
- Make sure Docker Desktop is open and the whale icon is in your menu bar (Mac) or system tray (Windows)

**"Connection refused" when accessing http://localhost:8080**
- Wait a minute after starting, then refresh your browser
- Make sure Docker containers are running: `docker-compose ps`

**"Invalid API key"**
- Double-check you copied the keys correctly (no extra spaces!)
- Make sure your `.env` file is named exactly `.env` (not `env.txt` or `.env.txt`)

**Board not updating**
- Make sure you clicked "Start Service" in the web interface
- Check the logs in your Terminal/Command Prompt window for errors
- Verify your board API key has Read/Write permissions enabled

**Can't find the .env file**
- Hidden files (those starting with a dot) may not be visible by default
- Mac: Press Cmd+Shift+. (period) in Finder to show hidden files
- Windows: In File Explorer, go to View → Show → Hidden items

### Still stuck?

- Check the main [Troubleshooting section](../../README.md#troubleshooting) in the README
- Review the [Local Development guide](./LOCAL_DEVELOPMENT.md) for more details
- Open an issue on GitHub with details about your problem

## What's Next?

Once you have FiestaBoard running, explore these features:

- **[Add more plugins](../../README.md#features)** - Check out all the available plugins like stocks, surf reports, transit times, and more
- **Browse plugin docs** - Each plugin has setup instructions in `plugins/<plugin_name>/docs/SETUP.md`
- **[Set up a silence schedule](../../README.md#configuration)** - Configure quiet hours when the board won't update
- **Use the Integrations page** - Enable and configure plugins from the web UI

Enjoy your new smart display! 🎊

