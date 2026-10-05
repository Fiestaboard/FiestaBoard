---
sidebar_position: 1
description: "FiestaBoard puts your data out in the real world — free, open-source, self-hosted software for Vestaboard split-flap displays (Flagship, Note, and Note arrays) and any TV with a browser. 60+ plugins for weather, stocks, sports, transit, and more, plus optional AI-assisted page drafting."
keywords: [FiestaBoard, split-flap display, split-flap display software, Vestaboard, Vestaboard software, Vestaboard app, Vestaboard dashboard, Vestaboard open source, best software for Vestaboard, Vestaboard Note array, FiestaPanel, TV dashboard, virtual split-flap display, smart dashboard, live display, self-hosted dashboard, open source, Vestaboard AI, AI page generation]
---

# Welcome to FiestaBoard

**Your data, out in the real world.** FiestaBoard turns live data into something you can glance at from across the room — your morning commute, the markets, the surf, a little Star Trek wisdom — on the displays around you: split-flap boards like Vestaboard, or any TV with a browser. Pick from 60+ plugins, design pages in a visual editor, schedule what shows when, and build your own plugins. Free, open source, and self-hosted in Docker.

FiestaBoard works with Vestaboard Flagship (22×6), Note (15×3), and Note arrays (several Notes tiled into one canvas), plus [FiestaPanel](/docs/features/fiestapanel), which turns any TV or screen with a web browser into a virtual split-flap board. You bring the display and the API keys for the services you care about, and FiestaBoard handles pulling data from those services and formatting it for your display.

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

FiestaBoard has a catalog of **60+ plugins**, and many of them work without any API key at all. You install them from the [plugin registry](/docs/plugins/overview#installing-external-plugins) — a curated list maintained in the FiestaBoard repository — or from any public git repository. A small set ships bundled in the repo; the rest are pulled in on demand when you enable them.

## How It Works

1. **Install FiestaBoard** on any computer with Docker (your laptop, a Raspberry Pi, a home server)
2. **Connect your display** in the web UI. For a Vestaboard, enter your board's API key — FiestaBoard talks to the board only through Vestaboard's official [Local API](/docs/setup/api-keys) or [Cloud API](/docs/setup/cloud-api), the same APIs any developer can use. For a TV, [create a FiestaPanel](/docs/features/fiestapanel) and open its URL in the TV's browser.
3. **Enable plugins** to pull in the data you care about (weather, stocks, transit, etc.)
4. **Create pages** using the visual editor to design exactly what your board displays — or describe a page in natural language and let an LLM draft it for you with the optional [Gen AI page drafts](/docs/setup/ai-providers) feature (bring your own API key)
5. **Set a schedule** so different pages show at different times of day (optional)

Everything after the initial install is done through a web interface at **http://localhost:4420** - no config files to edit, no code to write.

## What You'll Need

- **A display**, either:
  - **A Vestaboard** (Flagship, Note, or a Note array), already set up and working, plus your board's API key ([how to find it](/docs/setup/api-keys)), **or**
  - **Any TV or screen with a web browser**, to show a [FiestaPanel](/docs/features/fiestapanel) virtual board — no API key needed
- **A Raspberry Pi** (recommended — easiest path), **or** a computer with Docker installed, to run the FiestaBoard software. This is a separate device on your network; nothing gets installed on the board itself.

That's it. No other API keys or configuration are needed to get started. Plugins that connect to external services (weather, traffic, etc.) can be enabled and configured later through the web UI.

## The Easiest Way: Flash a Raspberry Pi

:::tip 🥇 Recommended for everyone
The simplest, most reliable way to run FiestaBoard — for technical and non-technical users alike — is to flash a Raspberry Pi with our pre-built **FiestaPi** image using **[Raspberry Pi Imager](https://www.raspberrypi.com/software/)**.

**No Docker setup. No command line. No config files. Self-updating with one click.**

You only need: a Raspberry Pi (3B or newer), a microSD card, and 5 minutes.

**[→ FiestaPi Quick Start](/docs/setup/raspberry-pi)** — flash the image, boot the Pi, open a browser.
:::

If you don't have a Pi yet, any model from the Raspberry Pi 3B onwards works. The Pi 4 and Pi 5 are great choices, and even the inexpensive **[Raspberry Pi Zero 2 W](https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/)** can run FiestaBoard.

## Other Ways to Run FiestaBoard

Don't have a Pi, or already have a home server? FiestaBoard runs anywhere Docker runs — and if you already use Home Assistant OS or Supervised, you can install it from the HA Add-on Store.

<div className="row">
<div className="col col--4">

### I'm new to all this

Never used Docker or the command line? No problem.

**[Beginner's Guide](/docs/setup/beginners-guide)** walks you through every step with clear instructions — including the easy Pi-flash path and a Docker fallback.

</div>
<div className="col col--4">

### I'm comfortable with Docker

Know your way around `docker compose`? Run FiestaBoard on a laptop, NAS, or home server.

**[Docker Quick Start](/docs/setup/quick-start)** gets you running in under 5 minutes.

</div>
<div className="col col--4">

### I run Home Assistant 🏠

On Home Assistant OS or Supervised? Install FiestaBoard from the **HA Add-on Store** with one click — Ingress, MQTT auto-discovery, and HA backups all wired up.

**[Home Assistant Add-on](/docs/setup/home-assistant-addon)** — currently in beta, feedback welcome via [GitHub issues](https://github.com/Fiestaboard/FiestaBoard-Home-Assistant-App/issues) or [Discord](https://discord.gg/2GAqKnRF6h).

</div>
</div>

---

### Already running? Here's what to do next

If you've already got FiestaBoard installed and running, check out **[Your First 10 Minutes](/docs/setup/first-10-minutes)** to learn how to create your first page, enable your first plugin, and set up a schedule.

## All Documentation

| Section | What's Covered |
|---------|---------------|
| **[FiestaPi Quick Start](/docs/setup/raspberry-pi)** | Flash a Pi image and be running in minutes |
| **[Quick Start](/docs/setup/quick-start)** | Installation and first run (Docker) |
| **[Home Assistant Add-on](/docs/setup/home-assistant-addon)** | Install from the HA Add-on Store (beta) — Ingress, MQTT auto-discovery, HA backups |
| **[Beginner's Guide](/docs/setup/beginners-guide)** | Step-by-step for non-technical users |
| **[Your First 10 Minutes](/docs/setup/first-10-minutes)** | What to do right after setup |
| **[Plugins Overview](/docs/plugins/overview)** | All 60+ plugins and what they do |
| **[Plugin Configuration](/docs/plugins/configuration)** | Enabling and configuring plugins |
| **[Page Editor](/docs/features/page-editor)** | Creating and editing board content |
| **[AI Page Drafts](/docs/setup/ai-providers)** | Optional: bring your own LLM to draft pages from a prompt |
| **[Schedule Mode](/docs/features/schedule)** | Automating when pages display |
| **[Silence Schedule](/docs/features/silence-schedule)** | Setting quiet hours for your board |
| **[In-App Updates](/docs/features/updating)** | One-click updates from the Settings UI |
| **[Raspberry Pi](/docs/deployment/raspberry-pi)** | Always-on deployment on a Pi |
| **[V3 Migration](/docs/setup/v3-migration)** | Upgrading from FiestaBoard V2 (external plugins) |
| **[V2 Migration](/docs/setup/v2-migration)** | Upgrading from FiestaBoard V1 |
| **[Troubleshooting](/docs/troubleshooting)** | Common issues and solutions |
| **[Plugin Development](/docs/development/plugin-guide)** | Creating your own plugins |

<!-- sync-canary: cutover round trip, 2026-08-15 -->

## About Vestaboard

FiestaBoard is an independent, open-source project. It isn't affiliated with, sponsored by, or endorsed by Vestaboard, Inc. "Vestaboard" is a trademark of Vestaboard, Inc. FiestaBoard is software that sends messages to compatible boards through Vestaboard's official APIs. For questions about the board hardware itself, see [Vestaboard's own documentation](https://docs.vestaboard.com/).
