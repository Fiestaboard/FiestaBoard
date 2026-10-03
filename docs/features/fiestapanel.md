---
sidebar_position: 7
description: "Turn any TV or screen with a web browser into a life-size virtual split-flap display — a FiestaPanel is a virtual board you drive with the same pages and schedules as a real Vestaboard."
keywords: [FiestaPanel, virtual board, virtual Vestaboard, split-flap TV, split flap display, wall display, digital signage, life-size board]
---

# FiestaPanel

FiestaPanel turns any screen with a web browser — most usefully a TV on a wall — into a realistic split-flap display that fills the screen. No Vestaboard hardware required.

A panel is a **virtual board**: FiestaBoard drives it exactly like a physical board (pages, schedules, plugins, transitions), and a full-screen web page renders whatever was last sent to it, optionally flipping its tiles with the same mechanical animation as the real thing.

## Overview

- **Auto-fit, true to life.** Tell FiestaBoard your screen's diagonal size and it builds the largest board that fits: every flap renders at real Vestaboard size, and the grid grows with the screen one character at a time — a 55″ TV gets a 29×12 board (29 columns, 12 rows), a 65″ TV gets 34×14, an 85″ TV gets 45×18. The board is borderless and frameless, filling the screen edge to edge (with up to a 10% gentle stretch to close any remaining gap).
- **Live.** The panel polls for new frames every 2 seconds, so anything that drives the board — a schedule flipping pages, a plugin update, the page editor's Live Output — appears on the TV within moments (with a full mechanical flip animation when you turn it on).
- **No login on the TV.** The panel URL works in any browser with no account or session. You configure everything in the FiestaBoard app; the TV just displays.

## Quick Setup

1. Open **Settings → Hardware → FiestaPanel** and click **Create panel**.
2. Give it a name and choose your TV's diagonal size (presets from 32″ to 85″, or a custom value). The board's grid is computed automatically.
3. Open the panel URL in the TV's web browser. Every panel gets a short URL that's easy to type on a TV — the first panel is `/p/1` (for example `http://192.168.1.50:4420/p/1`) — plus a QR code and a copy button in Settings.
4. Give the panel content the same way you would any board: it appears in the board selector, so set its active page, add it to schedules, or point plugins at it. A panel's grid is any number of columns and rows — it is not built from 15×3 Note blocks — and the page editor sizes pages to it for you (see below).

That's it. The TV shows a blank board until the first frame arrives.

## Making Pages for a Panel

A panel's grid is auto-fit from your TV size, so it is almost never one of the stock board shapes — which means a page has to be authored for *that panel*, not for a stock Flagship, Note or Note Array.

You never have to work that out yourself:

- **In the page editor**, the board-size picker beside the preview lists your panels by name at the top — "Kitchen TV · 29×12" (columns × rows). Pick one and the page is sized to that panel in one step. The generic Flagship / Note / Note Array choices stay below for real hardware.
- **Everywhere pages are listed**, a page whose grid matches a panel shows a quiet "Fits Kitchen TV" line, so you can tell at a glance which page belongs on which screen. Two panels the same size both fit the same page, and the label says so.
- **Ask FiestaBot.** "Make a page for my Kitchen TV panel" reads the panel's real grid before it builds anything.

A page is matched to a panel purely by its shape — nothing is stored to tie the two together. So a page fits every panel of that size, and re-fitting a panel (by changing its TV size) leaves pages authored for the old grid behind: the app warns you which ones when it happens.

Panels created on older versions were fit in whole 15×3 Note blocks, which often left part of the screen dark. After upgrading, FiestaBoard re-fits them per character on startup and moves the pages made for each panel's old grid to its new, larger one, so they keep showing — now across the whole screen. A page is left where it is if a real Note Array still uses that size, or if two panels that used to share it now fit differently.

## Display Options

Edit a panel any time — changes reach the TV within about 10 seconds, no reload needed:

| Setting | What it does |
|---|---|
| **TV size** | Drives everything: the flap scale (pixels-per-inch from your diagonal) and the auto-fit grid (as many real-size flaps — columns and rows — as fit a screen of that size and aspect ratio). Changing it re-fits the board's dimensions. |
| **Flip animation** | Off by default — characters update in place instantly. Turn it on for the full mechanical spin on every change. |
| **Auto-dim** | Fades the panel down during a nightly window (e.g. 22:00–07:00), using the TV's own clock. |
| **Size calibration** | ±15% fine-tune for TVs whose browsers misreport their resolution or overscan the picture. |

## FiestaPi HDMI Output

Running FiestaBoard on a FiestaPi? The Pi can drive a TV or monitor directly over HDMI — no browser setup on the TV at all:

1. Connect a screen to the Pi's HDMI port.
2. In **Settings → Hardware → FiestaPanel**, turn on **HDMI output on this FiestaPi**. The Pi installs a minimal kiosk browser (a few minutes, one time) and boots it onto the screen, pointed at the reserved `/p/display` URL.
3. Turn on **Display output** for the panel you want on that screen. Only one panel holds the role at a time — switching it re-points the screen from the app, no touching the Pi.

Until a panel is designated, the screen shows a short instruction card. Turn the HDMI switch off to stop the kiosk and reclaim its memory.

Notes:

- The switch appears only on FiestaPi installs with the updater sidecar running (it performs the install). If it reports the sidecar is too old, reboot the Pi once — it refreshes the sidecar on every boot — and try again.
- Fresh FiestaPi images also support a flash-time opt-in: drop an empty `fiestapi-hdmi.txt` on the SD card's boot partition and the kiosk is active from first boot.
- Prefer the command line? The same setup is one SSH command — see the [Raspberry Pi guide](https://github.com/Fiestaboard/FiestaBoard/blob/main/docs/internal/setup/RASPBERRY_PI.md).

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
| Grid seems smaller than expected | Auto-fit adds a column or row only when a whole real-size flap fits, so there can be a sliver of margin the ≤10% stretch can't close. Screens smaller than about 28″ (16:9) get a 15-column grid (the width of a Note) that is shrunk slightly to fit. |
| Board drawn too small, or only part of it, after an upgrade | The TV is still running the previous version of the panel page. Reload it once (or power-cycle a kiosk) to pick up the per-character grid. |
| Content looks clipped or misplaced | The panel has its own grid (e.g. 29×12). Pick the panel in the page editor's size picker — pages made for a 22×6 Flagship don't stretch to fill it. |
