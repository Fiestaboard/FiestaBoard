---
sidebar_position: 7
description: "Turn any TV or screen with a web browser into a life-size virtual split-flap display — a FiestaPanel is a virtual board you drive with the same pages and schedules as a real Vestaboard."
keywords: [FiestaPanel, virtual board, virtual Vestaboard, split-flap TV, split flap display, wall display, digital signage, life-size board]
---

# FiestaPanel

FiestaPanel turns any screen with a web browser — most usefully a TV on a wall — into a realistic split-flap display that fills the screen. No Vestaboard hardware required.

A panel is a **virtual board**: FiestaBoard drives it exactly like a physical board (pages, schedules, plugins, transitions), and a full-screen web page renders whatever was last sent to it, optionally flipping its tiles with the same mechanical animation as the real thing.

## Overview

- **Auto-fit, true to life.** Tell FiestaBoard your screen's diagonal size and it builds the largest board that fits: every flap renders at real Vestaboard size, and the grid grows with the screen — a 65″ TV gets a 30×12 board, an 85″ TV gets 45×18. The board is borderless and frameless, filling the screen edge to edge (with up to a 10% gentle stretch to close any remaining gap).
- **Live.** The panel polls for new frames every 2 seconds, so anything that drives the board — a schedule flipping pages, a plugin update, the page editor's Live Output — appears on the TV within moments (with a full mechanical flip animation when you turn it on).
- **No login on the TV.** The panel URL works in any browser with no account or session. You configure everything in the FiestaBoard app; the TV just displays.

## Quick Setup

1. Open **Settings → Hardware → FiestaPanel** and click **Create panel**.
2. Give it a name and choose your TV's diagonal size (presets from 32″ to 85″, or a custom value). The board's grid is computed automatically.
3. Open the panel URL in the TV's web browser. Every panel gets a short URL that's easy to type on a TV — the first panel is `/p/1` (for example `http://192.168.1.50:4420/p/1`) — plus a QR code and a copy button in Settings.
4. Give the panel content the same way you would any board: it appears in the board selector, so set its active page, add it to schedules, or point plugins at it. Panels use note-array layouts (blocks of 15×3), which the page editor supports natively.

That's it. The TV shows a blank board until the first frame arrives.

## Display Options

Edit a panel any time — changes reach the TV within about 10 seconds, no reload needed:

| Setting | What it does |
|---|---|
| **TV size** | Drives everything: the flap scale (pixels-per-inch from your diagonal) and the auto-fit grid (as many real-size flaps as fit a 16:9 screen of that size). Changing it re-fits the board's dimensions. |
| **Flip animation** | Off by default — characters update in place instantly. Turn it on for the full mechanical spin on every change. |
| **Auto-dim** | Fades the panel down during a nightly window (e.g. 22:00–07:00), using the TV's own clock. |
| **Size calibration** | ±15% fine-tune for TVs whose browsers misreport their resolution or overscan the picture. |

## TV Tips

- **Fullscreen:** click or tap anywhere on the panel to toggle browser fullscreen. Many TV browsers are effectively fullscreen already.
- **Keep the screen awake:** the panel asks the browser for a screen wake lock where supported, but TV sleep timers usually win — disable the TV's screensaver/auto-off for the best result.
- **Mind burn-in on OLED:** a static message is a static image. The panel's background is pure black to minimize lit pixels, and auto-dim helps overnight.
- The cursor hides itself after a few seconds.

## Troubleshooting

| Symptom | Meaning |
|---|---|
| Blank board | Nothing has been sent to the panel's virtual board yet — set an active page or wait for its schedule. A restart of FiestaBoard also blanks panels until the next send. |
| Small amber dot in the corner | The TV lost its connection to FiestaBoard; the last frame stays up and the panel keeps retrying. |
| "This panel no longer exists" | The panel was deleted in the app. Create a new one and open its new URL. |
| Board looks the wrong physical size | Double-check the TV size setting, then use **Size calibration** to nudge it true. |
| Grid seems smaller than expected | Auto-fit grows in blocks of 15 columns × 3 rows, so some screens have leftover margin the ≤10% stretch can't close — the next block simply didn't fit at real flap size. |
| Content looks clipped or misplaced | The panel is a note-array board (e.g. 30×12). Author pages for that layout in the page editor — pages made for a 22×6 Flagship don't stretch to fill it. |
