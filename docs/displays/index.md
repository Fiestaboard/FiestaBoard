---
sidebar_position: 1
description: "The displays FiestaBoard can drive — split-flap boards like Vestaboard, LED matrices like the Divoom Pixoo 64, and any TV with a web browser — and how to pick and add one."
keywords: [FiestaBoard displays, supported displays, Vestaboard, split-flap display, LED matrix, Divoom Pixoo 64, Pixoo dashboard, TV dashboard, FiestaPanel, Apple TV, Android TV, output plugins]
---

# Supported Displays

:::note Version availability
These instructions describe FiestaBoard v10 (`next` / beta). The output-plugin setup and Divoom Pixoo 64 support are not available in stable v9. Native Apple TV and Android TV apps are coming soon; use a browser for TV viewing.
:::

FiestaBoard shows your pages on three kinds of display: split-flap boards, LED matrices, and TVs. You design a page once, and FiestaBoard draws it the way each display needs. Split-flap boards get flaps, LED matrices get pixels, and a TV gets a life-size board on screen.

You can run several displays at once, and they don't have to be the same kind. A Vestaboard in the kitchen, a Pixoo on a desk, and a TV in the hallway can each show their own pages on their own schedules.

## Which Display Do I Have?

| Display | Devices | How FiestaBoard connects | Guide |
|---|---|---|---|
| **Split-flap** | Vestaboard Flagship (22×6), Note (15×3), and Note arrays | Vestaboard's official Local API on your network, or its Cloud API | [Split-flap boards](./split-flap.md) |
| **LED matrix** | Divoom Pixoo 64 | Directly over your Wi-Fi, no account or cloud needed | [LED matrices](./led-matrix.md) |
| **TV** | Any TV or screen with a web browser. Native Apple TV and Android TV apps are coming soon | The TV opens a FiestaPanel address and pulls each new frame | [TVs](./tv.md) |

Don't have any of these yet? You can still set FiestaBoard up. Choose **Skip — I'll add a display later** in the setup wizard, then build and preview pages in the app. When a display arrives, add it from **Displays**.

## Adding a Display

The first time you open FiestaBoard, the setup wizard asks **What do you want to show FiestaBoard on?** Pick your display and the wizard walks you through connecting it.

To add another display later:

1. Open **Displays** and click **Add a display**.
2. Pick the kind of display. In v10, the three seeded display plugins are bundled with the image; installing or updating other plugins requires internet access.
3. Fill in the display's settings screen. Most displays have a **Test connection** button, and some can search your network for you, like **Find my Pixoo**.
4. Save. The new display appears in the board selector, ready for pages and schedules.

Each display has its own grid size, so a page made for one shape won't always fit another. The page editor's size picker lists your TVs and LED displays by name, next to the standard Vestaboard sizes, so you can make a page for a specific display in one step.

:::warning Adding to an existing installation
Use **Displays → Add a display** to add hardware. Re-running the setup wizard and choosing Vestaboard currently replaces the saved display list and can remove other displays. Skipping setup can also leave a placeholder named **My Board**; it is not evidence that hardware was found.
:::

## Sharing a Display With Another App

If another app writes to a display, such as the Vestaboard app or the Divoom app, FiestaBoard puts your page back on its next update. To share a display with another app on purpose, open the display's settings under **Displays** and turn off **Restore automatically**, next to **Pause sends**. It's on by default. See [Saving what another app put on the board](../features/page-editor.md#saving-what-another-app-put-on-the-board) for how FiestaBoard notices and how to save the other app's content.

## Every Display Is a Plugin

Open a display to switch between **Overview** (its live preview), **Settings**
(connection and display options), and **Playback** (transitions, quiet hours,
schedule re-enable behavior, and update/read intervals). These scheduling
preferences belong to the individual display, not the app-wide Settings page.
The transition selector includes a preview you can replay. Split-flap
previews illustrate the ordering; hardware appearance may differ. Previews do
not send anything to your display.

Behind the scenes, each kind of display is an **output plugin**, just like weather or transit data come from data plugins. That includes the Vestaboard. The **Marketplace** tab on the **Displays** page lists every display plugin: install one, update it, or click **Add display** on its card.

Search and category controls help browse the catalog as it grows. **Install
from Git** opens the advanced installation form when needed. A **Community**
badge identifies a known repository outside the FiestaBoard organization; it
describes the publisher, not a security review.

This is how FiestaBoard grows to support new hardware without changing FiestaBoard itself. If you build displays, you have three ways to connect one:

| You want to… | Use |
|---|---|
| Have FiestaBoard push each page to your device | [Write an output plugin](/docs/development/output-plugins) |
| Have your device pull frames from FiestaBoard | [Output stream API](/docs/development/output-stream-api) |
| Read your data and render it yourself | The REST API and the MCP server |

## About Vestaboard and Divoom

FiestaBoard is an independent, open-source project. It isn't affiliated with, sponsored by, or endorsed by Vestaboard, Inc. or Divoom. "Vestaboard" and "Divoom" are trademarks of their owners. FiestaBoard talks to each device only through the interfaces its maker provides.
