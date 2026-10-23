---
sidebar_position: 4
description: "Turn any TV or screen with a web browser into a FiestaBoard display with FiestaPanel, in a split-flap or LED look. Native Apple TV and Android TV apps are coming soon."
keywords: [TV dashboard, FiestaPanel, TV information display, wall display, digital signage, virtual split-flap display, Apple TV dashboard, Android TV dashboard, Google TV]
---

# TVs

Any TV or screen with a web browser can be a FiestaBoard display. **FiestaPanel** fills the screen with a life-size board, drawn as split-flap flaps or as the dots of an LED sign. FiestaBoard drives it like any other display, with pages, schedules and plugins.

## Ways to Put FiestaBoard on a TV

| How | What you need | Status |
|---|---|---|
| **The TV's web browser** | A smart TV, streaming stick, or any screen with a browser | Available now |
| **HDMI from a FiestaPi** | A FiestaPi plugged into the TV | Available now |
| **Native TV apps** | Apple TV, Android TV or Google TV | Coming soon |

The native apps will show the same FiestaPanel boards without a browser. Until they ship, use the browser or a FiestaPi.

## Set It Up

1. In the setup wizard, pick **FiestaPanel**. If FiestaBoard is already set up, open **Displays**, click **Add a display**, and pick **FiestaPanel**.
2. Name the TV and enter its screen size in inches, measured diagonally. FiestaBoard works out the largest board that fits with life-size flaps. A 55″ TV gets 29 columns × 12 rows.
3. Open the panel's address in the TV's browser. The first panel is `/p/1`, for example `http://192.168.1.50:4420/p/1`. The panel's page in **Displays** also shows a QR code and a copy button.

That's it. The TV shows a blank board until the first page arrives. After that, it picks up each change within a couple of seconds.

## Split-Flap or LED Look

Each panel has a **Render style**:

- **Split-flap**, the default, draws life-size mechanical flaps, with an optional flip animation.
- **LED matrix** draws the board as the dots of an LED sign. It supports colored text and pixel canvases.

You can change the style any time, and the TV updates within about 10 seconds.

## Learn More

The [FiestaPanel guide](/docs/features/fiestapanel) covers every panel setting: auto-dim, size calibration, matrix sizing for the LED look, FiestaPi HDMI output, and tips for keeping the TV awake.
