---
title: "FiestaBoard Update — May 2026"
description: "Flash a Raspberry Pi and skip Docker entirely, one-click auto-updates, and 25+ new plugins — the FiestaBoard plugin registry has roughly doubled to 45+."
slug: may-2026-update
authors: [team]
tags: [release]
image: ./social-card.png
---

Hi friends,

For anyone who missed the [first](/blog/introducing-fiestaboard) and [second](/blog/wysiwyg-editor-scheduling-disney-parks) posts: FiestaBoard is the free, open-source dashboard for Vestaboard. You self-host it, plug in the data sources you care about (weather, transit, stocks, sports, surf, your calendar, Last.fm, Home Assistant, dad jokes — you name it), and it drives your board. Flagship and Note both supported.

<!-- truncate -->

Since the last update, two things have changed that we think genuinely matter for this project:

## You no longer need to know Docker — just flash a Raspberry Pi

The biggest accessibility unlock: there's now a FiestaPi image you flash onto a microSD card with the official Raspberry Pi Imager. No command line, no docker-compose, no editing config files. Boot the Pi, open `http://fiestapi.local:4420` on any device on your network, and the setup wizard walks you the rest of the way.

While it runs on the Raspberry Pi Zero 2 W, we are testing and using a Pi 3B+ because we wanted an Ethernet port for a more stable connection. A microSD and a 5V power supply and you're done — that's an always-on controller for your board. A Pi 3B/4/5 works too if you have one in a drawer.

Setup guide: [Raspberry Pi setup](/docs/setup/raspberry-pi)

## One-click auto-updates

The other big quality-of-life change: FiestaBoard now updates itself. There's an in-app "Update available" banner with a single button — click it, you get a full-screen progress overlay, and a minute or two later you're on the latest version. This does require a second "sidecar" docker image that comes automatically with the FiestaPi. For existing users you'll want to pull the new docker compose file to join in on the fun.

Translation: you're not stuck on whatever version you installed six months ago. Bug fixes and new plugins land on your board without you having to think about it.

## 25+ new plugins since the last post

The plugin registry has roughly doubled. A non-exhaustive sampler of what's new:

- **Calendar Subscription** — point it at any public iCal URL, get upcoming events + pre-event alerts on the board
- **Home Assistant** — display any entity state via REST or MQTT
- **Aurora Forecast, ISS Tracker, Spacecraft Launches, Solar Activity, Moon Phase**
- **Earthquake, Wildfire, Volcano Activity, Lightning Alerts, River Flow, Tide Times, UV Index**
- **Hacker News, Reddit Hot, Currency Exchange, Network Speed, Pi-hole Stats**
- **Word of the Day, Quote of the Day, National Day, On This Day, Element of the Day, Pet Facts, Dad Jokes**
- **Santa Tracker** (don't @ me, it's December-shaped fun)
- **Webhook + Generic Data** — point at any JSON/XML feed and map fields to template variables, no code

Total is now 45+ plugins. Browse the list inside the app under Integrations, or here: [fiestaboard.app/plugins](/plugins)

![The Integrations page with plugin cards](/img/integrations-page.png)

## A few other things worth mentioning

- **Inline expressions in templates** — spreadsheet-style formulas so you can do math, conditionals, and string formatting right in the page editor.
- **WYSIWYG editor and Scheduling** from the last post are still here and have gotten a lot more polish.
- **Multi-board support** if you have more than one board.
- **Note device rendering** (the heart ❤️ character, etc.) is now correct.

## Come hang out / break things with us

The project remains open source and a labor of love — expect a few rough edges, but getting from unboxing to a functional board is now a breeze. Plus, it is forever free.

- Repo / issues / discussions: https://github.com/Fiestaboard/FiestaBoard
- Docs: https://fiestaboard.app
- Discord: https://discord.gg/JvN8y6ahaf

If you build a plugin, file an issue, or just want a feature — GitHub is the best place so it's all in one spot and others can chime in. We genuinely read everything. And if you're already running FiestaBoard, drop a screenshot of what's on your board right now in [Discord](https://discord.gg/JvN8y6ahaf) — that's always the best part.

Happy flipping.
