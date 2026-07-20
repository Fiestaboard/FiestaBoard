---
sidebar_position: 1
description: "FiestaBoard is free, open-source software for Vestaboard and split-flap displays. Add weather, stocks, sports, transit, and 23 more plugins to your Vestaboard Flagship or Note."
keywords: [FiestaBoard, split-flap display, split-flap display software, Vestaboard, Vestaboard software, Vestaboard app, Vestaboard dashboard, Vestaboard open source, best software for Vestaboard, smart dashboard, live display, open source]
---

# Welcome to FiestaBoard

FiestaBoard is free, open-source software for Vestaboard and split-flap displays. It connects to your board and lets you control what it shows through a web interface with plugins, a visual editor, and scheduling. Compatible with Vestaboard Flagship (22x6) and Note (15x3). You bring the board, you bring the API keys for the services you care about, and FiestaBoard handles pulling data from those services and formatting it for your display.

## What Can FiestaBoard Do?

Here's a quick look at what your board can show once FiestaBoard is running:

| Category | Examples |
|----------|---------|
| **Weather & Environment** | Temperature, UV index, precipitation, air quality, fog, surf conditions |
| **Finance** | Stock prices with color-coded change indicators |
| **Transit & Travel** | Muni arrivals, traffic commute times, ferry schedules, bike share availability |
| **Sports & Entertainment** | NFL/NBA/NHL/Soccer scores, Star Trek quotes, currently playing music |
| **Home** | Smart home status via Home Assistant, guest WiFi credentials |
| **Fun & Visual** | Disney park wait times, sun art, visual clock, stardate |

There are **23 built-in plugins**, and many of them work without any API key at all.

## How It Works

1. **Install FiestaBoard** on any computer with Docker (your laptop, a Raspberry Pi, a home server)
2. **Connect your board** by entering your board's API key in the web UI
3. **Enable plugins** to pull in the data you care about (weather, stocks, transit, etc.)
4. **Create pages** using the visual editor to design exactly what your board displays
5. **Set a schedule** so different pages show at different times of day (optional)

Everything after the initial install is done through a web interface at **http://localhost:4420** - no config files to edit, no code to write.

## What You'll Need

- **A Vestaboard** (Flagship or Note) or compatible split-flap display, already set up and working
- **Your board's API key** ([how to find it](/docs/setup/quick-start#getting-your-board-api-key))
- **Docker** installed on your computer ([free download](https://docs.docker.com/get-started/get-docker/))

That's it. No other API keys or configuration are needed to get started. Plugins that connect to external services (weather, traffic, etc.) can be enabled and configured later through the web UI.

## Choose Your Path

<div className="row">
<div className="col col--6">

### I'm new to all this

Never used Docker or the command line? No problem.

**[Beginner's Guide](/docs/setup/beginners-guide)** walks you through every step with clear instructions.

</div>
<div className="col col--6">

### I'm comfortable with Docker

Know your way around `docker compose`?

**[Quick Start](/docs/setup/quick-start)** gets you running in under 5 minutes.

</div>
</div>

---

### Already running? Here's what to do next

If you've already got FiestaBoard installed and running, check out **[Your First 10 Minutes](/docs/setup/first-10-minutes)** to learn how to create your first page, enable your first plugin, and set up a schedule.

## All Documentation

| Section | What's Covered |
|---------|---------------|
| **[Quick Start](/docs/setup/quick-start)** | Installation and first run |
| **[Beginner's Guide](/docs/setup/beginners-guide)** | Step-by-step for non-technical users |
| **[Your First 10 Minutes](/docs/setup/first-10-minutes)** | What to do right after setup |
| **[Plugins Overview](/docs/plugins/overview)** | All 23 plugins and what they do |
| **[Plugin Configuration](/docs/plugins/configuration)** | Enabling and configuring plugins |
| **[Page Editor](/docs/features/page-editor)** | Creating and editing board content |
| **[Schedule Mode](/docs/features/schedule)** | Automating when pages display |
| **[Silence Schedule](/docs/features/silence-schedule)** | Setting quiet hours for your board |
| **[Raspberry Pi](/docs/deployment/raspberry-pi)** | Always-on deployment on a Pi |
| **[V2 Migration](/docs/setup/v2-migration)** | Upgrading from FiestaBoard V1 |
| **[Troubleshooting](/docs/troubleshooting)** | Common issues and solutions |
| **[Plugin Development](/docs/development/plugin-guide)** | Creating your own plugins |
