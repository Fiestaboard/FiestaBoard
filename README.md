<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs-site/static/img/branding/logo-lockup-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="docs-site/static/img/branding/logo-lockup-light.png">
    <img alt="FiestaBoard" src="docs-site/static/img/branding/logo-lockup-light.png" width="320">
  </picture>
</h1>

<p align="center">
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  <a href="https://github.com/Fiestaboard/FiestaBoard/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/Fiestaboard/FiestaBoard/ci.yml?label=CI" alt="CI"></a>
  <a href="https://hub.docker.com/r/fiestaboard/fiestaboard"><img src="https://img.shields.io/badge/docker-fiestaboard-blue?logo=docker" alt="Docker"></a>
  <a href="https://fiestaboard.app"><img src="https://img.shields.io/badge/docs-fiestaboard.app-orange" alt="Documentation"></a>
  <a href="https://discord.gg/JvN8y6ahaf"><img src="https://img.shields.io/badge/Discord-Join%20us-7289da?logo=discord&logoColor=white" alt="Discord"></a>
</p>

**FiestaBoard is free, open-source software for Vestaboard and split-flap displays.** It gives you a self-hosted platform with a plugin system to pull in data from the sources that matter to you - weather, stocks, transit, sports, surf conditions, and more - and display it on your board. Compatible with Vestaboard Flagship (22x6) and Note (15x3).

You bring the board. You bring the API keys for the services you care about. FiestaBoard handles the rest.

**[Full Documentation](https://fiestaboard.app)** &nbsp;|&nbsp; **[Discord Community](https://discord.gg/JvN8y6ahaf)**

---

## Get Started in 5 Minutes

### 🥇 Easiest path for everyone: Flash a Raspberry Pi

If you have (or are willing to buy) a Raspberry Pi 3B or newer, this is by far the simplest way to run FiestaBoard — no Docker setup, no command line, no config files. You only need three things:

1. A **Raspberry Pi** (3B / 3B+ / Zero 2 W / 4 / 5) with a microSD card and 5 V power supply
2. **[Raspberry Pi Imager](https://www.raspberrypi.com/software/)** — a free official tool from the Raspberry Pi Foundation that flashes SD cards (works on Mac, Windows, Linux)
3. The latest **FiestaPi image** from our [Releases page](https://github.com/Fiestaboard/FiestaBoard/releases/latest) (`FiestaPi-<version>-arm64.img.xz`)

**The 4-step flow:**

1. Open Raspberry Pi Imager → **Choose OS** → **Use custom** → pick the FiestaPi `.img.xz`.
2. Choose your microSD card and click **Next** → **Edit Settings** to pre-fill your Wi-Fi and timezone, then **Write**.
3. Insert the SD card into the Pi, plug in power, and wait 2–3 minutes for first boot.
4. Open **http://fiestapi.local:4420** in any browser on the same network. The setup wizard takes it from there.

That's it — FiestaBoard starts on every boot and updates itself with one click in Settings.

**→ [Full Raspberry Pi setup guide](docs/setup/RASPBERRY_PI.md)** with detailed flashing instructions, headless Wi-Fi setup, and troubleshooting.

> **Why we recommend this path:** The Pi is inexpensive, low-power, runs 24/7, and is purpose-built to be a reliable always-on display controller. Even users who have never touched a Raspberry Pi before can complete this in under 15 minutes.

### Already running Home Assistant? Use the HA add-on (beta)

If you have **Home Assistant OS** or **Home Assistant Supervised**, you can install FiestaBoard from the HA Add-on Store. You get sidebar Ingress, MQTT auto-discovery with the Mosquitto add-on, HA-managed backups of all your settings, and updates through HA's UI.

[![Open your Home Assistant instance and show the app store with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_store.svg)](https://my.home-assistant.io/redirect/supervisor_store/?repository_url=https%3A%2F%2Fgithub.com%2FFiestaboard%2FFiestaBoard-Home-Assistant-App)

**→ [Home Assistant Add-on setup guide](https://fiestaboard.app/docs/setup/home-assistant-addon)**

> 🧪 **The HA add-on is in beta and we want your feedback.** Report bugs or feature requests at the [add-on repo issues](https://github.com/Fiestaboard/FiestaBoard-Home-Assistant-App/issues), or come say hi on [Discord](https://discord.gg/JvN8y6ahaf) — even "it just worked" reports help us stabilize the beta.

### Alternative: Run on a computer with Docker

Already have a laptop, desktop, NAS, or home server? FiestaBoard runs anywhere Docker runs. **All you need:** Your board's API key + [Docker](https://docs.docker.com/get-started/get-docker/) installed.

#### Pull from Docker Hub (no clone needed)

```bash
# 1. Create a dedicated folder and move into it (this is where your settings will live)
mkdir -p ~/fiestaboard && cd ~/fiestaboard

# 2. Download the compose file
curl -O https://raw.githubusercontent.com/Fiestaboard/FiestaBoard/main/docker-compose.hub.yml

# 3. Start FiestaBoard
docker-compose -f docker-compose.hub.yml up -d
```

Open **http://localhost:4420** in your browser, connect your board, and you're running.

> **Important — keep using the same folder.** FiestaBoard stores all your settings, board credentials, and plugin configuration in a `./data` folder next to the compose file. Always `cd ~/fiestaboard` (or wherever you put it) before running `docker compose pull`, `up`, `down`, or any other compose command. Running compose from a different folder creates a brand-new empty `./data` and your previous settings will appear to be gone. See the [troubleshooting guide](https://fiestaboard.app/docs/troubleshooting#settings-or-board-credentials-are-gone-after-an-update) if this has already happened to you.

#### Clone and use the install wizard

```bash
git clone https://github.com/Fiestaboard/FiestaBoard.git
cd FiestaBoard

# Mac/Linux
./scripts/install.sh

# Windows (PowerShell)
.\scripts\install.ps1
```

The wizard collects your board API key, starts the server, and opens the setup page in your browser.

> **New to Docker or the terminal?** Follow the detailed [Beginner's Guide](https://fiestaboard.app/docs/setup/beginners-guide) for step-by-step instructions with screenshots — it leads with the easy Pi-flash path and falls back to Docker if you don't have a Pi.

### After Setup

1. Open **http://localhost:4420** — the setup wizard will guide you through connecting your board
2. The display service starts automatically once your board is connected
3. Go to **Integrations** to enable plugins (weather, stocks, etc.)
4. Go to **Pages** to create and design what your board displays
5. Go to **Schedule** to automate when different pages show up

> **Tip:** Many plugins need no API key at all - Date & Time, Star Trek Quotes, Guest WiFi, Visual Clock, Sun Art, and more work right out of the box. Start with those while you gather API keys for others.

> **Accessing from other devices:** FiestaBoard advertises itself on your local network via mDNS/Bonjour, so you can open **http://fiestaboard.local:4420** from any device on the same network. If `.local` addresses don't work on your network, use your server's IP address instead (e.g. `http://192.168.1.50:4420`).

---

## What Can You Display?

FiestaBoard has a catalog of **50+ plugins** covering weather, finance, transit, sports, entertainment, and home automation. Here's what they look like:

**Weather** - Temperature, UV index, precipitation, high/low, sunset time

![Weather Display](./docs-site/static/img/weather-display.png)

**Stocks** - Real-time prices with color-coded change indicators

![Stocks Display](./docs-site/static/img/stocks-display.png)

**Sports Scores** - Recent match scores from NFL, Soccer, NHL, and NBA

![Sports Scores Display](./docs-site/static/img/sports-scores-display.png)

**Nearby Aircraft** - Real-time aircraft info with call signs, altitude, and speed

![Nearby Aircraft Display](./docs-site/static/img/nearby-aircraft-display.png)

### All Available Plugins

<!-- Sorted alphabetically by plugin name -->
| Plugin | What It Shows | API Key? |
|--------|--------------|----------|
| [Air Quality & Fog](https://github.com/Fiestaboard/fiestaboard-plugin--air-fog) | AQI and fog conditions | Yes |
| [Airport Board](https://github.com/Fiestaboard/fiestaboard-plugin--airport-board) | Live flights near a configurable airport | No |
| [Allergy & Health](https://github.com/Fiestaboard/fiestaboard-plugin--health) | Allergy levels and health risk indicators | No |
| [Aurora Forecast](https://github.com/Fiestaboard/fiestaboard-plugin--aurora-forecast) | Geomagnetic Kp index and aurora visibility | No |
| [Bay Wheels](https://github.com/Fiestaboard/fiestaboard-plugin--baywheels) | Bike availability at stations | No |
| [Calendar Subscription](https://github.com/Fiestaboard/fiestaboard-plugin--calendar-sub) | Upcoming events from any .ics URL | No |
| [Countdown](./plugins/countdown/README.md) | Time remaining until an event | No |
| [Currency Exchange](https://github.com/Fiestaboard/fiestaboard-plugin--currency) | Live exchange rates (Frankfurter/ECB) | No |
| [Dad Jokes](https://github.com/Fiestaboard/fiestaboard-plugin--dad-jokes) | Random dad jokes | No |
| [Date & Time](./plugins/date_time/README.md) | Current date/time in many formats | No |
| [Disney Park Queue Times](https://github.com/Fiestaboard/fiestaboard-plugin--disney-parks-times) | Wait times for Disney rides | No |
| [Earthquake Monitor](https://github.com/Fiestaboard/fiestaboard-plugin--earthquake) | Recent USGS earthquake data | No |
| [Element of the Day](https://github.com/Fiestaboard/fiestaboard-plugin--element-of-day) | Periodic table element of the day | No |
| [Generic Data](https://github.com/Fiestaboard/fiestaboard-plugin--generic-data) | Custom data from any JSON/XML URL | No |
| [Guest WiFi](https://github.com/Fiestaboard/fiestaboard-plugin--guest-wifi) | WiFi credentials for guests | No |
| [Hacker News](https://github.com/Fiestaboard/fiestaboard-plugin--hacker-news) | Top Hacker News story title and score | No |
| [Home Assistant](https://github.com/Fiestaboard/fiestaboard-plugin--home-assistant) | Smart home status (doors, locks, garage) | Yes (self-hosted) |
| [ISS Tracker](https://github.com/Fiestaboard/fiestaboard-plugin--iss-tracker) | Real-time ISS position and altitude | No |
| [Last.fm Now Playing](https://github.com/Fiestaboard/fiestaboard-plugin--last-fm) | Currently playing music | Yes (free) |
| [Lightning Alerts](https://github.com/Fiestaboard/fiestaboard-plugin--lightning) | Active NWS weather alerts by US state | No |
| [Moon Phase](https://github.com/Fiestaboard/fiestaboard-plugin--moon-phase) | Current lunar phase and illumination | No |
| [Muni Transit](https://github.com/Fiestaboard/fiestaboard-plugin--muni) | Real-time SF Muni arrivals | Yes (free) |
| [National Day](https://github.com/Fiestaboard/fiestaboard-plugin--national-day) | Today's national days and observances | No |
| [Nearby Aircraft](https://github.com/Fiestaboard/fiestaboard-plugin--nearby-aircraft) | Real-time aircraft tracking | Optional |
| [Network Speed](https://github.com/Fiestaboard/fiestaboard-plugin--network-speed) | Internet download/upload speed | No |
| [On This Day](https://github.com/Fiestaboard/fiestaboard-plugin--on-this-day) | Historical event from today's date | No |
| [Pet Facts](https://github.com/Fiestaboard/fiestaboard-plugin--pet-facts) | Random cat or dog fact | No |
| [Pi-hole Stats](https://github.com/Fiestaboard/fiestaboard-plugin--pihole) | DNS query stats from local Pi-hole | No |
| [Quote of the Day](https://github.com/Fiestaboard/fiestaboard-plugin--quote-of-day) | Daily inspirational quote | No |
| [Random](./plugins/random/README.md) | Randomly selected values from a custom list, coin flip, or board color | No |
| [Reddit Hot](https://github.com/Fiestaboard/fiestaboard-plugin--reddit-hot) | Top post from any subreddit | No |
| [River Flow](https://github.com/Fiestaboard/fiestaboard-plugin--river-flow) | Real-time USGS streamflow data | No |
| [Santa Tracker](https://github.com/Fiestaboard/fiestaboard-plugin--santa-tracker) | Track Santa's journey on Christmas | No |
| [Solar Activity](https://github.com/Fiestaboard/fiestaboard-plugin--solar-activity) | Sunspot count and solar flare data | No |
| [Spacecraft Launches](https://github.com/Fiestaboard/fiestaboard-plugin--spacecraft-launches) | Upcoming rocket launch countdowns | No |
| [Sports Scores](https://github.com/Fiestaboard/fiestaboard-plugin--sports-scores) | NFL, Soccer, NHL, NBA scores | Optional |
| [Star Trek Quotes](https://github.com/Fiestaboard/fiestaboard-plugin--star-trek-quotes) | Quotes from TNG, Voyager, DS9 | No |
| [Stardate](https://github.com/Fiestaboard/fiestaboard-plugin--stardate) | Current TNG-era stardate | No |
| [Stocks](https://github.com/Fiestaboard/fiestaboard-plugin--stocks) | Stock prices with color indicators | Optional |
| [Sun Art](https://github.com/Fiestaboard/fiestaboard-plugin--sun-art) | Art pattern that follows the sun | No |
| [Surf Conditions](https://github.com/Fiestaboard/fiestaboard-plugin--surf) | Wave height and quality ratings | No |
| [Tide Times](https://github.com/Fiestaboard/fiestaboard-plugin--tide-times) | NOAA tide predictions by station | No |
| [Traffic](https://github.com/Fiestaboard/fiestaboard-plugin--traffic) | Travel time with live traffic | Yes (free tier) |
| [UV Index](https://github.com/Fiestaboard/fiestaboard-plugin--uv-index) | UV index and sun protection advice | No |
| [Visual Clock](https://github.com/Fiestaboard/fiestaboard-plugin--visual-clock) | Large pixel-art style clock | No |
| [Volcano Activity](https://github.com/Fiestaboard/fiestaboard-plugin--volcano) | Active volcanoes from Smithsonian GVP | No |
| [Weather](https://github.com/Fiestaboard/fiestaboard-plugin--weather) | Temperature, UV, precipitation, high/low | Yes (free) |
| [Webhook](https://github.com/Fiestaboard/fiestaboard-plugin--webhook) | Custom message via HTTP webhook | No |
| [White Noise](https://github.com/Fiestaboard/fiestaboard-plugin--white-noise) | Ambient rain/white noise effect | No |
| [Wildfire Monitor](https://github.com/Fiestaboard/fiestaboard-plugin--wildfire) | Active wildfires from NIFC | No |
| [Word of the Day](https://github.com/Fiestaboard/fiestaboard-plugin--word-of-day) | Word, pronunciation, and definition | No |
| [WSDOT Ferries](https://github.com/Fiestaboard/fiestaboard-plugin--wsdot) | WA State ferry schedules and alerts | Yes (free) |

---

## Features

### Rich Page Editor (WYSIWYG)

Create and edit board pages with a visual editor. See exactly how content will appear on your display, including dynamic data from plugins, colors, and alignment - all in real time.

![Rich Page Editor](./images/page-editor-wysiwyg.png)

### Schedule Mode

Use the visual calendar to schedule which page displays at which time. Set different pages for mornings, afternoons, and evenings. Choose a default page for gaps, or turn scheduling off to pick pages manually.

![Schedule Calendar](./images/schedule-calendar.png)

### Multi-Device Support

Create pages for both Vestaboard Flagship (22x6) and Note (15x3). The editor and preview adapt to each device's dimensions automatically.

### AI Page Drafts (Optional)

Click the **Gen AI** button in the page editor, describe what you want ("commute home dashboard with weather and the next two Muni arrivals"), and an LLM drafts the page for you. You always review and click **Save** — nothing is auto-published to your board.

**Bring your own provider.** FiestaBoard ships with no bundled LLM credentials and supports both **OpenAI-compatible** APIs (OpenRouter, OpenAI, Ollama, LM Studio, vLLM, llama.cpp) and the **Anthropic Messages API** (direct Claude access). See [docs/setup/AI_PROVIDERS.md](docs/setup/AI_PROVIDERS.md) for setup.

### More

- **Configurable Update Interval** - Refresh every 10 seconds to every hour
- **Silence Schedule** - Set quiet hours so the board doesn't flip at night
- **Smart Caching** - Page previews load fast; active displays always get fresh data
- **Docker Ready** - One command to deploy on any system, including Raspberry Pi

---

## Getting Your Board API Key

You'll need your board's API key to finish setup. There are two options:

### Local API (Recommended)

Faster, supports transition animations, works over your local network.

1. Request a Local API enablement token at [vestaboard.com/local-api](https://www.vestaboard.com/local-api)
2. After approval, Vestaboard emails you the token
3. Use the token to enable the Local API on your board (see [Vestaboard Local API docs](https://docs.vestaboard.com/docs/local-api/authentication))
4. Save the API key and note the board's IP address

### Cloud API

Works from anywhere with internet. No transition animations.

1. Go to [web.vestaboard.com](https://web.vestaboard.com)
2. Navigate to **Settings** > **API**
3. Enable **Read/Write API**
4. Copy the key

See [Cloud API Setup](https://fiestaboard.app/docs/setup/cloud-api) for details on choosing between the two modes.

---

## Running on a Raspberry Pi

For most users, the easiest way to run on a Pi is the pre-built **FiestaPi** image — see the [Get Started](#get-started-in-5-minutes) section above for the 4-step flash flow, or the [full Raspberry Pi setup guide](docs/setup/RASPBERRY_PI.md).

If you'd rather run Docker on a Pi you've already set up, the pre-built Docker image supports ARM64 out of the box — follow the same Docker Hub setup above. See the [Raspberry Pi Deployment guide](https://fiestaboard.app/docs/deployment/raspberry-pi) for advanced options.

---

## Stopping and Restarting

Run these from the folder you originally started FiestaBoard in (the one with your `docker-compose.hub.yml` or cloned `docker-compose.yml` and your `./data` directory).

```bash
# Stop FiestaBoard
docker-compose down

# Start it again (no rebuild needed)
docker-compose up -d

# View logs if something isn't working
docker-compose logs -f
```

If you pulled the image with `docker-compose.hub.yml`, add `-f docker-compose.hub.yml` to each command (for example `docker-compose -f docker-compose.hub.yml down`).

Then open **http://localhost:4420** — the service starts automatically once the container is running.

---

## Troubleshooting

### Board Not Updating

- Make sure the service shows **Running** on the dashboard (http://localhost:4420)
- Check your board API key is correct (Settings page in the web UI)
- For local mode: verify your board is on the same network as the server
- Check logs: `docker-compose logs -f`

### Docker Issues

- Make sure Docker Desktop is running (look for the whale icon)
- Check if the container is running: `docker ps`
- Port conflict? Change the host port in your compose file (left side of `4420:3000`)

### Plugin Issues

- Check the plugin's setup guide: `plugins/<plugin_name>/docs/SETUP.md`
- Verify API keys are correct and have no extra spaces
- Check API rate limits haven't been exceeded

### Still stuck?

- Check the full [Troubleshooting Guide](https://fiestaboard.app/docs/troubleshooting)
- Ask in [Discord](https://discord.gg/JvN8y6ahaf)
- [Open an issue](https://github.com/Fiestaboard/FiestaBoard/issues) on GitHub

---

## MCP Server

FiestaBoard exposes a built-in **MCP (Model Context Protocol) server** at `/api/mcp`. This lets external AI tools — Claude Desktop, Claude Code, or any MCP-compatible client — fully control your FiestaBoard via conversation: install plugins, create pages, manage schedules, and more.

### Connecting Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "fiestaboard": {
      "type": "http",
      "url": "http://fiestaboard.local:4420/api/mcp"
    }
  }
}
```

### Connecting Claude Code

```bash
/mcp add fiestaboard --transport http --url http://localhost:4420/api/mcp
```

### Available tools

The MCP server exposes 26+ tools covering the full FiestaBoard API:

| Category | Tools |
|----------|-------|
| Plugins | `list_installed_plugins`, `list_registry_plugins`, `install_plugin`, `enable_plugin`, `disable_plugin`, `uninstall_plugin`, `configure_plugin`, `update_plugin`, `get_template_variables` |
| Pages | `list_pages`, `get_page`, `create_page`, `update_page`, `delete_page` |
| Schedules | `list_schedules`, `create_schedule`, `update_schedule`, `delete_schedule` |
| Carousels | `list_carousels`, `create_carousel`, `update_carousel`, `delete_carousel` |
| System | `get_system_status`, `get_settings_summary`, `set_active_page`, `set_schedule_mode` |

The server is local-only with no authentication. When FiestaBoard gains a login system, Bearer-token auth will be added.

---

## Documentation

Full documentation is at **[fiestaboard.app](https://fiestaboard.app)**, including:

- **[Beginner's Guide](https://fiestaboard.app/docs/setup/beginners-guide)** - Step-by-step for non-technical users
- **[Your First 10 Minutes](https://fiestaboard.app/docs/setup/first-10-minutes)** - What to do right after setup
- **[Plugin Configuration](https://fiestaboard.app/docs/plugins/configuration)** - Enable and configure data sources
- **[Schedule Mode](https://fiestaboard.app/docs/features/schedule)** - Automate your display
- **[Raspberry Pi Deployment](https://fiestaboard.app/docs/deployment/raspberry-pi)** - Always-on setup
- **[Plugin Development Guide](https://fiestaboard.app/docs/development/plugin-guide)** - Build your own plugins

---

## For Developers

If you want to **contribute code** or **build plugins** (not just use FiestaBoard), see the development guides:

- **[Contributing Guide](./CONTRIBUTING.md)** - Branch workflow, PR process, standards
- **[Local Development](./docs/setup/LOCAL_DEVELOPMENT.md)** - Dev environment with hot-reload
- **[Plugin Development](./docs/development/PLUGIN_DEVELOPMENT.md)** - Create custom plugins

```bash
# Development environment (hot-reload for Python, volume mounts)
docker-compose -f docker-compose.dev.yml up --build
```

### Project Structure

```text
FiestaBoard/
├── plugins/          # Plugin-based data sources (weather, stocks, etc.)
├── src/              # Platform core (API server, display service, plugin system)
├── web/              # React Router v7 + Vite web UI
├── docs/             # Development documentation
├── docs-site/        # Documentation website (fiestaboard.app)
├── Dockerfile        # Unified container (API + Web UI + nginx)
└── docker-compose.yml
```


## Accessibility

FiestaBoard aims to meet [WCAG 2.2 Level AAA](https://www.w3.org/TR/WCAG22/) standards. We are committed to making the web UI accessible to everyone, including users who rely on assistive technologies. If you find an accessibility issue, please [open an issue](https://github.com/Fiestaboard/FiestaBoard/issues) or reach out on [Discord](https://discord.gg/JvN8y6ahaf).

---

## Sponsors

- [Vestaboard](https://fiestaboard.app/buyavestaboard) — Get $200 off a Vestaboard. Using this referral link helps support FiestaBoard at no extra cost to you.

## Support the Project

FiestaBoard is free and open source. If you find it useful and want to support continued development, consider buying me a coffee!

<a href="https://www.buymeacoffee.com/fiestaboard" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 60px !important;width: 217px !important;" ></a>

---

## Disclaimer

FiestaBoard is an independent, open-source project and is not affiliated with, sponsored by, or endorsed by Vestaboard, Inc. "Vestaboard" is a trademark of Vestaboard, Inc. FiestaBoard simply provides software that is compatible with Vestaboard hardware via their official APIs.


Made with ❤️ in San Francisco.
