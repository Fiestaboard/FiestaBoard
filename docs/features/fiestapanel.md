---
sidebar_position: 7
description: "Turn any TV or screen with a web browser into a life-size virtual split-flap display — a FiestaPanel is a virtual board you drive with the same pages and schedules as a real Vestaboard."
keywords: [FiestaPanel, virtual board, virtual Vestaboard, split-flap TV, split flap display, wall display, digital signage, life-size board]
---

# FiestaPanel

FiestaPanel turns any screen with a web browser — most usefully a TV on a wall — into a realistic, life-size split-flap display. No Vestaboard hardware required.

A panel is a **virtual board**: FiestaBoard drives it exactly like a physical board (pages, schedules, plugins, transitions), and a full-screen web page renders whatever was last sent to it, flipping its tiles with the same mechanical animation as the real thing.

## Overview

- **Life-size.** Tell FiestaBoard your screen's diagonal size and the board renders at true physical scale — a 55″ TV shows a Flagship at its real 41.2″ width, hung on a softly lit virtual wall.
- **Live.** The panel polls for new frames every 2 seconds, so anything that drives the board — a schedule flipping pages, a plugin update, the page editor's Live Output — appears on the TV within moments, with a full mechanical flip animation.
- **No login on the TV.** The panel URL works in any browser with no account or session. You configure everything in the FiestaBoard app; the TV just displays.

## Quick Setup

1. Open **Settings → Hardware → FiestaPanel** and click **Create panel**.
2. Give it a name, pick the board shape (**Flagship** 22×6 or **Note** 15×3), and choose your TV's diagonal size (presets from 32″ to 85″, or a custom value).
3. Copy the panel URL — or scan the QR code — and open it in the TV's web browser.
4. Give the panel content the same way you would any board: it appears in the board selector, so set its active page, add it to schedules, or point plugins at it.

That's it. The TV shows a blank board until the first frame arrives.

## Display Options

Edit a panel any time — changes reach the TV within about 10 seconds, no reload needed:

| Setting | What it does |
|---|---|
| **TV size** | Drives the physical-scale math. If the screen is smaller than the real board (e.g. a 27″ monitor showing a 41.2″ Flagship), the board renders larger than the screen — that's what life-size means. |
| **Backdrop** | *Lit wall* (default): a softly lit room scene around the board. *Dark*: plain near-black. *Pure black*: true black, ideal for OLED TVs. |
| **Auto-dim** | Fades the panel down during a nightly window (e.g. 22:00–07:00), using the TV's own clock. |
| **Size calibration** | ±15% fine-tune for TVs whose browsers misreport their resolution or overscan the picture. |

## TV Tips

- **Fullscreen:** click or tap anywhere on the panel to toggle browser fullscreen. Many TV browsers are effectively fullscreen already.
- **Keep the screen awake:** the panel asks the browser for a screen wake lock where supported, but TV sleep timers usually win — disable the TV's screensaver/auto-off for the best result.
- **Mind burn-in on OLED:** a static message is a static image. The *Pure black* backdrop minimizes lit pixels, and auto-dim helps overnight.
- The cursor hides itself after a few seconds.

## Troubleshooting

| Symptom | Meaning |
|---|---|
| Blank board | Nothing has been sent to the panel's virtual board yet — set an active page or wait for its schedule. A restart of FiestaBoard also blanks panels until the next send. |
| Small amber dot in the corner | The TV lost its connection to FiestaBoard; the last frame stays up and the panel keeps retrying. |
| "This panel no longer exists" | The panel was deleted in the app. Create a new one and open its new URL. |
| Board looks the wrong physical size | Double-check the TV size setting, then use **Size calibration** to nudge it true. |
